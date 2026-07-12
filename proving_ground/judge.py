"""Per-category judge proxy.

Scores an agent answer against a generated task's structured ground truth.
Provable categories are judged *exactly* (numeric match, entity set match,
executed tests, unique-owner match). Linguistic categories are judged by the
Track-1 rubric (accepted sentiment labels + both-sides reason; exact summary
counts/caps; factual keyword coverage). Returns a 0/1 pass plus a note.
"""
from __future__ import annotations

import re
from typing import Dict, Tuple

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from zeroproof.solvers.summarization_solver import parse_format  # noqa: E402
from zeroproof.utils.text import count_words, split_sentences  # noqa: E402
from zeroproof.verify.executor import run_function_with_tests  # noqa: E402

_NUM = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def _numbers(text: str):
    return [float(m.replace(",", "")) for m in _NUM.findall(text)]


def judge(category: str, answer: str, truth: Dict) -> Tuple[bool, str]:
    ans = (answer or "").strip()
    if not ans:
        return False, "empty answer"
    fn = _JUDGES.get(category)
    if fn is None:
        return False, f"no judge for {category}"
    try:
        return fn(ans, truth)
    except Exception as exc:  # a judge error must not crash the suite
        return False, f"judge error: {exc!r}"


def _judge_math(ans: str, truth: Dict) -> Tuple[bool, str]:
    target = float(truth["answer"])
    nums = _numbers(ans)
    if not nums:
        return False, "no number in answer"
    # Accept if the target appears (within tolerance) anywhere; prefer the last
    # number (the stated final answer). Allow small rounding.
    tol = max(0.02, abs(target) * 0.001)
    if any(abs(n - target) <= tol for n in nums):
        # For ratio problems, also check the auxiliary value if present.
        if "aux" in truth and not any(abs(n - float(truth["aux"])) <= 0.05 for n in nums):
            # aux is a bonus; don't fail solely on it.
            pass
        return True, f"matched {target}"
    return False, f"expected {target}, got {nums[-3:]}"


def _judge_logic(ans: str, truth: Dict) -> Tuple[bool, str]:
    owner = truth["owner"].lower()
    if re.search(r"\b" + re.escape(owner) + r"\b", ans.lower()):
        # Guard against "not <owner>" phrasing.
        if re.search(r"not\s+" + re.escape(owner), ans.lower()):
            return False, "names owner only in a negation"
        return True, f"names {truth['owner']}"
    return False, f"expected {truth['owner']}"


def _judge_ner(ans: str, truth: Dict) -> Tuple[bool, str]:
    want = {k.lower(): v for k, v in truth["entities"].items()}
    low = ans.lower()
    missing = []
    for span, label in want.items():
        # entity present and correctly labeled nearby
        m = re.search(re.escape(span) + r".{0,40}?(person|organization|organisation|location|date)", low)
        if not m:
            # date spans may be matched loosely (contain the year)
            if label == "DATE" and re.search(re.escape(span.split()[-1]), low):
                continue
            missing.append(f"{span}:{label}")
            continue
        got = m.group(1)
        norm = {"organisation": "organization"}.get(got, got)
        if norm[:3] != label.lower()[:3]:
            missing.append(f"{span} labeled {got} not {label}")
    if len(missing) <= 0:
        return True, f"all {len(want)} entities correct"
    # Allow at most one mislabel on harder/adversarial (rubric: "mislabelling more than one does not pass")
    if len(missing) == 1:
        return True, f"1 minor miss ({missing[0]})"
    return False, f"missed: {missing}"


def _judge_sentiment(ans: str, truth: Dict) -> Tuple[bool, str]:
    m = re.search(r"sentiment\s*:\s*(positive|negative|neutral|mixed)", ans, re.IGNORECASE)
    label = m.group(1).capitalize() if m else None
    if label is None:
        # try a leading word
        m2 = re.match(r"\s*(positive|negative|neutral|mixed)\b", ans, re.IGNORECASE)
        label = m2.group(1).capitalize() if m2 else None
    if label is None:
        return False, "no label found"
    if label not in truth["acceptable"]:
        return False, f"label {label} not in {truth['acceptable']}"
    if truth.get("both_sides"):
        # Reason must acknowledge both a positive and a negative signal.
        has_pos = bool(re.search(r"positive|works|flawless|perfect|fast|premium|intuitive|good|resolved", ans, re.IGNORECASE))
        has_neg = bool(re.search(r"negative|late|damaged|dented|missing|scratch|drains|disappoint|problem|slow", ans, re.IGNORECASE))
        if not (has_pos and has_neg):
            return False, "reason does not acknowledge both sides"
    return True, f"label {label} ok"


def _judge_summ(ans: str, truth: Dict) -> Tuple[bool, str]:
    if truth["mode"] == "bullets":
        bullets = [b for b in ans.split("\n") if b.strip()]
        if len(bullets) != truth["n"]:
            return False, f"{len(bullets)} bullets, want {truth['n']}"
        if truth.get("max_words"):
            over = [b for b in bullets if count_words(re.sub(r"^[\-\*•\d\.\)\s]+", "", b)) > truth["max_words"]]
            if over:
                return False, f"{len(over)} bullets exceed {truth['max_words']} words"
        return True, f"{truth['n']} bullets within cap"
    else:
        sents = split_sentences(ans)
        if len(sents) != truth["n"]:
            return False, f"{len(sents)} sentences, want {truth['n']}"
        return True, f"{truth['n']} sentences"


def _judge_factual(ans: str, truth: Dict) -> Tuple[bool, str]:
    low = ans.lower()
    kws = truth["keywords"]
    hits = [k for k in kws if k.lower() in low]
    # Require all mandatory keywords (these rubrics use minimal key facts).
    if len(hits) == len(kws):
        return True, f"covers {hits}"
    return False, f"missing {[k for k in kws if k.lower() not in low]}"


def _extract_code(ans: str) -> str:
    m = re.search(r"```(?:python|py)?\s*(.*?)```", ans, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ans


def _judge_code(ans: str, truth: Dict) -> Tuple[bool, str]:
    code = _extract_code(ans)
    if "def " not in code:
        return False, "no function defined"
    res = run_function_with_tests(code, truth["func"], truth["tests"], timeout=6.0)
    if not res.ok or not isinstance(res.result, dict) or not res.result.get("defined"):
        return False, "code did not run/define"
    results = res.result.get("results", [])
    if results and all(r.get("ok") for r in results):
        return True, f"passed {len(results)} tests"
    return False, f"failed tests: {[r for r in results if not r.get('ok')][:2]}"


_JUDGES = {
    "mathematical_reasoning": _judge_math,
    "logical_reasoning": _judge_logic,
    "named_entity_recognition": _judge_ner,
    "sentiment_analysis": _judge_sentiment,
    "text_summarization": _judge_summ,
    "factual_knowledge": _judge_factual,
    "code_generation": _judge_code,
    "code_debugging": _judge_code,
}
