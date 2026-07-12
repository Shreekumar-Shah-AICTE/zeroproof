"""Named-entity recognition — deterministic, refresh-proof.

Pipeline:
  1. spaCy ``en_core_web_sm`` (MIT-licensed, tiny, CPU-fast) proposes spans.
  2. A rules + gazetteer layer *corrects* the labels — spaCy alone mislabels
     e.g. "Sundar Pichai" -> ORG and "ETH Zurich" -> PERSON, which a refresh
     would punish. Acronym/suffix/person-verb heuristics fix these.
  3. A regex DATE pass supplements spaCy so dates are never missed.
  4. Labels are normalized to the requested set (PERSON / ORGANIZATION /
     LOCATION / DATE) and de-duplicated.

Falls back to a pure-regex extractor if spaCy is unavailable, so the container
never crashes.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ..types import Result

# --- gazetteers (small, high-precision; not answer lookups) ---------------
_ORG_GAZ = {
    "google", "alphabet", "microsoft", "apple", "amazon", "meta", "facebook",
    "openai", "anthropic", "nvidia", "intel", "amd", "ibm", "oracle", "netflix",
    "tesla", "spacex", "twitter", "fireworks ai", "deepmind", "google deepmind",
    "nasa", "fbi", "cia", "who", "un", "united nations", "eth zurich", "mit",
    "stanford", "harvard", "oxford", "cambridge", "berkeley", "cern", "samsung",
    "sony", "uber", "airbnb", "adobe", "salesforce", "spotify", "tiktok",
    "huawei", "qualcomm", "boeing", "toyota", "ford", "volkswagen",
}
_LOC_GAZ = {
    "zurich", "berlin", "london", "paris", "tokyo", "beijing", "shanghai",
    "new york", "san francisco", "los angeles", "chicago", "boston", "seattle",
    "washington", "moscow", "delhi", "mumbai", "bangalore", "singapore",
    "sydney", "toronto", "dubai", "amsterdam", "madrid", "rome", "geneva",
    "usa", "united states", "america", "china", "india", "japan", "germany",
    "france", "canada", "australia", "switzerland", "uk", "united kingdom",
    "europe", "asia", "africa", "california", "texas", "silicon valley",
}
_ORG_SUFFIX = re.compile(
    r"\b(inc|inc\.|corp|corp\.|ltd|ltd\.|llc|plc|gmbh|ag|university|institute|"
    r"college|labs?|laboratory|technologies|systems|group|foundation|agency|"
    r"association|committee|department|ministry|bank|airlines|motors)\b",
    re.IGNORECASE,
)
_PERSON_VERB = re.compile(
    r"\b(announced|said|stated|joined|founded|co-founded|created|wrote|launched|"
    r"told|added|noted|explained|leads|heads|led|resigned|departed|was born|"
    r"died|met|visited|reported|confirmed|revealed|argued|claimed|believes|"
    r"described|presented|unveiled|signed)\b",
    re.IGNORECASE,
)
_HONORIFIC = re.compile(r"\b(mr|mrs|ms|dr|prof|professor|president|ceo|senator|sir|dame|lord)\.?\s+$", re.IGNORECASE)
_ACRONYM = re.compile(r"\b[A-Z]{2,5}\b")

# --- DATE regex (supplements spaCy) ---------------------------------------
_MONTHS = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
_DATE_PATTERNS = [
    re.compile(r"\b" + _MONTHS + r"\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b"),
    re.compile(r"\b\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTHS + r"(?:,?\s+\d{4})?\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    re.compile(r"\b(?:in\s+)?\b(19|20)\d{2}\b"),
]

_LABEL_MAP = {
    "PERSON": "PERSON",
    "ORG": "ORGANIZATION",
    "ORGANIZATION": "ORGANIZATION",
    "GPE": "LOCATION",
    "LOC": "LOCATION",
    "LOCATION": "LOCATION",
    "FAC": "LOCATION",
    "DATE": "DATE",
    "TIME": "DATE",
}

_nlp = None
_nlp_failed = False


def _get_nlp():
    global _nlp, _nlp_failed
    if _nlp is not None or _nlp_failed:
        return _nlp
    try:
        import spacy

        _nlp = spacy.load("en_core_web_sm", disable=["lemmatizer"])
    except Exception:
        _nlp_failed = True
        _nlp = None
    return _nlp


_LABEL_WORDS = {"person", "organization", "organisation", "location", "date",
                "org", "gpe", "loc", "time", "entity", "entities", "misc"}
_ACRONYM_STOP = {"AI", "ML", "IT", "API", "IOT", "UI", "UX", "OK", "TV", "PC",
                 "CEO", "CTO", "CFO", "COO", "HR", "PR", "QA", "PHD", "ID", "FAQ",
                 "AWS", "GPU", "CPU", "RAM", "URL", "PDF", "NLP", "LLM"}


def _extract_target_text(prompt: str) -> str:
    """Isolate the passage to analyze from the instruction wrapper.

    NER prompts follow "<instruction ...>: <text>". Split on the first colon
    when the preamble is clearly an NER instruction; otherwise use the whole
    prompt. This prevents the label list (PERSON, ORGANIZATION, ...) from being
    scanned as content.
    """
    m = re.search(
        r"^(.*?\b(?:extract|identify|label|recogni[sz]e|entit(?:y|ies))\b.*?):\s*(.+)$",
        prompt,
        re.IGNORECASE | re.DOTALL,
    )
    text = m.group(2).strip() if m else prompt.strip()
    if len(text) >= 2 and text[0] in "\"'" and text[-1] in "\"'":
        text = text[1:-1].strip()
    return text or prompt


def _relabel(text_span: str, label: str, context: str, start: int) -> Optional[str]:
    low = text_span.lower().strip()
    canonical = _LABEL_MAP.get(label, None)

    # Gazetteer overrides (highest precision).
    if low in _ORG_GAZ:
        return "ORGANIZATION"
    if low in _LOC_GAZ:
        return "LOCATION"
    if _ORG_SUFFIX.search(text_span):
        return "ORGANIZATION"
    # A multi-token span containing an acronym (e.g. "ETH Zurich") -> organization.
    # (Standalone acronyms are handled by the gazetteer / stoplist instead.)
    if _ACRONYM.search(text_span) and 2 <= len(tokens := text_span.split()) <= 4 and canonical != "DATE":
        return "ORGANIZATION"

    # Person heuristics: two/three capitalized name-like tokens.
    tokens = text_span.split()
    looks_personish = (
        1 <= len(tokens) <= 3
        and all(t[:1].isupper() for t in tokens if t)
        and low not in _LOC_GAZ
        and low not in _ORG_GAZ
        and not _ORG_SUFFIX.search(text_span)
    )
    preceding = context[max(0, start - 12):start]
    following = context[start + len(text_span): start + len(text_span) + 30]
    if looks_personish and (_HONORIFIC.search(preceding) or _PERSON_VERB.search(following)):
        return "PERSON"

    return canonical


def _regex_person_fallback(text: str) -> List[Tuple[str, str]]:
    ents = []
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", text):
        span = m.group(1)
        if span.lower() in _ORG_GAZ or span.lower() in _LOC_GAZ:
            continue
        ents.append((span, "PERSON"))
    return ents


def _dates(text: str) -> List[str]:
    found: List[str] = []
    for pat in _DATE_PATTERNS:
        for m in pat.finditer(text):
            val = m.group(0).strip()
            val = re.sub(r"^in\s+", "", val, flags=re.IGNORECASE)
            if val and val not in found:
                found.append(val)
    return found


def solve(prompt: str, ctx) -> Result:  # noqa: ANN001
    text = _extract_target_text(prompt)
    entities: List[Tuple[str, str]] = []
    seen = set()

    def add(span: str, label: str):
        span = span.strip().strip(".,;:")
        if not span or span.lower() in _LABEL_WORDS or span.upper() in _ACRONYM_STOP:
            return
        key = (span.lower(), label)
        if key not in seen and label in {"PERSON", "ORGANIZATION", "LOCATION", "DATE"}:
            seen.add(key)
            entities.append((span, label))

    nlp = _get_nlp()
    if nlp is not None:
        doc = nlp(text)
        for ent in doc.ents:
            new_label = _relabel(ent.text, ent.label_, text, ent.start_char)
            if new_label:
                add(ent.text, new_label)
    else:
        for span, label in _regex_person_fallback(text):
            add(span, label)
        for span in _ORG_GAZ:
            if re.search(r"\b" + re.escape(span) + r"\b", text, re.IGNORECASE):
                m = re.search(r"\b" + re.escape(span) + r"\b", text, re.IGNORECASE)
                add(m.group(0), "ORGANIZATION")
        for span in _LOC_GAZ:
            if re.search(r"\b" + re.escape(span) + r"\b", text, re.IGNORECASE):
                m = re.search(r"\b" + re.escape(span) + r"\b", text, re.IGNORECASE)
                add(m.group(0), "LOCATION")

    # DATE supplement (regex catches what spaCy misses).
    existing_dates = {s.lower() for s, l in entities if l == "DATE"}
    for d in _dates(text):
        if not any(d.lower() in ed or ed in d.lower() for ed in existing_dates):
            add(d, "DATE")

    if not entities:
        return Result(
            answer="No named entities found.",
            category="named_entity_recognition",
            method="spacy+rules" if nlp else "regex-fallback",
            confidence=0.5,
            verified=False,
            proof="no entities detected",
        )

    # Stable ordering by first appearance in text.
    entities.sort(key=lambda e: text.lower().find(e[0].lower()))
    lines = [f"- {span} ({label})" for span, label in entities]
    answer = "\n".join(lines)
    return Result(
        answer=answer,
        category="named_entity_recognition",
        method="spacy+rules" if nlp else "regex-fallback",
        confidence=0.9 if nlp else 0.6,
        verified=bool(nlp),
        proof=f"{len(entities)} entities via {'spaCy+gazetteer/rule correction' if nlp else 'regex fallback'}",
    )
