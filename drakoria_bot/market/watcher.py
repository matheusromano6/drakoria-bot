"""Ciclo do Marketplace: a cada 'interval_minutes' le as categorias observadas, avalia os itens com oferta,
grava o historico, alerta oportunidades e compra o que o usuario permitiu.

Compra automatica so' com TUDO ligado: a chave geral 'auto_buy' + a regra do item (buy, max_price, quantity).
Limites: quantidade total por item, orçamento diario (so' compras do bot), reserva de ouro que nunca e' gasta,
e preço maximo (o do usuario; sem ele, 20% abaixo do preço justo). Compra pela oferta mais barata primeiro e
resgata a entrega pro Banco. Qualquer erro para as compras desse ciclo.
"""
from . import analysis as A
from .api import MarketApi, MarketError


def rule_for(cfg, name):
    return dict((cfg.get("rules") or {}).get((name or "").casefold()) or {})


class MarketWatcher:
    def __init__(self, cfg, store, log=print, notify=None, clock=None, api_factory=MarketApi):
        self.cfg = cfg                     # o dict 'market' da config (o mesmo da interface)
        self.store = store
        self.log = log
        self.notify = notify or (lambda title, text: None)
        self.clock = clock
        self.api_factory = api_factory
        self.last_run = None
        self.board = {}                    # nome_minusculo -> Evaluation (ou resumo da lista)
        self.listing = []                  # itens da(s) categoria(s): [{id, name, lowest_sell, sell_qty}]
        self.error = ""

    def due(self, now):
        return self.last_run is None or now - self.last_run >= self.cfg.get("interval_minutes", 5) * 60

    def tick(self, page, now):
        if not self.cfg.get("enabled") or not self.due(now):
            return False
        self.last_run = now
        api = self.api_factory(page)
        try:
            self._scan(api)
            self.error = ""
        except MarketError as error:
            self.error = str(error)
            self.log(f"market: {error}")
        return True

    def _scan(self, api):
        listing = []
        for category in self.cfg.get("categories") or []:
            listing.extend(api.items(category))
        self.listing = [{"id": str(i["id"]), "name": i.get("displayName") or i.get("name"), "category": i.get("category"),
                         "lowest_sell": A._num(i.get("lowestSell")), "sell_qty": int(A._num(i.get("sellQuantity")) or 0),
                         "highest_buy": A._num(i.get("highestBuy"))} for i in listing]
        wallet = None
        for row in self.listing:
            rule = rule_for(self.cfg, row["name"])
            if not row["sell_qty"] and not rule.get("watch"):
                continue
            detail = api.detail(row["id"])
            ev = A.evaluate(detail, self.cfg)
            self.store.save_evaluation(ev, detail)
            self.board[ev.name.casefold()] = ev
            self._alert(ev, rule)
            if self.cfg.get("auto_buy") and rule.get("buy") and ev.offers:
                if wallet is None:
                    wallet = A._num((api.overview().get("wallet") or {}).get("goldSpendable")) or 0
                wallet = self._buy(api, ev, rule, wallet)

    def _alert(self, ev, rule):
        if not ev.quality or not ev.offers:
            return
        if self.cfg.get("alerts_watched_only") and not rule.get("watch"):
            return
        if A.QUALITIES.index(ev.quality) < A.QUALITIES.index(self.cfg.get("alert_min_quality", "boa")):
            return
        offer = ev.offers[0]
        if not self.store.should_alert(ev.item_id, offer["id"], ev.lowest_sell, ev.quality):
            return
        text = (f"{ev.name}: {int(ev.lowest_sell):,} (justo {int(ev.fair):,}, -{ev.discount:.0%}) · "
                f"{ev.sell_qty} à venda").replace(",", ".")
        self.log(f"market: oportunidade {ev.quality.upper()} - {text}")
        self.notify(f"Oportunidade {ev.quality}", text)

    def _buy(self, api, ev, rule, wallet):
        want = int(rule.get("quantity") or 0) - self.store.bought(ev.item_id)
        if want <= 0:
            return wallet
        max_price = int(rule.get("max_price") or 0) or ev.suggested_max
        if not max_price:
            return wallet
        budget_left = max(0, self.cfg.get("daily_budget", 0) - self.store.spent_today())
        plan = A.buy_plan(ev, max_price, want, wallet, self.cfg.get("reserve_gold", 0), budget_left)
        for offer, quantity in plan:
            price = A._num(offer["unitPriceGold"])
            try:
                res = api.buy(offer, quantity)
            except MarketError as error:
                self.log(f"market: compra de {ev.name} falhou: {error}")
                return wallet
            delivery = (res.get("delivery") or {}).get("id")
            self.store.add_purchase(ev.item_id, ev.name, quantity, price, offer["id"], delivery, auto=True)
            wallet -= quantity * price
            msg = f"comprou {quantity}x {ev.name} a {int(price):,} (total {int(quantity * price):,})".replace(",", ".")
            self.log(f"market: {msg}")
            self.notify("Compra no Marketplace", msg)
            if delivery and self.cfg.get("claim", True):
                try:
                    api.claim(delivery)
                except MarketError as error:
                    self.log(f"market: resgatar a entrega de {ev.name} falhou: {error} (fica na Caixa do Mercado)")
        return wallet
