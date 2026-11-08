"""Reliable Windows desktop control through UI Automation (clicks controls by name, no screenshots needed).
Needs: pip install pywinauto"""
import ctypes
import sys

from ..registry import tool

KINDS = ("Button", "Hyperlink", "MenuItem", "TabItem", "Edit", "CheckBox", "ComboBox", "ListItem", "RadioButton")


def _active():
    if sys.platform != "win32":
        raise RuntimeError("UI Automation only works on Windows.")
    from pywinauto import Application
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    return Application(backend="uia").connect(handle=hwnd).window(handle=hwnd)


def _find(win, name, kinds=KINDS):
    name = name.lower().strip()
    best = None
    for c in win.descendants():
        try:
            label = (c.window_text() or "").strip().lower()
            if c.element_info.control_type not in kinds or not c.is_visible():
                continue
        except Exception:
            continue
        if label == name:
            return c
        if name and name in label and best is None:
            best = c
    return best


@tool("List the buttons, links, menus, tabs and text fields in the window that has focus.", {})
def ui_list_controls():
    win = _active()
    rows = []
    for c in win.descendants():
        try:
            kind, label = c.element_info.control_type, (c.window_text() or "").strip()
            if kind in KINDS and label and c.is_visible():
                rows.append(f"{kind}: {label[:60]}")
        except Exception:
            continue
        if len(rows) >= 60:
            break
    return f"Window: {win.window_text()}\n" + "\n".join(rows)


@tool("Click a control in the focused window by its visible name (e.g. 'Save', 'File', 'Send').",
      {"name": ("string", "Control name or part of it")}, risk="ask")
def ui_click(name):
    c = _find(_active(), name)
    if not c:
        return f"No control named '{name}'. Try ui_list_controls first."
    try:
        c.invoke()
    except Exception:
        c.click_input()
    return f"Clicked '{c.window_text()}'."


@tool("Type text into a text field of the focused window, found by name (empty name = first text field).",
      {"name": ("string", "Field name, or empty"), "text": ("string", "Text to enter")}, required=["text"], risk="ask")
def ui_type(text, name=""):
    win = _active()
    c = _find(win, name, ("Edit",)) if name else next(
        (e for e in win.descendants(control_type="Edit") if e.is_visible()), None)
    if not c:
        return "No matching text field."
    try:
        c.set_edit_text(text)
    except Exception:
        c.click_input()
        c.type_keys(text, with_spaces=True)
    return "Typed."
