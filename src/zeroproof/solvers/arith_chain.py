"""Conservative deterministic arithmetic-chain solver for word problems.

This is a *high-precision* parser for the common "running total" family of
problems (start with N, sell X%, restock M, sell K, ...). It only fires when the
structure is unambiguous; otherwise it returns None and the program-of-thought
path handles the problem. Because it translates recognized operations into plain
arithmetic and executes them, its answers are proof-carrying in the same sense as
PoT — but with zero model dependence, which keeps math robust even when the local
model is weak or absent.

Ratio/unit-cost problems ("3/4 cup for 12 cookies -> how much for 30, at $2.40/cup")
are handled by a separate proportional path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

_NUMWORD = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
    "dozen": 12, "hundred": 100, "thousand": 1000,
}


def _to_float(tok: str) -> Optional[float]:
    tok = tok.replace(",", "").strip()
    try:
        return float(tok)
    except ValueError:
        return _NUMWORD.get(tok.lower())


@dataclass
class Step:
    label: str
    op: str        # 'add' | 'sub' | 'mul' | 'set'
    value: float
    is_percent: bool = False


_START = re.compile(
    r"(?:starts?\s+with|begins?\s+with|has|had|have|contains?|there\s+(?:are|were)|"
    r"initial(?:ly)?|start(?:ing)?\s+(?:with|at)|inventory[^.\d]*\bis|is)\s+(?:about\s+)?([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
# Verb sets include base/-s/-ing/-ed/gerund forms so "sells", "selling", "sold"
# all match (and likewise add/adding/added, remove/removing/removed, ...).
_ADD = re.compile(
    r"\b(?:add(?:s|ing|ed)?|restock(?:s|ing|ed)?|gain(?:s|ing|ed)?|buy(?:s|ing)?|bought|"
    r"receiv(?:e|es|ing|ed)|deposit(?:s|ing|ed)?|earn(?:s|ing|ed)?|produc(?:e|es|ing|ed)|"
    r"mak(?:e|es|ing)|made|acquir(?:e|es|ing|ed)|get(?:s|ting)?|got|gain(?:s|ing|ed)?|plus)"
    r"\b[^.\d]*?([\d,]+(?:\.\d+)?)(\s*%)?",
    re.IGNORECASE,
)
_SUB = re.compile(
    r"\b(?:sell(?:s|ing)?|sold|los(?:e|es|ing)|lost|remov(?:e|es|ing|ed)|spend(?:s|ing)?|spent|"
    r"us(?:e|es|ing|ed)|giv(?:e|es|ing)|gave|withdraw(?:s|ing)?|withdrew|donat(?:e|es|ing|ed)|"
    r"eat(?:s|ing)?|ate|drop(?:s|ping|ped)?|discard(?:s|ing|ed)?|minus)"
    r"\b[^.\d]*?([\d,]+(?:\.\d+)?)(\s*%)?",
    re.IGNORECASE,
)
_INC_PCT = re.compile(r"\bincreas(?:e|es|ing|ed)\s+by\s+([\d,]+(?:\.\d+)?)\s*%", re.IGNORECASE)
_DEC_PCT = re.compile(r"\bdecreas(?:e|es|ing|ed)\s+by\s+([\d,]+(?:\.\d+)?)\s*%", re.IGNORECASE)


def _fmt(x: float) -> str:
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x)):,}"
    s = f"{x:,.4f}".rstrip("0").rstrip(".")
    return s


def solve_chain(prompt: str) -> Optional[Tuple[float, str]]:
    """Return (value, worked_steps) or None if the structure is not clean."""
    # Remove thousands-separator commas ("1,000" -> "1000") BEFORE any clause
    # splitting, so numbers survive the comma-based clause split intact.
    text = re.sub(r"(?<=\d),(?=\d\d\d(?:\D|$))", "", prompt.strip())
    start_m = _START.search(text)
    if not start_m:
        return None
    current = _to_float(start_m.group(1))
    if current is None:
        return None

    # Walk clauses in order after the start position.
    tail = text[start_m.end():]
    clauses = re.split(r"[.;]|\band then\b|\bthen\b|\bnext\b|,", tail)
    steps: List[Step] = [Step("start", "set", current)]
    consumed = 0
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        applied = False
        for regex, op in ((_DEC_PCT, "dec_pct"), (_INC_PCT, "inc_pct"), (_ADD, "add"), (_SUB, "sub")):
            m = regex.search(clause)
            if not m:
                continue
            val = _to_float(m.group(1))
            if val is None:
                continue
            is_pct = op in ("inc_pct", "dec_pct") or (m.lastindex and m.group(m.lastindex) and "%" in (m.group(m.lastindex) or ""))
            if op == "add":
                if is_pct:
                    delta = current * val / 100.0
                    steps.append(Step(f"add {val}%", "add", delta, True))
                    current += delta
                else:
                    steps.append(Step(f"add {val}", "add", val))
                    current += val
            elif op == "sub":
                if is_pct:
                    delta = current * val / 100.0
                    steps.append(Step(f"subtract {val}%", "sub", delta, True))
                    current -= delta
                else:
                    steps.append(Step(f"subtract {val}", "sub", val))
                    current -= val
            elif op == "inc_pct":
                delta = current * val / 100.0
                steps.append(Step(f"increase by {val}%", "add", delta, True))
                current += delta
            elif op == "dec_pct":
                delta = current * val / 100.0
                steps.append(Step(f"decrease by {val}%", "sub", delta, True))
                current -= delta
            applied = True
            consumed += 1
            break
    if consumed < 1:
        return None

    # ---- Safety guard against confidently-wrong parses ----
    # Count "operative" numbers in the tail: standalone numerics not glued to a
    # letter (excludes Q1/Q3, H2, etc.). If we did not consume exactly as many
    # numbers as appear, the structure is ambiguous -> refuse and defer to PoT.
    operative = re.findall(r"(?<![A-Za-z0-9])\d[\d,]*(?:\.\d+)?(?![A-Za-z])", tail)
    # Drop pure ordinals/labels like standalone years only if clearly not operands
    if len(operative) != consumed:
        return None

    work_lines = [f"Start: {_fmt(steps[0].value)}"]
    running = steps[0].value
    for st in steps[1:]:
        if st.op == "add":
            running += st.value
        elif st.op == "sub":
            running -= st.value
        work_lines.append(f"{st.label} -> {_fmt(running)}")
    return current, "\n".join(work_lines)
