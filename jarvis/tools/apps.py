"""Open, close and list applications."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..registry import tool

ALIASES = {
    "notepad": "notepad.exe", "calculator": "calc.exe", "calc": "calc.exe", "paint": "mspaint.exe",
    "explorer": "explorer.exe", "file explorer": "explorer.exe", "files": "explorer.exe",
    "command prompt": "cmd.exe", "cmd": "cmd.exe", "powershell": "powershell.exe",
    "terminal": "wt.exe", "windows terminal": "wt.exe", "task manager": "taskmgr.exe",
    "settings": "ms-settings:", "chrome": "chrome", "google chrome": "chrome", "edge": "msedge",
    "firefox": "firefox", "vscode": "code", "vs code": "code", "visual studio code": "code",
    "word": "winword", "excel": "excel", "powerpoint": "powerpnt", "snipping tool": "snippingtool",
}


def _launch_target(target):
    try:
        os.startfile(target)  # Windows only; resolves App Paths and URI schemes
        return True
    except (OSError, AttributeError):
        pass
    exe = shutil.which(target)
    if exe:
        subprocess.Popen(f'"{exe}"', shell=True)
        return True
    return False


def _find_shortcut(name):
    roots = [os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
             os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")]
    name, best = name.lower(), None
    for r in roots:
        if not os.path.isdir(r):
            continue
        for p in Path(r).rglob("*.lnk"):
            stem = p.stem.lower()
            if stem == name:
                return p
            if name in stem and (best is None or len(stem) < len(best.stem)):
                best = p
    return best


def _launch_start_app(name):
    """Covers Microsoft Store apps (Spotify, WhatsApp, Calculator...) via Get-StartApps."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json"],
                             capture_output=True, text=True, timeout=25).stdout
        apps = json.loads(out)
    except Exception:
        return False
    if isinstance(apps, dict):
        apps = [apps]
    name = name.lower()
    matches = sorted((a for a in apps if name in a["Name"].lower()), key=lambda a: len(a["Name"]))
    if not matches:
        return False
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{matches[0]['AppID']}"])
    return True


@tool("Open an application by name (e.g. 'chrome', 'notepad', 'spotify', 'vs code').",
      {"name": ("string", "Application name")})
def open_app(name):
    key = name.strip().lower()
    if sys.platform == "win32":
        if key in ALIASES and _launch_target(ALIASES[key]):
            return f"Opened {name}."
        lnk = _find_shortcut(key)
        if lnk:
            os.startfile(str(lnk))
            return f"Opened {lnk.stem}."
        if _launch_start_app(key):
            return f"Opened {name}."
        if _launch_target(key):
            return f"Opened {name}."
    elif sys.platform == "darwin":
        if subprocess.run(["open", "-a", name]).returncode == 0:
            return f"Opened {name}."
    else:
        exe = shutil.which(key.replace(" ", "-")) or shutil.which(key)
        if exe:
            subprocess.Popen([exe])
            return f"Opened {name}."
    return f"Couldn't find an app called {name}."


@tool("Force-close an application by process or app name (e.g. 'chrome', 'notepad').",
      {"name": ("string", "Process or application name")}, risk="ask")
def close_app(name):
    import psutil
    key = name.strip().lower().replace(" ", "")
    alias = ALIASES.get(name.strip().lower(), "").lower().replace(".exe", "")
    killed = set()
    for p in psutil.process_iter(["name"]):
        pn = (p.info["name"] or "").lower().replace(".exe", "").replace(" ", "")
        if pn and (key in pn or (alias and alias in pn)) and p.pid != os.getpid():
            try:
                p.terminate()
                killed.add(pn)
            except psutil.Error:
                pass
    return f"Closed: {', '.join(sorted(killed))}" if killed else f"No running app matched {name}."


@tool("List the applications using the most memory right now.", {})
def list_running_apps():
    import psutil
    seen = {}
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            seen[p.info["name"]] = seen.get(p.info["name"], 0) + p.info["memory_info"].rss
        except (psutil.Error, AttributeError, TypeError):
            continue
    top = sorted(seen.items(), key=lambda x: -x[1])[:20]
    return "\n".join(f"{n} ({m // 2**20} MB)" for n, m in top)
