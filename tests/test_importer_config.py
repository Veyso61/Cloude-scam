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
