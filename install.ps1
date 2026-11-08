# One-click setup for Windows. Right-click > Run with PowerShell, or run:  powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$venv = if (Test-Path "venv") { "venv" } else { ".venv" }
if (-not (Test-Path $venv)) {
    Write-Host "Creating virtual environment..."
    try { py -3.11 -m venv $venv } catch { python -m venv $venv }
}
$py = Join-Path $PSScriptRoot "$venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt
& $py -m playwright install chromium
if ((Read-Host "Install the natural British voice, neural wake word and face ID? (y/n)") -eq "y") {
    & $py -m pip install edge-tts pygame openwakeword opencv-python
}
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
$desktop = [Environment]::GetFolderPath("Desktop")
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("$desktop\Jarvis.lnk")
$lnk.TargetPath = Join-Path $PSScriptRoot "$venv\Scripts\pythonw.exe"
$lnk.Arguments = "main.py --hud"
$lnk.WorkingDirectory = $PSScriptRoot
$lnk.Save()
Write-Host "`nDone. A Jarvis shortcut is on your Desktop. Opening .env so you can set your model..."
Start-Process notepad ".env"
& $py main.py --check
