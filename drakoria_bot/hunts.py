"""Lista de caças e bosses (lidas ao vivo em 16/10/2026, data/*.json). O level das caças e' pensado pra 1 personagem;
com a party de 4 da pra ir em caças mais fortes, mas a escolha automatica usa a 'Melhor escolha' do proprio jogo."""
import json
import os

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as file:
        return json.load(file)


def load_hunts():
    return _load("hunts.json")


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
