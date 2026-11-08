"""Background things (agents, coding sessions) tell the user here. main.py points the sink at the voice."""
import collections
import time

_recent = collections.deque(maxlen=60)
_sink = [None]


def set_sink(fn):
    _sink[0] = fn


def send(text: str, speak: bool = True):
    _recent.append({"ts": time.strftime("%H:%M:%S"), "text": text})
    if speak and _sink[0]:
        try:
            _sink[0](text)
        except Exception as e:
            print(f"[notify] {e}")


def recent():
    return list(_recent)
