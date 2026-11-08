"""Reminders and recurring routines. A background thread checks every few seconds."""
import json
import threading
import time
from datetime import datetime, timedelta

from . import config

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
SCHEDULER = None  # set by main


class Scheduler:
    def __init__(self, on_reminder, on_routine):
        self.path = config.DATA_DIR / "jobs.json"
        self.on_reminder, self.on_routine = on_reminder, on_routine
        self.lock = threading.Lock()
        self.jobs = []
        if self.path.exists():
            try:
                self.jobs = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.jobs = []
        threading.Thread(target=self._loop, daemon=True, name="scheduler").start()

    def _save(self):
        self.path.write_text(json.dumps(self.jobs, indent=1), encoding="utf-8")

    def _next_id(self):
        return max([j["id"] for j in self.jobs], default=0) + 1

    def add_reminder(self, message, due: datetime):
        with self.lock:
            job = {"id": self._next_id(), "kind": "reminder", "message": message,
                   "due": due.strftime("%Y-%m-%d %H:%M:%S")}
            self.jobs.append(job)
            self._save()
            return job

    def add_routine(self, hhmm, prompt, days, agent=""):
        with self.lock:
            job = {"id": self._next_id(), "kind": "routine", "time": hhmm, "prompt": prompt,
                   "days": days, "last_run": "", "agent": agent}
            self.jobs.append(job)
            self._save()
            return job

    def remove(self, job_id):
        with self.lock:
            n = len(self.jobs)
            self.jobs = [j for j in self.jobs if j["id"] != int(job_id)]
            self._save()
            return n != len(self.jobs)

    def describe(self):
        out = []
        for j in self.jobs:
            if j["kind"] == "reminder":
                out.append(f"#{j['id']} reminder at {j['due']}: {j['message']}")
            else:
                d = ",".join(DAYS[i] for i in j["days"])
                out.append(f"#{j['id']} routine {j['time']} on {d}{' (agent ' + j['agent'] + ')' if j.get('agent') else ''}: {j['prompt']}")
        return out

    def _loop(self):
        while True:
            time.sleep(10)
            now = datetime.now()
            fire = []
            with self.lock:
                for j in list(self.jobs):
                    if j["kind"] == "reminder":
                        if now >= datetime.strptime(j["due"], "%Y-%m-%d %H:%M:%S"):
                            fire.append(j)
                            self.jobs.remove(j)
                    else:
                        h, m = map(int, j["time"].split(":"))
                        sched = now.replace(hour=h, minute=m, second=0, microsecond=0)
                        today = now.strftime("%Y-%m-%d")
                        if (now.weekday() in j["days"] and j["last_run"] != today
                                and sched <= now < sched + timedelta(hours=1)):
                            j["last_run"] = today
                            fire.append(j)
                if fire:
                    self._save()
            for j in fire:
                try:
                    if j["kind"] == "reminder":
                        self.on_reminder(j["message"])
                    else:
                        threading.Thread(target=self.on_routine, args=(j["prompt"], j.get("agent", "")), daemon=True).start()
                except Exception as e:
                    print(f"[scheduler] error: {e}")
