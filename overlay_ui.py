# -*- coding: utf-8 -*-
"""Oyunun üstünde duran yarı saydam, her zaman üstte (always-on-top) Tkinter penceresi."""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional

from game_state import fmt_time

COL = {
    "bg": "#0f1318", "panel": "#161c23", "fg": "#e8eef5", "dim": "#8b98a8", "say": "#ffe680",
    "say_bg": "#1d2530", "success": "#7cfc9a", "warn": "#ffb347", "danger": "#ff6b6b", "info": "#9fc5ff",
    "data": "#7cfc9a", "accent": "#5aa9ff", "btn": "#243040", "btn_fg": "#dfe7f1",
}
SEV_COLOR = {"info": COL["info"], "success": COL["success"], "warn": COL["warn"], "danger": COL["danger"]}

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20
WS_EX_TOOLWINDOW = 0x80
WS_EX_LAYERED = 0x80000
WS_EX_NOACTIVATE = 0x08000000


class OverlayUI:
    def __init__(self, root: tk.Tk, cfg: dict, actions: Dict[str, Callable], simulate: bool = False):
        self.root = root
        self.cfg = cfg
        self.ocfg = cfg["overlay"]
        self.actions = actions
        self.simulate = simulate
        self.visible = True
        self.click_through = bool(self.ocfg.get("click_through", False))
        self.compact = bool(self.ocfg.get("compact", False))
        self._drag = (0, 0)
        self.settings_win: Optional[tk.Toplevel] = None
        fam = self.ocfg.get("font_family", "Segoe UI")
        fs = int(self.ocfg.get("font_size", 11))
        self.f_small = (fam, max(8, fs - 1))
        self.f_norm = (fam, fs)
        self.f_bold = (fam, fs, "bold")
        self.f_say = (fam, int(self.ocfg.get("say_font_size", 17)), "bold")
        self.f_data = ("Consolas", fs + 3, "bold")
        self._build()
        self._apply_window_style()
        self._keep_on_top()

    # ================================================================== layout
    def _build(self) -> None:
        r = self.root
        r.title("SWYF Koç")
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.attributes("-alpha", float(self.ocfg.get("opacity", 0.9)))
        r.configure(bg=COL["bg"])
        r.geometry(f"{int(self.ocfg.get('width', 600))}x10+{int(self.ocfg.get('x', 40))}+{int(self.ocfg.get('y', 60))}")
        w = int(self.ocfg.get("width", 600))
        wrap = w - 28
        self.wrap = wrap

        self.header = tk.Frame(r, bg=COL["panel"])
        self.header.pack(fill="x")
        self.lbl_head = tk.Label(self.header, text="SWYF Koç", font=self.f_bold, fg=COL["fg"], bg=COL["panel"], anchor="w")
        self.lbl_head.pack(side="left", padx=8, pady=4, fill="x", expand=True)
        for txt, act in (("✕", "quit"), ("–", "toggle_compact"), ("⚙", "settings")):
            b = tk.Label(self.header, text=txt, font=self.f_bold, fg=COL["dim"], bg=COL["panel"], cursor="hand2", padx=6)
            b.pack(side="right")
            b.bind("<Button-1>", lambda e, a=act: self._do(a))
        self.level = tk.Canvas(self.header, width=60, height=10, bg=COL["panel"], highlightthickness=0)
        self.level.pack(side="right", padx=6)
        self.level_bar = self.level.create_rectangle(0, 0, 0, 10, fill=COL["accent"], width=0)
        for wdg in (self.header, self.lbl_head):
            wdg.bind("<ButtonPress-1>", self._drag_start)
            wdg.bind("<B1-Motion>", self._drag_move)
            wdg.bind("<ButtonRelease-1>", self._drag_end)

        body = tk.Frame(r, bg=COL["bg"])
        body.pack(fill="both", expand=True, padx=8, pady=(4, 6))
        self.body = body
        self.lbl_caller = tk.Label(body, text="🎭 —", font=self.f_bold, fg=COL["info"], bg=COL["bg"], anchor="w", justify="left", wraplength=wrap)
        self.lbl_scam = tk.Label(body, text="🎯 —", font=self.f_norm, fg=COL["fg"], bg=COL["bg"], anchor="w", justify="left", wraplength=wrap)
        self.lbl_heard = tk.Label(body, text="", font=self.f_small, fg=COL["dim"], bg=COL["bg"], anchor="w", justify="left", wraplength=wrap)
        self.lbl_gist = tk.Label(body, text="", font=self.f_norm, fg=COL["fg"], bg=COL["bg"], anchor="w", justify="left", wraplength=wrap)
        self.say_frame = tk.Frame(body, bg=COL["say_bg"], highlightbackground=COL["say"], highlightthickness=1)
        self.lbl_say_title = tk.Label(self.say_frame, text="🗣 SÖYLE", font=self.f_small, fg=COL["say"], bg=COL["say_bg"], anchor="w")
        self.lbl_say = tk.Label(self.say_frame, text="Oyunda bir arama aç; arayan konuşunca cümlen burada belirecek.",
                                font=self.f_say, fg=COL["say"], bg=COL["say_bg"], anchor="w", justify="left", wraplength=wrap - 16)
        self.lbl_alt = tk.Label(self.say_frame, text="", font=self.f_small, fg=COL["dim"], bg=COL["say_bg"], anchor="w", justify="left", wraplength=wrap - 16)
        self.lbl_say_title.pack(fill="x", padx=8, pady=(4, 0))
        self.lbl_say.pack(fill="x", padx=8, pady=(0, 2))
        self.lbl_alt.pack(fill="x", padx=8, pady=(0, 4))
        self.lbl_trust = tk.Label(body, text="", font=self.f_bold, fg=COL["info"], bg=COL["bg"], anchor="w", justify="left", wraplength=wrap)
        self._say_text = ""
        self._alt_text = ""
        for wdg in (self.say_frame, self.lbl_say, self.lbl_say_title):
            wdg.configure(cursor="hand2")
            wdg.bind("<Button-1>", lambda e: self._copy(self._say_text, "Cümle"))
        self.lbl_alt.configure(cursor="hand2")
        self.lbl_alt.bind("<Button-1>", lambda e: self._copy(self._alt_text, "Alternatif cümle"))
        self.lbl_note = tk.Label(body, text="", font=self.f_norm, fg=COL["fg"], bg=COL["bg"], anchor="w", justify="left", wraplength=wrap)
        self.lbl_action = tk.Label(body, text="", font=self.f_bold, fg=COL["accent"], bg=COL["bg"], anchor="w", justify="left", wraplength=wrap)
        self.lbl_data = tk.Label(body, text="", font=self.f_data, fg=COL["data"], bg=COL["bg"], anchor="w", justify="left", wraplength=wrap, cursor="hand2")
        self.lbl_data.bind("<Button-1>", lambda e: self._copy(self._data_value(), "Kod"))
        self.lbl_data.bind("<Enter>", lambda e: self.set_status("Tıkla → kod/numara boşluksuz kopyalanır (uygulamaya Ctrl+V)", transient=True))
        self.lbl_loc = tk.Label(body, text="", font=self.f_norm, fg=COL["info"], bg=COL["bg"], anchor="w", justify="left", wraplength=wrap)
        self.lbl_warn = tk.Label(body, text="", font=self.f_bold, fg=COL["danger"], bg=COL["bg"], anchor="w", justify="left", wraplength=wrap)
        self.lbl_foot = tk.Label(body, text="", font=self.f_bold, fg=COL["info"], bg=COL["bg"], anchor="w", justify="left", wraplength=wrap)
        self.btns = tk.Frame(body, bg=COL["bg"])
        for txt, act, tip in (("◀", "step_back", "F7"), ("✓ Adım", "step_done", "F6"), ("↻ Alt", "alt_line", "F9"),
                              ("Scam ▸", "next_scam", "F8"), ("📞 Yeni", "new_call", "F5"), ("⏱", "timer_toggle", "F10"),
                              ("Gün +", "next_day", "F11"), ("📋", "copy_line", "Ctrl+F9")):
            b = tk.Label(self.btns, text=txt, font=self.f_small, fg=COL["btn_fg"], bg=COL["btn"], padx=6, pady=2, cursor="hand2")
            b.pack(side="left", padx=(0, 4))
            b.bind("<Button-1>", lambda e, a=act: self._do(a))
            b.bind("<Enter>", lambda e, t=tip: self.set_status(f"Kısayol: {t}", transient=True))
        self.lbl_status = tk.Label(body, text="", font=self.f_small, fg=COL["dim"], bg=COL["bg"], anchor="w", justify="left", wraplength=wrap)
        self.sim_frame = None
        if self.simulate:
            self.sim_frame = tk.Frame(body, bg=COL["bg"])
            tk.Label(self.sim_frame, text="Arayan:", font=self.f_small, fg=COL["dim"], bg=COL["bg"]).pack(side="left")
            self.sim_entry = tk.Entry(self.sim_frame, font=self.f_norm, bg=COL["panel"], fg=COL["fg"], insertbackground=COL["fg"])
            self.sim_entry.pack(side="left", fill="x", expand=True, padx=4)
            self.sim_entry.bind("<Return>", self._sim_submit)
        self._layout()

    def _layout(self) -> None:
        for w in self.body.winfo_children():
            w.pack_forget()
        full = not self.compact
        seq = [self.lbl_caller, self.lbl_trust, self.lbl_scam]
        if full:
            seq += [self.lbl_heard, self.lbl_gist]
        seq += [self.say_frame, self.lbl_note, self.lbl_action, self.lbl_data]
        if full:
            seq += [self.lbl_loc, self.lbl_warn]
        seq += [self.lbl_foot]
        if full:
            seq += [self.btns, self.lbl_status]
        elif self._is_alert(self.lbl_status.cget("text")):
            seq += [self.lbl_status]
        if self.sim_frame is not None:
            seq.append(self.sim_frame)
        always = {self.lbl_caller, self.lbl_scam, self.say_frame, self.btns, self.sim_frame}
        for w in seq:
            if w in always or (isinstance(w, tk.Label) and w.cget("text")):
                w.pack(fill="x", pady=(2, 0))
        self.root.update_idletasks()
        self._fit()

    def _fit(self) -> None:
        self.root.update_idletasks()
        w = int(self.ocfg.get("width", 600))
        h = self.root.winfo_reqheight()
        self.root.geometry(f"{w}x{h}+{self.root.winfo_x()}+{self.root.winfo_y()}")

    # ================================================================== window style (Windows)
    def _hwnd(self) -> Optional[int]:
        if sys.platform != "win32":
            return None
        import ctypes
        self.root.update_idletasks()
        return ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()

    def _apply_window_style(self) -> None:
        hwnd = self._hwnd()
        if not hwnd:
            return
        import ctypes
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW
        if not self.simulate:
            style |= WS_EX_NOACTIVATE
        if self.click_through:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        self.root.attributes("-alpha", float(self.ocfg.get("opacity", 0.9)))

    def _keep_on_top(self) -> None:
        if self.visible:
            try:
                self.root.attributes("-topmost", True)
                self.root.lift()
            except tk.TclError:
                return
        self.root.after(int(self.ocfg.get("topmost_refresh_ms", 1500)), self._keep_on_top)

    def toggle_click_through(self) -> None:
        self.click_through = not self.click_through
        self.ocfg["click_through"] = self.click_through
        self._apply_window_style()
        self.set_status("Tıklama geçirgen: " + ("AÇIK (Ctrl+F11 ile kapat)" if self.click_through else "KAPALI"))

    def toggle_visibility(self) -> None:
        self.visible = not self.visible
        if self.visible:
            self.root.deiconify()
            self._apply_window_style()
        else:
            self.root.withdraw()

    def toggle_compact(self) -> None:
        self.compact = not self.compact
        self.ocfg["compact"] = self.compact
        self._layout()

    # ================================================================== drag
    def _drag_start(self, e) -> None:
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag_move(self, e) -> None:
        self.root.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _drag_end(self, _e) -> None:
        self.ocfg["x"], self.ocfg["y"] = self.root.winfo_x(), self.root.winfo_y()
        self._do("save_config")

    def _do(self, action: str) -> None:
        fn = self.actions.get(action)
        if fn:
            fn()

    def _sim_submit(self, _e=None) -> None:
        txt = self.sim_entry.get().strip()
        if txt:
            self.sim_entry.delete(0, "end")
            self.actions["sim_text"](txt)

    # ================================================================== rendering
    def render(self, adv) -> None:
        arch = f"{adv.archetype_tr} • {adv.level}"
        self.lbl_caller.config(text=f"🎭 {adv.caller_name}  —  {arch}")
        scam = "🎯 —"
        if adv.scam_name:
            scam = f"🎯 {adv.scam_name}  {adv.step_index}/{adv.step_total}: {adv.step_label_tr or adv.step_label}"
        if adv.plan:
            scam += "   ➜ " + " → ".join(adv.plan[1:3] if adv.plan and adv.scam_name and adv.plan[0].startswith(adv.scam_name) else adv.plan[:2])
        self.lbl_scam.config(text=scam)
        self.lbl_heard.config(text=f"👂 \"{adv.caller_said}\"" if adv.caller_said else "")
        gist = adv.caller_gist_tr or ""
        if adv.caller_tr:
            gist = f"🇹🇷 {adv.caller_tr}\n" + gist
        self.lbl_gist.config(text=gist)
        new_line = bool(adv.say) and adv.say != self._say_text
        self._say_text = adv.say or ""
        self._alt_text = adv.alternatives[0] if adv.alternatives else ""
        self._data_lines = list(adv.data_lines or [])
        self.lbl_say.config(text=adv.say or "…")
        auto = bool(self.cfg.get("auto_copy_say", True))
        hint = "  •  panoda — oyunda Ctrl+V" if auto else "  •  tıkla → kopyala"
        self.lbl_say_title.config(text="🗣 SÖYLE" + ("  (AI)" if adv.source == "AI" else "") + hint)
        self.lbl_alt.config(text=("alt (F9, tıkla → kopyala): " + adv.alternatives[0]) if adv.alternatives and not self.compact else "")
        if auto and new_line:
            self._copy(self._say_text, "Cümle", quiet=True)
        trust_line = getattr(adv, "trust_line", "")
        self.lbl_trust.config(text=trust_line, fg=SEV_COLOR.get(getattr(adv, "trust_severity", "info"), COL["info"]))
        note = adv.note_tr if self.cfg.get("show_turkish_notes", True) else ""
        self.lbl_note.config(text=("💡 " + note) if note else "", fg=SEV_COLOR.get(adv.severity, COL["fg"]) if adv.severity != "info" else COL["fg"])
        self.lbl_action.config(text=adv.player_action_tr or "")
        self.lbl_data.config(text="\n".join(adv.data_lines[-3:]) if adv.data_lines else "")
        self.lbl_loc.config(text=("📍 " + ", ".join(adv.location_hints)) if adv.location_hints else "")
        self.lbl_warn.config(text="\n".join(dict.fromkeys(adv.warnings)) if adv.warnings else "")
        self.update_footer(adv.footnote_tr, adv.footnote_severity, adv.quota_line)
        self._layout()

    def update_footer(self, foot: str, severity: str, quota_line: str) -> None:
        had = bool(self.lbl_foot.cget("text"))
        self.lbl_foot.config(text=foot or "", fg=SEV_COLOR.get(severity, COL["info"]))
        self.lbl_head.config(text=quota_line or "SWYF Koç")
        if had != bool(foot):
            self._layout()

    def set_level(self, db: float, speaking: bool) -> None:
        frac = max(0.0, min(1.0, (db + 70.0) / 60.0))
        self.level.coords(self.level_bar, 0, 0, int(60 * frac), 10)
        self.level.itemconfig(self.level_bar, fill=COL["success"] if speaking else COL["accent"])

    @staticmethod
    def _is_alert(text: str) -> bool:
        return bool(text) and (text.startswith(("❌", "⚠")) or "hata" in text.lower())

    def set_status(self, text: str, transient: bool = False) -> None:
        had = bool(self.lbl_status.cget("text"))
        self.lbl_status.config(text=text, fg=COL["warn"] if self._is_alert(text) else COL["dim"])
        if not transient:
            self._last_status = text
        if had != bool(text) or self.compact:
            self._layout()

    def show_briefing(self, text: str) -> None:
        self.lbl_note.config(text=text, fg=COL["fg"])
        self._layout()

    def _data_value(self) -> str:
        """Son veri satırını uygulamaya yapıştırılacak hale getirir (KOD/KART/SSN boşluksuz)."""
        for line in reversed(getattr(self, "_data_lines", [])):
            label, _, value = line.partition(": ")
            if not value:
                continue
            if any(k in label for k in ("KOD", "KART", "SSN")):
                return value.split("  SKT")[0].split(" / ")[-1].replace(" ", "").replace("-", "")
            return value.strip()
        return ""

    def _copy(self, text: str, what: str, quiet: bool = False) -> None:
        if not text:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()
        except tk.TclError:
            return
        if not quiet:
            self.set_status(f"📋 {what} kopyalandı → oyunda Ctrl+V", transient=True)
            old = self.lbl_say_title.cget("text")
            self.lbl_say_title.config(text=f"✅ {what} kopyalandı")
            self.root.after(1200, lambda: self.lbl_say_title.config(text=old))

    def copy_to_clipboard(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.set_status("📋 Cümle panoya kopyalandı (oyunda yazarak da gönderebilirsin).")

    # ================================================================== OCR region picker
    def pick_region(self, callback: Callable[[List[int]], None]) -> None:
        top = tk.Toplevel(self.root)
        top.attributes("-fullscreen", True)
        top.attributes("-topmost", True)
        top.attributes("-alpha", 0.3)
        top.configure(bg="black", cursor="crosshair")
        cv = tk.Canvas(top, bg="black", highlightthickness=0)
        cv.pack(fill="both", expand=True)
        cv.create_text(top.winfo_screenwidth() // 2, 40, text="HUD bölgesini (gün / kota / süre / Caller Trust / arayan adı) fareyle seç • Esc: iptal",
                       fill="white", font=self.f_bold)
        st = {"x": 0, "y": 0, "rect": None}

        def press(e):
            st["x"], st["y"] = e.x_root, e.y_root
            st["rect"] = cv.create_rectangle(e.x, e.y, e.x, e.y, outline="#00ff88", width=3)

        def move(e):
            if st["rect"]:
                cv.coords(st["rect"], st["x"] - top.winfo_rootx(), st["y"] - top.winfo_rooty(), e.x, e.y)

        def release(e):
            x0, y0 = min(st["x"], e.x_root), min(st["y"], e.y_root)
            w, h = abs(e.x_root - st["x"]), abs(e.y_root - st["y"])
            top.destroy()
            if w > 10 and h > 10:
                callback([int(x0), int(y0), int(w), int(h)])

        cv.bind("<ButtonPress-1>", press)
        cv.bind("<B1-Motion>", move)
        cv.bind("<ButtonRelease-1>", release)
        top.bind("<Escape>", lambda e: top.destroy())
        top.focus_force()

    # ================================================================== settings window
    def open_settings(self, state, db: dict, characters: List[tuple], apply_cb: Callable[[dict], None]) -> None:
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.lift()
            return
        win = tk.Toplevel(self.root)
        self.settings_win = win
        win.title("SWYF Koç — Durum & Ayarlar")
        win.attributes("-topmost", True)
        ox, ow = self.root.winfo_x(), int(self.ocfg.get("width", 600))
        sx = ox + ow + 10 if ox + ow + 520 < self.root.winfo_screenwidth() else max(0, ox - 530)
        win.geometry("+%d+%d" % (sx, self.root.winfo_y()))
        win.after(200, win.lift)
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        v: Dict[str, tk.Variable] = {}

        # ---------------- Durum
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="Durum")
        row = 0

        def add(label, widget):
            nonlocal row
            ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", pady=2)
            widget.grid(row=row, column=1, sticky="we", pady=2)
            row += 1

        v["day"] = tk.IntVar(value=state.day)
        wk_lbl = ttk.Label(f, text="")

        def upd_wk(*_):
            try:
                d = int(v["day"].get())
                wk_lbl.config(text=f"= {(d - 1) // 5 + 1}. Hafta, {(d - 1) % 5 + 1}. Gün")
            except (tk.TclError, ValueError):
                pass
        v["day"].trace_add("write", upd_wk)
        add("Gün (1-15):", ttk.Spinbox(f, from_=1, to=15, textvariable=v["day"], width=6))
        wk_lbl.grid(row=row, column=1, sticky="w")
        row += 1
        upd_wk()
        v["players"] = tk.IntVar(value=state.players)
        add("Oyuncu sayısı:", ttk.Spinbox(f, from_=1, to=8, textvariable=v["players"], width=6))
        v["quota"] = tk.StringVar(value=str(state.quota or ""))
        add(f"Kota $ (boş = tahmini {state.estimated_quota(db)}):", ttk.Entry(f, textvariable=v["quota"], width=10))
        v["earned"] = tk.StringVar(value=str(state.earned))
        add("Kazanılan $:", ttk.Entry(f, textvariable=v["earned"], width=10))
        quick = ttk.Frame(f)
        for amt in (-200, 200, 250, 300, 500, 600):
            ttk.Button(quick, text=f"{amt:+d}", width=5,
                       command=lambda a=amt: v["earned"].set(str(max(0, int(v["earned"].get() or 0) + a)))).pack(side="left")
        add("Hızlı ekle:", quick)
        v["shift"] = tk.DoubleVar(value=state.shift_minutes)
        add("Vardiya (dk):", ttk.Spinbox(f, from_=1, to=60, increment=1, textvariable=v["shift"], width=6))
        v["timer_enabled"] = tk.BooleanVar(value=state.timer_enabled)
        add("Sayaç açık:", ttk.Checkbutton(f, variable=v["timer_enabled"]))
        v["time_left"] = tk.StringVar(value="" if state.time_left() is None else fmt_time(state.time_left()))
        add("Kalan süre (dd:ss):", ttk.Entry(f, textvariable=v["time_left"], width=8))
        v["character"] = tk.StringVar(value="(Otomatik)")
        names = ["(Otomatik)"] + [n for _, n in characters]
        add("Arayan:", ttk.Combobox(f, textvariable=v["character"], values=names, width=40, state="readonly"))
        v["archetype"] = tk.StringVar(value="(Otomatik)")
        arch_names = ["(Otomatik)"] + [f"{k} — {a['name_tr']}" for k, a in db["archetypes"].items()]
        add("Arketip:", ttk.Combobox(f, textvariable=v["archetype"], values=arch_names, width=40, state="readonly"))
        f.columnconfigure(1, weight=1)

        # ---------------- Uygulamalar
        fa = ttk.Frame(nb, padding=8)
        nb.add(fa, text="Uygulamalar")
        ttk.Label(fa, text="İşaretli = bu gün açık ve satın alınmış (ücretliler için). Oyunda farklıysa düzelt.").grid(row=0, column=0, columnspan=3, sticky="w")
        v["apps"] = {}
        for i, (sid, s) in enumerate(db["scams"].items()):
            var = tk.BooleanVar(value=state.is_owned(sid, db))
            v["apps"][sid] = var
            cost = f" (${s['cost']})" if s.get("cost") else ""
            ttk.Checkbutton(fa, text=f"G{s.get('available_from_day', '?')}: {s['name']}{cost}", variable=var).grid(
                row=1 + i // 2, column=i % 2, sticky="w", padx=4)

        # ---------------- Ayarlar
        fs = ttk.Frame(nb, padding=8)
        nb.add(fs, text="Ayarlar")
        row2 = 0

        def add2(label, widget):
            nonlocal row2
            ttk.Label(fs, text=label).grid(row=row2, column=0, sticky="w", pady=2)
            widget.grid(row=row2, column=1, sticky="we", pady=2)
            row2 += 1

        v["language_level"] = tk.StringVar(value=self.cfg.get("language_level", "auto"))
        add2("Dil seviyesi:", ttk.Combobox(fs, textvariable=v["language_level"], values=["auto", "B1", "C1", "C2"], width=8, state="readonly"))
        v["max_level"] = tk.StringVar(value=self.cfg.get("max_level", "C2"))
        add2("En yüksek seviye:", ttk.Combobox(fs, textvariable=v["max_level"], values=["B1", "C1", "C2"], width=8, state="readonly"))
        v["agent_name"] = tk.StringVar(value=self.cfg.get("agent_name", "Steve"))
        add2("Sahte adın:", ttk.Entry(fs, textvariable=v["agent_name"]))
        v["company_name"] = tk.StringVar(value=self.cfg.get("company_name", ""))
        add2("Şirket adı:", ttk.Entry(fs, textvariable=v["company_name"]))
        v["translate_caller"] = tk.BooleanVar(value=self.cfg.get("translate_caller", True))
        add2("Arayanı Türkçeye çevir:", ttk.Checkbutton(fs, variable=v["translate_caller"]))
        v["auto_copy_say"] = tk.BooleanVar(value=self.cfg.get("auto_copy_say", True))
        add2("Yeni cümleyi otomatik panoya kopyala:", ttk.Checkbutton(fs, variable=v["auto_copy_say"]))
        v["ocr_enabled"] = tk.BooleanVar(value=self.cfg["ocr"].get("enabled", False))
        add2("OCR (ekrandan gün/kota/süre oku):", ttk.Checkbutton(fs, variable=v["ocr_enabled"]))
        ocr_btns = ttk.Frame(fs)
        ttk.Button(ocr_btns, text="Bölge ekle", command=lambda: self._do("calibrate_ocr")).pack(side="left")
        ttk.Button(ocr_btns, text="Bölgeleri temizle", command=lambda: self._do("clear_ocr")).pack(side="left", padx=4)
        add2("OCR bölgeleri:", ocr_btns)
        v["llm_enabled"] = tk.BooleanVar(value=self.cfg["llm"].get("enabled", False))
        add2("AI danışmanı (Claude):", ttk.Checkbutton(fs, variable=v["llm_enabled"]))
        v["llm_model"] = tk.StringVar(value=self.cfg["llm"].get("model", "claude-opus-5-5"))
        add2("AI modeli:", ttk.Combobox(fs, textvariable=v["llm_model"], values=["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"], width=24))
        v["llm_key"] = tk.StringVar(value=self.cfg["llm"].get("api_key", ""))
        add2("API anahtarı (boş = ANTHROPIC_API_KEY):", ttk.Entry(fs, textvariable=v["llm_key"], show="*"))
        v["opacity"] = tk.DoubleVar(value=float(self.ocfg.get("opacity", 0.9)))
        add2("Saydamlık:", ttk.Scale(fs, from_=0.4, to=1.0, variable=v["opacity"]))
        v["say_font"] = tk.IntVar(value=int(self.ocfg.get("say_font_size", 17)))
        add2("Cümle yazı boyutu:", ttk.Spinbox(fs, from_=10, to=32, textvariable=v["say_font"], width=6))
        fs.columnconfigure(1, weight=1)

        def collect() -> dict:
            out = {}
            for k, var in v.items():
                if k == "apps":
                    out["apps"] = {sid: bool(x.get()) for sid, x in var.items()}
                    continue
                try:
                    out[k] = var.get()
                except tk.TclError:
                    out[k] = None
            cname = out.get("character")
            out["character_id"] = next((cid for cid, n in characters if n == cname), None)
            arch = out.get("archetype") or ""
            out["archetype_id"] = arch.split(" — ")[0] if " — " in arch else None
            return out

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(bar, text="Uygula & Kaydet", command=lambda: apply_cb(collect())).pack(side="right")
        ttk.Button(bar, text="Kapat", command=win.destroy).pack(side="right", padx=4)
