import unittest

from drakoria_bot import imbuing as I
from tests.test_engine import FakeAccount, HUNTS, make

DATA = {"rules": {}, "imbuements": [
    {"id": "void", "name": "Void", "kinds": ["bow", "helmet"], "materials": [
        {"name": "rope belt", "display": "Rope Belt", "qty": 25},
        {"name": "silencer claws", "display": "Silencer Claws", "qty": 25},
        {"name": "some grimeleech wings", "display": "Some Grimeleech Wings", "qty": 5}]},
    {"id": "vampirism", "name": "Vampirism", "kinds": ["armor"], "materials": [
        {"name": "vampire teeth", "display": "Vampire Teeth", "qty": 25}]}]}
TARGET = {"member": "Pally", "slot": "weapon", "imbuement": "void", "tier": 2, "source": "auto"}


def game(entries=(), counts=None, gold=10_000_000, cap=3):
    return {"gold": gold, "counts": counts or {}, "members": [
        {"id": "p1", "name": "Pally", "level": 100, "slots": [
            {"slot": "weapon", "item": "Rift Bow", "itemId": 25522, "kind": "bow", "cap": cap, "entries": list(entries)}]}]}


FULL = {"rope belt": (30, 0), "silencer claws": (10, 20), "some grimeleech wings": (5, 0)}


class RulesTest(unittest.TestCase):
    def test_states(self):
        self.assertEqual(I.status(TARGET, game(), DATA, 6)["state"], "aplicar")
        on = {"id": "void", "tier": 2, "h": 20.0, "auto": False}
        self.assertEqual(I.status(TARGET, game([on]), DATA, 6)["state"], "ok")
        self.assertEqual(I.status(TARGET, game([dict(on, h=2.0)]), DATA, 6)["state"], "preparar")
        other = [{"id": "x", "tier": 0, "h": 5, "auto": False}]
        self.assertEqual(I.status(TARGET, game(other, cap=1), DATA, 6)["state"], "sem slot livre")
        self.assertEqual(I.status(dict(TARGET, member="Zed"), game(), DATA, 6)["state"], "personagem fora da party")
        self.assertIn("não serve", I.status(dict(TARGET, imbuement="vampirism"), game(), DATA, 6)["state"])

    def test_ready_counts_bank_and_keeps_reserve(self):
        st = I.status(TARGET, game(), DATA, 6)
        self.assertTrue(I.ready_to_apply(st, DATA, FULL, 1_000_000, 500_000))
        self.assertFalse(I.ready_to_apply(st, DATA, FULL, 700_000, 500_000))       # taxa 250k passaria da reserva
        self.assertFalse(I.ready_to_apply(st, DATA, dict(FULL, **{"rope belt": (10, 0)}), 10 ** 7, 0))

    def test_shortages_and_tier(self):
        st = I.status(TARGET, game(), DATA, 6)
        self.assertEqual(I.shortages([st], DATA, {"rope belt": (5, 0)}),
                         {"rope belt": (20, "auto"), "silencer claws": (25, "auto"), "some grimeleech wings": (5, "auto")})
        basic = I.status(dict(TARGET, tier=0), game(), DATA, 6)
        self.assertEqual(list(I.shortages([basic], DATA, {})), ["rope belt"])

    def test_best_hunt_prefers_drop_rate_and_level(self):
        drops = {"rope belt": {"troll": 0.1, "rotworm": 0.5}}
        self.assertEqual(I.best_hunt("rope belt", drops, HUNTS, 100)[0], "Rotworms")
        self.assertEqual(I.best_hunt("rope belt", drops, HUNTS, 10)[0], "Troll Cave")   # Rotworms pede 15
        self.assertIsNone(I.best_hunt("vampire teeth", drops, HUNTS, 100))


class ImbFake(FakeAccount):
    def __init__(self, g, **kw):
        super().__init__(**kw)
        self.g = g

    def read_imbuements(self, names):
        self._call("read_imbuements")
        return self.g

    def protect_materials(self, names):
        self._call("protect", tuple(names))
        return True

    def apply_imbuement(self, *args):
        self._call("apply", *args)
        self.g["members"][0]["slots"][0]["entries"].append({"id": args[3], "tier": args[4], "h": 30.0, "auto": False})

    def read_drops(self, names):
        self._call("drops")
        return {n: {"rotworm": 0.2} for n in names}


class EngineImbuingTest(unittest.TestCase):
    def cfg(self, **kw):
        return {"imbuing": dict({"enabled": True, "targets": [dict(TARGET, source="hunt")]}, **kw)}

    def test_applies_moving_from_depot(self):
        acc = ImbFake(game(counts=dict(FULL)))
        eng, _, logs = make(acc, hunt="Troll Cave", **self.cfg())
        eng.imb_data = DATA
        eng.last_ok["loot_settings"] = 0
        eng.tick(acc)
        apply = [c for c in acc.calls if c[0] == "apply"][0]
        self.assertEqual(apply[1:], ("p1", "weapon", 25522, "void", 2, [("silencer claws", 15)]))
        self.assertIn(("protect", ("rope belt", "silencer claws", "some grimeleech wings")), acc.calls)
        self.assertTrue(any("imbuement aplicado" in l for l in logs))
        self.assertIsNone(eng.imb_hunt)                         # aplicado e com 30h: segue a caça padrão

    def test_missing_materials_send_to_best_hunt_first(self):
        acc = ImbFake(game())
        eng, _, _ = make(acc, hunt="Troll Cave", **self.cfg(difficulty="Difícil"))
        eng.imb_data = DATA
        eng.last_ok["loot_settings"] = 0
        eng.tick(acc)
        self.assertEqual(acc.calls[-1], ("start_hunt", "Rotworms", "Difícil"))
        self.assertNotIn("apply", [c[0] for c in acc.calls])

    def test_loop_keeps_hunting_when_done(self):
        on = {"id": "void", "tier": 2, "h": 25.0, "auto": False}
        acc = ImbFake(game([on], counts=dict(FULL)))
        eng, _, _ = make(acc, hunt="Troll Cave", **self.cfg(end="loop"))
        eng.imb_data = DATA
        eng.last_ok["loot_settings"] = 0
        eng.tick(acc)
        self.assertEqual(acc.calls[-1][:2], ("start_hunt", "Rotworms"))


if __name__ == "__main__":
    unittest.main()
