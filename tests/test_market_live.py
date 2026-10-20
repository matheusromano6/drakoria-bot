import os
import tempfile
import unittest

from drakoria_bot import config
from drakoria_bot.market.api import item_id_of
from drakoria_bot.market.store import Store
from drakoria_bot.market.watcher import MarketWatcher
from tests.test_market import FakeApi, day, detail, offer

VAMP = {"id": "vampirism", "name": "Vampirism", "category": "support", "kinds": ["armor"],
        "materials": [{"name": "vampire teeth", "display": "Vampire Teeth", "qty": 25},
                      {"name": "bloody pincers", "display": "Bloody Pincers", "qty": 15},
                      {"name": "piece of dead brain", "display": "Piece of Dead Brain", "qty": 5}]}


class LiveApi(FakeApi):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.queue = []
        self.streams = 0

    def stream(self):
        self.streams += 1
        return "novo" if self.streams == 1 else "aberto"

    def events(self):
        out, self.queue = self.queue, []
        return out

    def assets(self):
        return {}


class LiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "m.db"), clock=lambda: 1_000_000.0)
        self.cfg = config._merge(config.DEFAULTS, {})["market"]
        listing = [{"id": "10602", "displayName": "vampire teeth", "sellQuantity": "0"},
                   {"id": "999", "displayName": "outro", "sellQuantity": "3"}]
        self.api = LiveApi(listing, {
            "10602": detail([], [day(19, 5000, 30)], vwap=5000, item_id="10602", name="vampire teeth"),
            "999": detail([offer("o", 1, 3)], [day(19, 50, 3)], vwap=50, item_id="999", name="outro")})
        self.logs = []
        self.w = MarketWatcher(self.cfg, self.store, self.logs.append, api_factory=lambda page: self.api)
        self.w.imb = {"imbuements": [VAMP], "rules": {"goldFee": 250000, "goldTokenCost": 10, "silverTokenCost": 10}}
        self.cfg["imbuements"] = {"vampirism": {"watch": True, "tier": 0, "uses": 1, "buy": True, "pay_pct": 90}}
        self.w.tick(None, 0)                 # varredura inicial (precisa da lista pra saber os ids)
        self.api.calls.clear()
        # a outra conta cria a oferta depois da varredura
        self.api.details["10602"]["sellOffers"] = [offer("v1", 1000, 1)]

    def tearDown(self):
        self.tmp.cleanup()

    def test_item_id_of(self):
        self.assertEqual(item_id_of({"marketKey": "item:2195:abc"}), "2195")
        self.assertIsNone(item_id_of({"marketKey": "drako-coin"}))

    def test_reacts_only_to_watched_items(self):
        self.api.queue = [{"type": "market_order_created", "marketKey": "item:999:x"}]
        self.assertEqual(self.w.react(None, 1), 0)
        self.assertNotIn(("detail", "999"), self.api.calls)
        self.api.queue = [{"type": "market_order_created", "marketKey": "item:10602:x"},
                          {"type": "market_order_created", "marketKey": "item:10602:y"}]
        self.assertEqual(self.w.react(None, 2), 1)
        self.assertEqual(self.api.calls.count(("detail", "10602")), 1)          # 1 consulta por item, mesmo com 2 eventos
        self.assertTrue(any("ao vivo: vampire teeth: menor 1.000" in line for line in self.logs))

    def test_buys_immediately_when_allowed(self):
        self.cfg["auto_buy"] = True
        self.api.queue = [{"type": "market_order_created", "marketKey": "item:10602:x"}]
        self.w.react(None, 1)
        self.assertIn(("buy", "v1", 1), self.api.calls)
        self.assertIn(("claim", "d-v1"), self.api.calls)

    def test_no_events_no_requests(self):
        self.assertEqual(self.w.react(None, 1), 0)
        self.assertEqual([c for c in self.api.calls if c[0] in ("detail", "items")], [])

    def test_disabled_live(self):
        self.cfg["live"] = False
        self.api.queue = [{"marketKey": "item:10602:x"}]
        self.assertEqual(self.w.react(None, 1), 0)


if __name__ == "__main__":
    unittest.main()
