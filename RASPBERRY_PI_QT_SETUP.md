# Raspberry Pi / Debian Bookworm Qt Setup

This project now supports both `PyQt6` and `PySide6` through a compatibility layer.
On Raspberry Pi OS / Debian 12 Bookworm, the safest path for embedded map rendering
is to use distro Qt packages (`PyQt6` + QtWebEngine).

## Why this is needed
Some `PySide6` wheels on arm64 require `libwebp.so.6`, while Bookworm ships
`libwebp.so.7`. This breaks embedded `QtWebEngine` loading.

## Safe setup steps (Bookworm)
1. Install distro Qt packages:

```bash
sudo apt update
sudo apt install python3-pyqt6 python3-pyqt6.qtwebengine qt6-webengine-dev-tools
```

2. Create a venv that can use system Python packages:

```bash
cd /home/karl/Nextcloud/Programmierung/Python/gpx_analyzer
python3 -m venv --system-site-packages .venv-qt
source .venv-qt/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

3. Verify Qt WebEngine import:

```bash
python -c "from PyQt6.QtWebEngineWidgets import QWebEngineView; print('QtWebEngine OK')"
```

4. Run the app:

```bash
python gpx_organizer_main.py
```

## Notes
- Do not symlink `libwebp.so.6` to `libwebp.so.7`.
- Do not downgrade core system multimedia libraries.
- If embedded map is unavailable, app will still open previews in your default browser.
