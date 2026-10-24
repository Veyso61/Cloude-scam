import os
import tempfile
import unittest

from tests._helpers import load_db
from game_state import GameState


class GameStateTest(unittest.TestCase):
    def setUp(self):
        self.db = load_db()

    def test_week_day(self):
        st = GameState(day=7)
        self.assertEqual((st.week, st.day_in_week), (2, 2))
        st.set_week_day(3, 1)
        self.assertEqual(st.day, 11)

    def test_next_day_and_prestige(self):
        st = GameState(day=15, earned=900)
        st.next_day()
        self.assertEqual((st.day, st.prestige, st.earned), (1, 1, 0))

    def test_quota(self):
        st = GameState(day=1)
        self.assertEqual(st.quota_value(self.db), 600)
        st.players = 2
        self.assertEqual(st.quota_value(self.db), 960)
        st.quota = 1608
        self.assertEqual(st.quota_value(self.db), 1608)

    def test_unlocks_and_purchases(self):
        st = GameState(day=1)
        self.assertEqual(st.usable_scams(self.db), ["gift_card"])
        st.owned_apps.append("credit_card")
        self.assertIn("credit_card", st.usable_scams(self.db))
        st.day = 6
        self.assertIn("warranty", st.usable_scams(self.db))
        self.assertNotIn("money_mule", st.usable_scams(self.db))
        st.unlock_overrides["money_mule"] = True
        self.assertIn("money_mule", st.usable_scams(self.db))

    def test_timer_and_persistence(self):
        st = GameState(shift_minutes=20)
        self.assertIsNone(st.time_left())
        st.set_time_left(125)
        self.assertAlmostEqual(st.time_left(), 125, delta=1)
        path = os.path.join(tempfile.mkdtemp(), "state.json")
        st.save(path)
        st2 = GameState.load(path)
        self.assertAlmostEqual(st2.time_left(), 125, delta=2)
        self.assertFalse(st2.timer_running)


if __name__ == "__main__":
    unittest.main()
