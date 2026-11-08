"""File system tools. Destructive ones ask for approval and refuse protected locations."""
import os
import shutil
import time
from pathlib import Path

from .. import config, safety
from ..registry import tool

S = config.SETTINGS
KNOWN = {"desktop": "Desktop", "downloads": "Downloads", "documents": "Documents",
         "pictures": "Pictures", "music": "Music", "videos": "Videos"}
SKIP_DIRS = {"node_modules", ".git", "appdata", "windows", "program files", "program files (x86)",
             "$recycle.bin", "system volume information", "__pycache__", ".venv", "venv", "site-packages"}


def resolve(p) -> Path:
    p = (p or "").strip().strip('"')
    if not p:
        return S.workspace
    norm = p.replace("\\", "/")
    first, _, rest = norm.partition("/")
    if first.lower() in KNOWN:
        folder = KNOWN[first.lower()]
        for base in (Path.home() / folder, Path.home() / "OneDrive" / folder):
            if base.exists():
                return base / rest
        return Path.home() / folder / rest
    path = Path(os.path.expandvars(os.path.expanduser(p)))
    return path if path.is_absolute() else S.workspace / path


def _guard(path: Path):
    if safety.is_protected(path):
        raise PermissionError(f"{path} is a protected location.")


@tool("List files and folders in a directory. Accepts 'desktop', 'downloads', 'documents' or a path.",
      {"path": ("string", "Directory path or well-known folder name")}, required=[])
def list_directory(path=""):
    d = resolve(path)
    if not d.is_dir():
        return f"{d} is not a folder."
    rows = []
    for e in sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:100]:
        try:
            rows.append(f"[D] {e.name}" if e.is_dir() else f"[F] {e.name} ({e.stat().st_size // 1024} KB)")
        except OSError:
            continue
    return f"{d}\n" + "\n".join(rows) if rows else f"{d} is empty."


@tool("Read a text file.", {"path": ("string", "File path"), "max_chars": ("integer", "Limit, default 8000")},
      required=["path"])
def read_file(path, max_chars=8000):
    f = resolve(path)
    if not f.is_file():
        return f"No such file: {f}"
    try:
        return f.read_text(encoding="utf-8", errors="strict")[: int(max_chars)]
    except UnicodeDecodeError:
        return "That looks like a binary file; I can only read text files."


@tool("Find files by name (all words must appear in the file name).",
      {"query": ("string", "Words from the file name"), "root": ("string", "Folder to search, default home"),
       "max_results": ("integer", "Default 15")}, required=["query"])
def search_files(query, root="", max_results=15):
    base = resolve(root) if root else Path.home()
    words = query.lower().split()
    out, deadline = [], time.time() + 20
    for dirpath, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith(".")]
        for n in files + dirs:
            if all(w in n.lower() for w in words):
                out.append(os.path.join(dirpath, n))
                if len(out) >= int(max_results):
                    return "\n".join(out)
        if time.time() > deadline:
            out.append("(search timed out, results may be incomplete)")
            break
    return "\n".join(out) or "No matches."


@tool("Search inside text files for a phrase.",
      {"text": ("string", "Phrase to find"), "root": ("string", "Folder to search"),
       "extensions": ("string", "Comma list like 'py,md,txt' (default py,md,txt,js,ts,json)")}, required=["text"])
def search_in_files(text, root="", extensions="py,md,txt,js,ts,json"):
    base = resolve(root) if root else S.workspace
    exts = tuple("." + e.strip().lstrip(".") for e in extensions.split(","))
    hits, deadline = [], time.time() + 25
    for dirpath, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith(".")]
        for n in files:
            if n.lower().endswith(exts):
                fp = os.path.join(dirpath, n)
                try:
                    for i, line in enumerate(open(fp, encoding="utf-8", errors="ignore"), 1):
                        if text.lower() in line.lower():
                            hits.append(f"{fp}:{i}: {line.strip()[:120]}")
                            break
                except OSError:
                    continue
        if len(hits) >= 20 or time.time() > deadline:
            break
    return "\n".join(hits) or "No matches."


@tool("Open a file or folder with its default program.", {"path": ("string", "Path")})
def open_path(path):
    p = resolve(path)
    if not p.exists():
        return f"No such path: {p}"
    if os.name == "nt":
        os.startfile(str(p))
    else:
        import subprocess
        subprocess.Popen(["open" if os.uname().sysname == "Darwin" else "xdg-open", str(p)])
    return f"Opened {p}"


@tool("Create a folder.", {"path": ("string", "Folder path")})
def create_folder(path):
    p = resolve(path)
    _guard(p)
    p.mkdir(parents=True, exist_ok=True)
    return f"Created {p}"


@tool("Write or append text to a file (creates it if needed).",
      {"path": ("string", "File path"), "content": ("string", "Text"), "append": ("boolean", "Append instead of overwrite")},
      required=["path", "content"], risk="ask")
def write_file(path, content, append=False):
    p = resolve(path)
    _guard(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a" if append else "w", encoding="utf-8") as f:
        f.write(content)
    return f"Wrote {len(content)} characters to {p}"


@tool("Move or rename a file or folder.", {"source": ("string", "From"), "destination": ("string", "To")}, risk="ask")
def move_path(source, destination):
    s, d = resolve(source), resolve(destination)
    _guard(s)
    _guard(d)
    shutil.move(str(s), str(d))
    return f"Moved {s} to {d}"


@tool("Delete a file or folder (sent to the Recycle Bin).", {"path": ("string", "Path")}, risk="ask")
def delete_path(path):
    from send2trash import send2trash
    p = resolve(path)
    _guard(p)
    if not p.exists():
        return f"No such path: {p}"
    send2trash(str(p))
    return f"Moved {p} to the Recycle Bin."
