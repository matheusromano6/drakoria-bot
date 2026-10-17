import unittest

from drakoria_bot import hunts as H
from drakoria_bot.account import parse_member, parse_state


def raw(**kw):
    base = {"scene": "panel city-temple-scene compact city-temple-idle-stage", "hasGame": True, "loginForm": False,
            "landing": False, "error": False, "disconnected": False,
            "members": [["Alfa", "TANK", "Lv 8 · 17%", "185/185", "75/75"]],
            "gold": "500", "loot": 3, "premium": "Premium Ouro", "dest": "Próximo destino: Troll Cave · Mundo · Level 5+"}
    base.update(kw)
    return base


class ParseTest(unittest.TestCase):
    def test_member(self):
        m = parse_member(["Beta", "DPS", "Lv 1.205 · 4%", "1.850/2.000", "35/35"])
        self.assertEqual((m.name, m.role, m.level, m.xp_pct, m.hp, m.hp_max), ("Beta", "DPS", 1205, 4, 1850, 2000))

    def test_phases(self):
        self.assertEqual(parse_state(raw()).phase, "city")
        self.assertEqual(parse_state(raw()).dest, "Troll Cave")
        self.assertEqual(parse_state(raw(scene="panel spatial-battle-stage compact phase-engage")).phase, "hunting")
        self.assertEqual(parse_state(raw(scene="panel city-temple-scene house-scene city-temple-idle-stage", training=True)).phase, "house")
        self.assertEqual(parse_state(raw(scene="panel city-temple-scene house-scene city-temple-idle-stage")).phase, "house_idle")
        self.assertEqual(parse_state(raw(hasGame=False, landing=True, scene="")).phase, "login")
        self.assertEqual(parse_state(raw(hasGame=False, error=True, scene="")).phase, "error")
        self.assertEqual(parse_state(raw(disconnected=True)).phase, "error")
        self.assertEqual(parse_state(raw(scene="")).phase, "unknown")

    def test_premium(self):
        self.assertTrue(parse_state(raw()).premium)
        self.assertFalse(parse_state(raw(premium="Free")).premium)


class HuntsTest(unittest.TestCase):
    def test_data(self):
        hunts, bosses = H.load_hunts(), H.load_bosses()
        self.assertGreaterEqual(len(hunts), 60)
        self.assertGreaterEqual(len(bosses), 80)
        self.assertTrue(all(h["name"] and h["creatures"] and h["level"] > 0 for h in hunts))

    def test_identify(self):
        hunts = [{"name": "A", "creatures": ["Troll", "Rat"]}, {"name": "B", "creatures": ["Rat", "Bat"]}]
        self.assertEqual(H.identify(["Troll", "Rat"], hunts), "A")
        self.assertEqual(H.identify(["Bat"], hunts), "B")
        self.assertIsNone(H.identify(["Rat"], hunts))       # ambiguo
        self.assertIsNone(H.identify([], hunts))


if __name__ == "__main__":
    unittest.main()
