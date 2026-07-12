"""Central configuration for ZeroProof.

All tunables live here and are overridable via environment variables so the
image behaves identically in dev and under the grader without code changes.

Ground-truth grading constraints (see PROJECT.md §3):
  * CPU-only, 2 vCPU, 4 GB RAM.
  * Total container runtime <= 10 min  -> internal watchdog at 9m30s.
  * Container ready < 60 s.
  * Each task < 30 s              -> internal per-task cap ~28s, remote ~25s.
  * Image linux/amd64, <= 5 GB.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip())
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip())
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    # ---- I/O contract ----
    input_path: str = field(default_factory=lambda: os.environ.get("ZP_INPUT", "/input/tasks.json"))
    output_path: str = field(default_factory=lambda: os.environ.get("ZP_OUTPUT", "/output/results.json"))

    # ---- Timing (all seconds) ----
    watchdog_seconds: float = field(default_factory=lambda: _env_float("ZP_WATCHDOG_SECONDS", 570.0))
    per_task_seconds: float = field(default_factory=lambda: _env_float("ZP_PER_TASK_SECONDS", 28.0))
    remote_timeout_seconds: float = field(default_factory=lambda: _env_float("ZP_REMOTE_TIMEOUT", 25.0))
    code_exec_timeout: float = field(default_factory=lambda: _env_float("ZP_CODE_EXEC_TIMEOUT", 5.0))

    # ---- Local model (GGUF via llama.cpp) ----
    model_path: str = field(default_factory=lambda: os.environ.get("ZP_MODEL_PATH", "/models/model.gguf"))
    n_threads: int = field(default_factory=lambda: _env_int("ZP_N_THREADS", 2))
    n_ctx: int = field(default_factory=lambda: _env_int("ZP_N_CTX", 4096))
    n_batch: int = field(default_factory=lambda: _env_int("ZP_N_BATCH", 256))
    llm_max_tokens: int = field(default_factory=lambda: _env_int("ZP_LLM_MAX_TOKENS", 512))
    self_consistency_samples: int = field(default_factory=lambda: _env_int("ZP_SC_SAMPLES", 3))
    seed: int = field(default_factory=lambda: _env_int("ZP_SEED", 1234))

    # ---- Fireworks valve (default HARD-OFF; see fireworks_valve.py) ----
    # This exists ONLY as a documented, audit-safe insurance lever. It is never
    # enabled at evaluation by default. Turning it on is a single explicit switch.
    fireworks_enabled: bool = field(default_factory=lambda: _env_bool("ZP_FIREWORKS_ENABLED", False))
    # When (and only when) the valve is on, it is restricted to this category set.
    fireworks_allowed_categories: List[str] = field(
        default_factory=lambda: [c for c in os.environ.get("ZP_FIREWORKS_CATEGORIES", "factual_knowledge").split(",") if c]
    )

    # ---- Behaviour ----
    verbose: bool = field(default_factory=lambda: _env_bool("ZP_VERBOSE", False))
    # Hard guarantee: never let a single task sink the whole run.
    fail_open_answer: str = "Unable to determine a confident answer for this task."

    def summary(self) -> str:
        return (
            f"ZeroProof config: input={self.input_path} output={self.output_path} "
            f"watchdog={self.watchdog_seconds}s per_task={self.per_task_seconds}s "
            f"model={self.model_path} fireworks_enabled={self.fireworks_enabled}"
        )


# A module-level singleton is convenient; callers may also construct their own.
CONFIG = Config()
