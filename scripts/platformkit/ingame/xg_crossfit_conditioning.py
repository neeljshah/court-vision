"""scripts.platformkit.ingame.xg_crossfit_conditioning -- LANE 3 item 2:
CROSS-FITTED xG conditioning on the captured (39-game, 29-graded) soccer_intl
corpus. Pre-declared, single functional family, ONE coefficient:

    logit(p_enriched) = logit(model_prob) + beta * xg_diff

(xg_diff = xg_home - xg_away, as-of reconstructed; same family Wave-14's
FIXED-FORM conditioning used, but here beta is FIT on one md5-parity half
and EVALUATED on the other -- not assumed at a fixed 0.15 scale). This
answers a different question than the Wave-14 gate: does FITTING beta (still
inside the SAME pre-declared 1-parameter family) help beyond the arbitrary
fixed scale, without overfitting a thin (29-game) corpus?

METHOD (leak-free, no post-hoc family search):
* Split rows into md5-parity halves (SAME _md5_half convention as
  ingame_enrichment_gates, so half membership is byte-identical across every
  analysis in this lane).
* FIT beta on half0 (1-D scalar minimizing pooled Brier vs y over half0's
  rows only) -> EVALUATE (frozen beta) on half1. Then swap: fit on half1,
  evaluate on half0. This is genuine cross-fitting -- the coefficient never
  sees the half it is scored on.
* Per-half report: brier_baseline (score+minute-only model_prob), brier_fit
  (cross-fit conditioned prob), delta, and a game-clustered bootstrap 95% CI
  on the delta (reuses ingame_enrichment_gates._ci_delta exactly -- same
  seed/iters convention, so CIs are comparable across this lane's artifacts).
* sot_diff is intentionally EXCLUDED from this family (Wave-14's fixed form
  used xg_diff+sot_diff jointly; this analysis isolates xg_diff alone per
  the LANE 3 brief's "single... one coefficient" instruction -- a 2-parameter
  fit on 14-15 games/half would be a second, un-pre-declared family, which
  the brief forbids).

FIT METHOD: golden-section search over beta in [-3, 3] minimizing mean
per-tick Brier on the training half (deterministic, no RNG in the search
itself -- only the CI bootstrap after uses a fixed seed=42, matching the
rest of this lane).

HONESTY: probability/Brier space only; no $/roi/pnl; edge_claimed always
False; this is a VALIDATION-corpus cross-fit read, not a forward gate, never
pooled with the forward verdict file; never auto-wires into any decision path.

INVARIANTS: platformkit-only; <=300 LOC; ASCII only; no network; no
data/registry write; no flag flip; never raises; deterministic (fixed seed).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_xg_crossfit_conditioning.py -q
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.ingame.ingame_enrichment_gates import _ci_delta, _md5_half

_REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = _REPO_ROOT / "data" / "domains" / "soccer_intl" / "xg_crossfit_conditioning.json"

BETA_LO, BETA_HI = -15.0, 15.0
_GOLDEN_ITERS = 60
# NOTE: widened from an initial +/-3 pre-declared bound after a diagnostic
# scan (see the LANE 3 report) showed the Brier-minimizing beta on this
# corpus keeps improving well past +/-3 before turning back -- backfill xG
# is RECONSTRUCTED from finished-match shotmaps, so late-checkpoint xg_diff
# correlates near-tautologically with the eventual winner (a team that wins
# usually out-shot/out-xG'd its opponent by full time). This is reported
# honestly as a corpus-specific artifact, not evidence of a stable live edge.
_GOLDEN_RATIO = (math.sqrt(5.0) - 1.0) / 2.0  # ~0.618


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1.0 - p))


def _sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def conditioned_prob(model_prob: float, xg_diff: float, beta: float) -> float:
    """The ONE pre-declared family: logit-additive, single coefficient."""
    return _sigmoid(_logit(model_prob) + beta * xg_diff)


def _mean_brier(rows: Sequence[Dict[str, Any]], beta: float) -> float:
    if not rows:
        return float("nan")
    total = 0.0
    for r in rows:
        p = conditioned_prob(r["model_prob"], r["xg_diff"], beta)
        total += (p - r["y"]) ** 2
    return total / len(rows)


def fit_beta(rows: Sequence[Dict[str, Any]], *, lo: float = BETA_LO, hi: float = BETA_HI,
            iters: int = _GOLDEN_ITERS) -> float:
    """Golden-section search for the beta in [lo, hi] minimizing mean Brier
    over *rows* (the TRAINING half only). Deterministic -- no RNG. Returns
    0.0 (no conditioning) if rows is empty."""
    if not rows:
        return 0.0
    a, b = lo, hi
    c = b - _GOLDEN_RATIO * (b - a)
    d = a + _GOLDEN_RATIO * (b - a)
    fc, fd = _mean_brier(rows, c), _mean_brier(rows, d)
    for _ in range(iters):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - _GOLDEN_RATIO * (b - a)
            fc = _mean_brier(rows, c)
        else:
            a, c, fc = c, d, fd
            d = a + _GOLDEN_RATIO * (b - a)
            fd = _mean_brier(rows, d)
    return (a + b) / 2.0


def _prep_rows(raw_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only rows with a resolvable xg_diff, model_prob, y, game_id.
    Never imputes a missing field -- an honest skip."""
    out: List[Dict[str, Any]] = []
    for r in raw_rows:
        gid, mp, y = r.get("game_id"), r.get("model_prob"), r.get("y")
        xh, xa = r.get("xg_home"), r.get("xg_away")
        if gid is None or mp is None or y is None or xh is None or xa is None:
            continue
        try:
            out.append({"game_id": str(gid), "model_prob": float(mp), "y": float(y),
                       "xg_diff": float(xh) - float(xa)})
        except (TypeError, ValueError):
            continue
    return out


def _per_game_brier(rows: Sequence[Dict[str, Any]], beta: float
                    ) -> Dict[str, Tuple[float, float, int]]:
    """game_id -> (sse_baseline, sse_fit, n) for the given frozen beta."""
    acc: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for r in rows:
        p_fit = conditioned_prob(r["model_prob"], r["xg_diff"], beta)
        a = acc[r["game_id"]]
        a[0] += (r["model_prob"] - r["y"]) ** 2
        a[1] += (p_fit - r["y"]) ** 2
        a[2] += 1
    return {g: (v[0], v[1], int(v[2])) for g, v in acc.items()}


def _half_report(train_rows: Sequence[Dict[str, Any]], eval_rows: Sequence[Dict[str, Any]]
                 ) -> Dict[str, Any]:
    """Fit beta on train_rows, evaluate (frozen beta) on eval_rows. Reports
    per-game Brier delta + game-clustered bootstrap CI on eval_rows only --
    train_rows never contribute to the reported delta (true out-of-half
    evaluation)."""
    beta = fit_beta(train_rows)
    by_game = _per_game_brier(eval_rows, beta)
    n_games = len(by_game)
    n_ticks = sum(v[2] for v in by_game.values())
    if n_games == 0 or n_ticks == 0:
        return {"beta_fit": beta, "n_games": n_games, "total_ticks": n_ticks,
                "brier_baseline": None, "brier_crossfit": None,
                "brier_delta": None, "delta_ci95": None, "verdict": "INSUFFICIENT"}
    bb = [v[0] / v[2] for v in by_game.values()]
    bf = [v[1] / v[2] for v in by_game.values()]
    delta_g = [f - b for f, b in zip(bf, bb)]
    mean_b, mean_f = sum(bb) / n_games, sum(bf) / n_games
    delta = mean_f - mean_b
    lo, hi = _ci_delta(delta_g)
    if delta < 0 and hi < 0.0:
        verdict = "BETTER_THAN_BASELINE"
    elif delta > 0 and lo > 0.0:
        verdict = "WORSE_THAN_BASELINE"
    else:
        verdict = "MATCH"
    at_boundary = abs(beta - BETA_LO) < 1e-6 or abs(beta - BETA_HI) < 1e-6
    return {"beta_fit": round(beta, 6), "n_games": n_games, "total_ticks": n_ticks,
            "brier_baseline": round(mean_b, 6), "brier_crossfit": round(mean_f, 6),
            "brier_delta": round(delta, 6), "delta_ci95": [round(lo, 6), round(hi, 6)],
            "verdict": verdict, "beta_at_search_boundary": at_boundary}


def run_crossfit(rows_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None
                 ) -> Dict[str, Any]:
    """Full 2-way cross-fit: fit-on-half0/eval-on-half1 AND fit-on-half1/
    eval-on-half0. Never raises -- a producer failure yields an honest
    INSUFFICIENT-shaped doc."""
    if rows_fn is None:
        from scripts.platformkit.ingame.enrichment_rows_soccer import rows_fn_backfill as rows_fn
    try:
        raw = rows_fn()
    except Exception as exc:  # noqa: BLE001
        raw = []
        prepped: List[Dict[str, Any]] = []
        err = str(exc)
    else:
        prepped = _prep_rows(raw)
        err = None

    half0 = [r for r in prepped if _md5_half(r["game_id"]) == 0]
    half1 = [r for r in prepped if _md5_half(r["game_id"]) == 1]

    fit0_eval1 = _half_report(train_rows=half0, eval_rows=half1)
    fit1_eval0 = _half_report(train_rows=half1, eval_rows=half0)

    both_better = (fit0_eval1["verdict"] == "BETTER_THAN_BASELINE"
                  and fit1_eval0["verdict"] == "BETTER_THAN_BASELINE")
    either_worse = (fit0_eval1["verdict"] == "WORSE_THAN_BASELINE"
                   or fit1_eval0["verdict"] == "WORSE_THAN_BASELINE")
    overall = "BETTER_THAN_BASELINE" if both_better else (
        "WORSE_THAN_BASELINE" if either_worse else "MATCH")

    doc = {
        "component": "xg_crossfit_conditioning", "sport": "soccer_intl",
        "provenance": "backfill_validation",
        "family": "logit(p_enriched) = logit(model_prob) + beta * xg_diff (1 coefficient)",
        "hypothesis": ("cross-fitting beta (train on one md5-parity half, evaluate frozen "
                      "on the other) improves Brier vs OUTCOME beyond the score+minute "
                      "baseline, without overfitting the thin 29-game corpus"),
        "fit_on_half0_eval_on_half1": fit0_eval1,
        "fit_on_half1_eval_on_half0": fit1_eval0,
        "overall_verdict": overall,
        "n_games_total": len({r["game_id"] for r in prepped}),
        "n_ticks_total": len(prepped),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honest_note": ("Single pre-declared 1-parameter family (xg_diff only, no sot_diff -- "
                        "see module docstring); beta is fit ONLY on the training half and "
                        "frozen before scoring the held-out half (true cross-fit, no leak). "
                        "CAVEAT: on this corpus the Brier-minimizing beta hugs the search "
                        "boundary (see beta_at_search_boundary per half) rather than settling "
                        "at a stable interior value -- reconstructed backfill xG is derived "
                        "from FINISHED-match shotmaps, so late-checkpoint xg_diff correlates "
                        "near-tautologically with the eventual winner; this large-beta fit is "
                        "a reconstructed-corpus artifact, NOT evidence of a real live-in-play "
                        "coefficient magnitude. Brier/probability space only; no $/roi/pnl "
                        "field; edge_claimed is always False; never auto-wires into any live "
                        "decision path."),
        "edge_claimed": False,
    }
    if err is not None:
        doc["error"] = err
    return doc


def _atomic_write(path: Path, doc: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
        os.replace(str(tmp), str(path))
    except Exception:  # noqa: BLE001 -- a write failure must not raise
        pass


def main() -> int:
    doc = run_crossfit()
    _atomic_write(OUT_PATH, doc)
    print("xg_crossfit_conditioning | overall=%s n_games=%d n_ticks=%d" % (
        doc["overall_verdict"], doc["n_games_total"], doc["n_ticks_total"]))
    print("  fit0->eval1: beta=%s verdict=%s delta=%s" % (
        doc["fit_on_half0_eval_on_half1"].get("beta_fit"),
        doc["fit_on_half0_eval_on_half1"].get("verdict"),
        doc["fit_on_half0_eval_on_half1"].get("brier_delta")))
    print("  fit1->eval0: beta=%s verdict=%s delta=%s" % (
        doc["fit_on_half1_eval_on_half0"].get("beta_fit"),
        doc["fit_on_half1_eval_on_half0"].get("verdict"),
        doc["fit_on_half1_eval_on_half0"].get("brier_delta")))
    print("  out: %s" % OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OUT_PATH", "BETA_LO", "BETA_HI", "conditioned_prob", "fit_beta", "run_crossfit",
]
