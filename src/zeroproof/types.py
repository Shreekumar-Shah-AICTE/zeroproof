"""Shared data types for ZeroProof."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Task:
    task_id: str
    prompt: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    """The outcome of a solver.

    `proof` documents *why* the answer is trustworthy (executed code, a second
    method that agrees, a satisfied constraint model, etc.). `verified` is True
    only when a proof-carrying check passed; the router uses it to decide
    whether to accept a free answer or fall back / escalate.
    """

    answer: str
    category: str
    method: str
    confidence: float = 0.0
    verified: bool = False
    proof: str = ""
    fireworks_tokens: int = 0          # MUST remain 0 at evaluation.
    local_tokens: int = 0              # free; tracked only for transparency.
    meta: Dict[str, Any] = field(default_factory=dict)

    def is_usable(self) -> bool:
        return bool(self.answer and self.answer.strip())
