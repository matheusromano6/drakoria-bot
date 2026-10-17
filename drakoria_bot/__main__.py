"""python -m drakoria_bot [--status]

  --status   le a pagina do Drakoria e mostra o estado (nao faz nada no jogo)
"""
import argparse
import os
import sys

from . import VERSION, config
from . import hunts as H
from .idledeck import Pool
from .paths import app_dir

ROOT = app_dir()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="drakoria_bot")
    ap.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    ap.add_argument("--status", action="store_true", help="so' le e mostra o estado")
    args = ap.parse_args(argv)
    if not args.status:
        from .gui import main as gui_main
        gui_main()
        return 0
    cfg = config.load(args.config)
    pool = Pool(cfg["cdp_url"], print)
    pool.open(launch=False)
    try:
        hunts = H.load_hunts()
        for acc in pool.refresh():
            st = acc.read()
            print(f"drakoria_bot {VERSION} | {st.phase} | caça {H.identify(st.tracker, hunts) or st.dest or '-'} "
                  f"{st.difficulty} | ouro {st.gold} | loot {st.loot_items} | premium {st.premium} | reserva {st.reserve}")
            for m in st.members:
                print(f"  - {m.name} {m.role} lv {m.level} ({m.xp_pct}%) hp {m.hp}/{m.hp_max}")
        return 0
    finally:
        pool.close()


if __name__ == "__main__":
    sys.exit(main())
