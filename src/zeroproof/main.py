"""ZeroProof entrypoint.

Reads /input/tasks.json, answers every task, writes /output/results.json, and
exits 0 — even on internal errors. A background watchdog guarantees a valid,
complete output file exists well before the 10-minute grader limit: results are
flushed incrementally and a final safety flush runs at the deadline.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Dict, List

from .config import Config
from .io_contract import build_results, read_tasks, validate_results, write_results
from .router import Context, build_context, route
from .types import Task
from .utils.watchdog import Deadline


def _log(msg: str) -> None:
    print(f"[zeroproof] {msg}", flush=True)


def _write_snapshot(output_path: str, tasks: List[Task], answers: Dict[str, str], fallback: str) -> None:
    results = build_results(tasks, answers, fallback)
    write_results(output_path, results)


def run(config: Config = None) -> int:  # noqa: ANN001
    config = config or Config()
    _log(config.summary())
    deadline = Deadline(config.watchdog_seconds)

    # ---- Read input (tolerant). On failure, still emit a valid empty file. ----
    try:
        tasks = read_tasks(config.input_path)
    except Exception as exc:
        _log(f"failed to read input: {exc!r}; writing empty results")
        write_results(config.output_path, [])
        return 0

    _log(f"loaded {len(tasks)} tasks")
    answers: Dict[str, str] = {}

    # Pre-seed a complete fallback file immediately (ready < 60s, output exists).
    _write_snapshot(config.output_path, tasks, answers, config.fail_open_answer)

    ctx: Context = build_context(config)
    _log(f"local model status: {ctx.llm.status if ctx.llm else 'none'} | fireworks_enabled={config.fireworks_enabled}")

    # ---- Watchdog: periodically flush progress; hard-stop near the deadline. ----
    stop_event = threading.Event()

    def _watch() -> None:
        while not stop_event.wait(5.0):
            if deadline.remaining() <= 8.0:
                _log("watchdog: approaching deadline, flushing snapshot and stopping")
                _write_snapshot(config.output_path, tasks, dict(answers), config.fail_open_answer)
                os._exit(0)  # guarantee we exit 0 before the grader kills us

    watcher = threading.Thread(target=_watch, daemon=True)
    watcher.start()

    # ---- Main loop ----
    for i, task in enumerate(tasks):
        if deadline.remaining() <= 10.0:
            _log("deadline guard: stopping task loop, remaining tasks use fallback")
            break
        # Per-task soft budget: never let one task consume the whole run.
        budget = min(config.per_task_seconds, max(2.0, (deadline.remaining() - 8.0) / max(1, len(tasks) - i)))
        ctx.task_deadline = time.monotonic() + budget
        t0 = time.monotonic()
        try:
            result = route(task, ctx)
            answers[task.task_id] = result.answer
            if config.verbose:
                _log(f"[{i+1}/{len(tasks)}] {task.task_id} <- {result.category}/{result.method} "
                     f"conf={result.confidence} verified={result.verified} ({time.monotonic()-t0:.1f}s)")
        except Exception as exc:
            _log(f"task {task.task_id} errored: {exc!r}")
            answers[task.task_id] = config.fail_open_answer

        # Incremental durability every few tasks.
        if (i + 1) % 3 == 0:
            _write_snapshot(config.output_path, tasks, answers, config.fail_open_answer)

    stop_event.set()

    # ---- Final write + validation ----
    results = build_results(tasks, answers, config.fail_open_answer)
    problems = validate_results(tasks, results)
    if problems:
        _log(f"contract validation issues (auto-corrected on write): {problems}")
    write_results(config.output_path, results)

    _log(f"done: {len(results)} results written to {config.output_path}")
    _log(f"FIREWORKS TOKENS USED: {ctx.fireworks_tokens} (target 0)")
    if ctx.llm is not None:
        _log(f"local tokens (free): in={ctx.llm.local_tokens_in} out={ctx.llm.local_tokens_out}")
    return 0


def main() -> None:
    code = 0
    try:
        code = run(Config())
    except Exception as exc:  # last-ditch: never crash the container
        _log(f"fatal error, exiting 0 with best-effort output: {exc!r}")
        code = 0
    sys.exit(code)


if __name__ == "__main__":
    main()
