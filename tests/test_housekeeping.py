import json
import os
import shutil
import tempfile
import unittest

from drakoria_bot import exercise as X
from drakoria_bot import housekeeping as H


class FixtureTest(unittest.TestCase):
    """Usa uma leitura REAL salva do jogo (Opera, 23/11/2026): se o formato mudar, o teste avisa."""

    def test_saved_read_gives_the_expected_plan(self):
        here = os.path.dirname(__file__)
        with open(os.path.join(here, "fixtures", "exercise_read.json"), encoding="utf-8") as file:
            info = json.load(file)
        self.assertEqual(info["weapon"], "sword")
        p = X.plan(info["stamina_h"], 40, info["owned"], 10)
        self.assertEqual(p["buy"], 0)                  # 6 durables na mochila ja cobrem ate 40h


class HousekeepingTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_old_logs_are_removed_recent_kept(self):
        old = os.path.join(self.dir, "drakoria_2026-01-01.log")
        new = os.path.join(self.dir, "drakoria_2026-11-23.log")
        other = os.path.join(self.dir, "notas.txt")
        for path in (old, new, other):
            open(path, "w").close()
        os.utime(old, (0, 0))
        removed = H.prune_logs(self.dir, days=14)
        self.assertEqual(removed, 1)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(new))
        self.assertTrue(os.path.exists(other))          # so' apaga logs do bot

    def test_spend_history_totals_by_kind(self):
        H.spend(self.dir, "arma de exercício", 4687500, "knight")
        H.spend(self.dir, "arma de exercício", 1000, "x")
        H.spend(self.dir, "atlas", 500, "y")
        totals = H.spent_today(self.dir)
        self.assertEqual(totals["arma de exercício"], 4688500)
        self.assertEqual(totals["atlas"], 500)


if __name__ == "__main__":
    unittest.main()
