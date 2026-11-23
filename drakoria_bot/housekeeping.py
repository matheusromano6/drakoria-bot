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


def spent_today(folder, clock=time.time):
    """{tipo: gold} dos gastos automaticos de hoje (logs/gastos_AAAA-MM-DD.jsonl)."""
    day = datetime.datetime.fromtimestamp(clock()).strftime("%Y-%m-%d")
    path = os.path.join(folder, f"gastos_{day}.jsonl")
    totals = {}
    if not os.path.exists(path):
        return totals
    try:
        with open(path, encoding="utf-8") as file:
            for line in file:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                totals[rec.get("tipo", "outros")] = totals.get(rec.get("tipo", "outros"), 0) + int(rec.get("gold", 0))
    except OSError:
        pass
    return totals


# ---------------------------------------------------------------- v1.17: relatorios, CSV, backup, diagnostico
def csv_row(folder, name, xp, profit, clock=time.time):
    """Uma linha por conta a cada 10 min: logs/xp_AAAA-MM-DD.csv (XP/h e lucro/h do dia, pra comparar a evolucao)."""
    try:
        os.makedirs(folder, exist_ok=True)
        now = datetime.datetime.fromtimestamp(clock())
        path = os.path.join(folder, f"xp_{now.strftime('%Y-%m-%d')}.csv")
        new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8") as file:
            if new:
                file.write("hora;conta;xp_hora;lucro_hora\n")
            file.write(f"{now.strftime('%H:%M')};{name};{xp or ''};{profit or ''}\n")
    except OSError:
        pass


def weekly_report(folder, memory, clock=time.time):
    """Relatorio de segunda-feira (1x por semana): gold gasto, bosses feitos e warzones. Grava logs/relatorio_AAAA-MM-DD.txt."""
    now = datetime.datetime.fromtimestamp(clock())
    if now.weekday() != 0 or (memory and memory.get("report_day") == now.date().isoformat()):
        return None
    totals = {}
    for offset in range(7):
        day = (now - datetime.timedelta(days=offset)).strftime("%Y-%m-%d")
        try:
            with open(os.path.join(folder, f"gastos_{day}.jsonl"), encoding="utf-8") as file:
                for line in file:
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    totals[rec.get("tipo", "outros")] = totals.get(rec.get("tipo", "outros"), 0) + int(rec.get("gold", 0))
        except OSError:
            pass
    bosses = len(memory.get("boss_days") or {}) if memory else 0
    lines = [f"Relatório semanal ({now.strftime('%d/%m/%Y')})", "Gold gasto em compras automáticas (7 dias):"]
    lines += [f"  {k}: {v:,}".replace(",", ".") for k, v in totals.items()] or ["  nada"]
    lines.append(f"Contas com boss feito hoje: {bosses}")
    try:
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, f"relatorio_{now.strftime('%Y-%m-%d')}.txt"), "w", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
    except OSError:
        pass
    if memory:
        memory.set("report_day", now.date().isoformat())
    return lines


def backup_state(root, dst_folder, names=("config.json", "memory.json")):
    """Copia config e memoria antes de trocar a versao (se der problema, da pra voltar)."""
    os.makedirs(dst_folder, exist_ok=True)
    copied = []
    for name in names:
        src = os.path.join(root, name)
        if os.path.exists(src):
            with open(src, "rb") as a, open(os.path.join(dst_folder, name), "wb") as b:
                b.write(a.read())
            copied.append(name)
    return copied


def diagnostic(version, cfg, memory_data, log_lines):
    """Texto pra colar no suporte: versao, configuracao SEM credenciais, estado e as ultimas linhas do log."""
    safe = {k: v for k, v in (cfg or {}).items() if k not in ("credentials", "login")}
    lines = [f"DRAKORIA BOT v{version}", f"Gerado: {datetime.datetime.now():%d/%m/%Y %H:%M}", "",
             "Configuração (sem senhas):", json.dumps(safe, ensure_ascii=False, indent=1)[:4000], "",
             "Estado salvo:", json.dumps({k: v for k, v in (memory_data or {}).items() if k != "party"},
                                         ensure_ascii=False)[:2000], "", "Últimas linhas do log:"]
    lines += list(log_lines)[-200:]
    return "\n".join(lines)
