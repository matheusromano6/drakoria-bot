"""Analise de preço (puro, sem navegador).

Preço justo = o MENOR entre o VWAP da janela (30 dias) e o VWAP recente (ultimo terço dos dias, minimo 1):
nao persegue alta e protege na queda (licao do market do Baiak: 'parece barato' com preço caindo engana).
Dias com VWAP fora de 1/3..3x a mediana sao descartados (visto ao vivo 20/10: Protective Charm vendida a 1 de ouro,
transferencia entre contas, derrubava a media do servidor de ~39k pra 27.9k). Por isso a media e' recalculada do
diario limpo; a do servidor (que inclui o lixo) so' e' usada sem diario.
Desconto = 1 - menor oferta / preço justo. Qualidade: boa / muito boa / excelente pelos limites da config;
preço caindo mais que 'trend_down' derruba um nivel. Sem negocios no historico -> nao da pra julgar (sem qualidade).
"""
from dataclasses import dataclass, field

QUALITIES = ["boa", "muito boa", "excelente"]


def _num(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


@dataclass
class Evaluation:
    item_id: str
    name: str
    lowest_sell: float = None
    sell_qty: int = 0
    highest_buy: float = None
    vwap_window: float = None        # VWAP da janela do servidor (30 dias)
    vwap_recent: float = None        # VWAP dos ultimos dias
    fair: float = None
    discount: float = None           # 0.25 = 25% abaixo do justo
    trend: float = None              # -0.2 = recente 20% abaixo do resto da janela
    per_day: float = None            # unidades negociadas por dia (liquidez)
    trades: int = 0
    quality: str = None
    offers: list = field(default_factory=list)   # ofertas de venda ativas (de outros), da mais barata

    @property
    def suggested_max(self):
        """Preço maximo sugerido pra compra automatica: 20% abaixo do justo."""
        return int(self.fair * 0.8) if self.fair else None


def clean_daily(daily, band=3.0):
    """Dias com VWAP dentro de [mediana/band, mediana*band] (tira negocios de 1 de ouro e afins)."""
    prices = sorted(_num(d.get("vwap_price_gold")) or 0 for d in daily if _num(d.get("quantity_traded")))
    prices = [p for p in prices if p > 0]
    if not prices:
        return []
    mid = len(prices) // 2
    median = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2
    return [d for d in daily if _num(d.get("quantity_traded")) and
            median / band <= (_num(d.get("vwap_price_gold")) or 0) <= median * band]


def evaluate(detail, cfg):
    """detail = resposta de /market/items/<id>. cfg = config['market'] (limites de qualidade)."""
    item = detail.get("item") or {}
    stats = detail.get("statistics") or {}
    daily = clean_daily(sorted(stats.get("daily") or [], key=lambda d: d.get("day") or ""))
    offers = sorted((o for o in detail.get("sellOffers") or []
                     if not o.get("mine") and o.get("status") in ("ACTIVE", "PARTIAL") and _num(o.get("remainingQuantity"))),
                    key=lambda o: _num(o.get("unitPriceGold")) or 0)
    ev = Evaluation(item_id=str(item.get("id", "")), name=item.get("displayName") or item.get("name") or "?", offers=offers)
    ev.lowest_sell = _num(offers[0]["unitPriceGold"]) if offers else _num(stats.get("lowestSell"))
    ev.sell_qty = int(sum(_num(o.get("remainingQuantity")) or 0 for o in offers))
    ev.highest_buy = _num(stats.get("highestBuy"))
    trades = stats.get("trades") or {}
    ev.trades = int(trades.get("trades") or 0)
    ev.vwap_window = _weighted(daily) if daily else _num(trades.get("vwap"))

    recent_days = max(1, len(daily) // 3)
    recent = daily[-recent_days:]
    older = daily[:-recent_days]
    ev.vwap_recent = _weighted(recent)
    older_vwap = _weighted(older)
    if ev.vwap_recent and older_vwap:
        ev.trend = ev.vwap_recent / older_vwap - 1
    if daily:
        qty = sum(_num(d.get("quantity_traded")) or 0 for d in daily)
        ev.per_day = qty / max(1, len(daily))

    candidates = [v for v in (ev.vwap_window, ev.vwap_recent) if v]
    ev.fair = min(candidates) if candidates else None
    if ev.fair and ev.lowest_sell:
        ev.discount = 1 - ev.lowest_sell / ev.fair
        ev.quality = quality(ev.discount, ev.trend, cfg)
    return ev


def _weighted(days):
    qty = sum(_num(d.get("quantity_traded")) or 0 for d in days)
    if not qty:
        return None
    return sum((_num(d.get("vwap_price_gold")) or 0) * (_num(d.get("quantity_traded")) or 0) for d in days) / qty


def quality(discount, trend, cfg):
    limits = [cfg.get("good", 0.15), cfg.get("great", 0.25), cfg.get("excellent", 0.40)]
    level = sum(1 for limit in limits if discount is not None and discount >= limit) - 1
    if level >= 0 and trend is not None and trend <= -cfg.get("trend_down", 0.10):
        level -= 1
    return QUALITIES[level] if level >= 0 else None


def buy_plan(ev, max_price, want, gold_available, reserve=0, budget_left=None):
    """[(oferta, quantidade)] das ofertas mais baratas <= max_price, ate 'want' unidades, sem passar do ouro
    (menos a reserva) nem do orçamento do dia."""
    plan, left = [], int(want)
    money = (gold_available or 0) - (reserve or 0)
    if budget_left is not None:
        money = min(money, budget_left)
    for offer in ev.offers:
        price = _num(offer.get("unitPriceGold")) or 0
        if left <= 0 or price <= 0 or price > max_price:
            break
        can = min(left, int(_num(offer.get("remainingQuantity")) or 0), int(money // price))
        if can <= 0:
            break
        plan.append((offer, can))
        left -= can
        money -= can * price
    return plan
