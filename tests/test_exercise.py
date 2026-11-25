import unittest

from drakoria_bot import exercise as X


class PlanTest(unittest.TestCase):
    def test_from_14h_to_40h_needs_7_when_nothing_owned(self):
        p = X.plan(14, 40, 0)
        self.assertAlmostEqual(p["hours"], 6.5)
        self.assertEqual(p["buy"], 7)              # 11.700 cargas / 1.800 = 6,5 -> 7 (inteiro)

    def test_owned_durables_are_discounted(self):
        self.assertEqual(X.plan(14, 40, 6)["buy"], 1)
        self.assertEqual(X.plan(18.7667, 40, 6)["buy"], 0)   # ja tem o suficiente

    def test_stamina_close_to_target_needs_nothing(self):
        self.assertEqual(X.plan(40, 40, 0)["buy"], 0)
        self.assertEqual(X.plan(41, 40, 0)["buy"], 0)

    def test_max_buy_limits_the_purchase(self):
        self.assertEqual(X.plan(14, 40, 0, max_buy=3)["buy"], 3)

    def test_unknown_stamina_does_not_buy(self):
        self.assertFalse(X.plan(None, 40, 0)["ok"])

    def test_vocation_from_formation_text(self):
        self.assertEqual(X.vocation_key("Elite Knight · Lv 972"), "knight")
        self.assertEqual(X.vocation_key("Royal Paladin · Lv 968"), "paladin")
        self.assertEqual(X.vocation_key("Master Sorcerer · Lv 972"), "sorcerer")
        self.assertEqual(X.vocation_key("Elder Druid · Lv 972"), "druid")
        self.assertIsNone(X.vocation_key("Monk · Lv 10"))


if __name__ == "__main__":
    unittest.main()
