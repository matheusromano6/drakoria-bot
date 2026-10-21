"""Imbuements por personagem/equipamento (aba Imbuements, usuario 21/10/2026). Puro: o motor le o jogo e decide aqui.

O usuario escolhe metas {member, slot, imbuement, tier, source}. Pra cada meta:
  - imbuement ativo com mais de 'prepare_hours' -> ok;
  - ativo mas acabando -> 'preparar' (junta os materiais da proxima aplicação);
  - ausente (acabou ou nunca aplicado) -> 'aplicar' assim que tiver material + taxa (reaplicar manual custa 250k no
    Powerful; a renovação nativa do jogo custa 750k, por isso o bot reaplica ele mesmo).
Materiais que faltam: source 'market' compra as ofertas mais baratas; 'hunt' caça; 'auto' compra se estiver ate X% do
preço justo e caça o resto. Caça do material = a que tem mais chance de drop por criatura (loot do proprio jogo)."""

SLOT_LABELS = {"weapon": "Arma", "head": "Capacete", "body": "Armadura", "shield": "Escudo", "feet": "Botas",
               "legs": "Calças", "backpack": "Mochila", "necklace": "Amuleto", "ring": "Anel", "ammo": "Munição"}
TIER_NAMES = ["Basic", "Intricate", "Powerful"]
SOURCES = {"auto": "Automático (compra barato, caça o resto)", "hunt": "Só caçar", "market": "Só comprar no Market"}


def target_key(t):
    return f"{t['member']}|{t['slot']}|{t['imbuement']}"


def definition(data, imb_id):
    return next((d for d in data["imbuements"] if d["id"] == imb_id), None)


def materials(data, imb_id, tier):
    """[(nome_minusculo, nome bonito, qtd)] do nivel: o nivel N usa os N+1 primeiros materiais."""
    d = definition(data, imb_id)
    if not d:
        return []
    return [(m["name"].casefold(), m.get("display") or m["name"], int(m["qty"]))
            for m in d["materials"][:max(0, min(2, int(tier))) + 1]]


def fee(data, tier):
    fees = (data.get("rules") or {}).get("goldFeeByTier") or [7500, 60000, 250000]
    return int(fees[max(0, min(len(fees) - 1, int(tier)))])


def compatible(data, kind):
    """Imbuements que servem pro tipo de item (kind do jogo: bow, helmet, ...)."""
    return [d for d in data["imbuements"] if kind in (d.get("kinds") or [])]


def all_material_names(data, targets):
    out = []
    for t in targets:
        for name, _, _ in materials(data, t["imbuement"], 2):
            if name not in out:
                out.append(name)
    return out


def status(target, game, data, prepare_hours):
    """Situação de uma meta no estado lido do jogo (Account.read_imbuements)."""
    out = {"key": target_key(target), "target": target, "state": "", "remaining": None, "item": None, "need": False,
           "member_id": None, "item_id": None}
    member = next((m for m in game.get("members") or [] if m["name"] == target["member"]), None)
    if not member:
        out["state"] = "personagem fora da party"
        return out
    out["member_id"] = member["id"]
    slot = next((s for s in member["slots"] if s["slot"] == target["slot"]), None)
    if not slot:
        out["state"] = "sem item com slot de imbuement"
        return out
    out["item"], out["item_id"] = slot["item"], slot["itemId"]
    d = definition(data, target["imbuement"])
    if not d or slot["kind"] not in (d.get("kinds") or []):
        out["state"] = f"{d['name'] if d else target['imbuement']} não serve em {slot['item']}"
        return out
    entry = next((e for e in slot["entries"] if e["id"] == target["imbuement"]), None)
    if entry:
        out["remaining"] = entry["h"]
        if entry["h"] >= prepare_hours:
            out["state"] = "ok"
        else:
            out["state"], out["need"] = "preparar", True
        return out
    if len(slot["entries"]) >= slot["cap"]:
        out["state"] = "sem slot livre"
        return out
    out["state"], out["need"] = "aplicar", True
    return out


def have(counts, name):
    inv, bank = counts.get(name, (0, 0))
    return inv + bank


def ready_to_apply(st, data, counts, gold, reserve):
    """True se da pra aplicar agora (materiais na mochila+depot e taxa sem passar da reserva)."""
    t = st["target"]
    if st["state"] != "aplicar":
        return False
    if gold is None or gold - fee(data, t["tier"]) < reserve:
        return False
    return all(have(counts, n) >= q for n, _, q in materials(data, t["imbuement"], t["tier"]))


def shortages(statuses, data, counts):
    """{material: (falta, source)} somando as metas que precisam de material agora (aplicar/preparar)."""
    need, source = {}, {}
    for st in statuses:
        if not st["need"]:
            continue
        t = st["target"]
        for name, _, qty in materials(data, t["imbuement"], t["tier"]):
            need[name] = need.get(name, 0) + qty
            source.setdefault(name, t.get("source") or "auto")
    return {n: (q - have(counts, n), source[n]) for n, q in need.items() if q > have(counts, n)}


def loop_material(statuses, data, counts):
    """'Continuar juntando': o material das metas com MENOS aplicações em estoque (pra caçar em loop)."""
    best = None
    for st in statuses:
        t = st["target"]
        if not st["item"] or t.get("source") == "market":
            continue
        for name, _, qty in materials(data, t["imbuement"], t["tier"]):
            uses = have(counts, name) / qty
            if best is None or uses < best[1]:
                best = (name, uses)
    return best[0] if best else None


def hunt_score(hunt, drops, material, others=()):
    """Chance media de drop por abate na caça (criaturas tratadas como igualmente frequentes) + metade das outras."""
    creatures = [c.casefold() for c in hunt["creatures"]]
    if not creatures:
        return 0.0

    def avg(name):
        table = drops.get(name) or {}
        return sum(table.get(c, 0.0) for c in creatures) / len(creatures)
    return avg(material) + 0.5 * sum(avg(o) for o in others if o != material)


def best_hunt(material, drops, hunts, level, others=()):
    """(caça, chance media) com mais drop do material que a party alcança (min <= level); None se nenhuma dropa."""
    best = None
    for hunt in hunts:
        if hunt.get("level", 0) > level:
            continue
        main = hunt_score(hunt, drops, material)
        if main <= 0:
            continue
        score = hunt_score(hunt, drops, material, others)
        if best is None or score > best[2] or (score == best[2] and hunt["level"] < best[0]["level"]):
            best = (hunt, main, score)
    return (best[0]["name"], best[1]) if best else None
