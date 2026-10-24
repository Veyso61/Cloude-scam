# -*- coding: utf-8 -*-
"""Strateji motoru: arayanı tanır, en kârlı dolandırıcılık zincirini seçer, adımları takip eder
ve okunacak İngilizce cümleyi + Türkçe strateji notunu üretir.

Tamamen kural tabanlıdır (çevrimdışı, anlık). İsteğe bağlı LLM katmanı (llm_advisor.py) bu
motorun ürettiği bağlamı kullanarak cümleyi iyileştirebilir.
"""
from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import text_analysis as ta
from game_state import GameState, fmt_money, fmt_time

LEVEL_ORDER = ["B1", "C1", "C2"]
OBJECTION_PRIORITY = [
    "scambaiter", "hangup_threat", "angry", "date_refuse", "screen_activity", "suspicious", "wants_procedure", "identity_question",
    "why_payment", "no_card", "no_money", "refuse", "cash_out_nervous", "hesitate", "confused",
    "question_price", "wants_supervisor",
]
NEGATIVE_INTENTS = {"refuse", "angry", "hangup_threat", "suspicious", "scambaiter", "date_refuse", "wants_procedure",
                    "identity_question", "why_payment", "confused", "hesitate", "no_money", "no_card"}
AUTO_COMPLETE_STEPS = {"enter_in_app", "connect", "scratch", "guess"}
INVEST_LADDER = {"greedy": [2000, 1500, 1000, 800, 500], "ego": [2000, 1500, 1000, 800, 500],
                 "default": [1500, 1000, 800, 500, 300]}
WORRY_RE = re.compile(r"\b(oh no|oh my|oh dear|goodness|really\??|what\?|that'?s (terrible|awful|scary|bad)|i'?m (scared|worried)|"
                      r"what (do|should|can) (i|we) do|how (did|could) that happen|help me|is it (bad|serious)|please (help|fix))\b", re.I)


@dataclass
class Advice:
    say: str = ""
    alternatives: List[str] = field(default_factory=list)
    note_tr: str = ""
    scam_id: Optional[str] = None
    scam_name: str = ""
    step_index: int = 0
    step_total: int = 0
    step_label: str = ""
    step_label_tr: str = ""
    step_goal_tr: str = ""
    player_action_tr: str = ""
    plan: List[str] = field(default_factory=list)
    caller_name: str = ""
    archetype: str = ""
    archetype_tr: str = ""
    level: str = "B1"
    caller_said: str = ""
    caller_gist_tr: str = ""
    caller_tr: str = ""
    data_lines: List[str] = field(default_factory=list)
    location_hints: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    footnote_tr: str = ""
    footnote_severity: str = "info"
    quota_line: str = ""
    severity: str = "info"            # info | success | warn | danger
    source: str = "kural"
    seq: int = 0
    intents: List[str] = field(default_factory=list)


@dataclass
class CallerProfile:
    char_id: Optional[str] = None
    identified_by: str = ""
    spoken_name: Optional[str] = None
    archetype_scores: Counter = field(default_factory=Counter)
    topic_scores: Counter = field(default_factory=Counter)
    char_scores: Counter = field(default_factory=Counter)
    interests: List[str] = field(default_factory=list)
    their_nickname: Optional[str] = None
    locations: Counter = field(default_factory=Counter)
    location_hints: Counter = field(default_factory=Counter)
    scambaiter_score: int = 0
    manual_archetype: Optional[str] = None


@dataclass
class CallSession:
    started_at: float = field(default_factory=time.time)
    profile: CallerProfile = field(default_factory=CallerProfile)
    transcript: List[Tuple[str, str, float]] = field(default_factory=list)
    plan: List[str] = field(default_factory=list)
    current: Optional[str] = None
    step_idx: Dict[str, int] = field(default_factory=dict)
    completed: List[str] = field(default_factory=list)
    abandoned: List[str] = field(default_factory=list)
    attempts: Counter = field(default_factory=Counter)
    neutral_streak: int = 0
    angry_streak: int = 0
    used_lines: set = field(default_factory=set)
    data: Dict[str, str] = field(default_factory=dict)
    code_parts: List[str] = field(default_factory=list)
    code_parts_at: float = 0.0
    last_progress_at: float = field(default_factory=time.time)
    invest_ask_idx: int = 0
    agreed_amount: Optional[int] = None
    earned_this_call: int = 0
    pending_since: Optional[float] = None
    manual_scam: bool = False
    last_pool: List[str] = field(default_factory=list)
    alt_idx: int = 0
    utterances: int = 0
    plan_locked: bool = False
    boss_mode: bool = False


class SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


class StrategyEngine:
    def __init__(self, db: dict, state: GameState, config: Optional[dict] = None):
        self.db = db
        self.state = state
        self.cfg = config or {}
        self.intents = ta.IntentClassifier(db["intents"])
        boss = db.get("boss", {})
        self.boss_patterns = [(re.compile(p, re.I), w) for p, w in boss.get("patterns", [])]
        self.boss_threshold = int(boss.get("threshold", 4))
        self.boss_fired = [re.compile(p, re.I) for p in boss.get("fired_patterns", [])]
        self.boss_passed = [re.compile(p, re.I) for p in boss.get("passed_patterns", [])]
        self.locator = ta.LocationExtractor(db.get("locations", {}))
        self.now = time.time
        self.seq = 0
        self.session = CallSession()
        self.last_advice: Optional[Advice] = None
        self._name_index = {cid: [c["name"]] + c.get("aliases", []) for cid, c in db["characters"].items() if not c.get("generic")}
        self._scam_name_res = [(sid, re.compile(r"\b" + re.escape(s["name"].split(" (")[0].split("'")[0].lower()) + r"\b", re.I))
                               for sid, s in db["scams"].items()]

    # ================================================================== public API
    def new_call(self, char_id: Optional[str] = None) -> Advice:
        self.session = CallSession(started_at=self.now(), last_progress_at=self.now())
        self.state.calls_today += 1
        if char_id:
            self._set_char(char_id, "manuel")
        elif self.state.caller_name_hint:
            self.set_caller_name_hint(self.state.caller_name_hint, quiet=True)
        self._replan(force=True)
        adv = self._advice_for_step(note="Yeni arama. Arayanı dinle; sorununu anlatınca cümle güncellenir.")
        adv.caller_gist_tr = "Arama başladı"
        return self._finish(adv)

    def set_character(self, char_id: Optional[str]) -> Advice:
        if char_id:
            self._set_char(char_id, "manuel")
        else:
            self.session.profile.char_id = None
            self.session.profile.identified_by = ""
        self._replan(force=not self._has_progress())
        return self._finish(self._advice_for_step(note=self._char_note()))

    def set_archetype(self, archetype: Optional[str]) -> Advice:
        self.session.profile.manual_archetype = archetype if archetype in self.db["archetypes"] else None
        self._replan(force=not self._has_progress())
        return self._finish(self._advice_for_step(note="Arketip elle ayarlandı."))

    def set_caller_name_hint(self, name: str, quiet: bool = False) -> Optional[Advice]:
        cid = ta.best_fuzzy(name, self._name_index)
        if cid and cid != self.session.profile.char_id:
            self._set_char(cid, "ekran")
            self._replan(force=not self._has_progress())
            if not quiet:
                return self._finish(self._advice_for_step(note=self._char_note()))
        return None

    def on_caller_text(self, text: str) -> Advice:
        text = ta.normalize(text)
        if not text:
            return self.refresh()
        s = self.session
        now = self.now()
        if self._is_boss(text):
            return self._finish(self._boss_advice(text))
        s.utterances += 1
        s.transcript.append(("caller", text, now))
        intents = self.intents.classify(text)
        data = self._extract(text)
        self._update_profile(text, intents, data)
        if s.utterances <= 3 and not self._has_progress():
            self._replan(force=True)

        prof = s.profile
        char = self._char()
        # ---------------------------------------------------------- scambaiter
        if "scambaiter" in intents or prof.scambaiter_score >= 3 or (char and char.get("scambaiter")):
            line, alts = self._objection_line("scambaiter")
            adv = self._advice_for_step(say=line, alts=alts, note=self.db["objections"]["scambaiter"]["note_tr"])
            adv.severity = "danger"
            adv.warnings = [w for w in adv.warnings if not w.startswith("❤️")]
            adv.warnings.append("⛔ SCAMBAITER: verdiği AnyViewer koduna BAĞLANMA, linke/Nitro hediyesine TIKLAMA. Hang Up → F5.")
            for k in [k for k in s.data if k.startswith("KOD")]:
                s.data["⛔ " + k + " (GİRME!)"] = s.data.pop(k)
            return self._finish(adv, text, intents, data)

        if any(k in intents for k in ("angry", "hangup_threat")):
            s.angry_streak += 1
        else:
            s.angry_streak = 0

        step = self._current_step()
        scam = self._scam()
        # ---------------------------------------------------------- data continuation on an "enter" step
        auto_adv: Optional[Advice] = None
        if step and step["id"] in AUTO_COMPLETE_STEPS and s.pending_since:
            if data.get("codes") and now - s.code_parts_at < 20 and len(s.code_parts) > 1:
                return self._finish(self._advice_for_step(note="Kodun devamı geldi → BİRLEŞİK kodu gir."), text, intents, data)
            if now - s.pending_since >= float(self.cfg.get("auto_enter_seconds", 8)):
                auto_adv = self._advance(auto=True)
                step = self._current_step()
                scam = self._scam()

        # ---------------------------------------------------------- AnyViewer code offered
        if data.get("codes") and re.search(r"\bany ?viewer\b", text, re.I) and s.current != "anyviewer":
            if char is None and self._archetype() not in ("skeptical",) and not s.completed and s.current not in ("tech_support",):
                adv = self._advice_for_step(note="Sormadan AnyViewer kodu veriyor → scambaiter taktiği olabilir (Arthur Lin). Emin değilsen GİRME.")
                adv.severity = "warn"
                for k in [k for k in s.data if k.startswith("KOD")]:
                    s.data["⚠ " + k + " (şüpheli)"] = s.data.pop(k)
                return self._finish(adv, text, intents, data)
            if self.state.is_owned("anyviewer", self.db):
                s.current = "anyviewer"
                s.manual_scam = True
                if "anyviewer" not in s.plan:
                    s.plan.insert(0, "anyviewer")
                s.step_idx["anyviewer"] = 1
                adv = self._advance()
                adv.note_tr = "🖥️ AnyViewer koduna geçildi. " + adv.note_tr
                return self._finish(adv, text, intents, data)

        # ---------------------------------------------------------- step success?
        if step is not None and self._step_success(step, text, intents, data):
            adv = self._advance()
            adv = self._cascade(adv, text, intents, data)
            return self._finish(adv, text, intents, data)

        # ---------------------------------------------------------- caller jumped ahead (e.g. read the code early)
        jump = self._lookahead(text, intents, data)
        if jump:
            s.step_idx[s.current] = jump - 1
            adv = self._advance()
            adv.note_tr = "⏩ Arayan öne geçti, adımlar atlandı. " + adv.note_tr
            return self._finish(adv, text, intents, data)

        # ---------------------------------------------------------- first words: open with the plan
        if s.utterances == 1 and not self._has_progress() and "hangup_threat" not in intents:
            note = self._char_note() if self._char() else "Arayan sorununu anlattı → plana göre açılış."
            return self._finish(self._advice_for_step(note=note), text, intents, data)

        # ---------------------------------------------------------- objections
        for intent in OBJECTION_PRIORITY:
            if intent in intents:
                if intent == "question_price" and step and "price" in step["id"]:
                    continue
                if intent == "date_refuse" and s.current != "romance":
                    continue
                if intent == "cash_out_nervous" and s.current not in ("bitcoin", "meme_coin"):
                    continue
                if intent == "screen_activity" and s.current not in ("anyviewer", "password_recovery", "ransom", "tech_support"):
                    continue
                key = (s.current, step["id"] if step else "")
                if not self._is_action_step(step):
                    s.attempts[key] += 1
                lowered = self._lower_invest_ask(intent, step)
                line, alts = self._objection_line(intent)
                note = self._objection_note(intent)
                if lowered:
                    note += f" Tutarı düşür → {fmt_money(self._invest_ask())}."
                    if "{invest_ask}" not in " ".join(self.db["scams"]["investment"]["objections"].get(intent, {}).get(self._level(), [])):
                        line, alts = self._step_line(step)
                adv = self._advice_for_step(say=line, alts=alts, note=note)
                if intent in ("angry", "hangup_threat", "suspicious", "refuse"):
                    adv.severity = "warn"
                if intent == "cash_out_nervous":
                    adv.warnings.append("📉 Arayan parasını çekmek istiyor → CASH OUT zamanı olabilir!")
                return self._finish(adv, text, intents, data)

        if auto_adv is not None:
            return self._finish(auto_adv, text, intents, data)

        # ---------------------------------------------------------- small talk
        if "small_talk" in intents and not self._has_progress():
            line, alts = self._objection_line("small_talk")
            return self._finish(self._advice_for_step(say=line, alts=alts, note="Kısa samimiyet → hedefe dön."), text, intents, data)

        # ---------------------------------------------------------- neutral: re-ask current step
        if step is not None and not self._is_action_step(step):
            key = (s.current, step["id"])
            if s.utterances > 1:
                s.attempts[key] += 1
            s.neutral_streak += 1
            if s.neutral_streak >= 3 and step["id"] not in ("keep_calm", "hold", "keep_talking"):
                s.neutral_streak = 0
                line, alts = self._objection_line("off_topic")
                step_line, _ = self._step_line(step)
                return self._finish(self._advice_for_step(say=line + " " + step_line, alts=alts, note="Konu dağıldı → nazikçe hedefe çek."), text, intents, data)
        return self._finish(self._advice_for_step(), text, intents, data)

    def step_done(self) -> Advice:
        return self._finish(self._advance(manual=True))

    def step_back(self) -> Advice:
        s = self.session
        if s.current:
            idx = s.step_idx.get(s.current, 0)
            if idx > 0:
                s.step_idx[s.current] = idx - 1
            elif s.completed:
                prev = s.completed.pop()
                s.current = prev
                s.step_idx[prev] = max(0, len(self.db["scams"][prev]["steps"]) - 1)
                reward = self._reward(prev)
                self.state.add_earnings(-reward)
                s.earned_this_call -= reward
        s.pending_since = None
        return self._finish(self._advice_for_step(note="Bir adım geri alındı."))

    def next_scam(self, delta: int = 1) -> Advice:
        s = self.session
        avail = [sid for sid in self._ranked_scams() if sid not in s.completed]
        if not avail:
            return self._finish(self._advice_for_step(note="Başka açık dolandırıcılık yok."))
        if s.current in avail:
            i = (avail.index(s.current) + delta) % len(avail)
        else:
            i = 0
        if s.current and s.step_idx.get(s.current, 0) > 0 and s.current not in s.abandoned:
            s.abandoned.append(s.current)
        s.current = avail[i]
        s.manual_scam = True
        s.pending_since = None
        s.plan = [s.current] + [x for x in s.plan if x != s.current]
        line, alts = self._bridge_line(s.current) if (s.completed or s.utterances) else self._step_line(self._current_step())
        return self._finish(self._advice_for_step(say=line, alts=alts, note=f"Elle geçildi → {self._sname(s.current)}."))

    def alt_line(self) -> Advice:
        s = self.session
        adv = self.last_advice or self._advice_for_step()
        pool = s.last_pool or [adv.say]
        if len(pool) <= 1:
            return self._finish(adv)
        s.alt_idx = (s.alt_idx + 1) % len(pool)
        adv.say = pool[s.alt_idx]
        adv.alternatives = [p for p in pool if p != adv.say][:2]
        return self._finish(adv)

    def refresh(self) -> Advice:
        adv = self.last_advice or self._advice_for_step()
        adv.footnote_tr, adv.footnote_severity = self._footnote()
        adv.quota_line = self._quota_line()
        return adv

    def apply_llm(self, result: dict, seq: int) -> Optional[Advice]:
        if not self.last_advice or seq != self.seq:
            return None
        adv = self.last_advice
        say = (result.get("say") or "").strip()
        if result.get("step_done") and self._current_step() is not None:
            step = self._current_step()
            if not step.get("expects") and step["id"] not in ("keep_calm", "hold", "keep_talking"):
                adv = self._advance()
        if say:
            if adv.say and adv.say != say:
                adv.alternatives = [adv.say] + [a for a in adv.alternatives if a != say][:1]
            adv.say = say
            self.session.last_pool = [say] + adv.alternatives
            self.session.alt_idx = 0
        if result.get("note_tr"):
            adv.note_tr = result["note_tr"]
        if result.get("caller_tr"):
            adv.caller_tr = result["caller_tr"]
        adv.source = "AI"
        self.last_advice = adv
        return adv

    # ------------------------------------------------------------------ briefing
    def day_briefing(self) -> str:
        st, db = self.state, self.db
        wk = db["game_rules"]["weeks"].get(str(st.week), {})
        lines = [f"📅 {st.week}. Hafta • {st.day_in_week}. Gün (Gün {st.day}/15)" + (f" • Prestij {st.prestige}" if st.prestige else ""),
                 f"Kota: {fmt_money(st.quota_value(db))} ({st.quota_source})"]
        new = st.new_today(db)
        if new:
            lines.append("🆕 Bugün açılan: " + ", ".join(self._sname(x) for x in new))
        usable = [x for x in st.usable_scams(db)]
        usable.sort(key=lambda x: -self._reward(x))
        if usable:
            lines.append("💰 En kârlı açık: " + ", ".join(f"{self._sname(x)} ({fmt_money(self._reward(x))})" for x in usable[:5]))
        buy = st.purchasable(db)
        if buy:
            lines.append("🛒 Scamazon'da alınabilir: " + ", ".join(f"{self._sname(x)} ({fmt_money(db['scams'][x]['cost'])})" for x in buy))
        if wk.get("focus_tr"):
            lines.append("🎯 " + wk["focus_tr"])
        return "\n".join(lines)

    # ------------------------------------------------------------------ LLM context
    def llm_context(self) -> dict:
        s, st, db = self.session, self.state, self.db
        char = self._char()
        arch = self._archetype()
        scam = self._scam()
        step = self._current_step()
        idx = s.step_idx.get(s.current, 0) if s.current else 0
        steps = scam["steps"] if scam else []
        nxt = steps[idx + 1]["label"] if scam and idx + 1 < len(steps) else (self._sname(s.plan[1]) + " (sonraki scam)" if len(s.plan) > 1 else None)
        convo = []
        for who, t, _ in s.transcript[-12:]:
            convo.append({"who": "caller" if who == "caller" else "player", "text": t})
        return {
            "game_state": {"week": st.week, "day_in_week": st.day_in_week, "day": st.day,
                           "quota": st.quota_value(db), "earned": st.earned, "gap": st.gap(db),
                           "time_left_seconds": None if st.time_left() is None else int(st.time_left())},
            "caller": {
                "name": self._display_name(),
                "known_character": char["name"] if char else None,
                "archetype": arch, "archetype_tr": db["archetypes"][arch]["name_tr"],
                "profile": (char or {}).get("profile_tr", ""), "weakness": (char or {}).get("weakness_tr", ""),
                "fatal_mistakes": (char or {}).get("fatal_tr", []) + db["archetypes"][arch].get("dont_tr", []),
                "problem": self._slot_values().get("problem"),
                "interests": s.profile.interests[-3:], "nickname_they_gave_player": s.profile.their_nickname,
            },
            "current_scam": None if not scam else {
                "id": s.current, "name": scam["name"], "summary": scam.get("summary_tr", ""),
                "checklist": [x["label"] for x in steps], "current_step_index": idx,
                "current_step": step["label"] if step else None,
                "current_goal": step["goal_tr"] if step else None,
                "player_action": step.get("player_action_tr") if step else None,
                "next_objective": nxt, "reward_usd": self._reward(s.current),
            },
            "plan_after": [self._sname(x) for x in s.plan[1:4]],
            "completed_on_this_call": [self._sname(x) for x in s.completed],
            "level": self._level(),
            "rule_based_suggestion": self.last_advice.say if self.last_advice else "",
            "detected_intents": self.last_advice.intents if self.last_advice else [],
            "agent_name": self.cfg.get("agent_name", "Steve"),
            "company": self.cfg.get("company_name", "Customer Protection Center"),
            "transcript": convo,
        }

    # ================================================================== internals: identity
    def _char(self) -> Optional[dict]:
        cid = self.session.profile.char_id
        return self.db["characters"].get(cid) if cid else None

    def _set_char(self, cid: str, how: str) -> None:
        if cid in self.db["characters"]:
            self.session.profile.char_id = cid
            self.session.profile.identified_by = how

    def _char_note(self) -> str:
        c = self._char()
        if not c:
            return "Karakter: otomatik algılama."
        parts = [f"🎭 {c['name']}"]
        if c.get("weakness_tr"):
            parts.append("Zaaf: " + c["weakness_tr"])
        return " • ".join(parts)

    def _archetype(self) -> str:
        prof = self.session.profile
        if prof.manual_archetype:
            return prof.manual_archetype
        c = self._char()
        if c:
            return c["archetype"]
        if prof.archetype_scores:
            arch, sc = prof.archetype_scores.most_common(1)[0]
            if sc >= 2:
                return arch
        return "trusting"

    def _topic(self) -> Optional[str]:
        c = self._char()
        if c and c.get("topic"):
            return c["topic"]
        if self.session.profile.topic_scores:
            return self.session.profile.topic_scores.most_common(1)[0][0]
        return None

    def _level(self) -> str:
        forced = (self.cfg.get("language_level") or "auto").upper()
        if forced in LEVEL_ORDER:
            return forced
        c = self._char()
        lvl = (c or {}).get("level") or self.db["archetypes"][self._archetype()].get("level", "B1")
        cap = (self.cfg.get("max_level") or "C2").upper()
        if cap in LEVEL_ORDER and LEVEL_ORDER.index(lvl) > LEVEL_ORDER.index(cap):
            lvl = cap
        return lvl

    def _display_name(self) -> str:
        c = self._char()
        if c:
            return c["name"]
        return self.session.profile.spoken_name or "Bilinmeyen arayan"

    def _update_profile(self, text: str, intents: Dict[str, int], data: dict) -> None:
        prof = self.session.profile
        low = text.lower()
        for aid, a in self.db["archetypes"].items():
            h = ta.keyword_hits(low, a.get("keywords", []))
            if h:
                prof.archetype_scores[aid] += h
        for tid, t in self.db["topics"].items():
            h = ta.keyword_hits(low, t.get("keywords", []))
            if h:
                prof.topic_scores[tid] += h
        prof.scambaiter_score += ta.keyword_hits(low, self.db["archetypes"]["scambaiter"]["keywords"])
        if "scambaiter" in intents:
            prof.scambaiter_score += 2
        name = ta.extract_self_name(text)
        if name:
            prof.spoken_name = name
        if not prof.char_id or prof.identified_by == "anahtar":
            cid = None
            if name:
                cid = ta.best_fuzzy(name, self._name_index)
            if not cid:
                for c_id, names in self._name_index.items():
                    for n in names:
                        if len(n) >= 4 and re.search(r"(?<![a-z])" + re.escape(n.lower()) + r"(?![a-z])", low):
                            cid = c_id
                            break
                    if cid:
                        break
            if cid:
                self._set_char(cid, "isim")
            else:
                for c_id, c in self.db["characters"].items():
                    if c.get("generic"):
                        continue
                    h = ta.keyword_hits(low, c.get("keywords", []))
                    if h:
                        prof.char_scores[c_id] += h
                if prof.char_scores and not prof.char_id:
                    c_id, sc = prof.char_scores.most_common(1)[0]
                    if sc >= 3:
                        self._set_char(c_id, "anahtar")
        if data.get("interest") and data["interest"] not in prof.interests:
            prof.interests.append(data["interest"])
        if data.get("nickname"):
            prof.their_nickname = data["nickname"]
        for p in data.get("places", []):
            prof.locations[p] += 1
        for h in data.get("hints", []):
            prof.location_hints[h] += 1

    def _is_boss(self, text: str) -> bool:
        score = sum(w for rx, w in self.boss_patterns if rx.search(text))
        return score >= self.boss_threshold

    def _boss_advice(self, text: str) -> Advice:
        st = self.state
        notes = ["🧑‍💼 Patron (Mr. Curry) konuşuyor — Boss Review. Arayan değil."]
        sev = "info"
        if any(rx.search(text) for rx in self.boss_fired):
            sev = "danger"
            tl = st.time_left()
            if self.cfg.get("auto_reset_on_fired", True) and (tl is None or tl <= 30):
                st.fired()
                notes.append("💀 KOVULDUN → 1. Güne sıfırlandı (yanlışsa Durum panelinden düzelt).")
            else:
                notes.append("💀 'Fired' duyuldu. Gerçekten kovulduysan Durum panelinden 1. Güne al.")
        elif any(rx.search(text) for rx in self.boss_passed):
            st.day_end_detected = True
            sev = "success"
            notes.append("✅ Gün geçti gibi. Sonraki vardiyayı F10 ile başlatınca gün otomatik ilerler.")
        mentioned = [sid for sid, rx in self._scam_name_res if rx.search(text)]
        if "tomorrow" in text.lower() and mentioned:
            for sid in mentioned:
                if sid not in st.pending_unlocks:
                    st.pending_unlocks.append(sid)
            notes.append("🆕 Yarın açılacak: " + ", ".join(self._sname(x) for x in mentioned))
        adv = Advice(say="(Patron konuşuyor — cevap gerekmiyor)", note_tr=" ".join(notes), severity=sev,
                     caller_said=text, caller_gist_tr="Patron değerlendirmesi")
        self.session.boss_mode = True
        return adv

    # ================================================================== internals: extraction
    def _extract(self, text: str) -> dict:
        s = self.session
        now = self.now()
        d: dict = {}
        step = self._current_step()
        expects = (step or {}).get("expects")
        waiting_code = expects in ("code", "card", "ssn") or (step is not None and step["id"] in AUTO_COMPLETE_STEPS and now - s.code_parts_at < 20)
        ssn = ta.extract_ssn(text) if expects == "ssn" or re.search(r"\d{3}-\d{2}-\d{4}", text) else None
        codes = [] if ssn else ta.extract_code_runs(text)
        codes = [c for c in codes if waiting_code or sum(ch.isdigit() for ch in c) >= 6]
        if codes:
            d["codes"] = codes
            if now - s.code_parts_at > 20 or not waiting_code:
                s.code_parts = []
            s.code_parts.extend(codes)
            s.code_parts_at = now
            s.data["KOD"] = ta.group_code(codes[-1]) if len(codes) == 1 else " / ".join(ta.group_code(c) for c in codes)
            if len(s.code_parts) > 1:
                s.data["KOD (birleşik)"] = ta.group_code("".join(s.code_parts))
            else:
                s.data.pop("KOD (birleşik)", None)
        card = ta.extract_card(text) if (expects == "card" or len(re.sub(r"\D", "", text)) >= 13) else {}
        if card.get("number"):
            d["card"] = card
            txt = ta.group_code(card["number"])
            if card.get("expiry"):
                txt += f"  SKT {card['expiry']}"
            if card.get("cvv"):
                txt += f"  CVV {card['cvv']}"
            s.data["KART"] = txt
        elif s.data.get("KART") and (card.get("expiry") or card.get("cvv")):
            extra = (f"  SKT {card['expiry']}" if card.get("expiry") else "") + (f"  CVV {card['cvv']}" if card.get("cvv") else "")
            s.data["KART"] += extra
        if ssn:
            d["ssn"] = ssn
            s.data["SSN"] = ta.format_ssn(ssn)
        email = ta.extract_email(text)
        if email:
            d["email"] = email
            s.data["E-POSTA"] = email
        amount = ta.extract_amount(text)
        if amount:
            d["amount"] = amount
            s.data["TUTAR"] = fmt_money(amount)
        interest = ta.extract_interest(text)
        if interest:
            d["interest"] = interest
            s.data["HOBİ"] = interest
        nick = ta.extract_nickname(text) if s.current == "romance" else None
        if nick:
            d["nickname"] = nick
            s.data["SANA LAKABI"] = nick
        places, hints = self.locator.extract(text)
        if places or hints:
            d["places"], d["hints"] = places, hints
        d["address"] = ta.has_address(text)
        d["dob"] = ta.has_dob(text)
        return d

    # ================================================================== internals: planning
    def _reward(self, sid: Optional[str]) -> int:
        if not sid:
            return 0
        s = self.db["scams"][sid]
        if s.get("reward_is_agreed_amount") and sid == self.session.current and self.session.agreed_amount:
            return int(self.session.agreed_amount)
        return int(s["reward"]["typical"])

    def _invest_ladder(self) -> List[int]:
        return INVEST_LADDER.get(self._archetype(), INVEST_LADDER["default"])

    def _invest_ask(self) -> int:
        lad = self._invest_ladder()
        return lad[min(self.session.invest_ask_idx, len(lad) - 1)]

    def _scam_score(self, sid: str) -> float:
        db, s = self.db, self.db["scams"][sid]
        char = self._char()
        arch = self._archetype()
        a = db["archetypes"][arch]
        reward = self._reward(sid)
        if sid in ("bitcoin", "meme_coin", "lottery_prize"):
            reward *= 0.85
        aff = float(a.get("scam_affinity", {}).get(sid, 0.85))
        if char:
            best = char.get("best_scams", [])
            if sid in best:
                aff *= 1.7 - 0.08 * best.index(sid)
            if sid in char.get("avoid_scams", []):
                aff *= 0.15
        topic = self._topic()
        if topic:
            aff *= 1.6 if sid in db["topics"].get(topic, {}).get("best_scams", []) else 0.85
        tcost = float(s.get("est_seconds", 180)) * float(a.get("time_factor", 1.0))
        rate = reward * aff / max(30.0, tcost)
        tl = self.state.time_left()
        if tl is not None and tl < tcost:
            rate *= max(0.02, tl / tcost) ** 2
        return rate

    def _ranked_scams(self) -> List[str]:
        st = self.state
        cands = [sid for sid in st.usable_scams(self.db) if not self.db["scams"][sid].get("parallel")]
        return sorted(cands, key=self._scam_score, reverse=True)

    def _replan(self, force: bool = False) -> None:
        s = self.session
        if s.manual_scam and not force:
            return
        ranked = [x for x in self._ranked_scams() if x not in s.completed and x not in s.abandoned]
        if not ranked:
            s.plan = []
            if force:
                s.current = None
            return
        plan = [ranked[0]]
        while len(plan) < 4:
            prev = self.db["scams"][plan[-1]]
            best, best_sc = None, -1.0
            for sid in ranked:
                if sid in plan:
                    continue
                sc = self._scam_score(sid) * (1.3 if sid in prev.get("chains_to", []) else 1.0)
                if sc > best_sc:
                    best, best_sc = sid, sc
            if not best:
                break
            plan.append(best)
        final: List[str] = []
        for sid in plan:
            for req in self.db["scams"][sid].get("requires", []):
                if req not in final and req not in s.completed and self.state.is_owned(req, self.db):
                    final.append(req)
            final.append(sid)
        s.plan = final
        if force or s.current is None or s.current in s.completed:
            if not (s.current and s.step_idx.get(s.current, 0) > 0 and s.current not in s.completed):
                s.current = final[0]
                s.manual_scam = False

    def _has_progress(self) -> bool:
        s = self.session
        return bool(s.completed) or any(v > 0 for v in s.step_idx.values())

    def _scam(self) -> Optional[dict]:
        return self.db["scams"].get(self.session.current) if self.session.current else None

    def _sname(self, sid: Optional[str]) -> str:
        return self.db["scams"][sid]["name"] if sid in self.db["scams"] else "-"

    def _current_step(self) -> Optional[dict]:
        scam = self._scam()
        if not scam or not scam.get("steps"):
            return None
        idx = self.session.step_idx.get(self.session.current, 0)
        return scam["steps"][idx] if idx < len(scam["steps"]) else None

    def _cascade(self, adv: Advice, text: str, intents: Dict[str, int], data: dict) -> Advice:
        """Aynı cümle sonraki adımı da karşılıyorsa (ör. 'evet, Apple kartım var') onu da tamamla."""
        for _ in range(3):
            nstep = self._current_step()
            if not nstep or self._is_action_step(nstep):
                break
            toks = [t for t in nstep.get("success", []) if t in self.SPECIFIC_TOKENS or not t.startswith("@")]
            if not toks or not self._step_success(dict(nstep, success=toks), text, intents, data):
                break
            adv = self._advance()
        return adv

    SPECIFIC_TOKENS = {"@code", "@card", "@ssn", "@email", "@love", "@date", "@nickname", "@interest", "@paid", "@amount", "@address", "@dob"}

    def _lookahead(self, text: str, intents: Dict[str, int], data: dict) -> Optional[int]:
        """Arayan sonraki bir adımın hedefini şimdiden karşıladıysa o adımın indeksini (+1) döndürür."""
        s = self.session
        scam = self._scam()
        if not scam or not scam.get("steps"):
            return None
        idx = s.step_idx.get(s.current, 0)
        negative = any(i in intents for i in ("refuse", "angry", "hangup_threat", "suspicious", "why_payment", "no_card", "no_money"))
        for j in range(idx + 1, min(idx + 4, len(scam["steps"]))):
            st = scam["steps"][j]
            toks = [t for t in st.get("success", []) if t in self.SPECIFIC_TOKENS or not t.startswith("@")]
            if not toks:
                continue
            if negative and not any(t in ("@code", "@card", "@ssn", "@email") for t in toks):
                continue
            if self._step_success(dict(st, success=toks), text, intents, data):
                return j + 1
        return None

    @staticmethod
    def _is_action_step(step: Optional[dict]) -> bool:
        return bool(step) and step.get("success") == ["@none"]

    def _step_success(self, step: dict, text: str, intents: Dict[str, int], data: dict) -> bool:
        negative = any(i in intents for i in NEGATIVE_INTENTS)
        s = self.session
        for tok in step.get("success", []):
            if tok == "@none":
                continue
            if tok == "@code" and data.get("codes"):
                return True
            if tok == "@card" and data.get("card"):
                return True
            if tok == "@ssn" and data.get("ssn"):
                return True
            if tok == "@email" and data.get("email"):
                return True
            if tok == "@amount" and data.get("amount") and not negative:
                s.agreed_amount = data["amount"]
                return True
            if tok == "@interest" and data.get("interest"):
                return True
            if tok == "@nickname" and (data.get("nickname") or "nickname_given" in intents):
                return True
            if tok == "@love" and "love" in intents:
                return True
            if tok == "@date" and "date_agree" in intents:
                return True
            if tok == "@location" and (data.get("places") or len(data.get("hints", [])) >= 2):
                return True
            if negative:
                continue
            if tok == "@agree" and "agree" in intents:
                return True
            if tok == "@positive" and "positive" in intents:
                return True
            if tok == "@flirt" and "flirt_back" in intents:
                return True
            if tok == "@paid" and "paid" in intents:
                return True
            if tok == "@question_price" and "question_price" in intents:
                return True
            if tok == "@any_worry" and WORRY_RE.search(text):
                return True
            if tok == "@address" and data.get("address"):
                return True
            if tok == "@dob" and data.get("dob"):
                return True
            if tok == "@text" and ta.word_count(text) >= 1 and not text.strip().endswith("?"):
                s.data["CEVAP"] = text.strip()
                return True
            if tok == "@any" and ta.word_count(text) >= 2:
                return True
            if not tok.startswith("@") and re.search(tok, text, re.I):
                return True
        return False

    def _advance(self, manual: bool = False, auto: bool = False) -> Advice:
        s = self.session
        if not s.current:
            self._replan(force=True)
            return self._advice_for_step(note="Plan yenilendi.")
        scam = self._scam()
        idx = s.step_idx.get(s.current, 0) + 1
        s.step_idx[s.current] = idx
        s.last_progress_at = self.now()
        s.neutral_streak = 0
        s.pending_since = None
        if not (self._current_step_after(idx) or {}).get("id") in AUTO_COMPLETE_STEPS:
            s.code_parts = []
        if idx >= len(scam["steps"]):
            return self._complete_scam(auto=auto)
        step = self._current_step()
        note = "✅ Adım tamam" + (" (elle)" if manual else "") + f" → {step['label_tr']}"
        if step["id"] in AUTO_COMPLETE_STEPS:
            s.pending_since = self.now()
        return self._advice_for_step(note=note, success=True)

    def _current_step_after(self, idx: int) -> Optional[dict]:
        scam = self._scam()
        return scam["steps"][idx] if scam and idx < len(scam.get("steps", [])) else None

    def _complete_scam(self, auto: bool = False) -> Advice:
        s = self.session
        done = s.current
        reward = self._reward(done)
        if done not in s.completed:
            s.completed.append(done)
        if reward:
            self.state.add_earnings(reward)
            s.earned_this_call += reward
        s.manual_scam = False
        s.current = None
        s.agreed_amount = None if done == "investment" else s.agreed_amount
        self._replan(force=True)
        msg = f"🎉 {self._sname(done)} TAMAM (+{fmt_money(reward)} tahmini; gerçek tutarı Durum'dan düzelt)."
        if auto:
            msg = "⌨️ Kodu girdiğini varsaydım. " + msg
        if not s.current:
            adv = self._advice_for_step(say="Thank you so much for your time. Have a wonderful day!", note=msg + " Açık başka scam yok → kapat / yeni arama.")
            adv.severity = "success"
            return adv
        line, alts = self._bridge_line(s.current)
        adv = self._advice_for_step(say=line, alts=alts, note=msg + f" Aynı arayana devam → {self._sname(s.current)}.", success=True)
        adv.severity = "success"
        return adv

    # ================================================================== internals: lines
    def _slot_values(self) -> Dict[str, str]:
        s, char = self.session, self._char()
        topic = self.db["topics"].get(self._topic() or "", {})
        first = (char or {}).get("first_name")
        spoken = s.profile.spoken_name
        if spoken and not first:
            first = spoken.split()[0] if spoken.split()[0] not in ("Mr.", "Mrs.", "Ms.", "Dr.") else spoken
        arch = self.db["archetypes"][self._archetype()]
        sid = s.current
        amount = self._reward(sid) if sid else 200
        if sid in ("investment",):
            amount = self._invest_ask()
        if not amount:
            amount = 200
        return {
            "name": first or "my friend",
            "formal_name": (char or {}).get("formal_name") or spoken or "dear customer",
            "agent": self.cfg.get("agent_name", "Steve"),
            "company": self.cfg.get("company_name", "Customer Protection Center"),
            "problem": (char or {}).get("problem_en") or topic.get("problem_en") or "the problem you called about",
            "service": (char or {}).get("service_en") or topic.get("service_en") or "Premium Protection Plan",
            "interest": s.profile.interests[-1] if s.profile.interests else "really",
            "pet_name": (char or {}).get("pet_name") or arch.get("pet_name") or "sweetheart",
            "their_nickname": s.profile.their_nickname or "my love",
            "amount_words": ta.amount_to_words(amount),
            "invest_ask": ta.amount_to_words(self._invest_ask()),
            "date_time": self.cfg.get("date_time", "8:00 PM"),
            "date_place": self.cfg.get("date_place", "the mall food court"),
        }

    def _fill(self, template: str) -> str:
        out = template.format_map(SafeDict(self._slot_values()))
        out = re.sub(r"\s+([,.!?])", r"\1", out)
        out = re.sub(r"\s{2,}", " ", out).strip()
        return out[0].upper() + out[1:] if out else out

    def _level_pool(self, lines_by_level: Dict[str, List[str]]) -> List[str]:
        lvl = self._level()
        order = [lvl] + [l for l in (LEVEL_ORDER if lvl == "B1" else list(reversed(LEVEL_ORDER))) if l != lvl]
        pool: List[str] = []
        for l in order:
            pool.extend(lines_by_level.get(l, []))
        return pool

    def _choose(self, pool: List[str]) -> Tuple[str, List[str]]:
        s = self.session
        filled = []
        for p in pool:
            f = self._fill(p)
            if f and f not in filled:
                filled.append(f)
        if not filled:
            return "", []
        pick = next((f for f in filled if f not in s.used_lines), None)
        if pick is None:
            for f in filled:
                s.used_lines.discard(f)
            pick = filled[0]
        s.used_lines.add(pick)
        ordered = [pick] + [f for f in filled if f != pick]
        s.last_pool = ordered
        s.alt_idx = 0
        return pick, ordered[1:3]

    def _step_line(self, step: Optional[dict]) -> Tuple[str, List[str]]:
        if not step:
            return "", []
        s = self.session
        char = self._char()
        custom = (char or {}).get("custom_lines", {}).get(f"{s.current}:{step['id']}", [])
        pool = list(custom) + self._level_pool(step["lines"])
        if custom and s.attempts.get((s.current, step["id"]), 0) == 0:
            pick_first = self._fill(custom[0])
            if pick_first not in s.used_lines:
                s.used_lines.add(pick_first)
                rest = [self._fill(p) for p in pool[1:]]
                rest = [r for r in dict.fromkeys(rest) if r != pick_first]
                s.last_pool = [pick_first] + rest
                s.alt_idx = 0
                return pick_first, rest[:2]
        return self._choose(pool)

    def _bridge_line(self, sid: str) -> Tuple[str, List[str]]:
        scam = self.db["scams"][sid]
        step0 = scam["steps"][0] if scam.get("steps") else None
        char = self._char()
        custom = (char or {}).get("custom_lines", {}).get(f"{sid}:{step0['id']}", []) if step0 else []
        pool = list(custom) + self._level_pool(scam.get("bridge", {})) + (self._level_pool(step0["lines"]) if step0 else [])
        if self.session.completed and self.session.completed[-1] == "credit_card" and sid == "gift_card":
            pool.insert(0, "I am sorry, the system says your card was declined by the issuer. Do you have another way to pay, like a gift card?")
        return self._choose(pool)

    def _objection_line(self, intent: str) -> Tuple[str, List[str]]:
        scam = self._scam()
        lvl_pool: List[str] = []
        if scam and intent in scam.get("objections", {}):
            lvl_pool.extend(self._level_pool(scam["objections"][intent]))
        spec = self.db["objections"].get(intent, {})
        arch_lines = spec.get(self._archetype(), [])
        pool = lvl_pool + list(arch_lines) + self._level_pool(spec.get("levels", {}))
        if intent == "question_price" and scam and scam.get("steps"):
            pool = self._level_pool(spec.get("levels", {}))
        return self._choose(pool)

    def _lower_invest_ask(self, intent: str, step: Optional[dict]) -> bool:
        s = self.session
        if s.current != "investment" or not step or step["id"] != "agree_amount":
            return False
        if intent not in ("refuse", "no_money", "hesitate"):
            return False
        if s.invest_ask_idx >= len(self._invest_ladder()) - 1:
            return False
        s.invest_ask_idx += 1
        return True

    def _objection_note(self, intent: str) -> str:
        base = self.db["objections"].get(intent, {}).get("note_tr", "")
        s = self.session
        step = self._current_step()
        n = s.attempts.get((s.current, step["id"] if step else ""), 0)
        if n >= 3:
            base += " (Bu adımda 3+ itiraz: F8 ile aynı arayana başka scam dene.)"
        return base

    # ================================================================== internals: advice
    def _advice_for_step(self, say: Optional[str] = None, alts: Optional[List[str]] = None, note: str = "", success: bool = False) -> Advice:
        s, db = self.session, self.db
        scam = self._scam()
        step = self._current_step()
        if say is None:
            if step is not None:
                say, alts = self._step_line(step)
            elif scam is None:
                say, alts = "Thank you for calling. Have a wonderful day!", []
            else:
                say, alts = "", []
        arch = self._archetype()
        adv = Advice(say=say or "", alternatives=list(alts or []), note_tr=note)
        adv.archetype = arch
        adv.archetype_tr = db["archetypes"][arch]["name_tr"] + ("" if self._char() or s.profile.manual_archetype or s.profile.archetype_scores else " (tahmini)")
        adv.level = self._level()
        adv.caller_name = self._display_name()
        if scam:
            adv.scam_id = s.current
            adv.scam_name = scam["name"]
            adv.step_total = len(scam.get("steps", []))
            idx = s.step_idx.get(s.current, 0)
            adv.step_index = min(idx + 1, adv.step_total)
            if step:
                adv.step_label = step["label"]
                adv.step_label_tr = step["label_tr"]
                adv.step_goal_tr = step["goal_tr"]
                adv.player_action_tr = step.get("player_action_tr") or ""
        adv.plan = [self._sname(x) + f" ({fmt_money(self._reward(x))})" for x in s.plan if x not in s.completed][:4]
        if success:
            adv.severity = "success"
        if not note and step is not None:
            adv.note_tr = f"🎯 {step['label_tr']}: {step['goal_tr']}"
        char = self._char()
        if char and s.utterances <= 1 and not s.completed and char.get("fatal_tr"):
            adv.warnings.append("YAPMA: " + "; ".join(char["fatal_tr"]))
        if char and char.get("hang_up"):
            adv.warnings.append(f"⛔ {char['name']}: tuzak karakter — kapatman önerilir.")
            adv.severity = "danger"
        if s.current == "romance" and s.step_idx.get("romance", 0) < 3 and not (char and char.get("scambaiter")):
            adv.warnings.append("❤️ 'I love you' dedirtmeden randevu isteme!")
        return adv

    def _quota_line(self) -> str:
        st, db = self.state, self.db
        q = st.quota_value(db)
        tl = st.time_left()
        gap = q - st.earned
        txt = f"H{st.week} G{st.day_in_week} (Gün {st.day}/15) • {fmt_money(st.earned)} / {fmt_money(q)}"
        txt += " ✅" if gap <= 0 else f" (eksik {fmt_money(gap)})"
        if tl is not None:
            txt += f" • ⏱ {fmt_time(tl)}"
        if st.trust is not None:
            txt += f" • Güven %{st.trust}"
        return txt

    def _remaining_secs_current(self) -> float:
        s = self.session
        scam = self._scam()
        if not scam:
            return 0.0
        idx = s.step_idx.get(s.current, 0)
        factor = float(self.db["archetypes"][self._archetype()].get("time_factor", 1.0))
        return sum(float(st.get("est_seconds", 30)) for st in scam["steps"][idx:]) * factor

    def _footnote(self) -> Tuple[str, str]:
        st, db, s = self.state, self.db, self.session
        q = st.quota_value(db)
        gap = q - st.earned
        tl = st.time_left()
        cur = s.current
        cur_reward = self._reward(cur) if cur and not db["scams"][cur].get("is_tool") else 0
        rem = self._remaining_secs_current()
        factor = float(db["archetypes"][self._archetype()].get("time_factor", 1.0))
        stuck = cur and s.attempts.get((cur, (self._current_step() or {}).get("id", "")), 0) >= 4
        par = [sid for sid in st.usable_scams(db) if db["scams"][sid].get("parallel") and sid not in s.completed]
        par_txt = (" 📡 Paralel: " + ", ".join(f"{self._sname(x)} (≤{fmt_money(db['scams'][x]['reward']['max'])})" for x in par)) if par else ""
        if gap <= 0:
            if tl is not None and tl < 60:
                return "✅ Kota tamam. Süre az: günü bitirebilirsin (End Day)." + par_txt, "success"
            if not cur:
                return f"✅ Kota tamam (+{fmt_money(-gap)}). Bu arayanda açık scam kalmadı → kapat; S-Tier için yeni arama ya da End Day.", "success"
            return f"✅ Kota tamam (+{fmt_money(-gap)}). S-Tier için aynı arayandan devam: {self._sname(cur)}." + par_txt, "success"
        if s.angry_streak >= 3 or (st.trust is not None and st.trust <= int(db["game_rules"]["trust"]["hang_up_below"])):
            if tl is None or tl >= db["game_rules"]["min_seconds_for_new_call"]:
                return "📵 Güven çöktü / üst üste öfke: 1 özür turu dene, olmazsa KAPAT → F5 yeni arama.", "danger"
        if tl is not None:
            if tl <= 0:
                return "⏰ Süre bitti → Boss Review. Yeni vardiyayı F10 ile başlat (gün otomatik ilerler).", "warn"
            if tl < 180:
                if rem <= tl and cur_reward >= gap:
                    return f"🔥 DEVAM! {fmt_time(tl)} kaldı, eksik {fmt_money(gap)} — {self._sname(cur)} bitince kota tamam (~{int(rem)} sn).", "warn"
                if rem > tl:
                    quick = None
                    for sid in self._ranked_scams():
                        if sid in s.completed or sid == cur:
                            continue
                        need = float(db["scams"][sid].get("est_seconds", 180)) * factor
                        if need <= tl and (quick is None or self._reward(sid) > self._reward(quick)):
                            quick = sid
                    if quick:
                        return (f"⚠ {fmt_time(tl)} kaldı, eksik {fmt_money(gap)}: {self._sname(cur)} yetişmez (~{int(rem)} sn) → "
                                f"aynı arayana hızlı {self._sname(quick)} ({fmt_money(self._reward(quick))}) ile geç (F8)."), "danger"
                    if tl >= db["game_rules"]["min_seconds_for_new_call"] and stuck:
                        return f"⚠ {fmt_time(tl)} kaldı: bu arayan ilerlemiyor → KAPAT, yeni aramada direkt Gift Card.", "danger"
                    if cur and cur_reward:
                        return (f"⏳ {fmt_time(tl)} kaldı, eksik {fmt_money(gap)}: {self._sname(cur)} ({fmt_money(cur_reward)}) bu arayanda en hızlı yol — "
                                f"kısa cümlelerle hızla kapat; yeni arama yetişmez."), "warn"
                    return f"⏳ Son dakikalar ({fmt_time(tl)}, eksik {fmt_money(gap)}): yeni arama yetişmez, bu arayandan elinden geleni al.", "warn"
                nxt = next((x for x in s.plan if x != cur and x not in s.completed), None)
                return (f"⏳ {fmt_time(tl)} kaldı: {self._sname(cur)} {fmt_money(cur_reward)} getirir, eksik {fmt_money(gap)} → "
                        f"bitince hemen {self._sname(nxt)} ile zincirle."), "warn"
        char = self._char()
        give_up = (char or {}).get("give_up_seconds")
        if give_up and not self._has_progress() and self.now() - s.started_at > float(give_up):
            return f"⏱ {char['name']}: {int(give_up)} sn'dir ilerleme yok → KAPAT (Hang Up), F5 yeni arama.", "danger"
        if stuck:
            nxt = next((x for x in s.plan if x != cur and x not in s.completed), None)
            if not nxt:
                return f"🔁 {self._sname(cur)} takıldı ve başka açık scam yok → son bir deneme, olmazsa KAPAT → F5.", "warn"
            return f"🔁 {self._sname(cur)} bu adımda takıldı (4+ deneme) → F8 ile aynı arayana {self._sname(nxt)} dene. Arayanı bırakma.", "warn"
        pot = sum(self._reward(x) for x in s.plan if x not in s.completed and not db["scams"][x].get("is_tool"))
        txt = f"Eksik {fmt_money(gap)} • Bu arayandaki plan potansiyeli ~{fmt_money(pot)}"
        if tl is not None:
            txt += f" • kalan {fmt_time(tl)}"
        return txt + par_txt, "info"

    def _gist(self, text: str, intents: Dict[str, int], data: dict) -> str:
        parts = []
        for name in intents:
            if name in self.intents.gist and name not in ("positive",) or (name == "positive" and len(intents) == 1):
                parts.append(self.intents.gist[name])
        if data.get("interest"):
            parts.append(f"Hobisi: {data['interest']}")
        if data.get("nickname"):
            parts.append(f"Sana lakabı: {data['nickname']}")
        if data.get("codes") or data.get("card") or data.get("ssn"):
            parts.append("🔢 NUMARA/KOD OKUYOR")
        if data.get("email"):
            parts.append("📧 E-posta verdi")
        if data.get("amount"):
            parts.append(f"Tutar: {fmt_money(data['amount'])}")
        if data.get("places"):
            parts.append("📍 Konum: " + ", ".join(data["places"]))
        if not parts:
            topic = self._topic()
            if topic and self.session.utterances <= 2:
                parts.append("Konu: " + self.db["topics"][topic].get("name_tr", topic))
            else:
                parts.append("Konuşuyor (belirgin itiraz yok)")
        return " · ".join(parts)

    def _finish(self, adv: Advice, text: str = "", intents: Optional[Dict[str, int]] = None, data: Optional[dict] = None) -> Advice:
        s = self.session
        self.seq += 1
        adv.seq = self.seq
        if text:
            adv.caller_said = text
            adv.intents = sorted((intents or {}).keys())
            adv.caller_gist_tr = self._gist(text, intents or {}, data or {})
        elif self.last_advice and not adv.caller_said:
            adv.caller_said = self.last_advice.caller_said
            adv.caller_gist_tr = adv.caller_gist_tr or self.last_advice.caller_gist_tr
        adv.data_lines = [f"{k}: {v}" for k, v in s.data.items()][-5:]
        locs = [p for p, _ in s.profile.locations.most_common(4)]
        hints = [h for h, _ in s.profile.location_hints.most_common(3)]
        adv.location_hints = locs + hints
        adv.footnote_tr, adv.footnote_severity = self._footnote()
        adv.quota_line = self._quota_line()
        if adv.say and (not s.transcript or s.transcript[-1][1] != adv.say):
            s.transcript.append(("player", adv.say, self.now()))
        self.last_advice = adv
        return adv
