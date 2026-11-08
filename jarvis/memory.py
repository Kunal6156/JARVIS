"""Long-term memory: facts the user asked Jarvis to remember. Stored in ~/.jarvis/memory.json."""
import json
import re
import threading
import time

from . import config


class Memory:
    def __init__(self):
        self.path = config.DATA_DIR / "memory.json"
        self.lock = threading.Lock()
        self.facts = []
        if self.path.exists():
            try:
                self.facts = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.facts = []

    def _save(self):
        self.path.write_text(json.dumps(self.facts, indent=1, ensure_ascii=False), encoding="utf-8")

    def add(self, text: str) -> bool:
        text = text.strip()
        with self.lock:
            if any(f["text"].lower() == text.lower() for f in self.facts):
                return False
            nid = max([f["id"] for f in self.facts], default=0) + 1
            self.facts.append({"id": nid, "text": text, "ts": time.strftime("%Y-%m-%d")})
            self._save()
            return True

    def search(self, query: str, limit=8):
        words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
        scored = []
        for f in self.facts:
            low = f["text"].lower()
            s = sum(w in low for w in words)
            if s:
                scored.append((s, f))
        scored.sort(key=lambda x: -x[0])
        return [f for _, f in scored[:limit]]

    def forget(self, query: str) -> int:
        with self.lock:
            hits = {f["id"] for f in self.search(query, 50)}
            self.facts = [f for f in self.facts if f["id"] not in hits]
            self._save()
            return len(hits)

    def recent(self, n=40):
        return self.facts[-n:]


MEMORY = Memory()
