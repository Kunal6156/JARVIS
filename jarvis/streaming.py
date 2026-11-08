"""Turns a stream of text chunks into whole sentences, so Jarvis can start talking before the model finishes."""
import re


class SentenceStreamer:
    def __init__(self, emit, min_len=20):
        self.emit, self.min_len = emit, min_len
        self.buf, self.spoken = "", False

    def _out(self, s):
        s = s.strip()
        if s:
            self.spoken = True
            self.emit(s)

    def feed(self, chunk: str):
        self.buf = re.sub(r"<think>.*?</think>", "", self.buf + chunk, flags=re.S)
        if "<think>" in self.buf:  # still inside a reasoning block, hold everything
            return
        start = 0
        for m in re.finditer(r"(?<=[.!?])\s+", self.buf):
            if len(self.buf[start:m.start()].strip()) >= self.min_len:
                self._out(self.buf[start:m.start()])
                start = m.end()
        self.buf = self.buf[start:]

    def flush(self):
        rest = re.sub(r"<think>.*?(</think>|$)", "", self.buf, flags=re.S)
        self.buf = ""
        self._out(rest)
