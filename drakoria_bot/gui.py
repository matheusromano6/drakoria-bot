"""Interface do bot do Drakoria (CustomTkinter), simples e leve: Painel, Regras, Login, Log.
So' redesenha o que mudou; fechar (X) pergunta se guarda na bandeja ou fecha de vez."""
import datetime
import importlib
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from . import VERSION, browsers, config, goals, hunts, imbuing, updater
from .market import imbuements as imb
from .market.store import Store as MarketStore
from .credentials import Credentials
from .memory import Memory
from .paths import app_dir, resource_dir
from .runner import Runner

ROOT = app_dir()
CONFIG_PATH = os.path.join(ROOT, "config.json")
MEMORY_PATH = os.path.join(ROOT, "memory.json")
BG, PANEL, PANEL_ALT, BORDER = "#0f1216", "#161b21", "#1e252d", "#2b3440"
TEXT, MUTED, ACCENT, ACCENT_HOVER, DANGER, OK = "#e8edf2", "#8c98a4", "#e0a526", "#c48d16", "#f05a4f", "#3fb950"
DARK_TEXT = "#1a1200"
PHASES = {"hunting": "Caçando", "house": "Treinando (house)", "house_idle": "Na house", "city": "Na cidade", "login": "Deslogado",
          "error": "Erro / reconectando", "unknown": "?", "-": "-"}
NO_HUNT = "Nenhuma (só treinar)"
DEFAULT_DIFF = "Padrão"
PREY_MODES = {"budget": "Até X de ouro por dia", "until_found": "Até achar (sem limite diário)"}
AUTO_SELL = {"auto": "Automático (liga se for Premium)", "on": "Sempre ligado", "off": "Desligado (vender pelo bot)"}
MAX_LOG_LINES = 400


def btn(parent, text, command, primary=False, **kw):
    if primary:
        return ctk.CTkButton(parent, text=text, command=command, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                             text_color=DARK_TEXT, **kw)
    return ctk.CTkButton(parent, text=text, command=command, fg_color=PANEL_ALT, hover_color=BORDER, text_color=TEXT, **kw)


class App:
    def __init__(self, root, runner_factory=Runner):
        self.root = root
        root.title(f"DRAKORIA BOT  v{VERSION}")
        root.geometry("960x680")
        root.minsize(760, 560)
        root.configure(fg_color=BG)
        icon = os.path.join(resource_dir(), "icon.ico")
        if os.path.exists(icon):
            try:
                root.iconbitmap(icon)
            except Exception:
                pass
        self.cfg = config.load(CONFIG_PATH)
        self.memory = Memory(MEMORY_PATH)
        self.log_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        self.tray_queue = queue.Queue()
        self.runner = runner_factory(self.cfg, self.log)
        self.tray_icon = None
        self.close_dialog = None
        self.updating = False
        self._last_view = None
        try:
            self.hunt_list = hunts.load_hunts()
            self.task_list = goals.doable_tasks(goals.load_tasks(), self.hunt_list)
        except Exception:
            self.hunt_list, self.task_list = [], []
        self.hunt_names = [h["name"] for h in self.hunt_list]

        self._build_header()
        self.tabs = ctk.CTkTabview(root, fg_color=PANEL, segmented_button_selected_color=ACCENT,
                                   segmented_button_selected_hover_color=ACCENT_HOVER, text_color=DARK_TEXT)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for name in ("Painel", "Regras", "Objetivos", "Imbuements", "Market", "Login", "Log"):
            self.tabs.add(name)
        self._build_panel(self.tabs.tab("Painel"))
        self._build_rules(self.tabs.tab("Regras"))
        self._build_goals(self.tabs.tab("Objetivos"))
        self._build_imbuing(self.tabs.tab("Imbuements"))
        self._build_market(self.tabs.tab("Market"))
        if hasattr(self.runner, "notify"):
            self.runner.notify = self.notify
        self._build_login(self.tabs.tab("Login"))
        self._build_log(self.tabs.tab("Log"))

        root.protocol("WM_DELETE_WINDOW", self.request_close)
        if sys.platform == "win32":
            root.bind("<Unmap>", self._on_unmap)
        root.after(150, self._poll_log)
        root.after(100, self._poll_ui)
        root.after(1000, self._poll_state)
        root.after(300, self._poll_tray)
        root.after(3000, self._startup_update_check)

    # ------------------------------------------------------------------ util
    def log(self, message):
        now = datetime.datetime.now()
        line = f"[{now.strftime('%H:%M:%S')}] {message}"
        self.log_queue.put(line)
        try:
            folder = os.path.join(ROOT, "logs")
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, f"drakoria_{now.strftime('%Y-%m-%d')}.log"), "a", encoding="utf-8") as file:
                file.write(line + "\n")
        except OSError:
            pass

    def save(self):
        config.save(CONFIG_PATH, self.cfg)

    def call_ui(self, fn):
        self.ui_queue.put(fn)

    def _poll_ui(self):
        try:
            while True:
                self.ui_queue.get_nowait()()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_ui)

    def _poll_log(self):
        lines = []
        try:
            while True:
                lines.append(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        if lines:
            for box in (self.log_box, self.mini_log):
                box.configure(state="normal")
                box.insert("end", "\n".join(lines) + "\n")
                limit = MAX_LOG_LINES if box is self.log_box else 6
                count = int(box.index("end-1c").split(".")[0])
                if count > limit:
                    box.delete("1.0", f"{count - limit}.0")
                box.see("end")
                box.configure(state="disabled")
        self.root.after(250, self._poll_log)

    # ---------------------------------------------------------------- header
    def _build_header(self):
        bar = ctk.CTkFrame(self.root, fg_color=PANEL, corner_radius=8)
        bar.pack(fill="x", padx=10, pady=10)
        top = ctk.CTkFrame(bar, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 2))
        ctk.CTkLabel(top, text="DRAKORIA BOT", font=("Segoe UI", 16, "bold"), text_color=ACCENT).pack(side="left")
        self.update_btn = btn(top, "Atualizar", self.start_update, width=80)
        self.update_btn.pack(side="right")
        self.toggle_btn = btn(top, "Iniciar", self.toggle, primary=True, width=80)
        self.toggle_btn.pack(side="right", padx=6)
        self.status = ctk.CTkLabel(bar, text="● Parado", font=("Segoe UI", 12, "bold"), text_color=MUTED, anchor="w")
        self.status.pack(fill="x", padx=10, pady=(0, 8))

    def toggle(self):
        if self.runner.running:
            self.runner.stop()
            self.toggle_btn.configure(text="Iniciar", fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=DARK_TEXT)
            self.status.configure(text="● Parado", text_color=MUTED)
        else:
            self.runner.start()
            self.toggle_btn.configure(text="Parar", fg_color=PANEL_ALT, hover_color=BORDER, text_color=TEXT)
            self.status.configure(text="● Conectando...", text_color=ACCENT)

    # ---------------------------------------------------------------- painel
    def _build_panel(self, tab):
        self.party_box = ctk.CTkFrame(tab, fg_color=PANEL_ALT, corner_radius=6)
        self.party_box.pack(fill="x", padx=4, pady=(4, 6))
        self.member_rows = []
        for _ in range(4):
            row = ctk.CTkFrame(self.party_box, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=3)
            name = ctk.CTkLabel(row, text="-", text_color=TEXT, width=150, anchor="w", font=("Segoe UI", 12, "bold"))
            name.pack(side="left")
            info = ctk.CTkLabel(row, text="", text_color=MUTED, width=80, anchor="w")
            info.pack(side="left")
            bar = ctk.CTkProgressBar(row, width=110, height=8, progress_color=OK, fg_color=BORDER)
            bar.set(0)
            bar.pack(side="right", pady=6)
            self.member_rows.append((name, info, bar))
        self.stats = ctk.CTkLabel(tab, text="", text_color=TEXT, justify="left", anchor="w", font=("Segoe UI", 12))
        self.stats.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(tab, text="Últimos eventos", text_color=MUTED, anchor="w").pack(fill="x", padx=8, pady=(6, 0))
        self.mini_log = ctk.CTkTextbox(tab, height=120, fg_color=BG, text_color=MUTED, font=("Consolas", 10), state="disabled")
        self.mini_log.pack(fill="both", expand=True, padx=4, pady=4)
        self._show_party(self.memory.get("party") or [])

    def _show_party(self, party):
        for i, (name, info, bar) in enumerate(self.member_rows):
            if i < len(party):
                m = party[i]
                name.configure(text=m[0])
                info.configure(text=f"{m[1]}  Lv {m[2]}")
            else:
                name.configure(text="-")
                info.configure(text="")

    def _poll_state(self):
        snap = self.runner.snapshot if self.runner.running else None
        st = snap.get("state") if snap else None
        if st is not None:
            view = (snap["phase"], snap.get("hunt"), snap.get("target"), st.difficulty, st.gold, st.loot_items, st.xp_hour,
                    st.profit_hour, st.reserve, tuple(snap.get("prey") or []), tuple(snap.get("tasks") or []),
                    snap.get("goal"), st.stamina and int(st.stamina * 60),
                    tuple((m.name, m.role, m.level, m.xp_pct, m.hp, m.hp_max) for m in st.members))
            if view != self._last_view:          # so' redesenha o que mudou
                self._last_view = view
                phase = PHASES.get(snap["phase"], snap["phase"])
                where = snap.get("hunt") or ""
                diff = f" ({st.difficulty})" if snap["phase"] == "hunting" and st.difficulty else ""
                color = OK if snap["phase"] == "hunting" else (DANGER if snap["phase"] in ("error", "login") else ACCENT)
                self.status.configure(text=f"● {phase}{' · ' + where if where else ''}{diff}", text_color=color)
                for i, (name, info, bar) in enumerate(self.member_rows):
                    if i < len(st.members):
                        m = st.members[i]
                        name.configure(text=m.name)
                        info.configure(text=f"{m.role}  Lv {m.level} · {m.xp_pct}%")
                        bar.set(m.hp / m.hp_max if m.hp_max else 0)
                loot = "-" if st.loot_items is None else st.loot_items
                stam = "-" if st.stamina is None else f"{int(st.stamina)}h{int(st.stamina % 1 * 60):02d}"
                self.stats.configure(text=(
                    f"Ouro {st.gold}   ·   Loot Pouch {loot}   ·   Stamina {stam}   ·   Reserva offline {st.reserve or '-'}\n"
                    f"XP/h {st.xp_hour or '-'}   ·   Lucro/h {st.profit_hour or '-'}\n"
                    f"Alvo: {snap.get('target') or '-'}   ·   Auto Sell {'Premium' if st.premium else 'Free'}\n"
                    f"Prey: {' · '.join(f'{c} {b} ({t})' for c, b, t in snap.get('prey') or []) or '-'}\n"
                    f"Tasks: {' · '.join(f'{n} {h}/{q}' for n, h, q in snap.get('tasks') or []) or '-'}"))
                self.goal_status.configure(text=f"Objetivo agora: {snap.get('goal') or 'nenhum (caça da aba Regras)'}")
        self._refresh_market()
        self._imbuing_refresh()
        self._imb_render()
        self._refresh_spent()
        self._refresh_task_market()
        self.root.after(1000, self._poll_state)

    # ---------------------------------------------------------------- regras
    def _build_rules(self, tab):
        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.pack(fill="x", padx=8, pady=8)
        grid.columnconfigure(1, weight=1)

        def label(r, text):
            ctk.CTkLabel(grid, text=text, text_color=TEXT, anchor="w").grid(row=r, column=0, sticky="w", pady=6, padx=(0, 10))

        def menu(r, values, current, on_change):
            m = ctk.CTkOptionMenu(grid, values=values, command=on_change, fg_color=PANEL_ALT, button_color=BORDER,
                                  button_hover_color=ACCENT_HOVER, dropdown_fg_color=PANEL_ALT, text_color=TEXT,
                                  dynamic_resizing=False, width=240)
            m.set(current)
            m.grid(row=r, column=1, sticky="ew", pady=6)
            return m

        label(1, "Caça")
        menu(1, [NO_HUNT] + self.hunt_names, self.cfg["hunt"] or NO_HUNT,
             lambda v: self._set("hunt", "" if v == NO_HUNT else v))
        label(2, "Dificuldade")
        menu(2, config.DIFFICULTIES, self.cfg["difficulty"], lambda v: self._set("difficulty", v))
        label(3, "Auto Sell")
        menu(3, list(AUTO_SELL.values()), AUTO_SELL.get(self.cfg["loot"]["auto_sell"], AUTO_SELL["auto"]),
             lambda v: self._set_loot("auto_sell", {b: a for a, b in AUTO_SELL.items()}[v]))
        label(4, "Vender com (itens)")
        self.sell_var = tk.StringVar(value=str(self.cfg["loot"]["sell_at_items"]))
        entry = ctk.CTkEntry(grid, textvariable=self.sell_var, width=80, fg_color=PANEL_ALT)
        entry.grid(row=4, column=1, sticky="w", pady=6)
        entry.bind("<FocusOut>", lambda e: self._save_sell())
        entry.bind("<Return>", lambda e: self._save_sell())
        self.prey_var = tk.BooleanVar(value=bool(self.cfg["prey"]["enabled"]))
        ctk.CTkCheckBox(grid, text="Prey automática", variable=self.prey_var, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        text_color=TEXT, command=lambda: self._set_prey("enabled", self.prey_var.get())
                        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 2))
        label(7, "Trocar lista")
        menu(7, list(PREY_MODES.values()), PREY_MODES.get(self.cfg["prey"]["mode"], PREY_MODES["budget"]),
             lambda v: self._set_prey("mode", {b: a for a, b in PREY_MODES.items()}[v]))
        label(8, "Ouro por dia")
        self.prey_gold_var = tk.StringVar(value=str(self.cfg["prey"]["gold_per_day"]))
        gold_entry = ctk.CTkEntry(grid, textvariable=self.prey_gold_var, width=100, fg_color=PANEL_ALT)
        gold_entry.grid(row=8, column=1, sticky="w", pady=6)
        gold_entry.bind("<FocusOut>", lambda e: self._save_prey_gold())
        gold_entry.bind("<Return>", lambda e: self._save_prey_gold())
        label(9, "Stamina")
        stam = ctk.CTkFrame(grid, fg_color="transparent")
        stam.grid(row=9, column=1, sticky="w", pady=6)
        st_cfg = self.cfg["stamina"]
        self.stam_below = tk.StringVar(value=str(st_cfg["train_below_hours"]))
        self.stam_resume = tk.StringVar(value=str(st_cfg["resume_hours"]))
        ctk.CTkLabel(stam, text="treinar abaixo de", text_color=TEXT).pack(side="left")
        for var, key, suffix in ((self.stam_below, "train_below_hours", "h, voltar a caçar com"), (self.stam_resume, "resume_hours", "h")):
            e = ctk.CTkEntry(stam, textvariable=var, width=44, fg_color=PANEL_ALT)
            e.pack(side="left", padx=4)
            e.bind("<FocusOut>", lambda ev, k=key, v=var: self._save_stamina(k, v))
            e.bind("<Return>", lambda ev, k=key, v=var: self._save_stamina(k, v))
            ctk.CTkLabel(stam, text=suffix, text_color=TEXT).pack(side="left")
        self.relogin_var = tk.BooleanVar(value=bool(self.cfg["relogin"]))
        ctk.CTkCheckBox(grid, text="Relogin automático", variable=self.relogin_var, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        text_color=TEXT, command=lambda: self._set("relogin", self.relogin_var.get())
                        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=8)
        ctk.CTkLabel(tab, text="Destino: objetivo (task/bestiary) -> caça padrão -> treino (nunca parado). Stamina abaixo do "
                               "limite (14h: a XP da caça cai pela metade) leva pro treino até recuperar. "
                               "'Proteger drops de boss' fica sempre ligado. Sem Auto Sell o bot usa 'Vender tudo agora' "
                               "quando a Loot Pouch chega no número de itens. Insano+ pede level 250/450/700/1000. "
                               "Prey: escolhe a criatura da caça; senão troca a lista (grátis, depois com ouro); "
                               "nunca gasta cartas nem Drako Coins.",
                     text_color=MUTED, wraplength=840, justify="left").pack(anchor="w", padx=10, pady=6)

    def _set(self, key, value):
        self.cfg[key] = value
        self.save()
        self.log(f"regra: {key} = {value or 'nenhuma'}")

    def _set_loot(self, key, value):
        self.cfg["loot"][key] = value
        self.save()
        self.log(f"regra: loot.{key} = {value}")

    def _set_prey(self, key, value):
        self.cfg["prey"][key] = value
        self.save()
        self.log(f"regra: prey.{key} = {value}")

    def _save_prey_gold(self):
        try:
            value = max(0, int(self.prey_gold_var.get().replace(".", "")))
        except ValueError:
            self.prey_gold_var.set(str(self.cfg["prey"]["gold_per_day"]))
            return
        if value != self.cfg["prey"]["gold_per_day"]:
            self._set_prey("gold_per_day", value)

    def _save_stamina(self, key, var):
        try:
            value = max(0, min(42, int(var.get())))
        except ValueError:
            var.set(str(self.cfg["stamina"][key]))
            return
        if value != self.cfg["stamina"][key]:
            self.cfg["stamina"][key] = value
            self.save()
            self.log(f"regra: stamina.{key} = {value}h")

    def _save_sell(self):
        try:
            value = max(1, int(self.sell_var.get()))
        except ValueError:
            self.sell_var.set(str(self.cfg["loot"]["sell_at_items"]))
            return
        if value != self.cfg["loot"]["sell_at_items"]:
            self._set_loot("sell_at_items", value)

    # ------------------------------------------------------------- objetivos
    def _build_goals(self, tab):
        g = self.cfg["goals"]
        ctk.CTkLabel(tab, text="Com objetivo, o bot vai pra caça mais fácil que tem a criatura. Terminou: caça padrão (aba Regras) "
                               "ou treino. Ao lado de cada task: quanto do item dela está à venda no Market (comprando "
                               "você também completa a task).", text_color=MUTED, wraplength=900, justify="left"
                     ).pack(anchor="w", padx=8, pady=(6, 2))
        self.goal_status = ctk.CTkLabel(tab, text="", text_color=ACCENT, anchor="w", justify="left", wraplength=840)
        self.goal_status.pack(fill="x", padx=8)
        inner = ctk.CTkTabview(tab, fg_color=PANEL_ALT, height=330, segmented_button_selected_color=ACCENT,
                               segmented_button_selected_hover_color=ACCENT_HOVER, text_color=DARK_TEXT)
        inner.pack(fill="both", expand=True, padx=2, pady=2)
        inner.add("Tasks")
        inner.add("Bestiary")
        ctk.CTkLabel(inner.tab("Tasks"), text="Marque as tasks: o bot aceita (até 2), caça, entrega e segue a ordem.",
                     text_color=MUTED, wraplength=840, justify="left").pack(anchor="w", padx=4)
        self.task_vars = {}
        box = ctk.CTkScrollableFrame(inner.tab("Tasks"), fg_color=BG)
        box.pack(fill="both", expand=True)
        done = self.memory.get("task_rows") or {}
        chosen = set(g["tasks"])
        self.diff_menus = {}
        self.task_checks = {}           # nome -> (checkbox, texto base, item) pra mostrar o Market
        self._task_market_view = None
        for task in self.task_list:
            var = tk.BooleanVar(value=task["name"] in chosen)
            mark = "✓ " if done.get(task["name"]) == "done" else ("▶ " if done.get(task["name"]) == "active" else "")
            text = f"{mark}{task['name']}  ·  {task['amount']} {task['item']}  ·  Lv {task['level']}"
            self.task_checks[task["name"]] = (self._goal_row(box, task["name"], text, var, self._save_goal_tasks), text, task["item"])
            self.task_vars[task["name"]] = var
        ctk.CTkLabel(inner.tab("Bestiary"), text="Marque as criaturas: o bot caça onde ela aparece até completar e passa pra próxima.",
                     text_color=MUTED, wraplength=840, justify="left").pack(anchor="w", padx=4)
        self.beast_vars = {}
        box = ctk.CTkScrollableFrame(inner.tab("Bestiary"), fg_color=BG)
        box.pack(fill="both", expand=True)
        progress = self.memory.get("bestiary") or {}
        chosen = {c.casefold() for c in g["bestiary"]}
        creatures = {}
        for hunt in self.hunt_list:
            for creature in hunt["creatures"]:
                creatures.setdefault(creature, hunt)
        self.creature_order = sorted(creatures, key=lambda c: (creatures[c]["level"], c))
        for creature in self.creature_order:
            hunt = creatures[creature]
            var = tk.BooleanVar(value=creature.casefold() in chosen)
            mark = "✓ " if goals.bestiary_done(creature, progress) else ""
            self._goal_row(box, creature, f"{mark}{creature}  ·  {hunt['name']} (Lv {hunt['level']})", var,
                           self._save_goal_beasts)
            self.beast_vars[creature] = var

    def _goal_row(self, box, key, text, var, on_save):
        """Linha: checkbox + seletor de dificuldade (so' aparece marcada, pra a lista ficar leve)."""
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", pady=1)

        def toggled():
            self._show_diff(row, key, var.get())
            on_save()

        cb = ctk.CTkCheckBox(row, text=text, variable=var, fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT,
                             font=("Segoe UI", 11), command=toggled)
        cb.pack(side="left")
        if var.get():
            self._show_diff(row, key, True)
        return cb

    def _show_diff(self, row, key, show):
        menu = self.diff_menus.pop(key, None)
        if menu is not None:
            menu.destroy()
        if not show:
            return
        current = (self.cfg["goals"].get("difficulty") or {}).get(key) or DEFAULT_DIFF
        menu = ctk.CTkOptionMenu(row, values=[DEFAULT_DIFF] + config.DIFFICULTIES, width=88, height=22,
                                 font=("Segoe UI", 10), fg_color=PANEL_ALT, button_color=BORDER,
                                 button_hover_color=ACCENT_HOVER, dropdown_fg_color=PANEL_ALT, text_color=TEXT,
                                 dynamic_resizing=False, command=lambda v, k=key: self._set_goal_diff(k, v))
        menu.set(current)
        menu.pack(side="right", padx=(4, 6))
        self.diff_menus[key] = menu

    def _set_goal_diff(self, key, value):
        diffs = dict(self.cfg["goals"].get("difficulty") or {})
        if value == DEFAULT_DIFF:
            diffs.pop(key, None)
        else:
            diffs[key] = value
        self.cfg["goals"]["difficulty"] = diffs
        self.save()
        self.log(f"dificuldade de {key}: {value}")

    def _refresh_task_market(self):
        watcher = getattr(self.runner, "market", None) if self.runner.running else None
        data = watcher.task_market if watcher else {}
        view = tuple(sorted((k, v["lowest"], v["qty"]) for k, v in data.items()))
        if view == self._task_market_view:
            return
        self._task_market_view = view
        for name, (cb, text, item) in self.task_checks.items():
            info = data.get(item.casefold())
            if info and info["qty"]:
                cb.configure(text=f"{text}   ·   Market: {info['qty']} à venda a partir de {self._gold(info['lowest'])}")
            else:
                cb.configure(text=text)

    def _save_goal_tasks(self):
        self.cfg["goals"]["tasks"] = [t["name"] for t in self.task_list if self.task_vars[t["name"]].get()]
        self.save()
        self.log(f"tasks escolhidas: {', '.join(self.cfg['goals']['tasks']) or 'nenhuma'}")

    def _save_goal_beasts(self):
        self.cfg["goals"]["bestiary"] = [c for c in self.creature_order if self.beast_vars[c].get()]
        self.save()
        self.log(f"bestiary escolhido: {', '.join(self.cfg['goals']['bestiary']) or 'nenhum'}")

    # ------------------------------------------------------------ imbuements (por personagem / equipamento)
    def _build_imbuing(self, tab):
        c = self.cfg["imbuing"]
        try:
            from .market import imbuements as market_imb
            self.imbuing_data = market_imb.load()
        except Exception:
            self.imbuing_data = {"imbuements": [], "rules": {}}
        ctk.CTkLabel(tab, text="Escolha o imbuement de cada equipamento. O bot aplica quando faltar, reaplica quando acabar "
                               "e junta os materiais antes (Market e/ou caça onde mais dropa). Materiais escolhidos nunca são "
                               "vendidos. Vem antes de tasks e bestiary.", text_color=MUTED, wraplength=900, justify="left"
                     ).pack(anchor="w", padx=8, pady=(6, 2))

        opts = ctk.CTkFrame(tab, fg_color=PANEL_ALT, corner_radius=6)
        opts.pack(fill="x", padx=8, pady=4)
        self.imbuing_on = tk.BooleanVar(value=bool(c["enabled"]))
        ctk.CTkCheckBox(opts, text="Ligado", variable=self.imbuing_on, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        text_color=TEXT, width=70, command=lambda: self._imbuing_set("enabled", self.imbuing_on.get())
                        ).pack(side="left", padx=8, pady=8)
        ends = {"default": "Ao terminar: caça padrão", "loop": "Ao terminar: continuar juntando"}
        self._imbuing_menu(opts, list(ends.values()), ends.get(c["end"], ends["default"]), 210,
                           lambda v: self._imbuing_set("end", {b: a for a, b in ends.items()}[v]))
        self._imbuing_menu(opts, [DEFAULT_DIFF] + config.DIFFICULTIES, c["difficulty"] or DEFAULT_DIFF, 100,
                           lambda v: self._imbuing_set("difficulty", "" if v == DEFAULT_DIFF else v))
        self.imbuing_nums = {}
        for key, label, suffix, width in (("prepare_hours", "preparar com", "h", 36), ("buy_pct", "comprar até", "% do justo", 40),
                                          ("daily_budget", "até", "/dia", 80)):
            ctk.CTkLabel(opts, text=label, text_color=TEXT).pack(side="left", padx=(8, 2))
            var = tk.StringVar(value=str(c[key]))
            e = ctk.CTkEntry(opts, textvariable=var, width=width, fg_color=BG)
            e.pack(side="left")
            e.bind("<FocusOut>", lambda ev, k=key, v=var: self._imbuing_num(k, v))
            e.bind("<Return>", lambda ev, k=key, v=var: self._imbuing_num(k, v))
            ctk.CTkLabel(opts, text=suffix, text_color=MUTED).pack(side="left", padx=(2, 0))

        add = ctk.CTkFrame(tab, fg_color=PANEL_ALT, corner_radius=6)
        add.pack(fill="x", padx=8, pady=4)
        self.imbuing_add = {}
        for key, width in (("member", 110), ("slot", 170), ("imbuement", 130), ("tier", 90), ("source", 250)):
            self.imbuing_add[key] = self._imbuing_menu(add, ["-"], "-", width, lambda v, k=key: self._imbuing_pick(k))
        btn(add, "Adicionar", self._imbuing_add_target, primary=True, width=90).pack(side="left", padx=6, pady=8)
        self.imbuing_hint = ctk.CTkLabel(tab, text="", text_color=MUTED, anchor="w")
        self.imbuing_hint.pack(fill="x", padx=10)
        self.imbuing_list = ctk.CTkScrollableFrame(tab, fg_color=BG)
        self.imbuing_list.pack(fill="both", expand=True, padx=8, pady=4)
        self.imbuing_rows = {}
        self._imbuing_party = None
        self._imbuing_view = None
        self._imbuing_load_party()
        self._imbuing_draw()

    def _imbuing_menu(self, parent, values, current, width, command):
        m = ctk.CTkOptionMenu(parent, values=values, width=width, command=command, fg_color=BG, button_color=BORDER,
                              button_hover_color=ACCENT_HOVER, dropdown_fg_color=PANEL_ALT, text_color=TEXT,
                              dynamic_resizing=False)
        m.set(current)
        m.pack(side="left", padx=(6, 0), pady=8)
        return m

    def _imbuing_set(self, key, value):
        self.cfg["imbuing"][key] = value
        self.save()
        self.log(f"imbuements: {key} = {value}")

    def _imbuing_num(self, key, var):
        try:
            value = max(0, int(float(var.get().replace(".", "").replace(",", "."))))
        except ValueError:
            var.set(str(self.cfg["imbuing"][key]))
            return
        if value != self.cfg["imbuing"][key]:
            self._imbuing_set(key, value)

    def _imbuing_load_party(self):
        """Set da party lido pelo bot (memory 'imbuing_party'); sem leitura ainda -> menus vazios com aviso."""
        engine = self.runner.engine if self.runner.running else None
        mem = engine.memory if engine and engine.memory else Memory(MEMORY_PATH)
        party = mem.get("imbuing_party") or []
        if party == self._imbuing_party:
            return
        self._imbuing_party = party
        names = [m["name"] for m in party]
        menu = self.imbuing_add["member"]
        menu.configure(values=names or ["-"])
        if menu.get() not in names:
            menu.set(names[0] if names else "-")
        self.imbuing_hint.configure(text="" if party else "Inicie o bot: ele lê os equipamentos da party e os menus se preenchem.")
        self._imbuing_pick("member")

    def _imbuing_slots(self, member):
        m = next((m for m in self._imbuing_party or [] if m["name"] == member), None)
        return m["slots"] if m else []

    def _imbuing_pick(self, changed):
        """Menus em cascata: personagem -> equipamento -> imbuement compativel -> nivel / fonte."""
        a = self.imbuing_add
        slots = self._imbuing_slots(a["member"].get())
        if changed == "member":
            labels = [f"{imbuing.SLOT_LABELS.get(s['slot'], s['slot'])} · {s['item']}" for s in slots]
            a["slot"].configure(values=labels or ["-"])
            a["slot"].set(labels[0] if labels else "-")
        if changed in ("member", "slot"):
            slot = self._imbuing_slot_pick(slots)
            defs = imbuing.compatible(self.imbuing_data, slot["kind"]) if slot else []
            names = [d["name"] for d in defs]
            a["imbuement"].configure(values=names or ["-"])
            if a["imbuement"].get() not in names:
                a["imbuement"].set(names[0] if names else "-")
            a["tier"].configure(values=imbuing.TIER_NAMES)
            if a["tier"].get() not in imbuing.TIER_NAMES:
                a["tier"].set("Powerful")
            a["source"].configure(values=list(imbuing.SOURCES.values()))
            if a["source"].get() not in imbuing.SOURCES.values():
                a["source"].set(imbuing.SOURCES["auto"])

    def _imbuing_slot_pick(self, slots):
        label = self.imbuing_add["slot"].get()
        return next((s for s in slots if label == f"{imbuing.SLOT_LABELS.get(s['slot'], s['slot'])} · {s['item']}"), None)

    def _imbuing_add_target(self):
        a = self.imbuing_add
        slot = self._imbuing_slot_pick(self._imbuing_slots(a["member"].get()))
        d = next((d for d in self.imbuing_data["imbuements"] if d["name"] == a["imbuement"].get()), None)
        if not slot or not d:
            self.imbuing_hint.configure(text="Escolha personagem, equipamento e imbuement.", text_color=DANGER)
            return
        target = {"member": a["member"].get(), "slot": slot["slot"], "imbuement": d["id"],
                  "tier": imbuing.TIER_NAMES.index(a["tier"].get()),
                  "source": {v: k for k, v in imbuing.SOURCES.items()}[a["source"].get()]}
        targets = [t for t in self.cfg["imbuing"]["targets"] if imbuing.target_key(t) != imbuing.target_key(target)]
        same_slot = [t for t in targets if t["member"] == target["member"] and t["slot"] == target["slot"]]
        if len(same_slot) >= slot["cap"]:
            self.imbuing_hint.configure(text=f"{slot['item']} tem {slot['cap']} slot(s): remova uma meta dele antes.",
                                        text_color=DANGER)
            return
        targets.append(target)
        self.cfg["imbuing"]["targets"] = targets
        self.save()
        self.imbuing_hint.configure(text="", text_color=MUTED)
        self.log(f"imbuements: meta {self._imbuing_label(target)}")
        self._imbuing_draw()

    def _imbuing_remove(self, key):
        self.cfg["imbuing"]["targets"] = [t for t in self.cfg["imbuing"]["targets"] if imbuing.target_key(t) != key]
        self.save()
        self.log(f"imbuements: meta removida ({key.replace('|', ' · ')})")
        self._imbuing_draw()

    def _imbuing_label(self, t):
        d = imbuing.definition(self.imbuing_data, t["imbuement"])
        source = {"auto": "automático", "hunt": "caçar", "market": "comprar"}.get(t.get("source"), "automático")
        return (f"{t['member']} · {imbuing.SLOT_LABELS.get(t['slot'], t['slot'])} · "
                f"{imbuing.TIER_NAMES[t['tier']]} {d['name'] if d else t['imbuement']} · {source}")

    def _imbuing_draw(self):
        for child in self.imbuing_list.winfo_children():
            child.destroy()
        self.imbuing_rows = {}
        self._imbuing_view = None
        targets = self.cfg["imbuing"]["targets"]
        if not targets:
            ctk.CTkLabel(self.imbuing_list, text="Nenhuma meta. Escolha acima e clique em Adicionar.", text_color=MUTED
                         ).pack(anchor="w", padx=6, pady=6)
            return
        for t in targets:
            key = imbuing.target_key(t)
            row = ctk.CTkFrame(self.imbuing_list, fg_color=PANEL_ALT, corner_radius=6)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=self._imbuing_label(t), text_color=TEXT, anchor="w",
                         font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=8, pady=(6, 0))
            info = ctk.CTkLabel(row, text="aguardando a leitura do jogo", text_color=MUTED, anchor="w", justify="left")
            info.pack(anchor="w", padx=8, pady=(0, 6))
            btn(row, "Remover", lambda k=key: self._imbuing_remove(k), width=70).place(relx=1.0, x=-8, y=6, anchor="ne")
            self.imbuing_rows[key] = info

    def _imbuing_refresh(self):
        self._imbuing_load_party()
        snap = self.runner.snapshot if self.runner.running else None
        rows = (snap or {}).get("imbuing") or []
        view = repr(rows)
        if view == self._imbuing_view:
            return
        self._imbuing_view = view
        for r in rows:
            info = self.imbuing_rows.get(r["key"])
            if not info:
                continue
            state = r["state"]
            if r["remaining"] is not None:
                h = r["remaining"]
                state = f"{state} · restam {int(h)}h{int(h % 1 * 60):02d} de uso"
            mats = "   ".join(f"{name} {have}/{need}{' ✓' if have >= need else ''}" for name, have, need in r["materials"])
            color = OK if r["state"] == "ok" else (ACCENT if r["state"] in ("preparar", "aplicar") else DANGER)
            info.configure(text=f"{r['item'] or '-'}: {state}\n{mats}", text_color=color)

    # ---------------------------------------------------------------- market
    def _build_market(self, tab):
        m = self.cfg["market"]
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Market.Treeview", background=BG, fieldbackground=BG, foreground=TEXT, rowheight=22,
                        borderwidth=0, font=("Segoe UI", 10))
        style.configure("Market.Treeview.Heading", background=PANEL_ALT, foreground=MUTED, borderwidth=0,
                        font=("Segoe UI", 9, "bold"))
        style.map("Market.Treeview", background=[("selected", BORDER)])

        # rodape fixo: status + chave geral + limites (vale pras duas sub-abas)
        bottom = ctk.CTkFrame(tab, fg_color=PANEL_ALT, corner_radius=6)
        bottom.pack(side="bottom", fill="x", padx=4, pady=(2, 4))
        self.auto_buy_var = tk.BooleanVar(value=bool(m["auto_buy"]))
        ctk.CTkSwitch(bottom, text="Compra automática (chave geral)", variable=self.auto_buy_var, progress_color=ACCENT,
                      text_color=TEXT, command=lambda: self._set_market("auto_buy", self.auto_buy_var.get())
                      ).pack(side="left", padx=8, pady=6)
        self.budget_var = tk.StringVar(value=str(m["daily_budget"]))
        self.reserve_var = tk.StringVar(value=str(m["reserve_gold"]))
        for label, var, key in (("Orçamento/dia", self.budget_var, "daily_budget"), ("Reserva de ouro", self.reserve_var, "reserve_gold")):
            ctk.CTkLabel(bottom, text=label, text_color=TEXT).pack(side="left", padx=(14, 4))
            entry = ctk.CTkEntry(bottom, textvariable=var, width=90, fg_color=BG)
            entry.pack(side="left")
            entry.bind("<FocusOut>", lambda e, k=key, v=var: self._save_market_number(k, v))
            entry.bind("<Return>", lambda e, k=key, v=var: self._save_market_number(k, v))
        ctk.CTkLabel(bottom, text="Gasto hoje", text_color=TEXT).pack(side="left", padx=(14, 4))
        self.spent_var = tk.StringVar(value="-")
        ctk.CTkEntry(bottom, textvariable=self.spent_var, width=300, fg_color=BORDER, text_color=TEXT,
                     state="readonly").pack(side="left")
        self.market_status = ctk.CTkLabel(bottom, text="Ligue o bot para coletar os preços.", text_color=MUTED, anchor="e")
        self.market_status.pack(side="right", padx=8)
        try:
            self.market_store = MarketStore(os.path.join(ROOT, "market.db"))
        except Exception:
            self.market_store = None
        self._spent_at = 0

        inner = ctk.CTkTabview(tab, fg_color=PANEL, segmented_button_selected_color=ACCENT,
                               segmented_button_selected_hover_color=ACCENT_HOVER, text_color=DARK_TEXT)
        inner.pack(fill="both", expand=True, padx=2)
        inner.add("Imbuements")
        inner.add("Itens")
        inner.add("Relatório")
        self._build_market_imb(inner.tab("Imbuements"))
        self._build_market_items(inner.tab("Itens"))
        self._build_market_report(inner.tab("Relatório"))

    # ------------------------------------------------------ market: relatorio
    REPORT_PERIODS = ["Hoje", "Ontem", "7 dias", "30 dias", "Tudo"]

    def _build_market_report(self, tab):
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", padx=4, pady=(4, 2))
        self.report_period = ctk.CTkSegmentedButton(top, values=self.REPORT_PERIODS, selected_color=ACCENT,
                                                    selected_hover_color=ACCENT_HOVER, text_color=TEXT,
                                                    command=lambda v: self._report_refresh())
        self.report_period.set("Hoje")
        self.report_period.pack(side="left")
        ctk.CTkLabel(top, text="ou de", text_color=TEXT).pack(side="left", padx=(16, 4))
        self.report_from = tk.StringVar()
        self.report_to = tk.StringVar()
        ctk.CTkEntry(top, textvariable=self.report_from, width=96, placeholder_text="dd/mm/aaaa", fg_color=BG).pack(side="left")
        ctk.CTkLabel(top, text="até", text_color=TEXT).pack(side="left", padx=4)
        ctk.CTkEntry(top, textvariable=self.report_to, width=96, placeholder_text="dd/mm/aaaa", fg_color=BG).pack(side="left")
        btn(top, "Filtrar", lambda: self._report_refresh(custom=True), primary=True, width=70).pack(side="left", padx=6)
        btn(top, "Atualizar", self._report_refresh, width=80).pack(side="right")

        cols = ("quando", "item", "qtd", "preco", "total", "motivo")
        heads = ("Data / hora", "Item", "Qtd", "Preço", "Total", "Motivo")
        widths = (130, 190, 50, 90, 100, 230)
        self.report_tree = ttk.Treeview(tab, columns=cols, show="headings", height=13, style="Market.Treeview")
        for col, head, width in zip(cols, heads, widths):
            self.report_tree.heading(col, text=head)
            self.report_tree.column(col, width=width, anchor="e" if col in ("qtd", "preco", "total") else "w",
                                    stretch=col in ("item", "motivo"))
        self.report_tree.pack(fill="both", expand=True, padx=4, pady=4)
        self.report_summary = ctk.CTkLabel(tab, text="", text_color=TEXT, anchor="w", justify="left", font=("Segoe UI", 12))
        self.report_summary.pack(fill="x", padx=8, pady=(0, 4))
        self._report_refresh()

    def _report_range(self, custom):
        today = datetime.datetime.combine(datetime.date.today(), datetime.time())
        if custom:
            def parse(text, end=False):
                text = (text or "").strip()
                if not text:
                    return None
                d = datetime.datetime.strptime(text, "%d/%m/%Y")
                return (d + datetime.timedelta(days=1) if end else d).timestamp()
            try:
                return parse(self.report_from.get()), parse(self.report_to.get(), end=True), "período escolhido"
            except ValueError:
                return None
        period = self.report_period.get()
        if period == "Hoje":
            return today.timestamp(), None, "hoje"
        if period == "Ontem":
            return (today - datetime.timedelta(days=1)).timestamp(), today.timestamp(), "ontem"
        if period in ("7 dias", "30 dias"):
            days = int(period.split()[0])
            return (today - datetime.timedelta(days=days - 1)).timestamp(), None, f"últimos {days} dias"
        return None, None, "todo o histórico"

    def _report_refresh(self, custom=False):
        if not self.market_store:
            return
        rng = self._report_range(custom)
        if rng is None:
            self.report_summary.configure(text="Data inválida: use dd/mm/aaaa (ex.: 20/10/2026).", text_color=DANGER)
            return
        start, end, label = rng
        rows = self.market_store.purchases_between(start, end)
        self.report_tree.delete(*self.report_tree.get_children())
        by_item = {}
        for ts, name, qty, price, total, reason in rows:
            when = datetime.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M:%S")
            self.report_tree.insert("", "end", values=(when, name, qty, self._gold(price), self._gold(total), reason or "-"))
            item = by_item.setdefault(name, [0, 0])
            item[0] += qty
            item[1] += total
        spent = sum(r[4] for r in rows)
        units = sum(r[2] for r in rows)
        top = sorted(by_item.items(), key=lambda kv: -kv[1][1])[:5]
        detail = " · ".join(f"{n}: {q} un. ({self._gold(t)})" for n, (q, t) in top)
        self.report_summary.configure(
            text=(f"{label.capitalize()}: {len(rows)} compras · {units} itens · {self._gold(spent)} de ouro"
                  + (f"\nMais gasto: {detail}" if detail else "")), text_color=TEXT)

    def _refresh_spent(self):
        """Campo 'Gasto hoje' (travado): soma das compras do bot desde 00h, orçamento e quanto resta."""
        if not self.market_store or time.time() - self._spent_at < 2:
            return
        self._spent_at = time.time()
        try:
            spent = self.market_store.spent_today()
        except Exception:
            return
        budget = self.cfg["market"]["daily_budget"]
        self.spent_var.set(f"{self._gold(spent)} de {self._gold(budget)} (resta {self._gold(max(0, budget - spent))})")

    # ------------------------------------------------------ market: imbuements
    def _build_market_imb(self, tab):
        try:
            self.imb_data = imb.load()
        except Exception:
            self.imb_data = {"imbuements": [], "rules": {}}
        self.imb_by_id = {d["id"]: d for d in self.imb_data["imbuements"]}
        self.imb_selected = None
        self.imb_buttons = {}
        left = ctk.CTkScrollableFrame(tab, width=200, fg_color=BG, corner_radius=6)
        left.pack(side="left", fill="y", padx=(2, 6), pady=2)
        groups = {}
        for d in self.imb_data["imbuements"]:
            groups.setdefault(d["category"], []).append(d)
        for category in ("skill", "damage", "protection", "support"):
            if category not in groups:
                continue
            ctk.CTkLabel(left, text=imb.CATEGORY_NAMES.get(category, category).upper(), text_color=MUTED,
                         font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=6, pady=(8, 1))
            for d in groups[category]:
                b = ctk.CTkButton(left, text=d["name"], anchor="w", height=24, fg_color="transparent", hover_color=BORDER,
                                  text_color=TEXT, command=lambda i=d["id"]: self._imb_select(i))
                b.pack(fill="x", padx=2, pady=0)
                self.imb_buttons[d["id"]] = b
        self._imb_marks()

        right = ctk.CTkFrame(tab, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)
        self.imb_title = ctk.CTkLabel(right, text="Escolha um imbuement à esquerda", text_color=TEXT,
                                      font=("Segoe UI", 16, "bold"), anchor="w")
        self.imb_title.pack(fill="x", padx=4, pady=(2, 0))
        self.imb_sub = ctk.CTkLabel(right, text="", text_color=MUTED, anchor="w", justify="left")
        self.imb_sub.pack(fill="x", padx=4)

        ctrl = ctk.CTkFrame(right, fg_color=PANEL_ALT, corner_radius=6)
        ctrl.pack(fill="x", padx=4, pady=6)
        self.imb_watch = tk.BooleanVar()
        ctk.CTkCheckBox(ctrl, text="Observar", variable=self.imb_watch, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        text_color=TEXT, command=self._imb_save).pack(side="left", padx=8, pady=6)
        ctk.CTkLabel(ctrl, text="acompanha os 3 materiais (todos os níveis) ao vivo", text_color=MUTED
                     ).pack(side="left", padx=(12, 4))

        cols = ("nivel", "mat", "tenho", "menor", "justo", "desc", "venda", "qual")
        heads = ("Nível", "Material", "Tenho", "Menor", "Justo", "Desc.", "À venda", "Qualidade")
        widths = (74, 170, 60, 80, 80, 56, 64, 86)
        self.imb_tree = ttk.Treeview(right, columns=cols, show="headings", height=4, style="Market.Treeview")
        for col, head, width in zip(cols, heads, widths):
            self.imb_tree.heading(col, text=head)
            self.imb_tree.column(col, width=width, anchor="w" if col == "mat" else "e", stretch=col == "mat")
        for q, color in (("excelente", OK), ("muito boa", ACCENT), ("boa", "#c9b26b"), ("ok", TEXT), ("vazio", MUTED)):
            self.imb_tree.tag_configure(q, foreground=color)
        self.imb_tree.pack(fill="x", padx=4)
        self.imb_summary = ctk.CTkLabel(right, text="", text_color=TEXT, anchor="w", justify="left", font=("Segoe UI", 12))
        self.imb_summary.pack(fill="x", padx=6, pady=(8, 2))

        buy = ctk.CTkFrame(right, fg_color=PANEL_ALT, corner_radius=6)
        buy.pack(fill="x", padx=4, pady=6)
        self.imb_buy = tk.BooleanVar()
        ctk.CTkCheckBox(buy, text="Comprar oportunidades (qualquer material deste imbuement)", variable=self.imb_buy, fg_color=ACCENT,
                        hover_color=ACCENT_HOVER, text_color=TEXT, command=self._imb_save).pack(side="left", padx=8, pady=6)
        ctk.CTkLabel(buy, text="pagando até", text_color=TEXT).pack(side="left", padx=(12, 4))
        self.imb_pct = tk.StringVar(value="80")
        pct = ctk.CTkEntry(buy, textvariable=self.imb_pct, width=46, fg_color=BG)
        pct.pack(side="left")
        pct.bind("<FocusOut>", lambda e: self._imb_save())
        pct.bind("<Return>", lambda e: self._imb_save())
        ctk.CTkLabel(buy, text="% do preço justo, estoque de", text_color=TEXT).pack(side="left", padx=4)
        self.imb_stock = tk.StringVar(value="2")
        stock = ctk.CTkEntry(buy, textvariable=self.imb_stock, width=36, fg_color=BG)
        stock.pack(side="left")
        stock.bind("<FocusOut>", lambda e: self._imb_save())
        stock.bind("<Return>", lambda e: self._imb_save())
        ctk.CTkLabel(buy, text="aplicações", text_color=TEXT).pack(side="left", padx=4)
        self.imb_hint = ctk.CTkLabel(right, text="Compra na hora (ao vivo) material deste imbuement até X% do preço de referência, "
                                                 "só até ter estoque para N aplicações (mochila + depot), dentro do orçamento do dia. "
                                                 "Travas: no 1º minuto depois de ligar só lê o mercado; não compra se o preço justo "
                                                 "estiver desatualizado (muita coisa à venda bem abaixo dele) e confere com os preços "
                                                 "que o próprio bot viu nas últimas 24h. Precisa da chave geral ligada.",
                                     text_color=MUTED, anchor="w", justify="left", wraplength=640)
        self.imb_hint.pack(fill="x", padx=6)
        self._imb_view = None

    def _imb_rule(self, imb_id):
        return dict((self.cfg["market"].get("imbuements") or {}).get(imb_id) or {})

    def _imb_marks(self):
        for imb_id, b in self.imb_buttons.items():
            rule = self._imb_rule(imb_id)
            mark = ("★ " if rule.get("watch") else "") + ("$ " if rule.get("watch") and rule.get("buy") else "")
            b.configure(text=mark + self.imb_by_id[imb_id]["name"],
                        fg_color=BORDER if imb_id == self.imb_selected else "transparent")

    def _imb_select(self, imb_id):
        self.imb_selected = imb_id
        rule = self._imb_rule(imb_id)
        d = self.imb_by_id[imb_id]
        self.imb_watch.set(bool(rule.get("watch")))
        self.imb_buy.set(bool(rule.get("buy")))
        self.imb_pct.set(str(rule.get("pay_pct", 80)))
        self.imb_stock.set(str(rule.get("stock", 2)))
        effect = d.get("effect") or {}
        values = " / ".join(str(v) for v in effect.get("values") or [])
        self.imb_title.configure(text=d["name"])
        self.imb_sub.configure(text=f"{imb.CATEGORY_NAMES.get(d['category'], d['category'])} · {effect.get('label', '')} "
                                    f"({values} por nível) · entra em: {', '.join(d['kinds'])}")
        self._imb_marks()
        self._imb_view = None
        self._imb_render()

    def _imb_save(self):
        if not self.imb_selected:
            return
        def num(var, default, low, high):
            try:
                return max(low, min(high, int(str(var.get()).replace(".", "") or default)))
            except ValueError:
                return default
        rule = {"watch": self.imb_watch.get(), "buy": self.imb_buy.get(), "pay_pct": num(self.imb_pct, 80, 10, 100),
                "stock": num(self.imb_stock, 2, 1, 50)}
        if rule["buy"] and not rule["watch"]:
            rule["watch"] = True
            self.imb_watch.set(True)
        rules = dict(self.cfg["market"].get("imbuements") or {})
        if rules.get(self.imb_selected) == rule:
            return
        rules[self.imb_selected] = rule
        self.cfg["market"]["imbuements"] = rules
        self.save()
        name = self.imb_by_id[self.imb_selected]["name"]
        self.log(f"market: {name}: observar={rule['watch']} comprar oportunidades={rule['buy']} "
                 f"até {rule['pay_pct']}% do justo, estoque de {rule['stock']} aplicações")
        self._imb_marks()
        self._imb_view = None
        self._imb_render()

    def _imb_render(self):
        if not self.imb_selected:
            return
        watcher = getattr(self.runner, "market", None) if self.runner.running else None
        rule = self._imb_rule(self.imb_selected)
        pct = rule.get("pay_pct", 80)
        view = (self.imb_selected, pct, rule.get("watch"), watcher.last_run if watcher else None,
                getattr(watcher, "last_live", None))
        if view == self._imb_view:
            return
        self._imb_view = view
        board = watcher.board if watcher else {}
        owned = watcher.owned if watcher else {}
        self.imb_tree.delete(*self.imb_tree.get_children())
        chances = []
        for tier, material in enumerate(self.imb_by_id[self.imb_selected]["materials"]):
            key = material["name"].casefold()
            ev = board.get(key)
            tag = (ev.quality if ev and ev.quality else ("ok" if ev and ev.offers else "vazio"))
            self.imb_tree.insert("", "end", tags=(tag,), values=(
                imb.TIER_NAMES[tier], material["display"], owned.get(key, 0) if watcher else "-",
                self._gold(ev.lowest_sell if ev else None), self._gold(ev.fair if ev else None),
                f"{ev.discount:.0%}" if ev and ev.discount is not None else "-",
                (ev.sell_qty or "-") if ev else "-", (ev.quality or "-") if ev else "-"))
            if ev and ev.fair and ev.offers and ev.lowest_sell <= ev.fair * pct / 100:
                chances.append(f"{material['display']} a {self._gold(ev.lowest_sell)}")
        if not watcher:
            text = "Ligue o bot para ver os preços ao vivo."
        elif not rule.get("watch"):
            text = "Marque 'Observar' para o bot acompanhar esses materiais ao vivo."
        elif chances:
            text = f"Oportunidade agora (até {pct}% do justo): " + " · ".join(chances)
        else:
            text = f"Nenhuma oferta até {pct}% do justo no momento."
        self.imb_summary.configure(text=text)

    def _build_market_items(self, tab):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Market.Treeview", background=BG, fieldbackground=BG, foreground=TEXT, rowheight=20,
                        borderwidth=0, font=("Segoe UI", 9))
        style.configure("Market.Treeview.Heading", background=PANEL_ALT, foreground=MUTED, borderwidth=0,
                        font=("Segoe UI", 9, "bold"))
        style.map("Market.Treeview", background=[("selected", BORDER)])
        cols = ("item", "menor", "justo", "desc", "venda", "qual")
        heads = ("Item", "Menor", "Justo", "Desc.", "À venda", "Qualidade")
        widths = (260, 90, 90, 70, 80, 110)
        self.market_tree = ttk.Treeview(tab, columns=cols, show="headings", height=14, style="Market.Treeview")
        for col, head, width in zip(cols, heads, widths):
            self.market_tree.heading(col, text=head)
            self.market_tree.column(col, width=width, anchor="w" if col == "item" else "e", stretch=col == "item")
        for q, color in (("excelente", OK), ("muito boa", ACCENT), ("boa", "#c9b26b"), ("vazio", MUTED)):
            self.market_tree.tag_configure(q, foreground=color)
        self.market_tree.pack(fill="both", expand=True, padx=4)
        self.market_tree.bind("<<TreeviewSelect>>", lambda e: self._market_selected())

        rule = ctk.CTkFrame(tab, fg_color=PANEL_ALT, corner_radius=6)
        rule.pack(fill="x", padx=4, pady=4)
        self.rule_title = ctk.CTkLabel(rule, text="Selecione um item", text_color=TEXT, font=("Segoe UI", 12, "bold"), anchor="w")
        self.rule_title.grid(row=0, column=0, columnspan=4, sticky="w", padx=8, pady=(6, 2))
        self.rule_watch = tk.BooleanVar()
        self.rule_buy = tk.BooleanVar()
        self.rule_price = tk.StringVar()
        self.rule_qty = tk.StringVar()
        ctk.CTkCheckBox(rule, text="Observar (alerta)", variable=self.rule_watch, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        text_color=TEXT, command=self._save_rule).grid(row=1, column=0, columnspan=2, sticky="w", padx=8)
        ctk.CTkCheckBox(rule, text="Comprar automático", variable=self.rule_buy, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        text_color=TEXT, command=self._save_rule).grid(row=1, column=2, columnspan=2, sticky="w")
        ctk.CTkLabel(rule, text="Preço máx.", text_color=TEXT).grid(row=2, column=0, sticky="w", padx=8, pady=4)
        price = ctk.CTkEntry(rule, textvariable=self.rule_price, width=80, fg_color=BG)
        price.grid(row=2, column=1, sticky="w")
        ctk.CTkLabel(rule, text="Quantidade", text_color=TEXT).grid(row=2, column=2, sticky="w", padx=(8, 4))
        qty = ctk.CTkEntry(rule, textvariable=self.rule_qty, width=60, fg_color=BG)
        qty.grid(row=2, column=3, sticky="w")
        for entry in (price, qty):
            entry.bind("<FocusOut>", lambda e: self._save_rule())
            entry.bind("<Return>", lambda e: self._save_rule())
        self.rule_hint = ctk.CTkLabel(rule, text="", text_color=MUTED, anchor="w", justify="left", wraplength=820)
        self.rule_hint.grid(row=3, column=0, columnspan=4, sticky="w", padx=8, pady=(0, 6))

        self._market_rows = {}
        self._market_view = None
        self._market_selected_name = None

    def _gold(self, value):
        return "-" if value is None else f"{int(value):,}".replace(",", ".")

    def _refresh_market(self):
        watcher = getattr(self.runner, "market", None) if self.runner.running else None
        if watcher is None:
            return
        board, listing = watcher.board, watcher.listing
        view = (watcher.last_run, len(listing), watcher.error, tuple(sorted(self.cfg["market"].get("rules", {}))))
        if view == self._market_view:
            return
        self._market_view = view
        if watcher.error:
            self.market_status.configure(text=f"Erro: {watcher.error}", text_color=DANGER)
        elif watcher.last_run:
            when = datetime.datetime.fromtimestamp(watcher.last_run).strftime("%H:%M")
            self.market_status.configure(text=f"{len(listing)} itens · atualizado {when}", text_color=MUTED)
        rules = self.cfg["market"].get("rules") or {}
        rows = []
        for row in listing:
            key = (row["name"] or "").casefold()
            ev = board.get(key)
            rows.append((0 if row["sell_qty"] else 1, -ev.discount if ev and ev.discount is not None else 9, key, row, ev))
        rows.sort(key=lambda r: (r[0], r[1], r[2]))
        selected = self._market_selected_name
        self.market_tree.delete(*self.market_tree.get_children())
        self._market_rows = {}
        for _, _, key, row, ev in rows:
            mark = ("★ " if rules.get(key, {}).get("watch") else "") + ("$ " if rules.get(key, {}).get("buy") else "")
            values = (mark + (row["name"] or "?"), self._gold(ev.lowest_sell if ev else row["lowest_sell"]),
                      self._gold(ev.fair if ev else None),
                      f"{ev.discount:.0%}" if ev and ev.discount is not None else "-", row["sell_qty"] or "-",
                      (ev.quality if ev and ev.quality else "-"))
            tag = ev.quality if ev and ev.quality else ("vazio" if not row["sell_qty"] else "")
            iid = self.market_tree.insert("", "end", values=values, tags=(tag,))
            self._market_rows[iid] = key
            if key == selected:
                self.market_tree.selection_set(iid)

    def _market_selected(self):
        sel = self.market_tree.selection()
        if not sel:
            return
        key = self._market_rows.get(sel[0])
        self._market_selected_name = key
        rule = (self.cfg["market"].get("rules") or {}).get(key, {})
        self.rule_title.configure(text=key)
        self.rule_watch.set(bool(rule.get("watch")))
        self.rule_buy.set(bool(rule.get("buy")))
        self.rule_price.set(str(rule.get("max_price") or ""))
        self.rule_qty.set(str(rule.get("quantity") or ""))
        watcher = getattr(self.runner, "market", None)
        ev = watcher.board.get(key) if watcher else None
        bought = 0
        try:
            bought = watcher.store.bought(ev.item_id) if watcher and ev else 0
        except Exception:
            pass
        if ev and ev.fair:
            trend = f" · tendência {ev.trend:+.0%}" if ev.trend is not None else ""
            per_day = f" · {ev.per_day:.0f}/dia" if ev.per_day else ""
            self.rule_hint.configure(text=f"Justo {self._gold(ev.fair)}{trend}{per_day}. Sem preço máx. o bot usa "
                                          f"{self._gold(ev.suggested_max)} (20% abaixo). Comprados pelo bot: {bought}.")
        else:
            self.rule_hint.configure(text="Sem negócios no histórico: o bot não sabe o preço justo. "
                                          "Pra comprar automático, informe o preço máximo.")

    def _save_rule(self):
        key = self._market_selected_name
        if not key:
            return
        def num(var):
            try:
                return max(0, int(var.get().replace(".", "") or 0))
            except ValueError:
                return 0
        rule = {"watch": self.rule_watch.get(), "buy": self.rule_buy.get(), "max_price": num(self.rule_price),
                "quantity": num(self.rule_qty)}
        rules = dict(self.cfg["market"].get("rules") or {})
        if rules.get(key) == rule:
            return
        if any(rule.values()):
            rules[key] = rule
        else:
            rules.pop(key, None)
        self.cfg["market"]["rules"] = rules
        self.save()
        self._market_view = None
        self.log(f"market: regra de {key}: observar={rule['watch']} comprar={rule['buy']} "
                 f"máx={rule['max_price'] or 'sugerido'} qtd={rule['quantity']}")

    def _set_market(self, key, value):
        self.cfg["market"][key] = value
        self.save()
        self.log(f"market: {key} = {value}")

    def _save_market_number(self, key, var):
        try:
            value = max(0, int(var.get().replace(".", "")))
        except ValueError:
            var.set(str(self.cfg["market"][key]))
            return
        if value != self.cfg["market"][key]:
            self._set_market(key, value)

    def notify(self, title, text):
        """Aviso de oportunidade/compra: balão da bandeja (se estiver na bandeja) + som (compra = som proprio)."""
        buying = title.startswith("Compra")
        def show():
            if self.tray_icon is not None:
                try:
                    self.tray_icon.notify(text, title)
                except Exception:
                    pass
            try:
                import winsound
                if buying:
                    for freq in (880, 1175, 1568):          # 3 notas subindo: comprou
                        winsound.Beep(freq, 140)
                else:
                    winsound.MessageBeep()
            except Exception:
                pass
        if buying:
            threading.Thread(target=show, daemon=True).start()   # Beep bloqueia: fora da thread da interface
        else:
            self.call_ui(show)

    # ----------------------------------------------------------------- login
    def _build_login(self, tab):
        self.credentials = Credentials(os.path.join(ROOT, "credentials.json"))
        ctk.CTkLabel(tab, text="Login do Drakoria pra o bot entrar sozinho se o jogo cair ou deslogar. A senha fica "
                               "criptografada pelo Windows (só abre neste PC, no seu usuário) e nunca vai pro log.",
                     text_color=MUTED, wraplength=840, justify="left").pack(anchor="w", padx=8, pady=(8, 10))
        form = ctk.CTkFrame(tab, fg_color="transparent")
        form.pack(fill="x", padx=8)
        form.columnconfigure(1, weight=1)
        self.login_user = tk.StringVar()
        self.login_pass = tk.StringVar()
        ctk.CTkLabel(form, text="Usuário", text_color=TEXT).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ctk.CTkEntry(form, textvariable=self.login_user, fg_color=PANEL_ALT).grid(row=0, column=1, sticky="ew", pady=4)
        ctk.CTkLabel(form, text="Senha", text_color=TEXT).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ctk.CTkEntry(form, textvariable=self.login_pass, show="•", fg_color=PANEL_ALT).grid(row=1, column=1, sticky="ew", pady=4)
        btn(form, "Salvar login", self._save_login, primary=True).grid(row=2, column=1, sticky="e", pady=8)
        self.login_msg = ctk.CTkLabel(tab, text="", text_color=MUTED)
        self.login_msg.pack(anchor="w", padx=8)
        self.login_list = ctk.CTkFrame(tab, fg_color=PANEL_ALT)
        self.login_list.pack(fill="x", padx=8, pady=8)
        self._refresh_logins()

        ctk.CTkLabel(tab, text="CONEXÃO COM O JOGO", text_color=MUTED, font=("Segoe UI", 10, "bold"), anchor="w"
                     ).pack(fill="x", padx=8, pady=(14, 2))
        self.conn_label = ctk.CTkLabel(tab, text="", text_color=TEXT, anchor="w", font=("Segoe UI", 12, "bold"))
        self.conn_label.pack(fill="x", padx=8)
        self._conn_text()

        find = ctk.CTkFrame(tab, fg_color=PANEL_ALT, corner_radius=6)
        find.pack(fill="x", padx=8, pady=(6, 2))
        btn(find, "Procurar navegadores", self._scan_browsers, primary=True, width=170).pack(side="left", padx=8, pady=8)
        ctk.CTkLabel(find, text="mostra os navegadores abertos no modo do bot e se estão com o Drakoria",
                     text_color=MUTED).pack(side="left", padx=4)
        self.scan_box = ctk.CTkFrame(tab, fg_color=BG, corner_radius=6)
        self.scan_box.pack(fill="x", padx=8, pady=2)

        opener = ctk.CTkFrame(tab, fg_color=PANEL_ALT, corner_radius=6)
        opener.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(opener, text="Abrir navegador para o bot:", text_color=TEXT).pack(side="left", padx=8, pady=8)
        self.installed = browsers.installed()
        names = [n for n, _ in self.installed] + ["IdleDeck"]
        self.open_choice = ctk.CTkOptionMenu(opener, values=names, width=140, fg_color=BG, button_color=BORDER,
                                             button_hover_color=ACCENT_HOVER, dropdown_fg_color=PANEL_ALT, text_color=TEXT)
        self.open_choice.set((self.cfg.get("browser") or {}).get("name") or names[0])
        self.open_choice.pack(side="left")
        btn(opener, "Abrir", self._open_browser, primary=True, width=80).pack(side="left", padx=8)
        self.conn_msg = ctk.CTkLabel(tab, text="", text_color=MUTED, anchor="w", justify="left", wraplength=900)
        self.conn_msg.pack(fill="x", padx=8, pady=(2, 0))
        ctk.CTkLabel(tab, text="O bot só consegue controlar um navegador aberto no 'modo do bot'. 'Abrir' faz isso por você "
                               "numa janela própria do bot (login e VPN do Opera ficam salvos nela) e já abre o jogo. "
                               "Se o navegador escolhido estiver fechado quando você iniciar o bot, ele reabre sozinho.",
                     text_color=MUTED, wraplength=900, justify="left").pack(anchor="w", padx=8, pady=4)

    def _conn_text(self):
        chosen = (self.cfg.get("browser") or {}).get("name")
        port = self.cfg["cdp_url"].rsplit(":", 1)[-1]
        name = chosen or ("IdleDeck" if self.cfg.get("launch_idledeck", True) else "navegador")
        self.conn_label.configure(text=f"Conectado a: {name} (porta {port})")

    def _use_connection(self, url, name, browser=None):
        """Escolhe a conexão. browser = {name, path} quando o bot sabe reabrir esse navegador sozinho."""
        self.cfg["cdp_url"] = url
        self.cfg["launch_idledeck"] = name == "IdleDeck"
        self.cfg["browser"] = browser
        self.save()
        self._conn_text()
        self.log(f"conexão: {name} ({url.rsplit(':', 1)[-1]})" + (" - reinicie o bot pra valer" if self.runner.running else ""))

    def _scan_browsers(self):
        self.conn_msg.configure(text="Procurando...", text_color=MUTED)

        def work():
            try:
                found = browsers.scan()
            except Exception as error:
                found, err = [], str(error)
            else:
                err = ""
            self.call_ui(lambda: self._show_scan(found, err))
        threading.Thread(target=work, daemon=True).start()

    def _show_scan(self, found, err):
        for child in self.scan_box.winfo_children():
            child.destroy()
        if err or not found:
            self.conn_msg.configure(text=err or "Nenhum navegador aberto no modo do bot. Use 'Abrir navegador para o bot'.",
                                    text_color=DANGER if err else MUTED)
            return
        self.conn_msg.configure(text=f"{len(found)} navegador(es) no modo do bot.", text_color=MUTED)
        paths = dict(self.installed)
        for b in found:
            row = ctk.CTkFrame(self.scan_box, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=2)
            game = ("Drakoria aberto" + (" (logado)" if b["logged"] else "")) if b["game_tabs"] else "sem a aba do Drakoria"
            current = b["url"] == self.cfg["cdp_url"]
            ctk.CTkLabel(row, text=f"{'● ' if current else ''}{b['name']}  ·  porta {b['port']}  ·  {game}",
                         text_color=OK if b["game_tabs"] else MUTED, anchor="w").pack(side="left")
            name = b["name"] if b["name"] != "Opera / Opera GX" else ("Opera GX" if "Opera GX" in paths else "Opera")
            known = {"name": name, "path": paths[name]} if name in paths else None
            btn(row, "Usar este", lambda u=b["url"], n=b["name"], k=known: self._use_connection(u, n, k),
                primary=bool(b["game_tabs"]), width=90).pack(side="right", padx=4)
            if not b["game_tabs"] and b["name"] != "IdleDeck":
                btn(row, "Abrir o jogo aqui", lambda u=b["url"]: self._open_game_tab(u), width=130).pack(side="right")

    def _open_game_tab(self, url):
        try:
            browsers.open_game_tab(url)
            self.conn_msg.configure(text="Aba do Drakoria aberta: entre no jogo nela e clique em 'Usar este'.", text_color=OK)
        except Exception as error:
            self.conn_msg.configure(text=f"Não consegui abrir a aba: {error}", text_color=DANGER)
        self._scan_browsers()

    def _open_browser(self):
        name = self.open_choice.get()
        if name == "IdleDeck":
            self._use_connection("http://127.0.0.1:9224", "IdleDeck", None)
            self.conn_msg.configure(text="IdleDeck escolhido: o bot abre o IdleDeck no modo certo ao iniciar.", text_color=OK)
            return
        path = dict(self.installed).get(name)
        self.conn_msg.configure(text=f"Abrindo {name}...", text_color=MUTED)

        def work():
            try:
                url = browsers.launch(name, path)
            except Exception as error:
                self.call_ui(lambda: self.conn_msg.configure(text=f"Não consegui abrir o {name}: {error}", text_color=DANGER))
                return
            def done():
                self._use_connection(url, name, {"name": name, "path": path})
                self.conn_msg.configure(text=f"{name} aberto na página do Drakoria. Entre no jogo nessa janela (e ligue a VPN, "
                                             f"se usar) e depois inicie o bot.", text_color=OK)
            self.call_ui(done)
        threading.Thread(target=work, daemon=True).start()

    def _refresh_logins(self):
        for child in self.login_list.winfo_children():
            child.destroy()
        names = self.credentials.usernames()
        if not names:
            ctk.CTkLabel(self.login_list, text="Nenhum login salvo.", text_color=MUTED).pack(anchor="w", padx=10, pady=8)
            return
        for name in names:
            line = ctk.CTkFrame(self.login_list, fg_color="transparent")
            line.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(line, text=f"{name}   ••••••", text_color=TEXT, anchor="w").pack(side="left")
            btn(line, "Remover", lambda n=name: self._remove_login(n), width=80).pack(side="right")

    def _save_login(self):
        user, password = self.login_user.get().strip(), self.login_pass.get()
        if not user or len(password) < 4:
            self.login_msg.configure(text="Preencha usuário e senha.", text_color=DANGER)
            return
        try:
            for old in self.credentials.usernames():     # 1 conta controla a party: guarda um login so'
                if old.casefold() != user.casefold():
                    self.credentials.remove(old)
            self.credentials.save(user, password)
        except Exception as error:
            self.login_msg.configure(text=f"Não consegui salvar: {error}", text_color=DANGER)
            return
        self.login_user.set("")
        self.login_pass.set("")
        self.login_msg.configure(text=f"Login {user} salvo.", text_color=OK)
        self.log(f"login salvo: {user}")
        self._refresh_logins()

    def _remove_login(self, name):
        self.credentials.remove(name)
        self.log(f"login removido: {name}")
        self._refresh_logins()

    # ------------------------------------------------------------------- log
    def _build_log(self, tab):
        self.log_box = ctk.CTkTextbox(tab, fg_color=BG, text_color=TEXT, font=("Consolas", 10), state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=4, pady=4)
        folder = os.path.join(ROOT, "logs")
        btn(tab, "Abrir pasta dos logs", lambda: os.startfile(folder) if os.path.isdir(folder) else None).pack(anchor="e", padx=4, pady=(0, 4))

    # ------------------------------------------------------------- atualizar
    def _startup_update_check(self):
        def work():
            info = updater.check_for_update(lambda m: None)
            if info:
                self.log(f"Nova versão disponível: v{info['version']} (você está na v{VERSION}). Clique em Atualizar.")
        threading.Thread(target=work, daemon=True).start()

    def start_update(self):
        if self.updating:
            return
        if self.runner.running:
            self.log("Pare o bot antes de atualizar.")
            return
        self.update_btn.configure(state="disabled", text="...")

        def work():
            info = updater.check_for_update(self.log)
            self.call_ui(lambda: self._on_update_checked(info))
        threading.Thread(target=work, daemon=True).start()

    def _on_update_checked(self, info):
        self.update_btn.configure(state="normal", text="Atualizar")
        if info is None:
            self.log(f"Você já está na última versão (v{VERSION}).")
            return
        if not updater.is_frozen():
            self.log(f"Há uma versão nova (v{info['version']}), mas a atualização automática só funciona no DrakoriaBot.exe.")
            return
        self.updating = True
        overlay = ctk.CTkFrame(self.root, fg_color=BG)
        overlay.place(x=0, y=0, relwidth=1, relheight=1)
        ctk.CTkLabel(overlay, text=f"Atualizando para a v{info['version']}...", font=("Segoe UI", 15, "bold"),
                     text_color=TEXT).place(relx=0.5, rely=0.45, anchor="center")
        bar = ctk.CTkProgressBar(overlay, width=300, progress_color=ACCENT)
        bar.set(0)
        bar.place(relx=0.5, rely=0.53, anchor="center")

        def work():
            ok = updater.apply_update(info["asset_url"], self.log, lambda f: self.call_ui(lambda: bar.set(f)))
            self.call_ui(lambda: self.root.after(1500, self.quit) if ok else (overlay.destroy(), setattr(self, "updating", False)))
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------- fechar / bandeja
    def request_close(self):
        if self.updating:
            return
        if sys.platform != "win32":
            self.quit()
            return
        if self.close_dialog is not None and self.close_dialog.winfo_exists():
            self.close_dialog.lift()
            return
        win = ctk.CTkToplevel(self.root)
        win.title("Fechar o bot")
        win.geometry("380x150")
        win.configure(fg_color=BG)
        win.transient(self.root)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        self.close_dialog = win

        def choose(action):
            win.destroy()
            if action == "tray":
                self.hide_to_tray()
            elif action == "quit":
                self.quit()

        hint = "Na bandeja o bot continua rodando." if self.runner.running else "Na bandeja o app fica escondido."
        ctk.CTkLabel(win, text=hint, text_color=TEXT).pack(padx=16, pady=(22, 16))
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack()
        btn(row, "Bandeja", lambda: choose("tray"), primary=True, width=100).pack(side="left", padx=5)
        btn(row, "Fechar de vez", lambda: choose("quit"), width=110).pack(side="left", padx=5)
        btn(row, "Cancelar", lambda: choose("cancel"), width=90).pack(side="left", padx=5)
        win.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))

    def _on_unmap(self, event):
        if event.widget is not self.root:
            return
        try:
            if self.root.state() == "iconic":
                self.root.after(50, self.hide_to_tray)
        except tk.TclError:
            pass

    def hide_to_tray(self):
        if sys.platform != "win32" or self.tray_icon is not None:
            return
        try:
            pystray = importlib.import_module("pystray")
            image_module = importlib.import_module("PIL.Image")
            icon_path = os.path.join(resource_dir(), "icon.ico")
            image = image_module.open(icon_path) if os.path.exists(icon_path) else image_module.new("RGB", (64, 64), ACCENT)
            menu = pystray.Menu(pystray.MenuItem("Abrir", lambda i, it: self.tray_queue.put("open"), default=True),
                                pystray.MenuItem("Fechar de vez", lambda i, it: self.tray_queue.put("quit")))
            self.tray_icon = pystray.Icon("DrakoriaBot", image, "DRAKORIA BOT", menu)
            self.tray_icon.run_detached()
        except Exception as error:
            self.tray_icon = None
            self.log(f"Bandeja indisponível ({error}) - o app fica só minimizado.")
            return
        self.root.withdraw()

    def _stop_tray(self):
        icon, self.tray_icon = self.tray_icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    def _poll_tray(self):
        try:
            while True:
                action = self.tray_queue.get_nowait()
                if action == "open":
                    self._stop_tray()
                    self.root.deiconify()
                    self.root.state("normal")
                    self.root.lift()
                elif action == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass
        self.root.after(300, self._poll_tray)

    def quit(self):
        self.runner.stop()
        self._stop_tray()
        self.root.destroy()


def main():
    root = ctk.CTk()
    app = App(root)
    if "--iniciar" in sys.argv:          # DrakoriaBot.exe --iniciar: ja abre rodando
        root.after(1500, app.toggle)
    root.mainloop()


if __name__ == "__main__":
    main()
