"""Navegadores pro bot, sem comando nenhum pro usuario (pedido 21/10/2026).

So' da pra controlar um navegador aberto com a porta de depuração (--remote-debugging-port); um navegador aberto do
jeito normal nao aceita. Entao:
  - scan(): acha os navegadores JA abertos nesse modo (portas 9200-9399 em escuta), diz qual programa e' (pelo PID) e
    se tem a aba do Drakoria -> o usuario escolhe um na interface.
  - launch(): abre o navegador escolhido nesse modo, num PERFIL PROPRIO do bot (o perfil principal do Chrome/Edge/
    Brave/Opera nao aceita depuração), ja na pagina do jogo. Login e VPN (Opera) ficam salvos nesse perfil.
"""
import json
import os
import re
import subprocess
import time
import urllib.request

from .paths import app_dir
from .selectors import GAME_HOST

GAME_URL = "https://jogo." + GAME_HOST + "/"
PORT_RANGE = range(9200, 9400)
NO_WINDOW = 0x08000000 if os.name == "nt" else 0

_LOCAL = os.environ.get("LOCALAPPDATA", "")
_PF = os.environ.get("ProgramFiles", r"C:\Program Files")
_PF86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
KNOWN = [
    ("Chrome", [rf"{_PF}\Google\Chrome\Application\chrome.exe", rf"{_PF86}\Google\Chrome\Application\chrome.exe",
                rf"{_LOCAL}\Google\Chrome\Application\chrome.exe"]),
    ("Edge", [rf"{_PF86}\Microsoft\Edge\Application\msedge.exe", rf"{_PF}\Microsoft\Edge\Application\msedge.exe"]),
    ("Brave", [rf"{_LOCAL}\BraveSoftware\Brave-Browser\Application\brave.exe",
               rf"{_PF}\BraveSoftware\Brave-Browser\Application\brave.exe"]),
    ("Opera", [rf"{_LOCAL}\Programs\Opera\opera.exe", rf"{_PF}\Opera\opera.exe"]),
    ("Opera GX", [rf"{_LOCAL}\Programs\Opera GX\opera.exe", rf"{_PF}\Opera GX\opera.exe"]),
    ("Vivaldi", [rf"{_LOCAL}\Vivaldi\Application\vivaldi.exe", rf"{_PF}\Vivaldi\Application\vivaldi.exe"]),
]
PROCESS_NAMES = {"chrome.exe": "Chrome", "msedge.exe": "Edge", "brave.exe": "Brave", "opera.exe": "Opera",
                 "vivaldi.exe": "Vivaldi", "idledeck.exe": "IdleDeck"}


def installed():
    """[(nome, caminho)] dos navegadores encontrados neste PC."""
    out = []
    for name, paths in KNOWN:
        for path in paths:
            if path and os.path.exists(path):
                out.append((name, path))
                break
    return out


def _listening_ports():
    """{porta: pid} das portas em escuta na faixa de depuração (netstat, sem dependencias)."""
    try:
        text = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=10,
                              creationflags=NO_WINDOW).stdout
    except Exception:
        return {}
    out = {}
    for line in text.splitlines():
        m = re.search(r"(?:127\.0\.0\.1|0\.0\.0\.0|\[::1?\]):(\d+)\s+\S+\s+LISTEN\w*\s+(\d+)", line)
        if m and int(m.group(1)) in PORT_RANGE:
            out[int(m.group(1))] = int(m.group(2))
    return out


def _process_name(pid):
    try:
        text = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True,
                              text=True, timeout=10, creationflags=NO_WINDOW).stdout
        exe = text.strip().split(",")[0].strip('"').lower()
    except Exception:
        return "Navegador"
    if exe == "opera.exe":
        return "Opera / Opera GX"
    return PROCESS_NAMES.get(exe, exe or "Navegador")


def _json(url, timeout=2):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


def scan():
    """Navegadores abertos no modo do bot: [{port, name, url, game_tabs, logged}] (com aba do jogo primeiro)."""
    found = []
    for port, pid in sorted(_listening_ports().items()):
        base = f"http://127.0.0.1:{port}"
        try:
            _json(base + "/json/version")
            targets = _json(base + "/json/list")
        except Exception:
            continue                     # porta em escuta mas nao e' depuração de navegador
        pages = [t for t in targets if t.get("type") == "page"]
        game = [t for t in pages if GAME_HOST in (t.get("url") or "")]
        found.append({"port": port, "name": _process_name(pid), "url": base, "game_tabs": len(game),
                      "logged": any("Online" in (t.get("title") or "") for t in game)})
    return sorted(found, key=lambda b: (not b["game_tabs"], b["port"]))


def free_port(start=9231):
    used = set(_listening_ports())
    for port in range(start, PORT_RANGE.stop):
        if port not in used:
            return port
    raise RuntimeError("nenhuma porta livre pra abrir o navegador")


def profile_dir(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return os.path.join(app_dir(), "navegador", slug)


def launch(name, path, port=None, url=GAME_URL, wait=25):
    """Abre o navegador no modo do bot (perfil proprio, porta de depuração) na pagina do jogo. Devolve a URL de conexão."""
    port = port or free_port()
    profile = profile_dir(name)
    os.makedirs(profile, exist_ok=True)
    subprocess.Popen([path, f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "--no-first-run",
                      "--no-default-browser-check", url], creationflags=NO_WINDOW)
    base = f"http://127.0.0.1:{port}"
    end = time.time() + wait
    while time.time() < end:
        try:
            _json(base + "/json/version", timeout=1)
            return base
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"{name} abriu mas a porta {port} nao respondeu")


def open_game_tab(base):
    """Abre uma aba do jogo num navegador ja no modo do bot (PUT /json/new)."""
    req = urllib.request.Request(f"{base}/json/new?{GAME_URL}", method="PUT")
    with urllib.request.urlopen(req, timeout=5):
        pass
