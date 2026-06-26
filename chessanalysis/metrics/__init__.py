"""Auto-discover every metric module (recursively) so they self-register.

Layout is by scope — metrics/player/, metrics/game/, metrics/compare/ — but
discovery is recursive, so nesting is just organization. Drop a file anywhere
under here with an @metric(...) function and it's picked up.
"""
import importlib
import pkgutil

for _info in pkgutil.walk_packages(__path__, prefix=f"{__name__}."):
    if not _info.name.rsplit(".", 1)[-1].startswith("_"):
        importlib.import_module(_info.name)
