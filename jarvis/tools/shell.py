"""Run shell commands. Always needs approval; dangerous patterns are blocked outright (see safety.py)."""
import os
import subprocess

from .. import config
from ..registry import tool
from .files import resolve


@tool("Run a shell command (PowerShell on Windows, bash elsewhere) and return its output.",
      {"command": ("string", "The command"), "cwd": ("string", "Working directory"),
       "timeout": ("integer", "Seconds, default 60")}, required=["command"], risk="ask")
def run_command(command, cwd="", timeout=60):
    wd = str(resolve(cwd)) if cwd else str(config.SETTINGS.workspace)
    args = (["powershell", "-NoProfile", "-NonInteractive", "-Command", command] if os.name == "nt"
            else ["bash", "-lc", command])
    try:
        r = subprocess.run(args, cwd=wd, capture_output=True, text=True, timeout=int(timeout),
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s."
    out = (r.stdout or "").strip()
    if (r.stderr or "").strip():
        out += "\n[stderr]\n" + r.stderr.strip()
    return f"exit code {r.returncode}\n{out[:5000]}"
