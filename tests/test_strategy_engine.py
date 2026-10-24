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
        self.assertEqual(a.step_label, "Get the Social Security Number")   # oyunda adres/doğum tarihi adımı yok
        self.assertIn("Social Security number", a.say)
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
        eng.new_call()
        for _ in range(len(eng.db["scams"])):          # F8 ile Investment seç
            if eng.session.current == "investment":
                break
            eng.next_scam()
        self.assertEqual(eng.session.current, "investment")
        say(eng, clock, "What do you want? I manage a large portfolio.")
        self.assertEqual(eng.session.current, "investment")   # elle seçim, arayan konuşunca bozulmaz
        say(eng, clock, "Interesting, tell me more.")
        a = say(eng, clock, "Sounds good, go on.")
        self.assertEqual(a.step_label, "Agree on an Investment Amount")
        self.assertIn("eight hundred dollars", a.say)          # oyundaki en yüksek kademe
        a = say(eng, clock, "No, that's too much.")
        self.assertIn("$600", a.note_tr)
        a = say(eng, clock, "Okay, I will invest 650 dollars.")
        self.assertEqual(eng.session.agreed_amount, 650)
        self.assertEqual(eng._reward("investment"), 600)       # 650 → $600 kademesi

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


class AutoCallAndTrustTest(unittest.TestCase):
    def test_new_call_is_greeting_and_clears_old_caller(self):
        eng, st, clock = make(day=3)
        eng.new_call()
        say(eng, clock, "Hello? Yes, this is Dorothy Mayfield. I got a letter about my pension.")
        a = eng.new_call()
        self.assertTrue(a.new_call)
        self.assertIn("How can I help you today", a.say)
        self.assertEqual(a.caller_said, "")
        self.assertEqual(a.caller_name, "Bilinmeyen arayan")

    def test_ocr_name_change_auto_resets(self):
        eng, st, clock = make(day=1)
        eng.new_call()
        a = eng.on_ocr_caller("DAMIEN HOLLOWAY")
        self.assertEqual(a.caller_name, "Damien Holloway")
        self.assertIn("Hello Damien", a.say)
        say(eng, clock, "Hello. What do you need from me?")
        say(eng, clock, "Okay, sounds good.")
        self.assertIsNone(eng.on_ocr_caller("Damien Holloway"))
        a = eng.on_ocr_caller("FOREST DUMP")
        self.assertTrue(a.new_call)
        self.assertIn("Forest Dump", a.note_tr)
        self.assertIn("Hello Forest", a.say)
        self.assertEqual(eng.session.utterances, 0)

    def test_greeting_after_silence_starts_new_call(self):
        eng, st, clock = make(day=1)
        eng.new_call()
        say(eng, clock, "My order never arrived.")
        say(eng, clock, "Okay, sounds good.")
        a = say(eng, clock, "Hi! My mama always said you shouldn't talk to strangers.", wait=30)
        self.assertIn("Yeni arama", a.note_tr)
        self.assertEqual(eng.session.utterances, 1)

    def test_still_there_does_not_reset(self):
        eng, st, clock = make(day=1)
        eng.new_call()
        say(eng, clock, "My order never arrived.")
        say(eng, clock, "Okay, sounds good.")
        a = say(eng, clock, "Hello? Are you still there?", wait=40)
        self.assertNotIn("Yeni arama", a.note_tr)
        self.assertEqual(eng.session.utterances, 3)

    def test_spongebob_skip_ahead_code_with_letters(self):
        eng, st, clock = make(day=1)
        eng.new_call("spongebob")
        say(eng, clock, "Hi! I'm SpongeBob! The Krusty Krab register is broken, what do I need to do now?")
        say(eng, clock, "Okay!")
        a = say(eng, clock, "Okay, the code is X J nine four, seven seven two one!")
        self.assertEqual(a.step_label, "Enter it in the app")
        self.assertTrue(any("XJ94 7721" in d for d in a.data_lines))

    def test_trust_delta_feedback_and_success(self):
        eng, st, clock = make(day=1)
        eng.new_call()
        eng.update_trust(40, "Neutral")
        say(eng, clock, "Hi, my computer is broken.")
        eng.update_trust(25, "Suspicious")
        info, sev = eng._trust_info()
        self.assertIn("▼-15", info)
        self.assertEqual(sev, "warn")
        eng.update_trust(50, "Neutral")          # son cümleden beri +10 → ikna adımı sayılır
        a = say(eng, clock, "Hmm, I see.")
        self.assertEqual(a.step_label, "Agree to Gift Card Payment")
        eng.update_trust(70, "Trusting")
        self.assertEqual(eng.refresh().trust_severity, "success")

    def test_sync_with_game_checklist(self):
        eng, st, clock = make(day=1, owned_apps=["credit_card"])
        eng.new_call()
        self.assertIsNone(eng.sync_app("Credit Card", 0, 3, 400, "Convince the caller they need your service."))
        a = eng.sync_app("Credit Card", 1, 3, 400, "Get them to agree on a price for the service.")
        self.assertEqual(a.scam_id, "credit_card")
        self.assertEqual(a.step_label, "Get them to agree on a price for the service.")
        self.assertIn("Oyunda sıradaki", a.player_action_tr)
        self.assertIn("four hundred dollars", a.say)
        a = eng.sync_app("Credit Card", 3, 3, 400, "")
        self.assertEqual(st.earned, 400)
        self.assertIn("credit_card", eng.session.completed)
        self.assertEqual(st.observed_rewards["credit_card"], 400)

    def test_card_number_in_pieces(self):
        eng, st, clock = make(day=1, owned_apps=["credit_card"])
        eng.new_call()
        eng.next_scam()
        if eng.session.current != "credit_card":
            eng.next_scam()
        eng.session.step_idx["credit_card"] = 2
        a = say(eng, clock, "Okay, it's 4417 2231")
        self.assertIn("8/12", a.note_tr)          # oyundaki kart numarası 12 hane (4-4-4)
        a = say(eng, clock, "9981", wait=5)
        self.assertIn("credit_card", eng.session.completed)
        self.assertTrue(any("4417 2231 9981" in d for d in a.data_lines))

    def test_ip_geolocation_city_guess(self):
        eng, st, clock = make(day=6)
        eng.new_call()
        eng.session.current, eng.session.manual_scam = "ip_geolocation", True   # paralel scam; elle seçildi
        say(eng, clock, "Ugh, it's raining again and the tube was packed this morning.")
        a = say(eng, clock, "I just want a cup of tea and a few quid back, mate.")
        self.assertIn("London", a.player_action_tr)

    def test_cooperative_anyviewer_code_is_not_scambaiter(self):
        # Oyun verisine göre scambaiter'lar AnyViewer kodu vermez; kodu okuyan normal arayan işbirliği yapıyordur.
        eng, st, clock = make(day=5)
        eng.new_call()
        say(eng, clock, "Hi, my computer is acting weird.")
        a = say(eng, clock, "Okay, my AnyViewer code is 482 991, go ahead.")
        self.assertNotEqual(a.severity, "danger")
        self.assertEqual(a.scam_id, "anyviewer")

    def test_voice_changer_slip_flags_scambaiter(self):
        eng, st, clock = make(day=5)
        eng.new_call()
        say(eng, clock, "Hello dear.")
        a = say(eng, clock, "Ha! Oops, my voice changer slipped, I'm actually a scambaiter, gotcha!")
        self.assertEqual(a.severity, "danger")

    def test_known_streamer_is_not_flagged_as_scambaiter(self):
        eng, st, clock = make(day=4)
        eng.new_call("cheese_dip")
        a = say(eng, clock, "YOOOO what's good, CHAT! This is a scam call, chat, I'm recording this for my stream!")
        self.assertNotEqual(a.severity, "danger")

    def test_video_eleanor_price_question_reaches_code(self):
        # Kullanıcının videosu: Eleanor fiyat sordu, overlay 1. adımda takılıp aynı şeyi tekrar ettirdi.
        eng, st, clock = make(day=1)
        eng.new_call("eleanor_grimshaw")
        a = say(eng, clock, "Hello, dearie. My computer's been acting up something awful.")
        self.assertEqual(a.scam_id, "gift_card")
        first = a.say
        a = say(eng, clock, "Well, what's this resolution gonna cost me? I ain't made of money, y'know.")
        self.assertIn("no_money", a.intents)
        a = say(eng, clock, "Fascinating my foot, you keep jabberin' about overhauls and ain't said one word about a price yet.")
        self.assertEqual(a.step_label, "Agree to Gift Card Payment")     # 1. adımda takılı kalmadı
        self.assertIn("dollar", a.say.lower())                           # fiyatı söylüyor
        self.assertNotEqual(a.say, first)
        a = say(eng, clock, "Two hundred dollars on a gift card? Well, alright, I suppose.")
        self.assertEqual(a.step_label, "Obtain Gift Card Code")
        self.assertIn("code", a.say.lower())                             # kodu istiyor
        a = say(eng, clock, "Fine, the numbers on the back are 4417 2231.")
        self.assertEqual(a.step_label, "Enter it in the app")
        self.assertTrue(any("4417 2231" in d for d in a.data_lines))

    def test_no_repeat_after_neutral_reply(self):
        # Söylenen adıma itirazsız cevap gelirse aynı adım tekrar ettirilmez.
        eng, st, clock = make(day=1)
        eng.new_call("dorothy_mayfield")
        a = say(eng, clock, "Hello, dear. I'm hoping you can help me with my email.")
        step1 = a.step_label
        a = say(eng, clock, "Oh, I see. And then what happens?")
        self.assertNotEqual(a.step_label, step1)

    def test_identify_by_opening_line(self):
        eng, st, clock = make(day=1)
        eng.new_call()
        a = say(eng, clock, "Do you know who you are talking to right now?")
        self.assertEqual(a.caller_name, "Hiesenburger")
        eng.new_call()
        a = say(eng, clock, "Hello... hee-hee... this is Michael Jackson.")       # Whisper adı böyle yazar
        self.assertEqual(a.caller_name, "Micheal Jorkson")
        eng.new_call()
        a = say(eng, clock, "I'm ready!")
        self.assertEqual(a.caller_name, "Sponge Boy")

    def test_wrong_manual_pick_is_corrected_by_opening_line(self):
        # Ekran görüntüsü: listede Eleanor seçili kalmış, arayan Hiesenburger.
        eng, st, clock = make(day=1)
        eng.new_call()
        eng.set_character("eleanor_grimshaw")
        a = say(eng, clock, "Do you know who you are talking to right now?")
        self.assertEqual(a.caller_name, "Hiesenburger")
        self.assertIn("Açılış cümlesinden tanındı", a.note_tr)

    def test_screen_name_is_not_overridden_by_fingerprint(self):
        eng, st, clock = make(day=1)
        eng.on_ocr_caller('ELEANOR "GRANNY" GRIMSHAW')
        a = say(eng, clock, "Hello dearie, I'm ready!")
        self.assertEqual(a.caller_name, 'Eleanor "Granny" Grimshaw')

    def test_screenshot_vegan_lady_question_is_answered_first(self):
        # Kullanıcı ekranı: "Hi there! Are YOU vegan?" → koç soruyu yok sayıp "Don't worry about that..." demişti.
        eng, st, clock = make(day=1)
        eng.new_call()
        a = say(eng, clock, "Hi there! Are YOU vegan?")
        self.assertEqual(a.caller_name, "That Vegan Lady")
        self.assertTrue(a.say.startswith("Yes, I'm vegan too!"))
        self.assertIn("help you", a.say)                         # henüz derdi yok → önce derdini sor
        self.assertNotIn("worry", a.say.lower())
        a = say(eng, clock, "Oh wonderful! My oat milk delivery never showed up and I'm furious.")
        self.assertEqual(a.step_label, "Establish a Service or Solution")
        self.assertIn("dollars", a.say)                          # şimdi teklif + fiyat
        a = say(eng, clock, "Hmm, okay. And is it cruelty-free?")
        self.assertEqual(a.step_label, "Agree to Gift Card Payment")

    def test_mid_call_question_gets_answered(self):
        eng, st, clock = make(day=1)
        eng.new_call("cletus_thibodeaux")
        say(eng, clock, "Whoo-wee, hello! My crawfish trap is broken, cher.")
        a = say(eng, clock, "Mais yeah, sounds good! Say, do you like crawfish?")
        self.assertTrue(a.say.startswith("Yes, I love crawfish!"))
