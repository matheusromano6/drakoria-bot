import copy
import unittest

from drakoria_bot import config


class ProfileTest(unittest.TestCase):
    def test_save_and_load_restores_the_rules(self):
        cfg = copy.deepcopy(config.DEFAULTS)
        cfg["hunt"] = "Rotworms"
        config.save_profile(cfg, "farm")
        cfg["hunt"] = "Orc Camp"
        self.assertTrue(config.load_profile(cfg, "farm"))
        self.assertEqual(cfg["hunt"], "Rotworms")

    def test_missing_profile_changes_nothing(self):
        cfg = copy.deepcopy(config.DEFAULTS)
        cfg["hunt"] = "Orc Camp"
        self.assertFalse(config.load_profile(cfg, "inexistente"))
        self.assertEqual(cfg["hunt"], "Orc Camp")


if __name__ == "__main__":
    unittest.main()
