"""Motor: a cada 'poll_seconds' le a pagina (1 evaluate) e faz NO MAXIMO uma acao.
Prioridade: erro/queda -> login -> avisos -> loot (protecao de boss / venda) -> tasks/bestiary -> prey -> destino.

Destino (usuario 20/10/2026): stamina abaixo de 'train_below_hours' (14h: a XP cai pela metade) -> treinar ate
'resume_hours'; senao objetivo (task ativa / bestiary) -> caça padrao da aba Regras -> treinar. Nunca parado."""
import time

import datetime

from . import goals as G
from . import hunts as H
from . import prey as P

LOOT_SETTINGS = "loot_settings"


class Engine:
    def __init__(self, accounts, cfg, log=print, refresh=None, memory=None, credentials=None, clock=time.time,
                 market=None):
        self.accounts = accounts
        self.cfg = cfg
        self.log = log
        self.refresh = refresh
        self.memory = memory
        self.credentials = credentials
        self.clock = clock
        self.market = market            # MarketWatcher (opcional)
        self.hunts = H.load_hunts()
        self.tasks = G.load_tasks()
        self.active_tasks = (memory.get("active_tasks") if memory else None) or []
        self.cooldown = {}              # acao -> horario liberado
        self.last_ok = {}               # acao -> ultimo sucesso
        self.phase_since = (None, 0)    # (fase, desde)
        self.mismatch = 0
        self.hunt_known = None          # caça atual quando o rastreador nao identifica (lida no 'Detalhes')
        self.resting = bool(memory.get("stamina_resting")) if memory else False   # treinando pra recuperar stamina
        self.user_busy_until = 0        # janela do usuario aberta: nada de mexer na tela ate esse horario
        self.hunts_checked = False      # catalogo de caças relido do jogo 1x por inicio do bot
        self.prey_spent = {}            # ouro gasto trocando lista da Prey hoje (sem memory.json)
        self.snapshot = {"state": None, "hunt": None, "target": None, "phase": "-", "action": "", "prey": [], "tasks": [], "goal": ""}

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

    def bestiary_progress(self):
        return (self.memory.get("bestiary") if self.memory else None) or getattr(self, "_bestiary", {})

    def _note_tracker(self, st):
        """Guarda abates/meta do bestiary lidos no rastreador da caça."""
        progress = dict(self.bestiary_progress())
        changed = False
        for title in st.tracker_titles:
            parsed = G.parse_tracker_title(title)
            if parsed:
                name, kills, goal = parsed
                key = name.casefold()
                if progress.get(key) != [kills, goal]:
                    if goal and kills >= goal and not G.bestiary_done(name, progress) and \
                            key in [c.casefold() for c in self.cfg["goals"]["bestiary"]]:
                        self.log(f"bestiary {name} completo ({kills}/{goal})")
                    progress[key] = [kills, goal]
                    changed = True
        if changed:
            self._bestiary = progress
            if self.memory:
                self.memory.set("bestiary", progress)

    def goal_target(self, st):
        goals = self.cfg.get("goals") or {}
        return G.goal_hunt(self.active_tasks, goals.get("bestiary") or [], self.bestiary_progress(), self.tasks,
                           self.hunts, st.level, 1000000)

    def target_difficulty(self, st):
        """Dificuldade do objetivo atual (escolhida na aba Objetivos) ou a da aba Regras."""
        _, _, key = self.goal_target(st)
        chosen = ((self.cfg.get("goals") or {}).get("difficulty") or {}).get(key or "")
        return chosen or self.cfg["difficulty"]

    def stamina_rest(self, st):
        """True enquanto a party deve treinar pra recuperar stamina (abaixo de train_below ate chegar em resume)."""
        cfg = self.cfg.get("stamina") or {}
        if st.stamina is None or not cfg.get("enabled", True):
            return self.resting
        below, resume = cfg.get("train_below_hours", 14), cfg.get("resume_hours", 24)
        if not self.resting and st.stamina < below:
            self.resting = True
            self.log(f"stamina {st.stamina:.1f}h (abaixo de {below}h): indo treinar ate {resume}h")
        elif self.resting and st.stamina >= resume:
            self.resting = False
            self.log(f"stamina recuperada ({st.stamina:.1f}h): voltando a caçar")
        if self.memory:
            self.memory.set("stamina_resting", self.resting)
        return self.resting

    def target_hunt(self, acc, st):
        """Caça de destino ou None = treinar."""
        if self.stamina_rest(st):
            self.snapshot["goal"] = "recuperando stamina (treino)"
            return None
        hunt, why, _ = self.goal_target(st)
        self.snapshot["goal"] = why
        if hunt:
            return hunt
        fixed = (self.cfg.get("hunt") or "").strip()
        if fixed:
            self.snapshot["goal"] = "caça padrão"
            return fixed
        self.snapshot["goal"] = "sem objetivo nem caça padrão: treino"
        return None

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
                    continue
                if self.market and self.snapshot.get("phase") not in ("login", "error", "unknown", "-"):
                    try:
                        if self.market.tick(acc.page, self.clock()):
                            self.snapshot["market"] = self.clock()
                    except Exception as error:
                        self.log(f"market: erro: {error}")
            # entre uma leitura e outra do jogo, o Market reage aos eventos ao vivo a cada ~1 s
            end = self.clock() + self.cfg["poll_seconds"]
            while not stop.is_set() and self.clock() < end:
                if self.market and self.accounts and self.snapshot.get("phase") not in ("login", "error", "unknown", "-"):
                    try:
                        self.market.react(self.accounts[0].page, self.clock())
                    except Exception as error:
                        self.log(f"market: erro ao vivo: {error}")
                stop.wait(1)

    def tick(self, acc):
        st = acc.read()
        now = self.clock()
        if st.phase != self.phase_since[0]:
            if self.phase_since[0] is not None:
                self.log(f"estado: {self.phase_since[0]} -> {st.phase}")
            self.phase_since = (st.phase, now)
        current = H.identify(st.tracker, self.hunts) if st.phase == "hunting" else None
        if st.phase != "hunting":
            self.hunt_known = None
        elif current:
            self.hunt_known = current
        elif self.hunt_known:
            current = self.hunt_known
        elif not st.modals:
            name = self._do("ler caça atual", acc.current_hunt)
            if isinstance(name, str) and name:
                self.hunt_known = current = name
        self.snapshot.update(state=st, phase=st.phase, hunt=current or (st.dest if st.phase == "city" else None))
        if self.memory and st.members:
            self.memory.set("party", [[m.name, m.role, m.level] for m in st.members])
        if st.phase in ("hunting", "house", "house_idle", "city") and not self.hunts_checked:
            self.hunts_checked = True
            self._refresh_hunts(acc)

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

        # 3) relatorio offline / avisos. Qualquer outra janela e' do USUARIO: o bot nao mexe na tela enquanto ela estiver
        #    aberta e por mais 'user_idle_seconds' depois (so' leitura; o Market ao vivo continua, ele nao usa a tela)
        if st.modals:
            done = acc.dismiss_popups()
            if done:
                self.log(done)
                return
            if now >= self.user_busy_until:
                self.log("janela aberta pelo usuário: o bot espera pra não atrapalhar")
            self.user_busy_until = now + self.cfg.get("user_idle_seconds", 60)
        if now < self.user_busy_until:
            self.snapshot["goal"] = "aguardando você usar o jogo"
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

        # 5) tasks de produto: entrega as prontas e aceita as proximas da fila
        goals = self.cfg.get("goals") or {}
        if st.phase == "hunting":
            self._note_tracker(st)
        if goals.get("bestiary") and st.phase in ("hunting", "city"):
            every = goals.get("bestiary_minutes", 30) * 60
            if now - self.last_ok.get("ler bestiary", -every) >= every and self._ready("ler bestiary"):
                found = self._do("ler bestiary", acc.read_bestiary)
                if isinstance(found, dict):
                    self._merge_bestiary(found)
                return
        if goals.get("enabled", True):
            every = goals.get("check_minutes", 10) * 60
            if now - self.last_ok.get("tasks", -every) >= every and self._ready("tasks"):
                self._tasks(acc, st)
                return

        # 6) prey (so' caçando: o tempo da prey so' corre na caça)
        prey = self.cfg.get("prey") or {}
        if prey.get("enabled") and st.phase == "hunting" and current and self._settled(st, current):
            every = prey.get("check_minutes", 10) * 60
            if now - self.last_ok.get("prey", -every) >= every and self._ready("prey"):
                self._prey(acc, st, current)
                return

        # 7) destino: sempre caça ou treino (usuario 20/10: sem modo 'so vigiar')
        target = self.target_hunt(acc, st)
        self.snapshot["target"] = target or "treino"
        if not target:
            self._go_train(acc, st)
            return
        if st.phase == "house":
            if self._do("parar treino", acc.stop_training):
                self.log("treino parado pra caçar")
        elif st.phase == "house_idle":
            if self._do("sair da house", acc.leave_house):
                self.log("saiu da house")
        elif st.phase == "city":
            self._start(acc, target, self.target_difficulty(st))
        elif st.phase == "hunting":
            diff = self.target_difficulty(st)
            wrong_hunt = current and current.casefold() != target.casefold()
            wrong_diff = current and not wrong_hunt and st.difficulty and \
                st.difficulty.casefold() != diff.casefold()
            if wrong_hunt or wrong_diff:
                self.mismatch += 1
                if self.mismatch >= 2:          # 2 leituras seguidas: troca de caça/dificuldade
                    self.mismatch = 0
                    if wrong_hunt:
                        self.log(f"caçando {current}, mas a escolhida e' {target}: trocando")
                    else:
                        self.log(f"{current} em {st.difficulty}, mas a escolhida e' {diff}: trocando a dificuldade")
                    self._start(acc, target, diff)
            else:
                self.mismatch = 0
                if current and self.memory:
                    self.memory.set("last_hunt", current)

    def _refresh_hunts(self, acc):
        """Rele o catalogo de caças do jogo (sem janela) e guarda ao lado do .exe; falhou = segue com o que tem."""
        try:
            fresh = acc.read_hunt_catalog()
        except Exception as error:
            self.log(f"catálogo de caças: não consegui ler do jogo ({error}); usando a lista salva")
            return
        if not fresh or len(fresh) < 20:
            return
        fresh = sorted(fresh, key=lambda h: (h["level"], h["name"]))
        if [h["name"] for h in fresh] != [h["name"] for h in self.hunts]:
            self.log(f"catálogo de caças atualizado do jogo: {len(fresh)} caças (eram {len(self.hunts)})")
        self.hunts = fresh
        try:
            H.save_live(fresh, datetime.datetime.now().isoformat(timespec="seconds"))
        except OSError:
            pass

    def _go_train(self, acc, st):
        """Destino treino: caçando -> volta pra cidade; cidade / house parada -> Treino Online. Treinando: nada."""
        if st.phase == "hunting":
            if self._do("sair da caça", acc.leave_hunt):
                self.log(f"saindo da caça pra treinar ({self.snapshot.get('goal')})")
        elif st.phase in ("city", "house_idle"):
            if self._do("treinar", acc.start_training):
                self.log(f"treinando ({self.snapshot.get('goal')})")

    def _settled(self, st, current):
        """Ja esta na caça que o bot quer? (nao escolhe Prey pra uma caça que vai trocar em seguida)"""
        if self.resting:
            return False
        hunt, _, _ = self.goal_target(st)
        wanted = hunt or (self.cfg.get("hunt") or "").strip()
        return bool(wanted) and wanted.casefold() == current.casefold()

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
                            acc.prey_reroll(slot["index"], value)
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

    def _tasks(self, acc, st):
        goals = self.cfg["goals"]
        try:
            data = acc.read_tasks()
            for task in data["active"]:
                if task["ready"]:
                    text = acc.deliver_task(task["name"])
                    self.log(f"task entregue: {task['name']} ({text})")
                    data = acc.read_tasks()
                    break
            active = [a for a in data["active"] if not a["ready"]]
            for name in G.next_tasks_to_accept(goals["tasks"], data["rows"], len(data["active"]), self.tasks,
                                               self.hunts, st.level, 1000000):
                acc.accept_task(name)
                self.log(f"task aceita: {name}")
                data = acc.read_tasks()
            self.active_tasks = [{"name": a["name"], "ready": a["ready"], "have": a["have"], "need": a["need"]}
                                 for a in data["active"]]
            self.task_rows = data["rows"]
            if self.memory:
                self.memory.set("active_tasks", self.active_tasks)
                self.memory.set("task_rows", data["rows"])
            self.snapshot["tasks"] = [(a["name"], a["have"], a["need"]) for a in self.active_tasks]
            self.last_ok["tasks"] = self.clock()
        except Exception as error:
            self._fail("tasks", error)
        finally:
            try:
                acc.close_windows()
            except Exception:
                pass

    def _merge_bestiary(self, found):
        progress = dict(self.bestiary_progress())
        queue = {c.casefold() for c in (self.cfg.get("goals") or {}).get("bestiary") or []}
        for key, value in found.items():
            before = progress.get(key)
            if key in queue and value[1] and value[0] >= value[1] and not (before and before[1] and before[0] >= before[1]):
                self.log(f"bestiary {key} completo ({value[0]}/{value[1]})")
            progress[key] = value
        self._bestiary = progress
        if self.memory:
            self.memory.set("bestiary", progress)

    def _start(self, acc, target, diff=None):
        diff = diff or self.cfg["difficulty"]
        if self._do("iniciar caça", acc.start_hunt, target, diff):
            self.cooldown["iniciar caça"] = self.clock() + 20      # o jogo demora uns segundos pra mostrar a caça
            self.hunt_known = target
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
