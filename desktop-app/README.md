# Gmail Email Cleanmail - Desktop App

Native Windows desktop application built with PySide6 (Qt).

## Features

- Native Windows UI (no browser needed)
- Same functionality as web version
- Dark mode support
- Export to CSV
- All data stays local

## Setup

### 1. Install Dependencies

```bash
cd desktop-app
pip install -r requirements.txt
```

### 2. Add Google Credentials

Place your `credentials.json` file in the `config/` folder.

See the main project README for Google Cloud setup instructions.

### 3. Run the App

```bash
python run.py
```

## Building Executable

To create a standalone `.exe` file:

```bash
pip install pyinstaller
pyinstaller build.spec
```

The executable will be in `dist/GmailEmailCleanmail.exe`

## Project Structure

```
desktop-app/
├── config/
│   └── credentials.json    ← Your OAuth credentials
├── data/
│   └── tokens/             ← OAuth tokens (auto-created)
├── src/
│   ├── gmail_client.py     # Gmail API wrapper
│   ├── aggregator.py       # Email analysis logic
│   └── main.py             # PySide6 GUI application
├── requirements.txt
├── run.py                  ← Entry point
├── build.spec              ← PyInstaller config
└── README.md
```

## Privacy

Same privacy guarantees as the web version:
- All data processed locally
- No external servers
- No analytics or telemetry
- Open source
