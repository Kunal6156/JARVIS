"""Approval requests from places with no microphone (the dashboard chat, background agents)."""
import threading
import time
import uuid


class Approvals:
    def __init__(self):
        self.enabled = False  # turned on when the dashboard is running
        self.items = {}
        self.lock = threading.Lock()

    def request(self, who: str, question: str, timeout: int = 300) -> str:
        if not self.enabled:
            return "no"
        item = {"id": uuid.uuid4().hex[:8], "who": who, "question": question, "answer": None}
        with self.lock:
            self.items[item["id"]] = item
        end = time.time() + timeout
        while time.time() < end and item["answer"] is None:
            time.sleep(0.3)
        with self.lock:
            self.items.pop(item["id"], None)
        return item["answer"] or "no"

    def pending(self):
        with self.lock:
            return [dict(i) for i in self.items.values() if i["answer"] is None]

    def answer(self, item_id: str, answer: str) -> bool:
        with self.lock:
            item = self.items.get(item_id)
            if item and answer in ("yes", "always", "no"):
                item["answer"] = answer
                return True
        return False


APPROVALS = Approvals()
