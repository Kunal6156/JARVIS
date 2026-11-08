"""Persistent background agents: named workers with their own role, tool allowlist, saved history and run log.
Ask one to do a job; it works on its own thread and tells you when it's done."""
import json
import re
import threading
import time

from . import config, notify
from .approvals import APPROVALS

DIR = config.DATA_DIR / "agents"
DIR.mkdir(exist_ok=True)
RUNNING = {}
DEFAULT_TOOLS = ["web_search", "fetch_url", "browser_open", "browser_search", "browser_read", "browser_links",
                 "browser_click", "browser_type", "browser_press", "browser_scroll", "browser_back",
                 "list_directory", "read_file", "search_files", "search_in_files", "get_time", "system_status",
                 "remember", "recall", "write_file", "run_command", "run_coding_agent", "add_reminder"]


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", name.lower().strip()).strip("-")[:40] or "agent"


def _path(name):
    return DIR / f"{slug(name)}.json"


def _save(spec):
    _path(spec["name"]).write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")


def create(name, role, tools=None):
    if _path(name).exists():
        raise ValueError(f"An agent called {slug(name)} already exists.")
    spec = {"name": slug(name), "role": role.strip(), "tools": tools or DEFAULT_TOOLS,
            "created": time.strftime("%Y-%m-%d %H:%M"), "runs": []}
    _save(spec)
    return spec


def get(name):
    p = _path(name)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, ValueError):
        return None


def listing():
    out = []
    for p in sorted(DIR.glob("*.json")):
        if p.name.endswith(".history.json"):
            continue
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def delete(name):
    existed = _path(name).exists()
    _path(name).unlink(missing_ok=True)
    (DIR / f"{slug(name)}.history.json").unlink(missing_ok=True)
    return existed


class BackgroundIO:
    """No microphone here. Approvals go to the dashboard; without it they are denied."""

    def __init__(self, who):
        self.who, self.parts = who, []

    def say(self, text): self.parts.append(text)
    def show(self, text): pass
    def confirm(self, q): return APPROVALS.request(self.who, q)
    def listen(self): return None
    def after_response(self): pass
    def sleep(self): pass
    def result(self): return " ".join(self.parts).strip()


def run(name, task, wait=False):
    spec = get(name)
    if not spec:
        raise ValueError(f"No agent called {name}.")
    key = spec["name"]
    if key in RUNNING:
        raise RuntimeError(f"Agent {key} is already working on something.")

    def work():
        from . import llm
        from .agent import Agent
        io, status = BackgroundIO(key), "done"
        RUNNING[key] = {"task": task[:200], "started": time.strftime("%H:%M:%S")}
        try:
            Agent(io, llm.get(), name=key, role=spec["role"], allowed=spec["tools"], background=True,
                  persist=DIR / f"{key}.history.json").handle(task)
        except Exception as e:
            io.parts.append(f"Failed: {e}")
            status = "failed"
        finally:
            RUNNING.pop(key, None)
        result = io.result() or "(no output)"
        fresh = get(key) or spec
        fresh["runs"] = (fresh.get("runs", []) + [{"task": task[:200], "finished": time.strftime("%Y-%m-%d %H:%M"),
                                                   "status": status, "result": result[:3000]}])[-20:]
        _save(fresh)
        notify.send(f"Agent {key} {'finished' if status == 'done' else 'failed'}. {result[:240]}")
        return result

    if wait:
        return work()
    threading.Thread(target=work, daemon=True, name=f"agent-{key}").start()
    return "started"
