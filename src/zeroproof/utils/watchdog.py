"""Run-level and task-level time guards.

The grader kills the container at 10 minutes. We keep a global deadline
(default 9m30s) and a per-task cap so a single pathological task can never
sink the whole run. `Deadline.remaining()` lets solvers shrink their own
budgets as the run progresses.
"""
from __future__ import annotations

import signal
import time
from contextlib import contextmanager
from typing import Iterator


class Deadline:
    def __init__(self, total_seconds: float):
        self.start = time.monotonic()
        self.total = total_seconds

    def elapsed(self) -> float:
        return time.monotonic() - self.start

    def remaining(self) -> float:
        return max(0.0, self.total - self.elapsed())

    def expired(self) -> bool:
        return self.remaining() <= 0.0


class TaskTimeout(Exception):
    pass


@contextmanager
def time_limit(seconds: float) -> Iterator[None]:
    """SIGALRM-based hard cap for a block of work (main thread only).

    Falls back to a no-op if signals are unavailable (e.g. worker threads),
    in which case callers rely on their own softer budgeting.
    """
    seconds = max(1, int(seconds))

    def _handler(signum, frame):  # noqa: ANN001
        raise TaskTimeout(f"task exceeded {seconds}s")

    have_alarm = hasattr(signal, "SIGALRM")
    previous = None
    if have_alarm:
        try:
            previous = signal.signal(signal.SIGALRM, _handler)
            signal.setitimer(signal.ITIMER_REAL, seconds)
        except (ValueError, OSError):
            have_alarm = False
    try:
        yield
    finally:
        if have_alarm:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if previous is not None:
                signal.signal(signal.SIGALRM, previous)
