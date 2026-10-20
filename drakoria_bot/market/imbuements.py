"""Imbuements x Market (puro). Receitas lidas do jogo (data/imbuements.json, de imbuement-data.js):
o nivel N (0 Basic, 1 Intricate, 2 Powerful) usa os materiais 1..N+1; qualquer nivel pode ser pago com 10 Gold Tokens
ou 10 Silver Tokens no lugar dos materiais; toda aplicacao cobra a taxa de ouro (250.000).

Plano de um imbuement escolhido pelo usuario: pra cada material, quanto precisa (qtd x aplicações), quanto ja tem
(me/assets), quanto falta, menor preço / preço justo do Market e quanto custa comprar o que falta pelas ofertas mais
baratas. Compara com o caminho por tokens."""
import json
import os
from dataclasses import dataclass, field

from . import analysis as A

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "imbuements.json")
TIER_NAMES = ["Basic", "Intricate", "Powerful"]
CATEGORY_NAMES = {"skill": "Skill", "damage": "Dano", "protection": "Proteção", "support": "Suporte"}


def load():
    with open(DATA, encoding="utf-8") as file:
        return json.load(file)


def materials_for(definition, tier):
    """Materiais do nivel (0..2): o nivel N usa os N+1 primeiros."""
    return list(definition["materials"][:max(0, min(2, int(tier))) + 1])


def offer_cost(ev, quantity):
    """Custo de comprar 'quantity' pelas ofertas mais baratas (None se nao ha oferta suficiente)."""
    if not ev or quantity <= 0:
        return 0 if quantity <= 0 else None
    left, total = quantity, 0.0
    for offer in ev.offers:
        take = min(left, int(A._num(offer.get("remainingQuantity")) or 0))
        total += take * (A._num(offer.get("unitPriceGold")) or 0)
        left -= take
        if left <= 0:
            return total
    return None


@dataclass
class MaterialLine:
    name: str
    display: str
    per_use: int
    need: int
    have: int
    ev: object = None                # Evaluation do Market (ou None se o item nao foi lido)

    @property
    def missing(self):
        return max(0, self.need - self.have)

    @property
    def lowest(self):
        return self.ev.lowest_sell if self.ev else None

    @property
    def fair(self):
        return self.ev.fair if self.ev else None

    @property
    def on_sale(self):
        return self.ev.sell_qty if self.ev else 0

    @property
    def cost_missing(self):
        return offer_cost(self.ev, self.missing)


@dataclass
class Plan:
    definition: dict
    tier: int
    uses: int
    lines: list = field(default_factory=list)
    fee: int = 0
    token_cost: dict = field(default_factory=dict)     # 'gold token' / 'silver token' -> custo de 10 x uses (ou None)

    @property
    def cost_missing(self):
        """Custo pra completar os materiais que faltam (None se algum nao tem oferta suficiente)."""
        costs = [line.cost_missing for line in self.lines]
        return None if any(c is None for c in costs) else sum(costs)

    @property
    def fair_total(self):
        """Valor dos materiais de TODAS as aplicações pelo preço justo (None se falta preço de algum)."""
        values = [line.fair * line.need if line.fair else None for line in self.lines]
        return None if any(v is None for v in values) else sum(values)


def plan(definition, tier, uses, board, owned, rules=None):
    """board: nome_minusculo -> Evaluation; owned: nome_minusculo -> quantidade que o usuario tem."""
    uses = max(1, int(uses or 1))
    rules = rules or {}
    p = Plan(definition=definition, tier=int(tier), uses=uses, fee=int(rules.get("goldFee", 250000)) * uses)
    for material in materials_for(definition, tier):
        key = material["name"].casefold()
        p.lines.append(MaterialLine(name=material["name"], display=material["display"], per_use=int(material["qty"]),
                                    need=int(material["qty"]) * uses, have=int(owned.get(key, 0)), ev=board.get(key)))
    for token, cost_key in (("gold token", "goldTokenCost"), ("silver token", "silverTokenCost")):
        need = int(rules.get(cost_key, 10)) * uses
        p.token_cost[token] = offer_cost(board.get(token), max(0, need - int(owned.get(token, 0))))
    return p


def watched_materials(cfg, data):
    """Nomes (minusculos) dos materiais dos imbuements observados no nivel escolhido + os tokens."""
    out = set()
    chosen = cfg.get("imbuements") or {}
    for definition in data["imbuements"]:
        rule = chosen.get(definition["id"]) or {}
        if rule.get("watch"):
            out.update(m["name"].casefold() for m in materials_for(definition, rule.get("tier", 0)))
    if out:
        out.update({"gold token", "silver token"})
    return out
