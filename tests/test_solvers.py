"""Deterministic solver tests — run with `pytest -q` (no model required).

These pin the proof-carrying behaviour of the model-free categories so a
regression is caught immediately. Model-dependent categories (factual, code
generation/debugging) are covered by the Proving Ground with a bundled GGUF.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from zeroproof.classifier import classify  # noqa: E402
from zeroproof.config import Config  # noqa: E402
from zeroproof.io_contract import build_results, validate_results  # noqa: E402
from zeroproof.types import Task  # noqa: E402
from zeroproof.solvers import (  # noqa: E402
    logic_solver, math_solver, ner_solver, sentiment_solver, summarization_solver,
)
from zeroproof.verify.executor import run_code, run_function_with_tests  # noqa: E402


def _ctx():
    return SimpleNamespace(config=Config(), llm=None, seconds_left=lambda: 999.0)


# ---- classifier ----------------------------------------------------------
def test_classifier_routes_samples():
    cases = {
        "What is the difference between RAM and ROM?": "factual_knowledge",
        "A store has 240 items. It sells 15% on Monday and 60 more. How many remain?": "mathematical_reasoning",
        "Classify the sentiment of this review: it was great but slow.": "sentiment_analysis",
        "Summarize the following passage in exactly two sentences: ...": "text_summarization",
        "Extract all named entities and label each as PERSON, ORGANIZATION, LOCATION, or DATE: ...": "named_entity_recognition",
        "This function has a bug: def f(x): return x[0]. Find and fix it.": "code_debugging",
        "Three friends each own a different pet. Who owns the cat?": "logical_reasoning",
        "Write a Python function that returns the second-largest number.": "code_generation",
    }
    for prompt, expected in cases.items():
        assert classify(prompt).category == expected, (prompt, classify(prompt).category)


# ---- math ----------------------------------------------------------------
def test_math_chain():
    r = math_solver.solve(
        "A warehouse starts with 2,400 units. In Q1 it sells 37% of stock. "
        "In Q2 it restocks 800 units. In Q3 it sells 640 units. How many units remain?",
        _ctx(),
    )
    assert "1,672" in r.answer and r.verified


def test_math_percent():
    r = math_solver.solve("What is 15% of 240?", _ctx())
    assert "36" in r.answer and r.verified


def test_math_ratio():
    r = math_solver.solve(
        "A recipe requires 3/4 cup of sugar for 12 cookies. How much sugar for 30 cookies? "
        "If sugar costs $2.40 per cup, what is the total cost?",
        _ctx(),
    )
    assert "4.5" in r.answer and r.verified


def test_math_gerund_and_is_start():
    r = math_solver.solve(
        "Starting inventory at a store is 2,400 items. After selling 30% of the stock, "
        "adding 1,000 items, and then removing 300 items, what is the remaining count?",
        _ctx(),
    )
    # 2400 - 30% = 1680; +1000 = 2680; -300 = 2380
    assert "2,380" in r.answer and r.verified


# ---- logic ---------------------------------------------------------------
def test_logic_constraint():
    r = logic_solver.solve(
        "Three friends, Sam, Jo, and Lee, each own a different pet: cat, dog, bird. "
        "Sam does not own the bird. Jo owns the dog. Who owns the cat?",
        _ctx(),
    )
    assert "sam" in r.answer.lower() and r.verified


# ---- NER -----------------------------------------------------------------
def test_ner_corrects_spacy():
    r = ner_solver.solve(
        "Extract all named entities and label each as PERSON, ORGANIZATION, LOCATION, or DATE: "
        "On March 15 2023, Sundar Pichai announced that Google would open a lab in Zurich with ETH Zurich.",
        _ctx(),
    )
    low = r.answer.lower()
    assert "sundar pichai (person)" in low
    assert "google (organization)" in low
    assert "zurich (location)" in low
    assert "eth zurich (organization)" in low


# ---- sentiment -----------------------------------------------------------
def test_sentiment_mixed_not_negative():
    r = sentiment_solver.solve(
        "Classify the sentiment: 'The delivery arrived late and the box was damaged, "
        "but the product works perfectly and support resolved my issue fast.'",
        _ctx(),
    )
    assert "negative" not in r.answer.split(".")[0].lower()  # label isn't Negative
    assert r.verified


# ---- summarization -------------------------------------------------------
def test_summ_exact_sentences():
    r = summarization_solver.solve(
        "Summarize the following passage in exactly two sentences: "
        "Cloud computing scales on demand. It raises cost and security questions. "
        "Adoption depends on migration effort. Latency also matters.",
        _ctx(),
    )
    from zeroproof.utils.text import split_sentences
    assert len(split_sentences(r.answer)) == 2


def test_summ_bullets_word_cap():
    r = summarization_solver.solve(
        "Summarize the following passage in exactly three bullet points, each no longer than 12 words: "
        "Remote work boosts flexibility. It challenges collaboration and culture. Firms invest in tools.",
        _ctx(),
    )
    from zeroproof.utils.text import count_words
    bullets = [b for b in r.answer.split("\n") if b.strip()]
    assert len(bullets) == 3
    assert all(count_words(b.lstrip("- ")) <= 12 for b in bullets)


# ---- executor ------------------------------------------------------------
def test_executor_timeout():
    res = run_code("while True: pass", timeout=2)
    assert res.timed_out and not res.ok


def test_executor_tests():
    sol = "def f(xs):\n    u=sorted(set(xs))\n    return u[-2] if len(u)>=2 else None"
    res = run_function_with_tests(sol, "f", [{"args": [[1, 2, 2, 3]], "expected": 2}])
    assert res.result["defined"] and res.result["results"][0]["ok"]


# ---- contract ------------------------------------------------------------
def test_contract_validation():
    tasks = [Task("a", "x"), Task("b", "y")]
    results = build_results(tasks, {"a": "ans", "b": ""}, "FALLBACK")
    assert results[1]["answer"] == "FALLBACK"  # empty coerced to fallback
    assert validate_results(tasks, results) == []
