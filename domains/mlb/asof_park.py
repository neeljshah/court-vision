"""domains.mlb.asof_park — Leak-free MLB park (scoring-environment) factor.

Per-home-team expanding-mean total runs, computed strictly prior-only
(snapshot-before-update).  Current game's runs enter the park history ONLY
AFTER the pre-game factor is recorded — future results can NEVER contaminate
the feature.

Mirrors the walk-forward discipline in ``domains.mlb.asof_features``:
  - Chronological (date, home_team, away_team, event_id) mergesort-stable order.
  - SNAPSHOT-BEFORE-UPDATE: feature for game i uses only games 0..i-1 for that
    home_team; game i updates the park history only AFTER the snapshot is taken.

Output columns per event_id:
  park_total_mean   — home park's prior mean total runs (NaN until MIN_GAMES)
  park_factor       — park_total_mean / league_prior_mean_total (NaN or 1.0)
  park_n_prior      — number of prior home games used for this park

NaN / neutral (factor=1.0) until MIN_GAMES prior home games are observed.

HONEST FRAMING:
  park_factor is an accuracy/calibration lever; it deepens total-runs substrate.
  Markets remain efficient; NO edge is claimed.

PURE pandas/numpy — no src.* / kernel.* / other-domain imports.
PRIVATE: derived from price-bearing corpora; never tracked on the public repo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.mlb.config import GAMES_PARQUET, MIN_GAMES

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Minimum prior home-game appearances before a park factor is non-NaN.
PARK_MIN_GAMES: int = MIN_GAMES  # reuse the existing corpus constant (10)

OUT_COLS = (
    "event_id",
    "park_total_mean",
    "park_factor",
    "park_n_prior",
)

_REQUIRED_COLS = ("event_id", "date", "home_team", "away_team",
                  "home_runs", "away_runs")


def _as_frame(obj, default_path: Path) -> pd.DataFrame:
    """Return a DataFrame from a DataFrame arg or by reading ``default_path``."""
    df = obj.copy() if isinstance(obj, pd.DataFrame) else pd.read_parquet(str(default_path))
    missing = [c for c in _REQUIRED_COLS if c not in df.columns]
    if missing:
        raise KeyError(f"asof_park: input missing columns {missing}")
    return df


def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    """Chronological (date, home_team, away_team, event_id) mergesort-stable order."""
    sk = pd.DataFrame(
        {
            "k0": pd.to_datetime(df["date"]).values,
            "k1": df["home_team"].astype(str).values,
            "k2": df["away_team"].astype(str).values,
            "k3": df["event_id"].astype(str).values,
        },
        index=df.index,
    )
    order = sk.sort_values(["k0", "k1", "k2", "k3"], kind="mergesort").index
    return df.loc[order].reset_index(drop=True)


def build_park_features(
    games=None,
    out_path: Optional[str] = None,
    min_games: int = PARK_MIN_GAMES,
) -> Path:
    """Build leak-free walk-forward park factor → parquet; return Path.

    Parameters
    ----------
    games : DataFrame or None
        Games frame with columns ``_REQUIRED_COLS``.  None → reads default path.
    out_path : str or None
        Override output parquet path.
    min_games : int
        Minimum prior home games before emitting a non-NaN factor (default 10).

    Walk-forward, snapshot-before-update:
      - At each game record the park's prior-mean total runs (NaN if < min_games).
      - Append this game's total_runs to the park's history AFTER the snapshot.
      - Divide park prior mean by the league prior mean (expanding over ALL games
        in chronological order, also snapshot-before-update) to get park_factor.
    """
    df = _as_frame(games, _REPO_ROOT / GAMES_PARQUET)
    df = _sorted(df)

    # Per-park history: home_team -> [sum, count]
    park_hist: Dict[str, List[float]] = {}

    # League-wide history for denominator: [sum, count]
    league_sum = 0.0
    league_n = 0

    eids: List[str] = []
    means: List[float] = []
    factors: List[float] = []
    ns: List[int] = []

    for i in range(len(df)):
        eid = df.at[i, "event_id"]
        home_team = str(df.at[i, "home_team"])
        total = float(df.at[i, "home_runs"]) + float(df.at[i, "away_runs"])

        # --- SNAPSHOT BEFORE UPDATE ---
        rec = park_hist.get(home_team, [0.0, 0])
        park_n = int(rec[1])

        if park_n >= min_games:
            park_mean = rec[0] / park_n
        else:
            park_mean = float("nan")

        # League prior mean (snapshot before this game)
        if league_n >= min_games:
            league_mean = league_sum / league_n
        else:
            league_mean = float("nan")

        # Park factor: ratio; NaN/1.0 when either mean is unavailable
        if (not np.isnan(park_mean)) and (not np.isnan(league_mean)) and league_mean > 0:
            park_fac = park_mean / league_mean
        else:
            park_fac = float("nan")

        eids.append(eid)
        means.append(park_mean)
        factors.append(park_fac)
        ns.append(park_n)

        # --- UPDATE AFTER SNAPSHOT ---
        if home_team not in park_hist:
            park_hist[home_team] = [0.0, 0]
        park_hist[home_team][0] += total
        park_hist[home_team][1] += 1

        league_sum += total
        league_n += 1

    out = pd.DataFrame(
        {
            "event_id": eids,
            "park_total_mean": means,
            "park_factor": factors,
            "park_n_prior": pd.array(ns, dtype="int32"),
        }
    )[list(OUT_COLS)]

    out_p = (
        Path(out_path)
        if out_path
        else _REPO_ROOT / "data/domains/mlb/asof_park.parquet"
    )
    out_p.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(out, preserve_index=False), str(out_p))
    return out_p


def load_park_features(path: Optional[str] = None) -> pd.DataFrame:
    """Load previously built park features parquet."""
    p = (
        Path(path)
        if path
        else _REPO_ROOT / "data/domains/mlb/asof_park.parquet"
    )
    return pd.read_parquet(str(p))
