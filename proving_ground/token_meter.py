"""Token meter — proves the agent spends ZERO Fireworks tokens.

Reads the accumulated Fireworks token counter off the agent's context (populated
only if the default-OFF valve is ever used) and reports pass/fail. The winning
path must always read exactly 0.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TokenReport:
    fireworks_tokens: int
    local_tokens_in: int
    local_tokens_out: int

    @property
    def passed(self) -> bool:
        return self.fireworks_tokens == 0

    def render(self) -> str:
        status = "PASS (0 tokens)" if self.passed else f"FAIL ({self.fireworks_tokens} tokens)"
        return (f"Token meter: {status} | "
                f"local(free): in={self.local_tokens_in} out={self.local_tokens_out}")


def measure(ctx) -> TokenReport:  # noqa: ANN001
    fw = getattr(ctx, "fireworks_tokens", 0)
    llm = getattr(ctx, "llm", None)
    ti = getattr(llm, "local_tokens_in", 0) if llm else 0
    to = getattr(llm, "local_tokens_out", 0) if llm else 0
    return TokenReport(fireworks_tokens=fw, local_tokens_in=ti, local_tokens_out=to)
