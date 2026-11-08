"""Drive coding CLIs (Claude Code, Codex, Gemini CLI, OpenCode) by voice."""
import shutil
import subprocess
import sys

from .. import config, sessions
from ..registry import tool
from .files import resolve


@tool("List which coding agent CLIs are installed.", {})
def list_coding_agents():
    return "\n".join(f"{n}: {'installed' if shutil.which(c['interactive'][0]) else 'not found'}"
                     for n, c in config.CODING_CLIS.items())


@tool("Run a coding agent CLI on a task. mode 'window' opens it in a new terminal you can watch; "
      "'headless' runs it silently and returns the output.",
      {"cli": ("string", "claude, codex, gemini or opencode", list(config.CODING_CLIS)),
       "prompt": ("string", "The task for the coding agent"),
       "directory": ("string", "Project folder"), "mode": ("string", "window, headless or background (runs on its own with a live log; Jarvis announces when done)", ["window", "headless", "background"])},
      required=["cli", "prompt"], risk="ask")
def run_coding_agent(cli, prompt, directory="", mode="window"):
    spec = config.CODING_CLIS.get(cli)
    if not spec:
        return f"Unknown CLI {cli}."
    exe = shutil.which(spec["interactive"][0])
    if not exe:
        return f"{cli} is not installed or not on PATH."
    wd = str(resolve(directory)) if directory else str(config.SETTINGS.workspace)
    prompt = prompt.replace('"', "'")
    if mode == "background":
        sid = sessions.start(cli, prompt, wd)
        return f"Started coding session {sid} with {cli} in {wd}. I'll tell you when it finishes."
    key = "headless" if mode == "headless" else "interactive"
    cmd = [exe] + spec[key][1:] + [prompt]
    if mode == "headless":
        try:
            r = subprocess.run(cmd, cwd=wd, capture_output=True, text=True, timeout=900,
                               encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return "Timed out after 15 minutes."
        return f"exit code {r.returncode}\n{(r.stdout or r.stderr)[-4000:]}"
    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/k"] + cmd, cwd=wd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    elif sys.platform == "darwin":
        import shlex
        script = f"cd {shlex.quote(wd)} && {shlex.join(cmd)}".replace("\\", "\\\\").replace('"', '\\"')
        subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{script}"'])
    else:
        subprocess.Popen(["x-terminal-emulator", "-e"] + cmd, cwd=wd)
    return f"Started {cli} in a new terminal window in {wd}."


@tool("List background coding sessions and their status.", {})
def list_coding_sessions():
    rows = [f"{x['id']}: {x['cli']} {x['status']} - {x['prompt'][:60]}" for x in sessions.listing()]
    return "\n".join(rows) or "No coding sessions."


@tool("Show the latest output of a background coding session.", {"id": ("string", "Session id")})
def coding_session_output(id):
    out = sessions.tail(id)
    return out if out is not None else "No such session."


@tool("Stop a running background coding session.", {"id": ("string", "Session id")}, risk="ask")
def stop_coding_session(id):
    return "Stopped." if sessions.stop(id) else "Not running."
