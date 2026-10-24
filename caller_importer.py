# -*- coding: utf-8 -*-
"""Oyunun kurulu dosyalarından (StreamingAssets/Callers, Workshop, CustomCallers) arayan kişiliklerini
okuyup characters_imported.json'a profil olarak yazar. Böylece veritabanında olmayan yeni / Workshop
arayanları da otomatik analiz edilir (arketip, konu, en iyi dolandırıcılıklar).

Kullanım:  python caller_importer.py            (Steam kurulumunu otomatik bulur)
           python caller_importer.py "D:\\SteamLibrary\\steamapps\\common\\Scam With Your Friends"
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import Counter
from typing import Dict, Iterable, List, Optional

import text_analysis as ta

APP_ID = "4954910"
GAME_DIR_HINTS = ["Scam With Your Friends", "ScamWithYourFriends", "Scam_With_Your_Friends"]
NAME_KEYS = ("name", "displayName", "display_name", "callerName", "caller_name", "characterName", "character_name", "fullName", "title")
TEXT_KEYS = ("personality", "description", "systemPrompt", "system_prompt", "prompt", "backstory", "bio", "background",
             "persona", "traits", "instructions", "notes", "context", "scenario", "reason", "problem", "opening", "greeting")
MAX_FILE_BYTES = 2_000_000


def _steam_paths() -> List[str]:
    paths = []
    if sys.platform == "win32":
        try:
            import winreg  # type: ignore
            for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        for val in ("SteamPath", "InstallPath"):
                            try:
                                paths.append(winreg.QueryValueEx(k, val)[0])
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass
        paths += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    else:
        paths += [os.path.expanduser("~/.steam/steam"), os.path.expanduser("~/.local/share/Steam")]
    libs = []
    for p in paths:
        p = os.path.normpath(p)
        if not os.path.isdir(p):
            continue
        libs.append(p)
        vdf = os.path.join(p, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf):
            try:
                with open(vdf, "r", encoding="utf-8", errors="ignore") as f:
                    for m in re.finditer(r'"path"\s*"([^"]+)"', f.read()):
                        libs.append(os.path.normpath(m.group(1).replace("\\\\", "\\")))
            except OSError:
                pass
    return list(dict.fromkeys(libs))


def find_game_dirs() -> List[str]:
    out = []
    for lib in _steam_paths():
        common = os.path.join(lib, "steamapps", "common")
        if os.path.isdir(common):
            for d in os.listdir(common):
                if any(h.lower() in d.lower() for h in GAME_DIR_HINTS):
                    out.append(os.path.join(common, d))
        ws = os.path.join(lib, "steamapps", "workshop", "content", APP_ID)
        if os.path.isdir(ws):
            out.append(ws)
    locallow = os.path.join(os.path.expanduser("~"), "AppData", "LocalLow")
    if os.path.isdir(locallow):
        for company in os.listdir(locallow):
            cdir = os.path.join(locallow, company)
            if not os.path.isdir(cdir):
                continue
            for prod in os.listdir(cdir):
                if "scam" in prod.lower():
                    out.append(os.path.join(cdir, prod))
    return list(dict.fromkeys(out))


def _iter_json_files(root: str) -> Iterable[str]:
    for path in glob.iglob(os.path.join(root, "**", "*.json"), recursive=True):
        low = path.lower()
        if any(s in low for s in ("caller", "character", "persona", "custom", "workshop", APP_ID)) or "streamingassets" in low:
            try:
                if os.path.getsize(path) <= MAX_FILE_BYTES:
                    yield path
            except OSError:
                continue


def _walk(obj, depth=0):
    if depth > 6:
        return
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v, depth + 1)


def _flatten_text(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return " ".join(_flatten_text(x) for x in v)
    if isinstance(v, dict):
        return " ".join(_flatten_text(x) for x in v.values())
    return ""


def extract_callers(data) -> List[Dict[str, str]]:
    found = []
    for d in _walk(data):
        name = next((d[k] for k in NAME_KEYS if isinstance(d.get(k), str) and 1 < len(d[k]) < 60), None)
        text = " ".join(_flatten_text(d[k]) for k in TEXT_KEYS if k in d)
        if name and len(text) >= 40:
            found.append({"name": name.strip(), "text": text[:6000]})
    return found


def build_profile(name: str, text: str, db: dict, source: str) -> dict:
    low = text.lower()
    arch_scores = Counter({aid: ta.keyword_hits(low, a.get("keywords", [])) for aid, a in db["archetypes"].items()})
    if re.search(r"\b(elderly|old (lady|man|woman)|grandma|grandpa|retired|senior|\b[6-9]\d[- ]year[- ]old)", low):
        arch_scores["trusting"] += 3
    if re.search(r"\b(scambait|waste (the )?scammer|troll|hack (the )?scammer|reverse)", low):
        arch_scores["scambaiter"] += 5
    if re.search(r"\b(suspicious|skeptic|paranoid|distrust|careful|cautious|verify)", low):
        arch_scores["skeptical"] += 2
    if re.search(r"\b(narcissis|ego|arrogant|famous|celebrity|rapper|star)\b", low):
        arch_scores["ego"] += 2
    if re.search(r"\b(lonely|widow|alone|single)\b", low):
        arch_scores["lonely"] += 2
    if re.search(r"\b(impatient|busy|rude|short-tempered|angry)\b", low):
        arch_scores["mixed"] += 2
    arch, sc = arch_scores.most_common(1)[0]
    if sc <= 0:
        arch = "trusting"
    topic_scores = Counter({tid: ta.keyword_hits(low, t.get("keywords", [])) for tid, t in db["topics"].items()})
    topic, tsc = topic_scores.most_common(1)[0]
    topic = topic if tsc > 0 else None
    best = []
    if topic:
        best += db["topics"][topic]["best_scams"]
    aff = db["archetypes"][arch].get("scam_affinity", {})
    best += [sid for sid, _ in sorted(aff.items(), key=lambda kv: -kv[1])]
    best = [s for s in dict.fromkeys(best) if s in db["scams"]][:6]
    words = re.findall(r"[a-z][a-z'\-]{3,}", low)
    stop = {"that", "this", "with", "they", "their", "have", "will", "your", "from", "when", "what", "about", "would",
            "there", "been", "were", "them", "very", "just", "like", "into", "always", "never", "caller", "player", "scammer",
            "should", "could", "which", "other", "only", "also", "then", "than", "more", "most", "some", "such", "does"}
    keywords = [w for w, _ in Counter(w for w in words if w not in stop).most_common(12)]
    cid = "imp_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    first = name.split()[0].strip('"')
    return {
        "id": cid, "name": name, "aliases": [first.lower()] if len(first) >= 3 else [],
        "archetype": arch, "verified": True, "source_tr": f"Oyun dosyasından içe aktarıldı: {source}",
        "first_name": first, "formal_name": name, "typical_week": 1,
        "profile_tr": "(Oyun dosyası) " + text[:280].replace("\n", " ") + ("…" if len(text) > 280 else ""),
        "weakness_tr": db["archetypes"][arch]["tone_tr"], "fatal_tr": db["archetypes"][arch].get("dont_tr", []),
        "keywords": keywords, "topic": topic, "best_scams": best, "avoid_scams": [],
        "scambaiter": arch == "scambaiter", "hang_up": arch == "scambaiter",
    }


def import_callers(roots: List[str], db: dict, out_path: str, log=print) -> int:
    existing_names = {c["name"].lower() for c in db["characters"].values()}
    result: Dict[str, dict] = {}
    for root in roots:
        n_files = 0
        for path in _iter_json_files(root):
            n_files += 1
            try:
                with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            for c in extract_callers(data):
                if c["name"].lower() in existing_names:
                    continue
                prof = build_profile(c["name"], c["text"], db, os.path.relpath(path, root))
                result[prof["id"]] = prof
        log(f"[import] {root}: {n_files} JSON tarandı")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"characters": result}, f, ensure_ascii=False, indent=1)
    log(f"[import] {len(result)} yeni arayan → {out_path}")
    return len(result)


def main(argv: Optional[List[str]] = None) -> int:
    from config import DB_PATH, IMPORTED_DB_PATH
    argv = argv if argv is not None else sys.argv[1:]
    with open(DB_PATH, "r", encoding="utf-8") as f:
        db = json.load(f)
    roots = argv or find_game_dirs()
    if not roots:
        print("Oyun klasörü bulunamadı. Yolu argüman olarak verin:\n  python caller_importer.py \"D:\\SteamLibrary\\steamapps\\common\\Scam With Your Friends\"")
        return 1
    import_callers(roots, db, IMPORTED_DB_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
