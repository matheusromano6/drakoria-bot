import unittest

from drakoria_bot import goals as G

HUNTS = [{"name": "A", "level": 5, "creatures": ["Rat", "Troll"]},
         {"name": "B", "level": 15, "creatures": ["Rat", "Rotworm"]},
         {"name": "C", "level": 60, "creatures": ["Dragon"]}]
TASKS = [{"name": "t1", "creature": "Rotworm"}, {"name": "t2", "creature": "Dragon"}, {"name": "t3", "creature": "Wolf"}]


class GoalsTest(unittest.TestCase):
    def test_reachable_prefers_easiest(self):
        self.assertEqual(G.reachable_hunt("Rat", HUNTS, 8, 10), "A")
        self.assertEqual(G.reachable_hunt("Rotworm", HUNTS, 8, 10), "B")
        self.assertIsNone(G.reachable_hunt("Rotworm", HUNTS, 4, 10))
        self.assertIsNone(G.reachable_hunt("Dragon", HUNTS, 8, 10))

    def test_doable_tasks(self):
        self.assertEqual([t["name"] for t in G.doable_tasks(TASKS, HUNTS)], ["t1", "t2"])

    def test_tracker_title(self):
        self.assertEqual(G.parse_tracker_title("Troll: 4 de 250 kills · faltam 246. Abrir a ficha."), ("Troll", 4, 250))
        self.assertEqual(G.parse_tracker_title("Hydra: 1.200 de 2.500 kills"), ("Hydra", 1200, 2500))
        self.assertIsNone(G.parse_tracker_title("nada"))

    def test_goal_hunt_priority(self):
        active = [{"name": "t1", "ready": False}]
        self.assertEqual(G.goal_hunt(active, ["Troll"], {}, TASKS, HUNTS, 8, 10)[0], "B")
        self.assertEqual(G.goal_hunt([{"name": "t1", "ready": True}], ["Troll"], {}, TASKS, HUNTS, 8, 10)[0], "A")
        self.assertEqual(G.goal_hunt([], ["Troll"], {"troll": [250, 250]}, TASKS, HUNTS, 8, 10), (None, "", None))
        self.assertEqual(G.goal_hunt(active, [], {}, TASKS, HUNTS, 8, 10)[2], "t1")

    def test_bestiary_title(self):
        self.assertEqual(G.parse_bestiary_title("Rotworm · 421 / 500 kills"), ("Rotworm", 421, 500))
        self.assertEqual(G.parse_bestiary_title("Ghoul · 1.050 / 500 kills"), ("Ghoul", 1050, 500))

    def test_next_to_accept(self):
        rows = {"t1": "available", "t2": "available", "t3": "available"}
        self.assertEqual(G.next_tasks_to_accept(["t2", "t3", "t1"], rows, 0, TASKS, HUNTS, 8, 10), ["t1"])
        self.assertEqual(G.next_tasks_to_accept(["t1"], {"t1": "done"}, 0, TASKS, HUNTS, 8, 10), [])
        self.assertEqual(G.next_tasks_to_accept(["t1"], rows, 2, TASKS, HUNTS, 8, 10), [])


if __name__ == "__main__":
    unittest.main()
