import unittest

import numpy as np

from tests._helpers import load_db
import text_analysis as ta
from audio_listener import VoiceSegmenter, resample
from hotkeys import MOD_CONTROL, MOD_SHIFT, VK, parse_hotkey
from screen_reader import parse_hud_text


class HotkeyParseTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_hotkey("f6"), (0, VK["f6"]))
        self.assertEqual(parse_hotkey("ctrl+shift+f12"), (MOD_CONTROL | MOD_SHIFT, VK["f12"]))
        with self.assertRaises(ValueError):
            parse_hotkey("ctrl+")


class HudParseTest(unittest.TestCase):
    def test_parse_hud(self):
        db = load_db()
        idx = {cid: [c["name"]] + c.get("aliases", []) for cid, c in db["characters"].items() if not c.get("generic")}
        text = "WEEK 1 DAY 3\nQUOTA\n$1,250 / $2,600\n04:06\nCALLER TRUST 65%\nTrusting\nDorothy Mayfield"
        r = parse_hud_text(text, idx, {"romance": "Romance Scam"})
        self.assertEqual((r.week, r.day, r.earned, r.quota, r.time_left, r.trust), (1, 3, 1250, 2600, 246, 65))
        self.assertEqual(r.trust_label, "Trusting")
        self.assertEqual(ta.best_fuzzy(r.caller_name, idx), "dorothy_mayfield")
        r2 = parse_hud_text("Tomorrow's scams: Romance Scam", None, {"romance": "Romance Scam"})
        self.assertEqual(r2.tomorrow_scams, ["romance"])


class AudioDspTest(unittest.TestCase):
    def test_resample_length(self):
        x = np.zeros(48000, dtype=np.float32)
        self.assertEqual(len(resample(x, 48000, 16000)), 16000)

    def test_segmenter_emits_speech_burst(self):
        sr = 48000
        seg = VoiceSegmenter(threshold_db=-50, margin_db=9, use_webrtcvad=False, end_silence_ms=300)
        t = np.arange(int(sr * 1.0)) / sr
        noise = (np.random.RandomState(0).randn(int(sr * 1.0)) * 0.0005).astype(np.float32)
        tone = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        out = []
        for chunk in (noise, tone, noise):
            for i in range(0, len(chunk), 480):
                out += seg.feed(chunk[i:i + 480], sr)
        self.assertEqual(len(out), 1)
        audio, rate = out[0]
        self.assertEqual(rate, sr)
        self.assertGreater(len(audio) / sr, 0.8)


if __name__ == "__main__":
    unittest.main()
