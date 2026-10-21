import os
import tempfile
import unittest

from drakoria_bot import config
from drakoria_bot.market import analysis as A
from drakoria_bot.market.api import MarketError
from drakoria_bot.market.store import Store
from drakoria_bot.market.watcher import MarketWatcher

CFG = {"good": 0.15, "great": 0.25, "excellent": 0.40, "trend_down": 0.10}


def day(d, vwap, qty):
    return {"day": f"2026-10-{d:02d}T03:00:00.000Z", "vwap_price_gold": str(vwap), "quantity_traded": str(qty),
            "minimum_price_gold": str(vwap), "maximum_price_gold": str(vwap), "trades_count": "1"}


def offer(oid, price, qty, mine=False, status="ACTIVE"):
    return {"id": oid, "unitPriceGold": str(price), "remainingQuantity": str(qty), "mine": mine, "status": status, "version": 1}


def detail(offers, daily, vwap=None, item_id="12448", name="rope belt"):
    trades = {"vwap": str(vwap) if vwap else None, "trades": len(daily)}
    return {"item": {"id": item_id, "displayName": name}, "sellOffers": offers, "buyOffers": [],
            "statistics": {"trades": trades, "daily": daily, "lowestSell": None, "highestBuy": None}}


class AnalysisTest(unittest.TestCase):
    def test_fair_is_lower_of_window_and_recent(self):
        d = detail([offer("a", 15000, 10)], [day(14, 40000, 10), day(15, 40000, 10), day(18, 20000, 10),
                                             day(19, 20000, 10), day(20, 20000, 10)], vwap=28000)
        ev = A.evaluate(d, CFG)
        self.assertEqual(ev.vwap_recent, 20000)
        self.assertEqual(ev.fair, 20000)
        self.assertAlmostEqual(ev.discount, 0.25)
        self.assertLess(ev.trend, -0.3)            # ultimo dia (20k) vs anteriores (30k)
        self.assertEqual(ev.quality, "boa")          # muito boa (25%) cai um nivel com o preço despencando

    def test_quality_levels_and_ignores_own_or_closed_offers(self):
        d = detail([offer("mine", 1000, 5, mine=True), offer("x", 1000, 5, status="FILLED"), offer("b", 12000, 3)],
                   [day(18, 20000, 10), day(19, 20000, 10), day(20, 20000, 10)], vwap=20000)
        ev = A.evaluate(d, CFG)
        self.assertEqual(ev.lowest_sell, 12000)
        self.assertEqual(ev.quality, "excelente")
        self.assertEqual(ev.suggested_max, 16000)

    def test_outlier_day_ignored(self):
        # visto ao vivo 20/10: Protective Charm com 50 un. a 1 de ouro num dia
        d = detail([offer("a", 49999, 185)], [day(18, 24607, 51), day(19, 1, 50), day(20, 50000, 71)], vwap=27936)
        ev = A.evaluate(d, CFG)
        self.assertAlmostEqual(ev.vwap_window, (24607 * 51 + 50000 * 71) / 122, places=0)
        self.assertGreater(ev.fair, 39000)

    def test_recent_follows_last_days(self):
        # Rope Belt 20/10: 43k -> 36,6k -> 25k (476 un.): o justo acompanha a queda
        d = detail([offer("a", 25000, 524)], [day(18, 43000, 80), day(19, 36666, 75), day(20, 25000, 476)], vwap=28669)
        ev = A.evaluate(d, CFG)
        self.assertEqual(ev.fair, 25000)
        self.assertLess(ev.trend, -0.3)
        self.assertIsNone(ev.quality)

    def test_no_trades_no_quality(self):
        ev = A.evaluate(detail([offer("a", 100, 1)], []), CFG)
        self.assertIsNone(ev.fair)
        self.assertIsNone(ev.quality)

    def test_buy_plan_limits(self):
        ev = A.evaluate(detail([offer("a", 10000, 2), offer("b", 12000, 5), offer("c", 30000, 9)],
                               [day(20, 25000, 5)], vwap=25000), CFG)
        plan = A.buy_plan(ev, max_price=15000, want=4, gold_available=100000)
        self.assertEqual([(o["id"], q) for o, q in plan], [("a", 2), ("b", 2)])
        plan = A.buy_plan(ev, 15000, 10, gold_available=60000, reserve=20000)          # 40k livres
        self.assertEqual([(o["id"], q) for o, q in plan], [("a", 2), ("b", 1)])
        plan = A.buy_plan(ev, 15000, 10, gold_available=10**9, budget_left=10000)
        self.assertEqual([(o["id"], q) for o, q in plan], [("a", 1)])


class FakeApi:
    def __init__(self, listing, details, gold=10_000_000):
        self.listing, self.details, self.gold = listing, details, gold
        self.calls = []
        self.fail_buy = False

    def items(self, category):
        self.calls.append(("items", category))
        return self.listing

    def detail(self, item_id):
        self.calls.append(("detail", item_id))
        return self.details[item_id]

    def overview(self):
        return {"wallet": {"goldSpendable": str(self.gold)}}

    def buy(self, off, quantity):
        self.calls.append(("buy", off["id"], quantity))
        if self.fail_buy:
            raise MarketError("versao mudou")
        return {"ok": True, "delivery": {"id": "d-" + off["id"]}}

    def claim(self, delivery_id):
        self.calls.append(("claim", delivery_id))
        return {"ok": True}


class WatcherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = [1_000_000.0]
        self.store = Store(os.path.join(self.tmp.name, "m.db"), clock=lambda: self.now[0])
        self.cfg = config._merge(config.DEFAULTS, {})["market"]
        listing = [{"id": "12448", "displayName": "rope belt", "category": "Imbuement Materials", "lowestSell": "12000",
                    "sellQuantity": "8"},
                   {"id": "1", "displayName": "sem oferta", "category": "Imbuement Materials", "sellQuantity": "0"}]
        self.api = FakeApi(listing, {"12448": detail([offer("a", 12000, 3), offer("b", 14000, 5), offer("c", 30000, 9)],
                                                     [day(18, 20000, 10), day(19, 20000, 10), day(20, 20000, 10)],
                                                     vwap=20000)})
        self.logs, self.notes = [], []
        self.cfg["warmup_seconds"] = 0
        self.w = MarketWatcher(self.cfg, self.store, self.logs.append, notify=lambda t, x: self.notes.append((t, x)),
                               api_factory=lambda page: self.api)

    def tearDown(self):
        self.tmp.cleanup()

    def run_tick(self):
        self.w.last_run = None
        return self.w.tick(page=None, now=self.now[0])

    def test_scans_only_items_with_offers_and_alerts_once(self):
        self.run_tick()
        self.assertEqual([c for c in self.api.calls if c[0] == "detail"], [("detail", "12448")])
        self.assertEqual(len(self.notes), 1)
        self.assertIn("rope belt", self.notes[0][1])
        self.run_tick()
        self.assertEqual(len(self.notes), 1)              # mesma oferta: nao repete
        self.assertEqual(self.w.board["rope belt"].quality, "excelente")

    def test_no_buy_without_master_switch(self):
        self.cfg["rules"] = {"rope belt": {"buy": True, "max_price": 15000, "quantity": 5}}
        self.run_tick()
        self.assertNotIn("buy", [c[0] for c in self.api.calls])

    def test_buys_cheapest_up_to_quantity_and_claims(self):
        self.cfg["auto_buy"] = True
        self.cfg["rules"] = {"rope belt": {"buy": True, "max_price": 15000, "quantity": 5}}
        self.run_tick()
        buys = [c for c in self.api.calls if c[0] == "buy"]
        self.assertEqual(buys, [("buy", "a", 3), ("buy", "b", 2)])
        self.assertIn(("claim", "d-a"), self.api.calls)
        self.assertEqual(self.store.bought("12448"), 5)
        self.assertEqual(self.store.spent_today(), 3 * 12000 + 2 * 14000)
        self.run_tick()                                    # quantidade atingida: nao compra mais
        self.assertEqual(len([c for c in self.api.calls if c[0] == "buy"]), 2)

    def test_default_max_price_is_20pct_below_fair(self):
        self.cfg["auto_buy"] = True
        self.cfg["rules"] = {"rope belt": {"buy": True, "quantity": 10}}       # sem max_price -> 16.000
        self.run_tick()
        self.assertEqual([c for c in self.api.calls if c[0] == "buy"], [("buy", "a", 3), ("buy", "b", 5)])

    def test_budget_and_reserve(self):
        self.cfg.update(auto_buy=True, daily_budget=30000, reserve_gold=0)
        self.cfg["rules"] = {"rope belt": {"buy": True, "max_price": 15000, "quantity": 10}}
        self.run_tick()
        self.assertEqual([c for c in self.api.calls if c[0] == "buy"], [("buy", "a", 2)])
        self.api.calls.clear()
        self.api.gold = 1_000_000
        self.cfg.update(daily_budget=10**9, reserve_gold=995_000)               # so' 5k livres
        self.run_tick()
        self.assertNotIn("buy", [c[0] for c in self.api.calls])

    def test_buy_error_stops_and_records_nothing(self):
        self.cfg["auto_buy"] = True
        self.cfg["rules"] = {"rope belt": {"buy": True, "max_price": 15000, "quantity": 5}}
        self.api.fail_buy = True
        self.run_tick()
        self.assertEqual(len([c for c in self.api.calls if c[0] == "buy"]), 1)
        self.assertEqual(self.store.bought("12448"), 0)
        self.assertTrue(any("falhou" in line for line in self.logs))

    def test_interval(self):
        self.assertTrue(self.w.tick(None, 0))
        self.assertFalse(self.w.tick(None, 60))
        self.assertTrue(self.w.tick(None, 301))


if __name__ == "__main__":
    unittest.main()


class StoreReportTest(unittest.TestCase):
    def test_period_query_reason_and_old_db_migration(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.db")
            db = sqlite3.connect(path)            # banco da v1.4-v1.8 (sem a coluna reason)
            db.execute("CREATE TABLE purchase (ts REAL, item_id TEXT, name TEXT, quantity INTEGER, price REAL, total REAL, "
                       "offer_id TEXT, delivery_id TEXT, auto INTEGER)")
            db.execute("INSERT INTO purchase VALUES (100, '1', 'velho', 2, 10, 20, 'o', 'd', 1)")
            db.commit()
            db.close()
            now = [200.0]
            store = Store(path, clock=lambda: now[0])
            store.add_purchase("2", "rope belt", 3, 1000, "o2", "d2", auto=True, reason="oportunidade Void")
            rows = store.purchases_between(150, None)
            self.assertEqual(rows, [(200.0, "rope belt", 3, 1000.0, 3000.0, "oportunidade Void")])
            self.assertEqual(len(store.purchases_between()), 2)
            self.assertEqual(store.purchases_between(0, 150)[0][5], "")          # compra antiga: sem motivo
