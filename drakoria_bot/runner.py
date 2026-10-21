"""Roda o motor numa thread (o Playwright precisa ser criado e usado na MESMA thread).
A interface so' le o 'snapshot' e liga/desliga."""
import os
import threading

from .engine import Engine
from .idledeck import Pool
from .credentials import Credentials
from .market.store import Store as MarketStore
from .market.watcher import MarketWatcher
from .memory import Memory
from .paths import app_dir

ROOT = app_dir()


class Runner:
    def __init__(self, cfg, log):
        self.cfg = cfg                 # o MESMO dict da interface: mudancas valem na hora
        self.log = log
        self.thread = None
        self.stop_event = threading.Event()
        self.engine = None
        self.connected = False
        self.notify = None             # a interface liga (aviso na bandeja)
        self.market = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    @property
    def snapshot(self):
        return self.engine.snapshot if self.engine else None

    def start(self):
        if self.running:
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _task_items(self):
        """Itens pedidos pelas tasks escolhidas na aba Objetivos (pra mostrar se da pra comprar no Market)."""
        from .goals import load_tasks
        chosen = set((self.cfg.get("goals") or {}).get("tasks") or [])
        return [t["item"] for t in load_tasks() if t["name"] in chosen]

    def _run(self):
        pool = Pool(self.cfg["cdp_url"], self.log)
        try:
            pool.open(launch=True, stop=self.stop_event)
            self.connected = True
            self.market = MarketWatcher(self.cfg["market"], MarketStore(os.path.join(ROOT, "market.db")), self.log,
                                        notify=lambda title, text: self.notify and self.notify(title, text))
            self.market.extra_items = self._task_items
            self.engine = Engine(pool.refresh(), self.cfg, self.log, refresh=pool.refresh, market=self.market,
                                 credentials=Credentials(os.path.join(ROOT, "credentials.json")),
                                 memory=Memory(os.path.join(ROOT, "memory.json")))
            self.log("bot iniciado")
            self.engine.run(self.stop_event)
        except Exception as error:
            self.log(f"parado por erro: {error}")
        finally:
            self.connected = False
            pool.close()
            self.log("bot parado")
