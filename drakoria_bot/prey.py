"""Regras da Prey (puro, sem navegador). Usuario (17/10/2026):
espaco livre -> escolhe a criatura da caça que mais aparece; senao usa a troca GRATIS da lista; depois troca PAGA com ouro
ate o limite ('ate achar' ou 'ate X de ouro por dia'); nao achou -> escolhe qualquer uma (em 2h de caça o espaco libera e o
bot tenta de novo). NUNCA gasta cartas (Prey Wildcards) nem Drako Coins."""
import re


def parse_reroll(title, text):
    """Botao 'Trocar lista' -> {'free': bool, 'gold': int|None, 'cards': bool}. Preço desconhecido = nao paga."""
    blob = f"{title} {text}".casefold()
    # o preço vem antes: 'Trocar a lista: 3.000 gold (a troca grátis volta à meia-noite)' NAO e' gratis
    value = parse_price(blob)
    if value:
        return {"free": False, "gold": value, "cards": False}
    if "carta" in blob or "coin" in blob:
        return {"free": False, "gold": None, "cards": True}
    if "grátis" in blob or "gratis" in blob:
        return {"free": True, "gold": None, "cards": False}
    return {"free": False, "gold": None, "cards": False}


def parse_price(text):
    """'3.000 gold' -> 3000, '3k gold' -> 3000, 'Pagar 1,5k gold' -> 1500; sem preço -> None."""
    m = re.search(r"([\d][\d.,]*)\s*(k)?\s*(gold|ouro)", (text or "").casefold())
    if not m:
        return None
    number = m.group(1)
    if m.group(2):
        return int(float(number.replace(".", "").replace(",", ".")) * 1000)
    return int(re.sub(r"[^\d]", "", number))


def wanted_order(hunt_creatures, kills):
    """Criaturas da caça, da que mais aparece (mais abates no rastreador) pra menos."""
    kills = {k.casefold(): v for k, v in (kills or {}).items()}
    order = list(hunt_creatures or [])
    return sorted(order, key=lambda c: -kills.get(c.casefold(), 0))


def pick(options, wanted):
    """1a criatura de 'wanted' que esta na lista do espaco."""
    have = {o.casefold(): o for o in options}
    for creature in wanted:
        if creature.casefold() in have:
            return have[creature.casefold()]
    return None


def decide(slot, wanted, cfg, spent_today, gold_now=None):
    """Proxima acao num espaco em escolha:
    ('choose', criatura) | ('reroll', preço) | ('any', criatura) | None."""
    options = slot.get("options") or []
    if not options:
        return None
    found = pick(options, wanted)
    if found:
        return ("choose", found)
    reroll = slot.get("reroll") or {}
    if slot.get("reroll_enabled") and reroll.get("free"):
        return ("reroll", 0)
    price = reroll.get("gold")
    if slot.get("reroll_enabled") and price and not reroll.get("cards") and wanted:
        reserve = cfg.get("reserve_gold", 0)
        affordable = gold_now is None or gold_now - price >= reserve
        if cfg.get("mode") == "until_found":
            if affordable:
                return ("reroll", price)
        elif spent_today + price <= cfg.get("gold_per_day", 0) and affordable:
            return ("reroll", price)
    return ("any", options[0])
