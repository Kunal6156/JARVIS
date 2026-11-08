"""Background coding-agent sessions (Claude Code, Codex, ...) with live logs you can read, tail and stop."""
import subprocess
import sys
import threading
import time
import uuid

from . import config, notify

DIR = config.DATA_DIR / "sessions"
DIR.mkdir(exist_ok=True)
SESS = {}


def start(cli, prompt, directory):
    import shutil
    spec = config.CODING_CLIS.get(cli)
    if not spec:
        raise ValueError(f"Unknown CLI {cli}.")
    exe = shutil.which(spec["interactive"][0])
    if not exe:
        raise FileNotFoundError(f"{cli} is not installed or not on PATH.")
    sid = uuid.uuid4().hex[:6]
    log = DIR / f"{sid}.log"
    prompt = prompt.replace('"', "'")
    cmd = [exe] + spec["headless"][1:] + [prompt]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    f = open(log, "wb")
    proc = subprocess.Popen(cmd, cwd=directory, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            creationflags=flags)
    SESS[sid] = {"id": sid, "cli": cli, "prompt": prompt[:200], "dir": str(directory), "log": str(log),
                 "started": time.strftime("%H:%M:%S"), "status": "running", "proc": proc}

    def watch():
        code = proc.wait()
        f.close()
        if SESS[sid]["status"] == "running":
            SESS[sid]["status"] = "done" if code == 0 else f"failed ({code})"
        notify.send(f"Coding session {sid} with {cli} is {SESS[sid]['status']}.")
    threading.Thread(target=watch, daemon=True, name=f"session-{sid}").start()
    return sid


def tail(sid, n=4000):
    s = SESS.get(sid)
    if not s:
        return None
    try:
        data = open(s["log"], "rb").read()[-n:]
    except OSError:
        return ""
    return data.decode("utf-8", "replace")


def stop(sid):
    s = SESS.get(sid)
    if not s or s["status"] != "running":
        return False
    s["status"] = "stopped"
    s["proc"].terminate()
    return True


def listing():
    return [{k: v for k, v in s.items() if k != "proc"} for s in SESS.values()]
