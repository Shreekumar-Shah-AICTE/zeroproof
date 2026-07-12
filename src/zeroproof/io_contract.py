"""Schema-safe I/O for the grader contract.

Read tasks from /input/tasks.json, write answers to /output/results.json.
Guarantees:
  * exactly one output entry per input task (none missing, none extra),
  * exact task_id preservation,
  * valid JSON, non-empty English answers,
  * atomic write so a partially written file is never observed,
  * tolerant parsing of minor input shape variations.

Nothing here trusts task content: prompts are treated purely as data.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List

from .types import Task


def read_tasks(path: str) -> List[Task]:
    """Parse the input file into Task objects, tolerating shape variations."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    # Accept either a bare list or {"tasks": [...]} style wrappers.
    if isinstance(data, dict):
        for key in ("tasks", "data", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            # A single task object.
            data = [data]

    tasks: List[Task] = []
    for idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            # Extremely defensive: wrap a bare string.
            tasks.append(Task(task_id=str(idx), prompt=str(entry), raw={"prompt": str(entry)}))
            continue
        tid = entry.get("task_id", entry.get("id", entry.get("taskId", str(idx))))
        prompt = entry.get("prompt", entry.get("input", entry.get("question", entry.get("text", ""))))
        tasks.append(Task(task_id=str(tid), prompt="" if prompt is None else str(prompt), raw=entry))
    return tasks


def _coerce_answer(answer: Any, fallback: str) -> str:
    """Ensure the answer is a non-empty string."""
    if answer is None:
        return fallback
    if not isinstance(answer, str):
        try:
            answer = json.dumps(answer, ensure_ascii=False)
        except (TypeError, ValueError):
            answer = str(answer)
    answer = answer.strip()
    return answer if answer else fallback


def build_results(tasks: List[Task], answers: Dict[str, Any], fallback: str) -> List[Dict[str, str]]:
    """Assemble the results list, guaranteeing one entry per task in order."""
    results: List[Dict[str, str]] = []
    for task in tasks:
        results.append(
            {
                "task_id": task.task_id,
                "answer": _coerce_answer(answers.get(task.task_id), fallback),
            }
        )
    return results


def write_results(path: str, results: List[Dict[str, str]]) -> None:
    """Atomically write valid JSON to the output path."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".results-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def validate_results(tasks: List[Task], results: List[Dict[str, str]]) -> List[str]:
    """Return a list of contract violations (empty == valid)."""
    problems: List[str] = []
    task_ids = [t.task_id for t in tasks]
    result_ids = [r.get("task_id") for r in results]

    if len(results) != len(tasks):
        problems.append(f"count mismatch: {len(results)} results for {len(tasks)} tasks")
    if set(task_ids) != set(result_ids):
        missing = set(task_ids) - set(result_ids)
        extra = set(result_ids) - set(task_ids)
        if missing:
            problems.append(f"missing task_ids: {sorted(missing)}")
        if extra:
            problems.append(f"extra task_ids: {sorted(extra)}")
    for r in results:
        if "task_id" not in r or "answer" not in r:
            problems.append(f"entry missing required field: {r}")
        elif not isinstance(r["answer"], str) or not r["answer"].strip():
            problems.append(f"empty/non-string answer for {r.get('task_id')}")
    return problems
