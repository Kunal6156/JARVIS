"""LLM back-ends with one interface: Anthropic, Ollama and any OpenAI-compatible gateway (OmniRoute...).
chat(system, history, on_text=None, tool_names=None) -> Reply. If on_text is given, text is streamed to it."""
import base64
import json
import re
import uuid
from dataclasses import dataclass, field

from . import config
from .registry import anthropic_tools, openai_tools

S = config.SETTINGS
_CURRENT = None


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Reply:
    text: str = ""
    tool_calls: list = field(default_factory=list)


def _clean(text):
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def _json(args):
    if isinstance(args, str):
        try:
            return json.loads(args or "{}")
        except ValueError:
            return {}
    return args or {}


def _stream_or_once(stream_fn, once_fn, on_text):
    """Stream if possible; if the server can't stream and nothing was emitted yet, fall back to one request."""
    if not (on_text and S.stream):
        return once_fn()
    emitted = [False]

    def tap(t):
        emitted[0] = True
        on_text(t)
    try:
        return stream_fn(tap)
    except Exception:
        if emitted[0]:
            raise
        return once_fn()


class AnthropicLLM:
    def __init__(self):
        import anthropic
        key = config.env("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set. Put it in .env, or use JARVIS_PROVIDER=omniroute/ollama.")
        self.client = anthropic.Anthropic(api_key=key)
        self.model = S.anthropic_model

    @staticmethod
    def _convert(history):
        out = []
        for m in history:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                blocks = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for c in m.get("tool_calls", []):
                    blocks.append({"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]})
                out.append({"role": "assistant", "content": blocks or "(no reply)"})
            else:
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
                last = out[-1] if out else None
                if (last and last["role"] == "user" and isinstance(last["content"], list)
                        and last["content"] and last["content"][0].get("type") == "tool_result"):
                    last["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
        return out

    def chat(self, system, history, on_text=None, tool_names=None) -> Reply:
        kw = dict(model=self.model, max_tokens=S.max_tokens, system=system,
                  messages=self._convert(history), tools=anthropic_tools(tool_names))
        if not kw["tools"]:
            del kw["tools"]

        def once():
            return self.client.messages.create(**kw)

        def stream(tap):
            with self.client.messages.stream(**kw) as st:
                for t in st.text_stream:
                    tap(t)
                return st.get_final_message()
        r = _stream_or_once(stream, once, on_text)
        text = "".join(b.text for b in r.content if b.type == "text").strip()
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in r.content if b.type == "tool_use"]
        return Reply(text, calls)

    def vision(self, question, png: bytes) -> str:
        r = self.client.messages.create(model=self.model, max_tokens=800, messages=[{
            "role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.b64encode(png).decode()}},
                {"type": "text", "text": question}]}])
        return "".join(b.text for b in r.content if b.type == "text").strip()


class OllamaLLM:
    def __init__(self):
        import requests
        self.requests = requests
        self.url = S.ollama_url.rstrip("/")
        self.model = S.ollama_model

    def _check(self, r):
        if r.status_code != 200:
            raise RuntimeError(f"Ollama error {r.status_code}: {r.text[:200]}")

    @staticmethod
    def _msgs(system, history):
        msgs = [{"role": "system", "content": system}]
        for m in history:
            if m["role"] == "user":
                msgs.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                msg = {"role": "assistant", "content": m.get("content", "")}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [{"function": {"name": c["name"], "arguments": c["args"]}}
                                         for c in m["tool_calls"]]
                msgs.append(msg)
            else:
                msgs.append({"role": "tool", "tool_name": m["name"], "content": m["content"]})
        return msgs

    @staticmethod
    def _reply(text, tool_calls):
        calls = [ToolCall(uuid.uuid4().hex[:12], tc["function"]["name"], _json(tc["function"].get("arguments")))
                 for tc in tool_calls or []]
        return Reply(_clean(text), calls)

    def chat(self, system, history, on_text=None, tool_names=None) -> Reply:
        payload = {"model": self.model, "messages": self._msgs(system, history), "options": {"num_ctx": 8192}}
        tools = openai_tools(tool_names)
        if tools:
            payload["tools"] = tools

        def once():
            r = self.requests.post(f"{self.url}/api/chat", json={**payload, "stream": False}, timeout=300)
            self._check(r)
            m = r.json()["message"]
            return self._reply(m.get("content", ""), m.get("tool_calls"))

        def stream(tap):
            r = self.requests.post(f"{self.url}/api/chat", json={**payload, "stream": True}, timeout=300, stream=True)
            self._check(r)
            text, tcs = "", []
            for line in r.iter_lines():
                if not line:
                    continue
                m = json.loads(line).get("message") or {}
                if m.get("content"):
                    text += m["content"]
                    tap(m["content"])
                tcs += m.get("tool_calls") or []
            return self._reply(text, tcs)
        return _stream_or_once(stream, once, on_text)

    def vision(self, question, png: bytes) -> str:
        r = self.requests.post(f"{self.url}/api/chat", timeout=300, json={
            "model": S.ollama_vision_model, "stream": False, "messages": [
                {"role": "user", "content": question, "images": [base64.b64encode(png).decode()]}]})
        self._check(r)
        return (r.json()["message"].get("content") or "").strip()


class OpenAICompatLLM:
    """OmniRoute, LM Studio, vLLM, llama.cpp server, Ollama's /v1, OpenAI..."""

    def __init__(self):
        import requests
        self.requests = requests
        self.base = S.openai_base_url.rstrip("/")
        self.model = S.openai_model
        if not self.model:
            raise RuntimeError("Set JARVIS_OPENAI_MODEL in .env (the model/combo name shown in OmniRoute).")

    def _post(self, payload, stream=False):
        headers = {"Content-Type": "application/json"}
        if S.openai_key:
            headers["Authorization"] = f"Bearer {S.openai_key}"
        r = self.requests.post(f"{self.base}/chat/completions", json=payload, headers=headers,
                               timeout=300, stream=stream)
        if r.status_code != 200:
            raise RuntimeError(f"Gateway error {r.status_code}: {r.text[:200]}")
        return r

    @staticmethod
    def _convert(system, history):
        msgs = [{"role": "system", "content": system}]
        for m in history:
            if m["role"] == "user":
                msgs.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                msg = {"role": "assistant", "content": m.get("content") or ""}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [{"id": c["id"], "type": "function",
                                          "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
                                         for c in m["tool_calls"]]
                msgs.append(msg)
            else:
                msgs.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
        return msgs

    def chat(self, system, history, on_text=None, tool_names=None) -> Reply:
        payload = {"model": self.model, "messages": self._convert(system, history), "max_tokens": S.max_tokens}
        tools = openai_tools(tool_names)
        if tools:
            payload["tools"] = tools

        def once():
            msg = self._post(payload).json()["choices"][0]["message"]
            calls = [ToolCall(tc.get("id") or uuid.uuid4().hex[:12], tc["function"]["name"],
                              _json(tc["function"].get("arguments"))) for tc in msg.get("tool_calls") or []]
            return Reply(_clean(msg.get("content")), calls)

        def stream(tap):
            r = self._post({**payload, "stream": True}, stream=True)
            r.encoding = "utf-8"
            text, acc = "", {}
            for raw in r.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                data = raw[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    d = ((json.loads(data).get("choices") or [{}])[0]).get("delta") or {}
                except ValueError:
                    continue
                if d.get("content"):
                    text += d["content"]
                    tap(d["content"])
                for tc in d.get("tool_calls") or []:
                    c = acc.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                    c["id"] = tc.get("id") or c["id"]
                    fn = tc.get("function") or {}
                    c["name"] += fn.get("name") or ""
                    c["args"] += fn.get("arguments") or ""
            calls = [ToolCall(c["id"] or uuid.uuid4().hex[:12], c["name"], _json(c["args"]))
                     for _, c in sorted(acc.items()) if c["name"]]
            return Reply(_clean(text), calls)
        return _stream_or_once(stream, once, on_text)

    def vision(self, question, png: bytes) -> str:
        url = "data:image/png;base64," + base64.b64encode(png).decode()
        r = self._post({"model": S.openai_vision_model or self.model, "max_tokens": 800, "messages": [
            {"role": "user", "content": [{"type": "text", "text": question},
                                         {"type": "image_url", "image_url": {"url": url}}]}]})
        return (r.json()["choices"][0]["message"].get("content") or "").strip()


def make_llm():
    global _CURRENT
    if S.provider in ("openai", "omniroute"):
        _CURRENT = OpenAICompatLLM()
    elif S.provider == "ollama":
        _CURRENT = OllamaLLM()
    else:
        _CURRENT = AnthropicLLM()
    return _CURRENT


def get():
    if _CURRENT is None:
        raise RuntimeError("LLM not initialised")
    return _CURRENT
