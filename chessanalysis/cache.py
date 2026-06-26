"""Tiny JSON disk cache for expensive computations (engine analysis)."""
from __future__ import annotations

import json
import os

CACHE_DIR = os.path.join("data", "cache")


def _path(namespace: str, key: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in str(key))
    return os.path.join(CACHE_DIR, namespace, f"{safe}.json")


def load(namespace: str, key: str) -> dict | None:
    path = _path(namespace, key)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def save(namespace: str, key: str, data: dict) -> None:
    path = _path(namespace, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
