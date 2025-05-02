#!/bin/bash
# crack.sh – CrossOver trial reset
# Log file: ~/cross_over_reset.log

LOGFILE="$HOME/cross_over_reset.log"

# language code passed from GUI; default to Italian
LANG_CODE="${2:-it}"
# define translations
if [ "$LANG_CODE" = "en" ]; then
  T_STEP_UPDATING="Updating trial dates"
  T_INFO_SETTING="Setting FirstRunDate and SULastCheckTime to"
  T_SUCCESS_DATES="Dates updated"
  T_STEP_SEARCH="Searching bottles in"
  T_WARN_NOBOTTLES="No bottles found, please enter alternative path"
  T_ERROR_NOBOTTLES="Failed: no bottles found"
  T_INFO_RESET="Resetting bottle:"
  T_SUCCESS_RESET="Reset completed for bottle"
  T_STEP_INSTALL="Executing initial reset"
  T_STEP_INST="Installing auto-reset service"
  T_SUCCESS_SERVICE="Service installed"
  T_STEP_UNINST="Removing auto-reset service"
  T_SUCCESS_UNINST="Service removed"
else
  T_STEP_UPDATING="Aggiorno date trial"
  T_INFO_SETTING="Imposto FirstRunDate e SULastCheckTime a"
  T_SUCCESS_DATES="Date aggiornate"
  T_STEP_SEARCH="Ricerca bottles in"
  T_WARN_NOBOTTLES="Nessun bottle trovato, chiedo path alternativo"
  T_ERROR_NOBOTTLES="Fallito: nessun bottle"
  T_INFO_RESET="Reset bottle:"
  T_SUCCESS_RESET="Reset completato per bottle"
  T_STEP_INSTALL="Eseguo reset iniziale"
  T_STEP_INST="Installo servizio auto-reset"
  T_SUCCESS_SERVICE="Servizio installato"
  T_STEP_UNINST="Rimuovo servizio auto-reset"
  T_SUCCESS_UNINST="Servizio rimosso"
fi

exec > >(tee -a "$LOGFILE") 2>&1

step() {
  echo "[STEP] $1..."
}
info() {
  echo "[INFO] $1"
}
success() {
  echo "[SUCCESS] $1"
}
warn() {
  echo "[WARNING] $1"
}
error() {
  echo "[ERROR] $1"
}

# Default bottles path
BOTTLES_PATH="$HOME/Library/Application Support/CrossOver/Bottles"
TOTAL_STEPS=3
STEP=0

executeReset() {
  step "$T_STEP_UPDATING"
  now="$(date '+%Y-%m-%d %H:%M:%S')"
  info "$T_INFO_SETTING $now"
  defaults write com.codeweavers.CrossOver FirstRunDate -date "$now"
  defaults write com.codeweavers.CrossOver SULastCheckTime -date "$now"
  success "$T_SUCCESS_DATES"

  step "$T_STEP_SEARCH $BOTTLES_PATH"
  # collect all system.reg paths, handling spaces
  bottles=()
  while IFS= read -r -d '' regfile; do
    bottles+=("$regfile")
  done < <(find "$BOTTLES_PATH" -name system.reg -print0)
  if [ ${#bottles[@]} -eq 0 ]; then
    warn "$T_WARN_NOBOTTLES"
    read -rp "> " path
    bottles=()
    while IFS= read -r -d '' regfile; do
      bottles+=("$regfile")
    done < <(find "$path" -name system.reg -print0)
    if [ ${#bottles[@]} -eq 0 ]; then
      error "$T_ERROR_NOBOTTLES"
      exit 1
    fi
  fi

  for regfile in "${bottles[@]}"; do
    bdir=$(dirname "$regfile")
    info "$T_INFO_RESET $(basename "$bdir")"
    rm -f "$bdir"/.version "$bdir"/.update-timestamp
    awk 'BEGIN{flag=0}/\[Software\\\\CodeWeavers\\\\CrossOver\\\\cxoffice\]/{flag=1}flag&&/^$/{flag=0;next}!flag' "$regfile" > tmp && mv tmp "$regfile"
    success "$T_SUCCESS_RESET $(basename "$bdir")"
  done
}

installService() {
  TOTAL_STEPS=4
  step "$T_STEP_INSTALL"
  executeReset

  step "$T_STEP_INST"
  mkdir -p "$HOME/Library/LaunchAgents"
  plist="$HOME/Library/LaunchAgents/com.codeweavers.CrossOver.license.plist"
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.codeweavers.CrossOver.license</string>
  <key>ProgramArguments</key>
  <array>
    <string>$SCRIPT_PATH</string>
    <string>execute</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>864000</integer>
</dict>
</plist>
EOF
  # try to load the LaunchAgent
  if launchctl load "$plist" 2>/dev/null; then
    success "$T_SUCCESS_SERVICE"
  else
    warn "Standard load failed, trying bootstrap..."
    # attempt bootstrap for the current GUI session
    if sudo launchctl bootstrap gui/"$(id -u)" "$plist" 2>/dev/null; then
      success "$T_SUCCESS_SERVICE (bootstrap)"
    else
      error "Unable to install service via load or bootstrap"
      exit 1
    fi
  fi
}

uninstallService() {
  TOTAL_STEPS=2
  step "$T_STEP_UNINST"
  plist="$HOME/Library/LaunchAgents/com.codeweavers.CrossOver.license.plist"
  launchctl unload "$plist" 2>/dev/null && rm "$plist"
  success "$T_SUCCESS_UNINST"
}

case "$1" in
  execute) executeReset ;;
  install) installService ;;
  uninstall) uninstallService ;;
  *) echo "Usage: $0 {execute|install|uninstall}" ;;
esac
