"""Browser control via Playwright. One dedicated worker thread owns the browser, so it is safe to call
from the agent thread and from background routines. Uses its own persistent profile, so logins stay."""
import concurrent.futures as cf
import re
from urllib.parse import quote_plus

from .. import config
from ..registry import tool

_pool = cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser")
_st = {"pw": None, "ctx": None}
RISKY = re.compile(r"\b(buy|purchase|pay|order|checkout|check out|place order|delete|remove|send|submit|"
                   r"confirm|post|publish|transfer|subscribe|unsubscribe|sign out|log out)\b", re.I)


def _page():
    if _st["ctx"] is None:
        from playwright.sync_api import sync_playwright
        _st["pw"] = sync_playwright().start()
        profile = str(config.DATA_DIR / "browser_profile")
        kw = dict(headless=config.SETTINGS.browser_headless, viewport={"width": 1280, "height": 800})
        try:
            _st["ctx"] = _st["pw"].chromium.launch_persistent_context(profile, channel="chrome", **kw)
        except Exception:
            _st["ctx"] = _st["pw"].chromium.launch_persistent_context(profile, **kw)
    ctx = _st["ctx"]
    pages = [p for p in ctx.pages if not p.is_closed()]
    page = pages[-1] if pages else ctx.new_page()
    page.bring_to_front()
    return page


def _reset():
    try:
        if _st["ctx"]:
            _st["ctx"].close()
        if _st["pw"]:
            _st["pw"].stop()
    except Exception:
        pass
    _st["ctx"] = _st["pw"] = None


def _do(fn):
    def job():
        return fn(_page())
    try:
        return _pool.submit(job).result(timeout=120)
    except Exception as e:
        msg = str(e)
        if any(k in msg.lower() for k in ("closed", "target", "disconnected")):
            _pool.submit(_reset).result()
        if "Executable doesn't exist" in msg or "playwright install" in msg:
            return "Run once in your terminal: playwright install chromium"
        return f"Browser error: {msg[:300]}"


def _text(page, n=3500):
    try:
        body = page.inner_text("body")
    except Exception:
        body = ""
    return f"{page.title()} ({page.url})\n{re.sub(chr(10) + '{3,}', chr(10) * 2, body)[:n]}"


@tool("Open a URL in the browser.", {"url": ("string", "Web address")})
def browser_open(url):
    if not re.match(r"^\w+://", url):
        url = "https://" + url

    def f(p):
        p.goto(url, wait_until="domcontentloaded", timeout=30000)
        return f"Opened {p.title()} ({p.url})"
    return _do(f)


@tool("Search the web in the browser and return the visible results.",
      {"query": ("string", "Search words"), "engine": ("string", "google, duckduckgo, youtube or bing",
                                                      ["google", "duckduckgo", "youtube", "bing"])},
      required=["query"])
def browser_search(query, engine="google"):
    urls = {"google": "https://www.google.com/search?q=", "duckduckgo": "https://duckduckgo.com/?q=",
            "youtube": "https://www.youtube.com/results?search_query=", "bing": "https://www.bing.com/search?q="}
    url = urls.get(engine, urls["google"]) + quote_plus(query)

    def f(p):
        p.goto(url, wait_until="domcontentloaded", timeout=30000)
        p.wait_for_timeout(1200)
        return _text(p)
    return _do(f)


@tool("Play the first YouTube result for a search.", {"query": ("string", "What to play")})
def youtube_play(query):
    def f(p):
        p.goto("https://www.youtube.com/results?search_query=" + quote_plus(query),
               wait_until="domcontentloaded", timeout=30000)
        p.wait_for_selector("ytd-video-renderer a#video-title", timeout=15000)
        title = p.locator("ytd-video-renderer a#video-title").first.get_attribute("title") or ""
        p.locator("ytd-video-renderer a#video-title").first.click()
        return f"Playing: {title}"
    return _do(f)


@tool("Read the visible text of the current page.", {"max_chars": ("integer", "Default 3500")}, required=[])
def browser_read(max_chars=3500):
    return _do(lambda p: _text(p, int(max_chars)))


@tool("List the visible links on the current page.", {})
def browser_links():
    def f(p):
        rows = p.eval_on_selector_all(
            "a[href]", "els=>els.filter(e=>e.offsetParent!==null).slice(0,40)"
            ".map(e=>[(e.innerText||e.getAttribute('aria-label')||'').trim().slice(0,70), e.href])")
        return "\n".join(f"{t or '(no text)'} -> {h}" for t, h in rows) or "No links."
    return _do(f)


def _click_risk(args):
    return "ask" if RISKY.search(str(args.get("target", ""))) else "safe"


@tool("Click something on the page by its visible text (or a CSS selector).",
      {"target": ("string", "Visible text or CSS selector")}, risk=_click_risk)
def browser_click(target):
    def f(p):
        for attempt in (lambda: p.get_by_role("button", name=re.compile(re.escape(target), re.I)).first,
                        lambda: p.get_by_role("link", name=re.compile(re.escape(target), re.I)).first,
                        lambda: p.get_by_text(target, exact=False).first,
                        lambda: p.locator(target).first):
            try:
                attempt().click(timeout=4000)
                break
            except Exception:
                continue
        else:
            return f"Couldn't find '{target}' on the page."
        try:
            p.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        return f"Clicked '{target}'. Now on: {p.title()} ({p.url})"
    return _do(f)


def _type_risk(args):
    return "ask" if args.get("submit") else "safe"


@tool("Type into a field (found by label, placeholder or selector). submit=true presses Enter afterwards.",
      {"field": ("string", "Label, placeholder or CSS selector"), "text": ("string", "Text to type"),
       "submit": ("boolean", "Press Enter afterwards")}, required=["field", "text"], risk=_type_risk)
def browser_type(field, text, submit=False):
    def f(p):
        loc = None
        for make in (lambda: p.get_by_label(field), lambda: p.get_by_placeholder(field),
                     lambda: p.get_by_role("searchbox", name=re.compile(re.escape(field), re.I)),
                     lambda: p.get_by_role("textbox", name=re.compile(re.escape(field), re.I)),
                     lambda: p.locator(field)):
            try:
                cand = make().first
                cand.wait_for(timeout=2500)
                loc = cand
                break
            except Exception:
                continue
        if loc is None:
            return f"Couldn't find a field matching '{field}'."
        loc.fill(text)
        if submit:
            loc.press("Enter")
            p.wait_for_timeout(1000)
        return "Typed" + (" and submitted." if submit else ".")
    return _do(f)


@tool("Press a key on the page (Enter, Escape, Tab, ArrowDown, PageDown...).", {"key": ("string", "Key name")})
def browser_press(key):
    return _do(lambda p: (p.keyboard.press(key), f"Pressed {key}")[1])


@tool("Scroll the page.", {"direction": ("string", "up or down", ["up", "down"])})
def browser_scroll(direction="down"):
    return _do(lambda p: (p.mouse.wheel(0, 700 if direction == "down" else -700), "Scrolled.")[1])


@tool("Go back to the previous page.", {})
def browser_back():
    return _do(lambda p: (p.go_back(), f"Back at {p.title()}")[1])


@tool("Close the browser.", {})
def browser_close():
    _pool.submit(_reset).result()
    return "Browser closed."
