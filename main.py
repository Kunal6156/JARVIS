"""Jarvis: a local, voice-controlled assistant. Run `python main.py` (voice) or `python main.py --text`."""
import argparse
import re
import sys
import threading

from jarvis import config

if sys.stdout is None:  # started with pythonw (shortcut / autostart): keep a log instead
    sys.stdout = sys.stderr = open(config.DATA_DIR / "jarvis.log", "a", buffering=1, encoding="utf-8")

EXIT = {"exit", "quit", "goodbye", "goodbye jarvis", "shut down jarvis", "stop jarvis", "exit jarvis", "quit jarvis"}
SLEEP = {"go to sleep", "that's all", "thats all", "that will be all", "stop listening"}


def norm(t):
    return re.sub(r"[^a-z' ]", "", t.lower()).strip()


def check():
    import importlib
    from jarvis import tools
    from jarvis.registry import REGISTRY
    tools.load_all()
    print(f"Python {sys.version.split()[0]} | provider: {config.SETTINGS.provider} | tools: {len(REGISTRY)}")
    for mod in ["anthropic", "numpy", "sounddevice", "faster_whisper", "pyttsx3", "keyboard", "psutil", "send2trash",
                "pyperclip", "pyautogui", "mss", "PIL", "bs4", "ddgs", "playwright", "mcp", "pycaw", "requests",
                "edge_tts", "pygame", "openwakeword", "cv2", "resemblyzer", "pywinauto"]:
        try:
            importlib.import_module(mod)
            print(f"  ok       {mod}")
        except Exception:
            print(f"  MISSING  {mod}")
    print("API key set:", bool(config.env("ANTHROPIC_API_KEY")))
    try:
        import sounddevice as sd
        print("Default microphone:", sd.query_devices(kind="input")["name"])
    except Exception as e:
        print("Microphone problem:", e)


def install_startup(remove=False):
    """Start Jarvis (HUD mode) at login. Windows: Startup folder. macOS: LaunchAgent. Linux: autostart entry."""
    import os
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        path = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs",
                            "Startup", "Jarvis.bat")
        body = f'@echo off\ncd /d "{config.ROOT}"\nstart "" "{sys.executable.replace("python.exe", "pythonw.exe")}" main.py --hud\n'
    elif sys.platform == "darwin":
        path = os.path.join(home, "Library", "LaunchAgents", "com.jarvis.assistant.plist")
        body = ('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Label</key>'
                '<string>com.jarvis.assistant</string><key>ProgramArguments</key><array>'
                f'<string>{sys.executable}</string><string>{config.ROOT}/main.py</string><string>--hud</string></array>'
                f'<key>WorkingDirectory</key><string>{config.ROOT}</string><key>RunAtLoad</key><true/></dict></plist>\n')
    else:
        path = os.path.join(home, ".config", "autostart", "jarvis.desktop")
        body = (f"[Desktop Entry]\nType=Application\nName=Jarvis\nPath={config.ROOT}\n"
                f"Exec={sys.executable} {config.ROOT}/main.py --hud\n")
    if remove:
        if os.path.exists(path):
            os.remove(path)
        return print("Autostart removed.")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(body)
    print(f"Jarvis will start at login. File: {path}")


def make_transcriber(io):
    """Speech-to-text for phone voice notes: reuse the microphone model, or load a small one on demand."""
    inner = getattr(io, "inner", io)
    if hasattr(inner, "ears"):
        return inner.ears.transcribe_file
    cache = {}

    def lazy(path):
        if "m" not in cache:
            from faster_whisper import WhisperModel
            cache["m"] = WhisperModel("base", device="cpu", compute_type="int8")
        segs, _ = cache["m"].transcribe(path, beam_size=1)
        return " ".join(x.text.strip() for x in segs).strip()
    return lazy


def list_voices():
    import pyttsx3
    for v in pyttsx3.init().getProperty("voices"):
        print(v.name)
    print("\nPut part of a name in .env as JARVIS_TTS_VOICE=<part>")


def main():
    ap = argparse.ArgumentParser(description="Jarvis voice assistant")
    ap.add_argument("--text", action="store_true", help="type instead of speak (no microphone needed)")
    ap.add_argument("--no-tts", action="store_true", help="don't speak replies aloud")
    ap.add_argument("--check", action="store_true", help="diagnose missing packages / microphone")
    ap.add_argument("--gui", action="store_true", help="show the Jarvis window (transcript, approve buttons)")
    ap.add_argument("--dashboard", action="store_true", help="open the web dashboard (agents, coding sessions, approvals)")
    ap.add_argument("--hud", action="store_true", help="voice mode plus the Iron-Man style HUD in your browser (press F11)")
    ap.add_argument("--headless", action="store_true", help="with --dashboard: no microphone, the dashboard is the interface")
    ap.add_argument("--telegram", action="store_true", help="control Jarvis from your phone via a Telegram bot")
    ap.add_argument("--enroll-face", action="store_true", help="register your face for JARVIS_AUTH=face")
    ap.add_argument("--enroll-voice", action="store_true", help="register your voice for JARVIS_AUTH=voice")
    ap.add_argument("--voices", action="store_true", help="list installed text-to-speech voices")
    ap.add_argument("--install-startup", action="store_true", help="start Jarvis automatically when Windows starts")
    ap.add_argument("--remove-startup", action="store_true")
    ap.add_argument("--provider", choices=["anthropic", "ollama", "openai", "omniroute"])
    ap.add_argument("--mode", choices=["wake", "neural", "always", "hotkey"], help="how voice listening starts")
    args = ap.parse_args()

    S = config.SETTINGS
    if args.provider:
        S.provider = args.provider
    if args.mode:
        S.listen_mode = args.mode
    if args.no_tts:
        S.tts_enabled = False
    if args.check:
        return check()
    if args.voices:
        return list_voices()
    if args.enroll_face:
        from jarvis import auth
        return auth.enroll_face()
    if args.enroll_voice:
        from jarvis import auth
        from jarvis.audio_io import Ears
        return auth.enroll_voice(Ears())
    if args.install_startup or args.remove_startup:
        return install_startup(remove=args.remove_startup)

    from jarvis import llm, scheduler, tools
    from jarvis.agent import Agent
    from jarvis.audio_io import TextIO, VoiceIO

    tools.load_all()
    try:
        brain = llm.make_llm()
    except Exception as e:
        sys.exit(f"Can't start the language model: {e}")
    from jarvis.tools import mcp_bridge
    mcp_bridge.start()

    if args.headless:
        args.dashboard = True
        S.auth_mode = "off"
    io = TextIO() if (args.text or args.headless) else VoiceIO()
    win = None
    if args.gui:
        from jarvis.gui import GuiIO, JarvisWindow
        win = JarvisWindow()
        io = GuiIO(io, win)
    agent = Agent(io, brain)

    from jarvis import agents, notify
    notify.set_sink(lambda t: io.say(t))

    def run_routine(prompt, agent=""):
        if agent and agents.get(agent):
            agents.run(agent, prompt, wait=True)  # announces its own result via notify
        else:
            Agent(io, brain, unattended=True).handle(prompt)

    scheduler.SCHEDULER = scheduler.Scheduler(
        on_reminder=lambda msg: io.say(f"Reminder: {msg}"), on_routine=run_routine)

    from jarvis.registry import REGISTRY
    print(f"{len(REGISTRY)} tools loaded.")
    if args.dashboard:
        from jarvis import dashboard
        dashboard.start(brain)
    if args.hud:
        from jarvis import dashboard
        dashboard.start(brain, page="hud")
    if args.telegram:
        from jarvis import telegram_bot
        telegram_bot.start(brain, make_transcriber(io))
    if args.headless:
        io.say("Jarvis is running with the dashboard only. Press Ctrl+C to stop.")
        try:
            while True:
                import time
                time.sleep(3600)
        except KeyboardInterrupt:
            return
    if args.text:
        io.say("Jarvis online (text mode). Type 'exit' to quit.")
    elif S.listen_mode == "wake":
        io.say(f"Jarvis online. Say '{S.wake_words[0]}' followed by a command.")
    elif S.listen_mode == "neural":
        io.say("Jarvis online. Say 'hey Jarvis'.")
    else:
        io.say("Jarvis online.")

    def loop():
        try:
            while True:
                try:
                    text = io.listen()
                except Exception as e:  # e.g. the audio device hiccuped: keep Jarvis alive
                    print(f"[listen error: {e}]")
                    import time
                    time.sleep(1)
                    continue
                if text is None:
                    break
                n = norm(text)
                if n in EXIT:
                    io.say("Goodbye.")
                    break
                if n in SLEEP:
                    io.say("Going quiet.")
                    io.sleep()
                    continue
                try:
                    agent.handle(text)
                except Exception as e:
                    print(f"[error: {e}]")
                    io.say("Something went wrong with that request.")
                io.after_response()
        except KeyboardInterrupt:
            print("\nBye.")
        if win:
            win.root.after(0, win.root.destroy)

    if win:
        threading.Thread(target=loop, daemon=True, name="assistant").start()
        try:
            win.root.mainloop()
        except KeyboardInterrupt:
            pass
    else:
        loop()


if __name__ == "__main__":
    main()
