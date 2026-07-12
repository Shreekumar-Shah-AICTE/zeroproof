# 🛠️ RUNBOOK — ship ZeroProof to Rank #1 (operator playbook)

This is your exact, click-by-click path from the finished code to a scored
submission. **No ML knowledge required.** Follow the steps in order. Each step
says what to do, the command to paste, and what success looks like.

> **Identities you'll use**
> - GitHub account: **`Shreekumar-Shah-AICTE`** (commit email `parzivalarts@gmail.com`)
> - Repo: `https://github.com/Shreekumar-Shah-AICTE/zeroproof`
> - Image (after build): `ghcr.io/shreekumar-shah-aicte/zeroproof:latest`
> - Submit on: [lablab.ai AMD Developer Hackathon Act II](https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-ii) → Track 1

---

## ✅ Pre-flight compliance checklist (must all be true before you submit)

- [ ] **0 Fireworks tokens** — `ZP_FIREWORKS_ENABLED` is `0` (default). The run log prints `FIREWORKS TOKENS USED: 0`.
- [ ] **No external calls** at evaluation (default path makes none).
- [ ] **No hardcoded answers** — the hardcode guard prints `CLEAN`.
- [ ] **No secrets** in the image or repo (only `.env.example` placeholders).
- [ ] **Image ≤ 5 GB**, `linux/amd64`.
- [ ] **License file present** (`LICENSE` MIT + `NOTICE` with model attribution).
- [ ] Output is valid JSON, one entry per task, exits 0.

---

## Step 0 — Get the code onto GitHub (already done for you)

The full repo is already pushed to `https://github.com/Shreekumar-Shah-AICTE/zeroproof`
(branch `master`). If you ever need to push by hand from a clone:

```bash
git clone https://github.com/Shreekumar-Shah-AICTE/zeroproof.git
cd zeroproof
git config user.name "Shreekumar-Shah-AICTE"
git config user.email "parzivalarts@gmail.com"
# ...make changes...
git add -A && git commit -m "your message"
git push origin master
```

**Success looks like:** the file tree is visible on GitHub, including `src/`,
`proving_ground/`, `Dockerfile`, `README.md`, `docs/`, `deck/`.

---

## Step 1 — Activate the CI workflow (one-time, 2 minutes)

The GitHub Actions workflow ships at **`ci/build-and-push.yml`** (it couldn't be
auto-placed under `.github/workflows/` because the automated push token lacked
the `workflow` scope). Move it so Actions can see it. **Easiest: GitHub web UI.**

1. On GitHub, click **Add file → Create new file**.
2. Name it exactly: `.github/workflows/build-and-push.yml`
3. Open `ci/build-and-push.yml` in the repo, copy its entire contents, paste them
   into the new file (you can delete the top "ACTIVATION" comment block).
4. **Commit** to `master`.

*(Alternative via terminal, needs a PAT with `repo` + `workflow` scopes:)*
```bash
mkdir -p .github/workflows
cp ci/build-and-push.yml .github/workflows/build-and-push.yml
git add .github/workflows/build-and-push.yml
git commit -m "ci: activate GHCR build workflow"
git push origin master
```

**Success looks like:** the **Actions** tab shows a `build-and-push` run starting.

---

## Step 2 — Build & push the image to GHCR (automatic)

Pushing to `master` (Step 1's commit already does this) triggers the workflow. It
builds the `linux/amd64` image, **downloads the model at build time** (baked in),
and pushes `ghcr.io/shreekumar-shah-aicte/zeroproof:latest`.

1. Open the **Actions** tab → click the running `build-and-push` job.
2. Wait for a green check (first build ~8–15 min, mostly the model download).

**Success looks like:** the job is green and the run summary shows the pushed
tags. A `zeroproof` package now appears under your GitHub **Packages**.

> **Fallback (no CI / build on a Linux amd64 box or Lightning.ai CPU Studio):**
> ```bash
> docker buildx build --platform linux/amd64 \
>   -t ghcr.io/shreekumar-shah-aicte/zeroproof:latest --push .
> ```
> (Log in first: `echo $GHCR_TOKEN | docker login ghcr.io -u Shreekumar-Shah-AICTE --password-stdin`.)

---

## Step 3 — Make the image PUBLIC (critical — else PULL_ERROR)

GHCR packages default to private. The grader pulls anonymously, so:

1. GitHub → your profile → **Packages** → click **`zeroproof`**.
2. **Package settings** → **Danger Zone** → **Change visibility** → **Public** → confirm.
3. (Optional) **Connect repository** → link it to `zeroproof`.

**Success looks like:** the package page shows **Public**.

---

## Step 4 — Verify an anonymous pull (prove the grader can fetch it)

From a clean machine (or after `docker logout ghcr.io`):

```bash
docker logout ghcr.io
docker pull ghcr.io/shreekumar-shah-aicte/zeroproof:latest
```

**Success looks like:** the pull completes without a login prompt.

---

## Step 5 — Run it exactly like the grader (local smoke test)

```bash
mkdir -p input output
# put a few tasks in input/tasks.json, e.g.:
cat > input/tasks.json <<'EOF'
[
 {"task_id":"t1","prompt":"A warehouse starts with 2,400 units. In Q1 it sells 37% of stock. In Q2 it restocks 800 units. In Q3 it sells 640 units. How many units remain?"},
 {"task_id":"t2","prompt":"Extract all named entities and label each as PERSON, ORGANIZATION, LOCATION, or DATE: On March 15 2023, Sundar Pichai announced that Google would open a lab in Zurich with ETH Zurich."},
 {"task_id":"t3","prompt":"Classify the sentiment: The box was damaged, but the device works perfectly and support was fast."}
]
EOF

docker run --rm --cpus 2 --memory 4g \
  -v "$PWD/input:/input:ro" -v "$PWD/output:/output" \
  ghcr.io/shreekumar-shah-aicte/zeroproof:latest

cat output/results.json
```

**Success looks like:** `output/results.json` has one entry per task, sensible
answers, and the container logs `FIREWORKS TOKENS USED: 0` and exits without error.

---

## Step 6 — Run the Proving Ground loop (optional but recommended)

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python proving_ground/run.py --seeds 5 --per 4          # deterministic categories (fast)
# To also measure factual/code, point at a local GGUF:
python proving_ground/run.py --seeds 2 --per 3 --model /path/to/model.gguf
```

**Success looks like:** a report with per-category accuracy, `Token meter: PASS
(0 tokens)`, `Hardcode guard: CLEAN`, and a new row in
`proving_ground/SCOREBOARD.md`.

---

## Step 7 — Submit on lablab.ai (Track 1)

1. Go to the [hackathon page](https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-ii) → your team dashboard → **Submit / Edit project** → **Track 1**.
2. In the Docker image field, paste **exactly** (plain `registry/repo:tag`, no `https://`, no digest):
   ```
   ghcr.io/shreekumar-shah-aicte/zeroproof:latest
   ```
3. Fill the basic fields (title, short/long description — the README has copy),
   attach the deck PDF and repo URL where asked, and **Save**.

**Success looks like:** your entry appears on the Track 1 leaderboard within a few
minutes (scoring can lag 1–5 h under load — that's normal).

---

## Step 8 — Submission cadence (don't churn)

- **Bank a known-good qualifying image first.** The current `:latest` is that
  image (0 tokens, deterministic 100%, overall ~95%). Keep it.
- Prefer **versioned tags** for iterations (e.g. `:v2`) so you can roll back; only
  point the submission at your best tag.
- The scoring queue is slow and **resubmitting does not move you up** — submit,
  then wait. Trust the Proving Ground, not the leaderboard, for iteration.
- Submit the single best version **before the deadline**; never end on a regression.

---

## Step 9 — Rotate the token (security)

If you pushed using a personal access token, **revoke/rotate it now**:
GitHub → **Settings → Developer settings → Personal access tokens** → delete the
one you used. Never commit a token; never paste it into an issue/PR/log.

---

## 🔧 Common failures → fixes

| Symptom | Fix |
| :-- | :-- |
| `PULL_ERROR` | Make the GHCR package **Public** (Step 3); paste the exact `registry/repo:tag` with no digest/extra text; confirm the `linux/amd64` manifest exists |
| `RUNTIME_ERROR` | Test locally under `--cpus 2 --memory 4g` (Step 5); check container logs; the agent is built to exit 0 — a crash usually means a broken image build |
| `TIMEOUT` | Ensure the model is **baked in** (no runtime download); keep `ZP_N_THREADS=2`; the per-task budget + watchdog should prevent this |
| `OUTPUT_MISSING` | Confirm `/output` is writable; the agent pre-seeds and atomically writes results |
| `INVALID_RESULTS_SCHEMA` | Each entry has `task_id` + `answer`; the writer guarantees this — rebuild from the current code |
| `MISSING_TASKS` | The writer emits exactly one entry per input task; rebuild from current code |
| `ACCURACY_GATE_FAILED` | Ensure the model baked correctly; run the Proving Ground; consider the factual model bake-off (below) |
| Image too large / slow pull | Current image ~1.6 GB; if you swapped a bigger model, prefer a Q4 GGUF and keep < 5 GB |

---

## 🎛️ Optional levers

**A. Factual model bake-off (biggest accuracy lever).** To try a stronger,
license-clean model, rebuild with a different GGUF URL (no code change):
```bash
docker buildx build --platform linux/amd64 \
  --build-arg MODEL_URL="https://huggingface.co/<repo>/<phi-3.5-mini-instruct-Q4_K_M>.gguf" \
  -t ghcr.io/shreekumar-shah-aicte/zeroproof:v2 --push .
```
Measure with `proving_ground/run.py --model ...` and keep it **only if** overall
generalized accuracy improves with no regression. Stay within 4 GB RAM / ≤ 5 GB image.

**B. Insurance valve (leave OFF unless forced).** If — and only if — the Proving
Ground proves factual cannot clear the gate locally, set `ZP_FIREWORKS_ENABLED=1`
(factual-only, reasoning-off). This spends minimal tokens and **loses the 0-token
advantage**, so it is a last resort. Default and recommended: **OFF**.
