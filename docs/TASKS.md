# TASKS.md — ordered build checklist

A fresh agent/IDE can (re)build ZeroProof by working top to bottom. `[x]` = done
in this repo; the order is also the recommended rebuild order.

## Phase 0 — Foundation
- [x] `config.py` — env-driven config + timing guards + valve flags
- [x] `types.py` — `Task`, `Result` (answer + proof + verified + token counts)
- [x] `io_contract.py` — tolerant reader, atomic schema-safe writer, validator
- [x] `utils/text.py`, `utils/watchdog.py` — text ops, run deadline, per-task limit

## Phase 1 — Skeleton (end-to-end at 0 tokens)
- [x] `classifier.py` — zero-token weighted-signal category classifier
- [x] `router.py` — classify → dispatch → verify → fallback; never raises
- [x] `main.py` — read/route/write loop, watchdog thread, always exit 0
- [x] Smoke test: run on practice tasks, confirm valid `results.json`

## Phase 2 — Verification substrate
- [x] `verify/executor.py` — subprocess sandbox (CPU/mem limits, timeout, offline)
- [x] `verify/executor.run_function_with_tests` — code test harness

## Phase 3 — Deterministic solvers (model-free, testable now)
- [x] `solvers/math_solver.py` — symbolic eval + program-of-thought (executed)
- [x] `solvers/arith_chain.py` — guarded operation-chain parser
- [x] math ratio/unit-cost path
- [x] `solvers/logic_solver.py` — constraint solver + self-consistency
- [x] `solvers/ner_solver.py` — spaCy + gazetteer/rule correction

## Phase 4 — Linguistic solvers + LLM
- [x] `llm/local_llm.py` — llama.cpp wrapper, lazy load, graceful degradation
- [x] `llm/fireworks_valve.py` — default-OFF, factual-only insurance valve
- [x] `solvers/sentiment_solver.py` — contrastive governance (LLM only if unsure)
- [x] `solvers/summarization_solver.py` — LLM draft + deterministic enforcement
- [x] `solvers/factual_solver.py` — LLM self-consistency medoid

## Phase 5 — Proving Ground (the iteration engine)
- [x] `proving_ground/generators.py` — 4-tier tasks with ground truth
- [x] `proving_ground/judge.py` — per-category exact/rubric scoring
- [x] `proving_ground/token_meter.py`, `constraint_sim.py`, `hardcode_guard.py`
- [x] `proving_ground/scoreboard.py` — persisted regression scoreboard
- [x] `proving_ground/run.py` — one-command MEASURE loop
- [x] Run the loop to convergence (det 100%, overall ≥95%, 0 tokens, guard clean)

## Phase 6 — Packaging & delivery
- [x] `requirements.txt` (+ `requirements-valve.txt`), `scripts/fetch_model.sh`
- [x] `Dockerfile` (slim linux/amd64, model baked at build), `entrypoint.sh`
- [x] `.dockerignore`, `.gitignore`, `.env.example`, `config/zeroproof.yaml`
- [x] `LICENSE` (MIT), `NOTICE` (model + deps attribution)
- [x] `ci/build-and-push.yml` (GHCR) — relocate to `.github/workflows/` (RUNBOOK Step 1)
- [x] `README.md`, `PROJECT.md`, `docs/*`, `deck/ZeroProof_Pitch_Deck.pdf`
- [x] Push to GitHub + attach chat bundle (both channels)

## Next levers (if pushing for more margin)
- [ ] Factual model bake-off: Phi-3.5-mini (MIT) / Qwen2.5-3B; keep if generalized accuracy improves
- [ ] Widen code test derivation (parse more example formats)
- [ ] Expand NER gazetteers / logic templates for rarer phrasings
