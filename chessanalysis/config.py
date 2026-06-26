"""Minimal .env loader (zero dependencies).

Reads KEY=VALUE lines from a .env file into a dict. Real environment variables
take precedence, so you can override any setting inline:

    CHESS_USERNAME=someoneelse python3 analyze.py
"""
from __future__ import annotations

import os


def _parse_env_file(path: str) -> dict:
    values: dict = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            val = val.strip()
            if val[:1] in ("'", '"'):                 # quoted: keep as-is inside quotes
                q = val[0]
                end = val.find(q, 1)
                val = val[1:end] if end > 0 else val[1:]
            elif "#" in val:                          # strip inline comment
                val = val.split("#", 1)[0].strip()
            values[key.strip()] = val
    return values


def load(path: str = ".env") -> dict:
    """Return config from os.environ overlaid on the .env file."""
    cfg = _parse_env_file(path)
    cfg.update({k: v for k, v in os.environ.items() if k in cfg or k.startswith("CHESS_")})
    return cfg


def get(key: str, default: str | None = None, path: str = ".env") -> str | None:
    """Look up a single key: real env var wins, then .env, then default."""
    if key in os.environ:
        return os.environ[key]
    return _parse_env_file(path).get(key, default)
