"""MCP bridge: connect any MCP server listed in mcp_servers.json and expose its tools to Jarvis.
Config (project root or ~/.jarvis/mcp_servers.json):
  {"servers": {"filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/me/Documents"]}}}
All MCP tools require approval (they are third-party code). Needs `pip install mcp`.
This module is written against the official `mcp` Python SDK and has not been tested against every server."""
import asyncio
import json
import re
import threading

from .. import config
from ..registry import register_raw

_loop = None
_sessions = {}


def _find_config():
    for p in (config.ROOT / "mcp_servers.json", config.DATA_DIR / "mcp_servers.json"):
        if p.exists():
            return p


async def _serve(name, cfg, ready: "asyncio.Future"):
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(command=cfg["command"], args=cfg.get("args", []), env=cfg.get("env"))
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                _sessions[name] = session
                ready.set_result(tools)
                await asyncio.Event().wait()  # keep the connection open
    except Exception as e:
        if not ready.done():
            ready.set_exception(e)


def _make_caller(server, tool_name):
    def call(**kwargs):
        fut = asyncio.run_coroutine_threadsafe(_sessions[server].call_tool(tool_name, kwargs), _loop)
        res = fut.result(timeout=120)
        parts = [getattr(c, "text", "") for c in res.content]
        return "\n".join(p for p in parts if p)[:6000] or "(no output)"
    return call


def start():
    global _loop
    path = _find_config()
    if not path:
        return
    try:
        servers = json.loads(path.read_text(encoding="utf-8")).get("servers", {})
    except ValueError as e:
        print(f"[mcp] bad config: {e}")
        return
    _loop = asyncio.new_event_loop()
    threading.Thread(target=_loop.run_forever, daemon=True, name="mcp").start()
    for name, cfg in servers.items():
        fut = asyncio.run_coroutine_threadsafe(_serve_ready(name, cfg), _loop)
        try:
            tools = fut.result(timeout=60)
        except Exception as e:
            print(f"[mcp] {name} failed: {e}")
            continue
        for t in tools:
            full = re.sub(r"[^a-zA-Z0-9_-]", "_", f"mcp__{name}__{t.name}")[:64]
            register_raw(full, f"[MCP {name}] {t.description or t.name}",
                         t.inputSchema or {"type": "object", "properties": {}},
                         _make_caller(name, t.name), risk="ask")
        print(f"[mcp] {name}: {len(tools)} tools")


async def _serve_ready(name, cfg):
    ready = asyncio.get_running_loop().create_future()
    asyncio.ensure_future(_serve(name, cfg, ready))
    return await ready
