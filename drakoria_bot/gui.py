"""Interface do bot do Drakoria (CustomTkinter), simples e leve: Painel, Regras, Login, Log.
So' redesenha o que mudou; fechar (X) pergunta se guarda na bandeja ou fecha de vez."""
import datetime
import importlib
import os
import queue
import sys
import threading
import tkinter as tk

import customtkinter as ctk

from . import VERSION, config, hunts, updater
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
PHASES = {"hunting": "Caçando", "house": "Treinando (house)", "city": "Na cidade", "login": "Deslogado",
          "error": "Erro / reconectando", "unknown": "?", "-": "-"}
AUTO = "Automática (Melhor escolha do jogo)"
MODES = {"hunt": "Caçar sempre", "watch": "Só vigiar (relogin, avisos, loot)"}
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
        root.geometry("440x580")
        root.minsize(420, 520)
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
            self.hunt_names = [h["name"] for h in hunts.load_hunts()]
        except Exception:
            self.hunt_names = []

        self._build_header()
        self.tabs = ctk.CTkTabview(root, fg_color=PANEL, segmented_button_selected_color=ACCENT,
                                   segmented_button_selected_hover_color=ACCENT_HOVER, text_color=DARK_TEXT)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for name in ("Painel", "Regras", "Login", "Log"):
            self.tabs.add(name)
        self._build_panel(self.tabs.tab("Painel"))
        self._build_rules(self.tabs.tab("Regras"))
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
                    st.profit_hour, st.reserve, tuple((m.name, m.role, m.level, m.xp_pct, m.hp, m.hp_max) for m in st.members))
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
                self.stats.configure(text=(
                    f"Ouro {st.gold}   ·   Loot Pouch {loot}   ·   Reserva offline {st.reserve or '-'}\n"
                    f"XP/h {st.xp_hour or '-'}   ·   Lucro/h {st.profit_hour or '-'}\n"
                    f"Alvo: {snap.get('target') or '-'}   ·   Auto Sell {'Premium' if st.premium else 'Free'}"))
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

        label(0, "Modo")
        menu(0, list(MODES.values()), MODES.get(self.cfg["mode"], MODES["hunt"]),
             lambda v: self._set("mode", {b: a for a, b in MODES.items()}[v]))
        label(1, "Caça")
        menu(1, [AUTO] + self.hunt_names, self.cfg["hunt"] or AUTO, lambda v: self._set("hunt", "" if v == AUTO else v))
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
        self.relogin_var = tk.BooleanVar(value=bool(self.cfg["relogin"]))
        ctk.CTkCheckBox(grid, text="Relogin automático", variable=self.relogin_var, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        text_color=TEXT, command=lambda: self._set("relogin", self.relogin_var.get())
                        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=8)
        ctk.CTkLabel(tab, text="'Proteger drops de boss' fica sempre ligado. Sem Auto Sell o bot usa 'Vender tudo agora' "
                               "quando a Loot Pouch chega no número de itens. Insano+ pede level 250/450/700/1000.",
                     text_color=MUTED, wraplength=380, justify="left").pack(anchor="w", padx=10, pady=6)

    def _set(self, key, value):
        self.cfg[key] = value
        self.save()
        self.log(f"regra: {key} = {value or 'automática'}")

    def _set_loot(self, key, value):
        self.cfg["loot"][key] = value
        self.save()
        self.log(f"regra: loot.{key} = {value}")

    def _save_sell(self):
        try:
            value = max(1, int(self.sell_var.get()))
        except ValueError:
            self.sell_var.set(str(self.cfg["loot"]["sell_at_items"]))
            return
        if value != self.cfg["loot"]["sell_at_items"]:
            self._set_loot("sell_at_items", value)

    # ----------------------------------------------------------------- login
    def _build_login(self, tab):
        self.credentials = Credentials(os.path.join(ROOT, "credentials.json"))
        ctk.CTkLabel(tab, text="Login do Drakoria pra o bot entrar sozinho se o jogo cair ou deslogar. A senha fica "
                               "criptografada pelo Windows (só abre neste PC, no seu usuário) e nunca vai pro log.",
                     text_color=MUTED, wraplength=380, justify="left").pack(anchor="w", padx=8, pady=(8, 10))
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
