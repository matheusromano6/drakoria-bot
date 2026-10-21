"""Caças e bosses. As caças vem do catalogo do PROPRIO jogo (v1-content + premium-hunts-test passados por
applyHuntCatalogOverrides, a mesma funcao da lista 'Escolher Hunt'): relido a cada inicio do bot (hunts.json ao lado do
.exe); data/hunts.json (embutido, 116 caças em 21/10/2026) e' a reserva. Level = minimo/recomendado do jogo."""
import json
import os

from .paths import app_dir

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
# copia lida do PROPRIO jogo ao iniciar o bot (Engine): ao lado do .exe, vale mais que a embutida
LIVE_HUNTS = os.path.join(app_dir(), "hunts.json")


def _load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as file:
        return json.load(file)


def load_hunts():
    """Caças: a copia lida do jogo (hunts.json ao lado do .exe) se existir; senao a embutida."""
    try:
        with open(LIVE_HUNTS, encoding="utf-8") as file:
            data = json.load(file)
        hunts = data.get("hunts") if isinstance(data, dict) else None
        if hunts and len(hunts) >= 20:
            return hunts
    except (OSError, ValueError):
        pass
    return _load("hunts.json")


def save_live(hunts, read_at):
    with open(LIVE_HUNTS, "w", encoding="utf-8") as file:
        json.dump({"read_at": read_at, "hunts": hunts}, file, ensure_ascii=False, indent=1)


def load_bosses():
    return _load("bosses.json")


def identify(tracker, hunts):
    """Caça atual pelas criaturas do rastreador de bestiario (a tela de caça nao mostra o nome).
    Devolve o nome so' quando uma unica caça tem exatamente essas criaturas."""
    seen = {c.casefold() for c in tracker if c}
    if not seen:
        return None
    exact = [h["name"] for h in hunts if {c.casefold() for c in h["creatures"]} == seen]
    if len(exact) == 1:
        return exact[0]
    cover = [h["name"] for h in hunts if seen <= {c.casefold() for c in h["creatures"]}]
    return cover[0] if len(cover) == 1 else None
