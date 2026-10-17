import unittest

from drakoria_bot import prey as P
from drakoria_bot.account import parse_gold

CFG = {"mode": "budget", "gold_per_day": 1000, "reserve_gold": 0}


def slot(options, free=False, gold=None, cards=False, enabled=True):
    return {"index": 0, "state": "selection", "options": options, "reroll_enabled": enabled,
            "reroll": {"free": free, "gold": gold, "cards": cards}}


class PreyRulesTest(unittest.TestCase):
    def test_parse_reroll(self):
        self.assertTrue(P.parse_reroll("Trocar a lista: grátis (1 por espaço por dia)", "Trocar lista Grátis hoje")["free"])
        self.assertEqual(P.parse_reroll("Trocar a lista: 1.200 gold", "Trocar lista 1.200 gold")["gold"], 1200)
        self.assertEqual(P.parse_reroll("", "Trocar lista 2,5k gold")["gold"], 2500)
        self.assertTrue(P.parse_reroll("", "Trocar lista 1 carta")["cards"])
        self.assertEqual(P.parse_reroll("", "Trocar lista")["gold"], None)       # preço desconhecido: nao paga
        paid = P.parse_reroll("Trocar a lista: 3.000 gold (a troca grátis volta à meia-noite)", "Trocar lista 3k gold")
        self.assertEqual((paid["free"], paid["gold"]), (False, 3000))                # visto ao vivo 17/10
        self.assertEqual(P.parse_price("Trocar a lista do espaço 2 por 3.000 gold? Cancelar Pagar 3.000 gold"), 3000)

    def test_gold(self):
        self.assertEqual(parse_gold("500"), 500)
        self.assertEqual(parse_gold("4,9k"), 4900)
        self.assertEqual(parse_gold("1.250"), 1250)
        self.assertEqual(parse_gold("1,2kk"), 1200000)

    def test_wanted_order_by_kills(self):
        self.assertEqual(P.wanted_order(["Rat", "Troll", "Spider"], {"Troll": 30, "Rat": 5}), ["Troll", "Rat", "Spider"])

    def test_choose_hunt_creature(self):
        self.assertEqual(P.decide(slot(["Bat", "Rat", "Troll"]), ["Troll", "Rat"], CFG, 0), ("choose", "Troll"))

    def test_free_reroll_before_paid(self):
        self.assertEqual(P.decide(slot(["Bat"], free=True), ["Troll"], CFG, 0), ("reroll", 0))

    def test_paid_reroll_respects_budget(self):
        self.assertEqual(P.decide(slot(["Bat"], gold=400), ["Troll"], CFG, 500), ("reroll", 400))
        self.assertEqual(P.decide(slot(["Bat"], gold=600), ["Troll"], CFG, 500), ("any", "Bat"))

    def test_until_found_ignores_budget_but_not_reserve(self):
        cfg = {"mode": "until_found", "gold_per_day": 0, "reserve_gold": 1000}
        self.assertEqual(P.decide(slot(["Bat"], gold=400), ["Troll"], cfg, 99999, gold_now=5000), ("reroll", 400))
        self.assertEqual(P.decide(slot(["Bat"], gold=400), ["Troll"], cfg, 0, gold_now=1200), ("any", "Bat"))

    def test_never_pays_cards_or_unknown(self):
        self.assertEqual(P.decide(slot(["Bat"], cards=True), ["Troll"], CFG, 0), ("any", "Bat"))
        self.assertEqual(P.decide(slot(["Bat"]), ["Troll"], CFG, 0), ("any", "Bat"))
        self.assertEqual(P.decide(slot(["Bat"], free=True, enabled=False), ["Troll"], CFG, 0), ("any", "Bat"))


if __name__ == "__main__":
    unittest.main()
