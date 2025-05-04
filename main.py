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
APP_NAME = "CrossOverTrialManager"
APP_AUTHOR = "erpaffo"
PLIST_NAME = f"com.{APP_AUTHOR}.{APP_NAME}.plist"

# --- Versioning ---
def get_base_path():
    """Determines the base path (script directory or PyInstaller bundle root)."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.abspath(__file__))

def load_version(base_path):
    """Loads the application version from the VERSION file."""
    try:
        version_file = os.path.join(base_path, "VERSION")
        with open(version_file, "r") as f:
            return f.read().strip()
    except Exception as e:
        logging.error(f"Error loading VERSION file: {e}")
        return "0.0.0"

BASE_PATH = get_base_path()
__version__ = load_version(BASE_PATH)

# --- Auto-update Configuration ---
GITHUB_REPO = "erpaffo/CrossOver-Reset-Trial-GUI"

# --- Essential Paths ---
APP_SUPPORT_DIR = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
CONFIG_FILE = os.path.join(APP_SUPPORT_DIR, "config.json")
PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{PLIST_NAME}")

def get_script_path():
    """
    Determines the absolute path to the 'script.sh' file.
    Handles both standard Python script execution and bundled application execution.
    Assumes 'script.sh' is in the same directory as the main file or bundle root.

    Returns:
        str: The absolute path to 'script.sh'.
    """
    script_filename = "script.sh"
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
        logging.debug(f"Running bundled, base path (sys._MEIPASS): {base_path}")
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        logging.debug(f"Running as script, base path (dirname): {base_path}")
    script_path_result = os.path.join(base_path, script_filename)
    logging.debug(f"Full path for {script_filename} determined as: {script_path_result}")
    return script_path_result

SCRIPT_PATH = get_script_path()
CHECKSUM_FILENAME = "script.sh.sha256"
CHECKSUM_FILE = os.path.join(APP_SUPPORT_DIR, CHECKSUM_FILENAME) # Store checksum in App Support
LOGO_PATH = os.path.join(BASE_PATH, "logo.png")

# --- Notifications ---
PYOBJC_AVAILABLE = False
PYNC_AVAILABLE = False
try:
    from Foundation import NSObject, NSUserNotificationCenter, NSUserNotification
    PYOBJC_AVAILABLE = True
    logging.info("Using PyObjC for notifications.")
except ImportError:
    logging.debug("PyObjC not available or macOS < 10.14.")
    try:
        from pync import Notifier
        Notifier("Test message", title="")
        PYNC_AVAILABLE = True
        logging.info("Using pync for notifications.")
    except Exception as e:
        logging.debug(f"pync Notifier not available: {e}")
        Notifier = None

def notify(title: str, message: str):
    """Send macOS notification using the best available method (PyObjC > pync > None)."""
    if PYOBJC_AVAILABLE:
        try:
            notification = NSUserNotification.alloc().init()
            notification.setTitle_(title)
            notification.setInformativeText_(message)
            center = NSUserNotificationCenter.defaultUserNotificationCenter()
            center.deliverNotification_(notification)
            logging.debug(f"PyObjC notification sent: {title}")
            return
        except Exception as e:
            logging.error(f"PyObjC notification failed: {e}")

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
    """Loads settings from config.json, returning defaults if missing or invalid."""
    defaults = {
        "dark_mode": None,
        "check_updates_on_startup": None # None = Ask user on first launch
    }
    try:
        if not os.path.exists(CONFIG_FILE):
            return defaults
        with open(CONFIG_FILE, "r") as f:
            settings = json.load(f)
            if not isinstance(settings, dict):
                 raise ValueError("Config content is not a dictionary")

            final_settings = defaults.copy()
            final_settings.update(settings) # Overwrite defaults with loaded values

            # Validate specific keys
            if "dark_mode" in final_settings and not isinstance(final_settings["dark_mode"], (bool, type(None))):
                 logging.warning("Invalid type for 'dark_mode' in settings, using default.")
                 final_settings["dark_mode"] = defaults["dark_mode"]
            if "check_updates_on_startup" in final_settings and not isinstance(final_settings["check_updates_on_startup"], (bool, type(None))):
                 logging.warning("Invalid type for 'check_updates_on_startup', using default.")
                 final_settings["check_updates_on_startup"] = defaults["check_updates_on_startup"]

            return final_settings
    except (json.JSONDecodeError, IOError, ValueError) as e:
        logging.error(f"Error loading or parsing config file {CONFIG_FILE}: {e}. Using defaults.")
        return defaults
    
def save_settings(settings: dict):
    """Saves the provided settings dictionary to config.json."""
    try:
        os.makedirs(APP_SUPPORT_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(settings, f, indent=4)
    except IOError as e:
        logging.error(f"Error saving config file {CONFIG_FILE}: {e}")

# --- Initial Setup ---
current_settings = load_settings()
if current_settings.get("dark_mode") is True: ctk.set_appearance_mode("Dark")
elif current_settings.get("dark_mode") is False: ctk.set_appearance_mode("Light")
else: ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# --- UI Constants & Theme ---
BADGE_SUCCESS_TIMEOUT_MS = 2500
COLOR_BACKGROUND_LIGHT = "#F2F2F7"; COLOR_BACKGROUND_DARK = "#1E1E1E"
COLOR_FRAME_LIGHT = "#EDEDED"; COLOR_FRAME_DARK = "#2C2C2E"
COLOR_TEXTBOX_LIGHT = "#FFFFFF"; COLOR_TEXTBOX_DARK = "#1E1E1E"
COLOR_TEXT_LIGHT = "black"; COLOR_TEXT_DARK = "white"
COLOR_PLACEHOLDER_LIGHT = "#666666"; COLOR_PLACEHOLDER_DARK = "#B0B0B0"
BTN_PRIMARY_FG = "#0A84FF"; BTN_SECONDARY_FG = "#30D158"; BTN_DANGER_FG = "#FF453A"
BTN_HOVER = "#096dd9"; BTN_TEXT_COLOR = "white"
TAG_COLORS = {
    "STEP": "#FFA500", "INFO": "#0A84FF", "SUCCESS": "#30D158",
    "WARNING": "#FFD60A", "ERROR": "#FF453A", "CMD": "#888888",
    "SCRIPT": "#FFFFFF" if ctk.get_appearance_mode() == "Dark" else "#000000"
}

# --- I18N Language Definitions ---
LANGUAGES = {
    "it": {
        "name": "Italiano", "title": f"{APP_NAME} v{__version__}",
        "execute": "Esegui Reset", "install": "Installa Servizio", "uninstall": "Disinstalla Servizio",
        "help": "Aiuto", "show_script": "Mostra Script", "export": "Esporta Log", "clear": "Pulisci Log",
        "filter": "Filtra Log...", "done": "Completato!", "error_occurred": "Errore durante l'esecuzione!",
        "status_ready": "Pronto.", "status_running": "Esecuzione '{action}'...",
        "status_checksum_ok": "Checksum Script OK.", "status_checksum_err": "ERRORE Checksum Script!", "status_checksum_na": "Checksum N/A.",
        "status_script_exec_error": "Errore esecuzione: {err}", "status_exported": "Log esportato.",
        "status_script_not_found": "ERRORE: Script script.sh non trovato!", "status_script_not_exec": "ERRORE: Script script.sh non eseguibile!",
        "help_text": (f"{APP_NAME} v{__version__}\nQuesta app resetta la trial di CrossOver.\n\n"
                      "• Esegui Reset: Effettua un reset manuale ora.\n"
                      "• Installa Servizio: Imposta un reset automatico all'avvio.\n"
                      "• Disinstalla Servizio: Rimuove il servizio di auto-reset.\n\n"
                      "Nota: L'installazione/disinstallazione richiede privilegi amministrativi.\n"
                      "L'app è intesa per uso didattico ed etico."),
        "script_viewer_title": "Visualizzatore Script - script.sh",
        "checksum_err_msg": "Il checksum dello script 'script.sh' è cambiato. Potrebbe essere stato modificato o corrotto.",
        "checksum_ok_msg": "Checksum verificato.", "checksum_saved_msg": "Checksum calcolato e salvato.",
        "error_title": "Errore", "warning_title": "Attenzione",
        "checksum_mismatch_title": "Checksum Non Corrisponde",
        "checksum_mismatch_ask_fix": "Checksum per '{script_name}' non corrisponde.\nLo script potrebbe essere corrotto/modificato.\n\nTi fidi della versione attuale e vuoi aggiornare il file checksum?",
        "checksum_updated_msg": "File checksum aggiornato.", "checksum_update_error_msg": "Impossibile aggiornare il file checksum.",
        "checksum_not_updated_msg": "Checksum non corrispondente ignorato.",
        "checksum_missing_title": "File Checksum Mancante",
        "checksum_missing_ask_create": "File checksum per '{script_name}' non trovato.\n\nVuoi crearne uno basato sulla versione attuale?",
        "checksum_created_msg": "File checksum creato.", "checksum_create_error_msg": "Impossibile creare il file checksum.",
        "checksum_not_created_msg": "File checksum non creato.",
        "menu_settings": "Impostazioni", "menu_dark_mode": "Modalità Scura", "menu_language": "Lingua", "menu_check_updates": "Controlla Aggiornamenti...",
        "update_available_title": "Aggiornamento Disponibile", "update_ask_install": "Versione {new_version} disponibile. Scaricare e installare ora?",
        "update_no_zip": "Nessun file ZIP trovato.", "update_downloading": "Download aggiornamento...", "update_installing": "Installazione aggiornamento...",
        "update_success_title": "Aggiornato", "update_success_msg": "Aggiornato alla versione {new_version}. Riavvio in corso...",
        "update_error_title": "Errore Aggiornamento", "update_up_to_date_title": "Aggiornato",
        "update_up_to_date_msg": "Stai già usando l'ultima versione ({current_version}).",
        "update_status_checking": "Verifica aggiornamenti...", "update_status_downloading": "Download ({percent:.0f}%)...",
        "update_status_installing": "Installazione...", "update_status_error": "Errore aggiornamento.",
        "update_newer_local_title": "Versione Sviluppo", "update_newer_local_msg": "Versione attuale ({local_version}) più recente della release ({gh_version}).",
        "service": "Servizio", "service_status_active": "Attivo", "service_status_inactive": "Non Installato", "service_status_error": "Errore Verifica",
    },
    "en": {
        "name": "English", "title": f"{APP_NAME} v{__version__}",
        "execute": "Run Reset", "install": "Install Service", "uninstall": "Uninstall Service",
        "help": "Help", "show_script": "Show Script", "export": "Export Log", "clear": "Clear Log",
        "filter": "Filter Log...", "done": "Done!", "error_occurred": "Error during execution!",
        "status_ready": "Ready.", "status_running": "Running '{action}'...",
        "status_checksum_ok": "Script Checksum OK.", "status_checksum_err": "ERROR Script Checksum!", "status_checksum_na": "Checksum N/A.",
        "status_script_exec_error": "Execution error: {err}", "status_exported": "Log exported.",
        "status_script_not_found": "ERROR: script.sh script not found!", "status_script_not_exec": "ERROR: script.sh script not executable!",
        "help_text": (f"{APP_NAME} v{__version__}\nThis app resets the CrossOver trial.\n\n"
                      "• Run Reset: Perform a manual reset now.\n"
                      "• Install Service: Set up automatic reset on startup.\n"
                      "• Uninstall Service: Remove the auto-reset service.\n\n"
                      "Note: Install/Uninstall requires administrative privileges.\n"
                      "This app is for educational/ethical use only."),
        "script_viewer_title": "Script Viewer - script.sh",
        "checksum_err_msg": "Checksum of 'script.sh' has changed. It might be modified or corrupted.",
        "checksum_ok_msg": "Checksum verified.", "checksum_saved_msg": "Checksum calculated and saved.",
        "error_title": "Error", "warning_title": "Warning",
        "checksum_mismatch_title": "Checksum Mismatch",
        "checksum_mismatch_ask_fix": "Checksum for '{script_name}' mismatch.\nScript might be corrupted/modified.\n\nTrust current version and update checksum file?",
        "checksum_updated_msg": "Checksum file updated.", "checksum_update_error_msg": "Failed to update checksum file.",
        "checksum_not_updated_msg": "Checksum mismatch ignored.",
        "checksum_missing_title": "Checksum File Missing",
        "checksum_missing_ask_create": "Checksum file for '{script_name}' not found.\n\nCreate one based on the current version?",
        "checksum_created_msg": "Checksum file created.", "checksum_create_error_msg": "Failed to create checksum file.",
        "checksum_not_created_msg": "Checksum file not created.",
        "menu_settings": "Settings", "menu_dark_mode": "Dark Mode", "menu_language": "Language", "menu_check_updates": "Check for Updates...",
        "update_available_title": "Update Available", "update_ask_install": "Version {new_version} available. Download and install now?",
        "update_no_zip": "No ZIP asset found.", "update_downloading": "Downloading update...", "update_installing": "Installing update...",
        "update_success_title": "Updated", "update_success_msg": "Updated to version {new_version}. Relaunching...",
        "update_error_title": "Update Error", "update_up_to_date_title": "Up to Date",
        "update_up_to_date_msg": "You are already running the latest version ({current_version}).",
        "update_status_checking": "Checking for updates...", "update_status_downloading": "Downloading ({percent:.0f}%)...",
        "update_status_installing": "Installing...", "update_status_error": "Update error.",
        "update_newer_local_title": "Development Version", "update_newer_local_msg": "Current version ({local_version}) is newer than latest release ({gh_version}).",
        "service": "Service", "service_status_active": "Active", "service_status_inactive": "Not Installed", "service_status_error": "Error Checking",
    }
}
# TODO: Load language from settings if implemented
# TODO: Implement other languages
LANG = "it"
TXT = LANGUAGES[LANG]

# --- Log Queue ---
log_queue = queue.Queue()

# --- Main Application Class ---
class CrossOverApp(ctk.CTk):
    """Main application window class for CrossOver Trial Manager."""

    # Dentro la classe CrossOverApp:
    def __init__(self):
        """Initializes the main application window, UI, and state."""
        super().__init__()

        # --- Initialize instance variables ---
        self.checksum_valid = None
        self.script_executable = False
        self.script_found = False
        self.current_action = None
        self.service_active = False
        self.bottles_path_override = None
        self.settings = current_settings # Use globally loaded settings

        # --- Window Setup ---
        self.title(TXT["title"])
        self.geometry("1000x700")
        self.minsize(800, 500)
        self.resizable(True, True)
        self._set_appearance()

        # --- UI Variables ---
        self.lang_var = ctk.StringVar(value=TXT["name"]) # TODO: Set from settings
        self.mode_var = ctk.BooleanVar(value=(ctk.get_appearance_mode() == "Dark"))
        self.update_check_on_startup_var = ctk.BooleanVar(
            value=bool(self.settings.get("check_updates_on_startup", False))
        )

        # --- Actions Definition ---
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

        # --- Build UI ---
        self._create_menu()
        self._create_ui_layout() # Builds widgets

        # --- Initialize Log List & Colors ---
        self.full_log = []
        self._update_ui_colors() # Apply colors to widgets

        # --- Start Log Queue Processor ---
        self.after(100, self._process_log_queue)

        # --- Delayed Startup Update Check ---
        # Check setting AFTER the main window might be ready
        if self.settings.get("check_updates_on_startup") is True:
             logging.info("Automatic update check on startup enabled. Scheduling check.")
             # Schedule check after a delay to avoid blocking UI init
             self.after(3000, self.check_for_updates_threaded)
        else:
             logging.info("Automatic update check on startup disabled or not set.")

        # Initial local checks (checksum, service status) are now run
        # in the __main__ block after the splash screen is shown.

    # --- UI Creation Methods ---
    def _create_ui_layout(self):
        """Creates the main UI layout."""
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)

        # Left frame
        self.left_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        self.left_frame.grid_propagate(False)

        for action in self.actions:
            key, cmd, color = action["key"], action["cmd"], action["color"]
            btn = ctk.CTkButton(self.left_frame, text=TXT.get(key, key), compound="left", anchor="w",
                                width=180, height=36, fg_color=color, hover_color=BTN_HOVER,
                                text_color=BTN_TEXT_COLOR, command=cmd)
            btn.pack(pady=8, padx=10, anchor="n")
            self.action_buttons[key] = btn
            self._create_badges(btn, key)

        self.action_progress_bar = ctk.CTkProgressBar(self.left_frame, height=10, corner_radius=5)
        self.action_progress_bar.set(0)

        self.service_status_label = ctk.CTkLabel(self.left_frame, text=f"{TXT.get('service', 'Service')}: ...", anchor="w")
        self.service_status_label.pack(side="bottom", pady=(0, 10), padx=10, anchor="w")

        # Right frame
        self.right_frame = ctk.CTkFrame(self, corner_radius=0)
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        self.right_frame.grid_rowconfigure(1, weight=1)
        self.right_frame.grid_columnconfigure(0, weight=1)

        filter_frame = ctk.CTkFrame(self.right_frame)
        filter_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10), padx=10)
        filter_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(filter_frame, text=TXT["filter"] + ":").grid(row=0, column=0, padx=(0, 5))
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(filter_frame, textvariable=self.search_var, placeholder_text=TXT["filter"])
        self.search_entry.grid(row=0, column=1, sticky="ew")
        self.search_entry.bind("<KeyRelease>", self.filter_log)

        self.output_box = ctk.CTkTextbox(self.right_frame, corner_radius=6)
        self.output_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.output_box.configure(state="disabled")
        self._configure_log_tags()

        # Update Progress Bar (below log)
        self.update_progress_bar = ctk.CTkProgressBar(self, height=10)
        self.update_progress_bar.set(0)
        self.update_progress_bar.grid(row=1, column=1, sticky="ew", padx=(5, 10), pady=(0, 5))
        self.update_progress_bar.grid_remove() # Hidden initially

        # Status Bar (bottom)
        self.status_bar = ctk.CTkFrame(self, height=25, corner_radius=0)
        self.status_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        self.status_label = ctk.CTkLabel(self.status_bar, text=TXT["status_ready"], anchor="w")
        self.status_label.pack(side="left", padx=10)
        self.checksum_status_label = ctk.CTkLabel(self.status_bar, text="", anchor="e", width=150)
        self.checksum_status_label.pack(side="right", padx=10)

    def _create_menu(self):
        """Creates the main application menu bar."""
        self.menu_bar = Menu(self)
        self.config(menu=self.menu_bar)

        settings_menu = Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label=TXT.get("menu_settings", "Settings"), menu=settings_menu)

        settings_menu.add_checkbutton(label=TXT.get("menu_dark_mode", "Dark Mode"),
                                      variable=self.mode_var, command=self.toggle_mode)

        settings_menu.add_checkbutton(
            label=TXT.get("menu_check_updates_startup", "Check for Updates on Startup"),
            variable=self.update_check_on_startup_var,
            command=self.toggle_startup_update_check
        )

        language_menu = Menu(settings_menu, tearoff=0)
        settings_menu.add_cascade(label=TXT.get("menu_language", "Language"), menu=language_menu)
        for code, d in LANGUAGES.items():
            language_menu.add_radiobutton(label=d["name"], variable=self.lang_var,
                                          value=d["name"], command=lambda c=d["name"]: self.change_language(c))
        # TODO: Load/Save selected language

        settings_menu.add_separator()
        settings_menu.add_command(label=TXT.get("menu_check_updates", "Check for Updates..."),
                                  command=self.check_for_updates_threaded)


    def toggle_startup_update_check(self):
        """Toggles the setting for checking updates on startup and saves it."""
        new_value = self.update_check_on_startup_var.get()
        self.settings["check_updates_on_startup"] = new_value
        save_settings(self.settings)
        logging.info(f"Check for updates on startup {'enabled' if new_value else 'disabled'}.")



    # --- UI Update & State Methods ---
    def _create_badges(self, parent_button, action_key):
        """Creates success/error badges for an action button."""
        badge_style = {"width": 16, "height": 16, "text_color": "white", "corner_radius": 8, "font": ctk.CTkFont(size=10, weight="bold")}
        err_badge = ctk.CTkLabel(parent_button, text="", fg_color=TAG_COLORS["ERROR"], **badge_style)
        succ_badge = ctk.CTkLabel(parent_button, text="", fg_color=TAG_COLORS["SUCCESS"], **badge_style)
        self.badges[action_key] = {"error": err_badge, "success": succ_badge}
        err_badge.place(relx=1.0, rely=0.0, x=-5, y=5, anchor="ne")
        succ_badge.place(relx=0.0, rely=0.0, x=5, y=5, anchor="nw")
        err_badge.lower()
        succ_badge.lower()

    def _update_badge(self, action_key, badge_type, count):
        """Updates the text and visibility of a specific badge."""
        if action_key in self.badges and badge_type in self.badges[action_key]:
            badge = self.badges[action_key][badge_type]
            badge.configure(text=str(count) if count > 0 else "")
            badge.lift() if count > 0 else badge.lower()

    def _reset_badges(self, action_key):
        """Resets both badges for a specific action."""
        self._update_badge(action_key, "success", 0)
        self._update_badge(action_key, "error", 0)

    def _configure_log_tags(self):
        """Configures color tags for the log output textbox."""
        mode = ctk.get_appearance_mode()
        TAG_COLORS["SCRIPT"] = COLOR_TEXT_DARK if mode == "Dark" else COLOR_TEXT_LIGHT
        if hasattr(self, "output_box"):
            for level, color in TAG_COLORS.items():
                self.output_box.tag_config(level, foreground=color)

    def _set_appearance(self):
        """Sets the initial global application appearance based on CTk mode."""
        mode = ctk.get_appearance_mode()
        fg_color = COLOR_BACKGROUND_DARK if mode == "Dark" else COLOR_BACKGROUND_LIGHT
        self.configure(fg_color=fg_color)

    def _update_ui_colors(self):
        """Updates widget colors based on the current appearance mode."""
        mode = ctk.get_appearance_mode()
        is_dark = (mode == "Dark")
        bg_color = COLOR_BACKGROUND_DARK if is_dark else COLOR_BACKGROUND_LIGHT
        frame_color = COLOR_FRAME_DARK if is_dark else COLOR_FRAME_LIGHT
        textbox_color = COLOR_TEXTBOX_DARK if is_dark else COLOR_TEXTBOX_LIGHT
        text_color = COLOR_TEXT_DARK if is_dark else COLOR_TEXT_LIGHT
        placeholder_color = COLOR_PLACEHOLDER_DARK if is_dark else COLOR_PLACEHOLDER_LIGHT

        self.configure(fg_color=bg_color)
        widgets_to_update = [
            ("left_frame", {"fg_color": frame_color}),
            ("right_frame", {"fg_color": frame_color}),
            ("status_bar", {"fg_color": frame_color}),
            ("status_label", {"text_color": text_color}),
            ("checksum_status_label", {"text_color": text_color}),
            ("service_status_label", {"text_color": text_color}),
            ("search_entry", {"fg_color": textbox_color, "text_color": text_color,
                             "border_color": frame_color, "placeholder_text_color": placeholder_color}),
            ("output_box", {"fg_color": textbox_color, "text_color": text_color, "border_color": frame_color})
        ]
        for widget_name, config in widgets_to_update:
            if hasattr(self, widget_name):
                getattr(self, widget_name).configure(**config)

        self._configure_log_tags()
        self.filter_log()

    def toggle_mode(self):
        """Toggles between light and dark mode and saves the setting."""
        is_dark = self.mode_var.get()
        mode = "Dark" if is_dark else "Light"
        ctk.set_appearance_mode(mode)
        self.settings["dark_mode"] = is_dark
        save_settings(self.settings)
        self._update_ui_colors()

    def change_language(self, choice):
        """Changes the application language."""
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
            self._create_menu()
            self.update_status_bar()
            # Update other language-dependent elements if needed

    # --- Log Processing Methods ---
    def _process_log_queue(self):
        """Processes messages from the log queue in the main GUI thread."""
        try:
            while True:
                log_entry = log_queue.get_nowait()
                self._append_text_to_gui(log_entry["text"], log_entry["log_level"])
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_log_queue)

    def _log(self, text: str, level: str = "CMD"):
        """Adds a log message to the queue for GUI update."""
        log_queue.put({"text": text, "log_level": level})

    def _append_text_to_gui(self, text: str, log_level: str = "CMD"):
        """Appends formatted text to the log output box (GUI thread)."""
        self.full_log.append(text)
        clean_text = re.sub(r'\x1B\[[0-9;]*[mK]', '', text).rstrip()
        if not clean_text: return

        effective_tag = log_level
        match = re.match(r'^\[(STEP|INFO|SUCCESS|WARNING|ERROR)\]', clean_text)
        if match: effective_tag = match.group(1)

        tag_to_apply = effective_tag if effective_tag in TAG_COLORS else "CMD"
        try:
             self.output_box.configure(state="normal")
             self.output_box.insert("end", clean_text + "\n", tag_to_apply)
             self.output_box.see("end")
             self.output_box.configure(state="disabled")
        except Exception as e:
             logging.error(f"Error appending text to output_box: {e}")


    def filter_log(self, event=None):
        """Filters the log display based on the search entry content."""
        if not hasattr(self, "search_var") or not hasattr(self, "output_box"): return
        query = self.search_var.get().lower()
        try:
            self.output_box.configure(state="normal")
            self.output_box.delete("1.0", "end")
            for line in self.full_log:
                if query in line.lower():
                    clean_line = re.sub(r'\x1B\[[0-9;]*[mK]', '', line).rstrip()
                    if not clean_line: continue
                    effective_tag = "CMD"
                    match = re.match(r'^\[(STEP|INFO|SUCCESS|WARNING|ERROR)\]', clean_line)
                    if match: effective_tag = match.group(1)
                    tag_to_apply = effective_tag if effective_tag in TAG_COLORS else "CMD"
                    self.output_box.insert("end", clean_line + "\n", tag_to_apply)
            self.output_box.see("end")
        except Exception as e:
            logging.error(f"Error filtering log: {e}")
        finally:
            if hasattr(self, "output_box"):
                 self.output_box.configure(state="disabled")


    def clear_log(self):
        """Clears the log display and history."""
        if self.current_action: return
        self.full_log = []
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        self.output_box.configure(state="disabled")
        for action in self.actions: self._reset_badges(action["key"])
        for key in ["execute", "install", "uninstall"]: self._reset_badges(key)

    def export_log(self):
        """Exports the current log content to a text file."""
        if self.current_action: return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title=TXT.get("export", "Export Log")
        )
        if path:
            try:
                with open(path, "w", encoding='utf-8') as f:
                    f.write(self.output_box.get("1.0", "end"))
                self.update_status_bar(TXT["status_exported"])
                notify(TXT["done"], TXT["status_exported"])
            except Exception as e:
                log_msg = f"Failed to export log: {e}"
                self._log(f"[ERROR] {log_msg}", "ERROR")
                messagebox.showerror(TXT["error_title"], log_msg)
                self.update_status_bar(f"Export failed: {e}")


    # --- Script/System Interaction Methods ---
    def _check_script_status(self):
        """Checks script existence, executability, and checksum."""
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
            self.verify_checksum()
        else:
            self._log(f"[ERROR] {TXT['status_script_not_found']}", "ERROR")
            self.script_executable = False
            self.checksum_valid = None

        # Update button states based on script status
        can_run_script = self.script_found and self.script_executable
        if hasattr(self, 'action_buttons'):
            for key in ["execute", "install", "uninstall", "show_script"]:
                if key in self.action_buttons:
                    self.action_buttons[key].configure(state="normal" if can_run_script else "disabled")

    def _update_checksum_file(self, checksum_path: str, hash_to_write: str) -> bool:
        """Helper to write the checksum file, ensuring directory exists."""
        try:
            # Ensure the target directory exists (useful for App Support)
            os.makedirs(os.path.dirname(checksum_path), exist_ok=True)
            with open(checksum_path, "w") as f:
                f.write(hash_to_write)
            logging.info(f"Checksum updated/created successfully: {checksum_path}")
            return True
        except Exception as e:
            log_msg = f"Failed to write checksum file '{checksum_path}': {e}"
            self._log(f"[ERROR] {log_msg}", "ERROR")
            messagebox.showerror(TXT["error_title"], log_msg)
            return False

    def verify_checksum(self):
        """Verifies script checksum, prompts to create/update if needed."""
        script_basename = os.path.basename(SCRIPT_PATH)
        self.checksum_valid = None

        if not self.script_found: return

        try:
            sha = hashlib.sha256()
            with open(SCRIPT_PATH, "rb") as f:
                while True:
                    chunk = f.read(8192);
                    if not chunk: break
                    sha.update(chunk)
            current_hash = sha.hexdigest()
            logging.debug(f"Calculated hash for {SCRIPT_PATH}: {current_hash}")

            if os.path.exists(CHECKSUM_FILE):
                try:
                    with open(CHECKSUM_FILE, "r") as cf:
                        expected_hash = cf.read().strip()
                except Exception as e:
                     logging.error(f"Error reading checksum file {CHECKSUM_FILE}: {e}")
                     self.checksum_valid = None # Treat read error as N/A
                     self._log(f"[ERROR] Failed to read checksum file: {e}", "ERROR")
                     messagebox.showerror(TXT["error_title"], f"Error reading checksum file:\n{e}")
                     self.after(0, self.update_status_bar)
                     return

                logging.debug(f"Expected hash from {CHECKSUM_FILE}: {expected_hash}")

                if expected_hash == current_hash:
                    self.checksum_valid = True
                    self._log(f"[INFO] {TXT['checksum_ok_msg']} ({script_basename})", "INFO")
                else:
                    self.checksum_valid = False
                    self._log(f"[ERROR] Checksum mismatch for {script_basename}!", "ERROR")
                    self._log(f"[ERROR]   Expected : {expected_hash}", "ERROR")
                    self._log(f"[ERROR]   Calculated: {current_hash}", "ERROR")
                    q_title = TXT.get("checksum_mismatch_title", "Checksum Mismatch")
                    q_msg = TXT.get("checksum_mismatch_ask_fix", "...").format(script_name=script_basename)
                    user_choice = messagebox.askyesno(q_title, q_msg)
                    if user_choice:
                        if self._update_checksum_file(CHECKSUM_FILE, current_hash):
                            self.checksum_valid = True
                            self._log(f"[INFO] {TXT.get('checksum_updated_msg', 'Checksum file updated.')}", "INFO")
                        else:
                             self.checksum_valid = False # Failed to update, remains invalid
                             self._log(f"[ERROR] {TXT.get('checksum_update_error_msg', 'Failed to update checksum file.')}", "ERROR")
                    else:
                        self._log(f"[WARNING] {TXT.get('checksum_not_updated_msg', 'Checksum mismatch ignored.')}", "WARNING")
            else:
                self.checksum_valid = None
                self._log(f"[WARNING] Checksum file '{CHECKSUM_FILENAME}' not found in {APP_SUPPORT_DIR}.", "WARNING")
                q_title = TXT.get("checksum_missing_title", "Checksum File Missing")
                q_msg = TXT.get("checksum_missing_ask_create", "...").format(script_name=script_basename)
                user_choice = messagebox.askyesno(q_title, q_msg)
                if user_choice:
                    if self._update_checksum_file(CHECKSUM_FILE, current_hash):
                        self.checksum_valid = True
                        self._log(f"[INFO] {TXT.get('checksum_created_msg', 'Checksum file created.')}", "INFO")
                    else:
                        self.checksum_valid = None # Failed to create
                        self._log(f"[ERROR] {TXT.get('checksum_create_error_msg', 'Failed to create checksum file.')}", "ERROR")
                else:
                    self._log(f"[INFO] {TXT.get('checksum_not_created_msg', 'Checksum file not created.')}", "INFO")

        except FileNotFoundError:
             self.checksum_valid = None # Script itself not found during hash calc
             self._log(f"[ERROR] Script file not found during checksum calculation: {SCRIPT_PATH}", "ERROR")
        except Exception as e:
            self.checksum_valid = None
            self._log(f"[ERROR] Error during checksum verification/handling: {e}", "ERROR")
            messagebox.showerror(TXT["error_title"], f"Checksum Error: {e}")

        self.after(0, self.update_status_bar)


    def update_status_bar(self, message=None, is_update_status=False):
        """Updates the status bar text and checksum status."""
        # Ensure UI elements exist before proceeding
        if not hasattr(self, "status_label") or not self.status_label.winfo_exists():
            logging.warning("update_status_bar called but status_label does not exist.")
            return

        # --- Logic for the main status label ---
        if is_update_status and message:
            # If it's an update status message, always display it directly.
            self.status_label.configure(text=message)
        elif message:
            # A specific, non-update message was provided. Display it.
            self.status_label.configure(text=message)
            # Setting a general message often implies no specific action is running anymore.
            # self.current_action = None # Optional: Uncomment if setting a message should clear the action state
        elif self.current_action and self.current_action in TXT: # Check if key exists!
            # An action is running, and it has a translation defined in TXT.
            action_text = TXT.get(self.current_action, self.current_action) # Get translated name or key itself as fallback
            try:
                status_running_msg = TXT["status_running"].format(action=action_text)
                self.status_label.configure(text=status_running_msg)
            except KeyError:
                logging.error(f"Key 'status_running' missing in the current language dictionary (LANG='{LANG}')")
                self.status_label.configure(text=f"Running {action_text}...") # Fallback text
        elif self.current_action:
            # An action is running, but it doesn't have a direct translation (like 'update').
            # Show a generic message or fallback. Avoid KeyError.
            logging.warning(f"Action '{self.current_action}' running but not found in TXT dictionary.")
            self.status_label.configure(text=f"Running action: {self.current_action}...") # Simple fallback
        else:
            # Default to "Ready" if no action and no specific message.
            self.status_label.configure(text=TXT.get("status_ready", "Ready.")) # Use .get for safety

        # --- Logic for the checksum status label ---
        # Check if update progress bar exists and is visible
        update_bar_visible = (hasattr(self, "update_progress_bar") and
                            self.update_progress_bar.winfo_exists() and
                            self.update_progress_bar.winfo_ismapped())

        if not update_bar_visible:
            # Update checksum status only if update bar is hidden
            cs_text, cs_color = "", COLOR_TEXT_LIGHT # Default colors based on theme
            if self.checksum_valid is True:
                cs_text, cs_color = TXT.get("status_checksum_ok", "Checksum OK"), TAG_COLORS.get("SUCCESS", "green")
            elif self.checksum_valid is False:
                cs_text, cs_color = TXT.get("status_checksum_err", "Checksum ERROR"), TAG_COLORS.get("ERROR", "red")
            else: # None or other state
                cs_text = TXT.get("status_script_not_found", "Script missing") if not self.script_found else TXT.get("status_checksum_na", "Checksum N/A")
                cs_color = TAG_COLORS.get("ERROR", "red") if not self.script_found else TAG_COLORS.get("WARNING", "orange")

            # Check if checksum_status_label exists before configuring
            if hasattr(self, "checksum_status_label") and self.checksum_status_label.winfo_exists():
                # Determine actual text color based on theme if color key not found
                default_text_color = COLOR_TEXT_DARK if ctk.get_appearance_mode() == "Dark" else COLOR_TEXT_LIGHT
                final_cs_color = cs_color if cs_color in [TAG_COLORS.get("SUCCESS"), TAG_COLORS.get("ERROR"), TAG_COLORS.get("WARNING")] else default_text_color
                self.checksum_status_label.configure(text=cs_text, text_color=final_cs_color)
        elif hasattr(self, "checksum_status_label") and self.checksum_status_label.winfo_exists():
            # Optionally clear checksum status when update is running
            self.checksum_status_label.configure(text="")

    def _set_ui_busy(self, busy: bool, action_key: str):
        """Disables/enables UI controls and shows/hides action progress bar."""
        self.current_action = action_key if busy else None
        state = "disabled" if busy else "normal"

        if hasattr(self, 'action_buttons'):
            for key, button in self.action_buttons.items():
                allow_always = key in ["clear", "help"] and not busy
                disable_when_busy = key not in ["clear", "help"]
                if allow_always:
                    button.configure(state="normal")
                elif disable_when_busy:
                    button.configure(state=state)

        if hasattr(self, 'search_entry'): self.search_entry.configure(state=state)
        if hasattr(self, 'action_buttons') and "clear" in self.action_buttons:
             self.action_buttons["clear"].configure(state="normal" if not busy else "disabled")

        # Manage action progress bar
        if hasattr(self, "action_progress_bar") and hasattr(self, "service_status_label"):
            if busy:
                self.action_progress_bar.configure(mode="indeterminate")
                # Pack it above the service status label
                self.action_progress_bar.pack(pady=(10, 5), padx=10, fill="x", anchor="s", before=self.service_status_label)
                self.action_progress_bar.start()
            else:
                self.action_progress_bar.stop()
                self.action_progress_bar.pack_forget()

        self.update_status_bar()


    def run_bash_script(self, action_key: str):
        """Runs the bash script in a background thread."""
        if self.current_action: return
        if not self.script_found or not self.script_executable:
            self._log(f"[ERROR] Cannot run script (not found or not executable).", "ERROR")
            messagebox.showerror(TXT["error_title"], TXT["status_script_not_found"] if not self.script_found else TXT["status_script_not_exec"])
            return

        if action_key in ["install", "uninstall", "execute"] and self.checksum_valid is False:
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
                                        text=True, encoding='utf-8', errors='replace', bufsize=1, universal_newlines=True)

                for line in iter(proc.stdout.readline, ''):
                    self._log(line, "CMD")
                    if "[ERROR]" in line: error_count += 1; self.after(0, lambda c=error_count: self._update_badge(action_key, "error", c))
                    if "[SUCCESS]" in line: success_count += 1; self.after(0, lambda c=success_count: self._update_badge(action_key, "success", c))

                proc.stdout.close()
                return_code = proc.wait()

                if return_code == 0:
                    self._log(f"[SUCCESS] Script finished successfully (Code: {return_code}).", "SUCCESS")
                    if success_count == 0: success_count = 1; self.after(0, lambda c=success_count: self._update_badge(action_key, "success", c))
                else:
                    self._log(f"[ERROR] Script finished with error (Code: {return_code}).", "ERROR")
                    if error_count == 0: error_count = 1; self.after(0, lambda c=error_count: self._update_badge(action_key, "error", c))

            except FileNotFoundError:
                self._log(f"[ERROR] Command 'bash' or script '{SCRIPT_PATH}' not found.", "ERROR")
                return_code = -1; error_count += 1; self.after(0, lambda c=error_count: self._update_badge(action_key, "error", c))
            except Exception as e:
                self._log(f"[ERROR] Unexpected error during script execution: {e}", "ERROR")
                return_code = -1; error_count += 1; self.after(0, lambda c=error_count: self._update_badge(action_key, "error", c))
            finally:
                self._log(f"=== [{action_key.upper()}] END (Exit Code: {return_code}) ===\n", "STEP")
                self.after(0, self._finalize_script_run, action_key, return_code)

        thread = threading.Thread(target=task, daemon=True)
        thread.start()


    def _finalize_script_run(self, action_key: str, return_code: int):
        """GUI operations after the script thread finishes."""
        self._set_ui_busy(False, action_key)

        if return_code == 0:
            msg = f"{TXT.get(action_key, action_key)} - {TXT['done']}"
            messagebox.showinfo(TXT["done"], msg)
            notify(TXT["done"], msg)
            self.after(BADGE_SUCCESS_TIMEOUT_MS, lambda: self._update_badge(action_key, "success", 0))
        else:
            msg = f"{TXT.get(action_key, action_key)} - {TXT['error_occurred']}"
            messagebox.showerror(TXT["error_title"], msg)
            notify(TXT["error_title"], msg)
            # Keep error badge until cleared manually

        self.refresh_status() # Refresh service status after install/uninstall actions
        self.update_status_bar()


    def refresh_status(self):
        """Updates the LaunchAgent service status label."""
        active_text = TXT.get("service_status_active", "Active")
        inactive_text = TXT.get("service_status_inactive", "Not Installed")
        status_text = inactive_text
        self.service_active = False

        try:
            result = subprocess.run(['launchctl', 'list', PLIST_NAME], capture_output=True, text=True, check=False, timeout=2)
            if result.returncode == 0 and PLIST_NAME in result.stdout:
                 status_text = active_text
                 self.service_active = True
            else:
                 self.service_active = os.path.exists(PLIST_PATH)
                 status_text = active_text if self.service_active else inactive_text
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
             logging.warning(f"launchctl check failed ({e}), checking service status via file existence only.")
             self.service_active = os.path.exists(PLIST_PATH)
             status_text = active_text if self.service_active else inactive_text
        except Exception as e:
            logging.error(f"Error checking service status with launchctl: {e}")
            self.service_active = os.path.exists(PLIST_PATH) # Fallback check
            status_text = active_text if self.service_active else inactive_text

        if hasattr(self, "service_status_label"):
            self.service_status_label.configure(text=f"{TXT.get('service', 'Service')}: {status_text}")

    # --- Action Methods (Wrappers) ---
    def execute_reset(self):   self.run_bash_script("execute")
    def install_service(self): self.run_bash_script("install")
    def uninstall_service(self): self.run_bash_script("uninstall")

    def show_help(self):
        """Shows the help message box."""
        messagebox.showinfo(TXT["help"], TXT["help_text"])

    def show_script_window(self):
        """Shows the script content in a separate window with syntax highlighting."""
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
            script_textbox.tag_config("SCRIPT", foreground=text_color)

            lexer = BashLexer()
            token_colors = {
                "Token.Comment": "#6a737d",
                "Token.Keyword": BTN_HOVER, "Token.Name.Builtin": BTN_HOVER,
                "Token.Literal.String": TAG_COLORS["SUCCESS"],
                "Token.Literal.Number": TAG_COLORS["INFO"],
                "Token.Operator": TAG_COLORS["ERROR"],
                "Token.Name.Variable": TAG_COLORS["STEP"],
            }
            for token_name, color in token_colors.items():
                 tag_name = token_name.replace(".", "_")
                 script_textbox.tag_config(tag_name, foreground=color)

            for ttype, value in lex(script_content, lexer):
                 applied_tag = "SCRIPT" # Default
                 current_ttype_str = str(ttype)
                 for token_name in token_colors:
                     if current_ttype_str.startswith(token_name):
                         applied_tag = token_name.replace(".", "_")
                         break
                 script_textbox.insert("end", value, (applied_tag,))

            script_textbox.configure(state="disabled")

        except FileNotFoundError:
             messagebox.showerror(TXT["error_title"], TXT["status_script_not_found"])
        except Exception as e:
             logging.exception("Error displaying script window")
             messagebox.showerror(TXT["error_title"], f"Error reading/displaying script: {e}")

    # --- Auto Update Methods ---
    def check_for_updates_threaded(self):
        """Runs the update check in a background thread."""
        if self.current_action == "update": # Prevent multiple update checks
             logging.warning("Update check already in progress.")
             return
        self.current_action = "update" # Set busy state for update
        thread = threading.Thread(target=self.check_for_updates, daemon=True)
        thread.start()

# Dentro la classe CrossOverApp

    def _update_progress_ui(self, value=None, text=None, indeterminate=False):
        """Helper to update the update progress bar and status label (thread-safe)."""
        def update():
            if not self.winfo_exists() or not hasattr(self, "update_progress_bar") or not self.update_progress_bar.winfo_exists():
                logging.debug("Update progress UI callback: Target widget destroyed. Aborting.")
                return

            progress_bar = self.update_progress_bar

            if value is not None:
                progress_bar.grid() # Show
                progress_bar.set(value)
                if indeterminate:
                    progress_bar.configure(mode="indeterminate")
                    progress_bar.start() # Rimosso check is_running
                else:
                    progress_bar.configure(mode="determinate")
                    progress_bar.stop() # Rimosso check is_running
            else:
                # Hide progress bar
                progress_bar.stop() # Rimosso check is_running
                progress_bar.grid_remove()

            if text is not None:
                # Check status_label exists before configuring
                if hasattr(self, "status_label") and self.status_label.winfo_exists():
                    self.update_status_bar(text, is_update_status=True)
                else:
                    logging.debug("Update progress UI callback: Status label destroyed.")

        # Schedule update only if main window exists
        if hasattr(self, 'after') and self.winfo_exists():
            self.after(0, update)
        else:
            logging.debug("Update progress UI: Main window destroyed before scheduling callback.")
    
    def check_for_updates(self):
        """
        Checks GitHub for updates. If found and newer, downloads the zip asset
        to the user's Downloads folder, extracts it, and prompts the user
        to launch the new version (quitting the current one).
        """
        logging.info("Checking for updates...")
        self._update_progress_ui(0, TXT.get("update_status_checking", "Checking for updates..."), indeterminate=True)
        update_zip_path = None
        extracted_app_path = None
        tmpdir_extraction = None # Sub-directory within Downloads

        try:
            # 1. Get latest release info from GitHub API
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            resp = requests.get(api_url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            latest_tag = data["tag_name"]
            logging.info(f"Latest release tag from GitHub: {latest_tag}")
            latest_version_str = latest_tag.lstrip('v')

            # 2. Compare versions
            try:
                gh_version = parse_version(latest_version_str)
                local_version = parse_version(__version__)
                logging.info(f"Comparing GitHub version {gh_version} with local version {local_version}")

                if gh_version <= local_version:
                    msg_key = "update_up_to_date_msg" if gh_version == local_version else "update_newer_local_msg"
                    title_key = "update_up_to_date_title" if gh_version == local_version else "update_newer_local_title"
                    log_msg = "Local version is up to date." if gh_version == local_version else f"Local version {local_version} is newer than release {gh_version}."
                    logging.info(log_msg)
                    messagebox.showinfo(
                        TXT.get(title_key, "Info"),
                        TXT.get(msg_key, "...").format(current_version=__version__, local_version=__version__, gh_version=latest_version_str)
                    )
                    return # Exit update check

            except Exception as e:
                 logging.error(f"Error comparing versions ('{latest_version_str}' vs '{__version__}'): {e}")
                 messagebox.showerror(TXT.get("update_error_title", "Update Error"), f"Error comparing versions:\n{e}")
                 return

            # 3. Ask user to proceed with download
            if not messagebox.askyesno(
                TXT.get("update_available_title", "Update Available"),
                TXT.get("update_ask_install", "Version {new_version} available. Download now?") # Adjusted text slightly
                   .format(new_version=latest_version_str)
            ):
                return # User cancelled download

            # 4. Find suitable ZIP asset
            assets = data.get("assets", [])
            expected_zip_name_pattern = f"{APP_NAME}-mac-{latest_tag}"
            zip_asset = next((a for a in assets if expected_zip_name_pattern in a["name"] and a["name"].endswith(".zip")), None) \
                        or next((a for a in assets if a["name"].endswith(".zip")), None)
            if not zip_asset: raise ValueError(TXT.get("update_no_zip", "No ZIP asset found."))
            zip_url = zip_asset["browser_download_url"]
            zip_size = zip_asset.get("size", 0)
            zip_filename = zip_asset["name"]
            logging.info(f"Found update asset: {zip_filename} ({zip_size} bytes)")

            # 5. Download to user's Downloads folder
            downloads_path = os.path.expanduser("~/Downloads")
            update_zip_path = os.path.join(downloads_path, zip_filename)
            logging.info(f"Downloading update to: {update_zip_path}")
            self._update_progress_ui(0, TXT.get("update_status_downloading", "Downloading ({percent:.0f}%)...").format(percent=0))
            downloaded_bytes = 0

            with requests.get(zip_url, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(update_zip_path, "wb") as f:
                    chunk_size = 8192 * 4
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded_bytes += len(chunk)
                            if zip_size > 0:
                                percent = (downloaded_bytes / zip_size) * 100
                                self._update_progress_ui(downloaded_bytes / zip_size,
                                                         TXT.get("update_status_downloading", "...").format(percent=percent))
                            else:
                                self._update_progress_ui(0, TXT.get("update_downloading", "..."), indeterminate=True)

            logging.info(f"Download complete: {update_zip_path}")
            self._update_progress_ui(1.0, TXT.get("done", "Done!")) # Show 100% briefly

            # 6. Ask user to extract and launch the new version
            if not messagebox.askyesno(
                TXT.get("update_download_complete_title", "Download Complete"),
                TXT.get("update_download_complete_ask_launch", "Update downloaded. Extract and launch new version?")
            ):
                logging.info("User chose not to launch the new version now.")
                return

            # 7. Extract zip to a subfolder in Downloads
            self._update_progress_ui(1.0, TXT.get("update_extracting_launching", "Extracting..."), indeterminate=True)
            extract_folder_name = f"{APP_NAME} Update {latest_version_str}"
            tmpdir_extraction = os.path.join(downloads_path, extract_folder_name)

            if os.path.exists(tmpdir_extraction):
                 logging.warning(f"Removing previous extraction directory: {tmpdir_extraction}")
                 shutil.rmtree(tmpdir_extraction)
            os.makedirs(tmpdir_extraction, exist_ok=True)

            logging.info(f"Extracting {update_zip_path} to {tmpdir_extraction}")
            with zipfile.ZipFile(update_zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdir_extraction)

            # Find the path to the extracted .app bundle
            extracted_app_name = f"{APP_NAME}.app"
            extracted_app_path = os.path.join(tmpdir_extraction, extracted_app_name)
            if not os.path.isdir(extracted_app_path): # Check if it's a directory
                found_apps = [d for d in os.listdir(tmpdir_extraction) if d.endswith(".app") and os.path.isdir(os.path.join(tmpdir_extraction, d))]
                if found_apps:
                    extracted_app_path = os.path.join(tmpdir_extraction, found_apps[0])
                    logging.warning(f"App name mismatch, launching found app: {found_apps[0]}")
                else:
                    raise FileNotFoundError(f"Could not find extracted '.app' bundle in {tmpdir_extraction}")

            logging.info(f"Extraction complete. Found app at: {extracted_app_path}")

            # 8. Launch the new app using 'open' command and quit the current one
            logging.info(f"Attempting to launch: {extracted_app_path}")
            try:
                subprocess.run(['open', extracted_app_path], check=True)
                logging.info("Successfully launched the new application via 'open'.")
                self.after(500, self.quit) # Quit current app after a short delay
            except Exception as launch_err:
                 logging.exception("Failed to launch the new application using 'open'.")
                 messagebox.showerror(
                     TXT.get("update_launch_error_title", "Launch Error"),
                     TXT.get("update_launch_error_msg", "Could not launch. Check Downloads.") + f"\n\nError: {launch_err}"
                 )

        # --- Error Handling ---
        except requests.exceptions.RequestException as e:
             logging.error(f"Network error during update check: {e}")
             messagebox.showerror(TXT.get("update_error_title", "Update Error"), f"Network error:\n{e}")
        except (zipfile.BadZipFile, ValueError, FileNotFoundError, OSError, PermissionError) as e:
             logging.error(f"Error during update file operation: {e}")
             messagebox.showerror(TXT.get("update_error_title", "Update Error"), f"File operation error:\n{e}")
        except Exception as e:
             logging.exception("Unexpected error during update check.")
             messagebox.showerror(TXT.get("update_error_title", "Update Error"), f"An unexpected error occurred:\n{e}")
        finally:
            # --- Cleanup & State Reset ---
            # No automatic cleanup of Downloads folder needed for this workflow.
            # Optionally remove the zip after successful extraction if desired.
            self.current_action = None # Reset update action state
            self._update_progress_ui(None)
            self.update_status_bar()


# --- Application Entry Point ---

if __name__ == "__main__":
    # --- Initialize Logging ---
    logging.basicConfig(
        level=logging.INFO, # Use INFO for production releases
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler()]
        # TODO: Add FileHandler for persistent logs if desired
    )
    logging.info(f"--- Starting {APP_NAME} v{__version__} ---")
    logging.info(f"Base path: {BASE_PATH}")
    logging.info(f"App Support Dir: {APP_SUPPORT_DIR}")
    logging.info(f"Config file: {CONFIG_FILE}")
    logging.info(f"Script path: {SCRIPT_PATH}")
    logging.info(f"Checksum file: {CHECKSUM_FILE}")

    # --- Load Settings & Apply Theme ---
    current_settings = load_settings()
    if current_settings.get("dark_mode") is True: ctk.set_appearance_mode("Dark")
    elif current_settings.get("dark_mode") is False: ctk.set_appearance_mode("Light")
    else: ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    # --- First Launch Check: Ask about Startup Update Check ---
    if current_settings.get("check_updates_on_startup") is None:
        logging.info("First launch detected. Asking about startup update check.")
        # Need a temporary root for messagebox before main app instance exists
        temp_root = ctk.CTk(); temp_root.withdraw()
        user_agrees = messagebox.askyesno(
            LANGUAGES[LANG].get("ask_enable_startup_update_title", "Automatic Update Check"),
            LANGUAGES[LANG].get("ask_enable_startup_update_msg", "Enable automatic update checks on startup?")
        )
        temp_root.destroy()
        current_settings["check_updates_on_startup"] = user_agrees
        save_settings(current_settings) # Save preference immediately
        logging.info(f"User chose to {'enable' if user_agrees else 'disable'} startup update check.")

    # --- Create Main App Instance (Hidden) ---
    app_instance = None
    initialization_ok = False
    try:
        app_instance = CrossOverApp() # Reads current_settings internally
        app_instance.withdraw()
        app_instance.update_idletasks()
        initialization_ok = True
        logging.info("CrossOverApp instance created and withdrawn.")
    except Exception as init_error:
        initialization_ok = False
        logging.exception("CRITICAL ERROR during CrossOverApp initialization!")
        import tkinter as tk; from tkinter import messagebox # Fallback import
        error_root = tk.Tk(); error_root.withdraw()
        messagebox.showerror("Fatal Error", f"Application failed to initialize:\n{init_error}")
        error_root.destroy(); sys.exit(1)

    if initialization_ok and app_instance:
        # --- Create and Display Splash Screen ---
        splash = Toplevel(app_instance)
        splash_width, splash_height = 450, 300
        screen_width = app_instance.winfo_screenwidth()
        screen_height = app_instance.winfo_screenheight()
        x_pos = (screen_width // 2) - (splash_width // 2)
        y_pos = (screen_height // 2) - (splash_height // 2)
        splash.geometry(f"{splash_width}x{splash_height}+{x_pos}+{y_pos}")
        splash.overrideredirect(True)
        splash.attributes("-topmost", True)

        current_mode_str = ctk.get_appearance_mode()
        frame_fg_color = COLOR_FRAME_DARK if current_mode_str == "Dark" else COLOR_FRAME_LIGHT
        splash_frame = ctk.CTkFrame(splash, corner_radius=15, border_width=1, fg_color=frame_fg_color)
        splash_frame.pack(expand=True, fill="both", padx=1, pady=1)

        # Splash Content
        try:
            logo_image = ctk.CTkImage(light_image=Image.open(LOGO_PATH), dark_image=Image.open(LOGO_PATH), size=(100, 100))
            ctk.CTkLabel(splash_frame, image=logo_image, text="").pack(pady=(40, 15))
        except Exception as e:
            logging.error(f"Failed to load logo {LOGO_PATH}: {e}")
            ctk.CTkLabel(splash_frame, text=APP_NAME, font=ctk.CTkFont(size=30, weight="bold")).pack(pady=(40, 15))
        ctk.CTkLabel(splash_frame, text=APP_NAME, font=ctk.CTkFont(size=20, weight="bold")).pack(pady=5)
        ctk.CTkLabel(splash_frame, text=f"Version {__version__}", font=ctk.CTkFont(size=12)).pack(pady=(0, 25))
        splash_progress = ctk.CTkProgressBar(splash_frame, mode='indeterminate', height=8, corner_radius=4)
        splash_progress.pack(fill="x", padx=40, pady=(0, 40)); splash_progress.start()
        splash.update()
        logging.info("Splash screen displayed.")

        # --- Perform Initial Local Checks (while splash is visible) ---
        logging.info("Performing initial local checks (script status, checksum, service)...")
        try:
            app_instance._check_script_status()
            app_instance.refresh_status()
            app_instance.update_status_bar()
            logging.info("Initial local checks completed.")
        except Exception as check_error:
            logging.exception("Error during initial checks!")
            if splash.winfo_exists(): splash.destroy()
            messagebox.showerror("Initialization Error", f"Failed during initial checks:\n{check_error}")
            # Consider exiting if checks are critical: sys.exit(1)

        # --- Define Transition Function ---
        def show_main_window():
            """Closes splash and reveals the main application window."""
            logging.info("Closing splash screen and showing main application window.")
            if splash.winfo_exists():
                 splash_progress.stop(); splash.destroy()
                 logging.debug("Splash screen destroyed.")
            else: logging.warning("Splash screen already destroyed when trying to close.")
            if app_instance.winfo_exists():
                 app_instance.deiconify(); app_instance.lift(); app_instance.focus_force()
                 logging.debug("Main application window shown.")
            else: logging.warning("Main application window destroyed before showing.")

        # --- Schedule Transition ---
        splash_min_duration_ms = 500 # Minimum splash display time
        app_instance.after(splash_min_duration_ms, show_main_window)
        logging.info(f"Scheduled main window display in {splash_min_duration_ms} ms.")

        # --- Start Main Event Loop ---
        logging.info("Starting main event loop (app.mainloop()).")
        app_instance.mainloop()

        # --- Application Exit ---
        logging.info(f"--- Exiting {APP_NAME} ---")