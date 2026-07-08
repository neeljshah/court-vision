"""Tidy-prep: our own scraped line feed (data/cache/line_history/<sport>/*.jsonl)
-> one row per (sport, game_id, market_type, side, book) pre-close drift
observation, written to data/domains/cross_sport_market/line_dynamics.parquet.

Grain choice: ONE row per (game_id, market_type, side, book) tuple (not per
timestamp) -- each row already summarizes that quote's whole pre-close path,
which is exactly the claims-factory's expected "one row = one observation"
shape (mirrors domains/soccer_intl/claims_grid.py's travel_scouting grain
note). `obs_id` is that same tuple joined into one string, so it is unique
BY CONSTRUCTION (verified this session: 0 duplicates) -- the factory's floor
mechanism (count_distinct(floor_col) per entity group) never undercounts.

DESCRIPTIVE ONLY: drift = raw devigged-prob change over a pre-close window.
No forecast, no $ figure, no bet signal -- edge_claimed:false is enforced
downstream by claims_factory.py itself.

Pre-close window: minutes_to_close in [0, 2880] (48h) -- keeps live/near-term
games, drops futures markets (commence_time months out) that would otherwise
dominate the "drift" stat with noise from a market that isn't approaching a
real close. Verified this session: only mlb/soccer_intl/wnba have any rows in
this window right now (kbo/nba/npb/soccer/tennis commence_time is either
offseason-far or futures-far) -- BLOCKED-on-premise for those sports is
reported by the caller, not silently papered over here.

CLI: python -m scripts.platformkit.quant.line_dynamics_prep
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.platformkit.intel_validation.basketball_claims_io import atomic_write_parquet
import pyarrow as pa

REPO_ROOT = Path(__file__).resolve().parents[3]
LINE_HISTORY_DIR = REPO_ROOT / "data" / "cache" / "line_history"
OUT_PATH = REPO_ROOT / "data" / "domains" / "cross_sport_market" / "line_dynamics.parquet"
_PRE_CLOSE_MAX_MIN = 2880.0  # 48h -- drop far-future/futures-market rows
_LONGSHOT_PROB = 0.15
_WINDOWS_MIN = (60, 30, 10)
_SPORTS = ("kbo", "mlb", "nba", "npb", "soccer", "soccer_intl", "tennis", "wnba")


def _load_sport_raw(sport: str) -> pd.DataFrame:
    rows = []
    for fn in sorted(glob.glob(str(LINE_HISTORY_DIR / sport / "*.jsonl"))):
        with open(fn, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue
    return pd.DataFrame(rows)


def _prep_sport(sport: str) -> pd.DataFrame:
    df = _load_sport_raw(sport)
    if df.empty or "devigged_prob" not in df.columns:
        return pd.DataFrame()
    df = df.dropna(subset=["devigged_prob", "game_id", "market_type", "side", "book"])
    df["captured_at"] = pd.to_datetime(df["captured_at"], utc=True, errors="coerce")
    df["commence_time"] = pd.to_datetime(df["commence_time"], utc=True, errors="coerce")
    df = df.dropna(subset=["captured_at", "commence_time"])
    df["minutes_to_close"] = (df["commence_time"] - df["captured_at"]).dt.total_seconds() / 60.0
    df = df[(df["minutes_to_close"] >= 0) & (df["minutes_to_close"] <= _PRE_CLOSE_MAX_MIN)]
    if df.empty:
        return pd.DataFrame()

    out_rows = []
    group_cols = ["game_id", "market_type", "side", "book"]
    for keys, g in df.groupby(group_cols, sort=False):
        g = g.sort_values("captured_at")
        rec = dict(zip(group_cols, keys))
        drift = {}
        for w in _WINDOWS_MIN:
            win = g[g["minutes_to_close"] <= w]
            if win["captured_at"].nunique() >= 2:
                drift[w] = float(win["devigged_prob"].iloc[-1] - win["devigged_prob"].iloc[0])
            else:
                drift[w] = np.nan

        win60 = g[g["minutes_to_close"] <= 60]
        if win60["captured_at"].nunique() >= 3:
            diffs = win60["devigged_prob"].diff().dropna()
            diffs = diffs[diffs != 0]
            signs = np.sign(diffs)
            reversal_flag = int((signs.values[1:] != signs.values[:-1]).any()) if len(signs) > 1 else 0
        else:
            reversal_flag = np.nan

        if win60["captured_at"].nunique() >= 2 and not np.isnan(drift[60]):
            start_prob = float(win60["devigged_prob"].iloc[0])
            is_longshot_start = bool(start_prob < _LONGSHOT_PROB)
            longshot_down_flag = int(drift[60] < 0) if is_longshot_start else np.nan
        else:
            is_longshot_start = np.nan
            longshot_down_flag = np.nan

        rec.update({
            "drift_60m": drift[60], "drift_30m": drift[30], "drift_10m": drift[10],
            "reversal_flag": reversal_flag,
            "is_longshot_start": is_longshot_start,
            "longshot_down_flag": longshot_down_flag,
        })
        out_rows.append(rec)

    res = pd.DataFrame(out_rows)
    res.insert(0, "sport", sport)
    res["market_bucket"] = res["sport"] + "_" + res["market_type"]
    res["obs_id"] = (
        res["game_id"].astype(str) + "_" + res["market_type"] + "_"
        + res["side"] + "_" + res["book"]
    )
    return res


def build(out_path: Path | None = None) -> dict:
    out_path = out_path or OUT_PATH
    parts = [p for s in _SPORTS if not (p := _prep_sport(s)).empty]
    combined = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    # Drift family needs all 4 dims non-null for a clean floor count (see module docstring).
    drift_ready = combined.dropna(
        subset=["drift_60m", "drift_30m", "drift_10m", "reversal_flag"]
    ).copy() if not combined.empty else combined
    if not drift_ready.empty:
        drift_ready["reversal_flag"] = drift_ready["reversal_flag"].astype(int)
    atomic_write_parquet(pa.Table.from_pandas(drift_ready, preserve_index=False), out_path)
    coverage = (
        combined.groupby("sport").size().to_dict() if not combined.empty else {}
    )
    longshot_n = int((combined["is_longshot_start"] == True).sum()) if not combined.empty else 0  # noqa: E712
    return {
        "out_path": str(out_path),
        "n_rows": len(drift_ready),
        "raw_pre_close_coverage_by_sport": coverage,
        "n_longshot_start_obs": longshot_n,
    }


def main() -> int:
    summary = build()
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
