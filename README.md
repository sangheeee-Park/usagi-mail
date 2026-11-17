# usagi-mail

Desktop widget that lists recent Naver / Gmail subjects; click to open in browser.

## Setup
1. Naver: Mail settings -> POP3/IMAP -> enable IMAP. Enable 2-step verification and create an app password.
2. Google: enable 2-step verification, create an app password at https://myaccount.google.com/apppasswords
3. `copy config.example.json config.json` and fill in your addresses.
4. `python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`
5. `.venv\Scripts\python setup_cred.py` and enter the app passwords (stored in Credential Manager).

Passwords are stored in Windows Credential Manager (keyring), never in files.

## Run / Build
- Dev: `.venv\Scripts\python main.py`
- Build: `.venv\Scripts\pip install pyinstaller` then `powershell -ExecutionPolicy Bypass -File build.ps1`
  -> `dist\usagi-mail\usagi-mail.exe` (dist config.json is copied once and keeps window positions)
- Autostart: put a `.vbs` in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup` that sleeps 15s then runs the exe.
