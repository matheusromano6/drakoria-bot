"""Ciclo do Marketplace: a cada 'interval_minutes' le as categorias observadas, avalia os itens com oferta,
grava o historico, alerta oportunidades e compra o que o usuario permitiu.

Compra automatica so' com TUDO ligado: a chave geral 'auto_buy' + a regra do item (buy, max_price, quantity).
Limites: quantidade total por item, orçamento diario (so' compras do bot), reserva de ouro que nunca e' gasta,
e preço maximo (o do usuario; sem ele, 20% abaixo do preço justo). Compra pela oferta mais barata primeiro e
resgata a entrega pro Banco. Qualquer erro para as compras desse ciclo.
"""
from . import analysis as A
from . import imbuements as I
from .api import MarketApi, MarketError, item_id_of


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
        self.owned = {}                    # nome_minusculo -> quantidade que o usuario tem (me/assets)
        self.error = ""
        try:
            self.imb = I.load()
        except Exception:
            self.imb = {"imbuements": [], "rules": {}}

    def watched_ids(self):
        """ids dos itens que interessam agora: com regra (observar/comprar) ou material de imbuement observado."""
        names = set(I.watched_materials(self.cfg, self.imb))
        names.update(k for k, r in (self.cfg.get("rules") or {}).items() if r.get("watch") or r.get("buy"))
        return {row["id"]: row["name"] for row in self.listing if (row["name"] or "").casefold() in names}

    def react(self, page, now):
        """Chamado a cada ~1 s: esvazia os eventos ao vivo e reavalia NA HORA so' os itens observados que mudaram."""
        if not self.cfg.get("enabled") or not self.cfg.get("live", True) or not self.listing:
            return 0
        api = self.api_factory(page)
        try:
            state = api.stream()
            if state == "novo":
                self.log("market: acompanhando o mercado ao vivo")
            events = api.events()
        except Exception as error:
            self.error = f"ao vivo: {error}"
            return 0
        if not events:
            return 0
        self.events_seen = getattr(self, "events_seen", 0) + len(events)
        watched = self.watched_ids()
        ids = []
        for event in events:
            item = item_id_of(event)
            if item in watched and item not in ids:
                ids.append(item)
        if not ids:
            return 0
        try:
            if any(r.get("buy") for r in (self.cfg.get("imbuements") or {}).values()):
                self.owned = api.assets()
            wallet = None
            for item in ids:
                detail = api.detail(item)
                ev = A.evaluate(detail, self.cfg)
                self.store.save_evaluation(ev, detail)
                before = self.board.get(ev.name.casefold())
                self.board[ev.name.casefold()] = ev
                if (before.lowest_sell if before else None) != ev.lowest_sell or (before.sell_qty if before else 0) != ev.sell_qty:
                    price = f"{int(ev.lowest_sell):,}".replace(",", ".") if ev.lowest_sell else "sem oferta"
                    fair = f" (justo {int(ev.fair):,})".replace(",", ".") if ev.fair else " (sem histórico de preço)"
                    self.log(f"market ao vivo: {ev.name}: menor {price}, {ev.sell_qty} à venda{fair}")
                rule = rule_for(self.cfg, ev.name)
                self._alert(ev, rule)
                if self.cfg.get("auto_buy") and rule.get("buy") and ev.offers:
                    if wallet is None:
                        wallet = A._num((api.overview().get("wallet") or {}).get("goldSpendable")) or 0
                    wallet = self._buy(api, ev, rule, wallet)
            if self.cfg.get("auto_buy"):
                self._buy_imbuements(api, wallet)
            self.last_live = now
        except MarketError as error:
            self.error = str(error)
            self.log(f"market (ao vivo): {error}")
        return len(ids)

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
        watched = I.watched_materials(self.cfg, self.imb)
        if watched or any(r.get("buy") for r in (self.cfg.get("imbuements") or {}).values()):
            self.owned = api.assets()
        for row in self.listing:
            rule = rule_for(self.cfg, row["name"])
            if not row["sell_qty"] and not rule.get("watch") and (row["name"] or "").casefold() not in watched:
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
        if self.cfg.get("auto_buy"):
            self._buy_imbuements(api, wallet)

    def plans(self):
        """Planos dos imbuements observados (pra interface): {id: Plan}."""
        out = {}
        for definition in self.imb["imbuements"]:
            rule = (self.cfg.get("imbuements") or {}).get(definition["id"]) or {}
            if rule.get("watch"):
                out[definition["id"]] = I.plan(definition, rule.get("tier", 0), rule.get("uses", 1), self.board,
                                               self.owned, self.imb.get("rules"))
        return out

    def _buy_imbuements(self, api, wallet):
        """Completa os materiais que faltam dos imbuements com compra ligada, pagando ate pay_pct% do preço justo."""
        for definition in self.imb["imbuements"]:
            rule = (self.cfg.get("imbuements") or {}).get(definition["id"]) or {}
            if not (rule.get("watch") and rule.get("buy")):
                continue
            p = I.plan(definition, rule.get("tier", 0), rule.get("uses", 1), self.board, self.owned, self.imb.get("rules"))
            for line in p.lines:
                if line.missing <= 0 or not line.ev or not line.ev.offers:
                    continue
                if not line.fair:
                    continue                    # sem historico nao da pra saber se e' barato
                max_price = int(line.fair * float(rule.get("pay_pct", 90)) / 100)
                if wallet is None:
                    wallet = A._num((api.overview().get("wallet") or {}).get("goldSpendable")) or 0
                before = self.store.bought(line.ev.item_id)
                wallet = self._buy_up_to(api, line.ev, max_price, line.missing, wallet,
                                         f"{definition['name']} {I.TIER_NAMES[p.tier]}")
                got = self.store.bought(line.ev.item_id) - before
                self.owned[line.name.casefold()] = self.owned.get(line.name.casefold(), 0) + got
        return wallet

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
        gold = lambda v: f"{int(v):,}".replace(",", ".")
        text = f"{ev.name}: {gold(ev.lowest_sell)} (justo {gold(ev.fair)}, -{ev.discount:.0%}) · {ev.sell_qty} à venda"
        self.log(f"market: oportunidade {ev.quality.upper()} - {text}")
        self.notify(f"Oportunidade {ev.quality}", text)

    def _buy(self, api, ev, rule, wallet):
        want = int(rule.get("quantity") or 0) - self.store.bought(ev.item_id)
        if want <= 0:
            return wallet
        max_price = int(rule.get("max_price") or 0) or ev.suggested_max
        if not max_price:
            return wallet
        return self._buy_up_to(api, ev, max_price, want, wallet, "regra do item")

    def _buy_up_to(self, api, ev, max_price, want, wallet, reason):
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
            msg = (f"comprou {quantity}x {ev.name} a {int(price):,} (total {int(quantity * price):,}) "
                   f"- {reason}").replace(",", ".")
            self.log(f"market: {msg}")
            self.notify("Compra no Marketplace", msg)
            if delivery and self.cfg.get("claim", True):
                try:
                    api.claim(delivery)
                except MarketError as error:
                    self.log(f"market: resgatar a entrega de {ev.name} falhou: {error} (fica na Caixa do Mercado)")
        return wallet
