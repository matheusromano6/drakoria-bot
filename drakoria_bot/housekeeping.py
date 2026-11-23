"""Rotinas de manutencao: limpeza de logs antigos, historico de gastos (gold) e checagem da versao do jogo."""
import datetime
import json
import os
import re
import time

LOG_KEEP_DAYS = 14


def prune_logs(folder, days=LOG_KEEP_DAYS, now=None):
    """Apaga logs com mais de 'days' dias (nome drakoria_AAAA-MM-DD.log / gastos_AAAA-MM-DD.jsonl). Devolve quantos."""
    if not os.path.isdir(folder):
        return 0
    limit = (now or time.time()) - days * 86400
    removed = 0
    for name in os.listdir(folder):
        if not re.match(r"(drakoria|gastos)_\d{4}-\d{2}-\d{2}\.(log|jsonl)$", name):
            continue
        path = os.path.join(folder, name)
        try:
            if os.path.getmtime(path) < limit:
                os.remove(path)
                removed += 1
        except OSError:
            pass
    return removed


def spend(folder, kind, gold, detail, clock=time.time):
    """Anota um gasto de gold (compra de exercise, Atlas...) em logs/gastos_AAAA-MM-DD.jsonl."""
    try:
        os.makedirs(folder, exist_ok=True)
        day = datetime.datetime.fromtimestamp(clock()).strftime("%Y-%m-%d")
        record = {"quando": datetime.datetime.fromtimestamp(clock()).strftime("%H:%M:%S"), "tipo": kind,
                  "gold": int(gold), "detalhe": detail}
        with open(os.path.join(folder, f"gastos_{day}.jsonl"), "a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def check_build(page, memory, log):
    """Versao do jogo (build do app.js). Se mudou desde a ultima vez, avisa: os seletores podem ter quebrado."""
    try:
        src = page.evaluate("() => (document.querySelector('script[src*=\"/js/app.js\"]') || {}).src || ''")
    except Exception:
        return None
    match = re.search(r"build=([^&]+)", src or "")
    if not match:
        return None
    build = match.group(1)
    previous = memory.get("game_build") if memory else None
    if previous and previous != build:
        log(f"o jogo mudou de versão ({previous} -> {build}): se algo parar de funcionar, reporte")
    if memory and previous != build:
        memory.set("game_build", build)
    return build
