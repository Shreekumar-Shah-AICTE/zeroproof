"""Zero-token category classifier.

Categories (Track 1):
    mathematical_reasoning, code_generation, code_debugging,
    logical_reasoning, named_entity_recognition, sentiment_analysis,
    text_summarization, factual_knowledge

Design notes
------------
* Purely deterministic and instant (regex + weighted signals) so it costs zero
  tokens and is identical across machines and prompt refreshes.
* Signals are *paraphrase-invariant intent markers* (e.g. the presence of a code
  block, a "summarize in N sentences" instruction, an explicit entity-label
  list) rather than surface keywords that a refresh could shuffle.
* Classification is only a routing hint: the router verifies each answer, so a
  misroute degrades gracefully instead of failing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

CATEGORIES = [
    "mathematical_reasoning",
    "code_generation",
    "code_debugging",
    "logical_reasoning",
    "named_entity_recognition",
    "sentiment_analysis",
    "text_summarization",
    "factual_knowledge",
]

_CODE_FENCE = re.compile(r"```|\bdef\s+\w+\s*\(|\bclass\s+\w+|\bimport\s+\w+|=>|;\s*$", re.MULTILINE)
_FUNC_HINT = re.compile(r"\b(function|method|program|script|snippet|code)\b", re.IGNORECASE)
_MATH_OP = re.compile(r"\d\s*[-+*/%×÷]\s*\d|\b\d+(\.\d+)?\s*%|\$\s*\d|\b\d{1,3}(,\d{3})+\b")
_NUMBER = re.compile(r"\b\d+(\.\d+)?\b")


@dataclass
class Classification:
    category: str
    confidence: float
    scores: Dict[str, float]


def _score(prompt: str) -> Dict[str, float]:
    p = prompt
    low = prompt.lower()
    s = {c: 0.0 for c in CATEGORIES}

    # ---- Named entity recognition ----
    if re.search(r"named entit|extract .*entit|entities? (from|in)", low):
        s["named_entity_recognition"] += 3.0
    if re.search(r"\b(person|organization|organisation|location|date)\b", low) and "label" in low:
        s["named_entity_recognition"] += 2.0
    if re.search(r"label each|classify each entity|entity types?", low):
        s["named_entity_recognition"] += 1.5

    # ---- Sentiment ----
    if re.search(r"\bsentiment\b", low):
        s["sentiment_analysis"] += 3.0
    if re.search(r"\b(positive|negative|neutral)\b", low) and re.search(r"classif|label|analy", low):
        s["sentiment_analysis"] += 2.0
    if re.search(r"\b(review|tweet|feedback|comment)\b", low) and "classif" in low:
        s["sentiment_analysis"] += 1.0

    # ---- Summarization ----
    if re.search(r"\bsummar(y|ize|ise|isation|ization)\b", low):
        s["text_summarization"] += 3.0
    if re.search(r"in exactly \w+ (sentence|bullet|word)", low):
        s["text_summarization"] += 2.5
    if re.search(r"\bcondense|\btl;?dr\b|in (one|two|three|1|2|3) sentences?", low):
        s["text_summarization"] += 1.5

    # ---- Code debugging ----
    has_code = bool(_CODE_FENCE.search(p))
    if has_code and re.search(r"\bbug|fix|debug|error|corrected?|wrong|broken|doesn'?t work|incorrect\b", low):
        s["code_debugging"] += 3.5
    if re.search(r"find (and fix|the bug)|what'?s wrong|identify the (bug|error)", low):
        s["code_debugging"] += 2.5

    # ---- Code generation ----
    if re.search(r"write (a|an|the)? ?(python |javascript |java )?(function|program|class|method|code|script)", low):
        s["code_generation"] += 3.0
    if re.search(r"\bimplement\b|\breturn(s)? a\b.*\bfunction|def that", low):
        s["code_generation"] += 1.5
    if has_code and not re.search(r"bug|fix|debug|wrong|broken|error", low):
        s["code_generation"] += 1.0
    if _FUNC_HINT.search(low) and re.search(r"write|create|generate|build", low):
        s["code_generation"] += 1.0

    # ---- Logical / deductive reasoning ----
    if re.search(r"\b(each|every)\b.*\b(different|owns?|has|is|are)\b", low) and re.search(r"\bwho\b|which", low):
        s["logical_reasoning"] += 2.0
    if re.search(r"puzzle|deduc|logic|if .* then|constraint|riddle", low):
        s["logical_reasoning"] += 1.5
    if re.search(r"\b(friends?|people|boxes|houses?|pets?)\b.*\b(each|respectively)\b", low):
        s["logical_reasoning"] += 1.0
    # Enumerated constraints ("X does not ...", "Y owns the ...").
    if len(re.findall(r"\b(not|does not|neither|either|only|exactly one)\b", low)) >= 2 and "?" in p:
        s["logical_reasoning"] += 1.0

    # ---- Mathematical reasoning ----
    math_hits = len(_MATH_OP.findall(p))
    num_hits = len(_NUMBER.findall(p))
    if re.search(r"how (many|much)|what is the (total|sum|result|value|average|percentage)|calculate|compute", low):
        s["mathematical_reasoning"] += 2.0
    if math_hits:
        s["mathematical_reasoning"] += min(2.0, 0.8 * math_hits)
    if re.search(r"\bpercent|%|discount|interest|profit|remain|per (cup|hour|unit|item)\b", low) and num_hits >= 1:
        s["mathematical_reasoning"] += 1.2
    if num_hits >= 3 and "?" in p:
        s["mathematical_reasoning"] += 0.8

    # ---- Factual knowledge (default / explanatory) ----
    if re.search(r"\b(what is|what are|who (is|was)|define|explain|describe|difference between|how does|why (is|do|does))\b", low):
        s["factual_knowledge"] += 1.8
    if re.search(r"\bname the\b|\blist the\b", low):
        s["factual_knowledge"] += 0.8

    return s


def classify(prompt: str) -> Classification:
    scores = _score(prompt)
    ranked: List[Tuple[str, float]] = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    if best_score <= 0.0:
        # No signal at all: default to factual knowledge (linguistic path).
        return Classification("factual_knowledge", 0.25, scores)

    # Confidence: separation between top-2, squashed to [0.3, 0.99].
    margin = best_score - second_score
    confidence = min(0.99, 0.45 + 0.18 * margin + 0.05 * best_score)
    return Classification(best, round(confidence, 3), scores)
