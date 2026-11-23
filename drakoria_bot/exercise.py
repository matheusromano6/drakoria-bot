"""Arma de exercicio no treino (Loja da Cidade > Treinamento), pelo motor do jogo, sem janela.

Verificado ao vivo (22-23/11/2026):
- a loja 'treinamento' vende as DURABLE exercise (1.800 cargas, 4.687.500 gold); as comuns (500 cargas) estao desligadas.
- arma por vocacao: Knight = sword, Paladin = bow, Sorcerer = wand, Druid = rod.
- o treino no Dummy gasta 0,5 carga por segundo (medido) e da 4 h de stamina por hora de treino ('Stamina +4h/h').
- a stamina aparece no HUD da house: 'Stamina HH:MM:SS'; as durables da mochila aparecem como 'Quantidade N'.
"""
import math

WEAPON = {"knight": "sword", "paladin": "bow", "sorcerer": "wand", "druid": "rod"}
SHOP = "treinamento"
TRAIN_GAIN_PER_HOUR = 4.0      # horas de stamina ganhas por hora de treino
CHARGES_PER_SECOND = 0.5       # cargas gastas por segundo de treino (medido)
CHARGES_PER_DURABLE = 1800


def plan(stamina_h, target_h, owned, max_buy=10):
    """Quantas durables comprar para ir da stamina atual ate target_h, descontando as que ja estao na mochila.
    Devolve horas de treino, cargas necessarias e a compra (limitada a max_buy)."""
    if stamina_h is None:
        return {"ok": False, "msg": "nao li a stamina no HUD"}
    hours = max(0.0, (float(target_h) - float(stamina_h)) / TRAIN_GAIN_PER_HOUR)
    need_charges = hours * 3600 * CHARGES_PER_SECOND
    missing = max(0.0, need_charges - int(owned) * CHARGES_PER_DURABLE)
    needed = math.ceil(round(missing / CHARGES_PER_DURABLE, 6))
    return {"ok": True, "hours": hours, "charges": need_charges, "owned": int(owned),
            "durables_needed": needed, "buy": min(needed, int(max_buy))}


# le vocacao, stamina (HUD), durables na mochila e o preco na loja. Nao compra nada.
READ_JS = r"""(shopId) => {
  const g = window.__drkMarket && window.__drkMarket.game;
  if (!g || !g.char) return {error: 'motor do jogo indisponivel'};
  const voc = String(g.char.vocationName || '');
  const key = /knight/i.test(voc) ? 'knight' : /paladin/i.test(voc) ? 'paladin'
    : /sorcerer/i.test(voc) ? 'sorcerer' : /druid/i.test(voc) ? 'druid' : null;
  const weapon = key ? ({knight: 'sword', paladin: 'bow', sorcerer: 'wand', druid: 'rod'})[key] : null;
  const shop = g.cityShop(shopId);
  const row = weapon && shop && (shop.items || []).find(i => i.item && i.item.name === 'durable exercise ' + weapon);
  const meter = [...document.querySelectorAll('.resource-meter')].map(e => (e.innerText || '').replace(/\s+/g, ' ').trim())
    .find(t => /^Stamina \d/.test(t)) || '';
  const m = meter.match(/(\d+):(\d\d):(\d\d)/);
  const stamina_h = m ? Number(m[1]) + Number(m[2]) / 60 : null;
  let owned = 0;
  if (weapon) document.querySelectorAll('.compact-storage-tile[aria-label]').forEach(e => {
    const label = e.getAttribute('aria-label') || '';
    if (label.toLowerCase().startsWith('durable exercise ' + weapon + '.')) {
      const q = label.match(/Quantidade (\d+)/); if (q) owned += Number(q[1]);
    }
  });
  return {vocation: voc, key, weapon, price: row ? Number(row.price) : null, gold: Number(g.char.gold || 0),
          stamina_h, owned};
}"""

# compra 'qty' durables do personagem da conta (pelo motor do jogo), sem deixar o gold abaixo da reserva.
BUY_JS = r"""async ([shopId, weapon, qty, reserve]) => {
  const g = window.__drkMarket && window.__drkMarket.game;
  if (!g || !g.char) return {ok: false, msg: 'motor do jogo indisponivel'};
  const name = 'durable exercise ' + weapon;
  const shop = g.cityShop(shopId);
  const row = shop && (shop.items || []).find(i => i.item && i.item.name === name);
  if (!row) return {ok: false, msg: name + ' nao esta a venda agora'};
  const cost = Number(row.price) * qty;
  if (Number(g.char.gold || 0) - cost < Number(reserve || 0)) return {ok: false, msg: 'gold abaixo da reserva (custaria ' + cost + ')'};
  const before = Number(g.char.gold || 0);
  const r = g.buyCityShopItem(shopId, row.itemId, qty);
  return {ok: !!(r && r.ok), item: name, qty, cost, msg: (r && r.msg) || '',
          gold_before: before, gold_after: Number(g.char.gold || 0)};
}"""
