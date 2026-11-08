"""Phone calls and SMS through Twilio (optional, needs your own account and costs money).
Set TWILIO_SID, TWILIO_TOKEN and TWILIO_FROM in .env. The call speaks a message; it is not a conversation."""
import html
import re

from .. import config
from ..registry import tool


def _creds():
    sid, token, frm = (config.env("TWILIO_SID"), config.env("TWILIO_TOKEN"), config.env("TWILIO_FROM"))
    if not (sid and token and frm):
        raise RuntimeError("Set TWILIO_SID, TWILIO_TOKEN and TWILIO_FROM in .env to use phone features.")
    return sid, token, frm


def _number(n):
    n = re.sub(r"[ \-()]", "", n)
    if not re.fullmatch(r"\+\d{8,15}", n):
        raise ValueError("Phone number must be in international format like +919876543210.")
    return n


@tool("Place a phone call that reads a message aloud to a number (international format).",
      {"to": ("string", "Number like +919876543210"), "message": ("string", "What to say")}, risk="ask")
def phone_call(to, message):
    import requests
    sid, token, frm = _creds()
    twiml = f"<Response><Say>{html.escape(message)}</Say></Response>"
    r = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json",
                      data={"To": _number(to), "From": frm, "Twiml": twiml}, auth=(sid, token), timeout=20)
    return f"Call queued ({r.json().get('sid')})." if r.ok else f"Twilio error {r.status_code}: {r.text[:200]}"


@tool("Send an SMS text message.",
      {"to": ("string", "Number like +919876543210"), "text": ("string", "Message")}, risk="ask")
def send_sms(to, text):
    import requests
    sid, token, frm = _creds()
    r = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                      data={"To": _number(to), "From": frm, "Body": text[:1500]}, auth=(sid, token), timeout=20)
    return f"SMS queued ({r.json().get('sid')})." if r.ok else f"Twilio error {r.status_code}: {r.text[:200]}"


@tool("Send a WhatsApp message through Twilio (sandbox or approved sender). To receive and control Jarvis "
      "from your phone, use the Telegram bot instead.",
      {"to": ("string", "Number like +919876543210"), "text": ("string", "Message")}, risk="ask")
def send_whatsapp(to, text):
    import requests
    sid, token, _ = _creds()
    frm = config.env("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    r = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                      data={"To": "whatsapp:" + _number(to), "From": frm, "Body": text[:1500]},
                      auth=(sid, token), timeout=20)
    return f"WhatsApp queued ({r.json().get('sid')})." if r.ok else f"Twilio error {r.status_code}: {r.text[:200]}"
