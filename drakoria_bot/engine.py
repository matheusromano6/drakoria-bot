"""Motor: a cada 'poll_seconds' le a pagina (1 evaluate) e faz NO MAXIMO uma acao.
Prioridade: erro/queda -> login -> avisos -> loot (protecao de boss / venda) -> caça."""
import time

import datetime

from . import hunts as H
from . import prey as P

LOOT_SETTINGS = "loot_settings"


class Engine:
    def __init__(self, accounts, cfg, log=print, refresh=None, memory=None, credentials=None, clock=time.time):
        self.accounts = accounts
        self.cfg = cfg
        self.log = log
        self.refresh = refresh
        self.memory = memory
        self.credentials = credentials
        self.clock = clock
        self.hunts = H.load_hunts()
        self.cooldown = {}              # acao -> horario liberado
        self.last_ok = {}               # acao -> ultimo sucesso
        self.phase_since = (None, 0)    # (fase, desde)
        self.mismatch = 0
        self.best = None                # (level, caça) da 'Melhor escolha' do jogo
        self.prey_spent = {}            # ouro gasto trocando lista da Prey hoje (sem memory.json)
        self.snapshot = {"state": None, "hunt": None, "target": None, "phase": "-", "action": "", "prey": []}

    # ------------------------------------------------------------------ util
    def _ready(self, key):
        return self.clock() >= self.cooldown.get(key, 0)

    def _fail(self, key, error):
        self.cooldown[key] = self.clock() + self.cfg["cooldown_fail_seconds"]
        self.log(f"{key}: {error} (tento de novo em {self.cfg['cooldown_fail_seconds'] // 60} min)")

    def _do(self, key, fn, *args):
        if not self._ready(key):
            return None
        try:
            result = fn(*args)
            self.last_ok[key] = self.clock()
            self.snapshot["action"] = key
            return True if result is None else result
        except Exception as error:      # o bot nunca para por uma acao que falhou
            self._fail(key, error)
            return None

    def auto_sell(self, st):
        mode = self.cfg["loot"]["auto_sell"]
        return st.premium if mode == "auto" else mode == "on"

    def target_hunt(self, acc, st):
        fixed = (self.cfg.get("hunt") or "").strip()
        if fixed:
            return fixed
        if self.best is None or self.best[0] != st.level:
            name = self._do("melhor caça", acc.best_hunt)
            if isinstance(name, str) and name:
                if not self.best or self.best[1] != name:
                    self.log(f"caça automatica pro level {st.level}: {name}")
                self.best = (st.level, name)
        return self.best[1] if self.best else (self.memory.get("last_hunt") if self.memory else None)

    # ------------------------------------------------------------------ ciclo
    def run(self, stop):
        while not stop.is_set():
            if self.refresh:
                self.accounts = self.refresh()
            for acc in self.accounts:
                try:
                    self.tick(acc)
                except Exception as error:
                    self.log(f"erro lendo a pagina: {error}")
            stop.wait(self.cfg["poll_seconds"])

    def tick(self, acc):
        st = acc.read()
        now = self.clock()
        if st.phase != self.phase_since[0]:
            if self.phase_since[0] is not None:
                self.log(f"estado: {self.phase_since[0]} -> {st.phase}")
            self.phase_since = (st.phase, now)
        current = H.identify(st.tracker, self.hunts) if st.phase == "hunting" else None
        self.snapshot.update(state=st, phase=st.phase, hunt=current or (st.dest if st.phase == "city" else None))
        if self.memory and st.members:
            self.memory.set("party", [[m.name, m.role, m.level] for m in st.members])

        # 1) erro / desconectado / travado
        if st.phase == "error":
            if self._ready("recarregar"):
                self.log("pagina com erro/desconectada: recarregando")
                self.cooldown["recarregar"] = now + self.cfg["error_reload_seconds"]
                self._do("recarregar pagina", acc.reload)
            return
        if st.phase == "unknown":
            if now - self.phase_since[1] > self.cfg["unknown_reload_seconds"] and self._ready("recarregar"):
                self.log("estado desconhecido ha muito tempo: recarregando")
                self.cooldown["recarregar"] = now + self.cfg["error_reload_seconds"]
                self._do("recarregar pagina", acc.reload)
            return

        # 2) deslogado
        if st.phase == "login":
            self._relogin(acc)
            return

        # 3) relatorio offline / avisos
        if st.modals:
            done = acc.dismiss_popups()
            if done:
                self.log(done)
                return

        # 4) loot: protecao de boss sempre ligada; Auto Sell conforme Premium/escolha
        auto = self.auto_sell(st)
        every = self.cfg["loot"]["check_minutes"] * 60
        if now - self.last_ok.get(LOOT_SETTINGS, -every) >= every:
            changed = self._do(LOOT_SETTINGS, acc.loot_settings, auto)
            if isinstance(changed, list):
                self.log("Loot Pouch: " + (", ".join(changed) if changed else
                                           f"ok (proteção de boss ligada, Auto Sell {'ligado' if auto else 'desligado'})"))
            return
        if not auto and st.loot_items is not None and st.loot_items >= self.cfg["loot"]["sell_at_items"]:
            if self._do("vender", acc.sell_all):
                self.log(f"Loot Pouch com {st.loot_items} itens: vendido tudo (ouro {st.gold})")
            return

        # 5) prey (so' caçando: o tempo da prey so' corre na caça)
        prey = self.cfg.get("prey") or {}
        if prey.get("enabled") and st.phase == "hunting" and current:
            every = prey.get("check_minutes", 10) * 60
            if now - self.last_ok.get("prey", -every) >= every and self._ready("prey"):
                self._prey(acc, st, current)
                return

        # 6) caça
        if self.cfg["mode"] != "hunt":
            return
        target = self.target_hunt(acc, st)
        self.snapshot["target"] = target
        if not target:
            return
        if st.phase == "house":
            if self._do("parar treino", acc.stop_training):
                self.log("treino parado pra caçar")
        elif st.phase == "house_idle":
            if self._do("sair da house", acc.leave_house):
                self.log("saiu da house")
        elif st.phase == "city":
            self._start(acc, target)
        elif st.phase == "hunting":
            if current and current.casefold() != target.casefold():
                self.mismatch += 1
                if self.mismatch >= 2:          # 2 leituras seguidas: troca de caça
                    self.mismatch = 0
                    self.log(f"caçando {current}, mas a escolhida e' {target}: trocando")
                    self._start(acc, target)
            else:
                self.mismatch = 0
                if current and self.memory:
                    self.memory.set("last_hunt", current)

    def _spent_today(self):
        day = datetime.date.fromtimestamp(self.clock()).isoformat()
        data = (self.memory.get("prey_spent") if self.memory else self.prey_spent) or {}
        return day, (data.get("gold", 0) if data.get("day") == day else 0)

    def _add_spent(self, gold):
        day, spent = self._spent_today()
        self.prey_spent = {"day": day, "gold": spent + gold}
        if self.memory:
            self.memory.set("prey_spent", self.prey_spent)

    def _prey(self, acc, st, hunt):
        """Escolhe a prey dos espacos livres (regra em prey.py). Uma janela aberta, varias acoes, depois fecha."""
        cfg = self.cfg["prey"]
        creatures = next((h["creatures"] for h in self.hunts if h["name"].casefold() == hunt.casefold()), [])
        wanted = P.wanted_order(creatures, st.kills)
        gold = st.gold_value
        rerolls = 0
        try:
            slots = acc.read_prey()
            self.snapshot["prey"] = [(s["creature"], s["bonus"], s["time"]) for s in slots if s["state"] == "active"]
            for slot in slots:
                while slot["state"] == "selection":
                    _, spent = self._spent_today()
                    action = P.decide(slot, wanted, cfg, spent, gold)
                    if action is None:
                        break
                    kind, value = action
                    if kind == "reroll":
                        if rerolls >= cfg.get("max_rerolls_per_check", 10):
                            action = ("any", slot["options"][0])
                            kind, value = action
                        else:
                            acc.prey_reroll(slot["index"])
                            rerolls += 1
                            if value:
                                self._add_spent(value)
                                gold = None if gold is None else gold - value
                            self.log(f"Prey espaço {slot['index'] + 1}: trocou a lista ({'grátis' if not value else f'{value} de ouro'})")
                            slot = next(s for s in acc.read_prey() if s["index"] == slot["index"])
                            continue
                    acc.prey_choose(slot["index"], value)
                    why = "da caça" if kind == "choose" else "qualquer (nenhuma da caça; tenta de novo quando liberar)"
                    self.log(f"Prey espaço {slot['index'] + 1}: {value} ({why})")
                    break
            self.last_ok["prey"] = self.clock()
        except Exception as error:
            self._fail("prey", error)
        finally:
            try:
                acc.close_windows()
            except Exception:
                pass

    def _start(self, acc, target):
        diff = self.cfg["difficulty"]
        if self._do("iniciar caça", acc.start_hunt, target, diff):
            self.log(f"caçando {target} ({diff})")
            if self.memory:
                self.memory.set("last_hunt", target)

    def _relogin(self, acc):
        if not self.cfg.get("relogin") or not self.credentials:
            return
        users = self.credentials.usernames()
        if not users:
            if self._ready("sem login"):
                self.log("jogo deslogado e nenhum login salvo (aba Login)")
                self.cooldown["sem login"] = self.clock() + 600
            return
        user = users[0]
        if self._do("login", lambda: acc.login(user, self.credentials.get(user))):
            self.log(f"login feito ({user})")
