"""Task generators with ground truth.

The Proving Ground never tests on the public sample tasks. Instead it *generates*
fresh variants across four tiers so we measure generalization, not memorization:

  * holdout      — canonical phrasings, held out from any tuning
  * paraphrase   — same problem, reworded structure/lexicon
  * harder       — more steps / entities / trickier numbers
  * adversarial  — edges designed to fool naive solvers (year-like numbers,
                   spaCy-fooling names, subtle contrastive sentiment, ...)

Each generated task carries structured ``truth`` so the judge can score exactly
(for provable categories) or by rubric (for linguistic ones). Numbers/names are
randomized by seed, so re-running with new seeds is a genuine anti-overfit test.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List

CATEGORIES = [
    "mathematical_reasoning", "code_generation", "code_debugging",
    "logical_reasoning", "named_entity_recognition", "sentiment_analysis",
    "text_summarization", "factual_knowledge",
]
TIERS = ["holdout", "paraphrase", "harder", "adversarial"]


@dataclass
class GenTask:
    task_id: str
    prompt: str
    category: str
    tier: str
    truth: Dict[str, Any] = field(default_factory=dict)
    model_dependent: bool = False   # True => needs the local LLM to solve


# ==========================================================================
# Mathematical reasoning
# ==========================================================================
_WAREHOUSE_TEMPLATES = [
    "A {place} starts with {s:,} {unit}. In Q1 it sells {p}% of stock. In Q2 it restocks {a:,} {unit}. In Q3 it sells {b:,} {unit}. How many {unit} remain at the end of Q3?",
    "A {place} has {s:,} {unit} in inventory. It sells {p}% of them, then receives a shipment of {a:,} more, and finally sells another {b:,}. How many {unit} are left?",
    "Starting inventory at a {place} is {s:,} {unit}. After selling {p}% of the stock, adding {a:,} {unit}, and then removing {b:,} {unit}, what is the remaining count?",
]


def _gen_math(rng: random.Random, tier: str, i: int) -> GenTask:
    kind = rng.choice(["chain", "percent", "ratio"]) if tier != "holdout" else ["chain", "percent", "ratio"][i % 3]
    if kind == "percent":
        p = rng.choice([10, 15, 20, 25, 37, 40, 60, 75])
        n = rng.choice([120, 240, 360, 500, 800, 1200, 2400])
        prompt = f"What is {p}% of {n:,}?"
        return GenTask(f"math_{tier}_{i}", prompt, "mathematical_reasoning", tier, {"answer": p / 100 * n})
    if kind == "ratio":
        cups_num, cups_den = 3, 4
        base_cookies = rng.choice([12, 6, 24])
        target = rng.choice([30, 18, 36, 48])
        cost = rng.choice([2.40, 3.20, 1.60])
        sugar = (cups_num / cups_den) * target / base_cookies
        total = sugar * cost
        prompt = (f"A recipe requires {cups_num}/{cups_den} cup of sugar for {base_cookies} cookies. "
                  f"How much sugar is needed for {target} cookies? If sugar costs ${cost:.2f} per cup, "
                  f"what is the total cost of sugar for {target} cookies?")
        return GenTask(f"math_{tier}_{i}", prompt, "mathematical_reasoning", tier, {"answer": round(total, 2), "aux": round(sugar, 3)})
    # chain
    place = rng.choice(["warehouse", "store", "depot", "factory outlet"])
    unit = rng.choice(["units", "items", "boxes", "widgets"])
    s = rng.choice([1200, 2000, 2400, 3000, 3600, 5000])
    p = rng.choice([10, 15, 20, 25, 30, 37, 40])
    a = rng.choice([400, 600, 800, 1000])
    b = rng.choice([300, 420, 640, 720])
    if tier == "harder":
        # extra step
        c = rng.choice([100, 250, 500])
        after = s - round(s * p / 100) if False else s - s * p / 100
        val = after + a - b - c
        prompt = (f"A {place} starts with {s:,} {unit}. It sells {p}% of stock, then restocks {a:,} {unit}, "
                  f"then sells {b:,} {unit}, and finally sells {c:,} more {unit}. How many {unit} remain?")
        return GenTask(f"math_{tier}_{i}", prompt, "mathematical_reasoning", tier, {"answer": val})
    tmpl = rng.choice(_WAREHOUSE_TEMPLATES)
    val = (s - s * p / 100) + a - b
    prompt = tmpl.format(place=place, unit=unit, s=s, p=p, a=a, b=b)
    return GenTask(f"math_{tier}_{i}", prompt, "mathematical_reasoning", tier, {"answer": val})


# ==========================================================================
# Logical / deductive reasoning
# ==========================================================================
_LOGIC_DOMAINS = [
    ("friends", "own a different pet", "owns", ["cat", "dog", "bird", "fish", "hamster"]),
    ("colleagues", "have a different job", "is", ["doctor", "lawyer", "teacher", "engineer", "chef"]),
    ("drivers", "drive a different car", "drives", ["red", "blue", "green", "black", "white"]),
    ("students", "study a different subject", "studies", ["math", "history", "biology", "art", "music"]),
]
_NAMES = ["Sam", "Jo", "Lee", "Anna", "Bob", "Carol", "Tom", "Uma", "Vic", "Dee", "Ada", "Ben"]


def _gen_logic(rng: random.Random, tier: str, i: int) -> GenTask:
    n = 3 if tier in ("holdout", "paraphrase") else rng.choice([3, 4])
    domain = rng.choice(_LOGIC_DOMAINS)
    _, rel, verb, items_pool = domain
    names = rng.sample(_NAMES, n)
    items = rng.sample(items_pool, n)
    truth = {names[k]: items[k] for k in range(n)}  # ground-truth assignment
    target_item = rng.choice(items)
    target_owner = [nm for nm, it in truth.items() if it == target_item][0]

    # Build clues: positive for some, negative for others, ensuring the target
    # is uniquely determined. Verify uniqueness by brute force before emitting.
    clues: List[str] = []
    for k, nm in enumerate(names):
        if nm == target_owner and tier in ("harder", "adversarial"):
            continue  # force deduction for the target
        if rng.random() < (0.7 if tier != "adversarial" else 0.4):
            clues.append(f"{nm} {verb} the {truth[nm]}.")
        else:
            wrong = rng.choice([it for it in items if it != truth[nm]])
            clues.append(f"{nm} does not {('own' if verb=='owns' else verb.rstrip('s'))} the {wrong}.")
    rng.shuffle(clues)

    # Brute-force uniqueness check for the asked item.
    owners = set()
    for perm in itertools.permutations(items):
        assign = {names[k]: perm[k] for k in range(n)}
        if _consistent(assign, clues, verb):
            owners.add([nm for nm, it in assign.items() if it == target_item][0])
    if len(owners) != 1:
        # Fall back to fully-specified positive clues (always unique).
        clues = [f"{nm} {verb} the {truth[nm]}." for nm in names if nm != target_owner]
        owners = {target_owner}

    intro = f"{', '.join(names[:-1])}, and {names[-1]} each {rel}: {', '.join(items)}."
    prompt = f"{intro} {' '.join(clues)} Who {verb} the {target_item}?"
    return GenTask(f"logic_{tier}_{i}", prompt, "logical_reasoning", tier, {"owner": target_owner, "item": target_item})


def _consistent(assign: Dict[str, str], clues: List[str], verb: str) -> bool:
    import re
    for clue in clues:
        low = clue.lower()
        neg = "not" in low
        nm = next((n for n in assign if n.lower() in low), None)
        it = next((i for i in set(assign.values()) if re.search(r"\b" + re.escape(i) + r"\b", low)), None)
        if nm is None or it is None:
            continue
        if neg and assign[nm] == it:
            return False
        if not neg and assign[nm] != it:
            return False
    return True


# ==========================================================================
# Named-entity recognition
# ==========================================================================
_PEOPLE = ["Sundar Pichai", "Satya Nadella", "Tim Cook", "Maria Sanchez", "Elena Rossi",
           "James Okafor", "Wei Zhang", "Priya Nair", "Carlos Mendes", "Aisha Khan"]
_ORGS = ["Google", "Microsoft", "Apple", "Fireworks AI", "OpenAI", "ETH Zurich", "MIT", "NASA", "IBM", "Samsung"]
_LOCS = ["Zurich", "Berlin", "London", "Tokyo", "San Francisco", "Singapore", "Toronto", "Mumbai", "Paris", "Seattle"]
_DATES = ["March 15 2023", "5 June 2024", "January 2022", "2021-09-30", "12 December 2020", "August 3 2019"]
_NER_TEMPLATES = [
    "On {date}, {person} announced that {org} would open a new research lab in {loc}.",
    "{person} joined {org} in {loc} on {date}.",
    "{person}, a director at {org}, visited {loc} in {date} to sign an agreement.",
    "In {date}, {org} relocated {person} to {loc} to lead a new team.",
]


def _gen_ner(rng: random.Random, tier: str, i: int) -> GenTask:
    person = rng.choice(_PEOPLE)
    org = rng.choice(_ORGS)
    loc = rng.choice(_LOCS)
    date = rng.choice(_DATES)
    tmpl = rng.choice(_NER_TEMPLATES)
    truth = {person: "PERSON", org: "ORGANIZATION", loc: "LOCATION", date: "DATE"}
    if tier in ("harder", "adversarial"):
        org2 = rng.choice([o for o in _ORGS if o != org])
        tmpl = tmpl.rstrip(".") + f", partnering with {org2}."
        truth[org2] = "ORGANIZATION"
    sentence = tmpl.format(person=person, org=org, loc=loc, date=date)
    prompt = (f"Extract all named entities from the following text and label each as "
              f"PERSON, ORGANIZATION, LOCATION, or DATE: {sentence}")
    return GenTask(f"ner_{tier}_{i}", prompt, "named_entity_recognition", tier, {"entities": truth})


# ==========================================================================
# Sentiment analysis
# ==========================================================================
_NEG_ASPECTS = [("delivery", "arrived two days late"), ("packaging", "was damaged"),
                ("box", "was dented"), ("manual", "was missing"), ("screen", "scratches easily"),
                ("battery", "drains quickly")]
_POS_ASPECTS = [("product", "works perfectly"), ("device", "is flawless"), ("support team", "resolved my issue fast"),
                ("setup", "took under five minutes"), ("build quality", "feels premium"), ("app", "is intuitive")]


def _gen_sentiment(rng: random.Random, tier: str, i: int) -> GenTask:
    mode = rng.choice(["mixed", "mixed", "positive", "negative"]) if tier != "holdout" else ["mixed", "positive", "negative"][i % 3]
    if mode == "mixed":
        neg = rng.choice(_NEG_ASPECTS)
        pos = rng.choice(_POS_ASPECTS)
        conj = rng.choice(["but", "however,", "though", "yet"])
        text = f"The {neg[0]} {neg[1]}, {conj} the {pos[0]} {pos[1]}."
        truth = {"acceptable": ["Mixed", "Neutral", "Positive"], "both_sides": True}
    elif mode == "positive":
        pos = rng.sample(_POS_ASPECTS, 2)
        text = f"The {pos[0][0]} {pos[0][1]} and the {pos[1][0]} {pos[1][1]}."
        truth = {"acceptable": ["Positive"], "both_sides": False}
    else:
        neg = rng.sample(_NEG_ASPECTS, 2)
        text = f"The {neg[0][0]} {neg[0][1]} and the {neg[1][0]} {neg[1][1]}. Very disappointing."
        truth = {"acceptable": ["Negative"], "both_sides": False}
    lead = rng.choice(["customer review", "tweet", "product review", "feedback"])
    prompt = (f"Classify the sentiment of this {lead} as Positive, Negative, or Neutral and "
              f"give a one-sentence reason: '{text}'")
    return GenTask(f"sent_{tier}_{i}", prompt, "sentiment_analysis", tier, truth)


# ==========================================================================
# Text summarization
# ==========================================================================
_TOPICS = [
    ("machine learning in healthcare", ["diagnosis", "images", "privacy", "bias", "regulation"]),
    ("remote work", ["flexibility", "commute", "collaboration", "culture", "tools"]),
    ("electric vehicles", ["emissions", "battery", "charging", "cost", "grid"]),
    ("cloud computing", ["scalability", "cost", "security", "latency", "migration"]),
]


def _gen_summ(rng: random.Random, tier: str, i: int) -> GenTask:
    topic, points = rng.choice(_TOPICS)
    sents = [
        f"{topic.capitalize()} is transforming how organizations operate.",
        f"It offers clear benefits such as {points[0]} and {points[1]}.",
        f"However, challenges remain around {points[2]} and {points[3]}.",
        f"Adoption also depends on {points[4]} keeping pace with change.",
    ]
    passage = " ".join(sents)
    if rng.random() < 0.5:
        n = rng.choice([2, 3])
        prompt = f"Summarize the following passage in exactly {['','one','two','three','four'][n]} sentences: {passage}"
        truth = {"mode": "sentences", "n": n, "keywords": points}
    else:
        n = 3
        w = rng.choice([12, 15])
        prompt = f"Summarize the following passage in exactly three bullet points, each no longer than {w} words: {passage}"
        truth = {"mode": "bullets", "n": n, "max_words": w, "keywords": points}
    return GenTask(f"summ_{tier}_{i}", prompt, "text_summarization", tier, truth)


# ==========================================================================
# Factual knowledge (model-dependent; keyword rubric)
# ==========================================================================
_FACTS = [
    ("What are the three primary colors in the RGB color model?", ["red", "green", "blue"]),
    ("What is the capital of Australia?", ["canberra"]),
    ("What is the capital of France?", ["paris"]),
    ("What is the difference between RAM and ROM?", ["volatile", "non-volatile"]),
    ("What is the boiling point of water at sea level in Celsius?", ["100"]),
    ("Who developed the theory of general relativity?", ["einstein"]),
    ("What gas do plants absorb during photosynthesis?", ["carbon dioxide"]),
    ("What is the largest planet in our solar system?", ["jupiter"]),
    ("What is the chemical symbol for gold?", ["au"]),
    ("How many continents are there on Earth?", ["seven", "7"]),
    ("What is the difference between machine learning and deep learning?", ["neural", "subset"]),
    ("What is the powerhouse of the cell?", ["mitochond"]),
]


def _gen_factual(rng: random.Random, tier: str, i: int) -> GenTask:
    q, kws = rng.choice(_FACTS)
    return GenTask(f"fact_{tier}_{i}", q, "factual_knowledge", tier, {"keywords": kws}, model_dependent=True)


# ==========================================================================
# Code generation & debugging (model-dependent; executed tests)
# ==========================================================================
_CODEGEN = [
    ("Write a Python function `second_largest(nums)` that returns the second-largest number in a list, handling duplicates correctly.",
     "second_largest", [{"args": [[1, 2, 3, 3]], "expected": 2}, {"args": [[5, 5, 4]], "expected": 4}, {"args": [[10]], "expected": None}]),
    ("Write a Python function `is_palindrome(s)` that returns True if the string is a palindrome ignoring case and spaces.",
     "is_palindrome", [{"args": ["Race car"], "expected": True}, {"args": ["hello"], "expected": False}]),
    ("Write a Python function `factorial(n)` that returns n! for non-negative integers.",
     "factorial", [{"args": [5], "expected": 120}, {"args": [0], "expected": 1}]),
    ("Write a Python function `count_vowels(s)` that returns the number of vowels (a,e,i,o,u) in a string, case-insensitive.",
     "count_vowels", [{"args": ["Hello"], "expected": 2}, {"args": ["xyz"], "expected": 0}]),
]
_DEBUG = [
    ("This function should return the maximum of a list but has a bug: def get_max(nums): return nums[0]. Find and fix it.",
     "get_max", [{"args": [[3, 7, 2]], "expected": 7}, {"args": [[-1, -5]], "expected": -1}]),
    ("This function should sum a list but has a bug: def total(xs): s=0\\n for x in xs: s=x\\n return s. Fix it.",
     "total", [{"args": [[1, 2, 3]], "expected": 6}, {"args": [[]], "expected": 0}]),
]


def _gen_code(rng: random.Random, tier: str, i: int, debug: bool) -> GenTask:
    if debug:
        prompt, func, tests = rng.choice(_DEBUG)
        cat = "code_debugging"
        tid = f"debug_{tier}_{i}"
    else:
        prompt, func, tests = rng.choice(_CODEGEN)
        cat = "code_generation"
        tid = f"codegen_{tier}_{i}"
    return GenTask(tid, prompt, cat, tier, {"func": func, "tests": tests}, model_dependent=True)


# ==========================================================================
# Orchestration
# ==========================================================================
_GEN = {
    "mathematical_reasoning": _gen_math,
    "logical_reasoning": _gen_logic,
    "named_entity_recognition": _gen_ner,
    "sentiment_analysis": _gen_sentiment,
    "text_summarization": _gen_summ,
    "factual_knowledge": _gen_factual,
}


def generate_suite(seed: int, per_category_per_tier: int = 4) -> List[GenTask]:
    rng = random.Random(seed)
    tasks: List[GenTask] = []
    for tier in TIERS:
        for _ in range(per_category_per_tier):
            for cat, fn in _GEN.items():
                tasks.append(fn(rng, tier, len(tasks)))
            tasks.append(_gen_code(rng, tier, len(tasks), debug=False))
            tasks.append(_gen_code(rng, tier, len(tasks), debug=True))
    return tasks
