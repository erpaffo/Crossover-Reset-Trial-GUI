#!/usr/bin/env python3
import os
import subprocess
import threading
import time
import hashlib
import re
import sys
import queue
import json
import platform
import logging
import requests
import zipfile
import io
import tempfile
import shutil

import customtkinter as ctk
from tkinter import messagebox, filedialog, Menu, Toplevel
from PIL import Image
from pygments import lex
from pygments.lexers import BashLexer
from packaging.version import parse as parse_version

# --- Application Constants ---
APP_NAME = "CrossOverTrialManager" # Used for paths and identifiers
APP_AUTHOR = "erpaffo"       # Used for Application Support path
PLIST_NAME = f"com.{APP_AUTHOR}.{APP_NAME}.plist" # Adjusted Plist name

# --- Versioning ---
def get_base_path():
    """Determina il percorso base (script dir o bundle root)."""
    if getattr(sys, "frozen", False):
        # Running in PyInstaller bundle
        return sys._MEIPASS
    else:
        # Running normally
        return os.path.dirname(os.path.abspath(__file__))

def load_version(base_path):
    """Carica la versione dal file VERSION."""
    try:
        version_file = os.path.join(base_path, "VERSION")
        with open(version_file, "r") as f:
            return f.read().strip()
    except Exception as e:
        logging.error(f"Error loading VERSION file: {e}")
        return "0.0.0" # Fallback version

BASE_PATH = get_base_path()
__version__ = load_version(BASE_PATH)

# --- Auto-update configuration ---
GITHUB_REPO = "erpaffo/CrossOver-Reset-Trial-GUI"  

# --- Paths ---
APP_SUPPORT_DIR = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
CONFIG_FILE = os.path.join(APP_SUPPORT_DIR, "config.json")
PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{PLIST_NAME}")
SCRIPT_PATH = os.path.join(BASE_PATH, "script.sh")
CHECKSUM_FILE = SCRIPT_PATH + ".sha256"
LOGO_PATH = os.path.join(BASE_PATH, "logo.png") 

# --- Notifications ---
PYOBJC_AVAILABLE = False
PYNC_AVAILABLE = False
try:
    # Try PyObjC first (macOS 10.14+)
    from Foundation import NSObject, NSUserNotificationCenter, NSUserNotification
    PYOBJC_AVAILABLE = True
    logging.info("Using PyObjC for notifications.")
except ImportError:
    logging.debug("PyObjC not available or macOS < 10.14.")
    try:
        # Fallback to pync
        from pync import Notifier
        Notifier("Test message", title="") # Test instantiation
        PYNC_AVAILABLE = True
        logging.info("Using pync for notifications.")
    except Exception as e:
        logging.debug(f"pync Notifier not available: {e}")
        Notifier = None # Ensure Notifier is None if pync failed

def notify(title: str, message: str):
    """Send macOS notification using best available method."""
    if PYOBJC_AVAILABLE:
        try:
            notification = NSUserNotification.alloc().init()
            notification.setTitle_(title)
            notification.setInformativeText_(message)
            # notification.setSoundName_("NSUserNotificationDefaultSoundName") # Optional sound
            center = NSUserNotificationCenter.defaultUserNotificationCenter()
            center.deliverNotification_(notification)
            logging.debug(f"PyObjC notification sent: {title}")
            return
        except Exception as e:
            logging.error(f"PyObjC notification failed: {e}")
            # Fall through to pync if PyObjC fails at runtime

    if PYNC_AVAILABLE and Notifier:
        try:
            Notifier.notify(message, title=title)
            logging.debug(f"pync notification sent: {title}")
        except Exception as e:
            logging.error(f"pync notification failed: {e}")
    else:
        logging.debug(f"No notification backend available for: {title}")

# --- Settings Persistence ---
def load_settings() -> dict:
    """Loads settings from config.json."""
    try:
        if not os.path.exists(CONFIG_FILE):
            return {"dark_mode": None} # Default: follow system
        with open(CONFIG_FILE, "r") as f:
            settings = json.load(f)
            # Ensure keys exist, provide defaults if not
            if "dark_mode" not in settings:
                 settings["dark_mode"] = None
            return settings
    except (json.JSONDecodeError, IOError) as e:
        logging.error(f"Error loading config file {CONFIG_FILE}: {e}")
        return {"dark_mode": None} # Return default on error

def save_settings(settings: dict):
    """Saves settings to config.json."""
    try:
        os.makedirs(APP_SUPPORT_DIR, exist_ok=True) # Ensure directory exists
        with open(CONFIG_FILE, "w") as f:
            json.dump(settings, f, indent=4)
    except IOError as e:
        logging.error(f"Error saving config file {CONFIG_FILE}: {e}")
        # Optionally show a user-facing error here
        # messagebox.showerror("Error", f"Could not save settings:\n{e}")

# Load initial settings
current_settings = load_settings()

# Apply initial appearance mode based on settings
if current_settings.get("dark_mode") is True:
    ctk.set_appearance_mode("Dark")
elif current_settings.get("dark_mode") is False:
    ctk.set_appearance_mode("Light")
else:
     ctk.set_appearance_mode("System") # None means follow system

ctk.set_default_color_theme("blue")

# --- Constants and Theme (rest of your definitions) ---
BADGE_SUCCESS_TIMEOUT_MS = 2500
COLOR_BACKGROUND_LIGHT = "#F2F2F7"
COLOR_BACKGROUND_DARK = "#1E1E1E"
# ... (keep all your color and TAG_COLORS definitions) ...
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


# --- I18N ---
LANGUAGES = {
    "it": {
        "name": "Italiano",
        "title": f"{APP_NAME} v{__version__}", # Include version in title
        # ... (keep all your IT translations, add new ones below) ...
        "execute":   "Esegui Reset",
        "install":   "Installa Servizio",
        "uninstall": "Disinstalla Servizio",
        "help":      "Aiuto",
        "show_script":"Mostra Script",
        "export":    "Esporta Log",
        "clear":     "Pulisci Log",
        "filter":    "Filtra Log...",
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
            f"{APP_NAME} v{__version__}\n"
            "Questa app resetta la trial di CrossOver.\n\n"
            "• Esegui Reset: Effettua un reset manuale ora.\n"
            "• Installa Servizio: Imposta un reset automatico all'avvio.\n"
            "• Disinstalla Servizio: Rimuove il servizio di auto-reset.\n\n"
            "Nota: L'installazione/disinstallazione richiede privilegi amministrativi.\n"
            "L'app è intesa per uso didattico ed etico."
        ),
        "script_viewer_title": "Visualizzatore Script - script.sh",
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
        "checksum_not_created_msg": "File checksum non creato.",
        "menu_settings": "Impostazioni",
        "menu_dark_mode": "Modalità Scura",
        "menu_language": "Lingua",
        "menu_check_updates": "Controlla Aggiornamenti...",
        "update_available_title": "Aggiornamento Disponibile",
        "update_ask_install": "Una nuova versione ({new_version}) è disponibile. Scaricare e installare ora?",
        "update_no_zip": "Nessun file ZIP trovato nell'ultima release.",
        "update_downloading": "Download aggiornamento...",
        "update_installing": "Installazione aggiornamento...",
        "update_success_title": "Aggiornato",
        "update_success_msg": "Aggiornato alla versione {new_version}. Riavvio in corso...",
        "update_error_title": "Errore Aggiornamento",
        "update_up_to_date_title": "Aggiornato",
        "update_up_to_date_msg": "Stai già usando l'ultima versione ({current_version}).",
        "update_status_checking": "Verifica aggiornamenti...",
        "update_status_downloading": "Download in corso ({percent:.0f}%)...",
        "update_status_installing": "Installazione...",
        "update_status_error": "Errore aggiornamento.",
        "update_newer_local_title": "Versione Sviluppo",
        "update_newer_local_msg": "La tua versione attuale ({local_version}) è più recente dell'ultima release ufficiale ({gh_version}).",
    },
    "en": {
        "name": "English",
        "title": f"{APP_NAME} v{__version__}", # Include version in title
        # ... (keep all your EN translations, add new ones below) ...
        "execute":   "Run Reset",
        "install":   "Install Service",
        "uninstall": "Uninstall Service",
        "help":      "Help",
        "show_script":"Show Script",
        "export":    "Export Log",
        "clear":     "Clear Log",
        "filter":    "Filter Log...",
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
            f"{APP_NAME} v{__version__}\n"
            "This app resets the CrossOver trial.\n\n"
            "• Run Reset: Perform a manual reset now.\n"
            "• Install Service: Set up automatic reset on startup.\n"
            "• Uninstall Service: Remove the auto-reset service.\n\n"
            "Note: Install/Uninstall requires administrative privileges.\n"
            "This app is for educational/ethical use only."
        ),
        "script_viewer_title": "Script Viewer - script.sh",
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
        "menu_settings": "Settings",
        "menu_dark_mode": "Dark Mode",
        "menu_language": "Language",
        "menu_check_updates": "Check for Updates...",
        "update_available_title": "Update Available",
        "update_ask_install": "A new version ({new_version}) is available. Download and install now?",
        "update_no_zip": "No ZIP asset found for the latest release.",
        "update_downloading": "Downloading update...",
        "update_installing": "Installing update...",
        "update_success_title": "Updated",
        "update_success_msg": "Updated to version {new_version}. Relaunching...",
        "update_error_title": "Update Error",
        "update_up_to_date_title": "Up to Date",
        "update_up_to_date_msg": "You are already running the latest version ({current_version}).",
        "update_status_checking": "Checking for updates...",
        "update_status_downloading": "Downloading ({percent:.0f}%)...",
        "update_status_installing": "Installing...",
        "update_status_error": "Update error.",
        "update_newer_local_title": "Development Version",
        "update_newer_local_msg": "Your current version ({local_version}) is newer than the latest official release ({gh_version}).",
    }
}
# Imposta lingua iniziale (potrebbe essere letto da un file di config -> ora non più, si basa sul sistema o default)
# TODO: Caricare la lingua salvata dalle impostazioni se implementato
LANG = "it" # Default language, could be loaded from settings
TXT = LANGUAGES[LANG]

# --- Coda per i log ---
log_queue = queue.Queue()

# --- Main App Class ---
class CrossOverApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.checksum_valid = None
        self.script_executable = False
        self.script_found = False
        self.current_action = None
        self.service_active = False
        self.bottles_path_override = None
        self.settings = current_settings # Carica le impostazioni globali

        # ── Window setup ────────────────────────────────────────────────────────
        self.title(TXT["title"])
        self.geometry("1000x700")
        self.minsize(800, 500)
        self.resizable(True, True)
        self._set_appearance() # Apply colors based on loaded settings/system

        # Lingua e dark mode vars
        self.lang_var = ctk.StringVar(value=TXT["name"]) # TODO: Impostare da settings
        # Imposta mode_var basato sullo stato corrente (che deriva da settings o sistema)
        initial_mode_is_dark = (ctk.get_appearance_mode() == "Dark")
        self.mode_var = ctk.BooleanVar(value=initial_mode_is_dark)

        # Elenco azioni e bottoni
        self.actions = [
            {"key": "execute",   "cmd": self.execute_reset,       "color": BTN_PRIMARY_FG},
            {"key": "install",   "cmd": self.install_service,     "color": BTN_SECONDARY_FG},
            {"key": "uninstall", "cmd": self.uninstall_service,   "color": BTN_DANGER_FG},
            {"key": "refresh_status", "cmd": self.refresh_status, "color": BTN_PRIMARY_FG},
            {"key": "show_script", "cmd": self.show_script_window, "color": BTN_PRIMARY_FG},
            {"key": "export",    "cmd": self.export_log,          "color": BTN_PRIMARY_FG},
            {"key": "clear",     "cmd": self.clear_log,           "color": BTN_PRIMARY_FG},
            {"key": "help",      "cmd": self.show_help,           "color": BTN_PRIMARY_FG},
        ]
        self.action_buttons = {}
        self.badges = {}

        # ── Menu bar ───────────────────────────────────────────────────────────
        self._create_menu()

        # ── Main layout ────────────────────────────────────────────────────────
        self._create_ui_layout() # Ora include le progress bar

        # ── Inizializzazione ─────────────────────────────────────────────────────
        self.full_log = []
        self._update_ui_colors() # Applica colori iniziali
        self._check_script_status() # Controlla script e checksum
        self.refresh_status() # Controlla stato servizio LaunchAgent
        self.update_status_bar() # Aggiorna status bar iniziale
        self.after(100, self._process_log_queue) # Avvia processore coda log

    # --- UI Creation ---
    def _create_ui_layout(self):
        """Crea il layout principale dell'interfaccia utente."""
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0) # Riga per update progress bar
        self.grid_rowconfigure(2, weight=0) # Riga per status bar

        # --- Left frame: action buttons and progress ---
        self.left_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        self.left_frame.grid_propagate(False)

        # Action Buttons
        for i, action in enumerate(self.actions):
            key, cmd, color = action["key"], action["cmd"], action["color"]
            btn = ctk.CTkButton(self.left_frame, text=TXT.get(key, key), compound="left", anchor="w",
                                width=180, height=36, fg_color=color, hover_color=BTN_HOVER,
                                text_color=BTN_TEXT_COLOR, command=cmd)
            btn.pack(pady=8, padx=10, anchor="n")
            self.action_buttons[key] = btn
            self._create_badges(btn, key)

        # Action Progress Bar (initially hidden)
        self.action_progress_bar = ctk.CTkProgressBar(self.left_frame, height=10, corner_radius=5)
        self.action_progress_bar.set(0)
        # self.action_progress_bar.pack(pady=(10, 5), padx=10, fill="x", anchor="s") # Packed when needed

        # Service status label
        self.service_status_label = ctk.CTkLabel(self.left_frame, text="Service: ...", anchor="w")
        self.service_status_label.pack(pady=(15, 0), padx=10, anchor="w")


        # --- Right frame: filter and log ---
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
        self.search_entry = ctk.CTkEntry(filter_frame, textvariable=self.search_var, placeholder_text=TXT["filter"])
        self.search_entry.grid(row=0, column=1, sticky="ew")
        self.search_entry.bind("<KeyRelease>", self.filter_log)

        # Output box
        self.output_box = ctk.CTkTextbox(self.right_frame, corner_radius=6)
        self.output_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10)) # Added bottom padding
        self.output_box.configure(state="disabled")
        self._configure_log_tags()

        # --- Update Progress Bar (below log) ---
        self.update_progress_bar = ctk.CTkProgressBar(self, height=10)
        self.update_progress_bar.set(0)
        # Grid position adjusted to be below right_frame
        self.update_progress_bar.grid(row=1, column=1, sticky="ew", padx=(5, 10), pady=(0, 5))
        self.update_progress_bar.grid_remove() # Hidden initially


        # ── Status Bar ──────────────────────────────────────────────────────────
        self.status_bar = ctk.CTkFrame(self, height=25, corner_radius=0)
        # Grid position adjusted to be the last row
        self.status_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        self.status_label = ctk.CTkLabel(self.status_bar, text=TXT["status_ready"], anchor="w")
        self.status_label.pack(side="left", padx=10)
        self.checksum_status_label = ctk.CTkLabel(self.status_bar, text="", anchor="e", width=150)
        self.checksum_status_label.pack(side="right", padx=10)

    def _create_menu(self):
        """Crea la barra dei menu."""
        self.menu_bar = Menu(self)
        self.config(menu=self.menu_bar)

        settings_menu = Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label=TXT.get("menu_settings", "Settings"), menu=settings_menu)

        settings_menu.add_checkbutton(
            label=TXT.get("menu_dark_mode", "Dark Mode"),
            variable=self.mode_var,
            command=self.toggle_mode
        )

        language_menu = Menu(settings_menu, tearoff=0)
        settings_menu.add_cascade(label=TXT.get("menu_language", "Language"), menu=language_menu)
        for code, d in LANGUAGES.items():
            language_menu.add_radiobutton(
                label=d["name"],
                variable=self.lang_var,
                value=d["name"],
                command=lambda choice=d["name"]: self.change_language(choice)
            )
        # TODO: Load/Save selected language in settings

        settings_menu.add_separator()
        settings_menu.add_command(
            label=TXT.get("menu_check_updates", "Check for Updates..."),
            command=self.check_for_updates_threaded # Use threaded version
        )
        # Commented out - checksum generation is now interactive via verify_checksum
        # {"key": "generate_checksum", "cmd": self.generate_checksum_file, "color": BTN_PRIMARY_FG},


    # --- UI Updates & State ---
    def _create_badges(self, parent_button, action_key):
        """Crea i badge per un dato bottone e chiave azione."""
        badge_style = {"width": 16, "height": 16, "text_color": "white", "corner_radius": 8, "font": ctk.CTkFont(size=10, weight="bold")}
        err_badge = ctk.CTkLabel(parent_button, text="", fg_color=TAG_COLORS["ERROR"], **badge_style)
        succ_badge = ctk.CTkLabel(parent_button, text="", fg_color=TAG_COLORS["SUCCESS"], **badge_style)
        self.badges[action_key] = {"error": err_badge, "success": succ_badge}
        err_badge.place(relx=1.0, rely=0.0, x=-5, y=5, anchor="ne")
        succ_badge.place(relx=0.0, rely=0.0, x=5, y=5, anchor="nw")
        err_badge.lower()
        succ_badge.lower()

    def _update_badge(self, action_key, badge_type, count):
        """Aggiorna un badge specifico."""
        if action_key in self.badges and badge_type in self.badges[action_key]:
            badge = self.badges[action_key][badge_type]
            if count > 0:
                badge.configure(text=str(count))
                badge.lift()
            else:
                badge.configure(text="")
                badge.lower()

    def _reset_badges(self, action_key):
        """Resetta i badge per un'azione."""
        self._update_badge(action_key, "success", 0)
        self._update_badge(action_key, "error", 0)

    def _configure_log_tags(self):
        """Configura i tag di colore per il CtkTextbox."""
        mode = ctk.get_appearance_mode()
        TAG_COLORS["SCRIPT"] = COLOR_TEXT_DARK if mode == "Dark" else COLOR_TEXT_LIGHT
        for level, color in TAG_COLORS.items():
            self.output_box.tag_config(level, foreground=color)

    def _set_appearance(self):
        """Imposta l'aspetto globale iniziale."""
        mode = ctk.get_appearance_mode()
        fg_color = COLOR_BACKGROUND_DARK if mode == "Dark" else COLOR_BACKGROUND_LIGHT
        self.configure(fg_color=fg_color)

    def _update_ui_colors(self):
        """Aggiorna i colori dei widget in base alla modalità."""
        mode = ctk.get_appearance_mode()
        is_dark = (mode == "Dark")
        bg_color = COLOR_BACKGROUND_DARK if is_dark else COLOR_BACKGROUND_LIGHT
        frame_color = COLOR_FRAME_DARK if is_dark else COLOR_FRAME_LIGHT
        textbox_color = COLOR_TEXTBOX_DARK if is_dark else COLOR_TEXTBOX_LIGHT
        text_color = COLOR_TEXT_DARK if is_dark else COLOR_TEXT_LIGHT
        placeholder_color = COLOR_PLACEHOLDER_DARK if is_dark else COLOR_PLACEHOLDER_LIGHT

        self.configure(fg_color=bg_color)
        if hasattr(self, "left_frame"): self.left_frame.configure(fg_color=frame_color)
        if hasattr(self, "right_frame"): self.right_frame.configure(fg_color=frame_color)
        if hasattr(self, "status_bar"): self.status_bar.configure(fg_color=frame_color)
        if hasattr(self, "status_label"): self.status_label.configure(text_color=text_color)
        if hasattr(self, "checksum_status_label"): self.checksum_status_label.configure(text_color=text_color)
        if hasattr(self, "service_status_label"): self.service_status_label.configure(text_color=text_color)
        if hasattr(self, "search_entry"):
            self.search_entry.configure(fg_color=textbox_color, text_color=text_color,
                                        border_color=frame_color, placeholder_text_color=placeholder_color)
        if hasattr(self, "output_box"):
            self.output_box.configure(fg_color=textbox_color, text_color=text_color, border_color=frame_color)

        self._configure_log_tags() # Reconfigure tags for script color
        self.filter_log() # Refilter log with new colors if needed

    def toggle_mode(self):
        """Cambia tra modalità chiara e scura e salva l'impostazione."""
        is_dark = self.mode_var.get()
        mode = "Dark" if is_dark else "Light"
        ctk.set_appearance_mode(mode)
        self.settings["dark_mode"] = is_dark # Salva True/False
        save_settings(self.settings)
        self._update_ui_colors()

    def change_language(self, choice):
        """Cambia la lingua dell'interfaccia."""
        global LANG, TXT
        # TODO: Save language choice to settings
        prev_lang = LANG
        for code, d in LANGUAGES.items():
            if d["name"] == choice:
                LANG, TXT = code, LANGUAGES[code]
                break
        if prev_lang != LANG:
            self.title(TXT["title"])
            for action in self.actions:
                if action["key"] in self.action_buttons:
                    self.action_buttons[action["key"]].configure(text=TXT[action["key"]])
            if hasattr(self,"search_entry"): self.search_entry.configure(placeholder_text=TXT["filter"])
            # Aggiorna menu
            self._create_menu() # Easiest way to update all menu labels
            self.update_status_bar()
            # Aggiorna testo help se necessario
            # Aggiorna titoli finestre (es. script viewer)

    # --- Log Processing ---
    def _process_log_queue(self):
        """Processa i messaggi dalla coda log nel thread principale."""
        try:
            while True:
                log_entry = log_queue.get_nowait()
                self._append_text_to_gui(log_entry["text"], log_entry["log_level"])
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_log_queue)

    def _log(self, text: str, level: str = "CMD"):
        """Aggiunge un messaggio alla coda log per l'aggiornamento GUI."""
        log_queue.put({"text": text, "log_level": level})

    def _append_text_to_gui(self, text: str, log_level: str = "CMD"):
        """Aggiunge testo al box di output (chiamato dal thread GUI)."""
        self.full_log.append(text)
        clean_text = re.sub(r'\x1B\[[0-9;]*[mK]', '', text).rstrip()
        if not clean_text: return

        effective_tag = log_level
        match = re.match(r'^\[(STEP|INFO|SUCCESS|WARNING|ERROR)\]', clean_text)
        if match: effective_tag = match.group(1)

        self.output_box.configure(state="normal")
        if effective_tag in TAG_COLORS:
            self.output_box.insert("end", clean_text + "\n", effective_tag)
        else:
            self.output_box.insert("end", clean_text + "\n", "CMD")
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def filter_log(self, event=None):
        """Filtra il contenuto del log box."""
        if not hasattr(self, "search_var") or not hasattr(self, "output_box"): return # UI not ready
        query = self.search_var.get().lower()
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        for line in self.full_log:
            if query in line.lower():
                clean_line = re.sub(r'\x1B\[[0-9;]*[mK]', '', line).rstrip()
                if not clean_line: continue
                effective_tag = "CMD"
                match = re.match(r'^\[(STEP|INFO|SUCCESS|WARNING|ERROR)\]', clean_line)
                if match: effective_tag = match.group(1)
                if effective_tag in TAG_COLORS:
                     self.output_box.insert("end", clean_line + "\n", effective_tag)
                else:
                     self.output_box.insert("end", clean_line + "\n", "CMD")
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def clear_log(self):
        """Pulisce il log box e la history."""
        if self.current_action: return
        self.full_log = []
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        self.output_box.configure(state="disabled")
        for action in self.actions: self._reset_badges(action["key"])
        for key in ["execute", "install", "uninstall"]: self._reset_badges(key)

    def export_log(self):
        """Esporta il contenuto del log box su file."""
        # ... (keep existing export_log logic) ...
        if self.current_action: return

        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title=TXT.get("export", "Export Log") # Use i18n title
        )
        if path:
            try:
                with open(path, "w", encoding='utf-8') as f:
                    f.write(self.output_box.get("1.0", "end"))
                self.update_status_bar(TXT["status_exported"])
                # Use our advanced notify function
                notify(TXT["done"], TXT["status_exported"])
            except Exception as e:
                 # Log error and notify user
                log_msg = f"Failed to export log: {e}"
                self._log(f"[ERROR] {log_msg}", "ERROR")
                messagebox.showerror(TXT["error_title"], log_msg)
                self.update_status_bar(f"Export failed: {e}")


    # --- Script/System Interaction ---
    def _check_script_status(self):
        """Verifica l'esistenza, l'eseguibilità e il checksum dello script."""
        self.script_found = os.path.exists(SCRIPT_PATH)
        if self.script_found:
            self.script_executable = os.access(SCRIPT_PATH, os.X_OK)
            if not self.script_executable:
                 self._log(f"[WARNING] {TXT['status_script_not_exec']} Trying to fix...", "WARNING")
                 try:
                     os.chmod(SCRIPT_PATH, os.stat(SCRIPT_PATH).st_mode | 0o111)
                     self.script_executable = os.access(SCRIPT_PATH, os.X_OK)
                     if self.script_executable:
                         self._log(f"[INFO] Made script executable: {SCRIPT_PATH}", "INFO")
                     else:
                          self._log(f"[ERROR] Failed to make script executable: {SCRIPT_PATH}", "ERROR")
                 except Exception as e:
                     self._log(f"[ERROR] Error changing script permissions: {e}", "ERROR")
            # Verify checksum only runs if script exists
            self.verify_checksum()
        else:
            self._log(f"[ERROR] {TXT['status_script_not_found']}", "ERROR")
            self.script_executable = False
            self.checksum_valid = None # N/A if script doesn't exist

        # Enable/disable buttons based on script status
        can_run_script = self.script_found and self.script_executable
        for key in ["execute", "install", "uninstall", "show_script"]:
             if key in self.action_buttons:
                 self.action_buttons[key].configure(state="normal" if can_run_script else "disabled")


    def _update_checksum_file(self, checksum_path: str, hash_to_write: str) -> bool:
        """Helper to write the checksum file."""
        # ... (keep existing _update_checksum_file logic) ...
        try:
            with open(checksum_path, "w") as f:
                f.write(hash_to_write)
            logging.info(f"Checksum updated/created successfully: {checksum_path}")
            return True
        except Exception as e:
            self._log(f"[ERROR] Impossibile scrivere nel file checksum '{checksum_path}': {e}", "ERROR")
            messagebox.showerror(TXT["error_title"], f"Failed to write checksum file:\n{e}")
            return False

    def get_script_path(self):
        """
        Determina il percorso assoluto dello script 'script.sh'.

        Questa funzione gestisce sia l'esecuzione come script Python standard
        sia l'esecuzione come applicazione impacchettata (es. PyInstaller),
        assumendo che 'script.sh' si trovi nella stessa directory del file
        principale o nella root del bundle.

        Returns:
            str: Il percorso assoluto del file 'script.sh'.
        """
        # Nome del file script che stiamo cercando
        script_filename = "script.sh"

        if getattr(sys, 'frozen', False):
            # L'applicazione è 'frozen', cioè impacchettata (es. PyInstaller).
            # In questo caso, i file inclusi nel bundle si trovano in una
            # directory temporanea il cui percorso è memorizzato in sys._MEIPASS.
            base_path = sys._MEIPASS
            logging.debug(f"Running bundled, base path (sys._MEIPASS): {base_path}")
        else:
            # L'applicazione sta girando come script Python normale.
            # __file__ è il percorso del file Python corrente (main.py).
            # Ne prendiamo la directory.
            base_path = os.path.dirname(os.path.abspath(__file__))
            logging.debug(f"Running as script, base path (dirname): {base_path}")

        # Combina il percorso base con il nome del file script.
        # os.path.join gestisce correttamente i separatori di percorso ('/' o '\').
        script_path = os.path.join(base_path, script_filename)
        logging.debug(f"Full path for {script_filename} determined as: {script_path}")

        return script_path


    def verify_checksum(self):
        """Verifica checksum, crea o chiede fix interattivamente."""
        # ... (keep existing verify_checksum logic using _update_checksum_file helper) ...
        import logging
        script_to_check_path = self.get_script_path()
        checksum_storage_path = script_to_check_path + ".sha256"
        script_basename = os.path.basename(script_to_check_path) # For messages

        self.checksum_valid = None

        # Script existence already checked in _check_script_status
        if not self.script_found: return

        try:
            sha = hashlib.sha256()
            with open(script_to_check_path, "rb") as f:
                while True:
                    chunk = f.read(8192);
                    if not chunk: break
                    sha.update(chunk)
            current_hash = sha.hexdigest()
            logging.debug(f"Calculated hash for {script_to_check_path}: {current_hash}")

            if os.path.exists(checksum_storage_path):
                with open(checksum_storage_path, "r") as cf:
                    expected_hash = cf.read().strip()
                logging.debug(f"Expected hash from {checksum_storage_path}: {expected_hash}")

                if expected_hash == current_hash:
                    self.checksum_valid = True
                    self._log(f"[INFO] {TXT['checksum_ok_msg']} ({script_basename})", "INFO")
                else:
                    self.checksum_valid = False
                    self._log(f"[ERROR] Checksum mismatch for {script_basename}!", "ERROR")
                    self._log(f"[ERROR]   Expected : {expected_hash}", "ERROR")
                    self._log(f"[ERROR]   Calculated: {current_hash}", "ERROR")

                    q_title = TXT.get("checksum_mismatch_title", "Checksum Mismatch")
                    q_msg = TXT.get("checksum_mismatch_ask_fix", "...") \
                               .format(script_name=script_basename)
                    user_choice = messagebox.askyesno(q_title, q_msg)

                    if user_choice:
                        if self._update_checksum_file(checksum_storage_path, current_hash):
                            self.checksum_valid = True
                            self._log(f"[INFO] {TXT.get('checksum_updated_msg', 'Checksum file updated.')}", "INFO")
                        else:
                            self._log(f"[ERROR] {TXT.get('checksum_update_error_msg', 'Failed to update checksum file.')}", "ERROR")
                    else:
                        self._log(f"[WARNING] {TXT.get('checksum_not_updated_msg', 'Checksum mismatch ignored by user.')}", "WARNING")
            else:
                self.checksum_valid = None
                self._log(f"[WARNING] Checksum file '{os.path.basename(checksum_storage_path)}' not found.", "WARNING")
                q_title = TXT.get("checksum_missing_title", "Checksum File Missing")
                q_msg = TXT.get("checksum_missing_ask_create", "...") \
                           .format(script_name=script_basename)
                user_choice = messagebox.askyesno(q_title, q_msg)
                if user_choice:
                    if self._update_checksum_file(checksum_storage_path, current_hash):
                        self.checksum_valid = True
                        self._log(f"[INFO] {TXT.get('checksum_created_msg', 'Checksum file created.')}", "INFO")
                    else:
                        self._log(f"[ERROR] {TXT.get('checksum_create_error_msg', 'Failed to create checksum file.')}", "ERROR")
                else:
                    self._log(f"[INFO] {TXT.get('checksum_not_created_msg', 'Checksum file not created.')}", "INFO")

        except Exception as e:
            self.checksum_valid = None
            self._log(f"[ERROR] Error during checksum verification/handling: {e}", "ERROR")
            messagebox.showerror(TXT["error_title"], f"Checksum Error: {e}")

        self.after(0, self.update_status_bar)


    def update_status_bar(self, message=None, is_update_status=False):
        """Aggiorna la barra di stato principale e/o quella di aggiornamento."""
        # Main status message
        if message and not is_update_status:
            self.status_label.configure(text=message)
        elif self.current_action:
             self.status_label.configure(text=TXT["status_running"].format(action=TXT[self.current_action]))
        elif not is_update_status: # Don't overwrite update status with "Ready"
            self.status_label.configure(text=TXT["status_ready"])

        # Checksum status (always update unless an update is in progress)
        if not self.update_progress_bar.winfo_ismapped(): # Only if update bar not visible
            if self.checksum_valid is True:
                self.checksum_status_label.configure(text=TXT["status_checksum_ok"], text_color=TAG_COLORS["SUCCESS"])
            elif self.checksum_valid is False:
                self.checksum_status_label.configure(text=TXT["status_checksum_err"], text_color=TAG_COLORS["ERROR"])
            else: # None (N/A or error)
                if not self.script_found:
                    self.checksum_status_label.configure(text=TXT["status_script_not_found"], text_color=TAG_COLORS["ERROR"])
                else:
                    self.checksum_status_label.configure(text=TXT["status_checksum_na"], text_color=TAG_COLORS["WARNING"])

    def _set_ui_busy(self, busy: bool, action_key: str):
        """Abilita/Disabilita UI e mostra/nasconde progress bar azione."""
        self.current_action = action_key if busy else None
        state = "disabled" if busy else "normal"

        # Enable/disable action buttons
        for key, button in self.action_buttons.items():
            # Allow Clear and Help when not busy
            allow_always = key in ["clear", "help"] and not busy
            # Disable export when busy
            disable_export = key == "export" and busy
            # Standard case
            standard_disable = key not in ["clear", "help"]

            if allow_always:
                button.configure(state="normal")
            elif disable_export:
                 button.configure(state="disabled")
            elif standard_disable:
                 button.configure(state=state)

        # Filter and Clear button
        self.search_entry.configure(state=state)
        self.action_buttons["clear"].configure(state="normal" if not busy else "disabled")

        # Show/Hide Action Progress Bar
        if busy:
            self.action_progress_bar.pack(pady=(10, 5), padx=10, fill="x", anchor="s", before=self.service_status_label)
            self.action_progress_bar.configure(mode="indeterminate")
            self.action_progress_bar.start()
        else:
            if hasattr(self, "action_progress_bar"): # Check if widget exists
                self.action_progress_bar.stop()
                self.action_progress_bar.pack_forget()

        self.update_status_bar() # Update status text (e.g., "Running...")


    def run_bash_script(self, action_key: str):
        """Esegue lo script bash in un thread separato, gestendo UI busy state."""
        # ... (keep existing run_bash_script logic, it already uses _set_ui_busy and threading) ...
        if self.current_action: return
        if not self.script_found or not self.script_executable:
            self._log(f"[ERROR] Cannot run script (not found or not executable).", "ERROR")
            messagebox.showerror(TXT["error_title"], TXT["status_script_not_found"] if not self.script_found else TXT["status_script_not_exec"])
            return

        # Checksum check before running sensitive actions
        if action_key in ["install", "uninstall", "execute"] and self.checksum_valid is False:
             # Ask again if they really want to run with bad checksum
             if not messagebox.askyesno(TXT["warning_title"],
                                        f"Checksum is invalid for script.sh.\nRunning it could be unsafe.\n\nProceed anyway?"):
                 self._log("[WARNING] Execution cancelled by user due to invalid checksum.", "WARNING")
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
                if bottles_path: command.append(bottles_path)
                self._log(f"[CMD] Running: {' '.join(command)}", "CMD")

                proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, encoding='utf-8', errors='replace', bufsize=1)

                for line in iter(proc.stdout.readline, ''):
                    self._log(line, "CMD") # Log output immediately
                    if "[ERROR]" in line:
                        error_count += 1
                        self.after(0, lambda cnt=error_count: self._update_badge(action_key, "error", cnt))
                    if "[SUCCESS]" in line:
                        success_count += 1
                        self.after(0, lambda cnt=success_count: self._update_badge(action_key, "success", cnt))

                proc.stdout.close()
                return_code = proc.wait()

                if return_code == 0:
                    self._log(f"[SUCCESS] Script finished successfully (Code: {return_code}).", "SUCCESS")
                    if success_count == 0: # Ensure at least one success badge if code is 0
                        success_count = 1
                        self.after(0, lambda cnt=success_count: self._update_badge(action_key, "success", cnt))
                else:
                    self._log(f"[ERROR] Script finished with error (Code: {return_code}).", "ERROR")
                    if error_count == 0: # Ensure at least one error badge if code != 0
                        error_count = 1
                        self.after(0, lambda cnt=error_count: self._update_badge(action_key, "error", cnt))

            except FileNotFoundError:
                self._log(f"[ERROR] Command 'bash' or script '{SCRIPT_PATH}' not found.", "ERROR")
                return_code = -1
                error_count += 1; self.after(0, lambda cnt=error_count: self._update_badge(action_key, "error", cnt))
            except Exception as e:
                self._log(f"[ERROR] Unexpected error during script execution: {e}", "ERROR")
                return_code = -1
                error_count += 1; self.after(0, lambda cnt=error_count: self._update_badge(action_key, "error", cnt))
            finally:
                self._log(f"=== [{action_key.upper()}] END (Exit Code: {return_code}) ===\n", "STEP")
                # Finalize on the main thread
                self.after(0, self._finalize_script_run, action_key, return_code)

        # Start the background thread
        thread = threading.Thread(target=task, daemon=True)
        thread.start()


    def _finalize_script_run(self, action_key: str, return_code: int):
        """Operazioni da eseguire nel thread GUI dopo la fine dello script."""
        # ... (keep existing _finalize_script_run logic, but use advanced notify) ...
        self._set_ui_busy(False, action_key) # Also hides progress bar

        if return_code == 0:
            msg = f"{TXT.get(action_key, action_key)} - {TXT['done']}"
            messagebox.showinfo(TXT["done"], msg)
            notify(TXT["done"], msg) # Use advanced notification

            # Rimuovi badge success dopo timeout
            def clear_success_badge(): self._update_badge(action_key, "success", 0)
            self.after(BADGE_SUCCESS_TIMEOUT_MS, clear_success_badge)
        else:
            msg = f"{TXT.get(action_key, action_key)} - {TXT['error_occurred']}"
            messagebox.showerror(TXT["error_title"], msg)
            notify(TXT["error_title"], msg) # Use advanced notification

        self.update_status_bar()


    def refresh_status(self):
        """Aggiorna lo stato del servizio LaunchAgent."""
        # Improved check using launchctl if possible, fallback to file existence
        active_text = TXT.get("service_status_active", "Active")
        inactive_text = TXT.get("service_status_inactive", "Not Installed")
        error_text = TXT.get("service_status_error", "Error Checking")
        status_text = inactive_text # Default

        try:
            # Try using launchctl to get the real status
            result = subprocess.run(['launchctl', 'list', PLIST_NAME], capture_output=True, text=True, check=False)
            if result.returncode == 0 and PLIST_NAME in result.stdout:
                 status_text = active_text
                 self.service_active = True
            else:
                 # If launchctl doesn't find it, double-check file existence as fallback
                 self.service_active = os.path.exists(PLIST_PATH)
                 status_text = active_text if self.service_active else inactive_text

        except FileNotFoundError:
             # launchctl not found, rely solely on file existence
             logging.warning("launchctl command not found, checking service status via file existence only.")
             self.service_active = os.path.exists(PLIST_PATH)
             status_text = active_text if self.service_active else inactive_text
        except Exception as e:
            logging.error(f"Error checking service status with launchctl: {e}")
            self.service_active = os.path.exists(PLIST_PATH) # Fallback check
            status_text = active_text if self.service_active else inactive_text
            # Optionally add an error indicator: status_text = f"{status_text} ({error_text})"


        if hasattr(self, "service_status_label"):
            self.service_status_label.configure(text=f"{TXT.get('service', 'Service')}: {status_text}")

    # --- Action Methods (Wrappers) ---
    def execute_reset(self):   self.run_bash_script("execute")
    def install_service(self): self.run_bash_script("install")
    def uninstall_service(self): self.run_bash_script("uninstall")

    def show_help(self):
        """Mostra il messaggio di aiuto."""
        messagebox.showinfo(TXT["help"], TXT["help_text"]) # help_text now includes version

    def show_script_window(self):
        """Mostra il contenuto dello script con syntax highlighting."""
        # ... (keep existing show_script_window logic) ...
        if not self.script_found:
             messagebox.showerror(TXT["error_title"], TXT["status_script_not_found"])
             return

        try:
            with open(SCRIPT_PATH, "r", encoding='utf-8') as f:
                script_content = f.read()

            script_win = Toplevel(self)
            script_win.title(TXT["script_viewer_title"])
            script_win.geometry("800x600")
            script_win.transient(self); script_win.grab_set()

            script_textbox = ctk.CTkTextbox(script_win, wrap="word", corner_radius=0)
            script_textbox.pack(expand=True, fill="both")
            script_textbox.configure(state="normal")

            is_dark = (ctk.get_appearance_mode() == "Dark")
            text_color = COLOR_TEXT_DARK if is_dark else COLOR_TEXT_LIGHT
            script_textbox.tag_config("SCRIPT", foreground=text_color) # Default tag

            # Define colors more dynamically based on theme/TAG_COLORS if desired
            lexer = BashLexer()
            # Pre-configure tags for efficiency
            token_colors = {
                "Token.Comment": "#6a737d",
                "Token.Keyword": BTN_HOVER, "Token.Name.Builtin": BTN_HOVER,
                "Token.Literal.String": TAG_COLORS["SUCCESS"],
                "Token.Literal.Number": TAG_COLORS["INFO"],
                "Token.Operator": TAG_COLORS["ERROR"],
                "Token.Name.Variable": TAG_COLORS["STEP"],
            }
            for token_name, color in token_colors.items():
                 # Normalize token name for tag
                 tag_name = token_name.replace(".", "_")
                 script_textbox.tag_config(tag_name, foreground=color)


            # Lex and insert
            for ttype, value in lex(script_content, lexer):
                 tag = str(ttype).replace(".","_")
                 # Find the most specific matching color definition
                 current_ttype_str = str(ttype)
                 applied_tag = "SCRIPT" # Default
                 for token_name in token_colors:
                     if current_ttype_str.startswith(token_name):
                         applied_tag = token_name.replace(".", "_")
                         break # Use the first match (most specific)

                 script_textbox.insert("end", value, (applied_tag,))


            script_textbox.configure(state="disabled")

        except FileNotFoundError:
             messagebox.showerror(TXT["error_title"], TXT["status_script_not_found"])
        except Exception as e:
             messagebox.showerror(TXT["error_title"], f"Error reading/displaying script: {e}")


    # --- Auto Update ---
    def check_for_updates_threaded(self):
        """Runs the update check in a separate thread to avoid blocking UI."""
        thread = threading.Thread(target=self.check_for_updates, daemon=True)
        thread.start()

    def _update_progress_ui(self, value=None, text=None, indeterminate=False):
        """Helper to update progress bar and status label from any thread."""
        def update():
            if not hasattr(self, "update_progress_bar"): return # Check UI exists

            if value is not None:
                self.update_progress_bar.grid() # Make visible
                self.update_progress_bar.set(value)
                if indeterminate:
                    self.update_progress_bar.configure(mode="indeterminate")
                    self.update_progress_bar.start()
                else:
                     self.update_progress_bar.configure(mode="determinate")
                     self.update_progress_bar.stop()
            else:
                # Hide progress bar if value is None
                self.update_progress_bar.stop()
                self.update_progress_bar.grid_remove()

            if text is not None:
                self.update_status_bar(text, is_update_status=True)

        # Schedule the UI update on the main thread
        self.after(0, update)

    def check_for_updates(self):
        """Checks GitHub for updates and handles download/install."""
        logging.info("Checking for updates...")
        self._update_progress_ui(0, TXT.get("update_status_checking", "Checking for updates..."), indeterminate=True)

        try:
            # 1) Get latest release info
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            resp = requests.get(api_url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            latest_tag = data["tag_name"]
            logging.info(f"Latest release tag from GitHub: {latest_tag}")
            latest_version_str = latest_tag.lstrip('v') # Rimuovi 'v' iniziale se presente

            # --- NUOVA LOGICA DI CONFRONTO ---
            try:
                gh_version = parse_version(latest_version_str)
                local_version = parse_version(__version__) # __version__ è caricato da VERSION
                logging.info(f"Comparing GitHub version {gh_version} with local version {local_version}")

                if gh_version > local_version:
                    # Versione GitHub è PIÙ NUOVA: procedi con l'offerta di aggiornamento
                    logging.info(f"Newer version found: {gh_version}")
                    # Adesso chiedi all'utente conferma
                    if not messagebox.askyesno(
                        TXT.get("update_available_title", "Update Available"),
                        TXT.get("update_ask_install", "A new version ({new_version}) is available. Download and install now?")
                        .format(new_version=latest_version_str)
                    ):
                        self._update_progress_ui(None) # Nascondi progress bar se utente annulla
                        return # Utente non vuole aggiornare

                    # --- Qui inizia la logica di download/installazione ---
                    # (Solo se gh_version > local_version E utente ha detto sì)

                elif gh_version == local_version:
                    # Le versioni sono uguali
                    logging.info("Local version is already up to date.")
                    self._update_progress_ui(None)
                    messagebox.showinfo(
                        TXT.get("update_up_to_date_title", "Up to Date"),
                        TXT.get("update_up_to_date_msg", "You are already running the latest version ({current_version}).")
                        .format(current_version=__version__)
                    )
                    return # Fine, nessuna azione necessaria

                else: # gh_version < local_version
                    # La versione locale è più recente (es. versione di sviluppo)
                    logging.info(f"Local version {local_version} is newer than latest release {gh_version}.")
                    self._update_progress_ui(None)
                    # Informa l'utente (opzionale ma utile)
                    messagebox.showinfo(
                        TXT.get("update_newer_local_title", "Development Version"), # Aggiungere a i18n
                        TXT.get("update_newer_local_msg", "Your current version ({local_version}) is newer than the latest official release ({gh_version}).") # Aggiungere a i18n
                        .format(local_version=__version__, gh_version=latest_version_str)
                    )
                    return # Fine, nessuna azione necessaria

            except Exception as e: # Errore durante il parsing o confronto versioni
                logging.error(f"Error comparing versions ('{latest_version_str}' vs '{__version__}'): {e}")
                self._update_progress_ui(None)
                messagebox.showerror(TXT.get("update_error_title", "Update Error"), f"Error comparing versions:\n{e}")
                return
            # --- FINE NUOVA LOGICA DI CONFRONTO ---


            # --- Logica di Download/Installazione (continua da sopra se necessario) ---
            logging.info("Proceeding with download and installation...") # Questo log verrà eseguito solo se gh_version > local_version

            # 4) Find ZIP asset
            assets = data.get("assets", [])
            zip_asset = next((a for a in assets if a["name"].endswith(f"-{latest_tag}.zip")), None) \
                        or next((a for a in assets if a["name"].endswith(".zip")), None)
            if not zip_asset:
                raise ValueError(TXT.get("update_no_zip", "No ZIP asset found for the latest release."))
            # ... (resto della logica di download, unzip, replace/notify come prima) ...
            # ... assicurati che questa parte venga eseguita SOLO se l'update è confermato ...

            zip_url = zip_asset["browser_download_url"]
            zip_size = zip_asset.get("size", 0)
            logging.info(f"Found update asset: {zip_asset['name']} ({zip_size} bytes)")

            # 5) Download with progress
            self._update_progress_ui(0, TXT.get("update_status_downloading", "Downloading...").format(percent=0))
            tmpdir = tempfile.mkdtemp(prefix=f"{APP_NAME}_update_")
            downloaded_bytes = 0
            content_buffer = io.BytesIO()

            try:
                with requests.get(zip_url, stream=True, timeout=60) as r:
                    # ... (logica download con progress bar) ...
                    r.raise_for_status()
                    chunk_size = 8192
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        content_buffer.write(chunk)
                        downloaded_bytes += len(chunk)
                        if zip_size > 0:
                            percent = (downloaded_bytes / zip_size) * 100
                            self._update_progress_ui(
                                downloaded_bytes / zip_size, # Progress bar value 0.0 to 1.0
                                TXT.get("update_status_downloading", "Downloading ({percent:.0f}%)...")
                                    .format(percent=percent)
                            )
                        else:
                            self._update_progress_ui(0, TXT.get("update_downloading", "Downloading update..."), indeterminate=True)

                # 6) Unzip
                self._update_progress_ui(1.0, TXT.get("update_status_installing", "Installing update..."), indeterminate=True)
                content_buffer.seek(0)
                with zipfile.ZipFile(content_buffer) as z:
                    z.extractall(tmpdir)
                logging.info(f"Extracted update to {tmpdir}")

                # 7) Replace app / Notify for manual update
                # ... (logica esistente per notificare aggiornamento manuale) ...
                current_app_path = None
                if getattr(sys, 'frozen', False) and '.app' in sys.executable:
                    current_app_path = os.path.abspath(os.path.join(os.path.dirname(sys.executable), '..', '..', '..'))
                    logging.info(f"Detected running from bundle: {current_app_path}")

                src_app_name = f"{APP_NAME}.app"
                src_app_path = os.path.join(tmpdir, src_app_name)

                if not os.path.exists(src_app_path):
                    raise FileNotFoundError(f"Expected '{src_app_name}' not found in the downloaded ZIP.")

                if current_app_path and current_app_path.endswith(".app"):
                    dst_app_path = current_app_path
                else:
                    dst_app_path = os.path.join("/Applications", src_app_name)
                    logging.warning(f"Not running from .app bundle or detection failed. Assuming install destination: {dst_app_path}")

                logging.info(f"Attempting to replace '{dst_app_path}' with '{src_app_path}'")
                logging.warning("Self-replacement requires external mechanism. Instructing manual update.")

                messagebox.showinfo("Manual Update Required",
                                f"Update downloaded to:\n{tmpdir}\n\nPlease close this application and replace it "
                                f"({dst_app_path}) with the new version found in the folder above.")

                # Abort automatic restart logic
                # os.execv(...) # Non eseguire


            finally:
                # Clean up temp directory
                if os.path.exists(tmpdir):
                    try:
                        shutil.rmtree(tmpdir)
                        logging.info(f"Cleaned up temp directory: {tmpdir}")
                    except Exception as cleanup_err:
                        logging.error(f"Error cleaning up temp directory {tmpdir}: {cleanup_err}")


        # --- Gestione Errori Generali (Resto della funzione come prima) ---
        except requests.exceptions.RequestException as e:
            # ... gestione errori ...
            logging.error(f"Network error during update check: {e}")
            self._update_progress_ui(None)
            messagebox.showerror(TXT.get("update_error_title", "Update Error"), f"Network error checking for updates:\n{e}")
        except (zipfile.BadZipFile, ValueError, FileNotFoundError, OSError) as e:
            # ... gestione errori ...
            logging.error(f"Error during update process: {e}")
            self._update_progress_ui(None)
            messagebox.showerror(TXT.get("update_error_title", "Update Error"), f"Error during update:\n{e}")
        except Exception as e:
            # ... gestione errori ...
            logging.exception("Unexpected error during update check.")
            self._update_progress_ui(None)
            messagebox.showerror(TXT.get("update_error_title", "Update Error"), f"An unexpected error occurred:\n{e}")
        finally:
            # Assicura che la progress bar sia nascosta e lo stato resettato
            self._update_progress_ui(None)
            self.update_status_bar() # Resetta la status bar


if __name__ == "__main__":
    # --- Configurazione Iniziale Essenziale ---
    logging.basicConfig(
        level=logging.DEBUG, # Cambia a INFO per produzione
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler()
            # TODO: Aggiungere FileHandler se desiderato
        ]
    )
    logging.info(f"--- Starting {APP_NAME} v{__version__} ---")

    # --- Creazione App Principale (ma nascosta) ---
    # Creiamo l'istanza principale dell'app. Questo esegue __init__
    # che potrebbe essere lento e configura la finestra principale.
    try:
        app = CrossOverApp()
        app.withdraw() # Nascondi la finestra principale subito
    except Exception as init_error:
        # Errore critico già durante la creazione dell'istanza principale
        logging.exception("Errore critico durante la creazione di CrossOverApp!")
        # Mostra un errore Tkinter base
        import tkinter as tk
        error_root = tk.Tk()
        error_root.withdraw()
        messagebox.showerror("Fatal Error", f"Application failed to initialize:\n{init_error}")
        error_root.destroy()
        sys.exit(1)

    # --- Creazione e Visualizzazione Splash Screen ---
    # Ora creiamo lo splash come Toplevel della VERA finestra principale 'app'
    splash = Toplevel(app)

    # Calcola dimensioni e posizione per centrare lo splash
    splash_width = 450
    splash_height = 300
    # Ottieni dimensioni schermo DALLA FINESTRA PRINCIPALE 'app'
    screen_width = app.winfo_screenwidth()
    screen_height = app.winfo_screenheight()
    x = (screen_width // 2) - (splash_width // 2)
    y = (screen_height // 2) - (splash_height // 2)

    splash.geometry(f"{splash_width}x{splash_height}+{x}+{y}")
    splash.overrideredirect(True)
    splash.attributes("-topmost", True)
    # splash.wm_attributes("-transparent", True) # Opzionale
    # splash.config(background='systemTransparent') # Opzionale

    # Frame interno stilizzato
    splash_frame = ctk.CTkFrame(splash, corner_radius=15, border_width=1,
                               fg_color=(COLOR_FRAME_DARK if ctk.get_appearance_mode() == "Dark" else COLOR_FRAME_LIGHT))
    splash_frame.pack(expand=True, fill="both", padx=1, pady=1)

    # --- Contenuto dello Splash (Logo, Titolo, Versione, Progress) ---
    try:
        logo_image = ctk.CTkImage(light_image=Image.open(LOGO_PATH),
                                 dark_image=Image.open(LOGO_PATH), size=(100, 100))
        logo_label = ctk.CTkLabel(splash_frame, image=logo_image, text="")
        logo_label.pack(pady=(40, 15))
    except Exception as e:
        logging.warning(f"Logo non caricato ({LOGO_PATH}): {e}")
        ctk.CTkLabel(splash_frame, text=APP_NAME, font=ctk.CTkFont(size=30, weight="bold")).pack(pady=(40, 15))
    ctk.CTkLabel(splash_frame, text=APP_NAME, font=ctk.CTkFont(size=20, weight="bold")).pack(pady=5)
    ctk.CTkLabel(splash_frame, text=f"Version {__version__}", font=ctk.CTkFont(size=12)).pack(pady=(0, 25))
    splash_progress = ctk.CTkProgressBar(splash_frame, mode='indeterminate', height=8, corner_radius=4)
    splash_progress.pack(fill="x", padx=40, pady=(0, 40))
    splash_progress.start()
    # ---------------------------------------------------------------------

    # Forza disegno iniziale splash
    splash.update()

    # --- Funzione per chiudere lo splash e mostrare l'app ---
    def show_main_window():
        logging.info("Initialization complete. Closing splash, showing main window.")
        if splash.winfo_exists(): # Controlla se esiste ancora prima di distruggerlo
             splash_progress.stop()
             splash.destroy()
        if app.winfo_exists(): # Controlla se l'app esiste ancora
             app.deiconify() # Mostra la finestra principale
             app.focus_force() # Porta la finestra in primo piano

    # Pianifica la visualizzazione della finestra principale dopo un certo tempo
    # Questo dà tempo all'__init__ di finire e al sistema di "respirare"
    # Scegli un tempo ragionevole (es. 2000-3000 ms)
    # Puoi anche legarlo a un evento specifico se l'init segnala la fine.
    splash_duration_ms = 2500
    app.after(splash_duration_ms, show_main_window)

    # --- Avvio Loop Eventi Principale ---
    # Ora c'è una sola finestra root ('app') che gestisce tutto
    app.mainloop()

    logging.info(f"--- Exiting {APP_NAME} ---")
