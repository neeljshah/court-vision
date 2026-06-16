"""scripts.platformkit.proof_mlb.beat_the_close_total — MLB totals: match the close?

The headline-ML map is done; this runs the SAME beat-the-close test on the TOTALS market,
framed exactly like the NBA totals map (RMSE of a POINT forecast, not Brier of P(over)).

WHY RMSE, NOT BRIER-OF-P(OVER): a totals market is priced so over/under is ~50/50 AT THE LINE
(both sides ~ -110). So the market's devigged P(over) is ~0.5 by construction and a Brier
comparison against it is uninformative (it barely beats a coin flip — that is a property of how
totals are priced, NOT of the close's forecasting power). The honest apples-to-apples test is:
treat the closing LINE (closeou) as the market's POINT forecast of total runs, our model's
expected total (lam_home + lam_away) as ours, and score RMSE to the realized total. This mirrors
scripts/platformkit/proof_nba/asof_box_accuracy.py (NBA totals RMSE-vs-close).

"Beat the best prediction" = lower RMSE-to-realized than the closing line. Markets are efficient,
so MATCHING the close (within noise) is the realistic best case. Honest either way. NO $ edge.

Leak-free: run-rate lambdas snapshot BEFORE each game's result is incorporated (RunRateState),
RMSE scored on the held-out SECOND half only; the closing line is the comparison forecaster,
NEVER a model input.

DATA NOTE: closeou is populated on ~3.36k rows (2020-21 seasons only) — data-limited but a
genuine overlap.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; calibration only.
Run: python -m scripts.platformkit.proof_mlb.beat_the_close_total
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.mlb.inning_engine import RunRateState  # noqa: E402


def _corpus_from_env() -> Optional[Path]:
    """$PROOF_CORPUS_ROOT/mlb if set else None (shared corpus-override contract)."""
    root = os.environ.get("PROOF_CORPUS_ROOT")
    return (Path(root) / "mlb") if root else None


def _resolve(corpus: Optional[Path]) -> Tuple[Path, Path]:
    """(games_path, odds_path): explicit arg > env > real data/domains (unchanged default)."""
    root = corpus or _corpus_from_env()
    if root is not None:
        return root / "games.parquet", root / "odds.parquet"
    return (_REPO / "data/domains/mlb/games.parquet",
            _REPO / "data/domains/mlb/odds.parquet")


def _rmse(pred: np.ndarray, y: np.ndarray) -> float:
    return float(np.sqrt(np.mean((pred - y) ** 2)))


def _bias(pred: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean(pred - y))


def _load_overlap(games_path: Path, odds_path: Path):
    """Merge games with closeou rows; date-sorted. Returns a DataFrame."""
    import pandas as pd
    g = pd.read_parquet(games_path)
    o = pd.read_parquet(odds_path)
    o = o.dropna(subset=["closeou"])
    m = g.merge(o[["event_id", "closeou"]], on="event_id", how="inner")
    m = m.dropna(subset=["home_runs", "away_runs", "closeou"])
    m["date"] = pd.to_datetime(m["date"])
    m = m.sort_values(["date", "event_id"]).reset_index(drop=True)
    return m


def _walk_forward_lambdas(games_all) -> Dict[str, Tuple[float, float]]:
    """Leak-free run-rate snapshot per event_id over the FULL corpus (warms up ratings).

    Returns event_id -> (lam_home, lam_away) BEFORE that game's result is incorporated.
    Walking the full date-sorted corpus (not just the overlap) gives mature ratings by 2020.
    """
    import pandas as pd
    df = games_all.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "event_id"]).reset_index(drop=True)
    rr = RunRateState()
    out: Dict[str, Tuple[float, float]] = {}
    h = df["home_team"].to_numpy(); a = df["away_team"].to_numpy()
    hr = df["home_runs"].to_numpy(float); ar = df["away_runs"].to_numpy(float)
    se = df["season"].to_numpy(int); ev = df["event_id"].to_numpy()
    for i in range(len(df)):
        home, away = str(h[i]), str(a[i])
        lh, la = rr.snapshot(home, away, int(se[i]))
        out[str(ev[i])] = (lh, la)
        rr.update(home, away, hr[i], ar[i])
    return out


def run(corpus: Optional[Path] = None) -> Dict:
    games_path, odds_path = _resolve(corpus)
    games_all = __import__("pandas").read_parquet(games_path)
    lam_map = _walk_forward_lambdas(games_all)
    m = _load_overlap(games_path, odds_path)
    n = len(m)
    if n < 60:
        return {"status": "data_limited", "n": n}

    ev = m["event_id"].to_numpy()
    line = m["closeou"].to_numpy(float)
    hr = m["home_runs"].to_numpy(float); ar = m["away_runs"].to_numpy(float)
    realized = hr + ar

    model_total = np.array([sum(lam_map.get(str(ev[i]), (4.4, 4.4))) for i in range(n)])

    mid = n // 2
    te = slice(mid, n)
    rmse_model = _rmse(model_total[te], realized[te])
    rmse_close = _rmse(line[te], realized[te])
    gap = round(rmse_model - rmse_close, 4)  # >0 => close sharper

    if gap < -0.05:
        verdict = (f"OUR run-rate totals model BEATS the close on RMSE "
                   f"({round(rmse_model,3)} vs {round(rmse_close,3)})")
    elif gap <= 0.20:
        verdict = (f"MATCH: our model RMSE {round(rmse_model,3)} ~ close {round(rmse_close,3)} "
                   f"(gap {gap:+}) on real total runs")
    else:
        verdict = (f"BEHIND: close sharper by {gap} RMSE — the freshness edge "
                   f"(lineups/weather/park/starting-pitcher) our pregame run-rate model lacks")

    return {
        "status": "ok",
        "n": n, "n_holdout": n - mid,
        "model_total_rmse": round(rmse_model, 3),
        "close_total_rmse": round(rmse_close, 3),
        "gap": gap,
        "model_bias": round(_bias(model_total[te], realized[te]), 3),
        "close_bias": round(_bias(line[te], realized[te]), 3),
        "mean_realized_total": round(float(realized[te].mean()), 2),
        "verdict": verdict,
        "note": ("MLB totals: model expected runs (lam_home+lam_away) vs the closing LINE as "
                 "point forecasts, RMSE to realized total (NBA-totals framing). closeou is "
                 "2020-21 only (data-limited). Brier-of-P(over) is intentionally NOT used: a "
                 "totals line is ~50/50 by construction so a market P(over) Brier is "
                 "uninformative. Leak-free: lambdas snapshot-before-update, RMSE on held-out "
                 "second half, close used only as comparator. NO $ edge."),
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n={rep.get('n')}")
        return 0
    print(f"=== MLB totals: OUR run-rate expected total vs the closing line "
          f"(n={rep['n']}, holdout={rep['n_holdout']}) ===")
    print(f"  mean realized total (holdout) = {rep['mean_realized_total']}")
    print(f"  {'predictor':>13}  {'RMSE':>8} {'bias':>8}")
    print(f"  {'close line':>13}  {rep['close_total_rmse']:>8} {rep['close_bias']:>8}")
    print(f"  {'our run-rate':>13}  {rep['model_total_rmse']:>8} {rep['model_bias']:>8}")
    print(f"\nRMSE gap to close: {rep['gap']:+}  (>0 => close sharper)")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
