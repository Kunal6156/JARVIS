"""Approval policy + audit log. Every tool call is assessed here before it runs."""
import json
import re
import time
from pathlib import Path

from . import config

BLOCKED_SHELL = [
    r"\bformat\s+[a-z]:", r"\brm\s+-[a-z]*r[a-z]*f?[a-z]*\s+(/|~|\*)(\s|$)", r"\brd\s+/s\s+/q\s+[a-z]:\\?(\s|$)",
    r"\bdel\s+(/[a-z]\s+)*[a-z]:\\\*?(\s|$)", r"\bremove-item\b.*-recurse.*\s[a-z]:\\?(\s|$)",
    r"\bdiskpart\b", r"\bbcdedit\b", r"\bmkfs\b", r"\bdd\s+if=", r":\(\)\s*\{", r"\bcipher\s+/w",
    r"\bvssadmin\s+delete", r"\breg\s+delete\s+hk(lm|cr)", r"\bformat-volume\b", r"\bclear-disk\b",
    r"\bnet\s+user\s+\S+\s+\S+\s+/add", r"\bsetx?\s+.*\bpath\b.*=\s*$",
]
PROTECTED_DIRS = [r"c:\windows", r"c:\program files", r"c:\program files (x86)", r"c:\programdata\microsoft",
                  "/etc", "/bin", "/sbin", "/usr", "/boot", "/system", "/library"]
# Tools that can never be switched to "always allow" for a session.
NEVER_ALWAYS = {"run_command", "delete_path", "system_power", "run_coding_agent", "write_file", "move_path", "phone_call", "send_sms", "send_whatsapp"}


def is_protected(path) -> bool:
    p = Path(path).resolve()
    s = str(p).lower()
    if p.parent == p:  # drive or filesystem root
        return True
    return any(s == d or s.startswith(d + "\\") or s.startswith(d + "/") for d in PROTECTED_DIRS)


def assess(t, args) -> str:
    """Returns 'allow', 'ask' or 'deny'."""
    if t.name == "run_command":
        cmd = str(args.get("command", ""))
        if any(re.search(p, cmd, re.I) for p in BLOCKED_SHELL):
            return "deny"
        return "ask"  # never auto-approved
    try:
        risk = t.risk(args) if callable(t.risk) else t.risk
    except Exception:
        risk = "ask"
    if risk == "deny":
        return "deny"
    if risk == "safe":
        return "allow"
    if t.name in config.SETTINGS.auto_approve:
        return "allow"
    return "ask"


def audit(event: dict):
    event = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), **event}
    try:
        with open(config.DATA_DIR / "audit.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str)[:3000] + "\n")
    except OSError:
        pass
