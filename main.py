#!/usr/bin/env python3
import os
import subprocess
import threading
import time
import hashlib
import re
import sys
import queue  # Aggiunto per comunicazione thread-safe
import json

import customtkinter as ctk
from tkinter import messagebox, filedialog, Menu, Toplevel # Aggiunto Toplevel
from PIL import Image  # Mantenuto per eventuali icone future; ImageTk rimosso
from pygments import lex
from pygments.lexers import BashLexer

# macOS notifications (optional)
PNYC_AVAILABLE = False
try:
    from pync import Notifier
    # test instantiation to catch installation errors
    Notifier("Test message", title="")  # will silently fail if broken
    PNYC_AVAILABLE = True
except Exception as e:
    import logging
    logging.debug(f"pync Notifier not available: {e}")
    Notifier = None
# ── Costanti aggiuntive ──────────────────────────────────────────────────────
PLIST_NAME = "com.example.crossovertrial.plist"
PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{PLIST_NAME}")
BADGE_SUCCESS_TIMEOUT_MS = 2500

# ── APPLE/CROSSOVER-STYLE THEME ────────────────────────────────────────────────
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# Definizioni Colori (potrebbero essere spostate in un dizionario theme)
COLOR_BACKGROUND_LIGHT = "#F2F2F7"
COLOR_BACKGROUND_DARK = "#1E1E1E"
COLOR_FRAME_LIGHT = "#EDEDED"
COLOR_FRAME_DARK = "#2C2C2E"
COLOR_TEXTBOX_LIGHT = "#FFFFFF"
COLOR_TEXTBOX_DARK = "#1E1E1E"
COLOR_TEXT_LIGHT = "black"
COLOR_TEXT_DARK = "white"
COLOR_PLACEHOLDER_LIGHT = "#666666"
COLOR_PLACEHOLDER_DARK = "#B0B0B0"

BTN_PRIMARY_FG = "#0A84FF"
BTN_SECONDARY_FG = "#30D158"
BTN_DANGER_FG = "#FF453A" # Aggiunto per Disinstalla
BTN_HOVER = "#096dd9"
BTN_TEXT_COLOR = "white"

TAG_COLORS = {
    "STEP": "#FFA500",
    "INFO": "#0A84FF",
    "SUCCESS": "#30D158",
    "WARNING": "#FFD60A",
    "ERROR": "#FF453A",
    "CMD": "#888888", # Aggiunto per comandi/output script
    "SCRIPT": "#FFFFFF" if ctk.get_appearance_mode() == "Dark" else "#000000" # Per il codice script
}

# ── I18N ──────────────────────────────────────────────────────────────────────
LANGUAGES = {
    "it": {
        "name":      "Italiano",
        "title":     "Gestore Trial di CrossOver",
        "execute":   "Esegui Reset", # Modificato per chiarezza
        "install":   "Installa Servizio", # Modificato per chiarezza
        "uninstall": "Disinstalla Servizio",
        "help":      "Aiuto",
        "show_script":"Mostra Script",
        "export":    "Esporta Log",
        "clear":     "Pulisci Log",
        "filter":    "Filtra Log...", # Modificato per chiarezza
        "done":      "Completato!",
        "error_occurred": "Errore durante l'esecuzione!",
        "status_ready": "Pronto.",
        "status_running": "Esecuzione '{action}'...",
        "status_checksum_ok": "Checksum Script OK.",
        "status_checksum_err": "ERRORE Checksum Script!",
        "status_checksum_na": "Checksum N/A.",
        "status_script_exec_error": "Errore esecuzione: {err}",
        "status_exported": "Log esportato.",
        "status_script_not_found": "ERRORE: Script script.sh non trovato!",
        "status_script_not_exec": "ERRORE: Script script.sh non eseguibile!",
        "help_text": (
            "Questa app resetta la trial di CrossOver.\n\n"
            "• Esegui Reset: Effettua un reset manuale ora.\n"
            "• Installa Servizio: Imposta un reset automatico all'avvio.\n"
            "• Disinstalla Servizio: Rimuove il servizio di auto-reset.\n\n"
            "Nota: L'installazione/disinstallazione richiede privilegi amministrativi.\n"
            "L'app è intesa per uso didattico ed etico."
        ),
        "script_viewer_title": "Visualizzatore Script - script.sh",
        "script_info":    "Contenuto di script.sh:", # Non più usato direttamente
        "checksum_err_msg": "Il checksum dello script 'script.sh' è cambiato rispetto all'ultima verifica. Potrebbe essere stato modificato o corrotto.",
        "checksum_ok_msg":    "Checksum verificato.",
        "checksum_saved_msg": "Checksum calcolato e salvato.",
        "error_title": "Errore",
        "warning_title": "Attenzione",
        "checksum_mismatch_title": "Checksum Non Corrisponde",
        "checksum_mismatch_ask_fix": "Il checksum per '{script_name}' non corrisponde.\nLo script potrebbe essere corrotto o modificato.\n\nTi fidi della versione attuale dello script e vuoi aggiornare il file checksum?",
        "checksum_updated_msg": "File checksum aggiornato.",
        "checksum_update_error_msg": "Impossibile aggiornare il file checksum.",
        "checksum_not_updated_msg": "Checksum non corrispondente ignorato dall'utente.",
        "checksum_missing_title": "File Checksum Mancante",
        "checksum_missing_ask_create": "File checksum per '{script_name}' non trovato.\n\nVuoi crearne uno basato sulla versione attuale dello script?",
        "checksum_created_msg": "File checksum creato.",
        "checksum_create_error_msg": "Impossibile creare il file checksum.",
        "checksum_not_created_msg": "File checksum non creato."
    },
    "en": {
        "name":      "English",
        "title":     "CrossOver Trial Manager",
        "execute":   "Run Reset", # Changed for clarity
        "install":   "Install Service", # Changed for clarity
        "uninstall": "Uninstall Service",
        "help":      "Help",
        "show_script":"Show Script",
        "export":    "Export Log",
        "clear":     "Clear Log",
        "filter":    "Filter Log...", # Changed for clarity
        "done":      "Done!",
        "error_occurred": "Error during execution!",
        "status_ready": "Ready.",
        "status_running": "Running '{action}'...",
        "status_checksum_ok": "Script Checksum OK.",
        "status_checksum_err": "ERROR Script Checksum!",
        "status_checksum_na": "Checksum N/A.",
        "status_script_exec_error": "Execution error: {err}",
        "status_exported": "Log exported.",
        "status_script_not_found": "ERROR: script.sh script not found!",
        "status_script_not_exec": "ERROR: script.sh script not executable!",
        "help_text": (
            "This app resets the CrossOver trial.\n\n"
            "• Run Reset: Perform a manual reset now.\n"
            "• Install Service: Set up automatic reset on startup.\n"
            "• Uninstall Service: Remove the auto-reset service.\n\n"
            "Note: Install/Uninstall requires administrative privileges.\n"
            "This app is for educational/ethical use only."
        ),
        "script_viewer_title": "Script Viewer - script.sh",
        "script_info":    "script.sh content:", # No longer used directly
        "checksum_err_msg": "The checksum of 'script.sh' has changed since the last check. It might have been modified or corrupted.",
        "checksum_ok_msg":    "Checksum verified.",
        "checksum_saved_msg": "Checksum calculated and saved.",
        "error_title": "Error",
        "warning_title": "Warning",
        "checksum_mismatch_title": "Checksum Mismatch",
        "checksum_mismatch_ask_fix": "Checksum mismatch for '{script_name}'.\nThe script may be corrupted or modified.\n\nDo you trust the current script version and want to update the checksum file?",
        "checksum_updated_msg": "Checksum file updated.",
        "checksum_update_error_msg": "Failed to update checksum file.",
        "checksum_not_updated_msg": "Checksum mismatch ignored by user.",
        "checksum_missing_title": "Checksum File Missing",
        "checksum_missing_ask_create": "Checksum file for '{script_name}' not found.\n\nDo you want to create one based on the current script version?",
        "checksum_created_msg": "Checksum file created.",
        "checksum_create_error_msg": "Failed to create checksum file.",
        "checksum_not_created_msg": "Checksum file not created.",
    }
}
# Imposta lingua iniziale (potrebbe essere letto da un file di config)
LANG = "it"
TXT = LANGUAGES[LANG]

# ── PATH allo script e checksum ────────────────────────────────────────────────
def get_script_path():
    """Determina il percorso base per i file di dati (normale o bundle PyInstaller)"""
    if getattr(sys, "frozen", False):
        # running in PyInstaller bundle
        base_path = sys._MEIPASS
    else:
        # running normally
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, "script.sh")

SCRIPT_PATH   = get_script_path()
CHECKSUM_FILE = SCRIPT_PATH + ".sha256"

# Coda per i log dal thread al main loop
log_queue = queue.Queue()

class CrossOverApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.checksum_valid = None  # Stato del checksum: True, False, None (N/A)
        self.script_executable = False  # Stato eseguibilità script
        self.script_found = False  # Stato esistenza script
        self.current_action = None  # Traccia l'azione in corso
        self.service_active = False  # Stato del servizio (LaunchAgent)
        self.bottles_path_override = None  # Eventuale override percorso bottles

        # ── Window setup ────────────────────────────────────────────────────────
        self.title(TXT["title"])
        self.geometry("1000x700")  # Dimensioni iniziali
        self.minsize(800, 500)  # Dimensioni minime
        self.resizable(True, True)
        self._set_appearance()  # Applica colori iniziali

        # Variabile per lingua e dark mode
        self.lang_var = ctk.StringVar(value=TXT["name"])
        self.mode_var = ctk.BooleanVar(value=(ctk.get_appearance_mode() == "Dark"))

        # Elenco delle azioni con metodi, chiavi i18n e colori
        self.actions = [
            {"key": "execute",   "cmd": self.execute_reset,       "color": BTN_PRIMARY_FG},
            {"key": "install",   "cmd": self.install_service,     "color": BTN_SECONDARY_FG},
            {"key": "uninstall", "cmd": self.uninstall_service,   "color": BTN_DANGER_FG},  # Colore diverso
            {"key": "refresh_status", "cmd": self.refresh_status, "color": BTN_PRIMARY_FG},
            {"key": "show_script", "cmd": self.show_script_window, "color": BTN_PRIMARY_FG},
            {"key": "export",    "cmd": self.export_log,          "color": BTN_PRIMARY_FG},
            {"key": "clear",     "cmd": self.clear_log,           "color": BTN_PRIMARY_FG},
            {"key": "help",      "cmd": self.show_help,           "color": BTN_PRIMARY_FG},
        ]
        self.action_buttons = {}  # Dizionario per i bottoni principali
        self.badges = {}  # Dizionario per i badge { action_key: { "success": ctk_label, "error": ctk_label } }

        # ── Menu bar ───────────────────────────────────────────────────────────
        self._create_menu()

        # ── Main layout ────────────────────────────────────────────────────────
        self._create_ui_layout()

        # ── Inizializzazione ─────────────────────────────────────────────────────
        self.full_log = []  # Lista per mantenere tutto il log per il filtro
        self._update_ui_colors()  # Applica colori basati sulla modalità
        self._check_script_status()  # Controlla script all'avvio
        self.update_status_bar()  # Aggiorna status bar iniziale
        self.after(100, self._process_log_queue)  # Avvia il processore della coda log

    def _create_ui_layout(self):
        """Crea il layout principale dell'interfaccia utente."""
        self.grid_columnconfigure(0, weight=0)  # Colonna bottoni non espandibile
        self.grid_columnconfigure(1, weight=1)  # Colonna log espandibile
        self.grid_rowconfigure(0, weight=1)     # Riga principale espandibile
        self.grid_rowconfigure(1, weight=0)     # Riga status bar non espandibile

        # Left frame: action buttons
        self.left_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        self.left_frame.grid_propagate(False)  # Impedisce al frame di restringersi

        for i, action in enumerate(self.actions):
            key = action["key"]
            cmd = action["cmd"]
            color = action["color"]
            # Placeholder per icona (da sostituire con CTkImage se hai le icone)
            btn = ctk.CTkButton(
                self.left_frame,
                text=TXT.get(key, key),
                compound="left",
                anchor="w",
                width=180, height=36,
                fg_color=color,
                hover_color=BTN_HOVER,
                text_color=BTN_TEXT_COLOR,
                command=cmd
            )
            btn.pack(pady=8, padx=10, anchor="n")
            self.action_buttons[key] = btn
            self._create_badges(btn, key)

        # Service status label
        self.service_status_label = ctk.CTkLabel(self.left_frame, text="Service: ...", anchor="w")
        self.service_status_label.pack(pady=(15, 0), padx=10, anchor="w")

        # Right frame: filter and log
        self.right_frame = ctk.CTkFrame(self, corner_radius=0)
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        self.right_frame.grid_rowconfigure(1, weight=1)
        self.right_frame.grid_columnconfigure(0, weight=1)

        # Filter frame
        filter_frame = ctk.CTkFrame(self.right_frame)
        filter_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10), padx=10)
        filter_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(filter_frame, text=TXT["filter"] + ":").grid(row=0, column=0, padx=(0, 5))
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            filter_frame,
            textvariable=self.search_var,
            placeholder_text=TXT["filter"],
        )
        self.search_entry.grid(row=0, column=1, sticky="ew")
        self.search_entry.bind("<KeyRelease>", self.filter_log)

        # Output box
        self.output_box = ctk.CTkTextbox(self.right_frame, corner_radius=6)
        self.output_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 0))
        self.output_box.configure(state="disabled")
        self._configure_log_tags()

        # ── Status Bar ──────────────────────────────────────────────────────────
        self.status_bar = ctk.CTkFrame(self, height=25, corner_radius=0)
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        self.status_label = ctk.CTkLabel(self.status_bar, text=TXT["status_ready"], anchor="w")
        self.status_label.pack(side="left", padx=10)
        self.checksum_status_label = ctk.CTkLabel(self.status_bar, text="", anchor="e", width=150)
        self.checksum_status_label.pack(side="right", padx=10)

    # ── UI Setup & Update Methods ──────────────────────────────────────────────

    def _create_menu(self):
        """Crea la barra dei menu."""
        self.menu_bar = Menu(self)
        self.config(menu=self.menu_bar)

        # Menu Settings
        settings_menu = Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Settings", menu=settings_menu) # TODO: i18n?

        # Dark Mode Toggle
        settings_menu.add_checkbutton(label="Dark Mode", variable=self.mode_var, command=self.toggle_mode) # TODO: i18n?

        # Language Submenu
        language_menu = Menu(settings_menu, tearoff=0)
        settings_menu.add_cascade(label="Language", menu=language_menu) # TODO: i18n?
        for code, d in LANGUAGES.items():
            language_menu.add_radiobutton(
                label=d["name"],
                variable=self.lang_var,
                value=d["name"],
                command=lambda choice=d["name"]: self.change_language(choice)
            )

        {"key": "generate_checksum", "cmd": self.generate_checksum_file, "color": BTN_PRIMARY_FG},

    def _create_badges(self, parent_button, action_key):
        """Crea i badge per un dato bottone e chiave azione."""
        badge_style = {"width": 16, "height": 16, "text_color": "white", "corner_radius": 8, "font": ctk.CTkFont(size=10, weight="bold")}
        err_badge = ctk.CTkLabel(parent_button, text="", fg_color=TAG_COLORS["ERROR"], **badge_style)
        succ_badge = ctk.CTkLabel(parent_button, text="", fg_color=TAG_COLORS["SUCCESS"], **badge_style)
        self.badges[action_key] = {"error": err_badge, "success": succ_badge}
        # Posizionati ma nascosti
        err_badge.place(relx=1.0, rely=0.0, x=-5, y=5, anchor="ne")
        succ_badge.place(relx=0.0, rely=0.0, x=5, y=5, anchor="nw")
        err_badge.lower() # Nascondi inizialmente
        succ_badge.lower()

    def _update_badge(self, action_key, badge_type, count):
        """Aggiorna un badge specifico."""
        if action_key in self.badges and badge_type in self.badges[action_key]:
            badge = self.badges[action_key][badge_type]
            if count > 0:
                badge.configure(text=str(count))
                badge.lift() # Rendi visibile
            else:
                badge.configure(text="")
                badge.lower() # Nascondi

    def _reset_badges(self, action_key):
        """Resetta i badge per un'azione."""
        self._update_badge(action_key, "success", 0)
        self._update_badge(action_key, "error", 0)

    def _configure_log_tags(self):
        """Configura i tag di colore per il CtkTextbox."""
        for level, color in TAG_COLORS.items():
            self.output_box.tag_config(level, foreground=color)

    def _set_appearance(self):
        """Imposta i colori globali dell'app."""
        mode = ctk.get_appearance_mode()
        fg_color = COLOR_BACKGROUND_DARK if mode == "Dark" else COLOR_BACKGROUND_LIGHT
        self.configure(fg_color=fg_color)

    def _update_ui_colors(self):
        """Aggiorna i colori dei widget in base alla modalità."""
        mode = ctk.get_appearance_mode()
        is_dark = (mode == "Dark")

        # Colori base
        bg_color = COLOR_BACKGROUND_DARK if is_dark else COLOR_BACKGROUND_LIGHT
        frame_color = COLOR_FRAME_DARK if is_dark else COLOR_FRAME_LIGHT
        textbox_color = COLOR_TEXTBOX_DARK if is_dark else COLOR_TEXTBOX_LIGHT
        text_color = COLOR_TEXT_DARK if is_dark else COLOR_TEXT_LIGHT
        placeholder_color = COLOR_PLACEHOLDER_DARK if is_dark else COLOR_PLACEHOLDER_LIGHT
        script_color = COLOR_TEXT_DARK if is_dark else COLOR_TEXT_LIGHT

        # Applica colori
        self.configure(fg_color=bg_color)
        self.left_frame.configure(fg_color=frame_color)
        self.right_frame.configure(fg_color=frame_color)
        self.status_bar.configure(fg_color=frame_color)
        self.status_label.configure(text_color=text_color)
        self.checksum_status_label.configure(text_color=text_color)
        if hasattr(self, "service_status_label"):
            self.service_status_label.configure(text_color=text_color)
        self.search_entry.configure(
            fg_color=textbox_color,
            text_color=text_color,
            border_color=frame_color,
            placeholder_text_color=placeholder_color
        )
        self.output_box.configure(
            fg_color=textbox_color,
            text_color=text_color,
            border_color=frame_color
        )
        TAG_COLORS["SCRIPT"] = script_color
        self._configure_log_tags()
        self.filter_log()


    def toggle_mode(self):
        """Cambia tra modalità chiara e scura."""
        mode = "Dark" if self.mode_var.get() else "Light"
        ctk.set_appearance_mode(mode)
        self._update_ui_colors()

    def change_language(self, choice):
        """Cambia la lingua dell'interfaccia."""
        global LANG, TXT
        prev_lang = LANG
        for code, d in LANGUAGES.items():
            if d["name"] == choice:
                LANG, TXT = code, LANGUAGES[code]
                break

        if prev_lang != LANG:
            # Aggiorna testi UI
            self.title(TXT["title"])
            for action in self.actions:
                if action["key"] in self.action_buttons:
                    self.action_buttons[action["key"]].configure(text=TXT[action["key"]])
            self.search_entry.configure(placeholder_text=TXT["filter"])
            self.update_status_bar() # Aggiorna testi status bar
            # Aggiorna menu (potrebbe richiedere ricreazione o configure)
            # TODO: aggiornare etichette menu se necessario

    # ── Log & Filtering Methods ────────────────────────────────────────────────

    def _process_log_queue(self):
        """Processa i messaggi dalla coda log nel thread principale."""
        try:
            while True: # Processa tutti i messaggi disponibili
                log_entry = log_queue.get_nowait()
                self._append_text_to_gui(log_entry["text"], log_entry["log_level"])
        except queue.Empty:
            pass # Coda vuota, normale
        finally:
            # Ripianifica il controllo della coda
            self.after(100, self._process_log_queue)

    def _log(self, text: str, level: str = "CMD"):
        """Aggiunge un messaggio alla coda log per l'aggiornamento GUI."""
        log_queue.put({"text": text, "log_level": level})

    def _append_text_to_gui(self, text: str, log_level: str = "CMD"):
        """Aggiunge testo al box di output (chiamato dal thread GUI)."""
        # Aggiungi alla history completa per il filtro
        self.full_log.append(text)

        # Pulisci da codici ANSI (anche se non dovrebbero esserci più)
        clean_text = re.sub(r'\x1B\[[0-9;]*[mK]', '', text).rstrip()
        if not clean_text: return # Non aggiungere linee vuote dopo rstrip

        # Determina il tag principale
        effective_tag = log_level
        match = re.match(r'^\[(STEP|INFO|SUCCESS|WARNING|ERROR)\]', clean_text)
        if match:
            effective_tag = match.group(1)

        # Inserisci nel textbox
        self.output_box.configure(state="normal")
        if effective_tag in TAG_COLORS:
            self.output_box.insert("end", clean_text + "\n", effective_tag)
        else:
            self.output_box.insert("end", clean_text + "\n", "CMD") # Tag di default
        self.output_box.see("end")
        self.output_box.configure(state="disabled")


    def filter_log(self, event=None):
        """Filtra il contenuto del log box."""
        query = self.search_var.get().lower()
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        for line in self.full_log:
            if query in line.lower():
                # Reinserisci la linea, riapplicando il tag corretto se presente
                clean_line = re.sub(r'\x1B\[[0-9;]*[mK]', '', line).rstrip()
                if not clean_line: continue

                effective_tag = "CMD" # Default
                match = re.match(r'^\[(STEP|INFO|SUCCESS|WARNING|ERROR)\]', clean_line)
                if match:
                    effective_tag = match.group(1)

                if effective_tag in TAG_COLORS:
                     self.output_box.insert("end", clean_line + "\n", effective_tag)
                else:
                     self.output_box.insert("end", clean_line + "\n", "CMD")

        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def clear_log(self):
        """Pulisce il log box e la history."""
        if self.current_action:
            return  # Non pulire se un'azione è in corso

        self.full_log = []
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        self.output_box.configure(state="disabled")
        # Resetta anche tutti i badge
        for action in self.actions:
            self._reset_badges(action["key"])
        # Reset badge anche per azioni principali se non già inclusi
        for key in ["execute", "install", "uninstall"]:
            self._reset_badges(key)

    def export_log(self):
        """Esporta il contenuto del log box su file."""
        if self.current_action: return

        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Export Log" # TODO: i18n
        )
        if path:
            try:
                with open(path, "w", encoding='utf-8') as f:
                    f.write(self.output_box.get("1.0", "end"))
                self.update_status_bar(TXT["status_exported"])
                messagebox.showinfo(TXT["done"], TXT["status_exported"])
            except Exception as e:
                messagebox.showerror(TXT["error_title"], f"Failed to export log: {e}")
                self.update_status_bar(f"Export failed: {e}")

    # ── Script Interaction Methods ─────────────────────────────────────────────

    def _check_script_status(self):
        """Verifica l'esistenza e l'eseguibilità dello script."""
        self.script_found = os.path.exists(SCRIPT_PATH)
        if self.script_found:
            self.script_executable = os.access(SCRIPT_PATH, os.X_OK)
            if not self.script_executable:
                 self._log(f"[ERROR] {TXT['status_script_not_exec']}", "ERROR")
                 # Prova a renderlo eseguibile
                 try:
                     os.chmod(SCRIPT_PATH, os.stat(SCRIPT_PATH).st_mode | 0o111) # Aggiunge permessi x
                     self.script_executable = os.access(SCRIPT_PATH, os.X_OK)
                     if self.script_executable:
                         self._log(f"[INFO] Resi eseguibili i permessi per {SCRIPT_PATH}", "INFO")
                     else:
                          self._log(f"[ERROR] Impossibile rendere eseguibile {SCRIPT_PATH}", "ERROR")
                 except Exception as e:
                     self._log(f"[ERROR] Errore nel cambiare permessi: {e}", "ERROR")

            self.verify_checksum() # Verifica checksum solo se lo script esiste
        else:
            self._log(f"[ERROR] {TXT['status_script_not_found']}", "ERROR")
            self.script_executable = False
            self.checksum_valid = None # Non applicabile

        # Disabilita bottoni se lo script non è utilizzabile
        can_run_script = self.script_found and self.script_executable
        for key in ["execute", "install", "uninstall", "show_script"]:
             if key in self.action_buttons:
                 self.action_buttons[key].configure(state="normal" if can_run_script else "disabled")

    def _update_checksum_file(self, checksum_path: str, hash_to_write: str) -> bool:
        """
        Scrive l'hash fornito nel file checksum specificato.
        Restituisce True se l'operazione ha successo, False altrimenti.
        """
        try:
            with open(checksum_path, "w") as f:
                f.write(hash_to_write)
            logging.info(f"Checksum aggiornato/creato con successo: {checksum_path}")
            return True
        except Exception as e:
            self._log(f"[ERROR] Impossibile scrivere nel file checksum '{checksum_path}': {e}", "ERROR")
            messagebox.showerror(TXT["error_title"], f"Failed to write checksum file:\n{e}")
            return False

    def verify_checksum(self):
        """
        Verifica il checksum SHA256 dello script.
        - Se il file .sha256 manca, chiede all'utente se vuole crearlo.
        - Se il file .sha256 esiste ma non corrisponde, chiede all'utente se vuole aggiornarlo.
        """
        import logging
        # Rinominiamo le variabili per chiarezza interna alla funzione
        script_to_check_path = get_script_path()
        checksum_storage_path = script_to_check_path + ".sha256"

        self.checksum_valid = None # Inizializza come indeterminato

        if not os.path.exists(script_to_check_path):
            self._log(f"[ERROR] File script '{script_to_check_path}' non trovato durante verifica checksum.", "ERROR")
            self.checksum_valid = None # Non applicabile se lo script non c'è
            # Aggiorna subito la status bar per mostrare l'errore script
            self.after(0, self.update_status_bar)
            return # Non possiamo fare altro

        try:
            # Calcola l'hash dello script corrente
            sha = hashlib.sha256()
            with open(script_to_check_path, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    sha.update(chunk)
            current_hash = sha.hexdigest()
            logging.debug(f"Hash calcolato per {script_to_check_path}: {current_hash}")

            # Verifica se il file checksum esiste
            if os.path.exists(checksum_storage_path):
                # Il file esiste, leggilo e confronta
                with open(checksum_storage_path, "r") as cf:
                    expected_hash = cf.read().strip()
                logging.debug(f"Hash atteso da {checksum_storage_path}: {expected_hash}")

                if expected_hash == current_hash:
                    # Match! Tutto OK.
                    self.checksum_valid = True
                    self._log(f"[INFO] {TXT['checksum_ok_msg']} ({os.path.basename(script_to_check_path)})", "INFO")
                else:
                    # Mismatch! Notifica e chiedi se fixare.
                    self.checksum_valid = False
                    self._log(f"[ERROR] Checksum mismatch per {os.path.basename(script_to_check_path)}!", "ERROR")
                    self._log(f"[ERROR]   Atteso  : {expected_hash}", "ERROR")
                    self._log(f"[ERROR]   Calcolato: {current_hash}", "ERROR")

                    # Prepara i testi i18n (aggiungili al dizionario LANGUAGES)
                    q_title = TXT.get("checksum_mismatch_title", "Checksum Mismatch")
                    q_msg = TXT.get("checksum_mismatch_ask_fix",
                                    f"Checksum mismatch for '{os.path.basename(script_to_check_path)}'.\n"
                                    f"The script may be corrupted or modified.\n\n"
                                    f"Do you trust the current script version and want to update the checksum file?")

                    user_choice = messagebox.askyesno(q_title, q_msg)

                    if user_choice:
                        # Utente vuole aggiornare (fixare)
                        if self._update_checksum_file(checksum_storage_path, current_hash):
                            self.checksum_valid = True # Ora è valido perché l'abbiamo aggiornato
                            self._log(f"[INFO] {TXT.get('checksum_updated_msg', 'Checksum file updated.')}", "INFO")
                        else:
                            # Errore durante l'aggiornamento, rimane False
                            self._log(f"[ERROR] {TXT.get('checksum_update_error_msg', 'Failed to update checksum file.')}", "ERROR")
                    else:
                        # Utente non vuole aggiornare, rimane False
                        self._log(f"[WARNING] {TXT.get('checksum_not_updated_msg', 'Checksum mismatch ignored by user.')}", "WARNING")

            else:
                # Il file checksum NON esiste. Chiedi se crearlo.
                self.checksum_valid = None # Non è né valido né invalido, semplicemente mancante
                self._log(f"[WARNING] File checksum '{os.path.basename(checksum_storage_path)}' non trovato.", "WARNING")

                # Prepara i testi i18n (aggiungili al dizionario LANGUAGES)
                q_title = TXT.get("checksum_missing_title", "Checksum File Missing")
                q_msg = TXT.get("checksum_missing_ask_create",
                                f"Checksum file for '{os.path.basename(script_to_check_path)}' not found.\n\n"
                                f"Do you want to create one based on the current script version?")

                user_choice = messagebox.askyesno(q_title, q_msg)

                if user_choice:
                     # Utente vuole creare il file
                    if self._update_checksum_file(checksum_storage_path, current_hash):
                        self.checksum_valid = True # Appena creato, quindi valido rispetto alla versione attuale
                        self._log(f"[INFO] {TXT.get('checksum_created_msg', 'Checksum file created.')}", "INFO")
                    else:
                         # Errore durante la creazione, rimane None
                        self._log(f"[ERROR] {TXT.get('checksum_create_error_msg', 'Failed to create checksum file.')}", "ERROR")
                else:
                    # Utente non vuole creare, rimane None
                     self._log(f"[INFO] {TXT.get('checksum_not_created_msg', 'Checksum file not created.')}", "INFO")


        except Exception as e:
            self.checksum_valid = None # Errore generico durante il processo
            self._log(f"[ERROR] Errore durante verifica/gestione checksum: {e}", "ERROR")
            # Potresti voler mostrare un messagebox anche qui se l'errore è critico
            messagebox.showerror(TXT["error_title"], f"Checksum Error: {e}")

        # Aggiorna la status bar alla fine di tutte le operazioni
        # Usiamo self.after per essere sicuri che sia eseguito nel thread principale
        self.after(0, self.update_status_bar)

    def update_status_bar(self, message=None):
        """Aggiorna la barra di stato."""
        # Messaggio principale
        if message:
            self.status_label.configure(text=message)
        elif self.current_action:
             self.status_label.configure(text=TXT["status_running"].format(action=TXT[self.current_action]))
        else:
            self.status_label.configure(text=TXT["status_ready"])

        # Stato Checksum
        if self.checksum_valid is True:
            self.checksum_status_label.configure(text=TXT["status_checksum_ok"], text_color=TAG_COLORS["SUCCESS"])
        elif self.checksum_valid is False:
            self.checksum_status_label.configure(text=TXT["status_checksum_err"], text_color=TAG_COLORS["ERROR"])
        else:
            # Se None (es. script non trovato o errore)
            if not self.script_found:
                 self.checksum_status_label.configure(text=TXT["status_script_not_found"], text_color=TAG_COLORS["ERROR"])
            else:
                 self.checksum_status_label.configure(text=TXT["status_checksum_na"], text_color=TAG_COLORS["WARNING"])


    def _set_ui_busy(self, busy: bool, action_key: str):
        """Abilita/Disabilita i controlli UI durante l'esecuzione."""
        self.current_action = action_key if busy else None
        state = "disabled" if busy else "normal"
        for key, button in self.action_buttons.items():
            # Permetti sempre Clear e Help (se non è già busy)
            if key in ["clear", "help"] and not busy:
                 button.configure(state="normal")
            # Disabilita export se busy
            elif key == "export" and busy:
                 button.configure(state="disabled")
            # Gestisci tutti gli altri bottoni
            elif key not in ["clear", "help"]:
                 button.configure(state=state)

        # Abilita/disabilita filtro e clear
        self.search_entry.configure(state=state)
        self.action_buttons["clear"].configure(state=state if not busy else "disabled") # Disabilita clear se busy

        self.update_status_bar() # Aggiorna testo status bar (es. "Running...")

    def generate_checksum_file(self):
        """Genera il file .sha256 per lo script corrente."""
        try:
            sha = hashlib.sha256()
            with open(SCRIPT_PATH, "rb") as f:
                while chunk := f.read(8192):
                    sha.update(chunk)
            current_hash = sha.hexdigest()

            with open(CHECKSUM_FILE, "w") as f:
                f.write(current_hash)

            self._log(f"[INFO] Checksum generato e salvato: {CHECKSUM_FILE}", "INFO")
            messagebox.showinfo("Checksum", f"Checksum salvato correttamente in:\n{CHECKSUM_FILE}")
        except Exception as e:
            self._log(f"[ERROR] Impossibile generare il file checksum: {e}", "ERROR")
            messagebox.showerror("Errore", f"Errore nella creazione del file .sha256:\n{e}")

    def run_bash_script(self, action_key: str):
        """Esegue lo script bash in un thread separato."""
        if self.current_action:
            return  # Impedisce esecuzioni multiple
        if not self.script_found or not self.script_executable:
            self._log(f"[ERROR] Impossibile eseguire lo script (non trovato o non eseguibile).", "ERROR")
            messagebox.showerror(TXT["error_title"], TXT["status_script_not_found"] if not self.script_found else TXT["status_script_not_exec"])
            return

        self._set_ui_busy(True, action_key)
        self._reset_badges(action_key)
        success_count = 0
        error_count = 0

        bottles_path = self.bottles_path_override
        lang_param = LANG

        def task():
            nonlocal success_count, error_count
            return_code = -1
            try:
                self._log(f"\n=== [{action_key.upper()}] START ===\n", "STEP")
                command = ["bash", SCRIPT_PATH, action_key, lang_param]
                if bottles_path:
                    command.append(bottles_path)
                self._log(f"[CMD] Esecuzione: {' '.join(command)}", "CMD")

                proc = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=1
                )

                for line in iter(proc.stdout.readline, ''):
                    self._log(line, "CMD")
                    if "[ERROR]" in line:
                        error_count += 1
                        self.after(0, lambda cnt=error_count: self._update_badge(action_key, "error", cnt))
                    if "[SUCCESS]" in line:
                        success_count += 1
                        self.after(0, lambda cnt=success_count: self._update_badge(action_key, "success", cnt))

                proc.stdout.close()
                return_code = proc.wait()

                if return_code == 0:
                    self._log(f"[SUCCESS] Script completato con successo (Codice: {return_code}).", "SUCCESS")
                    if success_count == 0:
                        success_count = 1
                        self.after(0, lambda cnt=success_count: self._update_badge(action_key, "success", cnt))
                else:
                    self._log(f"[ERROR] Script terminato con errore (Codice: {return_code}).", "ERROR")
                    if error_count == 0:
                        error_count = 1
                        self.after(0, lambda cnt=error_count: self._update_badge(action_key, "error", cnt))

            except FileNotFoundError:
                self._log(f"[ERROR] Comando 'bash' o script '{SCRIPT_PATH}' non trovato.", "ERROR")
                return_code = -1
            except Exception as e:
                self._log(f"[ERROR] Errore imprevisto durante l'esecuzione: {e}", "ERROR")
                return_code = -1
            finally:
                self._log(f"=== [{action_key.upper()}] END (Exit Code: {return_code}) ===\n", "STEP")
                self.after(0, self._finalize_script_run, action_key, return_code)

        thread = threading.Thread(target=task, daemon=True)
        thread.start()


    def _finalize_script_run(self, action_key: str, return_code: int):
        """Operazioni da eseguire nel thread GUI dopo la fine dello script."""
        self._set_ui_busy(False, action_key)
        import logging
        if return_code == 0:
            messagebox.showinfo(TXT["done"], f"{TXT[action_key]} - {TXT['done']}")
            if PNYC_AVAILABLE and Notifier:
                try:
                    Notifier.notify(f"{TXT[action_key]} - {TXT['done']}", title=TXT["title"])
                except Exception as e:
                    logging.debug(f"pync Notifier notify failed: {e}")
            # Rimuovi badge success dopo timeout
            def clear_success_badge():
                self._update_badge(action_key, "success", 0)
            self.after(BADGE_SUCCESS_TIMEOUT_MS, clear_success_badge)
        else:
            messagebox.showerror(TXT["error_title"], f"{TXT[action_key]} - {TXT['error_occurred']}")
            if PNYC_AVAILABLE and Notifier:
                try:
                    Notifier.notify(f"{TXT[action_key]} - {TXT['error_occurred']}", title=TXT["error_title"])
                except Exception as e:
                    logging.debug(f"pync Notifier notify failed: {e}")
        self.update_status_bar()
    def refresh_status(self):
        """Aggiorna lo stato del servizio e altri dettagli."""
        # Placeholder: implementare logica reale per controllare servizio
        service_exists = os.path.exists(PLIST_PATH)
        self.service_active = service_exists
        txt = f"Service: {'Active' if service_exists else 'Not installed'}"
        if hasattr(self, "service_status_label"):
            self.service_status_label.configure(text=txt)


    # ── Action Methods (Wrapper) ───────────────────────────────────────────────
    def execute_reset(self):   self.run_bash_script("execute")
    def install_service(self): self.run_bash_script("install")
    def uninstall_service(self): self.run_bash_script("uninstall")

    def show_help(self):
        """Mostra il messaggio di aiuto."""
        messagebox.showinfo(TXT["help"], TXT["help_text"])

    def show_script_window(self):
        """Mostra il contenuto dello script in una finestra separata."""
        if not self.script_found:
             messagebox.showerror(TXT["error_title"], TXT["status_script_not_found"])
             return

        try:
            with open(SCRIPT_PATH, "r", encoding='utf-8') as f:
                script_content = f.read()

            # Crea la finestra Toplevel
            script_win = Toplevel(self)
            script_win.title(TXT["script_viewer_title"])
            script_win.geometry("800x600")
            script_win.transient(self) # Lega alla finestra principale
            script_win.grab_set() # Rendi modale

            # Textbox per lo script
            script_textbox = ctk.CTkTextbox(script_win, wrap="word", corner_radius=0)
            script_textbox.pack(expand=True, fill="both")
            script_textbox.configure(state="normal") # Abilita per inserimento

            # Applica syntax highlighting
            is_dark = (ctk.get_appearance_mode() == "Dark")
            text_color = COLOR_TEXT_DARK if is_dark else COLOR_TEXT_LIGHT
            script_textbox.tag_config("SCRIPT", foreground=text_color) # Tag default

            for ttype, value in lex(script_content, BashLexer()):
                # Determina colore basato sul tema e tipo token
                tag = str(ttype).replace(".","_") # Crea nome tag valido
                color = text_color # Default
                s_ttype = str(ttype)
                if s_ttype.startswith("Token.Comment"):
                    color = "#6a737d" # Grigio commento
                elif s_ttype.startswith("Token.Keyword") or s_ttype.startswith("Token.Name.Builtin"):
                    color = BTN_HOVER # Blu keyword
                elif s_ttype.startswith("Token.Literal.String"):
                    color = TAG_COLORS["SUCCESS"] # Verde stringa
                elif s_ttype.startswith("Token.Literal.Number"):
                    color = TAG_COLORS["INFO"] # Blu numero
                elif s_ttype.startswith("Token.Operator"):
                    color = TAG_COLORS["ERROR"] # Rosso operatore
                elif s_ttype.startswith("Token.Name.Variable"):
                    color = TAG_COLORS["STEP"] # Arancio variabile

                # Configura e applica il tag
                script_textbox.tag_config(tag, foreground=color)
                script_textbox.insert("end", value, (tag, "SCRIPT")) # Applica tag specifico e default

            script_textbox.configure(state="disabled") # Rendi read-only

        except FileNotFoundError:
             messagebox.showerror(TXT["error_title"], TXT["status_script_not_found"])
        except Exception as e:
             messagebox.showerror(TXT["error_title"], f"Error reading script: {e}")


if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    app = CrossOverApp()
    app.mainloop()