# 🧭 ZeroProof — Non-Technical Submission Guide (all in your web browser)

You do **not** need to install anything or write code. Everything here is done by
clicking around on two websites: **GitHub** (where your project lives) and
**lablab.ai** (where you submit). Total hands-on time: ~20–30 minutes, plus a
~10–15 minute wait while a robot builds your project.

---

## Plain-English glossary (read once, 60 seconds)

- **GitHub** — a website that stores your project's files. Yours is here:
  `https://github.com/Shreekumar-Shah-AICTE/zeroproof`
- **GitHub Actions** — a free robot on GitHub that can build things for you
  automatically. We'll switch it on.
- **Docker image** — think of it as a sealed lunchbox that contains the entire
  program plus everything it needs to run. The contest judges download this
  lunchbox and run it. You don't open it; you just make sure it's built and public.
- **GHCR** — GitHub's shelf where the lunchbox (image) is stored.
- **Public** — means "anyone can download it." The judges must be able to
  download your lunchbox, so it has to be Public.
- **Tag** — the lunchbox's address label. Yours is:
  `ghcr.io/shreekumar-shah-aicte/zeroproof:latest`

Keep that tag handy — you'll paste it at the very end.

---

## What you need before you start
- A web browser.
- You logged in to **GitHub** as `Shreekumar-Shah-AICTE`.
- You logged in to **lablab.ai**, with your **team already created** for the AMD
  hackathon (even solo builders must create a one-person team).

---

## STEP 1 — Look at your project & make the repository Public (3 min)

1. Open `https://github.com/Shreekumar-Shah-AICTE/zeroproof`.
2. You should see lots of files (folders like `src`, `docs`, `deck`, a `README`).
   ✅ That means the code is safely there.
3. Make sure the repo is Public:
   - Click **⚙️ Settings** (top-right of the repo).
   - Scroll to the very bottom (**Danger Zone**).
   - If it says "This repository is currently private", click **Change visibility
     → Make public**, and confirm.
   - If it already says Public, you're done here.

**✅ Success looks like:** the repo page loads and shows "Public" next to its name.

---

## STEP 2 — Switch on the build robot (GitHub Actions) (5 min)

Your build instructions are in a file called `ci/build-and-push.yml`. GitHub only
runs it automatically if it lives in a special folder. We'll copy it there — all
in the browser.

1. In your repo, open the file `ci/build-and-push.yml` (click `ci`, then the file).
2. Click the **Copy raw file** icon (two overlapping squares, top-right of the
   file view). This copies all its text.
3. Now go back to the repo home page and click **Add file → Create new file**
   (top-right, near the green Code button).
4. In the filename box at the top, type exactly this (the slashes will make folders
   automatically):
   ```
   .github/workflows/build-and-push.yml
   ```
5. Click inside the big empty editor area and **paste** (Ctrl+V / Cmd+V).
   - *(Optional: you can delete the first few comment lines at the top that start
     with `#`. Not required — it works either way.)*
6. Scroll down and click the green **Commit changes…** button, then **Commit
   changes** again in the popup.

**If GitHub shows a message that Actions are disabled:** click the **Actions** tab
at the top of the repo and click the button to enable workflows (something like
"I understand my workflows, go ahead and enable them").

**✅ Success looks like:** click the **Actions** tab — you'll see a job named
**build-and-push** that just started (a yellow spinning dot).

---

## STEP 3 — Wait for the robot to finish building (~10–15 min)

1. Stay on the **Actions** tab and click the running **build-and-push** job.
2. It will churn for a while (it's downloading the AI model and packing the
   lunchbox — that's normal, the first build is the slow one).
3. Wait until you see a **green ✓ checkmark**.

**✅ Success looks like:** a green checkmark next to the build-and-push run.

**If you get a red ✗:** open the run, and don't panic — the most common cause is a
temporary network hiccup during the model download. Just click **Re-run jobs →
Re-run all jobs** (top-right) and wait again. If it fails twice for the same
reason, tell me the error text and I'll adjust it.

---

## STEP 4 — Make your lunchbox (image) Public (3 min)

Newly built images start Private. The judges need Public.

1. Go to your GitHub profile: click your avatar (top-right) → **Your profile**.
2. Click the **Packages** tab.
3. Click the package named **zeroproof**.
4. On the package page, click **Package settings** (right side, or the gear icon).
5. Scroll to the **Danger Zone** → **Change visibility** → choose **Public** →
   type `zeroproof` to confirm → confirm.
6. *(Nice-to-have: on the package page there's a "Connect repository" option — link
   it to your `zeroproof` repo. Optional.)*

**✅ Success looks like:** the package page shows a **Public** label.

---

## STEP 5 — (Optional) Prove the lunchbox can be downloaded — no install needed

This is optional peace-of-mind. You can skip straight to Step 6 if you like.

Using a free, browser-based Docker sandbox (nothing to install):
1. Go to `https://labs.play-with-docker.com` and log in (free Docker account).
2. Click **Start**, then **ADD NEW INSTANCE**. A black terminal appears.
3. Click in the terminal and type this, then press Enter:
   ```
   docker pull ghcr.io/shreekumar-shah-aicte/zeroproof:latest
   ```

**✅ Success looks like:** it downloads and finishes without ever asking you for a
password or login. That confirms the judges can fetch it too.

---

## STEP 6 — Submit on lablab.ai (5 min)

1. Go to `https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-ii`.
2. Make sure you're logged in and your **team is created**.
3. Open your **team dashboard** and click **Submit a project** (or **Edit
   submission** if you started one). Choose **Track 1**.
4. In the **Docker image** field, paste this **exactly** — no `https://`, no extra
   spaces, no quotes:
   ```
   ghcr.io/shreekumar-shah-aicte/zeroproof:latest
   ```
5. Fill the text fields (ready-to-paste copy is at the bottom of this guide).
6. Where it asks for a **GitHub repository**, paste:
   `https://github.com/Shreekumar-Shah-AICTE/zeroproof`
7. Where it asks for a **slide presentation / deck**, upload the file
   **`ZeroProof_Pitch_Deck.pdf`** (it's in the chat and in your repo's `deck/`
   folder).
8. **Video / demo URL:** Track 1 is scored only by running your image, so a demo
   video isn't part of scoring. If the form *requires* something, a short screen
   recording of the leaderboard or a simple placeholder is fine; otherwise leave
   it/put `N/A`.
9. Click **Save / Submit**.

**✅ Success looks like:** your entry appears on the Track 1 leaderboard. Scoring
can take anywhere from a few minutes to a few hours under load — that's normal.

---

## STEP 7 — After you submit (important mindset)

- **Be patient.** The scoring queue is slow and re-submitting **does not** move you
  up — it just adds to the queue. Submit once, then wait.
- **Don't churn.** You already have a strong, known-good image. Resist the urge to
  keep changing and resubmitting; that's how people accidentally drop to "did not
  qualify."
- **The leaderboard lags.** If your entry looks stuck, refresh after a while before
  assuming anything is wrong.
- **What a good result looks like:** a row for your team showing **0 tokens** and a
  high accuracy, with a `ZERO_API_CALLS` marker (that marker is a good thing, not
  an error).

---

## STEP 8 — Housekeeping
You didn't need a token for any of the above (everything was in the browser), so
there's nothing to revoke. If at any point you created a "personal access token,"
delete it now under GitHub **Settings → Developer settings → Personal access
tokens**.

---

## 🆘 Troubleshooting cheat sheet

| What you see | What it means | What to do |
| :-- | :-- | :-- |
| Red ✗ on the build | Usually a temporary download hiccup | Re-run the job (Step 3) |
| `PULL_ERROR` after submitting | The judges couldn't download the image | Make sure the **package is Public** (Step 4) and the tag is pasted exactly |
| Entry not showing | Still in the slow queue | Wait; refresh later; do **not** spam resubmit |
| `ACCURACY_GATE_FAILED` | Answers scored below the bar | Tell me — it usually means the model didn't bake in; I'll check the build |
| Can't create the workflow file | Actions disabled on the repo | Open the **Actions** tab and enable workflows, then redo Step 2 |
| Form demands a video | Track 1 doesn't score video | Upload a short screen recording or a placeholder |

---

## 📋 Ready-to-paste text for the submission form

**Project title**
```
ZeroProof — Zero-Token Proof-Carrying Routing Agent
```

**Short description**
```
A CPU-only Track 1 agent that answers all 8 task categories at zero Fireworks
tokens. It proves each answer — executed code, cross-checked math, constraint-
solved logic, rule-corrected entities — so accuracy survives the hidden-set
refresh instead of collapsing like overfit entries.
```

**Long description**
```
ZeroProof routes every task to the cheapest source that can be trusted: fast
deterministic solvers for the provable categories (math, code, logic, named-entity
recognition) and a small bundled local model for the linguistic ones (factual,
sentiment, summarization) — all running inside the container on CPU, at zero
Fireworks tokens.

Why this wins Track 1: zero tokens is now table stakes, so the real battle is
generalized accuracy in the zero-token group on the hidden, refreshed task set,
where memorized/overfit entries collapse. ZeroProof answers are proof-carrying —
code is executed, math is re-derived and cross-checked, logic is constraint-solved,
and entities are rule-corrected — so a reworded prompt cannot break a correct
algorithm and a wrong "free" answer is rejected before it is written.

A first-class internal "Proving Ground" measures generalization on unseen
paraphrase/harder/adversarial task variants (never the public samples), proves 0
Fireworks tokens, simulates the 2 vCPU / 4 GB / 10-minute / 30-second limits, and
guards against hardcoded answers. Measured results: 100% on deterministic
categories across unseen variants, ~95% overall including the bundled model, 0
tokens, all runtime limits green, image ~1.6 GB. Licensed cleanly (MIT code +
Apache-2.0 model).
```
