# -*- coding: utf-8 -*-
"""İsteğe bağlı ekran okuma (OCR): gün/hafta, kota, kazanç, kalan süre, Caller Trust ve arayan adı.

Gereken paketler:  pip install mss rapidocr onnxruntime     (Tesseract kuruluysa pytesseract da olur)
Bölgeler config.json → ocr.regions içinde [x, y, w, h] (ekran pikseli). Boşsa tüm birincil ekran
(küçültülmüş) okunur. Overlay'deki "OCR bölgesi seç" ile fareyle seçilebilir.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np

import text_analysis as ta


@dataclass
class HudReading:
    day: Optional[int] = None
    week: Optional[int] = None
    day_in_week: Optional[int] = None
    quota: Optional[int] = None
    earned: Optional[int] = None
    time_left: Optional[int] = None
    trust: Optional[int] = None
    trust_label: str = ""
    caller_name: str = ""
    tomorrow_scams: List[str] = field(default_factory=list)
    apps: List[dict] = field(default_factory=list)     # {"name", "done", "total", "reward", "next"}
    raw: str = ""

    def is_empty(self) -> bool:
        return all(v in (None, "", []) for k, v in self.__dict__.items() if k != "raw")


_MONEY = r"\$\s?(\d{1,3}(?:[,.]\d{3})+|\d+)"

UI_LABELS = {
    "caller trust", "neutral", "suspicious", "trusting", "angry", "happy", "annoyed", "furious", "calm", "phone",
    "hang up", "camera", "show", "hide", "personal", "team", "quota", "performance review", "scamazon", "kolkata pay",
    "verify", "claim", "reward", "next", "connect", "cash out", "fun random apps", "malwarebits", "notes", "ledger",
    "browser", "disscord", "rainbit", "settings", "end day", "clock in", "clock out", "day unlocks", "tomorrow's scams",
}
_NAME_LINE = re.compile(r"^[A-Za-z][A-Za-z .'\-\"]{1,38}$")


def _is_caps_name(ln: str) -> bool:
    words = ln.split()
    return (_NAME_LINE.match(ln) is not None and ln.isupper() and 1 <= len(words) <= 4
            and ln.lower() not in UI_LABELS and sum(c.isalpha() for c in ln) >= 3)


def _guess_caller_name(lines: List[str], scam_names: Dict[str, str]) -> str:
    """Veritabanında olmayan arayanlar: telefondaki BÜYÜK HARFLİ ad (ör. 'FOREST DUMP')."""
    app_names = {n.lower() for n in scam_names.values()}
    caps = [ln for ln in lines if _is_caps_name(ln) and ln.lower() not in app_names]
    lowered = {ln.lower() for ln in lines if not ln.isupper()}
    for ln in caps:                       # sohbet balonunun başlığında aynı ad küçük harfle de geçer
        if ln.lower() in lowered:
            return ln
    for i, ln in enumerate(lines):        # 'CALLER TRUST' bloğundan sonraki ilk büyük harfli ad
        if "caller trust" in ln.lower():
            for nxt in lines[i + 1:i + 7]:
                if nxt in caps:
                    return nxt
    return ""


def _parse_apps(lines: List[str], scam_names: Dict[str, str]) -> List[dict]:
    """Uygulama penceresi: başlık (Credit Card) + 'Reward: $400' + '0 / 3 done' + 'Next: ...'."""
    names = {n.lower(): n for n in scam_names.values()}
    apps = []
    for i, ln in enumerate(lines):
        m = re.search(r"reward\s*:?\s*\$\s?([\d,]+)", ln, re.I)
        if not m:
            continue
        app = {"name": "", "reward": _money(m.group(1)), "done": None, "total": None, "next": ""}
        for prev in reversed(lines[max(0, i - 8):i]):
            low = prev.lower().strip()
            hit = names.get(low) or next((names[n] for n in names if ta.fuzzy_ratio(n, low) >= 0.85), None)
            if hit:
                app["name"] = hit
                break
        for nxt in lines[i:i + 5]:
            d = re.search(r"(\d+)\s*/\s*(\d+)\s*done", nxt, re.I)
            if d and app["done"] is None:
                app["done"], app["total"] = int(d.group(1)), int(d.group(2))
            n = re.search(r"next\s*:\s*(.+)", nxt, re.I)
            if n and not app["next"]:
                app["next"] = n.group(1).strip()
        if app["name"]:
            apps.append(app)
    return apps


def _money(s: str) -> int:
    return int(re.sub(r"[,.]", "", s))


def parse_hud_text(text: str, name_index: Optional[Dict[str, List[str]]] = None,
                   scam_names: Optional[Dict[str, str]] = None) -> HudReading:
    """OCR metninden oyun durumunu çıkarır (toleranslı regex'ler)."""
    r = HudReading(raw=text or "")
    t = text or ""
    low = t.lower()
    m = re.search(r"\bweek\s*[:#]?\s*(\d)\b", low)
    if m:
        r.week = int(m.group(1))
    m = re.search(r"\bday\s*[:#]?\s*(\d{1,2})\b", low)
    if m:
        d = int(m.group(1))
        if r.week and d <= 5:
            r.day_in_week = d
            r.day = (r.week - 1) * 5 + d
        elif 1 <= d <= 30:
            r.day = d
    m = re.search(_MONEY + r"\s*/\s*" + _MONEY, t)
    if m:
        r.earned, r.quota = _money(m.group(1)), _money(m.group(2))
    else:
        mq = re.search(r"quota[^$\d\n]{0,20}" + _MONEY, low)
        if mq:
            r.quota = _money(mq.group(1))
        me = re.search(r"(?:earned|earnings|total|team|haul|balance|money)[^$\d\n]{0,20}" + _MONEY, low)
        if me:
            r.earned = _money(me.group(1))
    m = (re.search(r"trust[^\d%]{0,40}?(\d{1,3})\s*%", low, re.S)
         or re.search(r"(\d{1,3})\s*%\s*(?:trusting|angry|neutral|suspicious|happy)", low))
    if m:
        v = int(m.group(1))
        if 0 <= v <= 100:
            r.trust = v
    m = re.search(r"\b(trusting|angry|neutral|suspicious|happy|annoyed|furious|calm)\b", low)
    if m:
        r.trust_label = m.group(1).capitalize()
    # Oyundaki geri sayım: "PERFORMANCE REVIEW 10:31". Saat ("3:57 PM") ve tarih okunmaz.
    m = re.search(r"review[^\d]{0,20}(\d{1,2}):([0-5]\d)(?![\d:])", low, re.S)
    if m:
        r.time_left = int(m.group(1)) * 60 + int(m.group(2))
    else:
        cands = [int(a) * 60 + int(b) for a, b in re.findall(r"(?<![\d:])(\d{1,2}):([0-5]\d)(?![\d:])(?!\s*[ap]\.?\s?m\b)", low)
                 if int(a) <= 30]
        if cands:
            r.time_left = min(cands)
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if name_index:
        for ln in lines:
            if 2 < len(ln) < 40 and ln.lower() not in UI_LABELS:
                cid = ta.best_fuzzy(ln, name_index, cutoff=0.82)
                if cid:
                    r.caller_name = ln
                    break
    if not r.caller_name:
        r.caller_name = _guess_caller_name(lines, scam_names or {})
    r.apps = _parse_apps(lines, scam_names or {})
    if scam_names and "tomorrow" in low:
        after = low.split("tomorrow", 1)[1]
        for sid, nm in scam_names.items():
            if nm.lower() in after:
                r.tomorrow_scams.append(sid)
    return r


def _join_sorted(items) -> str:
    """(sol-üst nokta, metin) listesini satır satır, soldan sağa birleştirir."""
    items = sorted(items, key=lambda it: (round(float(it[0][1]) / 12), float(it[0][0])))
    return "\n".join(str(t) for _, t in items)


class _OcrEngine:
    def __init__(self, engine: str = "auto"):
        self.kind = None
        self.impl = None
        errors = []
        if engine in ("auto", "rapidocr"):
            try:
                from rapidocr import RapidOCR  # type: ignore  # rapidocr >= 2 (Python 3.13+ destekli)
                self.impl = RapidOCR()
                self.kind = "rapidocr"
                logging.getLogger("RapidOCR").setLevel(logging.WARNING)
                return
            except Exception as e:  # noqa: BLE001
                errors.append(f"rapidocr: {e}")
            try:
                from rapidocr_onnxruntime import RapidOCR  # type: ignore  # eski paket (Python <= 3.12)
                self.impl = RapidOCR()
                self.kind = "rapidocr_legacy"
                return
            except Exception as e:  # noqa: BLE001
                errors.append(f"rapidocr_onnxruntime: {e}")
        if engine in ("auto", "tesseract"):
            try:
                import pytesseract  # type: ignore
                pytesseract.get_tesseract_version()
                self.impl = pytesseract
                self.kind = "tesseract"
                return
            except Exception as e:  # noqa: BLE001
                errors.append(f"tesseract: {e}")
        raise RuntimeError("OCR motoru yok → pip install rapidocr onnxruntime  (" + " | ".join(errors) + ")")

    def read(self, rgb: np.ndarray) -> str:
        if self.kind == "rapidocr":
            out = self.impl(rgb)
            txts = list(getattr(out, "txts", None) or [])
            boxes = getattr(out, "boxes", None)
            if not txts:
                return ""
            items = [(boxes[i][0], t) for i, t in enumerate(txts)] if boxes is not None and len(boxes) == len(txts) else [((0, i), t) for i, t in enumerate(txts)]
            return _join_sorted(items)
        if self.kind == "rapidocr_legacy":
            result, _ = self.impl(rgb)
            if not result:
                return ""
            return _join_sorted([(it[0][0], it[1]) for it in result])
        from PIL import Image  # type: ignore
        return self.impl.image_to_string(Image.fromarray(rgb))


class ScreenReader:
    def __init__(self, ocr_cfg: dict, on_reading: Callable[[HudReading], None], on_status: Callable[[str], None],
                 name_index: Dict[str, List[str]], scam_names: Dict[str, str]):
        self.cfg = ocr_cfg
        self.on_reading = on_reading
        self.on_status = on_status
        self.name_index = name_index
        self.scam_names = scam_names
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_raw = ""
        self.mask_rects: List[tuple] = []   # (x, y, w, h) ekran pikseli — overlay'in kendisi okunmasın

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="ocr", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def set_regions(self, regions: List[List[int]]) -> None:
        self.cfg["regions"] = regions

    def _grab(self, sct, region: Optional[List[int]]) -> np.ndarray:
        if region:
            x, y, w, h = [int(v) for v in region]
            mon = {"left": x, "top": y, "width": max(8, w), "height": max(8, h)}
        else:
            mon = sct.monitors[1]
        img = np.array(sct.grab(mon))[:, :, :3][:, :, ::-1]  # BGRA -> RGB
        for mx, my, mw, mh in list(self.mask_rects):
            x0, y0 = max(0, mx - mon["left"]), max(0, my - mon["top"])
            x1, y1 = min(img.shape[1], mx + mw - mon["left"]), min(img.shape[0], my + mh - mon["top"])
            if x1 > x0 and y1 > y0:
                img[y0:y1, x0:x1] = 0
        if region:
            if img.shape[0] < 120:
                img = np.repeat(np.repeat(img, 2, axis=0), 2, axis=1)
        elif img.shape[1] > 2600:
            img = img[::2, ::2]
        return np.ascontiguousarray(img)

    def _run(self) -> None:
        try:
            import mss  # type: ignore
            engine = _OcrEngine(self.cfg.get("engine", "auto"))
        except Exception as e:  # noqa: BLE001
            self.on_status(f"OCR kapalı: {e}")
            return
        self.on_status(f"🔎 OCR açık ({engine.kind}), {len(self.cfg.get('regions') or [])} bölge")
        with mss.mss() as sct:
            while not self._stop.is_set():
                t0 = time.time()
                try:
                    regions = self.cfg.get("regions") or [None]
                    texts = [engine.read(self._grab(sct, r)) for r in regions]
                    raw = "\n".join(texts)
                    if raw and raw != self._last_raw:
                        self._last_raw = raw
                        reading = parse_hud_text(raw, self.name_index, self.scam_names)
                        if not reading.is_empty():
                            self.on_reading(reading)
                except Exception as e:  # noqa: BLE001
                    self.on_status(f"OCR hatası: {e}")
                wait = max(0.5, float(self.cfg.get("interval_s", 3.0)) - (time.time() - t0))
                self._stop.wait(wait)
