# Maria Free Download (licensed edition)

Download manager for Windows. Each copy is activated with a **serial number that works on one computer only**.

## Licensing (vendor guide)
1. **Once:** `pip install cryptography` then `python tools/keygen.py init`.
   This creates your PRIVATE key in `~/MariaKeys/private_key.pem` (back it up, never commit it) and writes the
   PUBLIC key into `app/license_key.py`. Commit that file.
2. Build the installer (GitHub Actions -> *Build Windows Installer*). The build stops if the public key is missing.
3. Install on the customer's computer. The program shows a **Device ID** (`XXXX-XXXX-XXXX-XXXX`).
4. Run `python tools/keygen.py` (small window) or
   `python tools/keygen.py make --device XXXX-XXXX-XXXX-XXXX --name "Customer" [--expires 2027-12-31]`
   and give the serial to the customer. Every serial is logged in `~/MariaKeys/issued_serials.csv`.
5. The customer pastes the serial and clicks **Activate**. The serial is accepted only on that computer.

The installer shows `installer/EULA_Terms_of_Use.rtf` and requires acceptance before installing. Edit that file
to change the terms.

## Features
- Multi-connection downloads (1–32 connections per file) with dynamic splitting
- Pause / resume, even after closing the app or losing the connection
- Speed limiter and a download queue (max simultaneous downloads)
- Scheduler: start and stop downloads at set times on chosen days
- Browser capture for Chrome / Edge (extension in `extension/`)
- Tray icon, completion notifications, optional start with Windows
- Arabic / English interface
- "Open / Play" button for finished files and a built-in player for video, audio and images

## Build the installer (GitHub Actions)
1. Upload this folder to a new GitHub repository.
2. Open **Actions → Build Windows Installer → Run workflow**.
3. Download `JDM-Setup` from the finished run.
   Pushing a tag like `v1.0.0` also publishes it under **Releases**.

## Build locally (Windows)
```
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --windowed --name JDM --icon assets/jdm.ico --add-data "assets;assets" --paths app app/main.py
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\jdm.iss
```

## Install the browser extension
1. Open `chrome://extensions` (or `edge://extensions`).
2. Turn on **Developer mode**.
3. Click **Load unpacked** and choose `C:\Program Files\JDM\extension`.

When JDM is closed, the browser downloads files normally.

## Project layout
```
app/main.py      UI (PySide6), scheduler, tray
app/engine.py    download engine
app/bridge.py    local bridge for the extension (127.0.0.1:9614)
extension/       Chrome / Edge extension (Manifest V3)
installer/       Inno Setup script
tests/           engine tests
```

---
© 2026 All rights reserved to the programmer Ali Abdulwahab Al-Saffar – Mosul, Iraq.
Email: alsfarly2@gmail.com · Support free service software – MasterCard: 2144558406
