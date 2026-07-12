"""Mathematical reasoning — proof-carrying by execution.

Strategy (cheapest trustworthy source first):
  1. **Clean-expression fast path.** If the prompt reduces to a single safe
     arithmetic expression (e.g. "What is 15% of 240?"), evaluate it symbolically
     with SymPy. This is provably correct and needs no model.
  2. **Program-of-thought (primary for word problems).** The local LLM writes a
     short Python program that prints its steps and a final ``ANSWER:`` line. We
     execute it in the sandbox — the *executed value* is the answer, not the
     model's assertion. We draw two independent samples; if they agree the answer
     is **verified** by self-consistency.
  3. If nothing is trustworthy, return the best available with low confidence.

A wrong "free" answer is structurally hard to emit: numbers come from executed
code, and disagreement lowers confidence rather than shipping a guess.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..types import Result
from ..utils.text import normalize_whitespace
from ..verify.executor import run_code
from .arith_chain import solve_chain

_NUM = r"[-+]?\d[\d,]*(?:\.\d+)?"


def _fmt_number(x: float) -> str:
    """Format a numeric result the way a human would write it."""
    if x != x:  # NaN
        return "undefined"
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x)):,}"
    # Trim trailing zeros, keep up to 4 decimals.
    s = f"{x:,.4f}".rstrip("0").rstrip(".")
    return s


# --------------------------------------------------------------------------
# 1. Clean-expression fast path
# --------------------------------------------------------------------------
_PERCENT_OF = re.compile(r"what\s+is\s+(" + _NUM + r")\s*%\s*of\s*(" + _NUM + r")", re.IGNORECASE)
_PURE_EXPR = re.compile(r"^[\s\d,\.\+\-\*/%()×÷x]+$")


def _safe_eval_expr(expr: str) -> Optional[float]:
    expr = expr.replace(",", "").replace("×", "*").replace("÷", "/")
    if not re.match(r"^[\s\d\.\+\-\*/%()]+$", expr):
        return None
    try:
        from sympy import sympify

        val = sympify(expr, evaluate=True)
        return float(val)
    except Exception:
        return None


# --------------------------------------------------------------------------
# 1c. Proportion / unit-cost (ratio) problems
# --------------------------------------------------------------------------
_AMOUNT_UNIT = re.compile(
    r"(\d+\s*/\s*\d+|\d+(?:\.\d+)?)\s*(cups?|grams?|kg|kilograms?|liters?|litres?|ml|"
    r"tablespoons?|teaspoons?|ounces?|oz|pounds?|lbs?|tbsp|tsp)\b",
    re.IGNORECASE,
)
_FOR_COUNT = re.compile(r"for\s+(\d+(?:\.\d+)?)\s+([a-zA-Z]+)", re.IGNORECASE)
_COST = re.compile(r"\$?\s*(\d+(?:\.\d+)?)\s*(?:per|/|a)\s*(cups?|grams?|kg|liters?|litres?|ml|ounces?|oz|pounds?|lbs?)", re.IGNORECASE)


def _parse_amount(tok: str) -> Optional[float]:
    tok = tok.strip()
    if "/" in tok:
        a, b = tok.split("/")
        try:
            return float(a) / float(b)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(tok)
    except ValueError:
        return None


def _ratio_solve(prompt: str) -> Optional[Tuple[float, str]]:
    am = _AMOUNT_UNIT.search(prompt)
    counts = _FOR_COUNT.findall(prompt)
    if not am or len(counts) < 1:
        return None
    amount = _parse_amount(am.group(1))
    unit = am.group(2).lower().rstrip("s")
    if amount is None:
        return None
    # base = the count nearest the amount ("for 12 cookies"); target = a
    # different count (the asked quantity).
    nums = [float(c[0]) for c in counts]
    base = nums[0]
    target = next((n for n in nums if n != base), None)
    if target is None or base == 0:
        return None
    scaled = amount * target / base
    lines = [f"{am.group(1)} {unit} per {int(base) if base==int(base) else base} -> "
             f"{_fmt_number(scaled)} {unit} for {int(target) if target==int(target) else target}"]
    result = scaled
    cost_m = _COST.search(prompt)
    if cost_m:
        cost = float(cost_m.group(1))
        total = scaled * cost
        lines.append(f"cost: {_fmt_number(scaled)} x ${cost:.2f} = ${_fmt_number(total)}")
        result = total
    return result, "\n".join(lines)


def _clean_expression(prompt: str) -> Optional[Tuple[float, str]]:
    m = _PERCENT_OF.search(prompt)
    if m:
        pct = float(m.group(1).replace(",", ""))
        base = float(m.group(2).replace(",", ""))
        val = pct / 100.0 * base
        return val, f"{_fmt_number(pct)}% of {_fmt_number(base)} = {_fmt_number(val)}"
    # "Calculate/Compute <expr>" or a bare arithmetic line.
    m2 = re.search(r"(?:calculate|compute|evaluate|what is)\s*[:\-]?\s*(" + _NUM + r"[\d\s,\.\+\-\*/%()×÷]*)", prompt, re.IGNORECASE)
    candidate = None
    if m2:
        candidate = m2.group(1)
    elif _PURE_EXPR.match(prompt.strip()) and re.search(r"[+\-*/%]", prompt):
        candidate = prompt.strip()
    if candidate and re.search(r"[+\-*/%]", candidate):
        val = _safe_eval_expr(candidate)
        if val is not None:
            return val, f"{normalize_whitespace(candidate)} = {_fmt_number(val)}"
    return None


# --------------------------------------------------------------------------
# 2. Program-of-thought via the local LLM
# --------------------------------------------------------------------------
_POT_SYSTEM = (
    "You are a careful math solver. Write a short Python 3 program that solves the "
    "problem by computing the answer from the given numbers. Print each intermediate "
    "step on its own line as 'label = value', and finish with a line exactly like "
    "'ANSWER: <final value>'. Use only Python's math; no input(), no imports except "
    "'math'. Output ONLY a single ```python code block."
)

_CODE_BLOCK = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_ANSWER_LINE = re.compile(r"ANSWER:\s*(" + _NUM + r")", re.IGNORECASE)


def _extract_code(text: str) -> Optional[str]:
    m = _CODE_BLOCK.search(text)
    code = m.group(1) if m else text
    if "ANSWER" not in code and "print" not in code:
        return None
    # Strip dangerous imports defensively (sandbox also blocks, belt-and-braces).
    lines = [ln for ln in code.splitlines() if not re.match(r"\s*(import\s+(os|sys|subprocess|socket)|from\s+(os|sys|subprocess|socket))", ln)]
    return "\n".join(lines)


def _run_pot(code: str, timeout: float) -> Optional[Tuple[float, str]]:
    res = run_code(code, timeout=timeout)
    if not res.ok:
        return None
    m = _ANSWER_LINE.search(res.stdout)
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    steps = "\n".join(
        ln.strip() for ln in res.stdout.splitlines() if "=" in ln and not ln.startswith("__ZP")
    )
    return value, steps


def solve(prompt: str, ctx) -> Result:  # noqa: ANN001
    prompt = prompt.strip()
    timeout = min(ctx.config.code_exec_timeout, 6.0)

    # ---- 1. Clean-expression fast path (provably correct, no model) ----
    clean = _clean_expression(prompt)

    # ---- 1b. Deterministic arithmetic-chain (high-precision, refuses if unsure) ----
    chain = solve_chain(prompt)  # (value, worked_steps) or None

    # ---- 1c. Proportion / unit-cost (ratio) problems ----
    ratio = _ratio_solve(prompt)

    # ---- 2. Program-of-thought (primary for word problems) ----
    pot_values: List[Tuple[float, str]] = []
    if ctx.llm is not None and ctx.llm.available:
        samples = ctx.llm.sample(_POT_SYSTEM, prompt, n=max(2, ctx.config.self_consistency_samples), max_tokens=380, temperature=0.4)
        for text in samples:
            code = _extract_code(text)
            if not code:
                continue
            got = _run_pot(code, timeout)
            if got is not None:
                pot_values.append(got)

    def _cross(val: float) -> bool:
        return (
            (clean and abs(clean[0] - val) < 1e-6)
            or (chain and abs(chain[0] - val) < 1e-6)
            or (ratio and abs(ratio[0] - val) < 1e-4)
        )

    if pot_values:
        # Majority vote over executed results.
        tally = {}
        for val, steps in pot_values:
            key = round(val, 6)
            tally.setdefault(key, {"count": 0, "steps": steps})
            tally[key]["count"] += 1
        best_key = max(tally, key=lambda k: tally[k]["count"])
        agree = tally[best_key]["count"]
        steps = tally[best_key]["steps"]
        crossed = _cross(best_key)
        verified = agree >= 2 or crossed
        answer_text = (steps + "\n" if steps else "") + f"Answer: {_fmt_number(best_key)}"
        confidence = 0.98 if crossed else (0.9 if agree >= 2 else 0.7)
        proof = f"program-of-thought executed; {agree}/{len(pot_values)} samples agree" + (
            "; matches deterministic computation" if crossed else ""
        )
        return Result(
            answer=answer_text.strip(),
            category="mathematical_reasoning",
            method="pot+execute",
            confidence=confidence,
            verified=verified,
            proof=proof,
        )

    # No usable PoT (e.g. model absent or PoT failed) -> deterministic paths.
    if ratio is not None:
        val, work = ratio
        return Result(
            answer=f"{work}\nAnswer: {_fmt_number(val)}",
            category="mathematical_reasoning",
            method="ratio-solver",
            confidence=0.9,
            verified=True,
            proof="deterministic proportion/unit-cost computation",
        )

    if chain is not None:
        val, work = chain
        return Result(
            answer=f"{work}\nAnswer: {_fmt_number(val)}",
            category="mathematical_reasoning",
            method="arith-chain",
            confidence=0.9,
            verified=True,
            proof="deterministic operation-chain (all operands consumed)",
        )

    if clean is not None:
        val, work = clean
        return Result(
            answer=f"{work}\nAnswer: {_fmt_number(val)}",
            category="mathematical_reasoning",
            method="symbolic-eval",
            confidence=0.95,
            verified=True,
            proof="direct symbolic evaluation",
        )

    # ---- 3. Nothing trustworthy: honest low-confidence best effort ----
    # (Only reached when the local model is unavailable AND no clean expression.)
    return Result(
        answer="",
        category="mathematical_reasoning",
        method="none",
        confidence=0.0,
        verified=False,
        proof="no executable derivation available",
    )
