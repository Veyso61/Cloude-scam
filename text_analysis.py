# -*- coding: utf-8 -*-
"""Metin analizi: niyet sınıflandırma, kod / kart / SSN / e-posta / tutar / konum çıkarımı.

Bu modül sadece standart kütüphane kullanır; böylece motor testleri her platformda çalışır.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- sayılar

DIGIT_WORDS = {
    "zero": "0", "oh": "0", "o": "0", "nought": "0", "null": "0",
    "one": "1", "won": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "niner": "9",
}
TEEN_WORDS = {
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19",
}
TENS_WORDS = {
    "twenty": "2", "thirty": "3", "forty": "4", "fourty": "4", "fifty": "5",
    "sixty": "6", "seventy": "7", "eighty": "8", "ninety": "9",
}
REPEAT_WORDS = {"double": 2, "triple": 3}
CODE_FILLERS = {"dash", "hyphen", "space", "and", "then", "uh", "um", "comma", "slash", "point", "dot", "next", "is"}

CARDINALS = {
    **{k: int(v) for k, v in DIGIT_WORDS.items() if k not in ("oh", "o", "won", "nought", "null", "niner")},
    **{k: int(v) for k, v in TEEN_WORDS.items()},
    **{k: int(v) * 10 for k, v in TENS_WORDS.items()},
    "a": 1, "an": 1,
}
MULTIPLIERS = {"hundred": 100, "thousand": 1000, "grand": 1000, "k": 1000, "million": 1_000_000}

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+|[\-/]")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def _tokens(text: str) -> List[str]:
    return _TOKEN_RE.findall(text or "")


def extract_code_runs(text: str) -> List[str]:
    """Konuşmadaki rakam/harf dizilerini birleştirir.

    "four four one seven - twenty two thirty one" -> ["44172231"]
    "My code is X7K2 9Q41" -> ["X7K29Q41"]
    """
    toks = _tokens(text)
    runs: List[str] = []
    cur: List[str] = []
    pending_repeat = 1
    i = 0

    def flush():
        nonlocal cur
        if cur:
            runs.append("".join(cur))
        cur = []

    while i < len(toks):
        raw = toks[i]
        low = raw.lower()
        nxt = toks[i + 1].lower() if i + 1 < len(toks) else ""
        piece: Optional[str] = None
        if low in REPEAT_WORDS:
            pending_repeat = REPEAT_WORDS[low]
            i += 1
            continue
        if re.fullmatch(r"\d+(st|nd|rd|th)", low):
            piece = None
        elif raw.isdigit():
            piece = raw
        elif re.fullmatch(r"[A-Za-z]*\d[A-Za-z0-9]*", raw) and any(c.isdigit() for c in raw):
            piece = raw.upper()
        elif low in DIGIT_WORDS and not (low in ("o", "oh") and not cur and nxt not in DIGIT_WORDS and not nxt.isdigit()):
            piece = DIGIT_WORDS[low]
        elif low in TEEN_WORDS:
            piece = TEEN_WORDS[low]
        elif low in TENS_WORDS:
            if nxt in DIGIT_WORDS and DIGIT_WORDS[nxt] != "0" and nxt not in ("o", "oh"):
                piece = TENS_WORDS[low] + DIGIT_WORDS[nxt]
                i += 1
            else:
                piece = TENS_WORDS[low] + "0"
        elif low == "hundred" and cur:
            piece = "00"
        elif len(raw) == 1 and raw.isalpha() and raw.isupper() and raw not in ("I", "A") and cur:
            piece = raw
        elif (low in CODE_FILLERS or raw in ("-", "/")) and cur:
            i += 1
            continue
        if piece is not None:
            cur.append(piece * pending_repeat if len(piece) == 1 else piece)
            pending_repeat = 1
        else:
            pending_repeat = 1
            flush()
        i += 1
    flush()
    out = []
    for r in runs:
        digits = sum(c.isdigit() for c in r)
        if digits >= 4 or (len(r) >= 6 and digits >= 2):
            out.append(r)
    return out


def group_code(code: str, size: int = 4) -> str:
    return " ".join(code[i:i + size] for i in range(0, len(code), size))


def extract_ssn(text: str) -> Optional[str]:
    m = re.search(r"\b(\d{3})[\s\-.]?(\d{2})[\s\-.]?(\d{4})\b", text or "")
    if m:
        return "".join(m.groups())
    for run in extract_code_runs(text):
        if run.isdigit() and len(run) == 9:
            return run
    return None


def format_ssn(ssn: str) -> str:
    return f"{ssn[:3]}-{ssn[3:5]}-{ssn[5:]}" if len(ssn) == 9 else ssn


MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]


def extract_card(text: str) -> Dict[str, str]:
    """Kart numarası / son kullanma / CVV (bulunanlar)."""
    res: Dict[str, str] = {}
    runs = extract_code_runs(text)
    m = re.search(r"(?<!\d)(?:\d[ \-]?){12,18}\d(?!\d)", text or "")
    if m:
        res["number"] = re.sub(r"\D", "", m.group(0))
    for r in runs:
        d = re.sub(r"\D", "", r)
        if "number" in res:
            break
        if 13 <= len(d) <= 19:
            res["number"] = d
        elif len(d) > 19:
            res["number"] = d[:16]
    low = (text or "").lower()
    m = re.search(r"\b(0?[1-9]|1[0-2])\s*(?:/|-|slash|\s)\s*(20\d{2}|\d{2})\b", low)
    if m and not (res.get("number") and m.group(0).replace(" ", "") in res.get("number", "")):
        res["expiry"] = f"{int(m.group(1)):02d}/{m.group(2)[-2:]}"
    else:
        m2 = re.search(r"\b(" + "|".join(MONTHS) + r")\s*(?:of\s*)?(20\d{2}|\d{2})\b", low)
        if m2:
            res["expiry"] = f"{MONTHS.index(m2.group(1)) + 1:02d}/{m2.group(2)[-2:]}"
    m = re.search(r"(?:cvv|cvc|security code|three digits|3 digits|code on the back|on the back)[^0-9a-z]{0,6}(?:(?:is|are|it'?s|it is)\s*)?((?:\d|\s){3,6}|(?:(?:zero|one|two|three|four|five|six|seven|eight|nine|oh)\s*){3,4})", low)
    if m:
        cv = "".join(DIGIT_WORDS.get(w, w) for w in m.group(1).split())
        cv = re.sub(r"\D", "", cv)
        if 3 <= len(cv) <= 4:
            res["cvv"] = cv
    elif "number" in res:
        exp_digits = res.get("expiry", "").replace("/", "")
        for r in re.findall(r"\b\d{3,4}\b", text or ""):
            if r not in res["number"] and r != exp_digits:
                res["cvv"] = r
    return res


def extract_email(text: str) -> Optional[str]:
    t = text or ""
    m = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", t)
    if m:
        return m.group(0).lower()
    low = t.lower()
    spoken = re.search(r"([a-z0-9][a-z0-9 ._\-]{0,40}?)\s+at\s+([a-z0-9\-]+(?:\s+dot\s+[a-z0-9\-]+)+)", low)
    if spoken:
        user = spoken.group(1).strip()
        user = re.sub(r"^(it'?s|it is|my email is|the email is|email is|is)\s+", "", user)
        user = user.replace(" dot ", ".").replace(" underscore ", "_").replace(" dash ", "-").replace(" ", "")
        domain = spoken.group(2).replace(" dot ", ".").replace(" ", "")
        if user and "." in domain:
            return f"{user}@{domain}"
    return None


def words_to_number(words: Sequence[str]) -> Optional[int]:
    total, current, seen = 0, 0, False
    for w in words:
        w = w.lower().replace(",", "")
        if w.isdigit():
            current += int(w)
            seen = True
        elif w in CARDINALS:
            current += CARDINALS[w]
            seen = True
        elif w in MULTIPLIERS:
            mult = MULTIPLIERS[w]
            current = max(current, 1) * mult
            if mult >= 1000:
                total += current
                current = 0
            seen = True
        elif w in ("and",):
            continue
        else:
            break
    return total + current if seen else None


def extract_amount(text: str) -> Optional[int]:
    """'$1,500', '1500 dollars', 'fifteen hundred dollars', 'two grand' -> int."""
    t = (text or "").lower()
    m = re.search(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|grand)?", t)
    if m:
        val = float(m.group(1).replace(",", ""))
        if m.group(2):
            val *= 1000
        return int(val)
    m = re.search(r"\b(\d[\d,]*)\s*(k|thousand|grand|hundred)?\s*(dollars|bucks|usd|dollar)\b", t)
    if m:
        val = int(m.group(1).replace(",", ""))
        if m.group(2) in ("k", "thousand", "grand"):
            val *= 1000
        elif m.group(2) == "hundred":
            val *= 100
        return val
    m = re.search(r"((?:(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|grand|and)[\s\-]+)+)(dollars|bucks|grand)\b", t)
    if m:
        words = re.split(r"[\s\-]+", m.group(1).strip())
        if m.group(2) == "grand":
            words.append("grand")
        val = words_to_number(words)
        if val:
            return val
    m = re.search(r"\binvest(?:ing)?\s+((?:[a-z]+(?:[\s\-]+|$)){1,5})", t)
    if m:
        val = words_to_number(re.split(r"[\s\-]+", m.group(1).strip()))
        if val and val >= 50:
            return val
    return None


def amount_to_words(n: int) -> str:
    """350 -> 'three hundred and fifty dollars' (konuşma için)."""
    ones = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
            "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

    def below_1000(x: int) -> str:
        parts = []
        if x >= 100:
            parts.append(ones[x // 100] + " hundred")
            x %= 100
            if x:
                parts.append("and")
        if x >= 20:
            parts.append(tens[x // 10] + ("-" + ones[x % 10] if x % 10 else ""))
        elif x or not parts:
            parts.append(ones[x])
        return " ".join(parts)

    n = int(n)
    if n >= 1000:
        th, rest = divmod(n, 1000)
        s = below_1000(th) + " thousand"
        if rest:
            s += (" and " if rest < 100 else " ") + below_1000(rest)
    else:
        s = below_1000(n)
    return s + " dollars"


# --------------------------------------------------------------------------- kişisel bilgiler

_NAME_STOP = {"I", "Okay", "Ok", "Sorry", "Yes", "No", "Well", "Hello", "Hi", "Hey", "Just", "Not", "So", "The", "Calling",
              "Fine", "Good", "Here", "Very", "Really", "Afraid", "Sure", "Going", "Trying", "Glad", "Happy", "From", "Your"}


def extract_self_name(text: str) -> Optional[str]:
    m = re.search(r"\b(?:[Mm]y name is|[Mm]y name's|[Tt]his is|[Ii] am|[Ii]'m|[Ii]t's|[Cc]all me)\s+((?:Mr\.|Mrs\.|Ms\.|Dr\.|Commander|Count)?\s?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text or "")
    if not m:
        return None
    name = m.group(1).strip()
    first = name.split()[0]
    if first in _NAME_STOP:
        return None
    return name


_INTEREST_RE = re.compile(
    r"\b(?:i (?:really |just |absolutely )?(?:love|like|enjoy|adore)(?: to)?|my (?:favorite )?(?:hobby|hobbies|passion)(?: is| are)?|"
    r"i'?m (?:really )?(?:into|passionate about|a (?:big )?fan of)|in my free time,? i(?: like to| love to)?)\s+([a-z][a-z' \-]{2,40})",
    re.I)
_INTEREST_VERB_RE = re.compile(
    r"\bi (collect|paint|knit|bake|garden|fish|hike|dance|sing|play|read|cook|write|draw|travel|watch|ride|build|swim|run|surf|skate|crochet|sew|golf)\b\s*([a-z' \-]{0,30})",
    re.I)
_INTEREST_STOP = ("that", "it", "this", "you", "the idea", "the sound", "your", "to help", "to know", "what", "how", "when", "being",
                  "the way", "talking to you", "him", "her", "them", "a refund", "money", "my money")


def extract_interest(text: str) -> Optional[str]:
    t = text or ""
    m = _INTEREST_RE.search(t)
    if m:
        phrase = re.split(r"\b(?:and|but|because|so|when|which|although)\b|[.,!?]", m.group(1))[0].strip()
        if phrase and not phrase.lower().startswith(_INTEREST_STOP) and len(phrase) > 2:
            return phrase
    m = _INTEREST_VERB_RE.search(t)
    if m:
        obj = re.split(r"\b(?:and|but|because|so|when)\b|[.,!?]", m.group(2) or "")[0].strip()
        return (m.group(1) + (" " + obj if obj else "")).lower()
    return None


_PET_WORDS = r"(honey|sugar|star|darling|sweetie|sweetheart|baby|babe|cupcake|angel|pumpkin|muffin|teddy bear|teddy|prince|princess|king|queen|handsome|cutie|love|dear|hero|tiger|sunshine|buttercup|honeybun|sweet pea|snookums|lovebug|bunny|kitten|cowboy)"


def extract_nickname(text: str) -> Optional[str]:
    low = (text or "").lower()
    m = re.search(r"\bcall you (?:my )?(?:little |sweet |dear |big )?([a-z][a-z \-]{1,20}?)(?:[.,!?]|$| from| because| okay)", low)
    if m and m.group(1).strip().split()[0] not in ("back", "later", "tomorrow", "again", "that", "it", "when", "if", "in", "on", "at"):
        return m.group(1).strip()
    m = re.search(r"\byou'?re my (?:little |sweet |dear |big )?" + _PET_WORDS + r"\b", low)
    if m:
        return m.group(1)
    m = re.search(r"\b(?:okay|ok|fine|alright|yes|sure),? (?:my )?(?:little |sweet )?" + _PET_WORDS + r"\b", low)
    if m:
        return m.group(1)
    return None


def has_address(text: str) -> bool:
    return bool(re.search(
        r"\b\d{1,6}\s+(?:[A-Za-z]+\s){0,3}(?:street|st|avenue|ave|road|rd|lane|ln|drive|dr|boulevard|blvd|court|ct|way|place|pl|circle|terrace|highway|hwy|parkway)\b",
        text or "", re.I) or re.search(r"\bi live (?:in|on|at)\b", text or "", re.I))


def has_dob(text: str) -> bool:
    t = (text or "").lower()
    if re.search(r"\b(" + "|".join(MONTHS) + r")\s+\d{1,2}(st|nd|rd|th)?\b", t):
        return True
    if re.search(r"\b\d{1,2}(st|nd|rd|th)?\s+(of\s+)?(" + "|".join(MONTHS) + r")\b", t):
        return True
    if re.search(r"\b\d{1,2}[/\-.]\d{1,2}[/\-.](19|20)?\d{2}\b", t):
        return True
    return bool(re.search(r"\bborn\b", t) and re.search(r"\b(19|20)\d{2}\b|nineteen", t))


class LocationExtractor:
    def __init__(self, gazetteer: Dict[str, List[str]]):
        names = []
        for key in ("cities", "us_states", "countries"):
            names.extend(gazetteer.get(key, []))
        names = sorted(set(names), key=len, reverse=True)
        self._re = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.I) if names else None
        self._canon = {n.lower(): n for n in names}
        hints = sorted(set(gazetteer.get("hint_words", [])), key=len, reverse=True)
        self._hint_re = re.compile(r"\b(" + "|".join(re.escape(h) for h in hints) + r")\b", re.I) if hints else None
        self._from_re = re.compile(r"\b(?:live in|living in|calling from|here in|located in|based in|i'?m from|we'?re from|out in|down in|up in)\s+([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)")

    def extract(self, text: str) -> Tuple[List[str], List[str]]:
        places, hints = [], []
        if self._re:
            for m in self._re.finditer(text or ""):
                places.append(self._canon.get(m.group(1).lower(), m.group(1)))
        for m in self._from_re.finditer(text or ""):
            p = m.group(1)
            if p not in places and p.split()[0] not in _NAME_STOP:
                places.append(p)
        if self._hint_re:
            for m in self._hint_re.finditer(text or ""):
                hints.append(m.group(1).lower())
        return places, hints


# --------------------------------------------------------------------------- niyet & anahtar kelime

class IntentClassifier:
    SHORT_BONUS = {"agree", "refuse"}

    def __init__(self, intents: Dict[str, dict], threshold: int = 2):
        self.threshold = threshold
        self.compiled: Dict[str, List[Tuple[re.Pattern, int]]] = {}
        self.gist: Dict[str, str] = {}
        for name, spec in intents.items():
            self.compiled[name] = [(re.compile(p, re.I), int(w)) for p, w in spec.get("patterns", [])]
            self.gist[name] = spec.get("gist_tr", name)

    def scores(self, text: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        wc = word_count(text)
        for name, pats in self.compiled.items():
            s = sum(w * min(2, len(rx.findall(text or ""))) for rx, w in pats)
            if s and name in self.SHORT_BONUS and wc <= 5:
                s += 1
            if s:
                out[name] = s
        return out

    def classify(self, text: str) -> Dict[str, int]:
        sc = self.scores(text)
        fired = {k: v for k, v in sc.items() if v >= self.threshold}
        if "agree" in fired and "refuse" in fired:
            if fired["refuse"] >= fired["agree"]:
                fired.pop("agree")
            else:
                fired.pop("refuse")
        return fired


def keyword_hits(text: str, keywords: Iterable[str]) -> int:
    low = " " + (text or "").lower() + " "
    hits = 0
    for kw in keywords:
        k = kw.lower().strip()
        if not k:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", low):
            hits += 1
    return hits


def fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def best_fuzzy(name: str, candidates: Dict[str, List[str]], cutoff: float = 0.78) -> Optional[str]:
    """candidates: id -> [görünen ad + takma adlar]"""
    best_id, best = None, 0.0
    n = (name or "").lower().strip()
    if not n:
        return None
    for cid, names in candidates.items():
        for c in names:
            c = c.lower()
            r = fuzzy_ratio(n, c)
            if c and (c in n or n in c) and len(min(c, n, key=len)) >= 4:
                r = max(r, 0.9)
            if r > best:
                best_id, best = cid, r
    return best_id if best >= cutoff else None
