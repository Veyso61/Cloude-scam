import re
import unittest

from tests._helpers import load_db

KNOWN_TOKENS = {"@agree", "@positive", "@question_price", "@any_worry", "@code", "@card", "@ssn", "@email", "@amount",
                "@interest", "@nickname", "@love", "@date", "@flirt", "@address", "@dob", "@text", "@location",
                "@paid", "@any", "@none"}
KNOWN_SLOTS = {"name", "formal_name", "agent", "company", "problem", "service", "interest", "pet_name",
               "their_nickname", "amount_words", "invest_ask", "date_time", "date_place"}


class DbIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = load_db()

    def _lines(self):
        db = self.db
        for sid, s in db["scams"].items():
            for st in s["steps"]:
                for lvl, lines in st["lines"].items():
                    for ln in lines:
                        yield f"{sid}:{st['id']}:{lvl}", ln
            for lvl, lines in s.get("bridge", {}).items():
                for ln in lines:
                    yield f"{sid}:bridge:{lvl}", ln
            for intent, by in s.get("objections", {}).items():
                for lvl, lines in by.items():
                    for ln in lines:
                        yield f"{sid}:obj:{intent}", ln
        for intent, spec in db["objections"].items():
            for key, val in spec.items():
                if key == "levels":
                    for lvl, lines in val.items():
                        for ln in lines:
                            yield f"obj:{intent}:{lvl}", ln
                elif isinstance(val, list):
                    for ln in val:
                        yield f"obj:{intent}:{key}", ln
        for cid, c in db["characters"].items():
            for key, lines in c.get("custom_lines", {}).items():
                for ln in lines:
                    yield f"char:{cid}:{key}", ln

    def test_scams_complete(self):
        for sid, s in self.db["scams"].items():
            self.assertIn("name", s)
            self.assertGreaterEqual(int(s["available_from_day"]), 1, sid)
            self.assertLessEqual(int(s["available_from_day"]), 15, sid)
            for c in s.get("chains_to", []) + s.get("requires", []):
                self.assertIn(c, self.db["scams"], f"{sid} -> {c}")
            if s.get("is_tool") and sid != "anyviewer":
                continue
            self.assertTrue(s["steps"], sid)
            for st in s["steps"]:
                for lvl in ("B1", "C1", "C2"):
                    self.assertTrue(st["lines"].get(lvl), f"{sid}:{st['id']} {lvl} boş")
                for tok in st["success"]:
                    if tok.startswith("@"):
                        self.assertIn(tok, KNOWN_TOKENS, f"{sid}:{st['id']}")
                    else:
                        re.compile(tok, re.I)
                for lvl in ("B1", "C1", "C2"):
                    self.assertIn(lvl, s["bridge"], f"{sid} bridge")

    def test_slots_known(self):
        for where, ln in self._lines():
            for slot in re.findall(r"\{([a-z_]+)\}", ln):
                self.assertIn(slot, KNOWN_SLOTS, f"{where}: {{{slot}}}")

    def test_intents_compile(self):
        for name, spec in self.db["intents"].items():
            for p, w in spec["patterns"]:
                re.compile(p, re.I)
                self.assertGreater(int(w), 0)
        for p, w in self.db["boss"]["patterns"]:
            re.compile(p, re.I)

    def test_characters_valid(self):
        db = self.db
        for cid, c in db["characters"].items():
            self.assertIn(c["archetype"], db["archetypes"], cid)
            for s in c["best_scams"] + c["avoid_scams"]:
                self.assertIn(s, db["scams"], f"{cid}: {s}")
            if c.get("topic"):
                self.assertIn(c["topic"], db["topics"], cid)
            for key in c.get("custom_lines", {}):
                sid, step = key.split(":")
                self.assertIn(step, [x["id"] for x in db["scams"][sid]["steps"]], f"{cid}: {key}")

    def test_pdf_and_research_characters_present(self):
        names = {c["name"] for c in self.db["characters"].values()}
        for must in ["Dorothy Mayfield", "Commander Miles \"Orbit\" Vega", "Kanye East", "Kenzo Sivley", "Chael Sonnen",
                     "Dracula", "Arthur Lin", "Franklin D. Hyper", "Damien Holloway", "Shanice \"Dee\" Bishop",
                     "Brittany \"Lexi\" Summers", "Eleanor \"Granny\" Grimshaw"]:
            self.assertIn(must, names)

    def test_week_schedule_matches_unlock_days(self):
        rules = self.db["game_rules"]
        seen = set()
        for wk, w in rules["weeks"].items():
            for day, sids in w["new_scams_by_day"].items():
                self.assertIn(int(day), w["days"])
                for sid in sids:
                    self.assertEqual(int(self.db["scams"][sid]["available_from_day"]), int(day), sid)
                    seen.add(sid)
        self.assertEqual(seen, set(self.db["scams"]))
        self.assertEqual(sorted(int(d) for d in rules["quota"]["solo_by_day"]), list(range(1, 16)))


if __name__ == "__main__":
    unittest.main()
