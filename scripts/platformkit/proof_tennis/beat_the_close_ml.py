"""scripts.platformkit.proof_tennis.beat_the_close_ml — ATP match-win: do we match the close?

The same beat-the-close test the NBA moneyline proof runs (proof_nba/ml_accuracy.py), on
ATP tennis: a leak-free walk-forward surface-blended Elo win-probability + leak-free Platt
recalibration vs the devigged Pinnacle closing line, scored on Brier over a held-out window.

"Beat the best prediction" = lower Brier than the devigged close on the SAME real outcomes.
Markets are efficient, so MATCH (within sampling noise) is the realistic best case; Pinnacle
prices ATP very sharply, so the honest expectation here is BEHIND (Elo ~0.226 vs Pinnacle
~0.200 per the edge map). Honest either way. No $ edge claimed.

LEAK GUARD (triple-checked): the score/winner fields in tennis are winner-ordered, which would
leak the outcome. This module NEVER uses winner-order. The corpus already stores a SYMMETRIC
player ordering independent of the outcome: matches.parquet has p1_id < p2_id for 100% of rows,
and odds.parquet maps the Pinnacle decimal odds to that SAME id-order (ps_p1/ps_p2), verified
outcome-independent. We predict P(p1 wins) where p1 is the lower-id player; the Elo win-prob and
the devigged market prob are both expressed in that id-order. The realized label is winner==1.
The closing line is ONLY the comparison forecaster, never an Elo input.

Leak-free Elo: each row's win_prob uses ratings built from strictly-prior matches only
(walk-forward). Leak-free Platt: each calibrator is fit on strictly-prior rows only.
INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Run: python -m scripts.platformkit.proof_tennis.beat_the_close_ml
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.tennis.elo_core import SURFACE_BLEND  # noqa: E402
from domains.tennis.elo_tune import _walk_forward_blend, platt_recalibrate  # noqa: E402

_MATCHES = _REPO / "data/domains/tennis/matches.parquet"
_ODDS = _REPO / "data/domains/tennis/odds.parquet"
_TRAIN_YEAR_MAX = 2022  # train (Elo warm-up + Platt fit) <= this; held-out test > this


def _corpus_from_env() -> Optional[Path]:
    """$PROOF_CORPUS_ROOT/tennis if set, else None (real data/domains default)."""
    root = os.environ.get("PROOF_CORPUS_ROOT")
    return Path(root) / "tennis" if root else None


def _brier_logloss(p: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(np.mean((p - y) ** 2)), float(
        -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _devig_market(odds: pd.DataFrame) -> pd.DataFrame:
    """Devig Pinnacle close to P(p1 win) in the id-order p1/p2 (outcome-independent)."""
    o = odds.dropna(subset=["ps_p1", "ps_p2"]).copy()
    o = o[(o["ps_p1"] > 1.0) & (o["ps_p2"] > 1.0)]
    imp1 = 1.0 / o["ps_p1"].to_numpy(float)
    imp2 = 1.0 / o["ps_p2"].to_numpy(float)
    o["p_market"] = imp1 / (imp1 + imp2)        # devig, mapped to p1 (lower id)
    return o[["event_id", "p_market"]]


def run(corpus: Optional[Path] = None) -> Dict:
    # precedence: explicit corpus arg > $PROOF_CORPUS_ROOT/tennis > real data/domains path
    root = corpus or _corpus_from_env()
    matches_path = (root / "matches.parquet") if root is not None else _MATCHES
    odds_path = (root / "odds.parquet") if root is not None else _ODDS
    matches = pd.read_parquet(matches_path)
    odds = pd.read_parquet(odds_path)

    # --- leak-free walk-forward surface-blended Elo (win_prob_p1 = P(lower-id wins)) ---
    wf = _walk_forward_blend(matches, blend=SURFACE_BLEND)

    # --- leak-free Platt recal: fit only on strictly-prior rows; test = year > TRAIN_YEAR_MAX ---
    test = platt_recalibrate(wf, train_year_max=_TRAIN_YEAR_MAX)
    test = test.copy()
    # Prefer the recalibrated prob (calibration housekeeping), fall back to raw if NaN.
    p_model = test["win_prob_recal"].to_numpy(float)
    raw = test["win_prob_p1"].to_numpy(float)
    p_model = np.where(np.isnan(p_model), raw, p_model)
    test["p_model"] = p_model

    # --- devigged Pinnacle close, joined on event_id (NO winner-order anywhere) ---
    mkt = _devig_market(odds)
    m = test.merge(mkt, on="event_id", how="inner").reset_index(drop=True)
    m = m.dropna(subset=["p_model", "p_market"]).reset_index(drop=True)
    n = len(m)
    if n < 60:
        return {"status": "data_limited", "n": n}

    y = (m["winner"] == 1).to_numpy(float)     # label: did p1 (lower id) win — symmetric
    pm = m["p_model"].to_numpy(float)
    pk = m["p_market"].to_numpy(float)

    b_model, ll_model = _brier_logloss(pm, y)
    b_mkt, ll_mkt = _brier_logloss(pk, y)
    gap = round(b_model - b_mkt, 4)            # >0 => market sharper

    if gap < -0.002:
        verdict = (f"BEATS: OUR Elo beats the Pinnacle close on Brier "
                   f"({round(b_model, 4)} vs {round(b_mkt, 4)})")
    elif gap <= 0.010:
        verdict = (f"MATCH: OUR Elo matches the Pinnacle close within noise "
                   f"(Brier {round(b_model, 4)} vs {round(b_mkt, 4)}, gap {gap:+})")
    else:
        verdict = (f"BEHIND: Pinnacle sharper by {gap} Brier — ATP closes are very "
                   f"efficient; Elo lacks the market's freshness/news edge")

    return {
        "status": "ok",
        "n": n,
        "model_metric": round(b_model, 4),
        "close_metric": round(b_mkt, 4),
        "metric_name": "Brier",
        "model_logloss": round(ll_model, 4),
        "close_logloss": round(ll_mkt, 4),
        "gap": gap,
        "corr_model_close": round(float(np.corrcoef(pm, pk)[0, 1]), 3),
        "verdict": verdict,
        "note": "ATP win-prob accuracy vs the devigged Pinnacle close on real outcomes. "
                "Symmetric id-order (p1_id<p2_id) — no winner-order leak. No $ edge claimed.",
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n={rep.get('n')}")
        return 0
    print(f"=== ATP moneyline: OUR walk-forward Elo (Platt-recal) vs the devigged "
          f"Pinnacle close (held-out n={rep['n']}, year>{_TRAIN_YEAR_MAX}) ===")
    print(f"  {'predictor':>14}  {'Brier':>8} {'LogLoss':>8}")
    print(f"  {'Pinnacle close':>14}  {rep['close_metric']:>8} {rep['close_logloss']:>8}")
    print(f"  {'our Elo':>14}  {rep['model_metric']:>8} {rep['model_logloss']:>8}")
    print(f"\ncorr(model, close) = {rep['corr_model_close']}  |  "
          f"Brier gap to close: {rep['gap']:+}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
