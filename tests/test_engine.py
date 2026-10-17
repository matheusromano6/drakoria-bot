import copy
import unittest

from drakoria_bot import config
from drakoria_bot.account import Member, State
from drakoria_bot.engine import Engine

HUNTS = [{"name": "Troll Cave", "level": 5, "creatures": ["Troll", "Young Troll", "Rat", "Spider"]},
         {"name": "Rotworms", "level": 15, "creatures": ["Carrion Worm", "Rotworm"]}]
TROLLS = ["Troll", "Young Troll", "Rat", "Spider"]


class FakeAccount:
    """Simula a pagina do jogo: o estado so muda quando o bot 'clica'."""

    def __init__(self, phase="city", premium=True, loot=0, tracker=None):
        self.st = State(phase=phase, premium=premium, loot_items=loot, tracker=tracker or [],
                        members=[Member("Alfa", "TANK", 8), Member("Beta", "DPS", 8)])
        self.calls = []
        self.best = "Troll Cave"
        self.fail = set()
        self.prey = []          # espacos da Prey
        self.prey_lists = []    # proximas listas ao trocar
        self.closed = 0

    def read(self):
        return copy.deepcopy(self.st)

    def _call(self, name, *args):
        self.calls.append((name,) + args)
        if name in self.fail:
            raise RuntimeError("falhou")

    def reload(self):
        self._call("reload")

    def dismiss_popups(self):
        self._call("dismiss")
        self.st.modals = []
        return "relatório offline coletado"

    def loot_settings(self, auto_sell):
        self._call("loot_settings", auto_sell)
        return []

    def sell_all(self):
        self._call("sell_all")
        self.st.loot_items = 0
        return True

    def best_hunt(self):
        self._call("best_hunt")
        return self.best

    def start_hunt(self, hunt, difficulty):
        self._call("start_hunt", hunt, difficulty)
        self.st.phase = "hunting"
        self.st.tracker = list(next(h["creatures"] for h in HUNTS if h["name"] == hunt))

    def stop_training(self):
        self._call("stop_training")
        self.st.phase = "house_idle"

    def leave_house(self):
        self._call("leave_house")
        self.st.phase = "city"

    def read_prey(self):
        self._call("read_prey")
        return copy.deepcopy(self.prey)

    def prey_choose(self, index, creature):
        self._call("prey_choose", index, creature)
        slot = self.prey[index]
        slot.update(state="active", creature=creature, options=[])

    def prey_reroll(self, index):
        self._call("prey_reroll", index)
        slot = self.prey[index]
        slot["options"] = self.prey_lists.pop(0)
        slot["reroll"] = {"free": False, "gold": 300, "cards": False}

    def close_windows(self):
        self.closed += 1

    def login(self, user, password):
        self._call("login", user)
        self.st.phase = "city"


class FakeCreds:
    def __init__(self, users):
        self.users = users

    def usernames(self):
        return list(self.users)

    def get(self, user):
        return "segredo"


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(acc, creds=None, **cfg_over):
    cfg_over.setdefault("prey", {"enabled": False})
    cfg = config._merge(config.DEFAULTS, cfg_over)
    clock = Clock()
    logs = []
    eng = Engine([acc], cfg, logs.append, credentials=creds, clock=clock)
    eng.hunts = HUNTS
    return eng, clock, logs


def names(acc):
    return [c[0] for c in acc.calls]


class EngineTest(unittest.TestCase):
    def test_first_tick_checks_loot_then_hunts_best(self):
        acc = FakeAccount()
        eng, clock, _ = make(acc)
        eng.tick(acc)
        self.assertEqual(acc.calls, [("loot_settings", True)])     # premium -> Auto Sell ligado + protecao
        eng.tick(acc)
        self.assertEqual(names(acc)[1:], ["best_hunt", "start_hunt"])
        self.assertEqual(acc.calls[-1], ("start_hunt", "Troll Cave", "Normal"))
        eng.tick(acc)                                                # caçando a certa: nada
        self.assertEqual(len(acc.calls), 3)

    def test_free_account_sells_at_threshold(self):
        acc = FakeAccount(phase="hunting", premium=False, loot=5, tracker=TROLLS)
        eng, clock, _ = make(acc, loot={"sell_at_items": 10})
        eng.tick(acc)
        self.assertEqual(acc.calls[0], ("loot_settings", False))
        eng.tick(acc)
        self.assertNotIn("sell_all", names(acc))
        acc.st.loot_items = 10
        eng.tick(acc)
        self.assertIn("sell_all", names(acc))
        self.assertEqual(acc.st.loot_items, 0)

    def test_premium_never_sells_by_bot(self):
        acc = FakeAccount(phase="hunting", loot=500, tracker=TROLLS)
        eng, clock, _ = make(acc)
        for _ in range(3):
            eng.tick(acc)
        self.assertNotIn("sell_all", names(acc))

    def test_auto_sell_choice_overrides_premium(self):
        acc = FakeAccount(phase="hunting", premium=True, tracker=TROLLS)
        eng, clock, _ = make(acc, loot={"auto_sell": "off"})
        eng.tick(acc)
        self.assertEqual(acc.calls[0], ("loot_settings", False))

    def test_loot_settings_rechecked_periodically(self):
        acc = FakeAccount(phase="hunting", tracker=TROLLS)
        eng, clock, _ = make(acc, hunt="Troll Cave")
        eng.tick(acc)
        eng.tick(acc)
        self.assertEqual(names(acc).count("loot_settings"), 1)
        clock.t += 31 * 60
        eng.tick(acc)
        self.assertEqual(names(acc).count("loot_settings"), 2)

    def test_fixed_hunt_and_switch_after_two_reads(self):
        acc = FakeAccount(phase="hunting", tracker=TROLLS)
        eng, clock, _ = make(acc, hunt="Rotworms", difficulty="Difícil")
        eng.tick(acc)       # loot
        eng.tick(acc)       # 1a leitura diferente
        self.assertNotIn("start_hunt", names(acc))
        eng.tick(acc)
        self.assertEqual(acc.calls[-1], ("start_hunt", "Rotworms", "Difícil"))
        self.assertNotIn("best_hunt", names(acc))

    def test_house_training_is_stopped_in_hunt_mode(self):
        acc = FakeAccount(phase="house")
        eng, clock, _ = make(acc)
        eng.tick(acc)
        eng.tick(acc)
        self.assertIn("stop_training", names(acc))
        eng.tick(acc)
        self.assertEqual(names(acc)[-1], "leave_house")
        eng.tick(acc)
        self.assertEqual(names(acc)[-1], "start_hunt")

    def test_watch_mode_never_touches_hunt(self):
        acc = FakeAccount(phase="house")
        eng, clock, _ = make(acc, mode="watch")
        for _ in range(3):
            eng.tick(acc)
        self.assertEqual(names(acc), ["loot_settings"])

    def test_relogin_with_saved_login(self):
        acc = FakeAccount(phase="login")
        eng, clock, logs = make(acc, FakeCreds(["conta1"]))
        eng.tick(acc)
        self.assertEqual(acc.calls, [("login", "conta1")])
        self.assertFalse(any("segredo" in line for line in logs))

    def test_relogin_without_login_only_warns(self):
        acc = FakeAccount(phase="login")
        eng, clock, logs = make(acc, FakeCreds([]))
        eng.tick(acc)
        eng.tick(acc)
        self.assertEqual(acc.calls, [])
        self.assertEqual(sum("nenhum login" in line for line in logs), 1)

    def test_relogin_disabled(self):
        acc = FakeAccount(phase="login")
        eng, clock, _ = make(acc, FakeCreds(["conta1"]), relogin=False)
        eng.tick(acc)
        self.assertEqual(acc.calls, [])

    def test_error_reloads_with_interval(self):
        acc = FakeAccount(phase="error")
        eng, clock, _ = make(acc)
        eng.tick(acc)
        eng.tick(acc)
        self.assertEqual(names(acc), ["reload"])
        clock.t += 61
        eng.tick(acc)
        self.assertEqual(names(acc), ["reload", "reload"])

    def test_unknown_reloads_only_after_timeout(self):
        acc = FakeAccount(phase="unknown")
        eng, clock, _ = make(acc)
        eng.tick(acc)
        clock.t += 60
        eng.tick(acc)
        self.assertEqual(acc.calls, [])
        clock.t += 70
        eng.tick(acc)
        self.assertEqual(names(acc), ["reload"])

    def test_popup_dismissed_first(self):
        acc = FakeAccount()
        acc.st.modals = ["Sua Party continuou treinando"]
        eng, clock, _ = make(acc)
        eng.tick(acc)
        self.assertEqual(names(acc), ["dismiss"])

    def test_failed_action_waits_cooldown(self):
        acc = FakeAccount()
        acc.fail.add("start_hunt")
        eng, clock, logs = make(acc, hunt="Troll Cave")
        eng.tick(acc)       # loot
        eng.tick(acc)
        eng.tick(acc)
        self.assertEqual(names(acc).count("start_hunt"), 1)
        clock.t += 301
        eng.tick(acc)
        self.assertEqual(names(acc).count("start_hunt"), 2)


def prey_slot(options, free=True):
    return {"index": 0, "state": "selection", "creature": "", "bonus": "", "time": "", "options": options,
            "reroll_enabled": True, "reroll": {"free": free, "gold": None, "cards": False}}


class PreyEngineTest(unittest.TestCase):
    def setUp(self):
        self.acc = FakeAccount(phase="hunting", tracker=TROLLS)
        self.acc.st.kills = {"Troll": 40, "Rat": 3}
        self.acc.st.gold = "4,9k"

    def run_prey(self, **prey):
        conf = {"enabled": True, "mode": "budget", "gold_per_day": 1000}
        conf.update(prey)
        eng, clock, logs = make(self.acc, hunt="Troll Cave", prey=conf)
        eng.tick(self.acc)      # loot
        eng.tick(self.acc)      # prey
        return eng, clock, logs

    def test_picks_most_seen_creature_of_hunt(self):
        self.acc.prey = [prey_slot(["Bat", "Rat", "Troll"])]
        self.run_prey()
        self.assertIn(("prey_choose", 0, "Troll"), self.acc.calls)
        self.assertNotIn("prey_reroll", names(self.acc))
        self.assertGreaterEqual(self.acc.closed, 1)

    def test_free_then_paid_reroll_until_found(self):
        self.acc.prey = [prey_slot(["Bat"])]
        self.acc.prey_lists = [["Wolf"], ["Spider", "Orc"]]
        eng, clock, logs = self.run_prey()
        self.assertEqual(names(self.acc).count("prey_reroll"), 2)    # gratis + 1 paga (300)
        self.assertIn(("prey_choose", 0, "Spider"), self.acc.calls)
        self.assertEqual(eng._spent_today()[1], 300)

    def test_budget_exhausted_picks_any(self):
        self.acc.prey = [prey_slot(["Bat"], free=False)]
        self.acc.prey[0]["reroll"]["gold"] = 2000
        self.run_prey()
        self.assertNotIn("prey_reroll", names(self.acc))
        self.assertIn(("prey_choose", 0, "Bat"), self.acc.calls)

    def test_active_slots_left_alone_and_checked_periodically(self):
        self.acc.prey = [dict(prey_slot([]), state="active", creature="Troll")]
        eng, clock, logs = self.run_prey()
        eng.tick(self.acc)
        self.assertEqual(names(self.acc).count("read_prey"), 1)
        clock.t += 11 * 60
        eng.tick(self.acc)
        self.assertEqual(names(self.acc).count("read_prey"), 2)
        self.assertNotIn("prey_choose", names(self.acc))

    def test_no_prey_outside_hunt(self):
        self.acc.st.phase = "city"
        self.acc.prey = [prey_slot(["Troll"])]
        self.run_prey()
        self.assertNotIn("read_prey", names(self.acc))


if __name__ == "__main__":
    unittest.main()
