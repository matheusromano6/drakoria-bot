"""Conexao com o IdleDeck (que precisa estar aberto com a depuracao remota).
Cada conta do Drakoria e' uma pagina 'drakoria.com.br' na mesma conexao; paginas
de OUTROS jogos nunca sao tocadas."""
import urllib.request

from playwright.sync_api import sync_playwright

from . import launcher
from .account import Account

from .selectors import GAME_HOST

CONNECT_TIMEOUT_MS = 45000


def port_open(cdp_url, timeout=2):
    try:
        urllib.request.urlopen(f"{cdp_url}/json/version", timeout=timeout)
        return True
    except Exception:
        return False


class Pool:
    """Mantem a conexao e a lista de contas (paginas do Drakoria)."""

    def __init__(self, cdp_url, log=print):
        self.cdp_url = cdp_url
        self.log = log
        self._pw = None
        self.browser = None
        self._accounts = {}      # id(page) -> Account
        self._warned_empty = False

    def open(self, launch=True, stop=None):
        """Conecta. Se o IdleDeck nao esta com a porta, ABRE ele (launch=True) - ver launcher.py."""
        if not port_open(self.cdp_url):
            if not launch:
                raise RuntimeError(f"nenhum navegador com depuração em {self.cdp_url}: abra o navegador do jogo com "
                                   f"--remote-debugging-port (ou ligue 'Abrir o IdleDeck' na aba Login)")
            if not launcher.launch(self.cdp_url, lambda: port_open(self.cdp_url), self.log, stop):
                raise RuntimeError(f"IdleDeck sem depuracao remota em {self.cdp_url}")
        self._pw = sync_playwright().start()
        self.log(f"Conectando ao navegador do jogo ({self.cdp_url.rsplit(':', 1)[-1]})...")
        try:
            # o Playwright precisa de resposta de TODAS as abas do IdleDeck; uma aba travada (de qualquer jogo)
            # segurava a conexao pra sempre sem log nenhum (visto 20/10 com as abas do Huntera)
            self.browser = self._pw.chromium.connect_over_cdp(self.cdp_url, timeout=CONNECT_TIMEOUT_MS)
        except Exception as error:
            self.close()
            if "Timeout" in type(error).__name__ or "Timeout" in str(error):
                raise RuntimeError(f"o IdleDeck nao respondeu em {CONNECT_TIMEOUT_MS // 1000}s: alguma aba (de "
                                   "qualquer jogo) esta travada. Recarregue as abas ou reinicie o IdleDeck.") from None
            raise

    def close(self):
        try:
            if self._pw:
                self._pw.stop()
        finally:
            self._pw = None
            self.browser = None

    def refresh(self):
        """Reencontra as paginas do Drakoria (conta aberta/fechada depois do inicio)."""
        pages = [p for c in self.browser.contexts for p in c.pages if GAME_HOST in p.url]
        known = {}
        for page in pages:
            acc = self._accounts.get(id(page)) or Account(page, self.log)
            if acc.page is page:
                known[id(page)] = acc
        gone = set(self._accounts) - set(known)
        new = set(known) - set(self._accounts)
        self._accounts = known
        if gone or new:
            self.log(f"paginas do Drakoria: {len(known)} (novas {len(new)}, fechadas {len(gone)})")
        if not known and not self._warned_empty:
            self._warned_empty = True
            self.log("Aguardando as contas do Drakoria abrirem no IdleDeck...")
        elif known:
            self._warned_empty = False
        # nomes ficam so' depois da 1a leitura
        for acc in known.values():
            if not acc.name:
                try:
                    acc.read()
                except Exception:
                    pass
        return list(known.values())
