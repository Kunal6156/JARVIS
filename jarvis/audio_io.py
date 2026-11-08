"""Ears (speech-to-text), mouth (text-to-speech) and the two I/O front-ends (voice and text)."""
import collections
import difflib
import os
import re
import subprocess
import sys
import threading
import time

from . import config, status

S = config.SETTINGS
SR = 16000
YES = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "proceed", "affirmative", "allow", "approved",
       "haan", "ha", "han", "haanji", "theek", "thik", "kardo", "हाँ", "हां", "जी", "ठीक"}
NO = {"no", "nope", "nah", "cancel", "stop", "deny", "negative", "don't", "dont", "never",
      "nahi", "nahin", "mat", "ruko", "नहीं", "मत", "रुको"}
JUNK = {"", "you", "thank you", "thanks for watching", "thank you.", "bye", ".", "uh", "um"}


def speakable(text: str, limit=450) -> str:
    text = re.sub(r"```.*?```", " code omitted. ", text, flags=re.S)
    text = re.sub(r"https?://\S+", "link", text)
    text = re.sub(r"[*_`#>|]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        cut = text[:limit]
        i = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        text = cut[: i + 1] if i > 100 else cut
        text += " The rest is on screen."
    return text


def beep():
    try:
        import winsound
        winsound.Beep(900, 90)
    except ImportError:
        print("\a", end="", flush=True)
    except Exception:
        pass


def find_wake(text: str):
    """Fuzzy wake-word detection. Accents make Whisper write 'Jarvis' as 'Jaarvees', 'Gharvis', 'Jalis'...
    Returns the command with the wake word removed ('' if only the wake word was said), or None if absent.
    The wake word may be at the start or the end ('what time is it, Jarvis')."""
    low = text.lower()
    for w in S.wake_words:
        i = low.find(w)
        if i != -1:
            return (text[:i] + " " + text[i + len(w):]).strip(" ,.!?")
    targets = {w for w in S.wake_words if " " not in w}
    toks = list(re.finditer(r"[^\s.,!?;:\"()]+", text))
    edge = set(range(min(3, len(toks)))) | set(range(max(0, len(toks) - 3), len(toks)))
    for idx in sorted(edge):
        word = toks[idx].group(0).lower()
        if word in S.wake_aliases or any(
                difflib.SequenceMatcher(None, word, t).ratio() >= S.wake_sensitivity for t in targets):
            m = toks[idx]
            rest = (text[:m.start()] + " " + text[m.end():]).strip(" ,.!?")
            return re.sub(r"^(hey|hi|ok|okay|yo)\b[ ,]*", "", rest, flags=re.I).strip(" ,.!?")
    return None


class Ears:
    def __init__(self):
        import sounddevice as sd
        from faster_whisper import WhisperModel
        self.sd = sd
        name = S.whisper_model
        if S.language != "en" and name.endswith(".en"):
            name = name[:-3]  # English-only models can't do Hindi
        print(f"Loading speech model '{name}' (first run downloads it)...")
        self.model = WhisperModel(name, device=S.whisper_device, compute_type=S.whisper_compute,
                                  cpu_threads=S.whisper_threads or (os.cpu_count() or 4))
        self.last_audio = None
        self.lock = threading.Lock()
        self.threshold = S.mic_threshold
        self.calibrate()

    def calibrate(self):
        import numpy as np
        with self.sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=1600) as st:
            levels = []
            for _ in range(8):
                data, _ = st.read(1600)
                levels.append(float(np.sqrt(np.mean(data ** 2))))
        self.threshold = max(S.mic_threshold, max(levels) * 2.5)
        print(f"Mic ready (threshold {self.threshold:.4f}).")

    def record_utterance(self, timeout=None, max_seconds=30):
        """Capture one phrase. Retries if Windows briefly drops the audio device ('Stream is stopped')."""
        for attempt in range(4):
            try:
                return self._record(timeout, max_seconds)
            except Exception as e:
                if attempt == 3:
                    raise
                print(f"[mic hiccup, retrying: {str(e)[:60]}]")
                time.sleep(0.4)

    def _record(self, timeout=None, max_seconds=30):
        import numpy as np
        block = 1600  # 0.1 s
        need_silent = max(1, int(S.silence_seconds / 0.1))
        pre = collections.deque(maxlen=3)
        frames, started, silent = [], False, 0
        t0 = time.time()
        t_start = t0
        with self.sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=block) as st:
            while True:
                data, _ = st.read(block)
                chunk = data[:, 0].copy()
                rms = float(np.sqrt(np.mean(chunk ** 2)))
                if not started:
                    pre.append(chunk)
                    if rms > self.threshold:
                        started, frames, silent, t_start = True, list(pre), 0, time.time()
                    elif timeout and time.time() - t0 > timeout:
                        return None
                else:
                    frames.append(chunk)
                    silent = silent + 1 if rms < self.threshold else 0
                    if silent >= need_silent or time.time() - t_start > max_seconds:
                        break
        audio = np.concatenate(frames)
        self.last_audio = audio
        return audio if len(audio) > SR * 0.35 else None

    def transcribe(self, audio) -> str:
        w = S.wake_words[0].title()
        hint = f"{w}, open Chrome. Hey {w}, what time is it?"
        if S.language in ("hi", "auto"):
            hint += f" {w}, Chrome kholo. Hey {w}, abhi time kya hai? जार्विस, म्यूज़िक चलाओ।"
        with self.lock:
            segs, _ = self.model.transcribe(audio, language=None if S.language == "auto" else S.language,
                                            beam_size=1, vad_filter=True, condition_on_previous_text=False,
                                            initial_prompt=hint)
            text = " ".join(s.text.strip() for s in segs).strip()
        return "" if text.lower().strip(" .!?") in JUNK else text


    def transcribe_file(self, path) -> str:
        """For voice notes (Telegram etc). faster-whisper decodes ogg/mp3/wav itself."""
        with self.lock:
            segs, _ = self.model.transcribe(path, language=None if S.language == "auto" else S.language, beam_size=1)
            return " ".join(x.text.strip() for x in segs).strip()


class Mouth:
    """Speaks through a pipelined worker process. say() returns immediately so Jarvis can keep working
    (running tools, writing the next sentence) while talking. wait() blocks until speech is finished;
    the microphone calls it first so Jarvis never hears itself. The stop key kills the worker instantly."""

    def __init__(self):
        self.lock = threading.Lock()
        self.cv = threading.Condition()
        self.pending, self.gen = 0, 0
        self.proc = None
        self.interrupted = False
        try:
            import keyboard
            keyboard.add_hotkey(S.stop_key, self.stop)
        except Exception:
            pass

    def stop(self):
        self.interrupted = True  # drop the rest of this reply too
        with self.cv:
            self.gen += 1
            self.pending = 0
            self.cv.notify_all()
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.kill()
            except OSError:
                pass
        status.set("idle")

    def _reader(self, proc, gen):
        for _ in proc.stdout:
            with self.cv:
                if gen == self.gen:
                    self.pending = max(0, self.pending - 1)
                    if self.pending == 0:
                        status.set("idle")
                    self.cv.notify_all()
        with self.cv:  # worker ended
            if gen == self.gen:
                self.pending = 0
                self.cv.notify_all()

    def _ensure(self):
        if self.proc is None or self.proc.poll() is not None:
            self.proc = subprocess.Popen(
                [sys.executable, str(config.ROOT / "jarvis" / "speak.py"), str(S.tts_rate), S.tts_voice],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)
            threading.Thread(target=self._reader, args=(self.proc, self.gen), daemon=True).start()

    def say(self, text: str):
        print(f"Jarvis: {text}")
        status.log("Jarvis", text)
        if not S.tts_enabled or self.interrupted:
            return
        line = speakable(text).replace("\n", " ")
        if not line:
            return
        with self.lock:
            try:
                self._ensure()
                status.set("speaking")
                with self.cv:
                    self.pending += 1
                self.proc.stdin.write(line + "\n")
                self.proc.stdin.flush()
            except Exception as e:
                self.proc = None
                with self.cv:
                    self.pending = 0
                print(f"[tts unavailable: {e}]")

    def wait(self, timeout=90):
        end = time.time() + timeout
        with self.cv:
            while self.pending > 0 and time.time() < end:
                self.cv.wait(0.2)


class NeuralWake:
    """Always-on, low-CPU wake word detector (openWakeWord). pip install openwakeword"""

    def __init__(self, sd):
        import openwakeword
        from openwakeword.model import Model
        try:
            openwakeword.utils.download_models()
        except Exception:
            pass
        self.sd = sd
        self.model = Model(wakeword_models=[S.neural_model], inference_framework="onnx")

    def wait(self):
        with self.sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=1280) as st:
            while True:
                data, _ = st.read(1280)
                scores = self.model.predict(data[:, 0])
                if scores and max(scores.values()) > S.neural_threshold:
                    if hasattr(self.model, "reset"):
                        self.model.reset()
                    return


def parse_yes_no(text: str):
    low = text.lower()
    words = set(re.findall(r"[^\s.,!?;:\"()]+", low))  # \w would split Devanagari at vowel signs
    if words & NO or "do not" in low:
        return "no"
    if "always" in words or "hamesha" in words or "हमेशा" in words:
        return "always"
    if words & YES or "go ahead" in low or "do it" in low:
        return "yes"
    return None


class VoiceIO:
    def __init__(self):
        self.ears = Ears()
        self.mouth = Mouth()
        self.active_until = 0.0
        self.auth, self.auth_until = None, 0.0
        self.neural = None

    def say(self, text):
        self.mouth.say(text)

    def show(self, text):
        print(f"  ({text})")

    def _heard(self, timeout=None):
        self.mouth.wait()  # never listen while talking
        audio = self.ears.record_utterance(timeout=timeout)
        if audio is None:
            return None
        text = self.ears.transcribe(audio)
        if text:
            print(f"You: {text}")
            status.log("You", text)
        return text or None

    def listen(self):
        while True:
            self.mouth.wait()
            self.mouth.interrupted = False
            status.set("listening")
            text = self._listen()
            if text is None or self._authorized():
                return text

    def _authorized(self) -> bool:
        if S.auth_mode == "off" or time.time() < self.auth_until:
            return True
        if self.auth is None:
            from .auth import Auth
            self.auth = Auth()
        ok, why = self.auth.allow(self.ears.last_audio)
        if ok:
            self.auth_until = time.time() + S.auth_ttl
            return True
        self.active_until = 0.0
        self.say(why or "Sorry, I only take commands from my owner.")
        return False

    def _listen(self):
        if S.listen_mode == "hotkey":
            print(f"[press {S.hotkey.upper()} and speak]")
            try:
                import keyboard
                keyboard.wait(S.hotkey)
            except Exception:
                input("[press Enter, then speak] ")
            beep()
            return self._heard(timeout=8) or self._listen()
        if S.listen_mode == "neural":
            if self.neural is None:
                self.neural = NeuralWake(self.ears.sd)
            while True:
                left = self.active_until - time.time()
                if left > 0:  # follow-ups need no wake word
                    text = self._heard(timeout=max(1.0, left))
                    if text:
                        return text
                    continue
                self.mouth.wait()
                self.neural.wait()
                beep()
                text = self._heard(timeout=8)
                if text:
                    return text
        while True:
            text = self._heard()
            if not text:
                continue
            if S.listen_mode == "always":
                return text
            cmd = find_wake(text)
            if cmd is not None:
                self.active_until = time.time() + S.session_seconds
                if cmd:
                    return cmd
                beep()
                self.say("Yes?")
                continue
            if time.time() < self.active_until:
                return text
            print("  (no wake word heard, ignored)")

    def after_response(self):
        self.mouth.interrupted = False
        self.active_until = time.time() + S.session_seconds

    def sleep(self):
        self.active_until = 0.0

    def confirm(self, question: str) -> str:
        self.say(f"{question} Say yes, always, or no.")
        for _ in range(2):
            beep()
            text = self._heard(timeout=8)
            if text:
                ans = parse_yes_no(text)
                if ans:
                    return ans
        self.say("No answer. Cancelled.")
        return "no"


class TextIO:
    """Keyboard fallback so you can test everything without a microphone."""

    def say(self, text):
        print(f"Jarvis: {text}")

    def show(self, text):
        print(f"  ({text})")

    def listen(self):
        try:
            return input("You> ").strip() or self.listen()
        except (EOFError, KeyboardInterrupt):
            return None

    def after_response(self):
        pass

    def sleep(self):
        pass

    def confirm(self, question):
        try:
            ans = input(f"{question} [y/n/always] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "no"
        return parse_yes_no(ans) or ("yes" if ans.startswith("y") else "no")
