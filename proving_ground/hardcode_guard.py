"""Hardcode guard — proves the agent generalizes, not memorizes.

Two checks:
  1. **Canary scan** — none of the public sample prompts/answers appear as string
     literals in the agent source (memorizing the public set is a DQ risk and
     collapses on the refresh).
  2. **Lookup-table scan** — no large dict literal maps prompt-like text to
     answers (the classic "cached answers" anti-pattern).

Gazetteers (org/location name sets, sentiment lexicons) are legitimate linguistic
resources, not answer caches, and are whitelisted by path/shape.
"""
from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from typing import List

# Canary substrings from the PUBLIC sample set — must never be embedded as answers.
_CANARIES = [
    "1,672", "1672 units", "Sam owns the cat", "Canberra", "Lake Burley Griffin",
    "additive color mixing", "mitochondria is the powerhouse",
]
# Files whose set-literals are legitimate resources, not answer lookups.
_WHITELIST_SUBSTR = ("ner_solver.py", "sentiment_solver.py", "summarization_solver.py", "classifier.py")


@dataclass
class GuardReport:
    scanned_files: int = 0
    findings: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.findings

    def render(self) -> str:
        status = "CLEAN" if self.passed else "FLAGGED"
        lines = [f"Hardcode guard: {status} ({self.scanned_files} files scanned)"]
        for f in self.findings:
            lines.append(f"  FINDING: {f}")
        return "\n".join(lines)


def _scan_dict_literals(path: str, source: str) -> List[str]:
    findings: List[str] = []
    if any(w in path for w in _WHITELIST_SUBSTR):
        return findings
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return findings
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict) and len(node.keys) >= 8:
            str_pairs = sum(
                1 for k, v in zip(node.keys, node.values)
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
                and isinstance(v, ast.Constant) and isinstance(v.value, str)
            )
            # A large str->str dict where keys look like sentences/questions.
            if str_pairs >= 8:
                longish_keys = sum(
                    1 for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str) and len(k.value.split()) >= 4
                )
                if longish_keys >= 4:
                    findings.append(f"{path}: suspicious {str_pairs}-entry str->str map (possible answer lookup)")
    return findings


def run_guard(src_root: str) -> GuardReport:
    report = GuardReport()
    for dirpath, _, files in os.walk(src_root):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, "r", encoding="utf-8") as fh:
                source = fh.read()
            report.scanned_files += 1
            low = source.lower()
            for canary in _CANARIES:
                if canary.lower() in low:
                    report.findings.append(f"{path}: canary '{canary}' found (public-set answer embedded)")
            report.findings.extend(_scan_dict_literals(path, source))
    return report
