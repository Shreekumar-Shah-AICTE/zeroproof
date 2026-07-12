"""Constraint simulator — enforces the grader's runtime envelope and fails loudly.

Grader envelope: 2 vCPU / 4 GB RAM / <=10 min total / <60 s ready / <30 s per task.
This module measures what is observable in-process (per-task latency, total
runtime, peak RSS) and flags any breach. Hardware caps (2 vCPU, 4 GB, image size)
are enforced at run time via `docker run --cpus 2 --memory 4g` and at build time
via the image size check — both documented in the RUNBOOK and asserted here as
thresholds so a regression is caught early.
"""
from __future__ import annotations

import resource
from dataclasses import dataclass, field
from typing import List, Tuple

# Thresholds tuned below the hard grader limits for safety margin.
MAX_PER_TASK_S = 28.0
MAX_TOTAL_S = 570.0
MAX_READY_S = 55.0
MAX_RSS_MB = 3900.0


@dataclass
class ConstraintReport:
    per_task_s: List[Tuple[str, float]] = field(default_factory=list)
    total_s: float = 0.0
    ready_s: float = 0.0
    peak_rss_mb: float = 0.0
    violations: List[str] = field(default_factory=list)

    def finalize(self) -> "ConstraintReport":
        self.peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
        slowest = sorted(self.per_task_s, key=lambda x: x[1], reverse=True)[:3]
        for tid, dt in self.per_task_s:
            if dt > MAX_PER_TASK_S:
                self.violations.append(f"task {tid} took {dt:.1f}s > {MAX_PER_TASK_S}s")
        if self.total_s > MAX_TOTAL_S:
            self.violations.append(f"total {self.total_s:.1f}s > {MAX_TOTAL_S}s")
        if self.ready_s > MAX_READY_S:
            self.violations.append(f"ready {self.ready_s:.1f}s > {MAX_READY_S}s")
        if self.peak_rss_mb > MAX_RSS_MB:
            self.violations.append(f"peak RSS {self.peak_rss_mb:.0f}MB > {MAX_RSS_MB}MB")
        self.slowest = slowest
        return self

    @property
    def passed(self) -> bool:
        return not self.violations

    def render(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        slow = ", ".join(f"{t}={d:.2f}s" for t, d in getattr(self, "slowest", [])[:3])
        lines = [
            f"Constraint simulator: {status}",
            f"  ready={self.ready_s:.2f}s  total={self.total_s:.2f}s  peak_rss={self.peak_rss_mb:.0f}MB",
            f"  slowest tasks: {slow}",
        ]
        for v in self.violations:
            lines.append(f"  VIOLATION: {v}")
        return "\n".join(lines)
