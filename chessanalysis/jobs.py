"""Background jobs: one worker thread per named job, a snapshot to poll.

The web app has long-running work that must not block a request — analysing
every game at review depth, growing the rating corpus — and the browser polls
for progress. Each used to carry its own thread, lock and status dict; this is
that pattern written once.

A job belongs to a `key` (the account it works for). Starting a job that is
already running for the same key just reports on it. Starting it for a
different key asks the running one to stop after its current step — a worker
checks `job.stopping` between units of work — and the caller asks again once
it has.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

_LOCK = threading.Lock()
_JOBS: dict[str, "Job"] = {}


class Job:
    def __init__(self, name: str):
        self.name = name
        self.key = None
        self.want = None             # the key the app currently wants served
        self.running = False
        self.finished = False
        self.error = None
        self.start = 0.0
        self.progress: dict = {}

    # --- called from the worker ------------------------------------------------
    def update(self, **fields) -> None:
        with _LOCK:
            self.progress.update(fields)

    def step(self, field: str = "done", by: int = 1) -> None:
        with _LOCK:
            self.progress[field] = self.progress.get(field, 0) + by

    @property
    def stopping(self) -> bool:
        """True once the app has moved on to another key."""
        with _LOCK:
            return self.want != self.key

    # --- read by the app -------------------------------------------------------
    def snapshot(self) -> dict:
        with _LOCK:
            return {"name": self.name, "key": self.key, "running": self.running,
                    "finished": self.finished, "error": self.error,
                    "elapsed": round(time.time() - self.start) if self.start else 0,
                    **self.progress}


def get(name: str) -> Job:
    with _LOCK:
        if name not in _JOBS:
            _JOBS[name] = Job(name)
        return _JOBS[name]


def start(name: str, key, fn: Callable, *args, initial: dict | None = None) -> dict:
    """Run `fn(job, *args)` in the background for `key`, unless already running.

    Returns the job's snapshot either way. A job running for another key is
    asked to stop; the caller sees `running` with the old key and retries.
    """
    job = get(name)
    with _LOCK:
        job.want = key
        if job.running:
            pass
        else:
            job.key, job.running, job.finished, job.error = key, True, False, None
            job.start, job.progress = time.time(), dict(initial or {})
            threading.Thread(target=_run, args=(job, fn, args), daemon=True).start()
    return job.snapshot()


def _run(job: Job, fn: Callable, args) -> None:
    try:
        fn(job, *args)
    except Exception as e:                       # noqa: BLE001 — surfaced to the UI
        with _LOCK:
            job.error = f"{type(e).__name__}: {e}"
    finally:
        with _LOCK:
            job.running = False
            job.finished = True


def wait(name: str, timeout: float = 30.0) -> dict:
    """Block until a job finishes (tests and the CLI)."""
    end = time.time() + timeout
    job = get(name)
    while time.time() < end:
        with _LOCK:
            if not job.running:
                break
        time.sleep(0.02)
    return job.snapshot()
