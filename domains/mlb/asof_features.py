"""domains.mlb.asof_features — leak-free walk-forward AS-OF starting-pitcher form.

The single biggest MLB predictor is the STARTING PITCHER.  ``ingest_pitchers``
captures the SP *identity* (announced rotations = leak-free) per game keyed 1:1 to
``games.parquet``; this builder turns identity into a leak-free trailing-form
feature by replaying games in date order and, BEFORE recording each game, looking
up each starter's mean runs-allowed over their STRICTLY-PRIOR starts.

Mirrors ``domains.mlb.ratings`` walk-forward discipline:
  - chronological (date, home_team, away_team, event_id) mergesort-stable order,
  - SNAPSHOT-BEFORE-UPDATE: the per-game feature uses only that pitcher's starts
    with date < the current game; the current game updates history only AFTER the
    snapshot is recorded, so future results can never contaminate features.

LEAK NOTE — honest approximation:
  Runs-allowed is a TEAM-PITCHING PROXY for the starter, not isolated to the SP:
  when the HOME starter pitches, the runs his side allows == ``away_runs``; when
  the AWAY starter pitches, runs allowed == ``home_runs``.  This bundles bullpen
  innings with the starter's — a documented over-attribution, NOT an isolated SP
  ERA.  It deepens the substrate / calibration; it is NOT a market edge and no
  edge is claimed.  History is indexed by pitcher NAME, so a pitcher's home and
  away prior starts combine into one trailing record.

Sign convention: ``sp_ra_diff_asof = away_sp_ra_asof - home_sp_ra_asof`` — a
HIGHER value means the AWAY starter has allowed more runs historically (worse),
so higher == HOME edge.

PURE pandas/numpy.  No ``src.*`` / ``kernel.*`` / other-domain imports.

PRIVATE: derived from price-bearing corpora; never tracked on the public repo.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.mlb.config import GAMES_PARQUET

_REPO_ROOT = Path(__file__).resolve().parents[2]

OUT_COLS = (
    "event_id",
    "home_sp_ra_asof", "away_sp_ra_asof", "sp_ra_diff_asof",
    "home_sp_starts_prior", "away_sp_starts_prior",
)
# Columns needed off pitchers / games sidecars.
_PITCHER_COLS = (
    "event_id", "date", "home_sp_name", "away_sp_name",
    "home_sp_present", "away_sp_present",
)
_GAME_COLS = ("event_id", "home_runs", "away_runs")


def _default_pitchers_path() -> Path:
    return _REPO_ROOT / "data/domains/mlb/pitchers.parquet"


def _default_games_path() -> Path:
    return _REPO_ROOT / GAMES_PARQUET


def _as_frame(obj, default_path: Path, cols) -> pd.DataFrame:
    """Return a DataFrame from a DataFrame arg or by reading ``default_path``."""
    df = obj.copy() if isinstance(obj, pd.DataFrame) else pd.read_parquet(str(default_path))
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"input missing columns {missing}")
    return df


def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    """Chronological (date, home_team, away_team, event_id) mergesort-stable order.

    Mirrors ``ratings._sorted`` so the replay walks rows in a deterministic,
    date-granular sequence; same-day doubleheaders never feed each other because
    the trailing lookup is strict-before only at the per-pitcher level.
    """
    sort_df = pd.DataFrame(
        {
            "k0": pd.to_datetime(df["date"]).values,
            "k1": df["home_team"].astype(str).values if "home_team" in df.columns else "",
            "k2": df["away_team"].astype(str).values if "away_team" in df.columns else "",
            "k3": df["event_id"].astype(str).values,
        },
        index=df.index,
    )
    order = sort_df.sort_values(["k0", "k1", "k2", "k3"], kind="mergesort").index
    return df.loc[order].reset_index(drop=True)


def build_asof_features(pitchers=None, games=None, out_path=None) -> Path:
    """Build leak-free walk-forward AS-OF starting-pitcher form → parquet; return Path.

    Parameters accept DataFrames OR fall back to the default sidecar paths
    (so tests pass tiny synthetic frames and never touch the real corpus).

    Walk-forward, snapshot-before-update:
      For each game in chronological order, for the home and away SP NAME, record
      the trailing-mean runs-allowed over that pitcher's STRICTLY-PRIOR starts
      (NaN when 0 prior starts or the SP name is absent), THEN append the current
      game's runs-allowed proxy to each starter's history.

    Runs-allowed proxy: home SP -> ``away_runs``; away SP -> ``home_runs``.
    Output keyed ``event_id`` (1 row per pitchers row), columns ``OUT_COLS``.
    """
    pf = _as_frame(pitchers, _default_pitchers_path(), _PITCHER_COLS)
    gf = _as_frame(games, _default_games_path(), _GAME_COLS)

    runs = gf[list(_GAME_COLS)].drop_duplicates("event_id").set_index("event_id")
    df = _sorted(pf)

    # Per-pitcher trailing history: name -> (running sum, count) of runs-allowed.
    hist: Dict[str, List[float]] = {}  # name -> [sum, count]

    def _asof(name, present) -> tuple:
        """Trailing mean & count of prior starts for ``name`` (NaN/0 if none)."""
        if not bool(present) or name is None or (isinstance(name, float) and pd.isna(name)):
            return float("nan"), 0
        rec = hist.get(str(name))
        if not rec or rec[1] == 0:
            return float("nan"), 0
        return rec[0] / rec[1], int(rec[1])

    def _update(name, present, ra) -> None:
        """Append this game's runs-allowed proxy to ``name``'s history."""
        if not bool(present) or name is None or (isinstance(name, float) and pd.isna(name)):
            return
        if ra is None or (isinstance(ra, float) and np.isnan(ra)):
            return
        rec = hist.setdefault(str(name), [0.0, 0])
        rec[0] += float(ra)
        rec[1] += 1

    eids: List[str] = []
    h_ra: List[float] = []
    a_ra: List[float] = []
    h_n: List[int] = []
    a_n: List[int] = []

    for i in range(len(df)):
        eid = df["event_id"].iloc[i]
        h_name = df["home_sp_name"].iloc[i]
        a_name = df["away_sp_name"].iloc[i]
        h_present = df["home_sp_present"].iloc[i]
        a_present = df["away_sp_present"].iloc[i]

        # Outcome lookup (proxy mapping). Missing game row -> NaN runs-allowed.
        if eid in runs.index:
            home_runs = float(runs.at[eid, "home_runs"])
            away_runs = float(runs.at[eid, "away_runs"])
        else:
            home_runs = away_runs = float("nan")
        home_ra = away_runs  # home SP's side allowed the away team's runs
        away_ra = home_runs  # away SP's side allowed the home team's runs

        # --- snapshot BEFORE update (strict-prior trailing form) ---
        hm, hc = _asof(h_name, h_present)
        am, ac = _asof(a_name, a_present)
        eids.append(eid)
        h_ra.append(hm)
        a_ra.append(am)
        h_n.append(hc)
        a_n.append(ac)

        # --- update AFTER snapshot ---
        _update(h_name, h_present, home_ra)
        _update(a_name, a_present, away_ra)

    out = pd.DataFrame(
        {
            "event_id": eids,
            "home_sp_ra_asof": h_ra,
            "away_sp_ra_asof": a_ra,
            # away_minus_home: higher == home edge (away SP historically worse).
            "sp_ra_diff_asof": np.subtract(a_ra, h_ra),
            "home_sp_starts_prior": pd.array(h_n, dtype="int32"),
            "away_sp_starts_prior": pd.array(a_n, dtype="int32"),
        }
    )[list(OUT_COLS)]

    out_p = Path(out_path) if out_path else (_REPO_ROOT / "data/domains/mlb/asof_features.parquet")
    out_p.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(out, preserve_index=False), str(out_p))
    return out_p


def _report(df: pd.DataFrame) -> str:
    """Coverage summary string for the CLI."""
    n = len(df)
    if n == 0:
        return "0 rows"
    both = ((df["home_sp_starts_prior"] > 0) & (df["away_sp_starts_prior"] > 0)).sum()
    return f"{n} rows | both-SP-have-prior {both / n * 100.0:.1f}%"


def main() -> None:
    """Entry: ``python -m domains.mlb.asof_features [--out PATH]`` (reads default sidecars)."""
    ap = argparse.ArgumentParser(description="Leak-free walk-forward AS-OF MLB SP form → parquet")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = build_asof_features(out_path=args.out)
    df = pd.read_parquet(str(out))
    print(f"wrote {out}")
    print(_report(df))
    if len(df):
        print(df.head(5).to_string(index=False))


if __name__ == "__main__":
    main()
