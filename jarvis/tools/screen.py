"""Screen vision + mouse control, tuned for speed and for small local vision models:
window-only capture, adaptive image size, short-lived answer cache, two-pass pointing, and a UI-Automation
shortcut that clicks named controls without any vision call. Slam the mouse into the top-left corner to abort."""
import hashlib
import io
import json
import re
import sys
import time

from .. import config, llm
from ..registry import tool

S = config.SETTINGS
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # make screenshot pixels match mouse pixels
    except Exception:
        pass

_cache = {}
STOP = {"the", "a", "an", "button", "icon", "link", "tab", "menu", "item", "field", "box", "blue", "red", "green",
        "big", "small", "top", "bottom", "left", "right", "on", "in", "of", "to", "please", "click", "press"}


def _width():
    return S.vision_width or (1024 if S.provider == "ollama" else 1280)


def _refine():
    return config.env("JARVIS_VISION_REFINE", "1" if S.provider == "ollama" else "0") == "1"


def _foreground_bbox():
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    u, r = ctypes.windll.user32, wintypes.RECT()
    h = u.GetForegroundWindow()
    if not h or not u.GetWindowRect(h, ctypes.byref(r)):
        return None
    left, top = max(r.left, 0), max(r.top, 0)  # maximised windows report negative offsets
    w, hh = r.right - left, r.bottom - top
    return {"left": left, "top": top, "width": w, "height": hh} if w > 50 and hh > 50 else None


def _grab(bbox=None, max_w=None):
    import mss
    from PIL import Image
    max_w = max_w or _width()
    with mss.mss() as sct:
        box = bbox or sct.monitors[1]
        shot = sct.grab(box)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        screen = sct.monitors[1]
    scale = 1.0
    if img.width > max_w:
        scale = max_w / img.width
        img = img.resize((max_w, int(img.height * scale)))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue(), scale, (box["left"], box["top"]), img.size, (screen["width"], screen["height"])


def _vision_risk(args):
    return "safe" if S.provider == "ollama" else "ask"  # cloud = the screenshot leaves the PC


@tool("Take a full-resolution screenshot and save it to a file.", {})
def take_screenshot():
    import mss
    out = config.DATA_DIR / "shots"
    out.mkdir(exist_ok=True)
    path = out / f"shot_{time.strftime('%Y%m%d_%H%M%S')}.png"
    with mss.mss() as sct:
        sct.shot(mon=1, output=str(path))
    return str(path)


@tool("Look at the screen and answer a question about it (read text, describe what's open, find errors). "
      "target 'window' looks only at the focused window: faster and more accurate.",
      {"question": ("string", "What to look for"), "target": ("string", "screen or window", ["screen", "window"])},
      required=[], risk=_vision_risk)
def look_at_screen(question="Describe what is on the screen.", target="screen"):
    png, *_ = _grab(_foreground_bbox() if target == "window" else None)
    key = hashlib.sha1(png).hexdigest() + question
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 15:
        return hit[1]
    answer = llm.get().vision(question, png)
    _cache[key] = (time.time(), answer)
    return answer


def _ask_point(png, w, h, description):
    q = (f"This image is {w}x{h} pixels. Find: {description}. Reply with ONLY JSON: "
         '{"found": true, "x": <int>, "y": <int>} giving the centre of the element in this image\'s '
         'pixel coordinates, or {"found": false}.')
    m = re.search(r"\{.*?\}", llm.get().vision(q, png), re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        return None
    if not d.get("found"):
        return None
    return min(max(int(d["x"]), 0), w), min(max(int(d["y"]), 0), h)


def _locate(description):
    png, scale, (ox, oy), (w, h), (sw, sh) = _grab()
    pos = _ask_point(png, w, h, description)
    if not pos:
        return None
    rx, ry = int(ox + pos[0] / scale), int(oy + pos[1] / scale)
    if _refine():  # second look at a 480px crop around the guess: much more precise for small models
        box = {"left": min(max(rx - 240, 0), max(sw - 480, 0)), "top": min(max(ry - 240, 0), max(sh - 480, 0)),
               "width": min(480, sw), "height": min(480, sh)}
        png2, s2, (ox2, oy2), (w2, h2), _ = _grab(box, max_w=480)
        p2 = _ask_point(png2, w2, h2, description + " (it should be near the middle of this crop)")
        if p2:
            return int(ox2 + p2[0] / s2), int(oy2 + p2[1] / s2)
    return rx, ry


@tool("Find a UI element on screen by description and return its screen coordinates.",
      {"description": ("string", "e.g. 'the blue Send button'")}, risk=_vision_risk)
def locate_on_screen(description):
    pos = _locate(description)
    return f"Found at x={pos[0]}, y={pos[1]}" if pos else "Not found on screen."


def _uia_click(description):
    """Fast path: click a control by its accessible name, no vision call. Windows only."""
    if sys.platform != "win32":
        return None
    try:
        from .uia import _active, _find
        win = _active()
        words = [w for w in re.findall(r"\w+", description.lower()) if w not in STOP]
        for cand in dict.fromkeys([" ".join(words), *sorted(words, key=len, reverse=True)]):
            if len(cand) < 3:
                continue
            c = _find(win, cand)
            if c:
                try:
                    c.invoke()
                except Exception:
                    c.click_input()
                return c.window_text()
    except Exception:
        pass
    return None


@tool("Find a UI element by description and click it. Tries the window's named controls first (instant), "
      "then falls back to screen vision.",
      {"description": ("string", "e.g. 'the Send button'"), "double": ("boolean", "Double click")},
      required=["description"], risk="ask")
def click_element(description, double=False):
    import pyautogui
    name = _uia_click(description)
    if name:
        return f"Clicked '{name}' (found by name, no vision needed)."
    pos = _locate(description)
    if not pos:
        return f"Couldn't find '{description}' on screen."
    pyautogui.click(*pos, clicks=2 if double else 1)
    return f"Clicked '{description}' at {pos}."


@tool("Click at exact screen coordinates.",
      {"x": ("integer", "X pixel"), "y": ("integer", "Y pixel"),
       "button": ("string", "left or right", ["left", "right"])}, required=["x", "y"], risk="ask")
def click_screen(x, y, button="left"):
    import pyautogui
    pyautogui.click(int(x), int(y), button=button)
    return f"Clicked ({x}, {y})."


@tool("Scroll the mouse wheel (positive = up, negative = down).", {"amount": ("integer", "Clicks, e.g. -5")})
def scroll_screen(amount):
    import pyautogui
    pyautogui.scroll(int(amount) * 100)
    return "Scrolled."
