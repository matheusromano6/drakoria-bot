"""Historico do Marketplace em SQLite (market.db ao lado do .exe): fotos de preço, diario do servidor, compras e alertas.
Uma conexao por chamada (o bot e a interface rodam em threads diferentes)."""
import contextlib
import datetime
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshot (ts REAL, item_id TEXT, name TEXT, lowest_sell REAL, sell_qty INTEGER,
    highest_buy REAL, fair REAL, discount REAL, quality TEXT);
CREATE INDEX IF NOT EXISTS snapshot_item ON snapshot(item_id, ts);
CREATE TABLE IF NOT EXISTS daily (item_id TEXT, day TEXT, vwap REAL, minimum REAL, maximum REAL, quantity REAL,
    trades INTEGER, PRIMARY KEY (item_id, day));
CREATE TABLE IF NOT EXISTS purchase (ts REAL, item_id TEXT, name TEXT, quantity INTEGER, price REAL, total REAL,
    offer_id TEXT, delivery_id TEXT, auto INTEGER);
CREATE TABLE IF NOT EXISTS alert (ts REAL, item_id TEXT, offer_id TEXT, price REAL, quality TEXT);
"""


class Store:
    def __init__(self, path, clock=time.time):
        self.path = path
        self.clock = clock
        with self._db() as db:
            db.executescript(SCHEMA)

    @contextlib.contextmanager
    def _db(self):
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            with conn:                     # commit/rollback
                yield conn
        finally:
            conn.close()

    def _day_start(self):
        now = datetime.datetime.fromtimestamp(self.clock())
        return datetime.datetime(now.year, now.month, now.day).timestamp()

    def save_evaluation(self, ev, detail):
        with self._db() as db:
            db.execute("INSERT INTO snapshot VALUES (?,?,?,?,?,?,?,?,?)",
                       (self.clock(), ev.item_id, ev.name, ev.lowest_sell, ev.sell_qty, ev.highest_buy, ev.fair,
                        ev.discount, ev.quality))
            for d in (detail.get("statistics") or {}).get("daily") or []:
                db.execute("INSERT OR REPLACE INTO daily VALUES (?,?,?,?,?,?,?)",
                           (ev.item_id, (d.get("day") or "")[:10], float(d.get("vwap_price_gold") or 0),
                            float(d.get("minimum_price_gold") or 0), float(d.get("maximum_price_gold") or 0),
                            float(d.get("quantity_traded") or 0), int(d.get("trades_count") or 0)))

    def add_purchase(self, item_id, name, quantity, price, offer_id, delivery_id, auto):
        with self._db() as db:
            db.execute("INSERT INTO purchase VALUES (?,?,?,?,?,?,?,?,?)",
                       (self.clock(), item_id, name, quantity, price, quantity * price, offer_id, delivery_id, int(auto)))

    def spent_today(self):
        with self._db() as db:
            row = db.execute("SELECT COALESCE(SUM(total), 0) FROM purchase WHERE auto = 1 AND ts >= ?",
                             (self._day_start(),)).fetchone()
        return row[0]

    def bought(self, item_id):
        """Unidades compradas pelo bot (automatico) desse item, em todo o historico."""
        with self._db() as db:
            row = db.execute("SELECT COALESCE(SUM(quantity), 0) FROM purchase WHERE auto = 1 AND item_id = ?",
                             (str(item_id),)).fetchone()
        return int(row[0])

    def purchases(self, limit=50):
        with self._db() as db:
            return db.execute("SELECT ts, name, quantity, price, total, auto FROM purchase ORDER BY ts DESC LIMIT ?",
                              (limit,)).fetchall()

    def should_alert(self, item_id, offer_id, price, quality):
        """Alerta 1x por oferta/preço/qualidade (a mesma oferta parada nao repete o aviso)."""
        with self._db() as db:
            seen = db.execute("SELECT 1 FROM alert WHERE offer_id = ? AND price = ? AND quality = ?",
                              (offer_id, price, quality)).fetchone()
            if seen:
                return False
            db.execute("INSERT INTO alert VALUES (?,?,?,?,?)", (self.clock(), str(item_id), offer_id, price, quality))
            return True

    def history(self, item_id, limit=200):
        with self._db() as db:
            return db.execute("SELECT ts, lowest_sell, sell_qty, fair FROM snapshot WHERE item_id = ? ORDER BY ts DESC LIMIT ?",
                              (str(item_id), limit)).fetchall()
