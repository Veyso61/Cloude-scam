# -*- coding: utf-8 -*-
"""Scam With Your Friends — canlı İngilizce konuşma koçu (Windows overlay).

Çalıştırma:
    python main.py                 # overlay + sistem sesi dinleme (normal kullanım)
    python main.py --simulate      # ses yerine arayan cümlesini kutuya yazarak dene
    python main.py --demo kanye    # hazır örnek konuşmayı oynat (dorothy|kanye|vega|lexi|arthur)
    python main.py --cli --simulate  # pencere olmadan konsolda dene
    python main.py --list-devices  # loopback ses cihazlarını listele
    python main.py --test-audio    # sadece dinle ve yazıya dök (ses ayarı testi)
    python main.py --import-callers [OYUN_KLASÖRÜ]   # oyundaki arayan dosyalarını içe aktar
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import queue
import sys
import threading
import time
import warnings
from typing import Optional

# Hugging Face model önbelleğinin zararsız uyarılarını (Windows symlink, HF_TOKEN) gizle.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
warnings.filterwarnings("ignore", module=r"huggingface_hub(\..*)?")

import config as C
from game_state import GameState, fmt_money, fmt_time
from strategy_engine import Advice, StrategyEngine

DEMOS = {
    "dorothy": ["Hello? Yes, this is Dorothy Mayfield. I got a letter about my pension and I'm so confused.",
                "Oh my, that's terrible! What do I do?",
                "I live at 42 Maple Street, Springfield.",
                "My birthday is March 3rd, 1948.",
                "Okay dear, it's 123-45-6789.",
                "Is everything alright now?",
                "A gift card? Why would I need a gift card?",
                "Alright, I have a Steam card here.",
                "The code is four four one seven, twenty two thirty one, nine nine eight one."],
    "kanye": ["Yo, this is Kanye. Somebody sold me bootleg Yeezys and I'm furious, I'm a genius, my fans deserve better.",
              "Haha, I love making music and designing sneakers, obviously.",
              "Oh stop it, you're making me blush, you're a charmer.",
              "Fine, I'll call you my little cupcake.",
              "Okay... I love you too, I guess!",
              "Yes! It's a date, see you at 8."],
    "vega": ["This is Commander Miles Vega aboard Orbital Station Three. My terminal telemetry is failing, over.",
             "Negative. I do not hand out access without procedure. Explain the protocol, over.",
             "Copy that. Opening AnyViewer. My authorization code is 7 7 1 4 0 9 2 3, over.",
             "I see windows opening on my screen. Is that standard procedure, over?"],
    "lexi": ["Ugh, literally my order never came and I want a refund right now, make it quick.",
             "No. I'm not doing that.", "No way, this is ridiculous.", "Whatever, I'm hanging up."],
    "arthur": ["Hi, I'm Arthur. My computer is acting weird. Here, my AnyViewer code is 482 991 330, connect to my computer please!"],
}


class App:
    def __init__(self, args):
        self.args = args
        self.cfg = C.load_config()
        self.db = C.load_db()
        self.state = GameState.load(C.STATE_PATH) if not args.reset_state else GameState()
        self.state.players = int(self.cfg.get("players", self.state.players) or 1)
        self.state.shift_minutes = float(self.cfg.get("shift_minutes", self.state.shift_minutes))
        self.state.timer_enabled = bool(self.cfg.get("timer_enabled", True))
        if args.day:
            self.state.day = max(1, min(15, args.day))
        engine_cfg = self.cfg
        if args.demo:
            engine_cfg = dict(self.cfg, auto_enter_seconds=max(1.0, float(args.demo_delay) * 1.5))
        self.engine = StrategyEngine(self.db, self.state, engine_cfg)
        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.ui = None
        self.root = None
        self.listener = None
        self.reader = None
        self.hotkeys = None
        self.llm = None
        self.translator = None
        self._stop = threading.Event()
        os.makedirs(C.LOG_DIR, exist_ok=True)
        self.log_path = os.path.join(C.LOG_DIR, _dt.datetime.now().strftime("session_%Y%m%d_%H%M%S.txt"))

    # ================================================================== helpers
    def log(self, kind: str, text: str) -> None:
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"[{_dt.datetime.now():%H:%M:%S}] {kind}: {text}\n")
        except OSError:
            pass

    def status(self, text: str) -> None:
        self.q.put(("status", text))

    def emit(self, adv: Advice) -> None:
        if adv.say:
            self.log("SAY", adv.say)
        if self.ui:
            self.ui.render(adv)
        else:
            self._print_advice(adv)

    def _print_advice(self, a: Advice) -> None:
        print("-" * 78)
        print(f"{a.quota_line}")
        print(f"🎭 {a.caller_name} — {a.archetype_tr} • {a.level}")
        if a.scam_name:
            print(f"🎯 {a.scam_name} {a.step_index}/{a.step_total}: {a.step_label_tr}   ➜ {' → '.join(a.plan[:3])}")
        if a.caller_said:
            print(f"👂 {a.caller_said}")
        if a.caller_gist_tr:
            print(f"   {a.caller_gist_tr}")
        if a.caller_tr:
            print(f"🇹🇷 {a.caller_tr}")
        print(f"\n🗣  SÖYLE{' (AI)' if a.source == 'AI' else ''}: {a.say}\n")
        if a.note_tr:
            print(f"💡 {a.note_tr}")
        if a.player_action_tr:
            print(a.player_action_tr)
        for d in a.data_lines[-3:]:
            print(f"🔢 {d}")
        if a.location_hints:
            print("📍 " + ", ".join(a.location_hints))
        for w in dict.fromkeys(a.warnings):
            print(f"⚠ {w}")
        if a.footnote_tr:
            print(f"➤ {a.footnote_tr}")
        sys.stdout.flush()

    # ================================================================== optional services
    def _auto_import_callers(self) -> None:
        """Oyun / Workshop / AppData klasörlerindeki arayanları içe aktar (veritabanında olmayan Workshop arayanları için)."""
        try:
            import json
            from caller_importer import auto_import
            with open(C.DB_PATH, "r", encoding="utf-8") as f:
                base = json.load(f)
            n = auto_import(base, C.IMPORTED_DB_PATH, log=lambda *a: None)
        except Exception as e:  # noqa: BLE001 — içe aktarma başarısız olsa da koç çalışmaya devam eder
            print(f"[import] atlandı: {e}", flush=True)
            return
        self.q.put(("callers_imported", n))

    def _reload_characters(self, n: int) -> None:
        fresh = C.load_db()
        self.db["characters"] = fresh["characters"]
        self.engine.reload_characters()
        if self.reader is not None and hasattr(self.reader, "name_index"):
            self.reader.name_index = dict(self.engine._name_index)
        if n:
            self.status(f"🧩 Oyun/Workshop klasöründen {n} yeni arayan eklendi")

    def _check_update(self) -> None:
        latest = C.fetch_remote_version()
        if latest and C.version_key(latest) > C.version_key(C.APP_VERSION):
            self.status(f"🔔 Yeni sürüm var: {latest} (sende {C.APP_VERSION}) → koçu kapat, update.bat'a çift tıkla")

    def _start_services(self) -> None:
        print(f"SWYF Koç — sürüm {C.APP_VERSION}  (klasör: {C.APP_DIR})", flush=True)
        if not self.args.simulate and not self.args.demo:
            threading.Thread(target=self._check_update, daemon=True).start()
            if self.cfg.get("auto_import_callers", True):
                threading.Thread(target=self._auto_import_callers, daemon=True).start()
        if self.cfg["llm"].get("enabled"):
            try:
                from llm_advisor import LLMAdvisor
                self.llm = LLMAdvisor(self.cfg["llm"], self.status)
                self.status(f"🤖 AI danışmanı açık ({self.llm.model})")
            except Exception as e:  # noqa: BLE001
                self.status(f"AI kapalı: {e}")
        if not self.llm and self.cfg.get("translate_caller", True):
            try:
                from llm_advisor import Translator
                self.translator = Translator()
            except Exception:
                self.translator = None
        if not self.args.simulate and not self.args.demo and self.cfg["audio"].get("enabled", True) and not self.args.no_audio:
            try:
                from audio_listener import AudioListener
                self.listener = AudioListener(
                    self.cfg["audio"], self.cfg["stt"],
                    on_text=lambda t, meta: self.q.put(("caller_text", t, meta)),
                    on_level=lambda db, sp: self.q.put(("level", db, sp)),
                    on_status=self.status, prompt_provider=self._stt_prompt,
                    hallucinations=self.db.get("stt_hallucinations", []))
                self.listener.start()
            except Exception as e:  # noqa: BLE001
                self.status(f"❌ Ses dinleme başlatılamadı: {e}")
        if self.cfg["ocr"].get("enabled"):
            self._start_ocr()
        if self.ui is not None or sys.platform == "win32":
            try:
                from hotkeys import HotkeyManager
                cbs = {name: (lambda n=name: self.q.put(("hotkey", n))) for name in self.cfg["hotkeys"]}
                self.hotkeys = HotkeyManager(self.cfg["hotkeys"], cbs, self.status)
                self.hotkeys.start()
            except Exception as e:  # noqa: BLE001
                self.status(f"Kısayollar kapalı: {e}")

    def _start_ocr(self) -> None:
        try:
            from screen_reader import ScreenReader
            name_index = {cid: [c["name"]] + c.get("aliases", []) for cid, c in self.db["characters"].items() if not c.get("generic")}
            scam_names = {sid: s["name"].split(" (")[0] for sid, s in self.db["scams"].items()}
            self.reader = ScreenReader(self.cfg["ocr"], lambda r: self.q.put(("hud", r)), self.status, name_index, scam_names)
            self.reader.start()
        except Exception as e:  # noqa: BLE001
            hint = " → install.bat'ı bir kez daha çalıştır (OCR paketleri)" if isinstance(e, ImportError) else ""
            self.status(f"OCR kapalı: {e}{hint}")

    def _stt_prompt(self) -> str:
        name = self.engine.last_advice.caller_name if self.engine.last_advice else ""
        base = "Phone call in the game Scam With Your Friends. Words: gift card, Scamazon, AnyViewer, Social Security, routing number, Bitcoin, meme coin, warranty."
        if name and not name.startswith("Bilinmeyen"):
            base += f" Caller: {name}."
        return base

    def _maybe_llm(self, adv: Advice) -> None:
        if not adv.caller_said or adv.source == "AI" or adv.caller_gist_tr == "Patron değerlendirmesi":
            return
        if self.llm is not None:
            ctx = self.engine.llm_context()
            started = self.llm.suggest_async(ctx, adv.seq, lambda seq, res: self.q.put(("llm", seq, res)))
            if started:
                self.status("🤖 AI düşünüyor…")
        elif self.translator is not None:
            self.translator.translate_async(adv.caller_said, adv.seq, lambda seq, tr: self.q.put(("translation", seq, tr)))

    # ================================================================== event handling
    def handle(self, ev: tuple) -> None:
        kind = ev[0]
        if kind == "caller_text":
            text, meta = ev[1], ev[2] if len(ev) > 2 else {}
            self.log("CALLER", text + (f"  (stt {meta.get('stt_seconds', 0):.1f}s)" if meta else ""))
            adv = self.engine.on_caller_text(text)
            self.emit(adv)
            self._maybe_llm(adv)
        elif kind == "status":
            self.log("STATUS", ev[1])
            if self.ui:
                self.ui.set_status(ev[1])
                if ev[1]:
                    print(f"[durum] {ev[1]}", flush=True)
            else:
                print(f"[durum] {ev[1]}")
        elif kind == "level":
            if self.ui:
                self.ui.set_level(ev[1], ev[2])
        elif kind == "llm":
            seq, res = ev[1], ev[2]
            self.status("")
            if res:
                adv = self.engine.apply_llm(res, seq)
                if adv is not None:
                    self.log("SAY(AI)", adv.say)
                    if self.ui:
                        self.ui.render(adv)
                    else:
                        self._print_advice(adv)
        elif kind == "translation":
            seq, tr = ev[1], ev[2]
            if tr and self.engine.last_advice and self.engine.last_advice.seq == seq:
                self.engine.last_advice.caller_tr = tr
                if self.ui:
                    self.ui.render(self.engine.last_advice)
                else:
                    print(f"🇹🇷 {tr}")
        elif kind == "hud":
            self._apply_hud(ev[1])
        elif kind == "hotkey":
            self.hotkey(ev[1])
        elif kind == "sim_text":
            self.handle(("caller_text", ev[1], {}))
        elif kind == "callers_imported":
            self._reload_characters(ev[1])
        elif kind == "quit":
            self._stop.set()

    def _apply_hud(self, r) -> None:
        st, ocfg = self.state, self.cfg["ocr"]
        changed_day = False
        if ocfg.get("read_day", True) and r.day and r.day != st.day:
            st.day = r.day
            changed_day = True
        if ocfg.get("read_money", True):
            if r.quota:
                st.quota, st.quota_source = r.quota, "ocr"
            if r.earned is not None:
                st.earned, st.earned_source = r.earned, "ocr"
        if ocfg.get("read_timer", True) and r.time_left is not None and st.timer_enabled:
            tl = st.time_left()
            if tl is None or abs(tl - r.time_left) > 5:
                st.set_time_left(r.time_left)
        trust_changed = False
        if ocfg.get("read_trust", True) and r.trust is not None:
            trust_changed = self.engine.update_trust(r.trust, r.trust_label)
        for sid in r.tomorrow_scams:
            if sid not in st.pending_unlocks:
                st.pending_unlocks.append(sid)
        if ocfg.get("read_caller_name", True) and r.caller_name:
            st.caller_name_hint = r.caller_name
            adv = self.engine.on_ocr_caller(r.caller_name)
            if adv:
                self.log("OCR-CALLER", r.caller_name)
                self.emit(adv)
                trust_changed = False
        for app in getattr(r, "apps", []) or []:
            adv = self.engine.sync_app(app.get("name", ""), app.get("done"), app.get("total"), app.get("reward"), app.get("next", ""))
            if adv:
                self.log("OCR-APP", str(app))
                self.emit(adv)
                trust_changed = False
        if trust_changed and self.ui and self.engine.last_advice:
            self.ui.render(self.engine.refresh())
        if changed_day:
            self.briefing()
        self.tick(force=True)

    def hotkey(self, name: str) -> None:
        e, st = self.engine, self.state
        if name == "new_call":
            self.emit(e.new_call())
        elif name == "step_done":
            self.emit(e.step_done())
        elif name == "step_back":
            self.emit(e.step_back())
        elif name == "next_scam":
            self.emit(e.next_scam(1))
        elif name == "prev_scam":
            self.emit(e.next_scam(-1))
        elif name == "alt_line":
            self.emit(e.alt_line())
        elif name == "timer_toggle":
            if st.timer_expired() or st.day_end_detected:
                st.next_day()
                st.start_timer()
                self.briefing()
                self.emit(e.new_call())
            elif st.timer_running:
                st.pause_timer()
                self.status("⏸ Sayaç durdu")
            else:
                st.start_timer()
                self.status(f"▶ Vardiya sayacı: {fmt_time(st.time_left())}")
        elif name == "next_day":
            st.next_day()
            self.briefing()
            self.emit(e.new_call())
        elif name == "copy_line":
            if self.ui and e.last_advice:
                self.ui.copy_to_clipboard(e.last_advice.say)
        elif name == "toggle_overlay" and self.ui:
            self.ui.toggle_visibility()
        elif name == "toggle_click_through" and self.ui:
            self.ui.toggle_click_through()
            C.save_config(self.cfg)
        elif name == "toggle_compact" and self.ui:
            self.ui.toggle_compact()
            C.save_config(self.cfg)
        elif name == "add_200":
            st.add_earnings(200)
            st.earned_source = "manuel"
            self.tick(force=True)
        elif name == "calibrate_ocr" and self.ui:
            self.ui.pick_region(self._add_region)
        self.save_state()

    def _add_region(self, region) -> None:
        self.cfg["ocr"].setdefault("regions", []).append(region)
        self.cfg["ocr"]["enabled"] = True
        C.save_config(self.cfg)
        self.status(f"OCR bölgesi eklendi: {region}")
        if self.reader is None:
            self._start_ocr()

    def briefing(self) -> None:
        text = self.engine.day_briefing()
        self.log("BRIEFING", text.replace("\n", " | "))
        if self.ui:
            self.ui.show_briefing(text)
        else:
            print("=" * 78 + "\n" + text + "\n" + "=" * 78)

    def tick(self, force: bool = False) -> None:
        adv = self.engine.refresh()
        if self.ui:
            self.ui.update_footer(adv.footnote_tr, adv.footnote_severity, adv.quota_line)
        elif force:
            print(f"➤ {adv.quota_line} | {adv.footnote_tr}")

    def save_state(self) -> None:
        try:
            self.state.save(C.STATE_PATH)
        except OSError:
            pass

    # ================================================================== settings
    def apply_settings(self, vals: dict) -> None:
        st, db = self.state, self.db
        old_day = st.day
        try:
            st.day = max(1, min(15, int(vals.get("day") or st.day)))
            st.players = max(1, int(vals.get("players") or 1))
            q = str(vals.get("quota") or "").replace("$", "").replace(",", "").strip()
            st.quota, st.quota_source = (int(q), "manuel") if q else (None, "tahmini")
            earned = str(vals.get("earned") or "0").replace("$", "").replace(",", "").strip()
            st.earned, st.earned_source = int(earned or 0), "manuel"
            st.shift_minutes = float(vals.get("shift") or st.shift_minutes)
            st.timer_enabled = bool(vals.get("timer_enabled"))
            tl = str(vals.get("time_left") or "").strip()
            if tl and ":" in tl:
                mm, ss = tl.split(":", 1)
                st.set_time_left(int(mm) * 60 + int(ss))
        except (TypeError, ValueError) as e:
            self.status(f"Geçersiz değer: {e}")
        for sid, want in (vals.get("apps") or {}).items():
            s = db["scams"][sid]
            if want == st.is_owned(sid, db):
                continue
            if want:
                if not st.is_unlocked(sid, db):
                    st.unlock_overrides[sid] = True
                if s.get("cost") and sid not in st.owned_apps:
                    st.owned_apps.append(sid)
            else:
                if s.get("cost") and sid in st.owned_apps:
                    st.owned_apps.remove(sid)
                else:
                    st.unlock_overrides[sid] = False
        self.cfg["players"] = st.players
        self.cfg["shift_minutes"] = st.shift_minutes
        self.cfg["timer_enabled"] = st.timer_enabled
        for k in ("language_level", "max_level", "agent_name", "company_name", "translate_caller", "auto_copy_say"):
            if vals.get(k) is not None:
                self.cfg[k] = vals[k]
        self.cfg["ocr"]["enabled"] = bool(vals.get("ocr_enabled"))
        llm_was = self.cfg["llm"].get("enabled")
        self.cfg["llm"]["enabled"] = bool(vals.get("llm_enabled"))
        self.cfg["llm"]["model"] = vals.get("llm_model") or self.cfg["llm"]["model"]
        self.cfg["llm"]["api_key"] = vals.get("llm_key") or ""
        if vals.get("opacity"):
            self.cfg["overlay"]["opacity"] = round(float(vals["opacity"]), 2)
        if vals.get("say_font"):
            self.cfg["overlay"]["say_font_size"] = int(vals["say_font"])
        C.save_config(self.cfg)
        self.engine.cfg = self.cfg
        if self.cfg["llm"]["enabled"] and (not llm_was or self.llm is None):
            try:
                from llm_advisor import LLMAdvisor
                self.llm = LLMAdvisor(self.cfg["llm"], self.status)
                self.status(f"🤖 AI danışmanı açık ({self.llm.model})")
            except Exception as e:  # noqa: BLE001
                self.status(f"AI açılamadı: {e}")
        elif not self.cfg["llm"]["enabled"]:
            self.llm = None
        if self.cfg["ocr"]["enabled"] and self.reader is None:
            self._start_ocr()
        elif not self.cfg["ocr"]["enabled"] and self.reader is not None:
            self.reader.stop()
            self.reader = None
        if self.ui:
            self.ui.root.attributes("-alpha", float(self.cfg["overlay"]["opacity"]))
            self.ui.lbl_say.config(font=(self.cfg["overlay"].get("font_family", "Segoe UI"), int(self.cfg["overlay"]["say_font_size"]), "bold"))
        if vals.get("character_id") and vals["character_id"] != self.engine.session.profile.char_id:
            self.emit(self.engine.set_character(vals["character_id"]))
        elif vals.get("archetype_id"):
            self.emit(self.engine.set_archetype(vals["archetype_id"]))
        if st.day != old_day:
            self.briefing()
        self.save_state()
        self.tick(force=True)
        self.status("✅ Ayarlar kaydedildi")

    # ================================================================== run modes
    def run_gui(self) -> None:
        import tkinter as tk
        from overlay_ui import OverlayUI
        _set_dpi_awareness()
        self.root = tk.Tk()
        actions = {
            "quit": self.quit, "settings": self.open_settings, "save_config": lambda: C.save_config(self.cfg),
            "sim_text": lambda t: self.q.put(("sim_text", t)), "clear_ocr": self._clear_ocr,
            **{name: (lambda n=name: self.q.put(("hotkey", n))) for name in
               ("step_back", "step_done", "alt_line", "next_scam", "new_call", "timer_toggle", "next_day", "copy_line",
                "toggle_compact", "calibrate_ocr")},
        }
        self.ui = OverlayUI(self.root, self.cfg, actions, simulate=bool(self.args.simulate or self.args.demo))
        self._start_services()
        self.emit(self.engine.new_call(self.args.char))
        self.briefing()
        if self.args.demo:
            self._start_demo()
        self.root.after(50, self._pump)
        self.root.after(1000, self._tick_loop)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.mainloop()

    def _clear_ocr(self) -> None:
        self.cfg["ocr"]["regions"] = []
        C.save_config(self.cfg)
        self.status("OCR bölgeleri temizlendi (tüm ekran okunur).")

    def open_settings(self) -> None:
        def label(c: dict) -> str:
            return c["name"] + (f" — {c['parody_of']}" if c.get("parody_of") else "")

        def order(c: dict) -> tuple:     # önce oyundaki arayanlar, sonra diğerleri, en sonda genel şablonlar
            return (bool(c.get("generic")), not c.get("game_id"), c["name"].lower())

        ordered = sorted(self.db["characters"].values(), key=order)
        chars = [(c["id"], label(c)) for c in ordered]
        cur = self.engine.session.profile.char_id
        current = next((lbl for cid, lbl in chars if cid == cur), "(Otomatik)")
        self.ui.open_settings(self.state, self.db, chars, self.apply_settings, current_character=current)

    def _pump(self) -> None:
        try:
            for _ in range(50):
                self.handle(self.q.get_nowait())
        except queue.Empty:
            pass
        if not self._stop.is_set():
            self.root.after(50, self._pump)

    def _tick_loop(self) -> None:
        self.tick()
        if self.reader is not None and self.ui is not None:
            r = self.ui.root
            rects = [(r.winfo_rootx(), r.winfo_rooty(), r.winfo_width(), r.winfo_height())]
            win = self.ui.settings_win
            if win is not None and win.winfo_exists():
                rects.append((win.winfo_rootx(), win.winfo_rooty(), win.winfo_width(), win.winfo_height()))
            self.reader.mask_rects = rects
        self._save_counter = getattr(self, "_save_counter", 0) + 1
        if self._save_counter % 5 == 0:
            self.save_state()
        if not self._stop.is_set():
            self.root.after(1000, self._tick_loop)

    def _start_demo(self) -> None:
        lines = DEMOS.get(self.args.demo, DEMOS["dorothy"])

        def run():
            time.sleep(1.5)
            for ln in lines:
                if self._stop.is_set():
                    return
                self.q.put(("caller_text", ln, {}))
                time.sleep(float(self.args.demo_delay))
            self._demo_done = True
        self._demo_done = False
        threading.Thread(target=run, name="demo", daemon=True).start()

    def run_cli(self) -> None:
        self._start_services()
        self.briefing()
        self.emit(self.engine.new_call(self.args.char))
        if self.args.demo:
            self._start_demo()
        if self.args.simulate:
            print("\nArayanın cümlesini yazıp Enter'a bas. Komutlar: /done /back /next /alt /new /day /timer /quit\n")
            threading.Thread(target=self._stdin_loop, name="stdin", daemon=True).start()
        try:
            while not self._stop.is_set():
                try:
                    ev = self.q.get(timeout=1.0)
                    self.handle(ev)
                except queue.Empty:
                    self.save_state()
                if self.args.demo and not self.args.simulate and self.q.empty() and getattr(self, "_demo_done", False):
                    break
        except KeyboardInterrupt:
            pass
        self.quit()

    def _stdin_loop(self) -> None:
        cmds = {"/done": "step_done", "/back": "step_back", "/next": "next_scam", "/alt": "alt_line",
                "/new": "new_call", "/day": "next_day", "/timer": "timer_toggle"}
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            if line == "/quit":
                break
            if line in cmds:
                self.q.put(("hotkey", cmds[line]))
            else:
                self.q.put(("caller_text", line, {}))
        self.q.put(("quit",))

    def quit(self) -> None:
        self._stop.set()
        self.save_state()
        for svc in (self.listener, self.reader, self.hotkeys):
            if svc is not None:
                try:
                    svc.stop()
                except Exception:
                    pass
        if self.root is not None:
            try:
                C.save_config(self.cfg)
                self.root.destroy()
            except Exception:
                pass


def _set_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Scam With Your Friends canlı konuşma koçu")
    ap.add_argument("--simulate", action="store_true", help="Ses yerine arayan cümlesini yazarak dene")
    ap.add_argument("--cli", action="store_true", help="Pencere açmadan konsolda çalış")
    ap.add_argument("--demo", choices=sorted(DEMOS), help="Hazır örnek konuşmayı oynat")
    ap.add_argument("--demo-delay", type=float, default=4.0, help="Demo cümleleri arası saniye")
    ap.add_argument("--no-audio", action="store_true", help="Ses dinlemeyi kapat")
    ap.add_argument("--list-devices", action="store_true", help="Loopback ses cihazlarını listele")
    ap.add_argument("--test-audio", action="store_true", help="Sadece dinle ve yazıya dök")
    ap.add_argument("--import-callers", nargs="*", metavar="KLASÖR", help="Oyundan arayan kişiliklerini içe aktar")
    ap.add_argument("--char", help="Başlangıç karakteri (characters_db.json id, ör. dorothy_mayfield)")
    ap.add_argument("--day", type=int, help="Mutlak gün (1-15)")
    ap.add_argument("--reset-state", action="store_true", help="Kayıtlı gün/kota durumunu sıfırla")
    args = ap.parse_args(argv)

    if args.list_devices:
        from audio_listener import list_loopback_devices
        devs = list_loopback_devices()
        print("Loopback cihazları:" if devs else "Loopback cihazı bulunamadı (PyAudioWPatch/soundcard kurulu mu?)")
        for d in devs:
            print("  -", d)
        return 0
    if args.import_callers is not None:
        from caller_importer import main as import_main
        return import_main(args.import_callers)
    if args.test_audio:
        return _test_audio()

    app = App(args)
    if args.cli:
        app.run_cli()
    else:
        try:
            app.run_gui()
        except ImportError as e:
            print(f"Tkinter açılamadı ({e}); --cli ile konsol modunda çalışın.")
            return 1
    return 0


def _test_audio() -> int:
    from audio_listener import AudioListener
    cfg = C.load_config()
    db = C.load_db()

    def on_text(t, meta):
        print(f"[{meta.get('duration', 0):.1f}s ses, {meta.get('stt_seconds', 0):.1f}s STT, gecikme {meta.get('latency', 0):.1f}s] {t}")

    lst = AudioListener(cfg["audio"], cfg["stt"], on_text=on_text, on_status=lambda s: print("[durum]", s),
                        hallucinations=db.get("stt_hallucinations", []))
    lst.start()
    print("Dinleniyor… (Ctrl+C ile çık). Bilgisayarda İngilizce bir video/oyun sesi açın.")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        lst.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
