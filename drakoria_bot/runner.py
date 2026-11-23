"""Roda o motor numa thread (o Playwright precisa ser criado e usado na MESMA thread).
A interface so' le o 'snapshot' e liga/desliga."""
import os
import threading

from .engine import Engine
from . import browsers
from .idledeck import Pool, port_open
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

    def _smoke_test(self, accounts, memory):
        """Depois de conectar: le uma conta de verdade e confere a versao (teste de fumaca da atualizacao)."""
        from . import VERSION
        try:
            if accounts:
                accounts[0].read()
            state = f"{len(accounts)} conta(s) lida(s)"
        except Exception as error:
            self.log(f"atenção: não consegui ler a conta depois de conectar ({error})")
            return
        last = memory.get("last_version")
        if last and last != VERSION:
            self.log(f"atualizado para v{VERSION} (era v{last}): conexão ok, {state}")
        else:
            self.log(f"conexão ok (v{VERSION}): {state}")
        memory.set("last_version", VERSION)

    def _run(self):
        cdp = self.cfg["cdp_url"]
        # o navegador configurado precisa ter a aba do jogo. Se a porta esta fechada OU aberta sem nenhuma aba do
        # Drakoria (ex.: outro navegador/jogo nessa porta), usa um navegador em depuração que TENHA o jogo aberto
        # (ex.: Brave com outros jogos) em vez de ficar esperando abrir o IdleDeck.
        port = int(cdp.rsplit(":", 1)[-1])
        found = [b for b in browsers.scan() if b["game_tabs"]]
        if found and not any(b["port"] == port for b in found):
            cdp = found[0]["url"]
            self.log(f"navegador em depuração com o jogo encontrado ({found[0]['name'] or 'navegador'}, "
                     f"porta {found[0]['port']}): usando ele")
        pool = Pool(cdp, self.log)
        try:
            chosen = self.cfg.get("browser") or {}
            if chosen.get("path") and not port_open(cdp):
                port = int(cdp.rsplit(":", 1)[-1])
                self.log(f"{chosen['name']} fechado: abrindo de novo (janela do bot)...")
                browsers.launch(chosen["name"], chosen["path"], port=port)
            pool.open(launch=self.cfg.get("launch_idledeck", True), stop=self.stop_event)
            self.connected = True
            self.market = MarketWatcher(self.cfg["market"], MarketStore(os.path.join(ROOT, "market.db")), self.log,
                                        notify=lambda title, text: self.notify and self.notify(title, text))
            self.market.extra_items = self._task_items
            memory = Memory(os.path.join(ROOT, "memory.json"))
            accounts = pool.refresh()
            if accounts:
                from . import housekeeping
                housekeeping.check_build(accounts[0].page, memory, self.log)
            self.engine = Engine(accounts, self.cfg, self.log, refresh=pool.refresh, market=self.market,
                                 credentials=Credentials(os.path.join(ROOT, "credentials.json")),
                                 memory=memory)
            self.engine.notify = lambda title, text: self.notify and self.notify(title, text)
            self._smoke_test(accounts, memory)
            self.log("bot iniciado")
            self.engine.run(self.stop_event)
        except Exception as error:
            self.log(f"parado por erro: {error}")
        finally:
            self.connected = False
            pool.close()
            self.log("bot parado")
