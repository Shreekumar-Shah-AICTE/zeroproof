# QUALITY_ENGINE.md — the Proving Ground & Iteration Engine

The Proving Ground is **not** a final check. It is a closed optimization loop —
the single most important activity in this build — that optimizes the *hidden
refreshed set* score competitors can't see. The leaderboard is too slow
(~1.5–5 h/submission) to iterate against, so **the Proving Ground is the oracle**.

## Run it

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm      # once
python proving_ground/run.py --seeds 5 --per 4                # deterministic categories
python proving_ground/run.py --seeds 2 --per 3 --model /models/model.gguf   # incl. factual/code
```

Outputs a per-category / per-tier report, the token meter, the constraint
simulator, the hardcode guard, and appends a row to
[`proving_ground/SCOREBOARD.md`](../proving_ground/SCOREBOARD.md).

## The loop (run relentlessly)

1. **MEASURE** — generate the full suite across seeds (holdout + paraphrase +
   harder + adversarial), judge every answer, meter tokens (must read 0),
   simulate constraints, run the hardcode guard, log to the scoreboard.
2. **DIAGNOSE** — for every miss, find the true root cause (solver gap, verifier
   miss, misroute, format/length violation, timeout, model weakness). Attack the
   highest-leverage failure first.
3. **IMPROVE** — one targeted change (widen a solver, tighten a verifier, fix a
   route, add a normalization rule, cap decoding, swap the model).
4. **RE-MEASURE & GUARD** — re-run across seeds. Keep the change only if
   generalized accuracy improves with **zero regression** and the guard stays
   clean; else revert. Bank each new best.
5. **REPEAT** — until the championship-locked condition holds, then keep hunting
   the weakest category (expected: factual).

## Components (`proving_ground/`)

| Module | Role |
| :-- | :-- |
| `generators.py` | Parameterized tasks **with ground truth** across 4 tiers; randomized by seed so re-runs are a genuine anti-overfit test |
| `judge.py` | Per-category scoring — exact for provable categories (numeric/entity/executed-tests/unique-owner), rubric for linguistic (sentiment labels + both-sides; exact summary counts/caps; factual keyword coverage) |
| `token_meter.py` | Proves Fireworks tokens == 0 |
| `constraint_sim.py` | Enforces per-task/total latency, ready time, peak RSS; **fails loudly** |
| `hardcode_guard.py` | Canary scan (no public-set answers embedded) + lookup-table scan; whitelists legitimate gazetteers |
| `scoreboard.py` | Persisted regression scoreboard (`.jsonl` + rendered `SCOREBOARD.md`) |
| `run.py` | One-command MEASURE → report → scoreboard |

## Anti-overfitting is the whole game

- We optimize for the **hidden refreshed set**, never the public tasks. Any
  trusted number comes from paraphrased/unseen generated variants.
- A gain that only shows on the sample tasks is a trap — rejected.
- The hardcode guard makes memorization structurally detectable.

## Championship-locked stop condition

- **≥ 95% generalized accuracy** across seeds/paraphrases (unseen variants), with
  margin over the 80% gate;
- **0 Fireworks tokens** proven by the meter;
- every runtime constraint green in the simulator;
- schema/output contract perfect; image ≤ 5 GB; hardcode-guard clean.

**Current state:** deterministic categories **100%** (400/400, model-free);
overall incl. bundled 1.5B model **95.3%**; 0 tokens; constraints green; guard
clean. Weakest category = factual (~87–90%) — the documented residual risk and
the next lever (model bake-off).
