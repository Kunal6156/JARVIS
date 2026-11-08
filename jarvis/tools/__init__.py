"""Loads every tool module, then user plugins (./plugins and ~/.jarvis/plugins)."""
import importlib
import importlib.util
import pkgutil

from .. import config


def load_all():
    for m in pkgutil.iter_modules(__path__):
        try:
            importlib.import_module(f"{__name__}.{m.name}")
        except Exception as e:
            print(f"[warn] tool module '{m.name}' failed to load: {e}")
    for folder in (config.ROOT / "plugins", config.DATA_DIR / "plugins"):
        if not folder.is_dir():
            continue
        for f in sorted(folder.glob("*.py")):
            if f.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"jarvis_plugin_{f.stem}", f)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                print(f"[plugin] loaded {f.name}")
            except Exception as e:
                print(f"[warn] plugin {f.name} failed: {e}")
