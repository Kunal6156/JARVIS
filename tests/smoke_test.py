"""Offline smoke test: runs the agent loop with a fake LLM, no microphone, no network, no API key.
Run:  python tests/smoke_test.py"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["JARVIS_HOME"] = tempfile.mkdtemp()

from jarvis import safety, tools  # noqa: E402
from jarvis.agent import Agent  # noqa: E402
from jarvis.llm import Reply, ToolCall  # noqa: E402
from jarvis.registry import REGISTRY, anthropic_tools, openai_tools  # noqa: E402

tools.load_all()
assert len(REGISTRY) > 40, len(REGISTRY)
assert len(anthropic_tools()) == len(openai_tools())


class FakeIO:
    def __init__(self, answer="yes"):
        self.said, self.answer, self.asked = [], answer, []

    def say(self, t): self.said.append(t)
    def show(self, t): pass
    def confirm(self, q): self.asked.append(q); return self.answer


class ScriptedLLM:
    def __init__(self, script): self.script = list(script)
    def chat(self, system, history, on_text=None, tool_names=None): return self.script.pop(0)


def run(script, answer="yes", **kw):
    io = FakeIO(answer)
    a = Agent(io, ScriptedLLM(script), **kw)
    a.handle("test")
    return io, a


# 1. safe tool runs without asking
io, a = run([Reply("", [ToolCall("1", "get_time", {})]), Reply("It is time.")])
assert not io.asked and io.said == ["It is time."]

# 2. risky tool asks; approval runs it
tmp = Path(tempfile.mkdtemp()) / "hello.txt"
io, a = run([Reply("", [ToolCall("1", "write_file", {"path": str(tmp), "content": "hi"})]), Reply("Written.")])
assert io.asked and tmp.read_text() == "hi"

# 3. denial blocks it
tmp2 = Path(tempfile.mkdtemp()) / "no.txt"
io, a = run([Reply("", [ToolCall("1", "write_file", {"path": str(tmp2), "content": "x"})]), Reply("Okay.")], answer="no")
assert not tmp2.exists()

# 4. dangerous shell commands are denied without even asking
io, a = run([Reply("", [ToolCall("1", "run_command", {"command": "rm -rf /"})]), Reply("Can't.")])
assert not io.asked and "Blocked" in a.history[2]["content"]

# 5. normal shell command always asks
io, a = run([Reply("", [ToolCall("1", "run_command", {"command": "echo hello"})]), Reply("Done.")])
assert io.asked

# 6. protected paths refused
io, a = run([Reply("", [ToolCall("1", "write_file", {"path": (r"C:\Windows\jarvis_test.txt" if os.name == "nt" else "/etc/jarvis_test.txt"), "content": "x"})]), Reply("No.")])
assert "protected" in a.history[2]["content"].lower() or "Error" in a.history[2]["content"]

# 7. unattended routines never get to run approval-required tools
io, a = run([Reply("", [ToolCall("1", "write_file", {"path": str(tmp2), "content": "x"})]), Reply("Skipped.")], unattended=True)
assert not tmp2.exists() and not io.asked

# 8. memory round trip + plugin loaded
io, a = run([Reply("", [ToolCall("1", "remember", {"fact": "favourite colour is blue"})]), Reply("Saved.")])
assert "blue" in a.system_prompt()
assert "roll_die" in REGISTRY

# 9. history trimming keeps user-first order
from jarvis import config  # noqa: E402
config.SETTINGS.history_limit = 4
a.history = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a", "tool_calls": [{"id": "x", "name": "get_time", "args": {}}]},
             {"role": "tool", "tool_call_id": "x", "name": "get_time", "content": "t"}, {"role": "assistant", "content": "done"}] * 3
a.history.append({"role": "user", "content": "new"})
a._trim()
assert a.history[0]["role"] == "user"

# 10. Anthropic message conversion groups parallel tool results
from jarvis.llm import AnthropicLLM  # noqa: E402
msgs = AnthropicLLM._convert([
    {"role": "user", "content": "go"},
    {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "name": "x", "args": {}}, {"id": "b", "name": "y", "args": {}}]},
    {"role": "tool", "tool_call_id": "a", "name": "x", "content": "1"},
    {"role": "tool", "tool_call_id": "b", "name": "y", "content": "2"}])
assert len(msgs) == 3 and len(msgs[2]["content"]) == 2

# 11. OpenAI-compatible conversion + lite toolset
from jarvis.llm import OpenAICompatLLM  # noqa: E402
om = OpenAICompatLLM._convert("sys", [
    {"role": "user", "content": "go"},
    {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "name": "get_time", "args": {}}]},
    {"role": "tool", "tool_call_id": "a", "name": "get_time", "content": "1"}])
assert om[2]["tool_calls"][0]["function"]["arguments"] == "{}" and om[3]["tool_call_id"] == "a"
from jarvis.registry import active  # noqa: E402
config.SETTINGS.provider, config.SETTINGS.lite = "ollama", "auto"
assert 10 < len(active()) < 40 and "open_app" in active()
config.SETTINGS.lite = "0"
assert len(active()) == len(REGISTRY)

# 12. fuzzy wake word (real mis-transcriptions from an Indian-English mic)
from jarvis.audio_io import find_wake  # noqa: E402
assert find_wake("Jaarvees") == "" and find_wake("Gharvis") == "" and find_wake("Hey Jarveez") == ""
assert find_wake("What time is it, Jalis?") == "What time is it"
assert find_wake("Jarvis, open chrome") == "open chrome"
assert find_wake("Garbage what is the time?") == "what is the time"
assert find_wake("Open Google.") is None and find_wake("Yep.") is None

# 13. new tools registered, lite set includes UI automation, window module imports cleanly if Tk exists
assert {"ui_click", "ui_list_controls", "ui_type"} <= set(REGISTRY)
config.SETTINGS.provider, config.SETTINGS.lite = "ollama", "auto"
assert "ui_click" in active()
try:
    import jarvis.gui  # noqa: F401
except ImportError:
    pass  # no Tk in this environment

# 14. sentence streaming: speaks while text arrives, never repeats the final text
from jarvis.streaming import SentenceStreamer  # noqa: E402
out = []
st = SentenceStreamer(out.append)
for chunk in ["Sure thing. I am open", "ing Chrome now. <think>hmm", " hidden</think>Done", " and dusted."]:
    st.feed(chunk)
st.flush()
assert out == ["Sure thing. I am opening Chrome now.", "Done and dusted."] or out == ["Sure thing. I am opening Chrome now.", "Done and dusted."], out


class StreamLLM:
    def chat(self, system, history, on_text=None, tool_names=None):
        for c in ["The weather looks fine today. ", "Take a light jacket."]:
            on_text(c)
        return Reply("The weather looks fine today. Take a light jacket.")


io = FakeIO()
Agent(io, StreamLLM()).handle("weather")
assert io.said == ["The weather looks fine today.", "Take a light jacket."], io.said

# 15. background agents: create, run with a scripted LLM, report saved, desktop tools blocked, history persisted
from jarvis import agents, llm as llm_mod  # noqa: E402
agents.create("Researcher One", "Research things")
assert agents.get("researcher-one") and agents.listing()[0]["name"] == "researcher-one"
llm_mod._CURRENT = ScriptedLLM([Reply("", [ToolCall("1", "get_time", {})]), Reply("The report is ready.")])
assert "report is ready" in agents.run("researcher-one", "check time", wait=True)
spec = agents.get("researcher-one")
assert spec["runs"][-1]["status"] == "done" and (agents.DIR / "researcher-one.history.json").exists()
bg = Agent(FakeIO(), None, name="x", background=True)
assert "Error: unknown or unavailable" in bg.run_tool(ToolCall("1", "type_text", {"text": "hi"}))
assert agents.delete("researcher-one") and not agents.listing()

# 16. background approvals go through the dashboard queue (denied when no dashboard)
import threading as _t, time as _time  # noqa: E402
from jarvis.approvals import APPROVALS  # noqa: E402
assert APPROVALS.request("t", "q?", timeout=1) == "no"
APPROVALS.enabled = True
_t.Thread(target=lambda: (_time.sleep(0.6), APPROVALS.answer(APPROVALS.pending()[0]["id"], "yes"))).start()
assert APPROVALS.request("t", "q?", timeout=5) == "yes"
APPROVALS.enabled = False

# 17. coding sessions: background run with a live log (python stands in for a coding CLI)
import sys as _sys  # noqa: E402
from jarvis import sessions  # noqa: E402
config.CODING_CLIS["fakecli"] = {"headless": [_sys.executable, "-c"], "interactive": [_sys.executable]}
sid = sessions.start("fakecli", "print('hello from session')", tempfile.gettempdir())
for _ in range(50):
    if sessions.SESS[sid]["status"] != "running":
        break
    _time.sleep(0.1)
assert sessions.SESS[sid]["status"] == "done" and "hello from session" in sessions.tail(sid)

# 18. dashboard security and API
import http.client, json as _json  # noqa: E402
from jarvis import dashboard  # noqa: E402
srv = dashboard.make_server(0)
port = srv.server_address[1]


def req(method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request(method, path, body=_json.dumps(body) if body is not None else None, headers=headers or {})
    r = c.getresponse()
    return r.status, r.read()


tok = {"X-Token": dashboard.TOKEN}
assert req("GET", "/")[0] == 403 and req("GET", "/?t=wrong")[0] == 403
code, page = req("GET", "/?t=" + dashboard.TOKEN)
assert code == 200 and b"<title>Jarvis</title>" in page
assert req("GET", "/api/state")[0] == 401
assert req("GET", "/api/state", headers={**tok, "Host": "evil.example.com"})[0] == 403
code, data = req("GET", "/api/state", headers=tok)
assert code == 200 and "agents" in _json.loads(data) and _json.loads(data)["tools"] > 10
assert req("POST", "/api/agent_create", {"name": "web-bot", "role": "x"}, {**tok})[0] == 200
assert [a["name"] for a in _json.loads(req("GET", "/api/state", headers=tok)[1])["agents"]] == ["web-bot"]
assert req("POST", "/api/memory_add", {"text": "dashboard fact"}, tok)[0] == 200
assert req("POST", "/api/nope", {}, tok)[0] == 404
agents.delete("web-bot")
srv.shutdown()

# 19. phone safety: numbers validated, never auto-approved
from jarvis.tools import phone  # noqa: E402
assert phone._number("+91 98765-43210") == "+919876543210"
try:
    phone._number("12345")
    raise SystemExit("bad number accepted")
except ValueError:
    pass
assert {"phone_call", "send_sms"} <= safety.NEVER_ALWAYS

# 20. HUD page + live state endpoint
srv = dashboard.make_server(0)
port = srv.server_address[1]
from jarvis import status as _status  # noqa: E402
_status.set("speaking"); _status.log("Jarvis", "Hello")
code, page = req("GET", "/hud?t=" + dashboard.TOKEN)
assert code == 200 and b"J.A.R.V.I.S." in page and req("GET", "/hud")[0] == 403
hud = _json.loads(req("GET", "/api/hud", headers=tok)[1])
assert hud["state"] == "speaking" and hud["log"][-1]["text"] == "Hello"
srv.shutdown()

# 21. Hindi / Hinglish: yes-no words and Devanagari wake word
from jarvis.audio_io import parse_yes_no  # noqa: E402
assert parse_yes_no("haan kar do") == "yes" and parse_yes_no("nahi") == "no" and parse_yes_no("हमेशा") == "always"
assert find_wake("जार्विस क्रोम खोलो") == "क्रोम खोलो"

# 22. owner check fails closed when not set up
from jarvis import auth  # noqa: E402
config.SETTINGS.auth_mode = "face"
ok, why = auth.Auth().allow(None)
assert ok is False and why
config.SETTINGS.auth_mode = "off"

# 23. phone control (Telegram): strangers refused, owner served, approvals routed through chat
from jarvis.telegram_bot import TelegramBot  # noqa: E402
sent = []
bot = TelegramBot("x", {1}, ScriptedLLM([Reply("", [ToolCall("1", "write_file", {"path": str(tmp2), "content": "tg"})]),
                                         Reply("All done.")]))
bot.api = lambda method, **d: sent.append((method, d)) or {"ok": True}
bot.handle({"chat": {"id": 999}, "text": "open chrome"})
assert "Not authorised" in sent[-1][1]["text"] and "999" in sent[-1][1]["text"]
bot.handle({"chat": {"id": 1}, "text": "write a file"})
for _ in range(50):
    if any("Allow?" in d.get("text", "") for _, d in sent):
        break
    _time.sleep(0.1)
bot.handle({"chat": {"id": 1}, "text": "yes"})
for _ in range(50):
    if any("All done." in d.get("text", "") for _, d in sent):
        break
    _time.sleep(0.1)
assert tmp2.read_text() == "tg" and any("All done." in d.get("text", "") for _, d in sent)

# 24. pipelined speech worker + non-blocking Mouth (stub pyttsx3 records what would be spoken)
stub = Path(tempfile.mkdtemp())
logf = stub / "spoken.txt"
(stub / "pyttsx3.py").write_text(
    "import os\nclass _E:\n    def setProperty(self,*a): pass\n    def getProperty(self,*a): return []\n"
    "    def say(self,t): open(os.environ['SPOKEN_LOG'],'a').write(t+'\\n')\n    def runAndWait(self): pass\n"
    "def init(): return _E()\n")
os.environ["PYTHONPATH"], os.environ["SPOKEN_LOG"] = str(stub), str(logf)
config.SETTINGS.tts_enabled = True
from jarvis.audio_io import Mouth  # noqa: E402
m = Mouth()
for line in ["First sentence here.", "Second one follows.", "Third and last."]:
    m.say(line)
m.wait(15)
assert m.pending == 0 and logf.read_text().splitlines() == ["First sentence here.", "Second one follows.", "Third and last."]
m.say("Cut me off please.")
m.stop()
assert m.pending == 0 and m.interrupted
m.say("ignored after stop")  # dropped while interrupted
m.interrupted = False
config.SETTINGS.tts_enabled = False

# 25. screen vision pointing: parses model JSON and clamps to the image
from jarvis.tools import screen  # noqa: E402


class VisionLLM:
    def __init__(self, text): self.text = text
    def vision(self, q, png): return self.text


llm_mod._CURRENT = VisionLLM('Sure: {"found": true, "x": 50, "y": 600}')
assert screen._ask_point(b"", 100, 100, "x") == (50, 100)
llm_mod._CURRENT = VisionLLM('{"found": false}')
assert screen._ask_point(b"", 100, 100, "x") is None
llm_mod._CURRENT = VisionLLM("no json here")
assert screen._ask_point(b"", 100, 100, "x") is None

print("All smoke tests passed.")
