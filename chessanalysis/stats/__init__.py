"""Auto-discover every stat module in this package so they self-register.

Just dropping a new `.py` file here is enough — no import list to maintain.
"""
import importlib
import pkgutil

for _m in pkgutil.iter_modules(__path__):
    if not _m.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_m.name}")
