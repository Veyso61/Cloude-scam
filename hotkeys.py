# -*- coding: utf-8 -*-
"""Global kısayol tuşları. Windows'ta Win32 RegisterHotKey (ek paket gerekmez), diğerlerinde pynput."""
from __future__ import annotations

import sys
import threading
from typing import Callable, Dict, List, Optional, Tuple

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

VK: Dict[str, int] = {**{f"f{i}": 0x6F + i for i in range(1, 25)},
                      **{chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)},
                      **{str(d): 0x30 + d for d in range(10)},
                      **{f"num{d}": 0x60 + d for d in range(10)},
                      "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "insert": 0x2D, "delete": 0x2E,
                      "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "left": 0x25, "up": 0x26,
                      "right": 0x27, "down": 0x28, "pause": 0x13, "scrolllock": 0x91, "printscreen": 0x2C,
                      "minus": 0xBD, "plus": 0xBB, "comma": 0xBC, "period": 0xBE}
MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}


def parse_hotkey(spec: str) -> Tuple[int, int]:
    mods, key = 0, None
    for part in [p.strip().lower() for p in spec.split("+") if p.strip()]:
        if part in MODS:
            mods |= MODS[part]
        elif part in VK:
            key = VK[part]
        else:
            raise ValueError(f"Bilinmeyen tuş: {part!r} ({spec})")
    if key is None:
        raise ValueError(f"Tuş eksik: {spec}")
    return mods, key


class HotkeyManager:
    def __init__(self, bindings: Dict[str, str], callbacks: Dict[str, Callable[[], None]],
                 on_status: Callable[[str], None] = lambda s: None):
        self.items: List[Tuple[str, str, Callable[[], None]]] = [
            (name, spec, callbacks[name]) for name, spec in bindings.items() if spec and name in callbacks]
        self.on_status = on_status
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._pynput = None

    def start(self) -> None:
        if sys.platform == "win32":
            self._thread = threading.Thread(target=self._win_loop, name="hotkeys", daemon=True)
            self._thread.start()
        else:
            self._start_pynput()

    def stop(self) -> None:
        if sys.platform == "win32" and self._thread_id:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._pynput is not None:
            try:
                self._pynput.stop()
            except Exception:
                pass

    # ------------------------------------------------------------------ Windows
    def _win_loop(self) -> None:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = wintypes.BOOL
        self._thread_id = kernel32.GetCurrentThreadId()
        registered: Dict[int, Callable[[], None]] = {}
        failed = []
        for i, (name, spec, cb) in enumerate(self.items, start=1):
            try:
                mods, vk = parse_hotkey(spec)
            except ValueError as e:
                failed.append(str(e))
                continue
            if user32.RegisterHotKey(None, i, mods | MOD_NOREPEAT, vk):
                registered[i] = cb
            else:
                failed.append(f"{spec} ({name}) başka program tarafından kullanılıyor")
        if failed:
            self.on_status("⚠ Kısayol hatası: " + "; ".join(failed))
        msg = wintypes.MSG()
        while True:
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r == 0 or r == -1:
                break
            if msg.message == WM_HOTKEY and msg.wParam in registered:
                try:
                    registered[msg.wParam]()
                except Exception as e:  # noqa: BLE001
                    self.on_status(f"Kısayol hatası: {e}")
        for i in registered:
            user32.UnregisterHotKey(None, i)

    # ------------------------------------------------------------------ pynput (Linux/macOS)
    def _start_pynput(self) -> None:
        try:
            from pynput import keyboard  # type: ignore
        except ImportError:
            self.on_status("Kısayollar kapalı (Windows dışında pynput gerekir).")
            return
        mapping = {}
        for name, spec, cb in self.items:
            parts = []
            for p in spec.lower().split("+"):
                p = p.strip()
                parts.append(f"<{'ctrl' if p == 'control' else p}>" if (p in MODS or (p.startswith("f") and p[1:].isdigit())) else p)
            mapping["+".join(parts)] = cb
        try:
            self._pynput = keyboard.GlobalHotKeys(mapping)
            self._pynput.start()
        except Exception as e:  # noqa: BLE001
            self.on_status(f"Kısayollar başlatılamadı: {e}")
