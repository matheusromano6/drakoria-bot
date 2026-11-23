"""Motor: a cada 'poll_seconds' le a pagina (1 evaluate) e faz NO MAXIMO uma acao.
Prioridade: erro/queda -> login -> avisos -> loot (protecao de boss / venda) -> imbuements -> tasks/bestiary -> prey
-> destino.

Destino (usuario 20/10/2026): stamina abaixo de 'train_below_hours' (14h: a XP cai pela metade) -> treinar ate
'resume_hours'; senao objetivo (task ativa / bestiary) -> caça padrao da aba Regras -> treinar. Nunca parado."""
import time

import datetime

from . import goals as G
from . import imbuing as I
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
        self.active_tasks = []  # tasks nao sao mais lidas: nao deixa a task antiga do memory.json mandar na caca
        self._prey_warned = set()  # avisos ja dados (espaco, criatura, caça): nao repete a cada checagem
        self.boss_until = 0        # auto boss rodando: ate esse horario (rede de seguranca) o bot nao mexe nas contas
        self.boss_last = None      # ultimo boss da fila: quando ele termina, o bot volta as funções
        self.boss_checked = 0
        self.cooldown = {}              # acao -> horario liberado
        self.last_ok = {}               # acao -> ultimo sucesso
        self.phase_since = (None, 0)    # (fase, desde)
        self.mismatch = 0
        self.hunt_known = None          # caça atual quando o rastreador nao identifica (lida no 'Detalhes')
        self.resting = bool(memory.get("stamina_resting")) if memory else False   # treinando pra recuperar stamina
        self.user_busy_until = 0        # janela do usuario aberta: nada de mexer na tela ate esse horario
        self.hunts_checked = False      # catalogo de caças relido do jogo 1x por inicio do bot
        self.prey_spent = {}            # ouro gasto trocando lista da Prey hoje (sem memory.json)
        try:
            from .market import imbuements as MI
            self.imb_data = MI.load()
        except Exception:
            self.imb_data = {"imbuements": [], "rules": {}}
        self.imb_hunt = None            # (caça, motivo) pra juntar material de imbuement
        self.imb_drops = {}             # material -> {criatura: chance}
        self.imb_protected = set()      # materiais ja marcados 'coletar / nao vender' nesta execução
        self.imb_rows = []
        self.imb_seen = False           # set da party lido 1x (a aba Imbuements monta os menus com ele)
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
        """Dificuldade do objetivo atual (escolhida na aba Objetivos / Imbuements) ou a da aba Regras."""
        if self.imb_hunt:
            return (self.cfg.get("imbuing") or {}).get("difficulty") or self.cfg["difficulty"]
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
        if self.imb_hunt:
            self.snapshot["goal"] = self.imb_hunt[1]
            return self.imb_hunt[0]
        hunt, why, _ = self.goal_target(st)
        if hunt and self._hunt_unavailable(hunt):
            why = f"{why} (indisponível no jogo: usando a caça padrão)"
            hunt = None
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
        row = self._row(acc, st)
        row.update(phase=st.phase, gold=st.gold, loot=st.loot_items, target=current or (st.dest if st.phase == "city" else None),
                   auto=self.auto_sell(st), premium=st.premium)
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

        # 3b) auto boss: uma vez por dia (00:01). Enquanto a fila roda, o bot nao mexe em nenhuma conta.
        if now < self.boss_until:
            self._boss_hold(acc, now)
            return
        if acc is self.accounts[0] and st.phase in ("hunting", "city") and self._boss_due(now):
            self._auto_boss(acc, now)
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

        # 4b) builder: caçando a caça escolhida, confere de tempos em tempos se o combo ainda e' o melhor
        bcfg = self.cfg.get("builder") or {}
        fixed = (self.cfg.get("hunt") or "").strip()
        if bcfg.get("enabled", True) and st.phase == "hunting" and current and fixed \
                and current.casefold() == fixed.casefold():
            every = bcfg.get("check_minutes", 10) * 60
            if now - self.last_ok.get("builder check", -every) >= every and self._ready("builder"):
                if self._do("builder", lambda: self._apply_builder(acc, current)) is not None:
                    self.last_ok["builder check"] = now
                    return

        # 4c) atlas celestial: de tempos em tempos confere os pontos livres e aplica a build (1 conta: o jogo
        # devolve os 4 personagens do grupo)
        acfg = self.cfg.get("atlas") or {}
        if acfg.get("enabled", True) and acc is self.accounts[0] and st.phase in ("hunting", "city", "house", "house_idle"):
            every = acfg.get("check_minutes", 30) * 60
            if now - self.last_ok.get("atlas check", -every) >= every and self._ready("atlas"):
                if self._do("atlas", lambda: self._atlas(acc, acfg)) is not None:
                    self.last_ok["atlas check"] = now

        # 5) imbuements (acima de tasks/bestiary): aplica o que acabou, compra/escolhe caça pros materiais
        imb = self.cfg.get("imbuing") or {}
        if imb.get("enabled", True) and (imb.get("targets") or not self.imb_seen) and st.phase in ("hunting", "city", "house", "house_idle"):
            every = imb.get("check_minutes", 2) * 60
            if now - self.last_ok.get("imbuements", -every) >= every and self._ready("imbuements"):
                self._imbuing(acc, st)
        elif self.imb_hunt:
            self.imb_hunt = None

        # 6) tasks de produto: entrega as prontas e aceita as proximas da fila
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

        # 7) prey (so' caçando: o tempo da prey so' corre na caça)
        prey = self.cfg.get("prey") or {}
        if prey.get("enabled") and st.phase == "hunting" and current and self._settled(st, current):
            every = prey.get("check_minutes", 10) * 60
            if now - self.last_ok.get("prey", -every) >= every and self._ready("prey"):
                self._prey(acc, st, current)
                return

        # 8) destino: sempre caça ou treino (usuario 20/10: sem modo 'so vigiar')
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
                        self._start(acc, target, diff)
                    else:
                        # so' a dificuldade: ALTERAR (topo), sem trocar a caça e sem rodar o Builder de novo
                        self.log(f"{current} em {st.difficulty}, mas a escolhida e' {diff}: trocando a dificuldade")
                        if self._do("dificuldade", acc.change_difficulty, diff):
                            self.log(f"dificuldade trocada para {diff}")
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
        if self.imb_hunt:
            return self.imb_hunt[0].casefold() == current.casefold()
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
            self._row(acc, st)["prey"] = [(s["index"] + 1, s["creature"], s["bonus"], s["time"]) for s in slots
                                          if s["state"] == "active"]
            # prey ativa de criatura que nao esta na caça atual: troca a lista (ouro, nunca cartas) pelas regras de gasto
            in_hunt = {c.casefold() for c in creatures}
            swapped = False
            for s in slots:
                if s["state"] == "active" and s["creature"] and s["creature"].casefold() not in in_hunt:
                    gold, did = self._swap_prey(acc, s, gold, hunt)
                    swapped = swapped or did
            if swapped:
                slots = acc.read_prey()
            for slot in slots:
                rerolls = 0   # limite de trocas vale POR espaco (antes o espaco 1 gastava o limite do espaco 2)
                while slot["state"] == "selection":
                    _, spent = self._spent_today()
                    action = P.decide(slot, wanted, cfg, spent, gold)
                    if action is None:
                        break
                    kind, value = action
                    if kind == "reroll":
                        # 'ate achar': troca ate achar a criatura da caça (so' a reserva de ouro e um teto de seguranca
                        # de 200 trocas); outros modos: limite por checagem
                        limit = 200 if cfg.get("mode") == "until_found" else cfg.get("max_rerolls_per_check", 10)
                        if rerolls >= limit:
                            break  # limite de trocas nesta checagem: tenta de novo depois
                        acc.prey_reroll(slot["index"], value)
                        rerolls += 1
                        if value:
                            self._add_spent(value)
                            gold = None if gold is None else gold - value
                        self.log(f"Prey espaço {slot['index'] + 1}: trocou a lista ({'grátis' if not value else f'{value} de ouro'})")
                        slot = next(s for s in acc.read_prey() if s["index"] == slot["index"])
                        continue
                    acc.prey_choose(slot["index"], value)
                    self.log(f"Prey espaço {slot['index'] + 1}: {value} (da caça)")
                    break
            self.last_ok["prey"] = self.clock()
        except Exception as error:
            self._fail("prey", error)
        finally:
            try:
                acc.close_windows()
            except Exception:
                pass

    def _row(self, acc, st):
        """Linha da conta no painel (chave = nome do personagem; sem nome: 'conta N')."""
        try:
            number = self.accounts.index(acc) + 1
        except ValueError:
            number = "?"
        key = st.name or f"conta {number}"
        return self.snapshot.setdefault("accounts", {}).setdefault(key, {})

    def _boss_due(self, now):
        cfg = self.cfg.get("boss") or {}
        if not cfg.get("enabled", True):
            return False
        when = datetime.datetime.fromtimestamp(now)
        hour, minute = (int(x) for x in str(cfg.get("time", "00:01")).split(":"))
        done = self.memory.get("boss_day") if self.memory else getattr(self, "_boss_day", None)
        return when.hour * 60 + when.minute >= hour * 60 + minute and done != when.date().isoformat()

    def _auto_boss(self, acc, now):
        cfg = self.cfg.get("boss") or {}
        day = datetime.datetime.fromtimestamp(now).date().isoformat()
        result = self._do("auto boss", acc.start_auto_boss)
        if result is None:
            return  # erro: tenta de novo na proxima volta
        status, last = result if isinstance(result, tuple) else (result, None)
        if self.memory:
            self.memory.set("boss_day", day)
        self._boss_day = day
        if status == "iniciado":
            # segue a fila ate o ULTIMO boss terminar; 'max_hours' so' e' a rede de seguranca
            self.boss_last = last
            self.boss_until = now + cfg.get("max_hours", 4) * 3600
            self.boss_checked = now
            self.log(f"auto boss: fila iniciada; acompanho até o último ({last or '?'}) terminar")
        else:
            self.log(f"auto boss: {status} (volta a tentar amanhã)")

    def _boss_hold(self, acc, now):
        """Enquanto a fila de bosses roda, nao mexe nas contas. Libera quando o ultimo boss terminar (checa a cada 60s)."""
        if self.boss_last and acc is self.accounts[0] and now - self.boss_checked >= 60:
            self.boss_checked = now
            try:
                pending = acc.boss_pending(self.boss_last)
            except Exception as error:
                self._fail("auto boss", error)
                return
            if not pending:
                self.log(f"auto boss: último da fila ({self.boss_last}) terminou; o bot volta às funções")
                self.boss_last, self.boss_until = None, 0
        if self.boss_last is None:
            self.boss_until = 0
        self.snapshot["goal"] = f"auto boss rodando (até {self.boss_last or '…'})"

    def _swap_prey(self, acc, slot, gold, hunt):
        """Prey ativa de criatura fora da caça: 'Trocar lista' (ouro) se a regra de gasto deixar.
        Devolve (ouro novo, trocou?)."""
        cfg = self.cfg["prey"]
        idx, creature = slot["index"] + 1, slot["creature"]
        rr = slot.get("reroll") or {}
        price = rr.get("gold")
        if not slot.get("reroll_enabled") or not price or rr.get("cards"):
            key = (slot["index"], creature, hunt)
            if key not in self._prey_warned:
                self._prey_warned.add(key)
                self.log(f"Prey espaço {idx}: {creature} não é da caça {hunt}; sem troca em ouro, fica até acabar")
            return gold, False
        reserve = cfg.get("reserve_gold", 0)
        _, spent = self._spent_today()
        affordable = gold is None or gold - price >= reserve
        within = cfg.get("mode") == "until_found" or spent + price <= cfg.get("gold_per_day", 0)
        if not (affordable and within):
            key = (slot["index"], creature, hunt, "limite")
            if key not in self._prey_warned:
                self._prey_warned.add(key)
                self.log(f"Prey espaço {idx}: {creature} não é da caça {hunt}; troca de {price} de ouro fora do limite")
            return gold, False
        try:
            acc.prey_reroll(slot["index"], price)
        except Exception as error:
            self.log(f"Prey espaço {idx}: troca de {creature} falhou ({error})")
            return gold, False
        self._add_spent(price)
        self.log(f"Prey espaço {idx}: {creature} não é da caça {hunt}: troquei a lista ({price} de ouro)")
        return (None if gold is None else gold - price), True

    def _imbuing(self, acc, st):
        """Le o set da party, aplica as metas prontas, compra materiais e escolhe a caça dos que faltam."""
        cfg = self.cfg["imbuing"]
        prep = cfg.get("prepare_hours", 6)
        targets = [t for t in cfg["targets"] if t.get("enabled", True)]
        names = I.all_material_names(self.imb_data, targets)
        try:
            game = acc.read_imbuements(names)
            self._imb_state(game)
            self.imb_seen = True
            new = [n for n in names if n not in self.imb_protected]
            if new and acc.protect_materials(new):
                self.imb_protected.update(new)
            statuses = [I.status(t, game, self.imb_data, prep) for t in targets]
            reserve = (self.cfg.get("market") or {}).get("reserve_gold", 0)
            for s in statuses:
                if I.ready_to_apply(s, self.imb_data, game["counts"], game["gold"], reserve):
                    self._imb_apply(acc, s, game)
                    game = acc.read_imbuements(names)
            statuses = [I.status(t, game, self.imb_data, prep) for t in targets]
            short = I.shortages(statuses, self.imb_data, game["counts"])
            hunt_for = {}
            for name, (missing, source) in short.items():
                got = self._imb_buy(acc, name, missing, source) if source in ("market", "auto") else 0
                if missing - got > 0 and source in ("hunt", "auto"):
                    hunt_for[name] = missing - got
            self.imb_hunt = self._imb_choose_hunt(acc, st, hunt_for, statuses, game)
            self.imb_rows = self._imb_view(statuses, game)
            self.snapshot["imbuing"] = self.imb_rows
            self.last_ok["imbuements"] = self.clock()
        except Exception as error:
            self.imb_hunt = None
            self._fail("imbuements", error)

    def _imb_state(self, game):
        """Guarda o set lido (a aba Imbuements monta os menus com ele)."""
        if self.memory:
            self.memory.set("imbuing_party", [{"name": m["name"], "slots": [
                {"slot": s["slot"], "item": s["item"], "kind": s["kind"], "cap": s["cap"]} for s in m["slots"]]}
                for m in game["members"]])

    def _imb_apply(self, acc, s, game):
        t = s["target"]
        moves = []
        for name, _, qty in I.materials(self.imb_data, t["imbuement"], t["tier"]):
            inv, _ = game["counts"].get(name, (0, 0))
            if inv < qty:
                moves.append((name, qty - inv))
        d = I.definition(self.imb_data, t["imbuement"])
        label = f"{I.TIER_NAMES[t['tier']]} {d['name'] if d else t['imbuement']} em {s['item']} ({t['member']})"
        if self._do("aplicar imbuement", acc.apply_imbuement, s["member_id"], t["slot"], s["item_id"], t["imbuement"],
                    t["tier"], moves):
            self.log(f"imbuement aplicado: {label}" + (" (materiais tirados do depot)" if moves else ""))

    def _imb_spent(self):
        day = datetime.date.fromtimestamp(self.clock()).isoformat()
        data = (self.memory.get("imbuing_spent") if self.memory else None) or getattr(self, "_imb_spent_mem", {})
        return day, (data.get("gold", 0) if data.get("day") == day else 0)

    def _imb_buy(self, acc, name, missing, source):
        """Compra 'missing' pelas ofertas mais baratas. auto: so' ate buy_pct% do justo. Devolve quantos comprou."""
        if not self._ready("comprar " + name):
            return 0
        self.cooldown["comprar " + name] = self.clock() + 600     # 1 tentativa por material a cada 10 min
        from .market import analysis as A
        from .market.api import MarketApi, MarketError
        cfg, mcfg = self.cfg["imbuing"], self.cfg.get("market") or {}
        api = MarketApi(acc.page)
        try:
            item = api.search(name)
            if not item:
                return 0
            ev = A.evaluate(api.detail(item["id"]), mcfg)
            if not ev.offers:
                return 0
            if source == "auto":
                store = getattr(self.market, "store", None)
                ref, why = A.trusted_price(ev, store.recent_lows(ev.item_id) if store else [])
                if not ref:
                    self.log(f"imbuement: não compro {ev.name} agora ({why}); vou caçar")
                    return 0
                max_price = int(ref * cfg.get("buy_pct", 100) / 100)
            else:
                max_price = 10 ** 12
            day, spent = self._imb_spent()
            wallet = A._num((api.overview().get("wallet") or {}).get("goldSpendable")) or 0
            plan = A.buy_plan(ev, max_price, missing, wallet, mcfg.get("reserve_gold", 0),
                              max(0, cfg.get("daily_budget", 0) - spent))
            got = 0
            for offer, qty in plan:
                price = A._num(offer["unitPriceGold"])
                res = api.buy(offer, qty)
                got += qty
                spent += qty * price
                delivery = (res.get("delivery") or {}).get("id")
                store = getattr(self.market, "store", None)
                if store:
                    store.add_purchase(ev.item_id, ev.name, qty, price, offer["id"], delivery, auto=True,
                                       reason="imbuement")
                self.log(f"imbuement: comprou {qty}x {ev.name} a {int(price):,} no Market".replace(",", "."))
                if delivery:
                    api.claim(delivery)
            self._imb_spent_mem = {"day": day, "gold": spent}
            if self.memory and got:
                self.memory.set("imbuing_spent", self._imb_spent_mem)
            return got
        except MarketError as error:
            self.log(f"imbuement: compra de {name} falhou: {error}")
            return 0

    def _imb_choose_hunt(self, acc, st, hunt_for, statuses, game):
        cfg = self.cfg["imbuing"]
        if not hunt_for and cfg.get("end") == "loop":
            loop = I.loop_material(statuses, self.imb_data, game["counts"])
            if loop:
                hunt_for = {loop: 0}
        if not hunt_for:
            return None
        missing = [n for n in hunt_for if n not in self.imb_drops]
        if missing:
            self.imb_drops.update(acc.read_drops(missing))
        level = min((m["level"] for m in game["members"]), default=0) or st.level or 10 ** 6
        for name in hunt_for:
            found = I.best_hunt(name, self.imb_drops, self.hunts, level, list(hunt_for))
            if found:
                hunt, chance = found
                left = hunt_for[name]
                why = f"imbuement: {name} (faltam {left})" if left else f"imbuement: juntando {name} (loop)"
                return hunt, f"{why} · {chance * 100:.1f}% por abate"
            if self._ready("sem caça " + name):
                self.cooldown["sem caça " + name] = self.clock() + 3600
                self.log(f"imbuement: nenhuma caça alcançável dropa {name}")
        return None

    def _imb_view(self, statuses, game):
        rows = []
        for s in statuses:
            t = s["target"]
            mats = [(disp, I.have(game["counts"], n), q) for n, disp, q in I.materials(self.imb_data, t["imbuement"], t["tier"])]
            rows.append({"key": s["key"], "state": s["state"], "remaining": s["remaining"], "item": s["item"], "materials": mats})
        return rows

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

    def _atlas(self, acc, acfg):
        from . import atlas
        reserve = int(acfg.get("reserve_gold", 5_000_000))
        rows = acc.atlas(reserve, apply=False)              # simula primeiro
        if not any(r.get("ok") for r in rows):
            return                                          # nada pra gastar: silencio
        if acfg.get("auto_apply", True):
            rows = acc.atlas(reserve, apply=True)
        for line in atlas.summary(rows):
            self.log(f"Atlas: {line}")

    def _apply_builder(self, acc, target):
        from . import builder
        # 1o: pelo motor do jogo (sem janela, em segundo plano). Se nao der, usa a janela do Builder.
        try:
            builder.apply_by_game(acc.page, target, self.log, mode="apply")
            return
        except Exception as error:
            self.log(f"builder pelo motor do jogo falhou ({error}): usando a janela do Builder")
        acc.open_picker()
        try:
            builder.apply_for_hunt(acc.page, target, self.log)
        except Exception:
            self._builder_snapshot(acc)
            raise
        finally:
            acc.close_windows()

    def _builder_snapshot(self, acc):
        """Falha no builder: salva foto + botoes visiveis em logs/ (pra diagnosticar sem ver a tela)."""
        try:
            import os
            from .paths import app_dir
            folder = os.path.join(app_dir(), "logs")
            os.makedirs(folder, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            acc.page.screenshot(path=os.path.join(folder, f"builder_erro_{stamp}.png"))
            texts = acc.page.evaluate("""() => [...document.querySelectorAll('button, [role=tab]')]
                .filter(b => b.offsetParent).map(b => (b.innerText || b.title || '').trim().replace(/\\s+/g, ' ').slice(0, 60))""")
            with open(os.path.join(folder, f"builder_erro_{stamp}.txt"), "w", encoding="utf-8") as file:
                file.write("\n".join(t for t in texts if t))
            self.log(f"builder: diagnóstico salvo em logs/builder_erro_{stamp}.png")
        except Exception as error:
            self.log(f"builder: não consegui salvar o diagnóstico ({error})")

    def _start(self, acc, target, diff=None):
        diff = diff or self.cfg["difficulty"]
        if (self.cfg.get("builder") or {}).get("enabled", True):
            self._do("builder", lambda: self._apply_builder(acc, target))
        if self._do("iniciar caça", acc.start_hunt, target, diff):
            self.cooldown["iniciar caça"] = self.clock() + 20      # o jogo demora uns segundos pra mostrar a caça
            self.hunt_known = target
            self.log(f"caçando {target} ({diff})")
            if self.memory:
                self.memory.set("last_hunt", target)
        elif target != (self.cfg.get("hunt") or "").strip():
            # caça que o jogo nao tem (ex.: task aponta pra uma caça renomeada): usa a padrao por 1h
            self._hunt_unavailable(target)  # garante o dicionario
            self.hunt_fail[target.casefold()] = self.clock() + 3600
            self.log(f"caça '{target}' indisponível no jogo: uso a caça padrão por 1h")

    def _hunt_unavailable(self, name):
        if not hasattr(self, "hunt_fail"):
            self.hunt_fail = {}
        return self.hunt_fail.get(name.casefold(), 0) > self.clock()

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
