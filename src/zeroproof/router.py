"""The router: classify -> cheapest trustworthy solver -> verify -> normalize.

Guarantees:
  * every task gets a non-empty, English answer,
  * provable categories return proof-carrying answers when possible,
  * a weak/unusable local answer triggers a general-model retry and, only if the
    operator has explicitly opened the (default-OFF) Fireworks valve for the
    allowed category, a single minimal remote call,
  * a task never raises out of ``route`` — worst case is a safe fallback string.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional

from .classifier import classify
from .config import Config
from .llm.fireworks_valve import FireworksValve
from .llm.local_llm import LocalLLM
from .solvers import (
    code_solver,
    factual_solver,
    logic_solver,
    math_solver,
    ner_solver,
    sentiment_solver,
    summarization_solver,
)
from .types import Result, Task
from .utils.text import looks_english, normalize_whitespace, to_ascii_safe

_GENERAL_SYSTEM = (
    "You are a precise, helpful assistant. Answer the task directly and correctly "
    "in clear English. Be concise and address exactly what is asked."
)

# Confidence below which a non-verified local answer is considered weak.
_WEAK_CONFIDENCE = 0.5


@dataclass
class Context:
    config: Config
    llm: Optional[LocalLLM]
    valve: FireworksValve

    @property
    def fireworks_tokens(self) -> int:
        return self.valve.fireworks_tokens


def build_context(config: Optional[Config] = None) -> Context:
    config = config or Config()
    llm = LocalLLM(
        model_path=config.model_path,
        n_threads=config.n_threads,
        n_ctx=config.n_ctx,
        n_batch=config.n_batch,
        seed=config.seed,
        verbose=config.verbose,
    )
    valve = FireworksValve(
        enabled=config.fireworks_enabled,
        allowed_categories=config.fireworks_allowed_categories,
        timeout=config.remote_timeout_seconds,
    )
    return Context(config=config, llm=llm, valve=valve)


_DISPATCH: Dict[str, Callable[[str, Context], Result]] = {
    "mathematical_reasoning": math_solver.solve,
    "code_generation": code_solver.solve_generation,
    "code_debugging": code_solver.solve_debugging,
    "logical_reasoning": logic_solver.solve,
    "named_entity_recognition": ner_solver.solve,
    "sentiment_analysis": sentiment_solver.solve,
    "text_summarization": summarization_solver.solve,
    "factual_knowledge": factual_solver.solve,
}


def _general_answer(prompt: str, ctx: Context) -> Optional[str]:
    if ctx.llm is None or not ctx.llm.available:
        return None
    reply = ctx.llm.chat(_GENERAL_SYSTEM, prompt, max_tokens=ctx.config.llm_max_tokens, temperature=0.0)
    if reply and reply.text.strip():
        return reply.text.strip()
    return None


def _finalize(answer: str, fallback: str) -> str:
    answer = to_ascii_safe(answer or "").strip()
    answer = normalize_whitespace(answer) if "\n" not in answer else answer.strip()
    if not answer:
        return fallback
    if not looks_english(answer):
        return fallback
    return answer


def route(task: Task, ctx: Context) -> Result:
    """Route a single task to an answer (never raises)."""
    try:
        cls = classify(task.prompt)
        solver = _DISPATCH.get(cls.category, factual_solver.solve)
        result = solver(task.prompt, ctx)
        result.meta["classified_as"] = cls.category
        result.meta["classify_confidence"] = cls.confidence

        good = result.is_usable() and (result.verified or result.confidence >= _WEAK_CONFIDENCE)

        if not good:
            # 1) General-model retry (still 0 Fireworks tokens).
            general = _general_answer(task.prompt, ctx)
            if general:
                if not result.is_usable() or result.confidence < 0.4:
                    result = Result(
                        answer=general, category=cls.category, method="general-llm",
                        confidence=0.55, verified=False, proof="general local-model answer",
                        meta=result.meta,
                    )
                    good = True

        if not good and ctx.valve.enabled:
            # 2) Fireworks valve — default OFF; allowed-category, last-resort only.
            reply = ctx.valve.call(cls.category, _GENERAL_SYSTEM, task.prompt,
                                   max_tokens=min(256, ctx.config.llm_max_tokens))
            if reply and reply.text.strip():
                result = Result(
                    answer=reply.text.strip(), category=cls.category, method="fireworks-valve",
                    confidence=0.6, verified=False,
                    proof=f"insurance valve ({reply.model})",
                    fireworks_tokens=reply.tokens_in + reply.tokens_out, meta=result.meta,
                )

        result.answer = _finalize(result.answer, ctx.config.fail_open_answer)
        return result
    except Exception as exc:  # absolute safety net — never sink a task
        return Result(
            answer=ctx.config.fail_open_answer,
            category="error",
            method="exception",
            confidence=0.0,
            verified=False,
            proof=f"router exception: {exc!r}",
        )
