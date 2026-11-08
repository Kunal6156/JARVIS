"""Tool registry. Decorate a function with @tool(...) and the LLM can call it."""
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    risk: Any  # "safe" | "ask" | callable(args) -> "safe" | "ask" | "deny"
    fn: Callable


REGISTRY: dict = {}


def tool(description, params=None, required=None, risk="safe"):
    """params: {name: (json_type, description[, enum_list])}. required defaults to all params."""
    params = params or {}

    def deco(fn):
        props = {}
        for k, v in params.items():
            spec = {"type": v[0], "description": v[1]}
            if len(v) > 2:
                spec["enum"] = list(v[2])
            props[k] = spec
        req = list(params) if required is None else list(required)
        REGISTRY[fn.__name__] = Tool(
            fn.__name__, description,
            {"type": "object", "properties": props, "required": req}, risk, fn)
        return fn
    return deco


def register_raw(name, description, schema, fn, risk="ask"):
    REGISTRY[name] = Tool(name, description, schema, risk, fn)


LITE_SET = {
    "open_app", "close_app", "get_time", "web_search", "fetch_url", "browser_open", "browser_search",
    "browser_read", "browser_click", "browser_type", "youtube_play", "set_volume", "media_control",
    "list_directory", "search_files", "read_file", "open_path", "write_file", "run_command",
    "look_at_screen", "click_element", "system_status", "remember", "recall", "add_reminder",
    "run_coding_agent", "type_text", "press_keys", "ui_list_controls", "ui_click", "ui_type",
    "create_agent", "ask_agent", "list_agents", "agent_report", "list_coding_sessions", "coding_session_output",
}


def active():
    """Tools exposed to the model. Lite mode keeps ~28 core tools so small local models stay accurate."""
    from . import config
    S = config.SETTINGS
    lite = S.lite == "1" or (S.lite == "auto" and S.provider != "anthropic")
    return {n: t for n, t in REGISTRY.items() if (not lite or n in LITE_SET or n.startswith("mcp__"))}


def _pick(names):
    return [t for n, t in active().items() if names is None or n in names]


def anthropic_tools(names=None):
    return [{"name": t.name, "description": t.description, "input_schema": t.schema} for t in _pick(names)]


def openai_tools(names=None):
    return [{"type": "function", "function": {
        "name": t.name, "description": t.description, "parameters": t.schema}} for t in _pick(names)]
