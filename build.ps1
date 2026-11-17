Set-Location $PSScriptRoot

# stop running widget
Get-Process "usagi-mail" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1

.venv\Scripts\pyinstaller -y --noconsole --onedir --noupx --name usagi-mail `
  --hidden-import win32gui --hidden-import win32con `
  --hidden-import keyring.backends.Windows `
  --exclude-module PySide6 main.py

# copy config only once: dist config keeps saved window positions
if (-not (Test-Path dist\usagi-mail\config.json)) {
  Copy-Item config.json dist\usagi-mail\config.json
}

# character images (local only, gitignored)
if (Test-Path assets\private) {
  New-Item -ItemType Directory -Force dist\usagi-mail\assets | Out-Null
  Copy-Item assets\private dist\usagi-mail\assets\ -Recurse -Force
}

Write-Host "build done: dist\usagi-mail\usagi-mail.exe"
