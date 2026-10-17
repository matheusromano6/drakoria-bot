"""A pagina do Drakoria no IdleDeck: UMA conta controla a party inteira (4 personagens).
read() le tudo num unico evaluate; as acoes so' clicam no que foi mapeado ao vivo."""
import re
import time
from dataclasses import dataclass, field

from . import selectors as S

READ_JS = r"""() => {
  const txt = e => (e && (e.innerText || e.textContent) || '').trim();
  const vis = e => e && e.getBoundingClientRect().width > 0;
  const body = document.body ? document.body.innerText : '';
  const scene = document.querySelector('main.content > section');
  const out = {url: location.href, title: document.title, scene: scene ? String(scene.className) : '',
    hasGame: !!document.querySelector('.td-member, .topbar-gold-balance'),
    loginForm: vis(document.querySelector('input[type=password]')),
    landing: /Monte seu grupo|Jogar grátis|Já tenho conta/.test(body.slice(0, 3000)),
    error: /Error 10\d\d|Bad Gateway|Cloudflare|ERR_|This site can.t be reached/i.test(body.slice(0, 2000)),
    disconnected: /desconectad|conexão perdida|reconectando/i.test(body.slice(0, 4000)),
    members: [], gold: '', goldTitle: '', loot: null, backpack: '', premium: '', reserve: '', xph: '', profith: '',
    tracker: [], difficulty: '', dest: '', modals: [], training: vis(document.querySelector('.house-hud-btn.danger'))};
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
  document.querySelectorAll('.bestiary-tracker-row').forEach(t => out.tracker.push((t.title || '').split(':')[0].trim()));
  out.difficulty = txt(document.querySelector('.world-hunt-difficulty-control')).split('\n')[0] || '';
  const d = document.querySelector('.cp-dest'); out.dest = d ? (d.title || '') : '';
  document.querySelectorAll('.modal, .tibia-window').forEach(w => {
    if (!vis(w)) return;
    const head = txt(w.querySelector('.tibia-window-brand, header')).split('\n')[0];
    if (head) out.modals.push(head);
  });
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
    difficulty: str = ""
    dest: str = ""                   # proxima caça na cidade
    modals: list = field(default_factory=list)

    @property
    def level(self):
        return min((m.level for m in self.members), default=0)


def _int(text):
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


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
               tracker=list(raw.get("tracker") or []), difficulty=raw.get("difficulty", ""),
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
    def _js_click(self, selector):
        return self.page.evaluate("s => { const e = document.querySelector(s); if (!e) return false; e.click(); return true; }",
                                  selector)

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
        """Relatorio offline / avisos: clica so' botoes inofensivos (Coletar e continuar, OK, Continuar...)."""
        if self._js_click(S.OFFLINE_COLLECT):
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
        box = self.page.locator(S.PICKER + " " + S.PICKER_SEARCH)
        box.click()
        box.fill("")
        box.press_sequentially(hunt, delay=30)        # digitar dispara o filtro (fill pode nao disparar)
        time.sleep(0.6)
        tile = self.page.locator(S.PICKER_TILE).filter(
            has=self.page.locator("strong", has_text=re.compile("^" + re.escape(hunt) + "$")))
        if tile.count() == 0:
            self.close_windows()
            raise RuntimeError(f"caça '{hunt}' nao encontrada na lista")
        tile.first.scroll_into_view_if_needed()
        tile.first.locator(S.PICKER_TILE_MAIN).evaluate("e => e.click()")
        time.sleep(0.5)
        start = self.page.locator(S.PICKER + " " + S.PICKER_START)
        if start.count() == 0 or start.first.is_disabled():
            self.close_windows()
            raise RuntimeError(f"'Caçada online' indisponivel em {hunt}")
        start.first.click()
        if not self._wait(lambda: self.page.locator(S.DIFF_WINDOW).is_visible(), 6):
            raise RuntimeError("a janela 'Prepare sua caçada' nao abriu")
        option = self.page.locator(S.DIFF_OPTION).filter(has_text=re.compile("^\\s*" + re.escape(difficulty)))
        if option.count() and option.first.is_enabled():
            option.first.click()
        else:
            self.log(f"dificuldade '{difficulty}' indisponivel: usando a selecionada")
        time.sleep(0.3)
        self.page.locator(S.DIFF_CONFIRM).click()
        if not self._wait(lambda: S.SCENE_HUNTING in (self.page.evaluate(
                "s => (document.querySelector(s) || {}).className || ''", S.SCENE) or ""), 12):
            raise RuntimeError("nao entrou na caçada")

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

    # ------------------------------------------------------------ login
    def login(self, username, password):
        """Pagina inicial -> 'Entrar' -> usuario/senha -> 'Entrar no jogo'. A senha nunca vai pro log."""
        if not self.page.locator(S.LOGIN_PASSWORD).first.is_visible():
            self._click_text("body", S.LOGIN_OPEN_TEXT)
            if not self._wait(lambda: self.page.locator(S.LOGIN_PASSWORD).first.is_visible(), 6):
                raise RuntimeError("formulario de login nao apareceu")
        pwd = self.page.locator(S.LOGIN_PASSWORD).first
        form = pwd.locator("xpath=ancestor::form[1]")
        scope = form if form.count() else self.page
        user = scope.locator("input:not([type=password]):not([type=checkbox]):not([type=hidden])").first
        user.fill(username)
        pwd.fill(password)
        if not self._click_text("body", S.LOGIN_SUBMIT_TEXT):
            pwd.press("Enter")
        if not self._wait(lambda: self.page.evaluate("() => !!document.querySelector('.td-member, .topbar-gold-balance')"), 25):
            raise RuntimeError("login nao entrou no jogo")
