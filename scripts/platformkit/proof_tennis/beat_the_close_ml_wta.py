"""scripts.platformkit.proof_tennis.beat_the_close_ml_wta — WTA match-win: do we
match the close?

WTA arm of beat_the_close_ml.py (same leak-free walk-forward surface-blended Elo +
leak-free Platt recalibration vs the devigged Pinnacle closing line, scored on Brier
over a held-out window). Un-PENDs the WTA close comparison now that WTA odds rows
exist (tour='wta' in data/domains/tennis/odds.parquet, joined via
domains.tennis.ingest_tennisdata against the Sackmann WTA matches corpus
wta_matches.parquet).

"Beat the best prediction" = lower Brier than the devigged close on the SAME real
outcomes. Markets are efficient, so MATCH (within sampling noise) is the realistic
best case, same framing as the ATP arm. Honest either way. No $ edge claimed.

LEAK GUARD: identical anti-leak orientation as the ATP arm — matches.parquet has
p1_id < p2_id for 100% of rows, odds.parquet maps prices to that SAME id-order
(ps_p1/ps_p2), independent of winner. We predict P(p1 wins); the closing line is
ONLY the comparison forecaster, never an Elo input.

PROVENANCE: WTA is a SEPARATE corpus from ATP (wta_matches.parquet, tour='wta' rows
of odds.parquet) — this module never pools ATP and WTA evidence into one verdict;
each tour's Brier is reported independently.

INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Run: python -m scripts.platformkit.proof_tennis.beat_the_close_ml_wta
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

_MATCHES = _REPO / "data/domains/tennis/wta_matches.parquet"
_ODDS = _REPO / "data/domains/tennis/odds.parquet"  # filtered to tour == 'wta'
_TRAIN_YEAR_MAX = 2022  # same split convention as the ATP arm


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
    o = odds[odds["tour"] == "wta"].dropna(subset=["ps_p1", "ps_p2"]).copy()
    o = o[(o["ps_p1"] > 1.0) & (o["ps_p2"] > 1.0)]
    imp1 = 1.0 / o["ps_p1"].to_numpy(float)
    imp2 = 1.0 / o["ps_p2"].to_numpy(float)
    o["p_market"] = imp1 / (imp1 + imp2)        # devig, mapped to p1 (lower id)
    return o[["event_id", "p_market"]]


def run(corpus: Optional[Path] = None) -> Dict:
    # precedence: explicit corpus arg > $PROOF_CORPUS_ROOT/tennis > real data/domains path
    root = corpus or _corpus_from_env()
    matches_path = (root / "wta_matches.parquet") if root is not None else _MATCHES
    odds_path = (root / "odds.parquet") if root is not None else _ODDS
    if not matches_path.exists() or not odds_path.exists():
        return {"status": "corpus_missing", "matches_path": str(matches_path),
                "odds_path": str(odds_path)}
    matches = pd.read_parquet(matches_path)
    odds = pd.read_parquet(odds_path)

    # --- leak-free walk-forward surface-blended Elo (win_prob_p1 = P(lower-id wins)) ---
    wf = _walk_forward_blend(matches, blend=SURFACE_BLEND)

    # --- leak-free Platt recal: fit only on strictly-prior rows; test = year > TRAIN_YEAR_MAX ---
    test = platt_recalibrate(wf, train_year_max=_TRAIN_YEAR_MAX)
    test = test.copy()
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
        verdict = (f"BEHIND: Pinnacle sharper by {gap} Brier -- WTA closes are "
                   f"efficient; Elo lacks the market's freshness/news edge")

    return {
        "status": "ok",
        "tour": "wta",
        "n": n,
        "model_metric": round(b_model, 4),
        "close_metric": round(b_mkt, 4),
        "metric_name": "Brier",
        "model_logloss": round(ll_model, 4),
        "close_logloss": round(ll_mkt, 4),
        "gap": gap,
        "corr_model_close": round(float(np.corrcoef(pm, pk)[0, 1]), 3),
        "verdict": verdict,
        "note": "WTA win-prob accuracy vs the devigged Pinnacle close on real outcomes. "
                "Symmetric id-order (p1_id<p2_id) — no winner-order leak. Separate "
                "corpus from ATP (no pooling). No $ edge claimed.",
    }


def _main() -> int:
    rep = run()
    if rep.get("status") == "corpus_missing":
        print(f"corpus_missing: matches={rep['matches_path']} odds={rep['odds_path']}")
        return 2
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n={rep.get('n')}")
        return 0
    print(f"=== WTA moneyline: OUR walk-forward Elo (Platt-recal) vs the devigged "
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
