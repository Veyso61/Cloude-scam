# -*- coding: utf-8 -*-
"""Ayarlar: config.json (ilk çalıştırmada varsayılanlarla oluşturulur)."""
from __future__ import annotations

import copy
import json
import os
import re
import sys
from typing import Any, Dict

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
STATE_PATH = os.path.join(APP_DIR, "state.json")
DB_PATH = os.path.join(APP_DIR, "characters_db.json")
CUSTOM_DB_PATH = os.path.join(APP_DIR, "characters_custom.json")
IMPORTED_DB_PATH = os.path.join(APP_DIR, "characters_imported.json")
LOG_DIR = os.path.join(APP_DIR, "logs")
VERSION_PATH = os.path.join(APP_DIR, "VERSION")
REMOTE_VERSION_URL = "https://raw.githubusercontent.com/Veyso61/Cloude-scam/ccr-c56d4dc6-5mxr8o/VERSION"


def _read_version() -> str:
    try:
        with open(VERSION_PATH, "r", encoding="utf-8") as f:
            return f.read().strip() or "?"
    except OSError:
        return "?"


APP_VERSION = _read_version()


def version_key(v: str) -> tuple:
    """'2026.10.24-6' → (2026, 10, 24, 6); bozuk değer en eski sayılır."""
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums) if nums else (0,)


def fetch_remote_version(timeout: float = 4.0) -> str:
    """GitHub'daki en son sürüm numarası; ağ yoksa ''."""
    import urllib.request
    try:
        with urllib.request.urlopen(REMOTE_VERSION_URL, timeout=timeout) as r:
            return r.read(64).decode("utf-8", "ignore").strip()
    except Exception:  # noqa: BLE001 — sürüm kontrolü hiçbir zaman programı durdurmamalı
        return ""

CONFIG_VERSION = 2

DEFAULT_CONFIG: Dict[str, Any] = {
    "config_version": CONFIG_VERSION,
    "agent_name": "Steve",
    "company_name": "Customer Protection Center",
    "language_level": "auto",
    "max_level": "C1",
    "show_turkish_notes": True,
    "translate_caller": True,
    "auto_copy_say": True,
    "new_call_gap_seconds": 20,
    "date_time": "8:00 PM",
    "date_place": "the mall food court",
    "auto_enter_seconds": 8,
    "auto_reset_on_fired": True,
    "players": 1,
    "shift_minutes": 20,
    "timer_enabled": True,
    "audio": {
        "enabled": True,
        "backend": "auto",
        "device_name": "",
        "frame_ms": 30,
        "threshold_db": -48.0,
        "margin_db": 9.0,
        "min_speech_ms": 300,
        "end_silence_ms": 650,
        "max_segment_s": 12.0,
        "pre_roll_ms": 300,
        "use_webrtcvad": True
    },
    "stt": {
        "engine": "faster_whisper",
        "model": "auto",
        "device": "auto",
        "compute_type": "auto",
        "beam_size": 1,
        "cpu_threads": 4,
        "language": "en",
        "google_fallback": True
    },
    "ocr": {
        "enabled": True,
        "interval_s": 3.0,
        "engine": "auto",
        "regions": [],
        "read_caller_name": True,
        "read_trust": True,
        "read_money": True,
        "read_timer": True,
        "read_day": True
    },
    "llm": {
        "enabled": False,
        "provider": "anthropic",
        "model": "claude-opus-5-5",
        "effort": "low",
        "api_key": "",
        "timeout_s": 20,
        "max_tokens": 4000
    },
    "overlay": {
        "x": 40,
        "y": 60,
        "width": 600,
        "opacity": 0.9,
        "font_family": "Segoe UI",
        "say_font_size": 17,
        "font_size": 11,
        "click_through": False,
        "compact": False,
        "topmost_refresh_ms": 1500
    },
    "hotkeys": {
        "new_call": "f5",
        "step_done": "f6",
        "step_back": "f7",
        "next_scam": "f8",
        "prev_scam": "shift+f8",
        "alt_line": "f9",
        "timer_toggle": "f10",
        "next_day": "f11",
        "copy_line": "ctrl+f9",
        "toggle_overlay": "ctrl+f12",
        "toggle_click_through": "ctrl+f11",
        "toggle_compact": "ctrl+f10",
        "add_200": "ctrl+f6",
        "calibrate_ocr": "ctrl+shift+f12"
    }
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str = CONFIG_PATH) -> dict:
    user: dict = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[config] {path} okunamadı ({e}); varsayılanlar kullanılıyor.")
    cfg = _merge(DEFAULT_CONFIG, user)
    if user and int(user.get("config_version", 1)) < CONFIG_VERSION:
        _migrate(cfg, user)
        save_config(cfg, path)
    if not os.path.exists(path):
        save_config(cfg, path)
    return cfg


def _migrate(cfg: dict, user: dict) -> None:
    """Eski config.json'ları yeni varsayılanlara bir kez taşır."""
    if int(user.get("config_version", 1)) < 2:
        # Ekrandan arayan adını okumak otomatik tanımanın en güvenilir yolu → varsayılan açık.
        cfg["ocr"]["enabled"] = True
        # C2 cümleleri uzun ve jargonlu; oyundaki arayan 1 cümleyle cevap veriyor → en fazla C1.
        if (user.get("max_level") or "C2").upper() == "C2":
            cfg["max_level"] = "C1"
    cfg["config_version"] = CONFIG_VERSION


def save_config(cfg: dict, path: str = CONFIG_PATH) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_db(path: str = DB_PATH, custom_path: str = CUSTOM_DB_PATH, imported_path: str = IMPORTED_DB_PATH) -> dict:
    """Ana veritabanı + oyundan içe aktarılan + kullanıcının elle eklediği karakterler."""
    with open(path, "r", encoding="utf-8") as f:
        db = json.load(f)
    for extra_path in (imported_path, custom_path):
        if not os.path.exists(extra_path):
            continue
        try:
            with open(extra_path, "r", encoding="utf-8") as f:
                extra = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[db] {extra_path} okunamadı: {e}")
            continue
        chars = extra.get("characters", extra if isinstance(extra, dict) else {})
        if isinstance(chars, list):
            chars = {c["id"]: c for c in chars if isinstance(c, dict) and c.get("id")}
        for cid, c in chars.items():
            if not isinstance(c, dict) or not c.get("name"):
                continue
            base = db["characters"].get(cid, {})
            merged = {**_character_defaults(cid), **base, **c}
            if merged.get("archetype") not in db["archetypes"]:
                merged["archetype"] = "trusting"
            merged["best_scams"] = [s for s in merged.get("best_scams", []) if s in db["scams"]]
            merged["avoid_scams"] = [s for s in merged.get("avoid_scams", []) if s in db["scams"]]
            db["characters"][cid] = merged
        for sid, s in (extra.get("scam_overrides") or {}).items():
            if sid in db["scams"] and isinstance(s, dict):
                db["scams"][sid] = _merge(db["scams"][sid], s)
    return db


def _character_defaults(cid: str) -> dict:
    return {
        "id": cid, "name": cid, "aliases": [], "game_id": None, "gender": None, "call_type": "victim",
        "first_messages": [], "archetype": "trusting", "secondary": [], "verified": False,
        "source_tr": "", "generic": False, "mod": False, "typical_week": 1, "trust_start": None,
        "formal_name": None, "first_name": None, "profile_tr": "", "weakness_tr": "", "fatal_tr": [],
        "keywords": [], "topic": None, "problem_en": None, "service_en": None, "best_scams": [],
        "avoid_scams": [], "level": None, "pet_name": None, "hang_up": False, "scambaiter": False,
        "silver_bullet": "", "custom_lines": {}, "tips_tr": [], "give_up_seconds": None,
    }
