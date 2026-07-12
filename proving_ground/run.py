"""ZeroProof Proving Ground — one-command generalization loop.

Usage:
    python proving_ground/run.py [--seeds N] [--per K] [--model PATH] [--label TXT]

Runs the full generalization suite across N random seeds, judges every answer,
meters Fireworks tokens (must be 0), simulates the runtime constraints, runs the
hardcode guard, prints a per-category/per-tier report, and appends the result to
the persisted regression scoreboard.

MEASURE -> DIAGNOSE -> (you) IMPROVE -> RE-MEASURE. Deterministic categories are
measured model-free here; model-dependent categories (factual, code) report
"needs model" unless a GGUF is supplied via --model / ZP_MODEL_PATH.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, _ROOT)

from proving_ground import constraint_sim, generators, hardcode_guard, scoreboard, token_meter  # noqa: E402
from proving_ground.judge import judge  # noqa: E402
from zeroproof.config import Config  # noqa: E402
from zeroproof.router import build_context, route  # noqa: E402
from zeroproof.types import Task  # noqa: E402


def _pct(passed: int, total: int) -> float:
    return round(100.0 * passed / total, 1) if total else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description="ZeroProof Proving Ground")
    ap.add_argument("--seeds", type=int, default=3, help="number of random seeds")
    ap.add_argument("--per", type=int, default=3, help="tasks per category per tier per seed")
    ap.add_argument("--model", type=str, default=os.environ.get("ZP_MODEL_PATH", ""), help="GGUF model path (optional)")
    ap.add_argument("--label", type=str, default="local-run", help="scoreboard label")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.model:
        os.environ["ZP_MODEL_PATH"] = args.model
    config = Config()
    # Never let the valve fire during measurement.
    config.fireworks_enabled = False

    t_ready0 = time.monotonic()
    ctx = build_context(config)
    model_loaded = ctx.llm is not None and ctx.llm.available
    ready_s = time.monotonic() - t_ready0

    csim = constraint_sim.ConstraintReport(ready_s=ready_s)

    # Accumulators.
    per_cat = defaultdict(lambda: {"passed": 0, "total": 0, "model_dependent": False})
    per_tier = defaultdict(lambda: {"passed": 0, "total": 0})
    det_pass = det_total = all_pass = all_total = 0
    failures = []

    t0 = time.monotonic()
    for seed in range(1, args.seeds + 1):
        suite = generators.generate_suite(seed=seed, per_category_per_tier=args.per)
        for gt in suite:
            task = Task(task_id=gt.task_id, prompt=gt.prompt)
            ts = time.monotonic()
            result = route(task, ctx)
            dt = time.monotonic() - ts
            csim.per_task_s.append((gt.task_id, dt))

            ok, note = judge(gt.category, result.answer, gt.truth)
            per_cat[gt.category]["total"] += 1
            per_cat[gt.category]["model_dependent"] = per_cat[gt.category]["model_dependent"] or gt.model_dependent
            per_tier[gt.tier]["total"] += 1
            if ok:
                per_cat[gt.category]["passed"] += 1
                per_tier[gt.tier]["passed"] += 1

            # Split deterministic vs model-dependent accounting.
            if gt.model_dependent and not model_loaded:
                pass  # not counted; cannot be solved without the model
            else:
                all_total += 1
                all_pass += 1 if ok else 0
                if not gt.model_dependent:
                    det_total += 1
                    det_pass += 1 if ok else 0
            if not ok and (not gt.model_dependent or model_loaded):
                failures.append((gt.category, gt.tier, gt.task_id, note, result.answer[:80]))

    csim.total_s = time.monotonic() - t0
    csim.finalize()
    tok = token_meter.measure(ctx)
    guard = hardcode_guard.run_guard(os.path.join(_ROOT, "src"))

    # ---- Report ----
    print("\n" + "=" * 72)
    print(f"ZeroProof Proving Ground  |  seeds={args.seeds} per={args.per} "
          f"model={'LOADED' if model_loaded else 'ABSENT'}")
    print("=" * 72)
    print("\nPer-category generalized accuracy:")
    for cat in generators.CATEGORIES:
        info = per_cat.get(cat, {"passed": 0, "total": 0, "model_dependent": False})
        tag = "  (needs model)" if info["model_dependent"] and not model_loaded else ""
        print(f"  {cat:28s} {_pct(info['passed'], info['total']):5.1f}%  "
              f"({info['passed']}/{info['total']}){tag}")
    print("\nPer-tier accuracy (deterministic + available):")
    for tier in generators.TIERS:
        info = per_tier[tier]
        print(f"  {tier:12s} {_pct(info['passed'], info['total']):5.1f}%  ({info['passed']}/{info['total']})")

    det_acc = _pct(det_pass, det_total)
    all_acc = _pct(all_pass, all_total)
    print(f"\nDeterministic-category accuracy: {det_acc}%  ({det_pass}/{det_total})")
    print(f"Overall available accuracy:      {all_acc}%  ({all_pass}/{all_total})"
          + ("" if model_loaded else "  [model-dependent categories excluded]"))
    print("\n" + tok.render())
    print(csim.render())
    print(guard.render())

    if failures and args.verbose:
        print("\nSample failures (diagnose highest-leverage first):")
        for cat, tier, tid, note, ans in failures[:25]:
            print(f"  [{cat}/{tier}] {tid}: {note} | ans={ans!r}")

    # ---- Persist to scoreboard ----
    scoreboard.append_run({
        "label": args.label,
        "seeds": args.seeds,
        "model": "loaded" if model_loaded else "absent",
        "det_acc": det_acc,
        "all_acc": all_acc if model_loaded else "n/a",
        "fireworks_tokens": tok.fireworks_tokens,
        "guard": "clean" if guard.passed else "FLAGGED",
        "per_category": {
            c: {"acc": _pct(v["passed"], v["total"]), "passed": v["passed"],
                "total": v["total"], "model_dependent": v["model_dependent"]}
            for c, v in per_cat.items()
        },
    })
    print(f"\nScoreboard updated -> {scoreboard.render_path()}")

    # ---- Championship-locked gate (informational exit code) ----
    ok_tokens = tok.passed
    ok_guard = guard.passed
    ok_constraints = csim.passed
    print("\nChampionship-locked checklist:")
    print(f"  [{'x' if det_acc >= 95 else ' '}] deterministic generalized accuracy >= 95%  ({det_acc}%)")
    print(f"  [{'x' if ok_tokens else ' '}] 0 Fireworks tokens")
    print(f"  [{'x' if ok_constraints else ' '}] runtime constraints green")
    print(f"  [{'x' if ok_guard else ' '}] hardcode guard clean")
    if model_loaded:
        print(f"  [{'x' if all_acc >= 95 else ' '}] overall (incl. model) generalized accuracy >= 95%  ({all_acc}%)")
    else:
        print("  [ ] overall (incl. model) accuracy: run with --model to measure factual/code")

    return 0 if (ok_tokens and ok_guard and ok_constraints) else 1


if __name__ == "__main__":
    sys.exit(main())
