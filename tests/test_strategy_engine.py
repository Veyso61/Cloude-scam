import unittest

from tests._helpers import FakeClock, load_db
from game_state import GameState
from strategy_engine import StrategyEngine


def make(day=3, **st_kw):
    db = load_db()
    st = GameState(day=day, **st_kw)
    eng = StrategyEngine(db, st, {"agent_name": "Steve"})
    clock = FakeClock()
    eng.now = clock
    return eng, st, clock


def say(eng, clock, text, wait=10):
    clock.advance(wait)
    return eng.on_caller_text(text)


class EngineTest(unittest.TestCase):
    def test_dorothy_ssn_chain(self):
        eng, st, clock = make(day=3)
        eng.new_call()
        a = say(eng, clock, "Hello? Yes, this is Dorothy Mayfield. I got a letter about my pension and I'm so confused.")
        self.assertEqual(a.caller_name, "Dorothy Mayfield")
        self.assertEqual(a.scam_id, "social_security")
        self.assertIn("Mrs. Mayfield", a.say)
        a = say(eng, clock, "Oh my, that's terrible! What do I do?")
        self.assertEqual(a.step_label, "Confirm Their Address")
        say(eng, clock, "I live at 42 Maple Street, Springfield.")
        say(eng, clock, "My birthday is March 3rd, 1948.")
        a = say(eng, clock, "Okay dear, it's 123-45-6789.")
        self.assertIn("SSN: 123-45-6789", a.data_lines)
        self.assertEqual(a.step_label, "Enter it in the app")
        a = say(eng, clock, "Is everything alright now?", wait=12)
        self.assertEqual(st.earned, 250)
        self.assertIn("social_security", eng.session.completed)
        self.assertNotEqual(a.scam_id, "social_security")
        self.assertEqual(a.severity, "success")

    def test_romance_order_and_reward(self):
        eng, st, clock = make(day=2)
        eng.new_call("kanye_east")
        a = say(eng, clock, "Yo, somebody sold me bootleg Yeezys, I'm a genius!")
        self.assertEqual(a.scam_id, "romance")
        self.assertNotIn("date", a.say.lower())
        say(eng, clock, "I love making music, obviously.")
        say(eng, clock, "Oh stop it, you're making me blush.")
        a = say(eng, clock, "Fine, I'll call you my little cupcake.")
        self.assertEqual(a.step_label, "Caller Says They Love You Back")
        a = say(eng, clock, "I love you too!")
        self.assertEqual(a.step_label, "Agree to a Date with a Specific Time")
        a = say(eng, clock, "Yes! It's a date, see you at 8.")
        self.assertEqual(st.earned, 600)
        self.assertEqual(a.scam_id, "gift_card")

    def test_caller_jumps_ahead_with_code(self):
        eng, st, clock = make(day=1)
        eng.new_call()
        say(eng, clock, "Hi, my order never arrived and I want a refund.")
        a = say(eng, clock, "Fine, here is the gift card code: X7K2 9Q41 ZZ38")
        self.assertEqual(a.step_label, "Enter it in the app")
        self.assertTrue(any("X7K2 9Q41 ZZ38" in d for d in a.data_lines))

    def test_objection_keeps_step(self):
        eng, st, clock = make(day=1)
        eng.new_call()
        say(eng, clock, "Hi, my computer is broken.")
        say(eng, clock, "Okay, sounds good.")
        a = say(eng, clock, "A gift card? Why would I pay with a gift card?")
        self.assertEqual(a.step_label, "Agree to Gift Card Payment")
        self.assertIn("why_payment", a.intents)

    def test_scambaiter_detection(self):
        eng, st, clock = make(day=4)
        eng.new_call()
        a = say(eng, clock, "Hi, I'm Arthur. Here, my AnyViewer code is 482 991 330, connect to my computer please!")
        self.assertEqual(a.severity, "danger")
        self.assertTrue(any("SCAMBAITER" in w for w in a.warnings))
        a = say(eng, clock, "Also click this link to get free Nitro!")
        self.assertEqual(a.severity, "danger")

    def test_vega_anyviewer_switch(self):
        eng, st, clock = make(day=5)
        eng.new_call("miles_vega")
        say(eng, clock, "This is Commander Vega. My terminal telemetry is failing, over.")
        a = say(eng, clock, "Negative. Explain the protocol, over.")
        self.assertIn("wants_procedure", a.intents)
        a = say(eng, clock, "Copy that. My AnyViewer code is 7 7 1 4 0 9 2 3, over.")
        self.assertEqual(a.scam_id, "anyviewer")
        self.assertTrue(any("7714 0923" in d for d in a.data_lines))

    def test_boss_fired_resets_run(self):
        eng, st, clock = make(day=5)
        eng.new_call()
        a = say(eng, clock, "The quota was missed by four hundred dollars. You're fired! All of you!")
        self.assertEqual(a.caller_gist_tr, "Patron değerlendirmesi")
        self.assertEqual(st.day, 1)

    def test_time_pressure_suggests_quick_switch(self):
        eng, st, clock = make(day=3, earned=800)
        st.set_time_left(100)
        eng.new_call()
        say(eng, clock, "Hi, I'm lonely and I just wanted someone to talk to.", wait=1)
        a = eng.refresh()
        self.assertEqual(eng.session.current, "gift_card")
        self.assertIn("eksik $200", a.footnote_tr)

    def test_time_pressure_hold_on_footnote(self):
        eng, st, clock = make(day=2, earned=300)
        st.set_time_left(170)
        eng.new_call()
        say(eng, clock, "Hi, my cereal box was empty!", wait=1)
        a = eng.refresh()
        self.assertIn(a.footnote_severity, ("warn", "danger"))
        self.assertTrue(a.footnote_tr)

    def test_quota_done_footnote(self):
        eng, st, clock = make(day=1, earned=700)
        a = eng.new_call()
        self.assertIn("Kota tamam", a.footnote_tr)

    def test_investment_ladder(self):
        eng, st, clock = make(day=5)
        eng.new_call("damien_holloway")
        say(eng, clock, "What do you want? I manage a large portfolio.")
        say(eng, clock, "Interesting, tell me more.")
        a = say(eng, clock, "Sounds good, go on.")
        self.assertEqual(a.step_label, "Agree on an Investment Amount")
        self.assertIn("two thousand dollars", a.say)
        a = say(eng, clock, "No, that's too much.")
        self.assertIn("$1,500", a.note_tr)
        a = say(eng, clock, "Okay, I will invest 1,500 dollars.")
        self.assertEqual(eng.session.agreed_amount, 1500)

    def test_character_by_keywords(self):
        eng, st, clock = make(day=1)
        eng.new_call()
        a = say(eng, clock, "Yo man, my 1999 Nissan Forza pickup truck needs more horsepower, I want a turbo and ECU tuning.")
        self.assertEqual(a.caller_name, "Kenzo Sivley")

    def test_llm_seq_guard(self):
        eng, st, clock = make(day=1)
        a = eng.new_call()
        self.assertIsNone(eng.apply_llm({"say": "x"}, a.seq - 1))
        b = eng.apply_llm({"say": "Custom line.", "note_tr": "not", "caller_tr": "çeviri", "step_done": False}, a.seq)
        self.assertEqual(b.say, "Custom line.")
        self.assertEqual(b.source, "AI")

    def test_manual_controls(self):
        eng, st, clock = make(day=2)
        eng.new_call()
        a = eng.step_done()
        self.assertEqual(a.step_index, 2)
        a = eng.step_back()
        self.assertEqual(a.step_index, 1)
        first = a.scam_id
        a = eng.next_scam()
        self.assertNotEqual(a.scam_id, first)
        alt = eng.alt_line()
        self.assertTrue(alt.say)

    def test_briefing(self):
        eng, st, clock = make(day=6)
        text = eng.day_briefing()
        self.assertIn("2. Hafta", text)
        self.assertIn("IP Geolocation", text)


if __name__ == "__main__":
    unittest.main()
