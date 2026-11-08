"""Tiny launcher: build it into Jarvis.exe with build_launcher.ps1. It starts Jarvis from the folder it sits in."""
import ctypes
import os
import subprocess
import sys

base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
for v in ("venv", ".venv"):
    py = os.path.join(base, v, "Scripts", "pythonw.exe")
    if os.path.exists(py):
        subprocess.Popen([py, "main.py", "--hud"], cwd=base)
        break
else:
    ctypes.windll.user32.MessageBoxW(0, "Run install.ps1 first (no virtual environment found next to Jarvis.exe).",
                                     "Jarvis", 0x10)
