"""Speech worker. One line in on stdin = one utterance; prints 'done' after each has been spoken.
With edge-tts the next sentence is synthesised while the current one plays, so there are no gaps.
Jarvis kills this process to interrupt speech. Usage: speak.py <rate> [offline-voice-name-fragment]"""
import os
import queue
import re
import signal
import sys
import tempfile
import threading
import time


def main():
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # Ctrl+C belongs to the parent; no traceback noise
    rate = int(sys.argv[1]) if len(sys.argv) > 1 else 185
    voice = sys.argv[2] if len(sys.argv) > 2 else ""
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    q_text, q_play = queue.Queue(), queue.Queue()
    edge = None
    if os.environ.get("JARVIS_TTS_ENGINE", "").lower() == "edge":
        try:
            os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
            import asyncio
            import edge_tts
            import pygame
            en = os.environ.get("JARVIS_EDGE_VOICE", "en-GB-RyanNeural")
            hi = os.environ.get("JARVIS_EDGE_VOICE_HI", "hi-IN-MadhurNeural")

            def edge(text):
                path = tempfile.mktemp(suffix=".mp3")
                v = hi if re.search(r"[\u0900-\u097F]", text) else en
                asyncio.run(edge_tts.Communicate(text, v).save(path))
                return path
        except Exception:
            edge = None  # not installed: use the offline voice

    def synth_loop():
        while True:
            text = q_text.get()
            if text is None:
                q_play.put(None)
                return
            path = None
            if edge:
                try:
                    path = edge(text)
                except Exception:
                    path = None  # offline or blocked: this line uses the offline voice
            q_play.put((text, path))

    def play_loop():
        eng = None
        mixer = False
        while True:
            item = q_play.get()
            if item is None:
                return
            text, path = item
            try:
                if path:
                    import pygame
                    if not mixer:
                        pygame.mixer.init()
                        mixer = True
                    pygame.mixer.music.load(path)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.04)
                    pygame.mixer.music.unload()
                    os.remove(path)
                else:
                    if eng is None:
                        import pyttsx3
                        eng = pyttsx3.init()
                        eng.setProperty("rate", rate)
                        for v in eng.getProperty("voices"):
                            if voice and voice.lower() in (v.name or "").lower():
                                eng.setProperty("voice", v.id)
                                break
                    eng.say(text)
                    eng.runAndWait()
            except Exception:
                pass
            print("done", flush=True)

    t1 = threading.Thread(target=synth_loop, daemon=True)
    t2 = threading.Thread(target=play_loop)
    t1.start()
    t2.start()
    for line in sys.stdin:
        text = line.strip()
        if text:
            q_text.put(text)
        else:
            print("done", flush=True)
    q_text.put(None)
    t2.join()


try:
    main()
except KeyboardInterrupt:
    pass
