"""Factual knowledge — local-LLM, concise and self-consistent.

This is the hardest 0-token category and ZeroProof's top documented risk: there
is no deterministic proof for open-world facts, and hardcoding answers is both a
DQ risk and guaranteed to collapse on the refreshed set. So we:

  * prompt the local model for a *concise, direct* answer (short answers focus the
    judge on the claim and are faster),
  * draw a few low-temperature samples and pick the **medoid** (the answer most
    corroborated by the others) to damp hallucination variance,
  * enforce English and a length cap.

No facts are stored in code. If the model is unavailable the solver returns an
empty answer and the router applies its safe fallback (never a fabricated fact).
The Fireworks valve (default OFF) may, only if the operator explicitly enables it,
serve as a last-resort insurance lever for *this category only*.
"""
from __future__ import annotations

import re
from typing import List

from ..types import Result
from ..utils.text import looks_english, normalize_whitespace, to_ascii_safe

_FACT_SYSTEM = (
    "You are a knowledgeable, accurate assistant. Answer the question directly and "
    "concisely in clear English. Include the key facts the question asks for and a "
    "brief explanation where requested. Do not add filler, disclaimers, or restate "
    "the question. If the question asks to compare or explain, cover each part."
)


def _tokens(text: str) -> set:
    return set(w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2)


def _medoid(answers: List[str]) -> str:
    """Pick the answer most similar (token Jaccard) to the others."""
    if len(answers) == 1:
        return answers[0]
    token_sets = [_tokens(a) for a in answers]
    best_i, best_score = 0, -1.0
    for i, ti in enumerate(token_sets):
        score = 0.0
        for j, tj in enumerate(token_sets):
            if i == j:
                continue
            union = ti | tj
            score += (len(ti & tj) / len(union)) if union else 0.0
        if score > best_score:
            best_i, best_score = i, score
    return answers[best_i]


def solve(prompt: str, ctx) -> Result:  # noqa: ANN001
    if ctx.llm is None or not ctx.llm.available:
        return Result(
            answer="",
            category="factual_knowledge",
            method="none",
            confidence=0.0,
            verified=False,
            proof="no knowledge source available (local model absent)",
        )

    # A deterministic primary answer, plus (budget permitting) one corroboration
    # sample for medoid selection. Output is capped so a single generation stays
    # well under the per-task latency cap on 2 vCPU.
    cap = min(ctx.config.llm_max_tokens, 224)
    primary = ctx.llm.chat(_FACT_SYSTEM, prompt, max_tokens=cap, temperature=0.0)
    answers: List[str] = []
    if primary and primary.text:
        answers.append(primary.text.strip())
    # Only spend a second sample if there is comfortable time left.
    if ctx.seconds_left() > 12.0:
        extra = ctx.llm.sample(_FACT_SYSTEM, prompt, n=1, max_tokens=cap, temperature=0.4)
        answers.extend(a.strip() for a in extra if a.strip())

    if not answers:
        return Result(answer="", category="factual_knowledge", method="none", confidence=0.0,
                      verified=False, proof="model produced no answer")

    chosen = _medoid(answers)
    chosen = normalize_whitespace(to_ascii_safe(chosen))
    if not looks_english(chosen):
        # Prefer the primary if the medoid drifted non-English.
        if answers and looks_english(answers[0]):
            chosen = normalize_whitespace(to_ascii_safe(answers[0]))

    # Agreement heuristic: how much the samples corroborate the chosen answer.
    agree = 0.0
    if len(answers) > 1:
        ct = _tokens(chosen)
        sims = []
        for a in answers:
            ta = _tokens(a)
            u = ct | ta
            sims.append((len(ct & ta) / len(u)) if u else 0.0)
        agree = sum(sims) / len(sims)

    confidence = round(min(0.9, 0.6 + 0.3 * agree), 3)
    return Result(
        answer=chosen,
        category="factual_knowledge",
        method="llm+self-consistency",
        confidence=confidence,
        verified=False,  # facts carry no hard proof; treated as best-effort.
        proof=f"medoid of {len(answers)} samples; corroboration={agree:.2f}",
    )
