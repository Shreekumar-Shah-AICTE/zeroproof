"""Code generation & debugging — proof-carrying by execution.

Both paths generate code with the local LLM, then **execute it in the sandbox**
to prove it runs (and passes any tests we can derive/parse). A repair loop feeds
the runtime error back to the model. The answer is only marked verified when the
code actually executes cleanly.

If the local model is unavailable we still return any code recovered from the
prompt (debugging) or an honest stub (generation) so the contract never breaks —
but such answers are marked unverified/low-confidence.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ..types import Result
from ..verify.executor import run_code, run_function_with_tests

_CODE_BLOCK = re.compile(r"```(?:python|py)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_DEF_NAME = re.compile(r"def\s+([a-zA-Z_]\w*)\s*\(")
_INLINE_DEF = re.compile(r"(def\s+[a-zA-Z_]\w*\s*\(.*?)(?:\.\s|$|\bFind\b|\bFix\b|\bIdentify\b)", re.DOTALL)

_GEN_SYSTEM = (
    "You are an expert Python engineer. Write a correct, self-contained Python 3 "
    "solution for the request. Handle edge cases (empty inputs, duplicates, negatives). "
    "Output ONLY one ```python code block containing the function(s); no prose, no examples."
)
_DEBUG_SYSTEM = (
    "You are an expert Python debugger. You are given buggy code. Return a corrected, "
    "self-contained version that satisfies the described intent and handles edge cases. "
    "Output ONLY one ```python code block with the fixed code; no prose."
)


def _extract_code(text: str) -> Optional[str]:
    m = _CODE_BLOCK.search(text)
    if m:
        return m.group(1).strip()
    # No fence: accept if it looks like code.
    if _DEF_NAME.search(text) or re.search(r"^\s*(return|for|if|while|import)\b", text, re.MULTILINE):
        return text.strip()
    return None


def _extract_prompt_code(prompt: str) -> Optional[str]:
    m = _CODE_BLOCK.search(prompt)
    if m:
        return m.group(1).strip()
    m2 = _INLINE_DEF.search(prompt)
    if m2:
        return m2.group(1).strip()
    return None


def _func_name(code: str) -> Optional[str]:
    m = _DEF_NAME.search(code)
    return m.group(1) if m else None


def _smoke_inputs(prompt: str) -> List[list]:
    """Cheap, generic smoke inputs based on argument-type hints in the prompt."""
    low = prompt.lower()
    inputs: List[list] = []
    if "list" in low or "array" in low or "numbers" in low:
        inputs += [[[3, 1, 2, 2, 5]], [[5, 5]], [[-1, -2, -3]], [[42]]]
    if "string" in low or "word" in low or "text" in low or "sentence" in low:
        inputs += [["hello world"], [""], ["a"]]
    if not inputs:
        inputs += [[5], [0], [1]]
    return inputs


def _parse_examples(prompt: str, func: str) -> List[Dict]:
    """Best-effort parse of explicit examples like ``f([1,2]) -> 3`` or
    ``f([1,2]) == 3`` into executable tests. Returns [] when none are found."""
    tests: List[Dict] = []
    pattern = re.compile(re.escape(func) + r"\(([^)]*)\)\s*(?:->|==|=|returns?)\s*([^\n.;]+)", re.IGNORECASE)
    for m in pattern.finditer(prompt):
        args_src, exp_src = m.group(1).strip(), m.group(2).strip()
        try:
            import ast

            args = list(ast.literal_eval("[" + args_src + "]")) if args_src else []
            expected = ast.literal_eval(exp_src)
            tests.append({"args": args, "expected": expected})
        except Exception:
            continue
    return tests


def _verify_code(code: str, func: Optional[str], prompt: str, timeout: float) -> Tuple[bool, str]:
    """Return (passed, detail). Passed means it defines/runs cleanly and any
    parsed example tests succeed."""
    if not code:
        return False, "no code"
    if func is None:
        # Just check it executes at module level.
        res = run_code(code + "\nprint('__ZP_RESULT__', 'ok')", timeout=timeout)
        return (res.ok and res.result == "ok"), (res.stderr.strip().splitlines()[-1] if res.stderr else "")

    tests = _parse_examples(prompt, func)
    if not tests:
        tests = [{"args": args} for args in _smoke_inputs(prompt)]
    res = run_function_with_tests(code, func, tests, timeout=timeout)
    if not res.ok or not isinstance(res.result, dict):
        return False, (res.stderr.strip().splitlines()[-1] if res.stderr else "execution failed")
    if not res.result.get("defined"):
        return False, res.result.get("error", "not defined")
    results = res.result.get("results", [])
    passed = all(r.get("ok") for r in results) if results else True
    detail = "; ".join(str(r.get("error") or r.get("got")) for r in results[:3])
    return passed, detail


def _generate_and_repair(system: str, user_builder, ctx, prompt: str) -> Tuple[Optional[str], bool, str]:  # noqa: ANN001
    timeout = min(ctx.config.code_exec_timeout, 6.0)
    cap = min(ctx.config.llm_max_tokens + 128, 420)  # code needs a little more room
    last_code = None
    last_detail = ""
    feedback = ""
    for attempt in range(2):  # first attempt + one repair; bounded for latency
        if ctx.llm is None or not ctx.llm.available:
            break
        if attempt > 0 and ctx.seconds_left() < 12.0:
            break  # not enough budget for another generation
        reply = ctx.llm.chat(system, user_builder(feedback), max_tokens=cap, temperature=0.1 if attempt == 0 else 0.4)
        if reply is None:
            break
        code = _extract_code(reply.text)
        if not code:
            feedback = "Your previous response had no valid ```python code block. Return only code."
            continue
        last_code = code
        func = _func_name(code)
        passed, detail = _verify_code(code, func, prompt, timeout)
        last_detail = detail
        if passed:
            return code, True, detail
        feedback = f"The code failed verification: {detail}. Fix it and return only the corrected ```python block."
    return last_code, False, last_detail


def solve_generation(prompt: str, ctx) -> Result:  # noqa: ANN001
    code, verified, detail = _generate_and_repair(
        _GEN_SYSTEM, lambda fb: (prompt + ("\n\n" + fb if fb else "")), ctx, prompt
    )
    if code:
        answer = f"```python\n{code}\n```"
        return Result(
            answer=answer,
            category="code_generation",
            method="llm-gen+execute",
            confidence=0.95 if verified else 0.6,
            verified=verified,
            proof=("executed cleanly" + (f" ({detail})" if detail else "")) if verified else f"unverified: {detail}",
        )
    return Result(answer="", category="code_generation", method="none", confidence=0.0, verified=False,
                  proof="no code produced")


def solve_debugging(prompt: str, ctx) -> Result:  # noqa: ANN001
    buggy = _extract_prompt_code(prompt)
    timeout = min(ctx.config.code_exec_timeout, 6.0)

    def build_user(fb: str) -> str:
        base = prompt
        if buggy:
            base += f"\n\nThe buggy code is:\n```python\n{buggy}\n```"
        if fb:
            base += "\n\n" + fb
        return base

    code, verified, detail = _generate_and_repair(_DEBUG_SYSTEM, build_user, ctx, prompt)
    if code:
        func = _func_name(code) or (_func_name(buggy) if buggy else None)
        bug_note = "Corrected implementation:"
        answer = f"{bug_note}\n```python\n{code}\n```"
        return Result(
            answer=answer,
            category="code_debugging",
            method="llm-fix+execute",
            confidence=0.95 if verified else 0.6,
            verified=verified,
            proof=("fixed code executes cleanly" + (f" ({detail})" if detail else "")) if verified else f"unverified: {detail}",
        )
    # Model unavailable but we at least recovered the buggy code: cannot fix safely.
    return Result(answer="", category="code_debugging", method="none", confidence=0.0, verified=False,
                  proof="no fix produced")
