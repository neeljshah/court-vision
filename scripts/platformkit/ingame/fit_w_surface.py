"""scripts.platformkit.ingame.fit_w_surface -- the OFFLINE in-game PROOF (honesty-critical).

Fits + validates an in-game blend weight surface and emits an HONEST verdict object
for the in-game spine (Milestone-6). It answers ONE question, leak-free and out-of-
sample: does conditioning on REALIZED live game state sharpen the forecast over a
pregame-only prior -- and is that gain real (clustered DM), not a median-vs-mean
artifact?

WHAT IT REUSES (does NOT reimplement): the verified eval_gate cores
  scripts.platformkit.eval_gate.ingame_blend  (fit_weight_surface / blended_predictions)
  scripts.platformkit.eval_gate.scoring        (brier -- kernel-backed)
  scripts.platformkit.eval_gate.dm_test        (cluster-robust Diebold-Mariano).

HONEST INVARIANTS (hard-learned; violating them = a false product):
  * Point markets are scored with RMSE + BIAS, NEVER MAE -- MAE wins from shrinking
    toward the current score are MEDIAN-vs-MEAN artifacts. Win-prob is scored with
    Brier. (A `_mae` helper exists ONLY so the leak test can prove we did not grade
    on it; it is never the verdict metric.)
  * The only validated lever is FRESHNESS: a correct reprice's variance must SHRINK
    as the game progresses (Q1 wide -> Q3 tight). assert_variance_shrink() enforces
    this on the data the verdict is built from.
  * Leak-free: P0 (the pregame prior) is the FIT-window home base rate -- it never
    sees the eval window's outcomes. P_live reads ONLY realized as-of score. A
    deliberately-leaky input (P0 == outcome) is REJECTED by reject_leaky_prior().
  * Out-of-sample: fit on one window, evaluate on a DIFFERENT window (temporal split).
  * No $-edge field anywhere. There is no devigged close in the offline linescore
    corpus, so the devigged-close comparison is SKIPPED with an explicit reason --
    the verdict is calibration vs a pregame BASE-RATE prior only.

REAL-DATA SCOPE (stated plainly): the only on-disk corpus with a leak-free in-game
score trajectory is data/domains/basketball_nba/linescores.parquet -- ONE real
season (2025-26, ~1.3k games, per-quarter scores). A true CROSS-SEASON OOS
(train season A, eval season B) is therefore NOT reachable offline; we do a
same-season TEMPORAL split (early -> late) as the OOS proxy and label that caveat
on the verdict. The cross-season run is a HUMAN-RUN step once a 2nd season's
linescores are ingested.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib only.
CLI: python -m scripts.platformkit.ingame.fit_w_surface
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.ingame_blend import (
    blended_predictions,
    fit_weight_surface,
)
from scripts.platformkit.eval_gate.scoring import brier

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_LINESCORES = os.path.join(
    _REPO, "data", "domains", "basketball_nba", "linescores.parquet")
_OUT = os.path.join(_REPO, "data", "frontend", "ingame", "proof_nba.json")

_REG_SEC = 2880.0
# Seconds REMAINING in regulation at the END of each quarter (leak-free as-of points).
_QSEC = {1: 2160.0, 2: 1440.0, 3: 720.0}


# --------------------------------------------------------------------------- metrics
def _rmse(a: Sequence[float], b: Sequence[float]) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(np.sqrt(np.mean((a - b) ** 2))) if a.size else float("nan")


def _bias(pred: Sequence[float], actual: Sequence[float]) -> float:
    """Mean signed error pred-actual (a point forecast must be unbiased)."""
    pred, actual = np.asarray(pred, float), np.asarray(actual, float)
    return float(np.mean(pred - actual)) if pred.size else float("nan")


def _mae(a: Sequence[float], b: Sequence[float]) -> float:
    """ONLY here so the leak test can assert we did NOT grade on MAE. Not a verdict
    metric -- MAE rewards shrink-to-current-score (median-vs-mean artifact)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(np.mean(np.abs(a - b))) if a.size else float("nan")


# --------------------------------------------------------------------------- states
def _p_live(score_diff: float, frac_elapsed: float) -> float:
    """Honest live win-prob from realized as-of margin only. Logistic slope grows
    with elapsed fraction = the freshness lever (more confident later, by design)."""
    slope = 0.06 + 0.10 * float(frac_elapsed)
    return float(1.0 / (1.0 + np.exp(-slope * float(score_diff))))


def states_from_linescores(df, p0: float) -> List[dict]:
    """Reconstruct leak-free as-of in-game states from a per-quarter linescore frame.

    One state per (game, end-of-Q1/Q2/Q3): score_diff = cumulative home-away AFTER
    that quarter (past only), outcome = realized home win, margin_final = realized
    final margin. p0 (pregame prior) is supplied by the caller and is constant per
    state -- it must be computed on the FIT window only (never the eval outcomes).
    """
    out: List[dict] = []
    for _, r in df.iterrows():
        hc = [float(r["home_q1"]), float(r["home_q2"]), float(r["home_q3"]),
              float(r["home_q4"])]
        ac = [float(r["away_q1"]), float(r["away_q2"]), float(r["away_q3"]),
              float(r["away_q4"])]
        hcum = np.cumsum(hc)
        acum = np.cumsum(ac)
        y = int(hcum[-1] > acum[-1])
        margin_final = float(hcum[-1] - acum[-1])
        for q in (1, 2, 3):
            diff = float(hcum[q - 1] - acum[q - 1])
            frac = 1.0 - _QSEC[q] / _REG_SEC
            out.append({
                "game_id": int(r["event_id"]), "period": q,
                "seconds_remaining": _QSEC[q], "score_diff": diff,
                "p0": float(p0), "p_live": _p_live(diff, frac),
                "outcome": y, "margin_final": margin_final,
            })
    return out


# --------------------------------------------------------------------------- guards
def reject_leaky_prior(states: List[dict]) -> None:
    """LEAK GUARD: a pregame prior that equals the outcome (or its as-of margin sign)
    is the future leaking in. Raise so a leaky build can never produce a verdict."""
    for s in states:
        if abs(float(s["p0"]) - float(s["outcome"])) < 1e-9 and s["outcome"] in (0, 1):
            raise AssertionError(
                "LEAK: p0 equals the realized outcome -- pregame prior saw the future")


def assert_variance_shrink(states: List[dict]) -> Dict[int, float]:
    """FRESHNESS invariant: residual variance of (final margin - as-of margin) must
    DROP as the period rises. Returns the per-period variance; raises if not monotone."""
    var: Dict[int, float] = {}
    for q in (1, 2, 3):
        resid = [s["margin_final"] - s["score_diff"] for s in states if s["period"] == q]
        var[q] = float(np.var(resid)) if resid else float("nan")
    if not (var[1] >= var[2] >= var[3]):
        raise AssertionError(f"variance did not shrink Q1->Q3: {var}")
    return var


# --------------------------------------------------------------------------- verdict
@dataclass
class Verdict:
    verdict: str                                  # baseline-relative: see _label()
    metrics: Dict[str, float] = field(default_factory=dict)
    seasons: Dict[str, str] = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {"verdict": self.verdict,
                # The verdict is graded against a pregame BASE-RATE prior, NOT the
                # market. Beating a base-rate prior with live state is expected and is
                # a CALIBRATION result, never a market edge. The real edge test (vs the
                # in-play devigged close) is unproven here -- it needs in-play odds.
                "baseline": "pregame_base_rate_prior",
                "vs_close": "UNPROVEN -- no in-play odds captured; NOT a market edge",
                "metrics": self.metrics,
                "seasons": self.seasons, "caveats": list(self.caveats)}


def _label(rmse_base: float, rmse_blend: float, dm_p: float) -> str:
    """Honest, BASE-RATE-relative verdict (never close-relative -- the devigged-close
    comparison is skipped in the offline corpus). CALIBRATION_GAIN_VS_BASERATE only if
    the blend's RMSE meaningfully beats the pregame base-rate prior AND the win-prob
    gain is clustered-significant; otherwise MATCHES_BASERATE; a real regression ->
    WORSE_THAN_BASERATE. This is NOT a market-edge claim (no devigged close, no $)."""
    if rmse_blend > rmse_base + 1e-9:
        return "WORSE_THAN_BASERATE"
    rel = (rmse_base - rmse_blend) / rmse_base if rmse_base > 0 else 0.0
    if rel >= 0.02 and dm_p < 0.05:
        return "CALIBRATION_GAIN_VS_BASERATE"
    return "MATCHES_BASERATE"


def evaluate(fit_states: List[dict], eval_states: List[dict],
             seasons: Optional[Dict[str, str]] = None,
             caveats: Optional[List[str]] = None) -> Verdict:
    """Fit the weight surface on fit_states, evaluate OOS on eval_states. Scores
    win-prob with Brier (base vs blend), the final-margin head with RMSE + BIAS
    (NEVER MAE), and runs a game-clustered DM (blend vs pregame-only)."""
    reject_leaky_prior(fit_states)
    reject_leaky_prior(eval_states)
    shrink = assert_variance_shrink(eval_states)

    surf = fit_weight_surface(fit_states, min_cell=20)
    y = np.array([s["outcome"] for s in eval_states], float)
    p0 = np.array([s["p0"] for s in eval_states], float)
    blend = blended_predictions(eval_states, surf)
    brier_base = brier(p0, y)
    brier_blend = brier(blend, y)

    # final-margin head: OLS(as-of diff -> final margin) fit on FIT, scored on EVAL.
    xf = np.array([[s["score_diff"], 1.0] for s in fit_states])
    yf = np.array([s["margin_final"] for s in fit_states])
    coef, *_ = np.linalg.lstsq(xf, yf, rcond=None)
    xe = np.array([[s["score_diff"], 1.0] for s in eval_states])
    ye = np.array([s["margin_final"] for s in eval_states])
    pred_blend = xe @ coef
    pred_base = np.full_like(ye, float(yf.mean()))   # pregame-only: league mean margin
    rmse_base = _rmse(pred_base, ye)
    rmse_blend = _rmse(pred_blend, ye)

    d = (p0 - y) ** 2 - (blend - y) ** 2             # +ve => blend beats base
    dm = diebold_mariano(d, [s["game_id"] for s in eval_states])

    metrics = {
        "rmse_base": round(rmse_base, 4), "rmse_blend": round(rmse_blend, 4),
        "bias": round(_bias(pred_blend, ye), 4),
        "brier_base": round(brier_base, 4), "brier_blend": round(brier_blend, 4),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "n": int(len(eval_states)),
        "var_shrink_q1": round(shrink[1], 2), "var_shrink_q3": round(shrink[3], 2),
    }
    cav = list(caveats or [])
    return Verdict(_label(rmse_base, rmse_blend, dm.p_value),
                   metrics, seasons or {}, cav)


# --------------------------------------------------------------------------- driver
def run_proof(path: str = _LINESCORES) -> Verdict:
    """Load the real one-season linescore corpus, temporal-split it (early -> late),
    and produce an honest verdict. Caveats state the SKIPPED comparisons explicitly."""
    import pandas as pd
    df = pd.read_parquet(path).dropna(
        subset=["home_q1", "home_q2", "home_q3", "home_q4",
                "away_q1", "away_q2", "away_q3", "away_q4"])
    df = df.sort_values("date").reset_index(drop=True)
    cut = df["date"].quantile(0.5)
    fit_df = df[df["date"] < cut]
    eval_df = df[df["date"] >= cut]
    p0 = float((fit_df["home_q1"] + fit_df["home_q2"] + fit_df["home_q3"] + fit_df["home_q4"]
                > fit_df["away_q1"] + fit_df["away_q2"] + fit_df["away_q3"] + fit_df["away_q4"]
                ).mean())
    fit_states = states_from_linescores(fit_df, p0)
    eval_states = states_from_linescores(eval_df, p0)
    seasons = {"train": f"<= {str(cut)[:10]}", "eval": f"> {str(cut)[:10]}",
               "corpus": "nba_2025-26_linescores"}
    caveats = [
        "SKIPPED devigged-close comparison: no closing odds in the offline linescore "
        "corpus; verdict grades calibration vs a pregame BASE-RATE prior, not the close.",
        "SKIPPED cross-season OOS: only ONE real season of linescores is on disk; this "
        "is a same-season TEMPORAL split (early->late). Cross-season is a human-run step "
        "once a 2nd season is ingested.",
        "P0 = fit-window home base rate (leak-free, not a calibrated pregame model); a "
        "stronger prior would shrink the measured gain.",
        "No $-edge is computed or implied. Gain = honest in-game CALIBRATION from "
        "realized state, not a market edge.",
    ]
    return evaluate(fit_states, eval_states, seasons, caveats)


def write_proof(verdict: Verdict, out: str = _OUT) -> str:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii") as f:
        json.dump(verdict.to_dict(), f, indent=2, sort_keys=True)
    return out


def main() -> None:
    v = run_proof()
    p = write_proof(v)
    print(f"verdict={v.verdict}  n={v.metrics['n']}  "
          f"rmse {v.metrics['rmse_base']}->{v.metrics['rmse_blend']}  "
          f"brier {v.metrics['brier_base']}->{v.metrics['brier_blend']}  "
          f"dm_p={v.metrics['dm_p']}")
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
