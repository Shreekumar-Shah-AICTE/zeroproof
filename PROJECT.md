# PROJECT.md — ZeroProof living source of truth

> The single source of truth for the ZeroProof build. Records every locked
> decision, the iteration history (scoreboard climb), the risk register, and the
> final state. A fresh agent/IDE should be able to continue from this file plus
> [`docs/START_HERE.md`](docs/START_HERE.md).

**Project:** ZeroProof — zero-token, proof-carrying routing agent
**Competition:** AMD Developer Hackathon Act II — Track 1 (Hybrid / Token-Efficient Routing Agent)
**Goal:** Rank #1 = clear the 80% accuracy gate with **0 Fireworks tokens** and the **highest generalized accuracy** in the 0-token cohort on the hidden, refreshed set.
**Repo:** `github.com/Shreekumar-Shah-AICTE/zeroproof` · **Image:** `ghcr.io/shreekumar-shah-aicte/zeroproof:latest`

---

## 1. Winning thesis (why this ranks #1)

0 tokens is table stakes — dozens of teams already sit at 0. The decisive,
hidden variable is **generalized accuracy in the 0-token cohort on the refreshed
set**, where overfit entries collapse (a real team went >80% local → ~52%
official). ZeroProof spends its entire budget on that variable via three moats:

1. **Algorithm moat** — widest exact-solver coverage (math, code, logic, NER). A
   correct algorithm is paraphrase-invariant; the refresh cannot break it.
2. **Verification moat** — proof-carrying answers (executed code, cross-checked
   math, constraint-solved logic, rule-corrected NER). Wrong "free" answers are
   structurally rejected.
3. **Measurement moat** — the Proving Ground optimizes the hidden-set score
   competitors can't see (paraphrase/harder/adversarial generators + judge proxy
   + token meter + constraint sim + hardcode guard + persisted scoreboard).

---

## 2. Locked decisions (do not re-litigate)

| # | Decision | Rationale |
| :- | :-- | :-- |
| D1 | **Strict ZERO tokens at eval**; Fireworks path present but **hard-OFF** | 0-token is the win path; valve is an audit-safe, factual-only insurance lever (`ZP_FIREWORKS_ENABLED`, default 0) |
| D2 | Default model **Qwen2.5-1.5B-Instruct Q4_K_M** (Apache-2.0) | Redistributable, ~1.1 GB, fits 4 GB/2 vCPU; ~3B challenger must be MIT (Phi-3.5-mini) — Qwen2.5-3B is research-license, avoided |
| D3 | Runtime **llama.cpp via llama-cpp-python** (prebuilt CPU wheel) | Self-contained, no Ollama, no runtime downloads |
| D4 | Build via **GitHub Actions → GHCR**, `docker buildx` fallback | No local Docker needed by operator |
| D5 | **Skip Gemma bonus** | Gemma-via-Fireworks costs tokens, conflicts with 0-token win |
| D6 | **Deterministic-first routing** | Instant + proof-carrying; model only for linguistic/unsolved cases → latency + token safety |
| D7 | Bank a **known-good qualifying checkpoint early**, then improve | Never end on a regression |

---

## 3. Architecture (summary)

`/input/tasks.json` → schema-safe reader → **zero-token classifier** → category
solver → **verifier/normalizer** → schema-safe writer → `/output/results.json`
(exit 0). Provable categories return proofs; linguistic categories are governed
by the local LLM with deterministic enforcement; a general local-LLM retry
handles misroutes; the default-OFF Fireworks valve is the only (opt-in) escalation.
Full detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 4. Iteration history (the Proving Ground climb)

Generalized accuracy measured on **generated paraphrase/harder/adversarial
variants** (never the public tasks). `det` = deterministic categories
(model-independent); `all` = incl. model-dependent (factual/code), measured with
the bundled 1.5B model. Live table: [`proving_ground/SCOREBOARD.md`](proving_ground/SCOREBOARD.md).

| Iteration | Change | det acc | all acc | Notes |
| :-- | :-- | :-- | :-- | :-- |
| v1 baseline | initial solvers, model absent | 88.3% | — | math 56%, sentiment 86% |
| v2 | gerund/comma parsing, ratio solver, context-aware sentiment cues | 98.3% | — | sentiment→100%, math→92% |
| v3 | first-number start fallback for chains | **100%** | — | math→100% (400/400) |
| v4 | first real-model run (1.5B) | 100% | 95.3% | exposed math PoT latency (71s!) |
| v6 | **deterministic-first + per-task budget** | 100% | **95.3%** | slowest task 71.7s→13.8s; all constraints green |

**Diagnosis→fix examples (the engine at work):**
- *Confidently-wrong parse* ("sells 15% ... and 60 more" → missed the 60): added
  an operative-number guard that refuses when any operand is unconsumed.
- *spaCy mislabels* ("Sundar Pichai"→ORG, "ETH Zurich"→PERSON): gazetteer +
  acronym + person-verb correction rules fix them → NER 100%.
- *"resolved my issue" false-negative cue*: context-aware sentiment lexicon.
- *Math PoT latency*: reordered to deterministic-first; PoT only when needed.

---

## 5. Risk register

| Risk | Severity | Mitigation | Residual |
| :-- | :-- | :-- | :-- |
| **Factual category** (no deterministic proof) | High | LLM self-consistency medoid; concise constrained answers; optional valve (OFF) | ~87–90% on 1.5B; honest top risk. Bake off Phi-3.5-mini (MIT) / Qwen2.5-3B to lift it |
| Code gen/debug on a small model | Med | generate→execute→repair; parsed example tests | ~75–100%; small-sample noise |
| Grader slower than dev host | Med | per-task budget + output caps + 9m30s watchdog + incremental writes | slowest observed 13.8s (dev); margin to 30s |
| Image pull under load | Low | image ~1.6 GB (<< 5 GB); single-arch amd64 manifest | — |
| Classifier misroute | Low | verifier + general-LLM retry; every path safe-fallbacks | — |
| Model/runtime missing | Low | graceful degradation; deterministic categories still 100%; never crashes | — |

---

## 6. Definition-of-done status

- [x] Slim `linux/amd64` image ≤ 5 GB with runtime + license-clean weights baked; nothing at runtime
- [x] Reads `/input/tasks.json`, writes valid `/output/results.json` (one/task, exact ids, English), exits 0
- [x] 0 Fireworks tokens; no external calls; no hardcoded answers; no secrets
- [x] All 8 categories handled; provable ones proof-carrying; soft ones governed + safe-fallback
- [x] Iteration engine run to convergence: **det 100%**, **overall 95.3%** (≥95% target), scoreboard shows the climb, guard clean
- [x] Runtime constraints verified green by the simulator
- [x] Pitch deck, README, RUNBOOK, handoff docs complete
- [x] Delivered via GitHub **and** chat bundle; safety checkpoint banked early

---

## 7. Honesty notes

- Deterministic-category accuracy (100%) is **measured** on generated unseen
  variants, not asserted. Numbers are reproducible via `python proving_ground/run.py`.
- Model-dependent numbers (factual/code) depend on the bundled model and were
  measured with Qwen2.5-1.5B on a dev host; the grader (2 vCPU) may differ. Re-run
  inside the image to confirm. No benchmark number is fabricated.
- The single biggest lever left is factual accuracy — see the model bake-off note
  in `NOTICE`/`config/zeroproof.yaml` and the RUNBOOK.
