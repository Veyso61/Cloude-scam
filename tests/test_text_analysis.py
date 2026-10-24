import unittest

from tests._helpers import load_db
import text_analysis as ta


class TextAnalysisTest(unittest.TestCase):
    def test_spoken_code(self):
        self.assertEqual(ta.extract_code_runs("the code is four four one seven, twenty two thirty one, nine nine eight one"),
                         ["441722319981"])
        self.assertEqual(ta.extract_code_runs("It says X7K2-9Q41-ZZ38"), ["X7K29Q41ZZ38"])
        self.assertEqual(ta.extract_code_runs("double five three oh nine"), ["55309"])
        self.assertEqual(ta.extract_code_runs("born on the 3rd of March"), [])

    def test_card_ssn_email(self):
        c = ta.extract_card("My number is 4417 2231 9981 0042 and it expires 04/27, the three digits on the back are 123")
        self.assertEqual(c, {"number": "4417223199810042", "expiry": "04/27", "cvv": "123"})
        self.assertEqual(ta.extract_ssn("it is 123-45-6789"), "123456789")
        self.assertEqual(ta.extract_ssn("one two three four five six seven eight nine"), "123456789")
        self.assertEqual(ta.extract_email("dorothy dot mayfield at gmail dot com"), "dorothy.mayfield@gmail.com")

    def test_amounts(self):
        self.assertEqual(ta.extract_amount("Okay I will invest 1,500 dollars"), 1500)
        self.assertEqual(ta.extract_amount("fifteen hundred dollars"), 1500)
        self.assertEqual(ta.extract_amount("two grand"), 2000)
        self.assertEqual(ta.extract_amount("I can invest five hundred"), 500)
        self.assertEqual(ta.amount_to_words(300), "three hundred dollars")

    def test_personal(self):
        self.assertEqual(ta.extract_self_name("Hi, this is Dorothy Mayfield calling"), "Dorothy Mayfield")
        self.assertIsNone(ta.extract_self_name("I'm Calling about my order"))
        self.assertEqual(ta.extract_interest("Oh, I love gardening and baking pies"), "gardening")
        self.assertEqual(ta.extract_nickname("I'll call you my little honeybun."), "honeybun")
        self.assertIsNone(ta.extract_nickname("I will call you back later"))
        self.assertTrue(ta.has_address("I live at 42 Maple Street"))
        self.assertTrue(ta.has_dob("I was born March 3rd, 1948"))

    def test_intents(self):
        clf = ta.IntentClassifier(load_db()["intents"])
        self.assertIn("why_payment", clf.classify("A gift card? Why would I need a gift card?"))
        self.assertIn("refuse", clf.classify("No."))
        self.assertNotIn("refuse", clf.classify("No problem, go ahead"))
        self.assertIn("agree", clf.classify("Alright fine, sounds good"))
        self.assertIn("love", clf.classify("Okay... I love you too!"))
        self.assertIn("scambaiter", clf.classify("Click this link to claim your free Nitro"))
        self.assertIn("suspicious", clf.classify("This sounds like a scam, how do I know you're legit?"))

    def test_game_card_is_twelve_digits(self):
        # Oyundaki kredi kartı numarası 12 hane (4-4-4) — eskiden 13+ beklendiği için tanınmıyordu.
        c = ta.extract_card("Sure, it's 4417 2231 9981")
        self.assertEqual(c.get("number"), "441722319981")
        self.assertEqual(ta.extract_card("only 4417 2231").get("number"), None)

    def test_locations(self):
        loc = ta.LocationExtractor(load_db()["locations"])
        places, hints = loc.extract("I'm calling from Houston, Texas and it's raining")
        self.assertIn("Houston", places)
        self.assertIn("Texas", places)
        self.assertIn("raining", hints)


if __name__ == "__main__":
    unittest.main()
