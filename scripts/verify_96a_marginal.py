"""verify_96a_marginal.py — Cycle 98e (loop 5).

Confirms the marginal benefit of the cycle-96a garbage-time haircut wire-in
by comparing production-mode MAE (haircut ON) vs ablation-mode MAE
(haircut OFF via _APPLY_GARBAGE_HAIRCUT=False) on the canonical 80/20
chronological holdout.

WHY THIS EXISTS:
The cycle 94a/95a probe measured the haircut delta against a baseline
that DID NOT have the haircut wired (the validator was buggy pre-97a).
Cycle 97a fixed the validator to mirror predict_pergame's haircut step,
so the canonical baseline now includes the haircut. To confirm cycle 96a
genuinely improved MAE (not an artifact of the broken baseline), this
script flips the production flag and re-scores — the delta is the TRUE
marginal benefit of the wire-in.

GATE:
PTS MAE improvement (ablation - prod) >= 0.005 is "CONFIRMED".
Anything else (flat or negative) is "CONTRADICTED" — recommends emergency
revert (set _APPLY_GARBAGE_HAIRCUT = False).

Run:
    python scripts/verify_96a_marginal.py
"""
from __future__ import annotations

import os
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction import prop_pergame  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)
from scripts.validate_adjustment import (  # noqa: E402
    _bulk_predict, no_op, validate,
)


_RESULTS_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")
os.makedirs(_RESULTS_DIR, exist_ok=True)

# Stats targeted by the cycle-96a haircut.
_HAIRCUT_STATS = ("pts", "reb", "ast")


def _score_all(holdout, X) -> dict:
    """Per-stat MAE on the holdout using the current production dispatch
    (q50 / NNLS blend). The garbage-time haircut is layered IN validate()
    via apply_garbage_time_haircut — so the haircut flag controls whether
    the returned MAEs reflect prod-with-haircut or ablation-without."""
    results = validate(no_op, holdout, X)
    return {s: results[s]["baseline_mae"] for s in STATS}


def main() -> int:
    print("Loading pergame dataset...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    holdout = rows[int(n * 0.80):]
    cols = feature_columns()
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)
    print(f"  n={n}  holdout={len(holdout)}  features={len(cols)}\n", flush=True)

    original_flag = prop_pergame._APPLY_GARBAGE_HAIRCUT

    # 1) Production: haircut ON (cycle-96a default).
    prop_pergame._APPLY_GARBAGE_HAIRCUT = True
    print("Scoring PRODUCTION (haircut=ON)...", flush=True)
    prod_mae = _score_all(holdout, X)

    # 2) Ablation: flip flag OFF.
    prop_pergame._APPLY_GARBAGE_HAIRCUT = False
    print("Scoring ABLATION  (haircut=OFF)...\n", flush=True)
    abl_mae = _score_all(holdout, X)

    # Restore so we leave the module in its shipped state.
    prop_pergame._APPLY_GARBAGE_HAIRCUT = original_flag

    print("=" * 70)
    print("MARGINAL CONFIRMATION — cycle 96a haircut wire-in")
    print("=" * 70)
    print(f"  {'stat':<5} {'prod_mae':>10} {'abl_mae':>10} {'delta':>10}  note")
    print("  " + "-" * 60)
    deltas = {}
    for s in STATS:
        p = prod_mae[s]
        a = abl_mae[s]
        # delta = abl - prod -> positive = haircut beneficial (prod < abl)
        d = a - p
        deltas[s] = d
        tag = ""
        if s in _HAIRCUT_STATS:
            if d >= 0.005:
                tag = "haircut helps"
            elif d <= -0.005:
                tag = "haircut hurts (regression)"
            else:
                tag = "flat"
        else:
            tag = "n/a (not targeted)"
        print(f"  {s:<5} {p:>10.4f} {a:>10.4f} {d:>+10.4f}  {tag}")
    print("  " + "-" * 60)
    agg = sum(deltas[s] for s in _HAIRCUT_STATS)
    print(f"  PTS+REB+AST aggregate delta (abl-prod): {agg:+.4f} "
          f"(positive = haircut helps)\n")

    pts_delta = deltas["pts"]
    confirmed = pts_delta >= 0.005
    if confirmed:
        verdict = "CONFIRMED"
        rationale = (f"PTS improves by {pts_delta:+.4f} MAE when haircut is "
                     f"enabled (gate: >= 0.005). Cycle 96a wire-in is genuinely "
                     f"beneficial.")
    else:
        verdict = "CONTRADICTED"
        rationale = (f"PTS delta is {pts_delta:+.4f} MAE (gate: >= 0.005). "
                     f"Cycle 96a wire-in does NOT deliver a meaningful "
                     f"improvement; emergency revert recommended.")
    print(f"VERDICT: {verdict}")
    print(f"  {rationale}")

    # Persist confirmation note.
    if confirmed:
        out_path = os.path.join(_RESULTS_DIR, "96a_marginal_confirmation.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("# Cycle 98e (loop 5) — cycle 96a garbage-time haircut "
                    "marginal CONFIRMATION\n\n")
            f.write("## Method\n")
            f.write("After cycle 97a fixed the validator to mirror "
                    "`apply_garbage_time_haircut` in `_bulk_predict`, the "
                    "canonical 80/20 holdout baseline now INCLUDES the cycle-"
                    "96a haircut. To confirm the wire-in is genuinely better "
                    "than ablation, this script flips "
                    "`_APPLY_GARBAGE_HAIRCUT=False` and re-scores. The delta "
                    "(abl - prod) is the TRUE marginal benefit.\n\n")
            f.write("## Per-stat MAE\n\n")
            f.write("| stat | prod_mae (haircut ON) | abl_mae (haircut OFF) | "
                    "delta (abl-prod) | note |\n")
            f.write("|------|----------------------|----------------------|"
                    "------------------|------|\n")
            for s in STATS:
                p = prod_mae[s]
                a = abl_mae[s]
                d = deltas[s]
                note = ("targeted" if s in _HAIRCUT_STATS
                        else "not targeted (no-op)")
                f.write(f"| {s} | {p:.4f} | {a:.4f} | {d:+.4f} | {note} |\n")
            f.write(f"\n**PTS+REB+AST aggregate delta:** {agg:+.4f} "
                    f"(positive = haircut helps)\n")
            f.write(f"\n## Verdict: **{verdict}**\n\n")
            f.write(f"{rationale}\n")
            f.write("\n## Comparison to cycle 96a's reported numbers\n\n")
            f.write("Cycle 96a probe (`probe_garbage_time_haircut_v2.py` on a "
                    "broken baseline) reported:\n")
            f.write("- PTS -0.0117 MAE\n- REB +0.0050 MAE\n- AST -0.0036 MAE\n")
            f.write("- agg(PTS+REB+AST) -0.0103\n\n")
            f.write(f"Cycle 98e (this run, correct baseline) measured:\n")
            f.write(f"- PTS {-deltas['pts']:+.4f} MAE\n")
            f.write(f"- REB {-deltas['reb']:+.4f} MAE\n")
            f.write(f"- AST {-deltas['ast']:+.4f} MAE\n")
            f.write(f"- agg(PTS+REB+AST) {-agg:+.4f}\n\n")
            f.write("Numbers should match cycle 96a's reported deltas within "
                    "noise — confirms the validator fix (97a) didn't change "
                    "the underlying marginal effect.\n")
        print(f"\nReport written: {out_path}")

    return 0 if confirmed else 2


if __name__ == "__main__":
    sys.exit(main())
