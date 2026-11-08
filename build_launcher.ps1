# Builds a double-clickable Jarvis.exe launcher (the app itself stays in this folder).
Set-Location $PSScriptRoot
$venv = if (Test-Path "venv") { "venv" } else { ".venv" }
$py = Join-Path $PSScriptRoot "$venv\Scripts\python.exe"
& $py -m pip install pyinstaller
& $py -m PyInstaller --onefile --noconsole --name Jarvis launcher.py
Copy-Item "dist\Jarvis.exe" "Jarvis.exe" -Force
Write-Host "Jarvis.exe created in this folder. Keep it next to main.py. Right-click > Send to > Desktop (shortcut)."
