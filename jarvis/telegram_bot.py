"""Control Jarvis from your phone with a Telegram bot (free, no public URL needed). Text and voice notes work.
Setup: talk to @BotFather, create a bot, put its token in TELEGRAM_TOKEN. Message the bot once: it replies with your
chat id. Put that in TELEGRAM_ALLOWED_IDS and restart. Only listed chat ids are obeyed. Risky actions still ask
you, on Telegram. Commands: /screen (screenshot), /status, /id."""
import os
import tempfile
import threading
import time

from . import config
from .audio_io import parse_yes_no


class TelegramIO:
    def __init__(self, bot, chat):
        self.bot, self.chat = bot, chat

    def say(self, t): self.bot.send(self.chat, t)
    def show(self, t): pass
    def listen(self): return None
    def after_response(self): pass
    def sleep(self): pass

    def confirm(self, q):
        self.bot.send(self.chat, f"{q}\nReply yes, always or no.")
        return parse_yes_no(self.bot.wait_reply(self.chat, 120) or "") or "no"


class TelegramBot:
    def __init__(self, token, allowed, brain, transcribe=None):
        self.token, self.allowed, self.brain, self.transcribe = token, set(allowed), brain, transcribe
        self.base = f"https://api.telegram.org/bot{token}"
        self.agents, self.waiting, self.offset = {}, {}, 0

    def api(self, method, **data):
        import requests
        return requests.post(f"{self.base}/{method}", data=data, timeout=40).json()

    def send(self, chat, text):
        for i in range(0, max(len(text), 1), 3900):
            self.api("sendMessage", chat_id=chat, text=text[i:i + 3900])

    def wait_reply(self, chat, timeout):
        slot = {"ev": threading.Event(), "text": None}
        self.waiting[chat] = slot
        slot["ev"].wait(timeout)
        self.waiting.pop(chat, None)
        return slot["text"]

    def _voice_text(self, msg):
        import requests
        fid = (msg.get("voice") or msg.get("audio"))["file_id"]
        info = self.api("getFile", file_id=fid)["result"]
        data = requests.get(f"https://api.telegram.org/file/bot{self.token}/{info['file_path']}", timeout=60).content
        path = tempfile.mktemp(suffix=".oga")
        open(path, "wb").write(data)
        try:
            return self.transcribe(path) if self.transcribe else None
        finally:
            os.remove(path)

    def _command(self, chat, text):
        cmd = text.split()[0].split("@")[0].lower()
        if cmd in ("/id", "/start"):
            self.send(chat, f"Your chat id is {chat}.")
        elif cmd == "/status":
            from .tools.system import system_status
            self.send(chat, system_status())
        elif cmd == "/screen":
            import requests
            from .tools.screen import take_screenshot
            with open(take_screenshot(), "rb") as f:
                requests.post(f"{self.base}/sendPhoto", data={"chat_id": chat}, files={"photo": f}, timeout=60)
        else:
            self.send(chat, "Commands: /screen /status /id. Or just type or speak a request.")

    def _run(self, chat, text):
        from .agent import Agent
        ag = self.agents.setdefault(chat, Agent(TelegramIO(self, chat), self.brain))
        ag.handle(text)

    def handle(self, msg):
        chat = msg["chat"]["id"]
        if chat not in self.allowed:
            self.send(chat, f"Not authorised. Your chat id is {chat}. Add it to TELEGRAM_ALLOWED_IDS in .env "
                            "and restart Jarvis.")
            return
        text = msg.get("text")
        if not text and (msg.get("voice") or msg.get("audio")):
            text = self._voice_text(msg)
            if text is None:
                return self.send(chat, "I can't transcribe voice notes right now.")
            self.send(chat, f"Heard: {text}")
        if not text:
            return
        slot = self.waiting.get(chat)
        if slot:  # this message answers an approval question
            slot["text"] = text
            slot["ev"].set()
            return
        if text.startswith("/"):
            return self._command(chat, text)
        threading.Thread(target=self._run, args=(chat, text), daemon=True).start()

    def run(self):
        import requests
        me = self.api("getMe")
        if not me.get("ok"):
            return print("[telegram] bad TELEGRAM_TOKEN")
        print(f"[telegram] @{me['result']['username']} ready. Allowed chats: {sorted(self.allowed) or 'none yet'}")
        while True:
            try:
                upd = requests.post(f"{self.base}/getUpdates", data={"offset": self.offset, "timeout": 25},
                                    timeout=40).json()
                for u in upd.get("result", []):
                    self.offset = u["update_id"] + 1
                    if "message" in u:
                        try:
                            self.handle(u["message"])
                        except Exception as e:
                            print(f"[telegram] {e}")
            except Exception:
                time.sleep(3)


def start(brain, transcribe=None):
    token = config.env("TELEGRAM_TOKEN")
    if not token:
        return print("[telegram] set TELEGRAM_TOKEN in .env (create a bot with @BotFather)")
    ids = {int(x) for x in config.env("TELEGRAM_ALLOWED_IDS", "").replace(" ", "").split(",")
           if x.strip().lstrip("-").isdigit()}
    bot = TelegramBot(token, ids, brain, transcribe)
    threading.Thread(target=bot.run, daemon=True, name="telegram").start()
    return bot
