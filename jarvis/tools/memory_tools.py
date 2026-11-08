"""Tools for long-term memory, reminders and routines."""
from datetime import datetime, timedelta

from .. import scheduler as sch
from ..memory import MEMORY
from ..registry import tool


@tool("Save a lasting fact or preference about the user.", {"fact": ("string", "What to remember")})
def remember(fact):
    return "Saved." if MEMORY.add(fact) else "Already known."


@tool("Search saved memories.", {"query": ("string", "Search words")})
def recall(query):
    hits = MEMORY.search(query)
    return "\n".join(f"- {h['text']}" for h in hits) or "Nothing found."


@tool("Delete saved memories matching a phrase.", {"query": ("string", "Words identifying the memory")}, risk="ask")
def forget(query):
    return f"Forgot {MEMORY.forget(query)} item(s)."


def _need():
    if sch.SCHEDULER is None:
        raise RuntimeError("Scheduler not running.")
    return sch.SCHEDULER


@tool("Set a spoken reminder. Give minutes_from_now OR an absolute local time 'YYYY-MM-DD HH:MM'.",
      {"message": ("string", "What to remind"), "minutes_from_now": ("number", "Delay in minutes"),
       "at": ("string", "Absolute local time 'YYYY-MM-DD HH:MM'")}, required=["message"])
def add_reminder(message, minutes_from_now=None, at=None):
    if at:
        due = datetime.strptime(at.strip(), "%Y-%m-%d %H:%M")
    elif minutes_from_now is not None:
        due = datetime.now() + timedelta(minutes=float(minutes_from_now))
    else:
        return "Need minutes_from_now or at."
    job = _need().add_reminder(message, due)
    return f"Reminder #{job['id']} set for {job['due']}."


@tool("Create a recurring routine: at a time of day, Jarvis runs a prompt on its own (unattended: tools that need "
      "approval are skipped). Example: a morning briefing.",
      {"time": ("string", "24h 'HH:MM'"), "prompt": ("string", "What Jarvis should do"),
       "days": ("string", "'daily', 'weekdays', or comma list like 'mon,wed,fri'"),
       "agent": ("string", "Optional background agent name to run it")},
      required=["time", "prompt"], risk="ask")
def add_routine(time, prompt, days="daily", agent=""):
    d = days.lower().strip()
    if d == "daily":
        idx = list(range(7))
    elif d == "weekdays":
        idx = [0, 1, 2, 3, 4]
    else:
        idx = [sch.DAYS.index(x.strip()[:3]) for x in d.split(",") if x.strip()[:3] in sch.DAYS]
    datetime.strptime(time, "%H:%M")
    job = _need().add_routine(time, prompt, idx, agent)
    return f"Routine #{job['id']} created."


@tool("List reminders and routines.", {})
def list_schedule():
    return "\n".join(_need().describe()) or "Nothing scheduled."


@tool("Remove a reminder or routine by its number.", {"id": ("integer", "Job number")})
def remove_schedule(id):
    return "Removed." if _need().remove(id) else "No such job."
