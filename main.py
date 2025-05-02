#!/usr/bin/env python3
import os
import subprocess
import threading
import time
import hashlib
import re

import customtkinter as ctk
from tkinter import messagebox, filedialog, Menu
from PIL import Image, ImageTk
from pygments import lex
from pygments.lexers import BashLexer

# macOS notifications (optional)
try:
    from pync import Notifier
except ImportError:
    Notifier = None

# ── APPLE/CROSSOVER-STYLE THEME ────────────────────────────────────────────────
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

BTN_PRIMARY   = "#0A84FF"
BTN_SECONDARY = "#30D158"
BTN_HOVER     = "#096dd9"
TXT_COLOR     = "black"

# ── I18N ──────────────────────────────────────────────────────────────────────
LANGUAGES = {
    "it": {
        "name":      "Italiano",
        "title":     "Gestore Trial di CrossOver",
        "execute":   "Esegui Ora",
        "install":   "Installa Auto-Reset",
        "uninstall": "Disinstalla Servizio",
        "help":      "Aiuto",
        "show_script":"Mostra Script",
        "export":    "Esporta Log",
        "clear":     "Pulisci Log",
        "filter":    "Filtra",
        "done":      "Completato!",
        "help_text": (
            "Questa app resetta la trial di CrossOver.\n\n"
            "• Esegui: reset manuale\n"
            "• Installa: servizio auto-reset\n"
            "• Disinstalla: rimuove il servizio\n\n"
            "Uso didattico ed etico solamente."
        ),
        "script_info":    "Contenuto di crack.sh:",
        "checksum_err":   "Attenzione: checksum non corrispondente!",
        "checksum_ok":    "Checksum verificato."
    },
    "en": {
        "name":      "English",
        "title":     "CrossOver Trial Manager",
        "execute":   "Execute Now",
        "install":   "Install Auto-Reset",
        "uninstall": "Uninstall Service",
        "help":      "Help",
        "show_script":"Show Script",
        "export":    "Export Log",
        "clear":     "Clear Log",
        "filter":    "Filter",
        "done":      "Done!",
        "help_text": (
            "This app resets the CrossOver trial.\n\n"
            "• Execute: run reset manually\n"
            "• Install: create auto-reset service\n"
            "• Uninstall: remove the service\n\n"
            "For educational/ethical use only."
        ),
        "script_info":    "crack.sh content:",
        "checksum_err":   "Warning: checksum mismatch!",
        "checksum_ok":    "Checksum verified."
    }
}
LANG = "it"
TXT = LANGUAGES[LANG]

# ── PATH allo script e checksum ────────────────────────────────────────────────
SCRIPT_PATH    = os.path.abspath(os.path.expanduser(
                   "~/Desktop/CrossOver Scripts/crack.sh"))
CHECKSUM_FILE  = SCRIPT_PATH + ".sha256"

class CrossOverApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        # set window background to match main_container
        self.configure(fg_color="#1E1E1E")

        # ── Window setup ────────────────────────────────────────────────────────
        self.title(TXT["title"])
        self.geometry("1000x700")
        self.resizable(True, True)

        # mantengo la variabile lingua
        self.lang_var = ctk.StringVar(value=TXT["name"])

        # elenco delle azioni con metodi
        actions = [
            ("execute",     self.execute_reset),
            ("install",     self.install_service),
            ("uninstall",   self.uninstall_service),
            ("show_script", self.show_script),
            ("export",      self.export_log),
            ("clear",       self.clear_log),
            ("help",        self.show_help),
        ]

        # init badges & log storage
        self.badges = {}
        self.action_counts = { key: {"success": 0, "error": 0} for key, _ in actions }
        self.big_buttons = {}

        # ── Menu bar ───────────────────────────────────────────────────────────
        self.menu_bar = Menu(self)
        self.config(menu=self.menu_bar)
        settings_menu = Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Settings", menu=settings_menu)
        self.mode_var = ctk.BooleanVar(value=(ctk.get_appearance_mode()=="Dark"))
        settings_menu.add_checkbutton(label="Dark Mode", variable=self.mode_var, command=self.toggle_mode)
        language_menu = Menu(settings_menu, tearoff=0)
        settings_menu.add_cascade(label="Language", menu=language_menu)
        for code, d in LANGUAGES.items():
            language_menu.add_radiobutton(
                label=d["name"],
                variable=self.lang_var,
                value=d["name"],
                command=lambda choice=d["name"]: self.change_language(choice)
            )

        # ── Main layout: Buttons left, Log right ───────────────────────────────
        self.main_container = ctk.CTkFrame(self, corner_radius=0, fg_color="#2C2C2E")
        self.main_container.pack(expand=True, fill="both", padx=10, pady=10)

        # Left frame: action buttons
        self.left_frame = ctk.CTkFrame(self.main_container, width=200, fg_color="#1E1E1E")
        self.left_frame.pack(side="left", fill="y", padx=(0,10))
        for key, cmd in actions:
            btn = ctk.CTkButton(
                self.left_frame, text=TXT[key], width=180, height=36,
                fg_color=(BTN_PRIMARY if key in ("execute","show_script","help","export")
                          else BTN_SECONDARY),
                hover_color=BTN_HOVER, text_color="white",
                command=cmd
            )
            btn.pack(pady=5)
            # store and attach badges
            self.big_buttons[key] = btn
            err_badge = ctk.CTkLabel(btn, text="", width=16, height=16,
                                     fg_color="red", text_color="white",
                                     corner_radius=8, font=ctk.CTkFont(size=10, weight="bold"))
            err_badge.place(relx=1.0, rely=0.0, x=-8, y=4)
            err_badge.place_forget()
            succ_badge = ctk.CTkLabel(btn, text="", width=16, height=16,
                                      fg_color="green", text_color="white",
                                      corner_radius=8, font=ctk.CTkFont(size=10, weight="bold"))
            succ_badge.place(relx=0.0, rely=0.0, x=4, y=4)
            succ_badge.place_forget()
            self.badges[key] = {"error": err_badge, "success": succ_badge}

        # Right frame: filter and log
        self.right_frame = ctk.CTkFrame(self.main_container, fg_color="#2C2C2E")
        self.right_frame.pack(side="right", expand=True, fill="both")
        filter_frame = ctk.CTkFrame(self.right_frame)
        filter_frame.pack(fill="x", pady=(0,5), padx=10)
        ctk.CTkLabel(filter_frame, text=TXT["filter"]).pack(side="left", padx=(0,5))

        # Search entry
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            filter_frame,
            textvariable=self.search_var,
            placeholder_text=TXT["filter"],
            fg_color="#1E1E1E",
            text_color="white",
            placeholder_text_color="#B0B0B0"
        )
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", self.filter_log)

        # Output box
        self.output_box = ctk.CTkTextbox(
            self.right_frame,
            corner_radius=10,
            fg_color="#1E1E1E",
            text_color="white"
        )
        self.output_box.configure(state="disabled")
        self.output_box.pack(expand=True, fill="both", padx=10, pady=(0,10))
        # configure tags for log levels
        for level, color in [("STEP","#FFA500"), ("INFO","#0A84FF"),
                             ("SUCCESS","#30D158"), ("WARNING","#FFD60A"),
                             ("ERROR","#FF453A")]:
            self.output_box.tag_config(level, foreground=color)


        # Iniziali
        self.full_log = []
        self.verify_checksum()

    # ── UTILITY ──────────────────────────────────────────────────────────────────

    def toggle_mode(self):
        mode = "Dark" if self.mode_var.get() else "Light"
        ctk.set_appearance_mode(mode)
        if mode == "Light":
            self.configure(fg_color="#F2F2F7")
            self.main_container.configure(fg_color="#EDEDED")
            self.left_frame.configure(fg_color="#F2F2F7")
            self.right_frame.configure(fg_color="#F2F2F7")
            self.search_entry.configure(
                fg_color="#EDEDED",
                text_color="black",
                placeholder_text_color="#666666"
            )
            self.output_box.configure(
                fg_color="#EDEDED",
                text_color="black"
            )
        else:
            self.configure(fg_color="#1E1E1E")
            self.main_container.configure(fg_color="#2C2C2E")
            self.left_frame.configure(fg_color="#1E1E1E")
            self.right_frame.configure(fg_color="#2C2C2E")
            self.search_entry.configure(
                fg_color="#1E1E1E",
                text_color="white",
                placeholder_text_color="#B0B0B0"
            )
            self.output_box.configure(
                fg_color="#1E1E1E",
                text_color="white"
            )

    def change_language(self, choice):
        # find language code and update TXT
        global LANG, TXT
        for code, d in LANGUAGES.items():
            if d["name"] == choice:
                LANG, TXT = code, LANGUAGES[code]
                break
        # update window title
        self.title(TXT["title"])
        # update big buttons
        for key, btn in self.big_buttons.items():
            btn.configure(text=TXT[key])
        # update search placeholder
        self.search_entry.configure(placeholder_text=TXT["filter"])

    def _append_text(self, txt: str):
        # store for filter
        self.full_log.append(txt)
        # strip ANSI escape sequences
        clean = re.sub(r'\x1B\[[0-9;]*[mK]', '', txt)
        # detect level tag
        tag = None
        m = re.match(r'^\[(STEP|INFO|SUCCESS|WARNING|ERROR)\]', clean)
        if m:
            tag = m.group(1)
        self.output_box.configure(state="normal")
        if tag:
            self.output_box.insert("end", clean, tag)
        else:
            self.output_box.insert("end", clean)
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def export_log(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt",
            filetypes=[("Text files","*.txt"),("All files","*.*")])
        if path:
            with open(path, "w") as f:
                f.write(self.output_box.get("1.0", "end"))
            messagebox.showinfo(TXT["done"], f"{TXT['export']} ✔")

    def verify_checksum(self):
        try:
            sha = hashlib.sha256()
            with open(SCRIPT_PATH, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha.update(chunk)
            current = sha.hexdigest()
            if os.path.exists(CHECKSUM_FILE):
                with open(CHECKSUM_FILE) as cf:
                    expected = cf.read().strip()
                if expected != current:
                    messagebox.showwarning(TXT["checksum_err"], TXT["checksum_err"])
                else:
                    self._append_text(f"[✓] {TXT['checksum_ok']}\n")
            else:
                with open(CHECKSUM_FILE, "w") as cf:
                    cf.write(current)
                self._append_text(f"[✓] {TXT['checksum_ok']} (saved)\n")
        except Exception as e:
            messagebox.showerror("Checksum Error", str(e))

    def _highlight_bash(self, code: str):
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        for ttype, value in lex(code, BashLexer()):
            if value.strip() == "":
                color = TXT_COLOR
            else:
                s = str(ttype)
                if s.startswith("Token.Comment"):
                    color = "#6a737d"
                elif s.startswith("Token.Keyword"):
                    color = BTN_HOVER
                elif s.startswith("Token.Literal.String"):
                    color = "#22863a"
                elif s.startswith("Token.Literal.Number"):
                    color = "#005cc5"
                elif s.startswith("Token.Operator"):
                    color = "#d73a49"
                else:
                    color = TXT_COLOR
            tag = str(ttype)
            self.output_box.tag_config(tag, foreground=color)
            self.output_box.insert("end", value, tag)
        self.output_box.configure(state="disabled")

    def run_bash(self, arg: str):
        def task():
            # reset badge counts
            self.action_counts[arg]["error"]   = 0
            self.action_counts[arg]["success"] = 0
            self.badges[arg]["error"].place_forget()
            self.badges[arg]["success"].place_forget()

            self._append_text(f"\n=== [{arg.upper()}] START ===\n")
            proc = subprocess.Popen(
                ["bash", SCRIPT_PATH, arg, LANG],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
            for line in proc.stdout:
                self._append_text(line)
                if "[ERROR]" in line:
                    self.action_counts[arg]["error"] += 1
                    bd = self.badges[arg]["error"]
                    bd.configure(text=str(self.action_counts[arg]["error"]))
                    bd.place(relx=1.0, rely=0.0, x=-10, y=5)
                if "[SUCCESS]" in line:
                    self.action_counts[arg]["success"] += 1
                    bd = self.badges[arg]["success"]
                    bd.configure(text=str(self.action_counts[arg]["success"]))
                    bd.place(relx=0.0, rely=0.0, x=5, y=5)
            proc.wait()
            self._append_text(f"=== [{arg.upper()}] END ===\n")
            messagebox.showinfo(TXT["done"], f"{TXT[arg]} ✔")
            if Notifier:
                Notifier.notify(f"{TXT[arg]} ✔", title=TXT["title"])
        threading.Thread(target=task, daemon=True).start()

    # ── ACTION METHODS ─────────────────────────────────────────────────────────
    def execute_reset(self):   self.run_bash("execute")
    def install_service(self): self.run_bash("install")
    def uninstall_service(self): self.run_bash("uninstall")

    def show_help(self):
        messagebox.showinfo(TXT["help"], TXT["help_text"])

    def show_script(self):
        if os.path.exists(SCRIPT_PATH):
            with open(SCRIPT_PATH, "r") as f:
                code = f.read()
            self._highlight_bash(code)
        else:
            self._append_text("[ERROR] Script non trovato.\n")

    def filter_log(self, event=None):
        query = self.search_var.get().lower()
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        for line in self.full_log:
            if query in line.lower():
                self.output_box.insert("end", line)
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def clear_log(self):
        self.full_log = []
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        self.output_box.configure(state="disabled")


if __name__ == "__main__":
    app = CrossOverApp()
    app.mainloop()