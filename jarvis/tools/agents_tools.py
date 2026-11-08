"""Tools for creating and using persistent background agents."""
from .. import agents
from ..registry import tool


@tool("Create a persistent background agent with a role, e.g. name 'researcher', role 'Research topics on the web "
      "and report briefly'. Optional comma list of allowed tools (default is a safe research/files set).",
      {"name": ("string", "Short name"), "role": ("string", "What this agent is for"),
       "tools": ("string", "Comma-separated tool names, or empty for the default set")},
      required=["name", "role"], risk="ask")
def create_agent(name, role, tools=""):
    spec = agents.create(name, role, [t.strip() for t in tools.split(",") if t.strip()] or None)
    return f"Agent {spec['name']} created."


@tool("List the background agents and whether they are busy.", {})
def list_agents():
    rows = [f"{a['name']}: {a['role'][:80]} ({'working on: ' + agents.RUNNING[a['name']]['task'] if a['name'] in agents.RUNNING else 'idle'})"
            for a in agents.listing()]
    return "\n".join(rows) or "No agents yet."


@tool("Give a background agent a job. It works on its own and Jarvis announces when it finishes. "
      "wait=true blocks until the report is ready (only for quick jobs).",
      {"name": ("string", "Agent name"), "task": ("string", "The job"), "wait": ("boolean", "Wait for the result")},
      required=["name", "task"])
def ask_agent(name, task, wait=False):
    r = agents.run(name, task, wait=bool(wait))
    return r if wait else f"{name} is on it. You'll hear when it's done."


@tool("Get an agent's most recent report.", {"name": ("string", "Agent name")})
def agent_report(name):
    spec = agents.get(name)
    if not spec:
        return "No such agent."
    if spec["name"] in agents.RUNNING:
        return "Still working."
    runs = spec.get("runs", [])
    return runs[-1]["result"] if runs else "No runs yet."


@tool("Delete a background agent and its history.", {"name": ("string", "Agent name")}, risk="ask")
def delete_agent(name):
    return "Deleted." if agents.delete(name) else "No such agent."
