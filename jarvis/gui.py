"""Small always-on-top window: live transcript, status, Allow/Always/Deny buttons, Stop-talking, typed input.
Tk must own the main thread, so main.py runs the assistant loop in a worker thread and calls mainloop() here."""
import queue
import tkinter as tk
from tkinter import scrolledtext


class JarvisWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Jarvis")
        self.root.geometry("440x540")
        self.root.attributes("-topmost", True)
        self.q, self.typed = queue.Queue(), queue.Queue()
        self.answer = None
        self.on_stop = lambda: None
        self.status_var = tk.StringVar(value="Starting...")
        tk.Label(self.root, textvariable=self.status_var, font=("Segoe UI", 12, "bold")).pack(pady=(8, 2))
        self.box = scrolledtext.ScrolledText(self.root, state="disabled", wrap="word", font=("Segoe UI", 10))
        self.box.pack(fill="both", expand=True, padx=8, pady=4)
        self.box.tag_config("You", foreground="#1a5fb4")
        self.box.tag_config("Jarvis", foreground="#26a269")
        self.box.tag_config("note", foreground="#888888")
        bar = tk.Frame(self.root)
        bar.pack(pady=2)
        self.btns = [tk.Button(bar, text=t, width=9, state="disabled", command=lambda a=a: self._answer(a))
                     for t, a in (("Allow", "yes"), ("Always", "always"), ("Deny", "no"))]
        for b in self.btns:
            b.pack(side="left", padx=3)
        tk.Button(bar, text="Stop talking", command=lambda: self.on_stop()).pack(side="left", padx=10)
        row = tk.Frame(self.root)
        row.pack(fill="x", padx=8, pady=6)
        self.entry = tk.Entry(row, font=("Segoe UI", 10))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self._send())
        tk.Button(row, text="Send", command=self._send).pack(side="left", padx=4)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(100, self._pump)

    # ---- thread-safe API (call from any thread) ----
    def log(self, who, text): self.q.put(("log", (who, text)))
    def status(self, text): self.q.put(("status", text))
    def ask(self, text):
        self.answer = None
        self.q.put(("ask", text))

    def done_asking(self): self.q.put(("unask", None))

    def get_typed(self):
        return self.typed.get()

    # ---- Tk side ----
    def _answer(self, a):
        self.answer = a

    def _send(self):
        t = self.entry.get().strip()
        if t:
            self.entry.delete(0, "end")
            self.typed.put(t)
            self.log("You", t)

    def _close(self):
        self.typed.put(None)
        self.root.destroy()

    def _pump(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "log":
                    who, text = data
                    self.box.config(state="normal")
                    self.box.insert("end", f"{who}: " if who in ("You", "Jarvis") else "  ", who if who in ("You", "Jarvis") else "note")
                    self.box.insert("end", f"{text}\n")
                    self.box.see("end")
                    self.box.config(state="disabled")
                elif kind == "status":
                    self.status_var.set(data)
                elif kind in ("ask", "unask"):
                    for b in self.btns:
                        b.config(state="normal" if kind == "ask" else "disabled")
                    if kind == "ask":
                        self.status_var.set("Waiting for your approval")
        except queue.Empty:
            pass
        self.root.after(100, self._pump)


class GuiIO:
    """Wraps VoiceIO or TextIO and mirrors everything into the window."""

    def __init__(self, inner, win):
        self.inner, self.win = inner, win
        self.text_mode = not hasattr(inner, "ears")
        if hasattr(inner, "mouth"):
            win.on_stop = inner.mouth.stop

    def say(self, text):
        self.win.log("Jarvis", text)
        self.win.status("Speaking...")
        self.inner.say(text)
        self.win.status("Idle")

    def show(self, text):
        self.win.log("·", text)
        self.inner.show(text)

    def listen(self):
        self.win.status("Typing mode" if self.text_mode else "Listening...")
        if self.text_mode:
            return self.win.get_typed()
        text = self.inner.listen()
        if text:
            self.win.log("You", text)
            self.win.status("Thinking...")
        return text

    def after_response(self):
        self.inner.after_response()

    def sleep(self):
        self.inner.sleep()

    def confirm(self, question):
        import time
        from .audio_io import parse_yes_no
        self.win.log("Jarvis", question)
        self.win.ask(question)
        try:
            if self.text_mode:
                end = time.time() + 60
                while time.time() < end and self.win.answer is None:
                    time.sleep(0.2)
                return self.win.answer or "no"
            self.inner.mouth.say(f"{question} Say yes, always, or no, or press a button.")
            self.inner.mouth.wait()
            for _ in range(5):
                if self.win.answer:
                    return self.win.answer
                text = self.inner._heard(timeout=3)
                if text and parse_yes_no(text):
                    return parse_yes_no(text)
            return self.win.answer or "no"
        finally:
            self.win.done_asking()
