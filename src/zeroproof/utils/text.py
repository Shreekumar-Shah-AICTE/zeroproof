"""Text utilities: sentence splitting, English enforcement, normalization.

Deliberately dependency-light and deterministic so behaviour is identical
across machines and refreshes.
"""
from __future__ import annotations

import re
import unicodedata
from typing import List

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_ABBREV = {"e.g.", "i.e.", "etc.", "vs.", "mr.", "mrs.", "ms.", "dr.", "prof.", "st.", "inc.", "ltd.", "u.s.", "u.k."}


def normalize_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def to_ascii_safe(text: str) -> str:
    """Best-effort transliteration of exotic unicode to ASCII-ish English text.

    Keeps common punctuation; strips control characters. The grader expects
    English output, and this guards against a model emitting stray non-English
    glyphs while preserving legitimate accented names.
    """
    text = unicodedata.normalize("NFKC", text)
    # Replace smart quotes / dashes with ASCII equivalents.
    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00a0": " ",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    # Drop control chars except newline/tab.
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or unicodedata.category(ch)[0] != "C")
    return text


def split_sentences(text: str) -> List[str]:
    """Lightweight, robust sentence splitter that respects common abbreviations."""
    text = normalize_whitespace(text.replace("\n", " "))
    if not text:
        return []
    rough = _SENTENCE_END.split(text)
    sentences: List[str] = []
    buffer = ""
    for chunk in rough:
        candidate = (buffer + " " + chunk).strip() if buffer else chunk.strip()
        last_word = candidate.split()[-1].lower() if candidate.split() else ""
        if last_word in _ABBREV:
            buffer = candidate
            continue
        sentences.append(candidate)
        buffer = ""
    if buffer:
        sentences.append(buffer.strip())
    return [s for s in sentences if s]


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def truncate_words(text: str, max_words: int) -> str:
    words = re.findall(r"\S+", text)
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).strip()


def looks_english(text: str) -> bool:
    """Heuristic: at least 85% of alphabetic characters are ASCII letters."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    ascii_letters = sum(1 for c in letters if ord(c) < 128)
    return (ascii_letters / len(letters)) >= 0.85


def first_json_block(text: str) -> str:
    """Extract the first balanced JSON object/array substring, or ''."""
    start = None
    depth = 0
    opener = closer = ""
    for i, ch in enumerate(text):
        if start is None and ch in "[{":
            start = i
            opener, closer = ch, "]" if ch == "[" else "}"
            depth = 1
        elif start is not None:
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return ""
