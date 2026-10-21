import os
import tempfile
import unittest

from drakoria_bot import config
from drakoria_bot.market import analysis as A
from drakoria_bot.market import imbuements as I
from drakoria_bot.market.store import Store
from drakoria_bot.market.watcher import MarketWatcher
from tests.test_market import FakeApi, day, detail, offer

CFG = {"good": 0.15, "great": 0.25, "excellent": 0.40, "trend_down": 0.10}
VOID = {"id": "void", "name": "Void", "category": "support", "kinds": ["helmet"],
        "materials": [{"name": "rope belt", "display": "Rope Belt", "qty": 25},
                      {"name": "silencer claws", "display": "Silencer Claws", "qty": 25},
                      {"name": "some grimeleech wings", "display": "Some Grimeleech Wings", "qty": 5}]}


def ev(name, offers, vwap):
    return A.evaluate(detail(offers, [day(20, vwap, 50)], vwap=vwap, name=name), CFG)


class RecipeTest(unittest.TestCase):
    def test_real_data(self):
        data = I.load()
        self.assertEqual(len(data["imbuements"]), 23)
        void = next(d for d in data["imbuements"] if d["id"] == "void")
        self.assertEqual([m["name"] for m in void["materials"]], ["rope belt", "silencer claws", "some grimeleech wings"])
        self.assertEqual(data["rules"]["goldFee"], 250000)

    def test_tier_uses_first_n_materials(self):
        self.assertEqual(len(I.materials_for(VOID, 0)), 1)
        self.assertEqual(len(I.materials_for(VOID, 1)), 2)
        self.assertEqual(len(I.materials_for(VOID, 2)), 3)

    def test_offer_cost(self):
        e = ev("rope belt", [offer("a", 20000, 10), offer("b", 25000, 100)], 25000)
        self.assertEqual(I.offer_cost(e, 15), 10 * 20000 + 5 * 25000)
        self.assertIsNone(I.offer_cost(e, 500))
        self.assertEqual(I.offer_cost(e, 0), 0)

    def test_plan_need_have_missing_and_tokens(self):
        board = {"rope belt": ev("rope belt", [offer("a", 20000, 100)], 25000),
                 "silencer claws": ev("silencer claws", [offer("s", 20000, 100)], 20000),
                 "gold token": ev("gold token", [offer("g", 40000, 50)], 40000)}
        p = I.plan(VOID, 1, 2, board, {"rope belt": 10}, {"goldFee": 250000, "goldTokenCost": 10, "silverTokenCost": 10})
        self.assertEqual([(l.name, l.need, l.have, l.missing) for l in p.lines],
                         [("rope belt", 50, 10, 40), ("silencer claws", 50, 0, 50)])
        self.assertEqual(p.cost_missing, 40 * 20000 + 50 * 20000)
        self.assertEqual(p.fee, 500000)
        self.assertEqual(p.token_cost["gold token"], 20 * 40000)
        self.assertIsNone(p.token_cost["silver token"])          # sem oferta

    def test_watched_materials(self):
        data = {"imbuements": [VOID]}
        self.assertEqual(I.watched_materials({"imbuements": {"void": {"watch": True, "tier": 0}}}, data),
                         {"rope belt", "silencer claws", "some grimeleech wings", "gold token", "silver token"})
        self.assertEqual(I.watched_materials({"imbuements": {"void": {"watch": False, "tier": 2}}}, data), set())


class ImbuementBuyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "m.db"), clock=lambda: 1_000_000.0)
        self.cfg = config._merge(config.DEFAULTS, {})["market"]
        listing = [{"id": "12448", "displayName": "rope belt", "sellQuantity": "40"},
                   {"id": "22534", "displayName": "silencer claws", "sellQuantity": "0"}]
        self.api = FakeApi(listing, {
            "12448": detail([offer("a", 21000, 10), offer("b", 24000, 30)], [day(20, 25000, 50)], vwap=25000,
                            item_id="12448", name="rope belt"),
            "22534": detail([], [day(19, 20000, 40)], vwap=20000, item_id="22534", name="silencer claws")})
        self.api.assets = lambda: {"rope belt": 5}
        self.logs = []
        self.w = MarketWatcher(self.cfg, self.store, self.logs.append, api_factory=lambda page: self.api)
        self.w.imb = {"imbuements": [VOID], "rules": {"goldFee": 250000, "goldTokenCost": 10, "silverTokenCost": 10}}

    def tearDown(self):
        self.tmp.cleanup()

    def tick(self):
        self.w.last_run = None
        self.w.tick(None, 1_000_000.0)

    def test_watched_material_without_offers_is_read(self):
        self.cfg["imbuements"] = {"void": {"watch": True, "tier": 1, "uses": 1}}
        self.tick()
        self.assertIn(("detail", "22534"), self.api.calls)
        self.assertEqual(self.w.owned, {"rope belt": 5})
        p = self.w.plans()["void"]
        self.assertEqual([(l.name, l.missing) for l in p.lines], [("rope belt", 20), ("silencer claws", 25)])

    def test_buys_opportunity_even_with_stock(self):
        self.api.assets = lambda: {"rope belt": 999}            # estoque cheio: compra mesmo assim (revenda)
        self.cfg.update(auto_buy=True, daily_budget=10**9)
        self.cfg["imbuements"] = {"void": {"watch": True, "tier": 0, "uses": 1, "buy": True, "pay_pct": 90}}
        self.tick()                    # justo 25k, paga ate 22.500 -> toda a oferta de 21k (10 un.), nao a de 24k
        self.assertEqual([c for c in self.api.calls if c[0] == "buy"], [("buy", "a", 10)])
        self.assertTrue(any("oportunidade Void" in line for line in self.logs))

    def test_daily_budget_limits_opportunities(self):
        self.cfg.update(auto_buy=True, daily_budget=50000, reserve_gold=0)
        self.cfg["imbuements"] = {"void": {"watch": True, "tier": 0, "uses": 1, "buy": True, "pay_pct": 90}}
        self.tick()
        self.assertEqual([c for c in self.api.calls if c[0] == "buy"], [("buy", "a", 2)])     # 2 x 21k = 42k
        self.api.calls.clear()
        self.tick()                    # orçamento do dia acabou (sobram 8k)
        self.assertNotIn("buy", [c[0] for c in self.api.calls])

    def test_above_pay_pct_not_bought(self):
        self.cfg.update(auto_buy=True, daily_budget=10**9)
        self.cfg["imbuements"] = {"void": {"watch": True, "tier": 0, "uses": 1, "buy": True, "pay_pct": 80}}
        self.tick()                    # 80% de 25k = 20k < 21k
        self.assertNotIn("buy", [c[0] for c in self.api.calls])

    def test_no_buy_without_switches(self):
        self.cfg["imbuements"] = {"void": {"watch": True, "tier": 0, "uses": 1, "buy": True, "pay_pct": 100}}
        self.tick()                    # chave geral desligada
        self.assertNotIn("buy", [c[0] for c in self.api.calls])
        self.cfg.update(auto_buy=True)
        self.cfg["imbuements"]["void"]["buy"] = False
        self.tick()
        self.assertNotIn("buy", [c[0] for c in self.api.calls])


if __name__ == "__main__":
    unittest.main()
