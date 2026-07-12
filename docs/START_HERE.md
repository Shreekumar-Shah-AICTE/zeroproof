# START_HERE.md — kickoff for a fresh, context-free agent or IDE

You are picking up **ZeroProof**, a zero-token, proof-carrying routing agent for
the AMD Developer Hackathon Act II — Track 1. This file gets you productive in
five minutes with **no prior conversation**.

## What this is (30 seconds)
Track 1 ranks agents that clear an 80% accuracy gate by **fewest Fireworks
tokens**. Everyone converges on 0 tokens, so the real battle is **generalized
accuracy in the 0-token cohort on a hidden, refreshed task set**. ZeroProof wins
it by **proving** answers with deterministic solvers (math/code/logic/NER) and
governing linguistic answers (factual/sentiment/summary) with a bundled small
local LLM — **0 Fireworks tokens**.

## Read these, in order
1. `PROJECT.md` — decisions, iteration history, risk register, current state.
2. `docs/ARCHITECTURE.md` — system design and the request/response contract.
3. `docs/QUALITY_ENGINE.md` — the Proving Ground (how we measure & improve).
4. `docs/RUNBOOK.md` — how to build, publish, and submit (operator steps).
5. `docs/TASKS.md` — the ordered build checklist (what's done / next).

## Set up (local dev)
```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
# Run the agent on some tasks (deterministic categories work with no model):
mkdir -p input output
echo '[{"task_id":"t1","prompt":"What is 15% of 240?"}]' > input/tasks.json
PYTHONPATH=src ZP_INPUT=input/tasks.json ZP_OUTPUT=output/results.json python -m zeroproof.main
cat output/results.json
```

## Measure generalization (the oracle)
```bash
python proving_ground/run.py --seeds 5 --per 4                 # model-free (deterministic)
python proving_ground/run.py --seeds 2 --per 3 --model model.gguf   # incl. factual/code
```
The report prints per-category accuracy, the token meter (must be 0), the
constraint simulator, and the hardcode guard, and updates
`proving_ground/SCOREBOARD.md`.

## The golden rules
- **Never** hardcode/cache answers. **Never** add non-Fireworks network calls.
- Optimize for **unseen generated variants**, never the public sample tasks.
- Deterministic categories must stay **proof-carrying**; keep the Fireworks valve
  **OFF** by default.
- Change → re-measure across seeds → keep only if generalized accuracy improves
  with **zero regression** and the guard stays clean; otherwise revert.
- Every task must return a non-empty English answer; the container must exit 0.

## Ship it
Follow `docs/RUNBOOK.md`: activate CI (`ci/build-and-push.yml` →
`.github/workflows/`), let GHCR build the image (model baked at build), make the
package **public**, verify an anonymous pull, then submit the plain
`ghcr.io/shreekumar-shah-aicte/zeroproof:latest` on lablab.ai Track 1.
