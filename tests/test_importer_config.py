import json
import os
import tempfile
import unittest

from tests._helpers import ROOT, load_db
import caller_importer as ci
import config as C


class ImporterTest(unittest.TestCase):
    def test_import_from_fake_game_folder(self):
        tmp = tempfile.mkdtemp()
        callers = os.path.join(tmp, "Game_Data", "StreamingAssets", "Callers", "Defaults")
        os.makedirs(callers)
        with open(os.path.join(callers, "042-margaret.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "Margaret Pemberton", "personality": "A lonely retired widow, 78 years old, very polite, "
                       "worried about her computer being slow and her pension. Loves knitting and her cat Mittens."}, f)
        with open(os.path.join(callers, "043-troll.json"), "w", encoding="utf-8") as f:
            json.dump({"displayName": "Zed Baiter", "systemPrompt": "You are a scambaiter. Waste the scammer's time, "
                       "send them a fake Nitro link and try to get them to click it."}, f)
        db = load_db()
        out = os.path.join(tmp, "imported.json")
        n = ci.import_callers([tmp], db, out, log=lambda *_: None)
        self.assertEqual(n, 2)
        with open(out, encoding="utf-8") as f:
            data = json.load(f)["characters"]
        m = data["imp_margaret_pemberton"]
        self.assertIn(m["archetype"], ("trusting", "lonely"))
        self.assertTrue(m["best_scams"])
        z = data["imp_zed_baiter"]
        self.assertEqual(z["archetype"], "scambaiter")
        self.assertTrue(z["hang_up"])
        merged = C.load_db(os.path.join(ROOT, "characters_db.json"), custom_path=os.path.join(tmp, "none.json"), imported_path=out)
        self.assertIn("imp_margaret_pemberton", merged["characters"])

    def test_import_real_identity_format(self):
        # Oyunun gerçek biçimi: kolkata-json/caller-identities/*.json → kimlik listesi
        tmp = tempfile.mkdtemp()
        folder = os.path.join(tmp, "kolkata-json", "caller-identities")
        os.makedirs(folder)
        identities = [
            {"id": "dorothy_mayfield", "displayName": "Dorothy Mayfield", "initialTrustPercent": 50,
             "personalityPrompt": "You are Dorothy, a kind retired librarian who is bad with technology and calls people dear."},
            {"id": "new_caller_x", "displayName": "Gus Peabody", "gender": "Male", "initialTrustPercent": 40,
             "firstMessages": ["Howdy, is this the help line?"],
             "personalityPrompt": "You are Gus, a grumpy 80 year old retired fisherman who is suspicious of phone calls."},
            {"id": "baiter_y", "displayName": "Ned Trickster", "callType": "scambaiter", "initialTrustPercent": 50,
             "personalityPrompt": "You are Ned, using a voice changer to play a sweet confused pensioner on the phone."},
        ]
        with open(os.path.join(folder, "set9.json"), "w", encoding="utf-8") as f:
            json.dump(identities, f)
        db = load_db()
        out = os.path.join(tmp, "imported.json")
        n = ci.import_callers([tmp], db, out, log=lambda *_: None)
        self.assertEqual(n, 2)                        # Dorothy zaten veritabanında (game_id) → atlanır
        with open(out, encoding="utf-8") as f:
            data = json.load(f)["characters"]
        gus = data["imp_gus_peabody"]
        self.assertEqual((gus["game_id"], gus["trust_start"], gus["gender"]), ("new_caller_x", 40, "Male"))
        self.assertEqual(gus["first_messages"], ["Howdy, is this the help line?"])
        ned = data["imp_ned_trickster"]
        self.assertTrue(ned["scambaiter"] and ned["hang_up"])
        self.assertEqual(ned["call_type"], "scambaiter")

    def test_workshop_caller_imported_and_recognised_by_opening_line(self):
        from game_state import GameState
        from strategy_engine import StrategyEngine
        tmp = tempfile.mkdtemp()
        ws = os.path.join(tmp, "steamapps", "workshop", "content", ci.APP_ID, "3999999999")
        os.makedirs(ws)
        with open(os.path.join(ws, "caller.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "default-workshop-3999999999", "displayName": "Tofu Tina", "callType": "victim",
                       "initialTrustPercent": 45, "firstMessages": ["Hiya! Have you tried my tofu lasagna?"],
                       "personalityPrompt": "You are Tofu Tina, a bubbly vegan chef who runs a tiny food truck and loves animals."}, f)
        db = load_db()
        out = os.path.join(tmp, "imported.json")
        self.assertEqual(ci.import_callers([ws], db, out, log=lambda *_: None), 1)
        merged = C.load_db(os.path.join(ROOT, "characters_db.json"), custom_path=os.path.join(tmp, "none.json"), imported_path=out)
        tina = merged["characters"]["imp_tofu_tina"]
        self.assertIn("kw:lasagna tried", tina["fingerprints"])
        eng = StrategyEngine(load_db(), GameState(day=1), {})
        eng.db["characters"] = merged["characters"]          # açılışta arka planda yapılan yenileme
        eng.reload_characters()
        eng.new_call()
        a = eng.on_caller_text("Hiya, have you tried my tofu lasagna?")
        self.assertEqual(a.caller_name, "Tofu Tina")
        self.assertTrue(a.say.startswith("Yes, I have"))

    def test_old_config_migrates_ocr_on_and_level_c1(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "config.json")
        old = {"agent_name": "Kevin", "max_level": "C2", "ocr": {"enabled": False, "interval_s": 3.0}}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(old, f)
        cfg = C.load_config(path)
        self.assertTrue(cfg["ocr"]["enabled"])
        self.assertEqual(cfg["max_level"], "C1")
        self.assertEqual(cfg["agent_name"], "Kevin")
        cfg["ocr"]["enabled"] = False                      # kullanıcı sonradan kapatırsa kapalı kalır
        C.save_config(cfg, path)
        self.assertFalse(C.load_config(path)["ocr"]["enabled"])

    def test_version_file_and_compare(self):
        self.assertNotEqual(C.APP_VERSION, "?")                 # VERSION dosyası paketle birlikte gelir
        self.assertGreater(C.version_key("2026.10.24-6"), C.version_key("2026.10.24-5"))
        self.assertGreater(C.version_key("2026.10.25-1"), C.version_key("2026.10.24-9"))
        self.assertGreater(C.version_key("2026.10.24-1"), C.version_key(""))

    def test_config_defaults_written(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "config.json")
        cfg = C.load_config(path)
        self.assertTrue(os.path.exists(path))
        self.assertEqual(cfg["hotkeys"]["step_done"], "f6")
        cfg["agent_name"] = "Kevin"
        C.save_config(cfg, path)
        self.assertEqual(C.load_config(path)["agent_name"], "Kevin")


if __name__ == "__main__":
    unittest.main()
