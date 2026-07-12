"""Text summarization — local-LLM draft with *deterministic* format enforcement.

The rubric fails you for the wrong number of sentences/bullets or an over-length
bullet, independent of content quality. So format is enforced mechanically:

  * parse the requested shape ("exactly two sentences", "three bullet points,
    each no longer than 15 words", "one sentence"),
  * draft with the local LLM when available,
  * **force** the output to the exact sentence/bullet count and per-item word cap,
  * fall back to a deterministic extractive summarizer (coverage-aware) when no
    model is present, which selects exactly N salient sentences spanning the
    passage so both "sides" of a contrastive passage are represented.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional

from ..types import Result
from ..utils.text import count_words, normalize_whitespace, split_sentences, truncate_words

_WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "single": 1, "a": 1,
}
_STOPWORDS = set(
    "the a an and or but of to in on for with as by is are was were be been being "
    "that this these those it its their his her they them we you i he she at from "
    "into over under about which who whom whose than then so such can could may "
    "might will would should have has had do does did not no yes if while also".split()
)


def _num(token: str) -> Optional[int]:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return _WORD_NUM.get(token)


def parse_format(prompt: str) -> Dict:
    low = prompt.lower()
    fmt: Dict = {"mode": "sentences", "n": 1, "max_words_per_item": None, "max_words_total": None}

    m = re.search(r"(?:exactly\s+)?(\w+)\s+bullet", low)
    if m and _num(m.group(1)):
        fmt["mode"] = "bullets"
        fmt["n"] = _num(m.group(1))
    else:
        m = re.search(r"(?:in\s+)?(?:exactly\s+)?(\w+)\s+sentences?", low)
        if m and _num(m.group(1)):
            fmt["mode"] = "sentences"
            fmt["n"] = _num(m.group(1))
        elif re.search(r"\b(one|single|1)\s+sentence\b", low):
            fmt["mode"] = "sentences"
            fmt["n"] = 1

    m = re.search(r"(?:no longer than|no more than|under|at most|maximum of|up to)\s+(\d+)\s+words", low)
    if m:
        per = int(m.group(1))
        if fmt["mode"] == "bullets":
            fmt["max_words_per_item"] = per
        else:
            fmt["max_words_total"] = per
    return fmt


def _source_text(prompt: str) -> str:
    """Extract the passage to summarize (after the instruction / colon)."""
    # Prefer the largest quoted block, else text after the first colon.
    quoted = re.findall(r"['\"](.{40,})['\"]", prompt, re.DOTALL)
    if quoted:
        return max(quoted, key=len).strip()
    m = re.search(r":\s*(.+)$", prompt, re.DOTALL)
    text = m.group(1).strip() if m else prompt
    return text


# --------------------------------------------------------------------------
# Deterministic extractive summarizer (fallback / cross-check)
# --------------------------------------------------------------------------
def _score_sentences(sentences: List[str]) -> List[float]:
    freq: Counter = Counter()
    for s in sentences:
        for w in re.findall(r"[a-zA-Z]+", s.lower()):
            if w not in _STOPWORDS and len(w) > 2:
                freq[w] += 1
    if not freq:
        return [1.0] * len(sentences)
    maxf = max(freq.values())
    scores = []
    for s in sentences:
        words = [w for w in re.findall(r"[a-zA-Z]+", s.lower()) if w not in _STOPWORDS and len(w) > 2]
        scores.append(sum(freq[w] / maxf for w in words) / (len(words) + 1e-6))
    return scores


def _extractive(source: str, n: int) -> List[str]:
    sents = split_sentences(source)
    if not sents:
        return [normalize_whitespace(source)]
    if len(sents) <= n:
        return sents
    # Coverage-aware: split into n contiguous segments, take the top-scoring
    # sentence from each so the whole passage (both "sides") is represented.
    scores = _score_sentences(sents)
    chosen_idx: List[int] = []
    seg = len(sents) / n
    for i in range(n):
        lo, hi = int(round(i * seg)), int(round((i + 1) * seg))
        hi = max(hi, lo + 1)
        window = list(range(lo, min(hi, len(sents))))
        if not window:
            continue
        best = max(window, key=lambda j: scores[j])
        chosen_idx.append(best)
    chosen_idx = sorted(dict.fromkeys(chosen_idx))
    while len(chosen_idx) < n:  # pad if segments collided
        for j in sorted(range(len(sents)), key=lambda k: scores[k], reverse=True):
            if j not in chosen_idx:
                chosen_idx.append(j)
                break
    return [sents[i] for i in sorted(chosen_idx[:n])]


# --------------------------------------------------------------------------
# Format enforcement
# --------------------------------------------------------------------------
def _force_sentence_count(text: str, n: int) -> str:
    sents = split_sentences(text)
    if len(sents) > n:
        head = sents[: n - 1]
        tail = " ".join(sents[n - 1:])
        sents = head + [tail]
    elif len(sents) < n:
        # Split the longest sentence at a natural break to reach n.
        while len(sents) < n:
            longest = max(range(len(sents)), key=lambda i: len(sents[i]))
            parts = re.split(r"(?<=[,;:])\s+", sents[longest], maxsplit=1)
            if len(parts) < 2:
                break
            a = parts[0].rstrip(",;:") + "."
            b = parts[1][0].upper() + parts[1][1:] if parts[1] else parts[1]
            sents[longest:longest + 1] = [a, b]
    out = []
    for s in sents[:n]:
        s = s.strip()
        if s and s[-1] not in ".!?":
            s += "."
        out.append(s)
    return " ".join(out)


def _force_bullets(items: List[str], n: int, max_words: Optional[int]) -> str:
    items = [normalize_whitespace(re.sub(r"^[\-\*•\d\.\)\s]+", "", it)) for it in items if it.strip()]
    # Reach exactly n bullets.
    if len(items) > n:
        items = items[:n]
    while len(items) < n and items:
        items.append(items[-1])
    if max_words:
        items = [truncate_words(it, max_words).rstrip(",;.") for it in items]
    return "\n".join(f"- {it}" for it in items[:n])


_SUM_SYSTEM = (
    "You are a precise summarizer. Follow the exact format requested (sentence "
    "count, bullet count, and word limits). Output only the summary, no preamble."
)


def solve(prompt: str, ctx) -> Result:  # noqa: ANN001
    fmt = parse_format(prompt)
    source = _source_text(prompt)
    draft: Optional[str] = None
    method = "extractive"

    if ctx.llm is not None and ctx.llm.available and ctx.seconds_left() > 10.0:
        reply = ctx.llm.chat(_SUM_SYSTEM, prompt, max_tokens=min(ctx.config.llm_max_tokens, 224), temperature=0.2)
        if reply and reply.text:
            draft = reply.text.strip()
            method = "llm+enforced"

    if fmt["mode"] == "bullets":
        if draft:
            raw_items = [ln for ln in re.split(r"\n+", draft) if ln.strip()]
            if len(raw_items) < fmt["n"]:
                raw_items = split_sentences(draft)
        else:
            raw_items = _extractive(source, fmt["n"])
        answer = _force_bullets(raw_items, fmt["n"], fmt["max_words_per_item"])
        verified = answer.count("\n") + 1 == fmt["n"] and (
            fmt["max_words_per_item"] is None
            or all(count_words(b) <= fmt["max_words_per_item"] for b in answer.split("\n"))
        )
        proof = f"exactly {fmt['n']} bullets" + (f", each <= {fmt['max_words_per_item']} words" if fmt["max_words_per_item"] else "")
    else:
        base = draft if draft else " ".join(_extractive(source, fmt["n"]))
        answer = _force_sentence_count(base, fmt["n"])
        if fmt["max_words_total"]:
            answer = truncate_words(answer, fmt["max_words_total"])
        verified = len(split_sentences(answer)) == fmt["n"]
        proof = f"exactly {fmt['n']} sentence(s)" + (f", <= {fmt['max_words_total']} words" if fmt["max_words_total"] else "")

    return Result(
        answer=answer,
        category="text_summarization",
        method=method,
        confidence=0.9 if verified else 0.65,
        verified=verified,
        proof=proof,
    )
