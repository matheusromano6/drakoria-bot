"""Compra de arma de exercicio (Loja da Cidade > Treinamento) pelo motor do jogo, sem janela.

Verificado ao vivo (22/11/2026): a loja 'treinamento' vende as DURABLE exercise (1.800 cargas, 4.687.500 gold cada);
as exercise comuns (500 cargas) estao desligadas na configuracao da loja. Arma por vocacao: Knight = sword,
Paladin = bow, Sorcerer = wand, Druid = rod. A compra vai pro personagem da conta aberta (g.char).
"""

WEAPON = {"knight": "sword", "paladin": "bow", "sorcerer": "wand", "druid": "rod"}
SHOP = "treinamento"

# check=true so le (quanto custaria) sem comprar. quotas = {vocacao: quantidade}; reserve = gold que nunca e' gasto.
BUY_JS = r"""async ([shopId, quotas, reserve, check]) => {
  const g = window.__drkMarket && window.__drkMarket.game;
  if (!g || !g.char) return {ok: false, msg: 'motor do jogo indisponivel'};
  const voc = String(g.char.vocationName || '');
  const key = /knight/i.test(voc) ? 'knight' : /paladin/i.test(voc) ? 'paladin'
    : /sorcerer/i.test(voc) ? 'sorcerer' : /druid/i.test(voc) ? 'druid' : null;
  if (!key) return {ok: false, msg: 'vocacao sem arma de exercicio: ' + voc};
  const qty = Math.floor(Number(quotas[key] || 0));
  if (qty <= 0) return {ok: true, skip: 'quantidade 0 para ' + key};
  const name = 'durable exercise ' + ({knight: 'sword', paladin: 'bow', sorcerer: 'wand', druid: 'rod'})[key];
  const shop = g.cityShop(shopId);
  const row = shop && (shop.items || []).find(i => i.item && i.item.name === name);
  if (!row) return {ok: false, msg: name + ' nao esta a venda agora'};
  const cost = Number(row.price) * qty;
  const gold = Number(g.char.gold || 0);
  if (gold - cost < Number(reserve || 0)) return {ok: false, msg: 'gold abaixo da reserva (custaria ' + cost + ')'};
  if (check) return {ok: true, item: name, qty, cost, msg: 'simulado'};
  const r = g.buyCityShopItem(shopId, row.itemId, qty);
  return {ok: !!(r && r.ok), item: name, qty, cost, msg: (r && r.msg) || ''};
}"""
