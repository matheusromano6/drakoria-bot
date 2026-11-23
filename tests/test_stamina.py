import copy
import unittest
from types import SimpleNamespace

from drakoria_bot import config
from drakoria_bot.engine import Engine


class Mem:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


def engine(cfg, memory):
    return Engine([], cfg, log=lambda m: None, memory=memory)


class StaminaGoalTest(unittest.TestCase):
    def setUp(self):
        self.cfg = copy.deepcopy(config.DEFAULTS)
        self.cfg["exercise"]["enabled"] = True
        self.cfg["exercise"]["target_stamina_h"] = 40

    def test_rest_goes_to_target_not_24h(self):
        mem = Mem()
        e = engine(self.cfg, mem)
        self.assertTrue(e.stamina_rest(SimpleNamespace(stamina=13.5)))
        self.assertEqual(mem.get("stamina_goal"), 40)
        self.assertTrue(e.stamina_rest(SimpleNamespace(stamina=30)))   # ainda nao chegou em 40

    def test_restart_while_training_keeps_the_goal(self):
        mem = Mem({"stamina_resting": True, "stamina_goal": 40})
        e = engine(self.cfg, mem)                                       # bot caiu e voltou
        self.assertTrue(e.resting)
        self.assertTrue(e.stamina_rest(SimpleNamespace(stamina=15)))    # 15h: NAO volta pra caca
        self.assertFalse(e.stamina_rest(SimpleNamespace(stamina=40)))   # so volta no alvo

    def test_without_exercise_uses_resume_hours(self):
        self.cfg["exercise"]["enabled"] = False
        mem = Mem()
        e = engine(self.cfg, mem)
        e.stamina_rest(SimpleNamespace(stamina=13))
        self.assertEqual(mem.get("stamina_goal"), 24)


if __name__ == "__main__":
    unittest.main()
