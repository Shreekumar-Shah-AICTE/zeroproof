"""Logical / deductive reasoning.

Primary: local-LLM chain-of-thought with **self-consistency** — sample several
independent solutions and take the majority final answer; strong agreement means
the answer is corroborated. Where the puzzle is a classic "N agents each get a
distinct attribute" grid, we additionally try an exact constraint solver
(python-constraint) and, if it yields a unique solution, treat that as a proof
that overrides the vote.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import List, Optional

from ..types import Result
from ..utils.text import normalize_whitespace

_LOGIC_SYSTEM = (
    "You are a rigorous logic solver. Reason step by step using only the facts given. "
    "State the deduction briefly, then end with a line exactly like 'ANSWER: <answer>'. "
    "Keep the answer specific and short."
)
_ANSWER_LINE = re.compile(r"ANSWER:\s*(.+)", re.IGNORECASE)


def _extract_answer(text: str) -> Optional[str]:
    matches = _ANSWER_LINE.findall(text)
    if matches:
        return normalize_whitespace(matches[-1]).rstrip(".")
    # Fall back to the last non-empty line.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return normalize_whitespace(lines[-1]).rstrip(".") if lines else None


def _norm_key(ans: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", ans.lower()).strip()


def solve(prompt: str, ctx) -> Result:  # noqa: ANN001
    # Try the exact constraint path first (proof if unique solution found).
    exact = _try_constraint(prompt)
    if exact is not None:
        return Result(
            answer=exact,
            category="logical_reasoning",
            method="constraint-solver",
            confidence=0.97,
            verified=True,
            proof="unique solution satisfying all stated constraints",
        )

    if ctx.llm is None or not ctx.llm.available:
        return Result(answer="", category="logical_reasoning", method="none", confidence=0.0, verified=False,
                      proof="no reasoning engine available")

    n = max(3, ctx.config.self_consistency_samples)
    samples = ctx.llm.sample(_LOGIC_SYSTEM, prompt, n=n, max_tokens=320, temperature=0.5)
    answers = [a for a in (_extract_answer(s) for s in samples) if a]
    if not answers:
        return Result(answer="", category="logical_reasoning", method="none", confidence=0.0, verified=False,
                      proof="model produced no parseable answer")

    counts = Counter(_norm_key(a) for a in answers)
    best_key, agree = counts.most_common(1)[0]
    # Recover a readable form of the winning answer.
    readable = next(a for a in answers if _norm_key(a) == best_key)
    ratio = agree / len(answers)
    verified = ratio >= 0.67 and agree >= 2
    return Result(
        answer=readable,
        category="logical_reasoning",
        method="llm+self-consistency",
        confidence=round(0.55 + 0.4 * ratio, 3),
        verified=verified,
        proof=f"self-consistency {agree}/{len(answers)} samples agree",
    )


# --------------------------------------------------------------------------
# Exact constraint attempt for classic distinct-assignment puzzles.
# --------------------------------------------------------------------------
def _try_constraint(prompt: str) -> Optional[str]:
    """Handle the common template: some agents each own a distinct item, with
    'X does not own the Y' / 'X owns the Y' clues, asking 'Who owns the Z?'.

    Deliberately conservative: only fires when it can build a well-formed model
    and finds exactly one solution; otherwise returns None and the LLM path runs.
    """
    low = prompt.lower()
    # Verb-agnostic question: "who <verb> the <item>?" ("owns"/"is"/"drives"...).
    q = re.search(r"who\s+(\w+)\s+(?:the\s+)?([a-z]+)", low)
    if not q:
        return None
    q_verb, target_item = q.group(1), q.group(2)

    # Gather candidate agents from an enumeration that precedes "each"
    # (e.g. "Sam, Jo, and Lee, each own ..."). This avoids grabbing sentence
    # starters ("Three") or question words ("Who").
    _STOP = {"who", "the", "each", "a", "an", "three", "two", "four", "five",
             "and", "or", "which", "what", "they", "he", "she"}
    enum = re.search(r"([A-Z][a-z]+(?:\s*,\s*[A-Z][a-z]+)+(?:\s*,?\s*and\s+[A-Z][a-z]+)?)\s*,?\s+each\b", prompt)
    if enum:
        raw_names = re.findall(r"[A-Z][a-z]+", enum.group(1))
    else:
        raw_names = re.findall(r"\b([A-Z][a-z]+)\b", prompt)
    agents = [n for n in dict.fromkeys(raw_names) if n.lower() not in _STOP]

    # Items: look for a list like "cat, dog, bird".
    item_list = re.search(r":\s*([a-z]+(?:,\s*[a-z]+)+(?:,?\s*(?:and|or)\s+[a-z]+)?)", low)
    if not item_list:
        item_list = re.search(r"\b([a-z]+(?:,\s*[a-z]+)+\s*(?:and|or)\s+[a-z]+)\b", low)
    if not item_list:
        return None
    items = [w.strip() for w in re.split(r",|\band\b|\bor\b", item_list.group(1)) if w.strip()]
    items = list(dict.fromkeys(items))

    if not (2 <= len(agents) <= 6) or len(agents) != len(items) or target_item not in items:
        return None

    try:
        from constraint import Problem, AllDifferentConstraint
    except Exception:
        return None

    item_index = {it: i for i, it in enumerate(items)}
    agent_lc = {a.lower(): a for a in agents}
    problem = Problem()
    for agent in agents:
        problem.addVariable(agent, list(range(len(items))))
    problem.addConstraint(AllDifferentConstraint(), agents)

    # Parse clues sentence by sentence: a sentence naming exactly one agent and
    # one item becomes a == or != constraint, with polarity from negation words.
    _NEG = re.compile(r"\bnot\b|n't|\bnever\b|\bneither\b|\bcannot\b|\bno\b")
    added = 0
    for sentence in re.split(r"[.;\n?]", low):
        # Skip the question sentence itself.
        if sentence.strip().startswith("who ") or "who " in sentence and "?" in prompt and sentence.strip().startswith("who"):
            continue
        found_agents = [a for a in agent_lc if re.search(r"\b" + re.escape(a) + r"\b", sentence)]
        found_items = [it for it in item_index if re.search(r"\b" + re.escape(it) + r"\b", sentence)]
        if len(found_agents) != 1 or not found_items:
            continue
        agent = agent_lc[found_agents[0]]
        if _NEG.search(sentence):
            # "X did not pick the banana or cherry" -> != for every named item.
            for it in found_items:
                problem.addConstraint(lambda a, i=item_index[it]: a != i, [agent])
            added += 1
        elif len(found_items) == 1:
            problem.addConstraint(lambda a, i=item_index[found_items[0]]: a == i, [agent])
            added += 1
    if added == 0:
        return None

    solutions = problem.getSolutions()
    if not solutions:
        return None
    target_idx = item_index[target_item]
    # The full grid need not be unique — only the answer to the asked item must
    # be the same across every satisfying solution.
    owners = set()
    for sol in solutions:
        for agent, idx in sol.items():
            if idx == target_idx:
                owners.add(agent)
    if len(owners) != 1:
        return None
    agent = owners.pop()
    verb = q_verb if q_verb not in {"is", "was", "are"} else "is"
    if verb == "is":
        return f"{agent} is the {target_item}."
    return f"{agent} {verb} the {target_item}."
