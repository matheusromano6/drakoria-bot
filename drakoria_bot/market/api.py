"""Marketplace do Drakoria pela aba JA LOGADA (mapeado ao vivo em 20/10/2026).

A API (/api/v1/market/...) exige o cookie de sessao (HttpOnly), entao tudo roda DENTRO da pagina do jogo, sem
abrir janela. Leitura = fetch simples. Escrita (comprar / resgatar) = o MESMO fluxo do jogo,
MarketplaceUI.authoritativeMutation(): para o jogo, salva, sincroniza, chama a API e adota o save do servidor.
Chamar a URL crua deixaria o save local sobrescrever a compra.

A instancia viva do MarketplaceUI e' capturada embrulhando os metodos da classe (o modulo e' o mesmo objeto do jogo);
o jogo so' chama esses metodos quando o Marketplace abre, entao o bot abre a janela 1x por carga da pagina (~1s) e fecha.
"""

HOOK_JS = r"""async () => {
  const live = () => window.__drkMarket && window.__drkMarket.enabled && window.__drkMarket.enabled();
  if (live()) return 'ok';
  const app = [...document.scripts].map(s => s.src).find(s => /\/js\/app\.js/.test(s)) || '';
  const build = (app.match(/\?build=[^&]+/) || [''])[0];
  const mod = await import('/System/Marketplace/marketplace-ui.js' + build);
  const proto = mod.MarketplaceUI && mod.MarketplaceUI.prototype;
  if (!proto) return 'sem MarketplaceUI';
  if (!proto.__drkBotHook) {
    for (const name of Object.getOwnPropertyNames(proto)) {
      const orig = proto[name];
      if (name === 'constructor' || typeof orig !== 'function') continue;
      proto[name] = function (...args) { window.__drkMarket = this; return orig.apply(this, args); };
    }
    proto.__drkBotHook = true;
  }
  if (live()) return 'ok';
  const nav = document.querySelector('button.nav-item[data-nav=market]');
  if (!nav) return 'sem botao do Marketplace';
  nav.click();
  const t0 = Date.now();
  while (!live() && Date.now() - t0 < 8000) await new Promise(r => setTimeout(r, 200));
  await new Promise(r => setTimeout(r, 500));
  document.querySelectorAll('.tibia-window-controls button, .workspace-window button[title=Fechar]').forEach(b => {
    if (b.getBoundingClientRect().width > 0 && /Fechar|×/.test((b.title || '') + (b.getAttribute('aria-label') || '') + b.innerText)) b.click();
  });
  return live() ? 'ok' : 'nao capturou o Marketplace';
}"""

GET_JS = r"""async (path) => {
  const r = await fetch(path, {credentials: 'include', headers: {Accept: 'application/json'}});
  const text = await r.text();
  let body = null; try { body = JSON.parse(text); } catch (e) {}
  return {status: r.status, body, text: body ? '' : text.slice(0, 200)};
}"""

MUTATE_JS = r"""async ([path, body]) => {
  const m = window.__drkMarket;
  if (!m || !m.enabled()) return {error: 'marketplace indisponivel'};
  if (m.busy) return {error: 'marketplace ocupado'};
  body = Object.assign({}, body, {deviceId: m.client.deviceId, clientBuild: m.client.clientBuild});
  try {
    const p = await m.authoritativeMutation(path, body);
    if (!p) return {error: 'sem resposta (ocupado)'};
    return {ok: !!p.ok, trade: p.trade || null, delivery: p.delivery || null, claimed: p.claimed || null,
            wallet: p.wallet || null, replayed: !!p.replayed};
  } catch (e) {
    return {error: String(e && e.message || e)};
  }
}"""


# Fluxo ao vivo do mercado (o mesmo EventSource que a tela do jogo usa): cada mudança vira um evento 'market'
# {"type": "market_order_filled"|..., "orderId", "marketKey": "item:<id>:<variante>", "at"}. Os eventos ficam num buffer
# da pagina e o bot so' esvazia o buffer (leitura local, sem ir ao servidor).
STREAM_JS = r"""() => {
  const s = window.__drkStream;
  if (s && s.readyState !== 2) return s.readyState === 1 ? 'aberto' : 'conectando';
  window.__drkEvents = window.__drkEvents || [];
  const es = new EventSource('/api/v1/market/events', {withCredentials: true});
  es.addEventListener('market', (e) => {
    let data = null; try { data = JSON.parse(e.data); } catch (err) { data = {raw: String(e.data).slice(0, 200)}; }
    window.__drkEvents.push(data);
    if (window.__drkEvents.length > 500) window.__drkEvents.splice(0, window.__drkEvents.length - 500);
  });
  window.__drkStream = es;
  return 'novo';
}"""

DRAIN_JS = r"""() => { const out = window.__drkEvents || []; window.__drkEvents = []; return out; }"""


def item_id_of(event):
    """'item:2195:abc' -> '2195' (None pra Drako Coin e afins)."""
    key = (event or {}).get("marketKey") or ""
    parts = key.split(":")
    return parts[1] if len(parts) >= 2 and parts[0] == "item" else None


class MarketError(RuntimeError):
    pass


class MarketApi:
    """Leitura e escrita no Marketplace pela pagina do jogo (Playwright Page)."""

    def __init__(self, page):
        self.page = page

    # ------------------------------------------------------------ leitura
    def _get(self, path):
        res = self.page.evaluate(GET_JS, path)
        if res["status"] == 401:
            raise MarketError("Marketplace pede login (aba deslogada)")
        if res["status"] != 200 or not res["body"] or res["body"].get("ok") is False:
            raise MarketError(f"{path}: HTTP {res['status']} {res.get('text') or (res['body'] or {}).get('message', '')}")
        return res["body"]

    def items(self, category=None):
        """Todos os itens (ou de uma categoria), com lowestSell/highestBuy/quantidades."""
        out, page = [], 1
        while page <= 30:
            query = f"page={page}&limit=100&sort=volume"
            if category:
                query += "&category=" + category.replace(" ", "%20")
            body = self._get(f"/api/v1/market/items?{query}")
            out.extend(body.get("items") or [])
            if not body.get("hasMore"):
                break
            page += 1
        return out

    def search(self, name):
        """Item do Market pelo nome exato (busca 'search='); None se nao achar."""
        query = name.replace(" ", "%20").replace("'", "%27")
        for item in self._get(f"/api/v1/market/items?page=1&limit=20&search={query}").get("items") or []:
            if (item.get("displayName") or item.get("name") or "").casefold() == name.casefold():
                return item
        return None

    def detail(self, item_id):
        """{item, sellOffers, buyOffers, statistics}"""
        return self._get(f"/api/v1/market/items/{item_id}")

    def overview(self):
        return self._get("/api/v1/market/overview")

    def assets(self):
        """{nome_minusculo: quantidade} dos itens do usuario (banco + inventario), via me/assets."""
        out = {}
        for asset in self._get("/api/v1/market/me/assets").get("assets") or []:
            key = (asset.get("name") or asset.get("displayName") or "").casefold()
            try:
                out[key] = out.get(key, 0) + int(float(asset.get("quantity") or 0))
            except (TypeError, ValueError):
                pass
        return out

    def deliveries(self):
        return self._get("/api/v1/market/me/deliveries").get("deliveries") or []

    def stream(self):
        """Liga (ou mantem) o fluxo ao vivo; devolve 'novo' / 'aberto' / 'conectando'."""
        return self.page.evaluate(STREAM_JS)

    def events(self):
        """Eventos recebidos desde a ultima chamada."""
        return self.page.evaluate(DRAIN_JS) or []

    # ------------------------------------------------------------ escrita (fluxo seguro do jogo)
    def ensure(self):
        status = self.page.evaluate(HOOK_JS)
        if status != "ok":
            raise MarketError(status)

    def _mutate(self, path, body):
        self.ensure()
        res = self.page.evaluate(MUTATE_JS, [path, body])
        if res.get("error"):
            raise MarketError(res["error"])
        return res

    def buy(self, offer, quantity):
        """Aceita uma oferta de VENDA (compra). offer = item de sellOffers (id, version)."""
        return self._mutate(f"/api/v1/market/orders/{offer['id']}/accept",
                            {"quantity": str(int(quantity)), "instanceId": None, "expectedVersion": offer["version"]})

    def claim(self, delivery_id):
        """Resgata uma entrega da Caixa do Mercado (vai pro Banco)."""
        return self._mutate(f"/api/v1/market/me/deliveries/{delivery_id}/claim", {})
