# CrossOver Trial Manager

A GUI tool to reset and manage the trial period for CrossOver on macOS.

## Features

- **Manual Reset**: Run a trial reset on demand.  
- **Auto-Reset Service**: Install or uninstall a LaunchAgent for periodic resets.  
- **Multi-Language**: English and Italian UI and log output.  
- **Dark/Light Mode**: Toggle between modern dark and soft light themes.  
- **Interactive Logs**: Syntax-highlighted, color-coded STEP/INFO/SUCCESS/WARNING/ERROR messages.  
- **Log Controls**: Clear logs, filter by keyword, and export to a file.  
- **Checksum Verification**: Ensures `crack.sh` integrity at startup.  

## Checksum Mismatch

On first run, a `.sha256` file is generated for `crack.sh`.  
If you modify or replace `crack.sh`, the checksum will no longer match.  
To reset verification, delete `crack.sh.sha256` and restart the app—this will regenerate the checksum.

## Installation

1. Clone this repository.  
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   python main.py
   ```

## Requirements

See `requirements.txt` for the full list of Python packages.