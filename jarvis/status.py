"""Shared live state for the HUD: what Jarvis is doing right now and the recent transcript."""
import collections
import time

STATE = {"v": "idle"}  # idle | listening | thinking | speaking
TRANSCRIPT = collections.deque(maxlen=40)


def set(v):
    STATE["v"] = v


def log(who, text):
    TRANSCRIPT.append({"who": who, "text": text, "ts": time.time()})
