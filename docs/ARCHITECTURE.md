# ARCHITECTURE.md — ZeroProof system design

## 1. Contract (the immovable boundary)

- **Input:** `/input/tasks.json` — a JSON list of `{ "task_id", "prompt" }`.
- **Output:** `/output/results.json` — a JSON list of `{ "task_id", "answer" }`,
  exactly one entry per input task, exact ids preserved, non-empty English
  answers, valid JSON, process exits 0.
- **Environment:** CPU-only, 2 vCPU / 4 GB RAM, ≤ 10 min total, container ready
  < 60 s, each task < 30 s, image `linux/amd64` ≤ 5 GB, no runtime network.
- **Security:** task content is **untrusted data**, never instructions. No prompt
  in `tasks.json` can change control flow; model output is never executed
  in-process (only in a locked sandbox).

## 2. Data flow

```
main.run()
  read_tasks(/input/tasks.json)            # io_contract — tolerant parsing
  pre-seed /output/results.json fallback   # output exists immediately (<60s ready)
  build_context()                          # config + LocalLLM(lazy) + FireworksValve(OFF)
  start watchdog thread                    # flush + exit 0 near 9m30s
  for task in tasks:
     set per-task time budget (ctx.seconds_left)
     route(task, ctx) ---------------------> classify -> solve -> verify -> normalize
     record answer; snapshot every 3 tasks
  write_results (atomic) + validate
  log FIREWORKS TOKENS USED (must be 0); exit 0
```

## 3. Components (`src/zeroproof/`)

| Module | Responsibility |
| :-- | :-- |
| `config.py` | All tunables via env; timing guards; valve flags |
| `io_contract.py` | Tolerant reader, schema-safe atomic writer, contract validator |
| `classifier.py` | Zero-token category classifier (weighted intent signals) |
| `router.py` | Orchestration: classify → dispatch → verify → fallback; never raises |
| `main.py` | Entrypoint, watchdog, incremental durability, always exit 0 |
| `types.py` | `Task`, `Result` (answer + proof + verified + tokens) |
| `solvers/math_solver.py` | symbolic eval · arithmetic-chain · ratio · program-of-thought (executed) |
| `solvers/arith_chain.py` | high-precision operation-chain parser (refuses when ambiguous) |
| `solvers/code_solver.py` | generate/debug → execute against tests → repair loop |
| `solvers/logic_solver.py` | constraint solver (proof) + LLM self-consistency |
| `solvers/ner_solver.py` | spaCy + gazetteer/acronym/person-verb correction |
| `solvers/sentiment_solver.py` | contrastive-cue governance + LLM only when uncertain |
| `solvers/summarization_solver.py` | LLM draft + deterministic count/word-cap enforcement |
| `solvers/factual_solver.py` | LLM self-consistency medoid (top risk) |
| `verify/executor.py` | subprocess sandbox: CPU/mem limits, timeout, offline |
| `llm/local_llm.py` | llama.cpp wrapper; lazy load; graceful degradation; token accounting |
| `llm/fireworks_valve.py` | default-OFF, factual-only, reasoning-off insurance valve |
| `utils/text.py` | sentence split, English enforcement, JSON extraction |
| `utils/watchdog.py` | run deadline + per-task time limit |

## 4. Routing policy

1. **Classify** (0 tokens) → category + confidence.
2. **Solve** via the category solver. Provable categories try **deterministic
   paths first** (instant, proof-carrying); linguistic categories use the local
   model with deterministic post-processing.
3. **Verify/normalize**: a `Result` is *trusted* if `verified` or
   `confidence ≥ 0.5`. English-only + non-empty enforced by the writer.
4. **Fallbacks** (still 0 tokens): weak/empty → general local-LLM retry.
5. **Fireworks valve**: only if the operator set `ZP_FIREWORKS_ENABLED=1` **and**
   category ∈ allowed (default `factual_knowledge`). Off by default → never fires.
6. Any exception anywhere → safe fallback string for that task. The run never dies.

## 5. Why proof-carrying

A `Result.verified=True` means the answer was checked by construction:
- **math** — the number came from executed code / a guarded operation chain / a
  symbolic evaluation;
- **code** — the code ran and passed parsed/derived tests;
- **logic** — a constraint model yielded a unique answer for the asked item;
- **NER** — spans corrected by high-precision rules/gazetteers.

Unverifiable categories (factual) are explicitly `verified=False` and treated as
best-effort — never dressed up as proven.

## 6. Build order (for a rebuild)

1. I/O contract + types + config (the boundary).
2. Classifier + router skeleton + main + watchdog (end-to-end skeleton).
3. Sandbox executor (unlocks math PoT + code).
4. Deterministic solvers (math, logic, NER) — testable without a model.
5. Linguistic solvers (sentiment, summarization, factual) + LLM wrapper.
6. Proving Ground (generators, judge, meters, guard, scoreboard).
7. Run the iteration engine to convergence.
8. Dockerfile + CI + docs + deck. Ship.
