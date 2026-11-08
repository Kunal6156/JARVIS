"""System controls: volume, media keys, clipboard, typing, status, power. Windows, macOS and Linux."""
import ctypes
import os
import shutil
import subprocess
import sys
import time

from ..registry import tool

WIN, MAC = sys.platform == "win32", sys.platform == "darwin"


def _pag():
    import pyautogui
    pyautogui.PAUSE = 0.05
    return pyautogui


def _run(*cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout or r.stderr).strip()


@tool("Get the current date and time.", {})
def get_time():
    return time.strftime("%A %d %B %Y, %H:%M:%S")


@tool("Report battery, CPU, memory and disk usage.", {})
def system_status():
    import psutil
    lines = [f"CPU {psutil.cpu_percent(interval=0.5)}%", f"Memory {psutil.virtual_memory().percent}%"]
    try:
        lines.append(f"Disk {psutil.disk_usage(os.path.abspath(os.sep)).percent}% used")
    except OSError:
        pass
    b = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if b:
        lines.append(f"Battery {int(b.percent)}%{' (charging)' if b.power_plugged else ''}")
    return ", ".join(lines)


def _endpoint():
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    dev = AudioUtilities.GetSpeakers()
    if hasattr(dev, "EndpointVolume"):
        return dev.EndpointVolume
    iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return ctypes.cast(iface, ctypes.POINTER(IAudioEndpointVolume))


@tool("Set the system volume (0-100).", {"level": ("integer", "Volume percent")})
def set_volume(level):
    level = max(0, min(100, int(level)))
    if MAC:
        _run("osascript", "-e", f"set volume output volume {level}")
    elif not WIN:
        if not (shutil.which("pactl") and _run("pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%")[0]):
            _run("amixer", "set", "Master", f"{level}%")
    else:
        try:
            _endpoint().SetMasterVolumeLevelScalar(level / 100.0, None)
        except Exception:
            pag = _pag()  # fallback: media keys (each press is about 2%)
            pag.press("volumedown", presses=50)
            pag.press("volumeup", presses=level // 2)
    return f"Volume set to {level}%."


@tool("Get the current system volume.", {})
def get_volume():
    try:
        if MAC:
            return f"Volume is {_run('osascript', '-e', 'output volume of (get volume settings)')[1]}%."
        if not WIN:
            return _run("pactl", "get-sink-volume", "@DEFAULT_SINK@")[1][:120] or "Unknown."
        return f"Volume is {round(_endpoint().GetMasterVolumeLevelScalar() * 100)}%."
    except Exception as e:
        return f"Can't read volume here ({e})."


@tool("Mute, unmute or toggle the system audio.", {"state": ("string", "mute, unmute or toggle", ["mute", "unmute", "toggle"])})
def set_mute(state="toggle"):
    if MAC:
        cur = _run("osascript", "-e", "output muted of (get volume settings)")[1] == "true"
        new = (not cur) if state == "toggle" else state == "mute"
        _run("osascript", "-e", f"set volume output muted {'true' if new else 'false'}")
        return "Muted." if new else "Unmuted."
    if not WIN:
        _run("pactl", "set-sink-mute", "@DEFAULT_SINK@", {"mute": "1", "unmute": "0", "toggle": "toggle"}[state])
        return f"{state} done."
    try:
        ep = _endpoint()
        new = (not ep.GetMute()) if state == "toggle" else state == "mute"
        ep.SetMute(1 if new else 0, None)
        return "Muted." if new else "Unmuted."
    except Exception:
        _pag().press("volumemute")
        return "Toggled mute."


@tool("Control media playback.", {"action": ("string", "play_pause, next, previous or stop",
                                             ["play_pause", "next", "previous", "stop"])})
def media_control(action):
    key = {"play_pause": "playpause", "next": "nexttrack", "previous": "prevtrack", "stop": "stop"}[action]
    _pag().press(key)
    return f"Sent {action}."


@tool("Read the clipboard text.", {})
def clipboard_read():
    import pyperclip
    return pyperclip.paste()[:4000] or "(clipboard empty)"


@tool("Copy text to the clipboard.", {"text": ("string", "Text")})
def clipboard_write(text):
    import pyperclip
    pyperclip.copy(text)
    return "Copied."


@tool("Type text into whatever window currently has focus.", {"text": ("string", "Text to type")}, risk="ask")
def type_text(text):
    if text.isascii():
        _pag().write(text, interval=0.01)
    else:
        import pyperclip
        pyperclip.copy(text)
        _pag().hotkey("command" if MAC else "ctrl", "v")
    return f"Typed {len(text)} characters."


@tool("Press a keyboard shortcut in the focused window, e.g. 'ctrl+s', 'alt+tab', 'win+d', 'enter'.",
      {"keys": ("string", "Keys joined by +")}, risk="ask")
def press_keys(keys):
    _pag().hotkey(*[k.strip().lower() for k in keys.split("+")])
    return f"Pressed {keys}."


@tool("Get the title of the window or app currently in focus.", {})
def active_window():
    if WIN:
        u = ctypes.windll.user32
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(u.GetForegroundWindow(), buf, 256)
        return buf.value or "(no title)"
    if MAC:
        return _run("osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true')[1]
    return _run("xdotool", "getactivewindow", "getwindowname")[1] or "Needs xdotool."


@tool("Lock the computer.", {})
def lock_screen():
    if WIN:
        ctypes.windll.user32.LockWorkStation()
    elif MAC:
        _run("pmset", "displaysleepnow")
    else:
        _run("loginctl", "lock-session")
    return "Locked."


@tool("Shut down or restart the computer after a short delay, or cancel a pending one.",
      {"action": ("string", "shutdown, restart or cancel", ["shutdown", "restart", "cancel"])}, risk="ask")
def system_power(action):
    if WIN:
        flag = {"shutdown": ["/s", "/t", "30"], "restart": ["/r", "/t", "30"], "cancel": ["/a"]}[action]
        subprocess.run(["shutdown"] + flag)
    else:
        flag = {"shutdown": ["-h", "+1"], "restart": ["-r", "+1"], "cancel": ["-c"]}[action]
        ok, out = _run("shutdown", *flag)
        if not ok:
            return f"Couldn't: {out[:150]} (this may need admin rights)"
    return f"{action} {'scheduled' if action != 'cancel' else 'done'}."
