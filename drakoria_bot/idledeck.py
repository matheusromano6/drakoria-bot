"""Conexao com o IdleDeck (que precisa estar aberto com a depuracao remota).
Cada conta do Drakoria e' uma pagina 'drakoria.com.br' na mesma conexao; paginas
de OUTROS jogos nunca sao tocadas."""
import time
import urllib.request

from playwright.sync_api import sync_playwright

from . import launcher
from .account import Account

from .selectors import GAME_HOST

CONNECT_TIMEOUT_MS = 45000
RECONNECT_AFTER_S = 60      # sem nenhuma conta do Drakoria por esse tempo: reconecta


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
        self._empty_since = None

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

    def _reconnect(self):
        from . import browsers
        try:
            best = [b for b in browsers.scan() if b["game_tabs"]]
        except Exception:
            best = []
        target = best[0]["url"] if best else self.cdp_url
        self.log(f"reconectando: navegador com o Drakoria em {target.rsplit(':', 1)[-1]}"
                 + ("" if best else " (nenhum achado; tentando a porta configurada)"))
        self.close()
        self.cdp_url = target
        self._accounts = {}
        try:
            self.open(launch=False)
        except Exception as error:
            self.log(f"reconexao falhou: {error}")

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
        if known:
            self._empty_since = None
        elif self._empty_since is None:
            self._empty_since = time.time()
        elif time.time() - self._empty_since > RECONNECT_AFTER_S:
            # sem nenhuma conta ha' muito tempo: a conexao pode estar presa num navegador sem o jogo (ex.: porta
            # errada ou conexao velha). Reconecta procurando o navegador em depuração que TEM o jogo aberto.
            self._empty_since = time.time()
            self._reconnect()
            return self.refresh()
        if not known and not self._warned_empty:
            self._warned_empty = True
            # diagnostico: mostra as paginas que o bot ENXERGA neste navegador (so o host, sem dados pessoais)
            seen = sorted({p.url.split("/")[2] for c in self.browser.contexts for p in c.pages if "://" in p.url})
            self.log(f"Aguardando as contas do Drakoria abrirem no IdleDeck (porta {self.cdp_url.rsplit(':', 1)[-1]}; "
                     f"paginas visiveis: {', '.join(seen[:8]) or 'nenhuma'})...")
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
