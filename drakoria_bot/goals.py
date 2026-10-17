"""Objetivos escolhidos pelo usuario (17/10/2026): tasks de produto e criaturas do bestiary, em fila.
Prioridade da caça: task ativa -> proxima criatura do bestiary -> caça da aba Regras.
A party pode ir ate 'level_over' levels acima do level recomendado da caça (4 personagens aguentam mais)."""
import json
import os
import re

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def load_tasks():
    with open(os.path.join(DATA, "tasks.json"), encoding="utf-8") as file:
        return json.load(file)


def hunts_for(creature, hunts):
    """Caças que tem a criatura, da mais facil pra mais dificil."""
    key = (creature or "").casefold()
    return sorted((h for h in hunts if key in {c.casefold() for c in h["creatures"]}), key=lambda h: h["level"])


def reachable_hunt(creature, hunts, party_level, level_over):
    """Caça mais facil com a criatura que a party alcança (recomendado <= level + level_over)."""
    for hunt in hunts_for(creature, hunts):
        if hunt["level"] <= party_level + level_over:
            return hunt["name"]
    return None


def doable_tasks(tasks, hunts):
    """Tasks cuja criatura aparece em alguma caça do jogo (as outras o bot nao consegue fazer)."""
    return [t for t in tasks if hunts_for(t["creature"], hunts)]


def parse_tracker_title(title):
    """'Troll: 4 de 250 kills · faltam 246. Abrir a ficha.' -> ('Troll', 4, 250)."""
    m = re.match(r"^([^:]+):\s*([\d.]+)\s*de\s*([\d.]+)", title or "")
    if not m:
        return None
    return m.group(1).strip(), int(m.group(2).replace(".", "")), int(m.group(3).replace(".", ""))


def bestiary_done(creature, progress):
    """progress: {criatura_minusculas: [abates, meta]}; sem dado = nao sabe (nao concluida)."""
    data = progress.get((creature or "").casefold())
    return bool(data and data[1] and data[0] >= data[1])


def next_tasks_to_accept(queue, task_state, active_count, tasks, hunts, party_level, level_over, max_active=2):
    """Nomes das proximas tasks da fila pra aceitar (disponiveis, alcançaveis), ate completar 'max_active'."""
    by_name = {t["name"]: t for t in tasks}
    out = []
    for name in queue:
        if active_count + len(out) >= max_active:
            break
        state = task_state.get(name)
        task = by_name.get(name)
        if state != "available" or not task:
            continue
        if reachable_hunt(task["creature"], hunts, party_level, level_over):
            out.append(name)
    return out


def goal_hunt(active_tasks, bestiary_queue, progress, tasks, hunts, party_level, level_over):
    """(caça, motivo) do objetivo atual, ou (None, '') se nenhum objetivo pode ser feito agora.
    active_tasks: [{'name', 'ready'}] na ordem do jogo."""
    by_name = {t["name"]: t for t in tasks}
    for active in active_tasks:
        task = by_name.get(active["name"])
        if not task or active.get("ready"):
            continue
        hunt = reachable_hunt(task["creature"], hunts, party_level, level_over)
        if hunt:
            return hunt, f"task {task['name']} ({task['creature']})"
    for creature in bestiary_queue:
        if bestiary_done(creature, progress):
            continue
        hunt = reachable_hunt(creature, hunts, party_level, level_over)
        if hunt:
            return hunt, f"bestiary {creature}"
    return None, ""
