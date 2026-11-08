"""Local web dashboard (standard library only): chat, approvals, background agents, coding sessions,
schedule, memory, activity. Bound to 127.0.0.1 and protected by a random token printed at startup,
plus a Host-header check against DNS-rebinding, so other websites can't drive it."""
import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import agents, config, notify, scheduler as sch, sessions, status
from .approvals import APPROVALS
from .memory import MEMORY
from .registry import active

S = config.SETTINGS
TOKEN = secrets.token_urlsafe(18)
CTX = {"webio": None, "agent": None}


class WebIO:
    """I/O for chat typed into the dashboard. Approvals appear as buttons on the page."""

    def __init__(self):
        self.chat = []

    def _add(self, who, text):
        if who in ("You", "Jarvis"):
            status.log(who, text)
        self.chat.append({"who": who, "text": text, "ts": time.strftime("%H:%M")})
        del self.chat[:-200]

    def say(self, t): self._add("Jarvis", t)
    def show(self, t): self._add("·", t)
    def confirm(self, q):
        self._add("Jarvis", q)
        return APPROVALS.request("chat", q, timeout=120)
    def listen(self): return None
    def after_response(self): pass
    def sleep(self): pass


def _audit(n=100):
    try:
        lines = (config.DATA_DIR / "audit.jsonl").read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out[::-1]


def state():
    from . import llm
    try:
        model = getattr(llm.get(), "model", "")
    except RuntimeError:
        model = ""
    return {"provider": S.provider, "model": model, "mode": S.listen_mode, "tools": len(active()),
            "agents": agents.listing(), "running": agents.RUNNING, "sessions": sessions.listing(),
            "schedule": sch.SCHEDULER.jobs if sch.SCHEDULER else [], "memory": MEMORY.facts[-100:],
            "chat": CTX["webio"].chat[-80:] if CTX["webio"] else [], "approvals": APPROVALS.pending(),
            "feed": notify.recent()[::-1], "busy": CTX.get("busy", False)}


def _chat(b):
    text = (b.get("text") or "").strip()
    if not text:
        return {"ok": False}
    CTX["webio"]._add("You", text)

    def work():
        CTX["busy"] = True
        try:
            CTX["agent"].handle(text)
        finally:
            CTX["busy"] = False
    threading.Thread(target=work, daemon=True).start()
    return {"ok": True}


def _wrap(fn):
    def call(b):
        try:
            r = fn(b)
            return r if isinstance(r, dict) else {"ok": True, "result": r}
        except Exception as e:
            return {"ok": False, "error": str(e)[:300]}
    return call


def _agent_create(b):
    tools = [t.strip() for t in (b.get("tools") or "").split(",") if t.strip()] or None
    return agents.create(b["name"], b.get("role", ""), tools) and {"ok": True}


def _session_start(b):
    from .tools.files import resolve
    return {"ok": True, "id": sessions.start(b["cli"], b["prompt"], str(resolve(b.get("directory", ""))))}


ROUTES = {
    "chat": _chat,
    "approve": _wrap(lambda b: {"ok": APPROVALS.answer(b["id"], b["answer"])}),
    "agent_create": _wrap(_agent_create),
    "agent_run": _wrap(lambda b: agents.run(b["name"], b["task"])),
    "agent_delete": _wrap(lambda b: agents.delete(b["name"])),
    "session_start": _wrap(_session_start),
    "session_stop": _wrap(lambda b: sessions.stop(b["id"])),
    "job_remove": _wrap(lambda b: sch.SCHEDULER.remove(b["id"])),
    "memory_add": _wrap(lambda b: MEMORY.add(b["text"])),
    "memory_forget": _wrap(lambda b: MEMORY.forget(b["text"])),
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _guard(self):
        if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
            self._send(403, {"error": "bad host"})
            return False
        return True

    def _authed(self):
        if not secrets.compare_digest(self.headers.get("X-Token", ""), TOKEN):
            self._send(401, {"error": "bad token"})
            return False
        return True

    def do_GET(self):
        if not self._guard():
            return
        u = urlparse(self.path)
        if u.path in ("/", "/hud"):
            if parse_qs(u.query).get("t", [""])[0] != TOKEN:
                return self._send(403, b"Open the link printed in the Jarvis terminal.", "text/plain")
            page = "hud.html" if u.path == "/hud" else "dashboard.html"
            return self._send(200, (Path(__file__).parent / "web" / page).read_bytes(), "text/html")
        if not self._authed():
            return
        q = parse_qs(u.query)
        if u.path == "/api/state":
            return self._send(200, state())
        if u.path == "/api/hud":
            return self._send(200, {"state": status.STATE["v"], "log": list(status.TRANSCRIPT)[-12:],
                                    "tool": (_audit(1) or [{}])[0].get("tool", "")})
        if u.path == "/api/audit":
            return self._send(200, _audit())
        if u.path == "/api/tail":
            t = sessions.tail(q.get("id", [""])[0])
            return self._send(200, {"text": t if t is not None else "No such session."})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not (self._guard() and self._authed()):
            return
        route = ROUTES.get(urlparse(self.path).path.removeprefix("/api/"))
        if not route:
            return self._send(404, {"error": "not found"})
        try:
            n = min(int(self.headers.get("Content-Length", "0")), 100_000)
            body = json.loads(self.rfile.read(n) or "{}")
        except ValueError:
            return self._send(400, {"error": "bad json"})
        try:
            self._send(200, route(body))
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)[:300]})


def make_server(port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True, name="dashboard").start()
    return srv


def start(brain, open_browser=True, page=""):
    from .agent import Agent
    CTX["webio"] = WebIO()
    CTX["agent"] = Agent(CTX["webio"], brain)
    APPROVALS.enabled = True
    srv = make_server(S.dashboard_port)
    url = f"http://127.0.0.1:{srv.server_address[1]}/{page}?t={TOKEN}"
    print(f"Dashboard: {url}")
    if open_browser:
        webbrowser.open(url)
    return url
