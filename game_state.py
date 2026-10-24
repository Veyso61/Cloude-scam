# -*- coding: utf-8 -*-
"""Oyun durumu: hafta/gün, kota, kazanç, vardiya sayacı, açık/satın alınmış uygulamalar."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class GameState:
    day: int = 1                      # mutlak gün (1..15)
    prestige: int = 0
    players: int = 1
    quota: Optional[int] = None       # None -> tahmini kota tablosu
    quota_source: str = "tahmini"     # tahmini | manuel | ocr
    earned: int = 0
    earned_source: str = "otomatik"   # otomatik | manuel | ocr
    shift_minutes: float = 20.0
    timer_enabled: bool = True
    timer_running: bool = False
    timer_started_at: Optional[float] = None
    timer_elapsed_before: float = 0.0
    owned_apps: List[str] = field(default_factory=list)
    unlock_overrides: Dict[str, bool] = field(default_factory=dict)
    pending_unlocks: List[str] = field(default_factory=list)
    trust: Optional[int] = None
    trust_label: str = ""
    caller_name_hint: str = ""
    day_end_detected: bool = False
    calls_today: int = 0

    # ------------------------------------------------------------------ takvim
    @property
    def days_per_week(self) -> int:
        return 5

    @property
    def week(self) -> int:
        return (self.day - 1) // self.days_per_week + 1

    @property
    def day_in_week(self) -> int:
        return (self.day - 1) % self.days_per_week + 1

    def set_week_day(self, week: int, day_in_week: int) -> None:
        self.day = max(1, min(15, (int(week) - 1) * self.days_per_week + int(day_in_week)))

    def next_day(self, total_days: int = 15) -> None:
        self.day += 1
        if self.day > total_days:
            self.day = 1
            self.prestige += 1
        for sid in self.pending_unlocks:
            self.unlock_overrides[sid] = True
        self.pending_unlocks = []
        self.earned = 0
        self.earned_source = "otomatik"
        self.quota = None
        self.quota_source = "tahmini"
        self.trust = None
        self.trust_label = ""
        self.day_end_detected = False
        self.calls_today = 0
        self.reset_timer()

    def fired(self) -> None:
        self.day = 1
        self.earned = 0
        self.quota = None
        self.quota_source = "tahmini"
        self.unlock_overrides = {}
        self.pending_unlocks = []
        self.day_end_detected = False
        self.calls_today = 0
        self.reset_timer()

    # ------------------------------------------------------------------ kota
    def estimated_quota(self, db: dict) -> int:
        q = db["game_rules"]["quota"]
        base = int(q["solo_by_day"].get(str(self.day), q["solo_by_day"]["15"]))
        mult = 1.0 + float(q.get("coop_multiplier_per_extra_player", 0.6)) * max(0, self.players - 1)
        return int(round(base * mult))

    def quota_value(self, db: dict) -> int:
        return int(self.quota) if self.quota else self.estimated_quota(db)

    def gap(self, db: dict) -> int:
        return self.quota_value(db) - int(self.earned)

    def add_earnings(self, amount: int) -> None:
        self.earned = max(0, int(self.earned) + int(amount))

    # ------------------------------------------------------------------ sayaç
    def elapsed(self) -> float:
        run = (time.time() - self.timer_started_at) if (self.timer_running and self.timer_started_at) else 0.0
        return self.timer_elapsed_before + run

    def time_left(self) -> Optional[float]:
        if not self.timer_enabled:
            return None
        if not self.timer_running and self.timer_elapsed_before == 0:
            return None
        return max(0.0, self.shift_minutes * 60.0 - self.elapsed())

    def start_timer(self) -> None:
        if not self.timer_running:
            self.timer_running = True
            self.timer_started_at = time.time()

    def pause_timer(self) -> None:
        if self.timer_running:
            self.timer_elapsed_before = self.elapsed()
            self.timer_running = False
            self.timer_started_at = None

    def reset_timer(self) -> None:
        self.timer_running = False
        self.timer_started_at = None
        self.timer_elapsed_before = 0.0

    def set_time_left(self, seconds: float) -> None:
        """OCR / manuel: kalan süreyi ayarla ve sayacı çalıştır."""
        seconds = max(0.0, float(seconds))
        if seconds > self.shift_minutes * 60:
            self.shift_minutes = seconds / 60.0
        self.timer_elapsed_before = self.shift_minutes * 60.0 - seconds
        self.timer_running = True
        self.timer_started_at = time.time()
        self.timer_elapsed_before = max(0.0, self.timer_elapsed_before)

    def timer_expired(self) -> bool:
        tl = self.time_left()
        return tl is not None and tl <= 0

    # ------------------------------------------------------------------ uygulamalar
    def is_unlocked(self, sid: str, db: dict) -> bool:
        if sid in self.unlock_overrides:
            return bool(self.unlock_overrides[sid])
        s = db["scams"].get(sid)
        return bool(s) and self.day >= int(s.get("available_from_day", 99))

    def is_owned(self, sid: str, db: dict) -> bool:
        s = db["scams"].get(sid)
        if not s or not self.is_unlocked(sid, db):
            return False
        if int(s.get("cost", 0)) <= 0:
            return True
        return sid in self.owned_apps

    def usable_scams(self, db: dict, include_tools: bool = False) -> List[str]:
        out = []
        for sid, s in db["scams"].items():
            if s.get("is_tool") and not include_tools:
                continue
            if self.is_owned(sid, db):
                out.append(sid)
        return out

    def purchasable(self, db: dict) -> List[str]:
        return [sid for sid, s in db["scams"].items()
                if int(s.get("cost", 0)) > 0 and self.is_unlocked(sid, db) and sid not in self.owned_apps]

    def new_today(self, db: dict) -> List[str]:
        return [sid for sid, s in db["scams"].items() if int(s.get("available_from_day", 0)) == self.day]

    # ------------------------------------------------------------------ kalıcılık
    def to_dict(self) -> dict:
        d = asdict(self)
        if self.timer_running:
            d["timer_elapsed_before"] = self.elapsed()
            d["timer_running"] = False
            d["timer_started_at"] = None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        st = cls()
        for k, v in (d or {}).items():
            if hasattr(st, k):
                setattr(st, k, v)
        st.timer_running = False
        st.timer_started_at = None
        st.day = max(1, min(15, int(st.day)))
        st.players = max(1, int(st.players))
        return st

    def save(self, path: str) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str) -> "GameState":
        try:
            with open(path, "r", encoding="utf-8") as f:
                return cls.from_dict(json.load(f))
        except (OSError, ValueError):
            return cls()


def fmt_time(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--"
    s = int(max(0, seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def fmt_money(n: Optional[int]) -> str:
    if n is None:
        return "$?"
    return ("-" if n < 0 else "") + "${:,}".format(abs(int(n)))
