"""Memoria pequena em disco (memory.json): ultima caça, login usado e a party vista (a interface usa com o bot parado)."""
import json
import os


class Memory:
    def __init__(self, path=None):
        self.path = path
        self.data = {}
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as file:
                    self.data = json.load(file)
            except (OSError, ValueError):
                self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        if self.data.get(key) != value:
            self.data[key] = value
            self._save()

    def _save(self):
        if not self.path:
            return
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=2)
