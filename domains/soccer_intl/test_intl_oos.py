"""domains.soccer_intl.test_intl_oos - honest leak-free OOS validation.

Builds EW ratings on the international corpus UP TO a cutoff, then scores the
held-out last ~2 years of played internationals:
  * O/U-2.5 binary Brier (over side) vs the base-rate baseline,
  * 1X2 three-way multiclass Brier vs the base-rate baseline.

Run ONLY this file (full pytest freezes the box):
    python -m pytest domains/soccer_intl/test_intl_oos.py -q -s

NO edge claim - the assertions only require the model to be NO WORSE than the
base-rate baseline (a calibrated null is a success).  The -s flag prints the
real numbers.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from domains.soccer_intl.config import RESULTS_PARQUET
from domains.soccer_intl.ratings import _lambdas, replay
from domains.soccer.scoreline_engine import markets_from_matrix, scoreline_matrix

_REPO = Path(__file__).resolve().parents[2]
_RESULTS = _REPO / RESULTS_PARQUET
_CUTOFF = dt.date(2024, 6, 1)   # held-out = matches on/after this date (~2 years)


def _load() -> pd.DataFrame:
    if not _RESULTS.exists():
        pytest.skip(f"corpus not materialised at {_RESULTS}")
    df = pd.read_parquet(_RESULTS)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _brier_binary(p, y) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    return float(np.mean((p - y) ** 2))


def _brier_multiclass(P, Y) -> float:
    """Mean squared error over the 3-way (home/draw/away) probability vectors."""
    P, Y = np.asarray(P, float), np.asarray(Y, float)
    return float(np.mean(np.sum((P - Y) ** 2, axis=1)))


def _evaluate():
    """Leak-free walk-forward eval. Returns a results dict (no I/O assertions)."""
    df = _load()
    # Train-period state: strictly before the cutoff (leak-free).
    state = replay(df, until=_CUTOFF)

    played = df[df["home_score"].notna() & df["away_score"].notna()].copy()
    held = played[played["date"].dt.date >= _CUTOFF].copy()
    held = held.sort_values("date", kind="mergesort").reset_index(drop=True)

    over_p, over_y = [], []
    x2_P, x2_Y = [], []

    # Walk FORWARD through held-out matches: predict from prior-only state, then fold.
    for r in held.itertuples():
        home, away = str(r.home_team), str(r.away_team)
        neutral = bool(r.neutral)
        lam_h, lam_a = _lambdas(state, home, away, neutral)
        P = scoreline_matrix(lam_h, lam_a, rho=0.0)
        mk = markets_from_matrix(P, top_n=1)

        over_p.append(float(mk["over_2.5"]))
        over_y.append(1.0 if (r.home_score + r.away_score) >= 3 else 0.0)
        x2_P.append([mk["1X2_home"], mk["1X2_draw"], mk["1X2_away"]])
        if r.home_score > r.away_score:
            x2_Y.append([1, 0, 0])
        elif r.home_score == r.away_score:
            x2_Y.append([0, 1, 0])
        else:
            x2_Y.append([0, 0, 1])

        # fold the realised result so later held-out predictions use it (still
        # strictly prior to THAT match - genuine walk-forward, no leak).
        from domains.soccer_intl.ratings import _fold, _init_team
        _init_team(state, home)
        _init_team(state, away)
        _fold(state, home, away, float(r.home_score), float(r.away_score))

    n = len(over_y)
    over_base = float(np.mean(over_y)) if n else float("nan")
    x2_base = np.mean(np.array(x2_Y, float), axis=0) if n else np.array([np.nan] * 3)

    return {
        "n": n,
        "ou_brier_model": _brier_binary(over_p, over_y),
        "ou_brier_base": _brier_binary([over_base] * n, over_y),
        "ou_over_rate": over_base,
        "x2_brier_model": _brier_multiclass(x2_P, x2_Y),
        "x2_brier_base": _brier_multiclass([x2_base.tolist()] * n, x2_Y),
        "x2_base_rates": x2_base.tolist(),
    }


def test_oos_no_worse_than_base_rate():
    res = _evaluate()
    print("\n=== soccer_intl OOS walk-forward (held-out >= 2024-06-01) ===")
    print(f"  held-out matches: {res['n']}")
    print(f"  O/U-2.5  Brier: model={res['ou_brier_model']:.4f}  "
          f"base-rate={res['ou_brier_base']:.4f}  (over-rate={res['ou_over_rate']:.3f})")
    print(f"  1X2 (3way) Brier: model={res['x2_brier_model']:.4f}  "
          f"base-rate={res['x2_brier_base']:.4f}  "
          f"base-rates H/D/A={[round(x,3) for x in res['x2_base_rates']]}")
    print("  HONEST: calibration only; no edge claimed; matching the base-rate is a pass.")

    assert res["n"] > 200, "too few held-out matches to validate"
    # A calibrated model should be NO WORSE than the base rate (small tolerance).
    assert res["ou_brier_model"] <= res["ou_brier_base"] + 0.01
    assert res["x2_brier_model"] <= res["x2_brier_base"] + 0.01


if __name__ == "__main__":
    import json
    print(json.dumps(_evaluate(), indent=2))
