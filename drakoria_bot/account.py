"""A pagina do Drakoria no IdleDeck: UMA conta controla a party inteira (4 personagens).
read() le tudo num unico evaluate; as acoes so' clicam no que foi mapeado ao vivo."""
import re
import time
from dataclasses import dataclass, field

from . import prey as prey_rules
from . import selectors as S

READ_JS = r"""() => {
  const txt = e => (e && (e.innerText || e.textContent) || '').trim();
  const vis = e => e && e.getBoundingClientRect().width > 0;
  const body = document.body ? document.body.innerText : '';
  const scene = document.querySelector('main.content > section');
  const out = {url: location.href, title: document.title, scene: scene ? String(scene.className) : '',
    hasGame: [...document.querySelectorAll('.td-member, .topbar-gold-balance')].some(vis),
    loginForm: vis(document.querySelector('input[type=password]')),
    landing: /Monte seu grupo|Jogar grátis|Já tenho conta/.test(body.slice(0, 3000)),
    error: /Error 10\d\d|Bad Gateway|Cloudflare|ERR_|This site can.t be reached/i.test(body.slice(0, 2000)),
    disconnected: /desconectad|conexão perdida|reconectando/i.test(body.slice(0, 4000)),
    members: [], gold: '', goldTitle: '', loot: null, backpack: '', premium: '', reserve: '', xph: '', profith: '',
    tracker: [], kills: {}, trackerTitles: [], stamina: '', difficulty: '', dest: '', modals: [], training: vis(document.querySelector('.house-hud-btn.danger'))};
  document.querySelectorAll('.td-member-main').forEach(m => {
    const lines = txt(m).split('\n').map(s => s.trim()).filter(Boolean);
    out.members.push(lines);
  });
  const g = document.querySelector('.topbar-gold-balance');
  out.gold = txt(g); out.goldTitle = g ? (g.title || g.getAttribute('aria-label') || '') : '';
  document.querySelectorAll('.td-title, header').forEach(h => {
    const t = txt(h).split('\n').map(s => s.trim());
    if (t[0] === 'Loot Pouch' && out.loot === null && /^\d+$/.test(t[1] || '')) out.loot = +t[1];
    if (t[0] === 'Backpack' && !out.backpack) out.backpack = t[1] || '';
  });
  const m = body.match(/\nConta\n([^\n]+)/); if (m) out.premium = m[1];
  const r = body.match(/Reserva offline\n([\d:]+)/); if (r) out.reserve = r[1];
  const x = body.match(/XP da Party\/h\n([^\n]+)/); if (x) out.xph = x[1];
  const p = body.match(/Lucro\/h\n([^\n]+)/); if (p) out.profith = p[1];
  document.querySelectorAll('.bestiary-tracker-row').forEach(t => { const m = (t.title || '').match(/^([^:]+):\s*([\d.]+)/);
    if (m) { out.tracker.push(m[1].trim()); out.kills[m[1].trim()] = +m[2].replace(/\./g, ''); }
    if (t.title) out.trackerTitles.push(t.title); });
  out.difficulty = txt(document.querySelector('.world-hunt-difficulty-control')).split('\n')[0] || '';
  const d = document.querySelector('.cp-dest'); out.dest = d ? (d.title || '') : '';
  const sm = [...document.querySelectorAll('.td-skill.resource-meter')].find(e => /^\s*Stamina/.test(e.innerText || ''));
  out.stamina = sm ? sm.innerText.replace(/\s+/g, ' ').trim() : '';
  document.querySelectorAll('.modal, .tibia-window, .workspace-window').forEach(w => {
    if (!vis(w)) return;
    const head = txt(w.querySelector('.tibia-window-brand, header')).split('\n')[0];
    if (head) out.modals.push(head);
  });
  return out;
}"""


PREY_JS = r"""([slotSel, creatureSel, toolSel]) => {
  const out = [];
  document.querySelectorAll('.drk-prey-window ' + slotSel).forEach((s, index) => {
    const cls = String(s.className);
    if (cls.includes('state-locked')) return;
    const lines = (s.innerText || '').split('\n').map(x => x.trim()).filter(Boolean);
    const tool = [...s.querySelectorAll(toolSel)].find(b => /Trocar lista/.test(b.innerText));
    const active = cls.includes('state-active');
    const at = lines.indexOf('Prey ativo');
    out.push({index, state: active ? 'active' : (cls.includes('state-selection') ? 'selection' : 'other'),
      creature: active && at >= 0 ? lines[at + 1] : '', bonus: active && at >= 0 ? lines[at + 2] : '',
      time: (lines.find(l => /^\d+:\d\d:\d\d$/.test(l)) || ''),
      options: active ? [] : [...s.querySelectorAll(creatureSel)].map(b => b.title),
      reroll_title: tool ? (tool.title || '') : '', reroll_text: tool ? tool.innerText.replace(/\n/g, ' ') : '',
      reroll_enabled: !!tool && !tool.disabled});
  });
  return out;
}"""


TASKS_JS = r"""() => {
  const lines = e => (e.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
  const rows = {};
  document.querySelectorAll('.tibia-tasks-list .tibia-task-row').forEach(r => {
    const cls = String(r.className); const name = lines(r)[0];
    rows[name] = cls.includes('claimed') ? 'done' : cls.includes('accepted') ? 'active' : cls.includes('locked') ? 'locked' : 'available';
  });
  const active = [...document.querySelectorAll('.tibia-tasks-active .tibia-task-active')].map(a => {
    const l = lines(a); const pm = l.map(x => x.match(/^([\d.]+)\s*\/\s*([\d.]+)(\s|$)/)).find(Boolean);
    const deliver = [...a.querySelectorAll('button')].find(b => !b.classList.contains('tibia-task-cancel'));
    const have = pm ? +pm[1].replace(/\./g, '') : 0, need = pm ? +pm[2].replace(/\./g, '') : 0;
    return {name: l[0], have, need, deliver: !!deliver && !deliver.disabled, deliverText: deliver ? deliver.innerText.trim() : ''};
  });
  return {rows, active};
}"""


BESTIARY_JS = r"""async () => {
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const tiles = () => [...document.querySelectorAll('.bestiary-class-tile')];
  const known = tiles().map(t => t.innerText.replace(/\s+/g, ' ').trim()).filter(t => !/ 0 \//.test(' ' + t.split(' ').slice(-3).join(' ')));
  const out = [];
  for (const label of known) {
    const tile = tiles().find(x => x.innerText.replace(/\s+/g, ' ').trim() === label);
    if (!tile) continue;
    tile.click(); await wait(500);
    document.querySelectorAll('.bestiary-creature:not(.unknown)').forEach(c => out.push(c.title || ''));
    const back = [...document.querySelectorAll('.workspace-window button')].find(b => b.innerText.trim() === 'Voltar');
    if (back) { back.click(); await wait(350); }
  }
  return out;
}"""


@dataclass
class Member:
    name: str
    role: str = ""
    level: int = 0
    xp_pct: int = 0
    hp: int = 0
    hp_max: int = 0


@dataclass
class State:
    phase: str = "unknown"           # hunting | house (treinando) | house_idle | city | login | error | unknown
    members: list = field(default_factory=list)
    gold: str = ""
    loot_items: int = None
    backpack: str = ""
    premium: bool = False
    reserve: str = ""
    xp_hour: str = ""
    profit_hour: str = ""
    tracker: list = field(default_factory=list)     # criaturas do rastreador (identifica a caça)
    kills: dict = field(default_factory=dict)       # criatura -> abates no bestiario (qual aparece mais)
    tracker_titles: list = field(default_factory=list)  # 'Troll: 4 de 250 kills · faltam 246' (meta do bestiary)
    stamina: float = None            # horas de stamina de caça (maximo 42); None = nao lida
    difficulty: str = ""
    dest: str = ""                   # proxima caça na cidade
    modals: list = field(default_factory=list)

    @property
    def gold_value(self):
        return parse_gold(self.gold)

    @property
    def level(self):
        return min((m.level for m in self.members), default=0)


def _int(text):
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def parse_gold(text):
    """'500' -> 500, '4,9k' -> 4900, '1,2kk' / '1,2m' -> 1200000 (o topo arredonda)."""
    t = (text or "").strip().lower().replace(" ", "")
    if not re.search(r"\d", t):
        return None
    mult = 1
    if t.endswith("kk") or t.endswith("m"):
        mult, t = 1_000_000, t.rstrip("km")
    elif t.endswith("k"):
        mult, t = 1000, t[:-1]
    try:
        if mult > 1:
            return int(float(t.replace(".", "").replace(",", ".")) * mult)
        return int(re.sub(r"[^\d]", "", t) or 0)
    except ValueError:
        return None


def parse_stamina(text):
    """'Stamina 23:07:40' -> 23.13 (horas); None se nao achar."""
    m = re.search(r"(\d+):(\d\d)(?::(\d\d))?", text or "")
    if not m:
        return None
    return int(m.group(1)) + int(m.group(2)) / 60 + int(m.group(3) or 0) / 3600


def parse_member(lines):
    """['MRKina', 'TANK', 'Lv 8 · 17%', '185/185', '75/75'] -> Member."""
    mem = Member(name=lines[0] if lines else "?")
    for line in lines[1:]:
        lv = re.match(r"Lv\s*([\d.]+)\s*·\s*(\d+)%", line)
        if lv:
            mem.level, mem.xp_pct = _int(lv.group(1)), int(lv.group(2))
        elif re.fullmatch(r"[A-Z]{2,6}", line) and not mem.role:
            mem.role = line
        elif "/" in line and not mem.hp_max:
            a, _, b = line.partition("/")
            mem.hp, mem.hp_max = _int(a), _int(b)
    return mem


def parse_state(raw):
    st = State(gold=raw.get("gold", ""), loot_items=raw.get("loot"), backpack=raw.get("backpack", ""),
               reserve=raw.get("reserve", ""), xp_hour=raw.get("xph", ""), profit_hour=raw.get("profith", ""),
               tracker=list(raw.get("tracker") or []), kills=dict(raw.get("kills") or {}),
               tracker_titles=list(raw.get("trackerTitles") or []), stamina=parse_stamina(raw.get("stamina")),
               difficulty=raw.get("difficulty", ""),
               modals=list(raw.get("modals") or []))
    st.premium = "premium" in (raw.get("premium") or "").casefold()
    dest = re.match(r"Próximo destino:\s*([^·]+)", raw.get("dest") or "")
    st.dest = dest.group(1).strip() if dest else ""
    st.members = [parse_member(lines) for lines in raw.get("members") or [] if lines]
    scene = raw.get("scene") or ""
    if raw.get("error") and not raw.get("hasGame"):
        st.phase = "error"
    elif raw.get("disconnected"):
        st.phase = "error"
    elif not raw.get("hasGame") and (raw.get("loginForm") or raw.get("landing")):
        st.phase = "login"
    elif S.SCENE_HUNTING in scene:
        st.phase = "hunting"
    elif S.SCENE_HOUSE in scene:
        st.phase = "house" if raw.get("training") else "house_idle"
    elif S.SCENE_CITY in scene:
        st.phase = "city"
    return st


class Account:
    def __init__(self, page, log=print):
        self.page = page
        self.log = log
        self.state = State()

    @property
    def name(self):
        return self.state.members[0].name if self.state.members else ""

    # ------------------------------------------------------------ leitura
    def read(self):
        self.state = parse_state(self.page.evaluate(READ_JS))
        return self.state

    # ------------------------------------------------------------ util
    def _js_click(self, selector, visible=False):
        return self.page.evaluate("""([s, visible]) => { const e = [...document.querySelectorAll(s)]
                 .find(e => !visible || e.getBoundingClientRect().width > 0);
                 if (!e) return false; e.click(); return true; }""", [selector, visible])

    def _click_text(self, scope, pattern):
        """Clica o 1o botao VISIVEL dentro de 'scope' cujo texto casa com o regex."""
        return self.page.evaluate(
            """([scope, pattern]) => { const r = new RegExp(pattern);
               const b = [...document.querySelectorAll(scope + ' button')].find(b => b.getBoundingClientRect().width > 0
                         && !b.disabled && r.test((b.innerText || '').trim()));
               if (!b) return false; b.click(); return true; }""", [scope, pattern])

    def _wait(self, fn, timeout=8.0, step=0.25):
        end = time.time() + timeout
        while time.time() < end:
            if fn():
                return True
            time.sleep(step)
        return False

    def close_windows(self):
        self.page.evaluate("""s => document.querySelectorAll(s).forEach(b => {
            if (b.getBoundingClientRect().width > 0 && /Fechar|×/.test((b.title || '') + (b.getAttribute('aria-label') || '') + b.innerText)) b.click(); })""",
                           S.WINDOW_CLOSE)
        time.sleep(0.3)

    def dismiss_popups(self):
        """Relatorio offline / avisos: clica so' botoes inofensivos (Coletar e continuar, OK, Continuar...).
        NUNCA fecha outras janelas: podem ser do usuario (20/10: o bot fechava a lista de caças que o usuario abria)."""
        if self._js_click(S.OFFLINE_COLLECT, visible=True):
            return "relatório offline coletado"
        if self._click_text(".modal", S.DISMISS_TEXT):
            return "aviso fechado"
        return None

    def reload(self):
        self.page.goto("https://jogo." + S.GAME_HOST + "/", wait_until="domcontentloaded", timeout=45000)

    # ------------------------------------------------------------ caça
    def open_picker(self):
        self.close_windows()
        self.page.evaluate("s => document.querySelector(s).click()", S.NAV.format("hunt"))
        if not self._wait(lambda: self.page.locator(S.PICKER).is_visible(), 6):
            raise RuntimeError("a janela 'Escolher Hunt' nao abriu")
        self.page.evaluate("s => document.querySelector(s).click()", S.PICKER_BAND_ALL)
        time.sleep(0.4)

    def best_hunt(self):
        """Nome da caça marcada pelo jogo como 'Melhor escolha' pro level da party."""
        self.open_picker()
        try:
            return self.page.evaluate("""s => { const f = document.querySelector(s); const t = f && f.closest('.hw-tile');
                                          return t ? t.querySelector('strong').innerText.trim() : ''; }""", S.PICKER_BEST)
        finally:
            self.close_windows()

    def start_hunt(self, hunt, difficulty="Normal"):
        """Escolher Hunt -> card da caça -> Caçada online -> dificuldade -> Entrar na caçada."""
        self.open_picker()
        # a janela se redesenha o tempo todo (20/10: campo e botoes 'somem' no meio do click do Playwright):
        # tudo por JS no elemento do momento. Busca: valor + evento 'input' (o mesmo que digitar).
        self.page.evaluate("""([sel, text]) => { const box = document.querySelector(sel); if (!box) return;
            box.focus(); box.value = text; box.dispatchEvent(new Event('input', {bubbles: true}));
            box.dispatchEvent(new Event('change', {bubbles: true})); }""", [S.PICKER + " " + S.PICKER_SEARCH, hunt])
        pick = """([tileSel, mainSel, startSel, name]) => {
            const tile = [...document.querySelectorAll(tileSel)].find(t => (t.querySelector('strong')?.innerText || '').trim().toLowerCase() === name.toLowerCase());
            if (!tile) return 'sem card';
            if (!tile.classList.contains('is-selected')) { tile.scrollIntoView({block: 'center'}); tile.querySelector(mainSel)?.click(); return 'selecionou'; }
            const start = document.querySelector(startSel);
            if (!start) return 'sem botao';
            return start.disabled ? 'desabilitado' : 'pronto'; }"""
        state = ""
        for _ in range(12):
            time.sleep(0.5)
            state = self.page.evaluate(pick, [S.PICKER_TILE, S.PICKER_TILE_MAIN, S.PICKER + " " + S.PICKER_START, hunt])
            if state in ("pronto", "desabilitado"):
                break
        if state != "pronto":
            self.close_windows()
            raise RuntimeError(f"caça '{hunt}': {state if state != 'sem card' else 'nao encontrada na lista'}")
        # o jogo redesenha a janela o tempo todo (o botao 'some' no meio do click do Playwright, visto 20/10):
        # clica o elemento do momento via JS e confere se a janela de dificuldade abriu; tenta 3x
        for _ in range(3):
            self._js_click(S.PICKER + " " + S.PICKER_START, visible=True)
            if self._wait(lambda: self.page.locator(S.DIFF_WINDOW).is_visible(), 3):
                break
        else:
            raise RuntimeError("a janela 'Prepare sua caçada' nao abriu")
        clicked = self.page.evaluate("""([sel, name]) => {
            const o = [...document.querySelectorAll(sel)].find(e => (e.innerText || '').trim().startsWith(name) && !e.disabled);
            if (!o) return false; o.click(); return true; }""", [S.DIFF_OPTION, difficulty])
        if not clicked:
            self.log(f"dificuldade '{difficulty}' indisponivel: usando a selecionada")
        time.sleep(0.3)
        self._js_click(S.DIFF_CONFIRM, visible=True)
        if not self._wait(lambda: S.SCENE_HUNTING in (self.page.evaluate(
                "s => (document.querySelector(s) || {}).className || ''", S.SCENE) or ""), 12):
            raise RuntimeError("nao entrou na caçada")

    def current_hunt(self):
        """Nome da caça atual pela janela 'Detalhes das criaturas' (o rastreador pode estar mostrando as tasks)."""
        if not self._js_click(S.HUNT_DETAILS):
            raise RuntimeError("botao 'Detalhes das criaturas' nao encontrado")
        try:
            if not self._wait(lambda: self.page.locator(S.HUNT_DETAILS_WINDOW).first.is_visible(), 5):
                raise RuntimeError("janela de detalhes da caça nao abriu")
            head = self.page.locator(S.HUNT_DETAILS_WINDOW + " .tibia-window-brand").first.inner_text()
            return head.split("\n")[0].strip()
        finally:
            self.close_windows()

    def start_training(self):
        """Cidade/house -> 'Treino Online' (vai pra house e ja treina). Na house parada, o mesmo item volta a treinar."""
        if not self._js_click(S.TRAIN_ONLINE):
            raise RuntimeError("item de menu 'Treino Online' nao encontrado")
        if not self._wait(lambda: self.page.locator(S.HOUSE_STOP).first.is_visible(), 10):
            raise RuntimeError("nao comecou a treinar")

    def leave_hunt(self):
        """Caçando -> 'Retornar para Thais' (confirma se o jogo pedir)."""
        if not self._js_click(S.HUNT_EXIT, visible=True):
            raise RuntimeError("botao 'Retornar para Thais' nao encontrado")
        time.sleep(0.8)
        self._click_text(".modal", r"^(Retornar|Confirmar|Sim|Voltar|Sair)")
        if not self._wait(lambda: S.SCENE_HUNTING not in (self.page.evaluate(
                "s => (document.querySelector(s) || {}).className || ''", S.SCENE) or ""), 15):
            raise RuntimeError("nao saiu da caça")

    def stop_training(self):
        if not self._js_click(S.HOUSE_STOP):
            raise RuntimeError("botao 'Parar' do treino nao encontrado")
        self._wait(lambda: not self.page.locator(S.HOUSE_STOP).is_visible(), 6)

    def leave_house(self):
        if not self._js_click(S.HOUSE_LEAVE):
            raise RuntimeError("botao 'Sair da house' nao encontrado")
        if not self._wait(lambda: S.SCENE_HOUSE not in (self.page.evaluate(
                "s => (document.querySelector(s) || {}).className || ''", S.SCENE) or ""), 10):
            raise RuntimeError("nao saiu da house")

    # ------------------------------------------------------------ loot
    def _open_loot(self):
        self.close_windows()
        self.page.evaluate("s => document.querySelector(s).click()", S.LOOT_OPEN)
        if not self._wait(lambda: self.page.locator(S.LOOT_WINDOW).is_visible(), 5):
            raise RuntimeError("a Loot Pouch nao abriu")

    def _checkbox(self, label):
        return self.page.locator(S.LOOT_WINDOW + " label", has_text=label).locator("input[type=checkbox]").first

    def loot_settings(self, auto_sell):
        """Garante 'Proteger drops de boss' LIGADO e Auto Sell como pedido (None = nao mexe). Devolve o que mudou."""
        self._open_loot()
        changed = []
        try:
            protect = self._checkbox(S.LOOT_PROTECT_LABEL)
            if not protect.is_checked():
                protect.click()
                changed.append("Proteger drops de boss ligado")
            if auto_sell is not None:
                box = self._checkbox(S.LOOT_AUTOSELL_LABEL)
                if box.is_checked() != auto_sell:
                    box.click()
                    changed.append("Auto Sell " + ("ligado" if auto_sell else "desligado"))
            return changed
        finally:
            self.close_windows()

    def sell_all(self):
        """Loot Pouch -> 'Vender tudo agora' (confirma se o jogo pedir). Protegidos de boss ficam."""
        self._open_loot()
        try:
            protect = self._checkbox(S.LOOT_PROTECT_LABEL)
            if not protect.is_checked():          # nunca vender sem a protecao de boss
                protect.click()
                time.sleep(0.3)
            button = self.page.locator(S.LOOT_SELL_ALL)
            if button.is_disabled():
                return False
            button.click()
            time.sleep(0.8)
            self._click_text(".modal", r"^(Vender|Confirmar|Vender tudo)$")
            time.sleep(0.5)
            return True
        finally:
            self.close_windows()

    # ------------------------------------------------------------ tasks de produto
    def _open_tasks(self):
        self.close_windows()
        self.page.evaluate("s => document.querySelector(s).click()", S.TASKS_OPEN)
        if not self._wait(lambda: self.page.locator(S.TASKS_LIST).first.is_visible(), 6):
            raise RuntimeError("a janela de Tasks nao abriu")
        time.sleep(0.3)

    def read_tasks(self):
        """{'rows': {nome: done|active|locked|available}, 'active': [{name, have, need, ready, deliver}]}. Deixa a janela aberta."""
        self._open_tasks()
        data = self.page.evaluate(TASKS_JS)
        for task in data["active"]:
            task["ready"] = bool(task["deliver"] or (task["need"] and task["have"] >= task["need"]))
        return data

    def accept_task(self, name):
        row = self.page.locator(S.TASK_ROW).filter(has=self.page.locator(f"text={name}"))
        button = row.first.locator("button", has_text=S.TASK_ACCEPT_TEXT)
        if button.count() == 0 or button.first.is_disabled():
            raise RuntimeError(f"task '{name}' sem 'Aceitar' habilitado")
        button.first.click()
        if not self._wait(lambda: "accepted" in (row.first.get_attribute("class") or ""), 5):
            raise RuntimeError(f"task '{name}' nao ficou ativa")

    def deliver_task(self, name):
        """Botao da task ativa que NAO e' o Cancelar (texto ainda nao visto: Entregar/Concluir/Coletar)."""
        card = self.page.locator(S.TASK_ACTIVE).filter(has=self.page.locator(f"text={name}")).first
        button = card.locator("button:not(.tibia-task-cancel)").first
        if button.count() == 0 or button.is_disabled():
            raise RuntimeError(f"task '{name}' sem botao de entrega habilitado")
        text = button.inner_text().strip()
        if re.search(r"cancel|desist|abandon", text, re.I):
            raise RuntimeError(f"botao inesperado na task '{name}': {text}")
        button.click()
        time.sleep(0.8)
        self._click_text(".modal", r"^(Entregar|Confirmar|Concluir|Coletar|OK)$")
        if not self._wait(lambda: card.count() == 0 or not card.is_visible(), 6):
            raise RuntimeError(f"task '{name}' continua ativa depois de entregar")
        return text

    # ------------------------------------------------------------ bestiary
    def read_bestiary(self):
        """Cyclopedia > Bestiário: {criatura_minusculas: [abates, meta]} das conhecidas (as desconhecidas nem aparecem)."""
        from . import goals as goal_rules
        self.close_windows()
        self.page.evaluate("s => document.querySelector(s).click()", S.CYCLOPEDIA_OPEN)
        if not self._wait(lambda: self.page.locator(S.CYCLOPEDIA_TAB).first.is_visible(), 6):
            raise RuntimeError("a Cyclopedia nao abriu")
        try:
            self.page.locator(S.CYCLOPEDIA_TAB, has_text=S.BESTIARY_TAB_TEXT).first.click()
            if not self._wait(lambda: self.page.locator(S.BESTIARY_CLASS).first.is_visible(), 5):
                raise RuntimeError("aba Bestiário nao abriu")
            out = {}
            for title in self.page.evaluate(BESTIARY_JS):
                parsed = goal_rules.parse_bestiary_title(title)
                if parsed:
                    out[parsed[0].casefold()] = [parsed[1], parsed[2]]
            return out
        finally:
            self.close_windows()

    # ------------------------------------------------------------ prey
    def _open_prey(self):
        if self.page.locator(S.PREY_WINDOW).is_visible():
            return
        self.close_windows()
        self.page.evaluate("s => document.querySelector(s).click()", S.PREY_OPEN)
        if not self._wait(lambda: self.page.locator(S.PREY_WINDOW).is_visible(), 5):
            raise RuntimeError("a janela Prey nao abriu")

    def read_prey(self):
        """Abre a Prey e devolve os espacos liberados: [{index, state, creature, bonus, time, options, reroll, reroll_enabled}]."""
        self._open_prey()
        raw = self.page.evaluate(PREY_JS, [S.PREY_SLOT, S.PREY_CREATURE, S.PREY_TOOL])
        for slot in raw:
            slot["reroll"] = prey_rules.parse_reroll(slot.pop("reroll_title", ""), slot.pop("reroll_text", ""))
        return raw

    def _slot(self, index):
        return self.page.locator(S.PREY_WINDOW + " " + S.PREY_SLOT).nth(index)

    def prey_choose(self, index, creature):
        slot = self._slot(index)
        slot.locator(S.PREY_CREATURE + f'[title="{creature}"]').click()
        time.sleep(0.4)
        confirm = slot.locator(S.PREY_CONFIRM)
        if not confirm.is_enabled():
            raise RuntimeError(f"Confirmar da Prey desabilitado ({creature})")
        confirm.click()
        if not self._wait(lambda: "state-active" in (slot.get_attribute("class") or ""), 6):
            raise RuntimeError(f"Prey {creature} nao ficou ativa")
        # quando acabar: 'Liberar o espaco' (gratis) -> o bot escolhe de novo; nunca renovar/travar (gasta cartas)
        free = slot.locator(S.PREY_OPTION, has_text=S.PREY_RELEASE_TEXT).locator("input[type=radio]")
        if free.count() and not free.first.is_checked():
            free.first.check()

    def prey_reroll(self, index, max_price=0):
        """Troca a lista. Se o jogo pedir confirmacao com preço, so' paga se o preço for <= max_price; senao cancela."""
        slot = self._slot(index)
        names = "l => l.map(b => b.title).join('|')"
        before = slot.locator(S.PREY_CREATURE).evaluate_all(names)
        tool = slot.locator(S.PREY_TOOL, has_text=S.PREY_REROLL_TEXT).first
        if tool.is_disabled():
            raise RuntimeError("Trocar lista desabilitado")
        tool.click()
        time.sleep(0.6)
        ask = self.page.locator(S.PREY_ASK)
        if ask.count() and ask.first.is_visible():
            price = prey_rules.parse_price(ask.first.inner_text()) or 0
            if price > max_price:
                self.page.locator(S.PREY_ASK_CANCEL).first.click()
                raise RuntimeError(f"troca da lista custa {price} de ouro (limite {max_price}): cancelado")
            self.page.locator(S.PREY_ASK_PAY).first.click()
        if not self._wait(lambda: slot.locator(S.PREY_CREATURE).evaluate_all(names) != before, 6):
            raise RuntimeError("a lista da Prey nao mudou")

    # ------------------------------------------------------------ login
    def login(self, username, password):
        """Pagina inicial -> 'Entrar' -> usuario/senha -> 'Entrar no jogo'. A senha nunca vai pro log."""
        if not self.page.locator(S.LOGIN_PASSWORD).first.is_visible():
            self._click_text("body", S.LOGIN_OPEN_TEXT)
            if not self._wait(lambda: self.page.locator(S.LOGIN_PASSWORD).first.is_visible(), 6):
                raise RuntimeError("formulario de login nao apareceu")
        pwd = self.page.locator(S.LOGIN_PASSWORD + ":visible").first
        user = self.page.locator(S.LOGIN_USER + ":visible").first
        if user.count() == 0:
            user = self.page.locator("input[type=text]:visible").first
        user.fill(username)
        pwd.fill(password)
        if not self._click_text("body", S.LOGIN_SUBMIT_TEXT):
            pwd.press("Enter")
        visible = """s => [...document.querySelectorAll(s)].some(e => e.getBoundingClientRect().width > 0)"""
        if not self._wait(lambda: self.page.evaluate(visible, S.GAME_VISIBLE), 30):
            raise RuntimeError("login nao entrou no jogo")
