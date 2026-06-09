"""build_per_player_calibration.py — INT-69: Per-Player Calibration Shift (B5).

Corrects systematic FIRST-MOMENT bias (model under/over-predicts a specific player).
Distinct from INT-16 (second-moment volatility / CV shrinkage).

Residual source priority:
  1. data/cache/pregame_oof.parquet  (has player_id — PREFERRED)
  2. L5 proxy: oof_pred ≈ L5 rolling mean(actual).shift(1) — flagged as "l5_proxy"

Per (player_id, stat, asof_date):
  window = last 20 prior games strict < asof_date, rolling(20, min_periods=10)
  residuals = actual - oof_pred
  bias_l20 = residuals.mean()
  bias_z_l20 = bias_l20 / (residuals.std(ddof=1) + 1e-6)
  shrink = n / (n + 10)  [James-Stein toward zero]
  bias_shift_applied = 0.5 * shrink * bias_l20

Output schema (long format):
  player_id, player_name, asof_date, stat,
  n_prior_games, bias_l20, bias_z_l20, sigma_resid, bias_shift_applied,
  residual_source, build_ts

Coverage gate: n_prior_games >= 10.
Stats: pts, reb, ast, fg3m, stl, blk, tov.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
WINDOW = 20
MIN_PERIODS = 10
JS_K = 10  # James-Stein shrinkage denominator
MULTIPLIER = 0.5  # conservative shift multiplier

_OOF = ROOT / "data" / "cache" / "pregame_oof.parquet"
_OUT = ROOT / "data" / "intelligence" / "per_player_calibration.parquet"
_NBA_DIR = ROOT / "data" / "nba"


# ---------------------------------------------------------------------------
# Player name -> id mapping (for attaching player_name to output)
# ---------------------------------------------------------------------------
def _build_pid_to_name() -> Dict[int, str]:
    pid_to_name: Dict[int, str] = {}
    for season in ("2023-24", "2024-25", "2025-26"):
        path = _NBA_DIR / f"player_avgs_{season}.json"
        if not path.exists():
            continue
        try:
            for name_lc, info in json.load(open(path, encoding="utf-8")).items():
                pid = info.get("player_id")
                if pid is not None:
                    # Title-case the stored lowercase key
                    pid_to_name[int(pid)] = name_lc.title()
        except Exception:
            continue
    return pid_to_name


# ---------------------------------------------------------------------------
# Build calibration table
# ---------------------------------------------------------------------------
def build(asof_date_filter: Optional[str] = None) -> pd.DataFrame:
    """Build per-player calibration table.

    Parameters
    ----------
    asof_date_filter : str | None
        If provided (ISO date string), only emit rows for that asof_date.
        Primarily used in tests. None => emit one row per (player, stat, game_date)
        which gives a time-series of shifts.
    """
    # ------------------------------------------------------------------
    # 1. Load OOF residuals
    # ------------------------------------------------------------------
    if not _OOF.exists():
        log.error("pregame_oof.parquet not found at %s", _OOF)
        sys.exit(1)

    log.info("Loading OOF: %s", _OOF)
    oof = pd.read_parquet(_OOF)

    required = {"player_id", "stat", "oof_pred", "actual", "game_date"}
    missing = required - set(oof.columns)
    if missing:
        log.error("OOF missing columns: %s", missing)
        sys.exit(1)

    oof = oof[oof["stat"].isin(STATS)].copy()
    oof["game_date"] = pd.to_datetime(oof["game_date"])
    oof = oof.sort_values(["player_id", "stat", "game_date"]).reset_index(drop=True)
    oof["residual"] = oof["actual"] - oof["oof_pred"]
    residual_source = "oof"
    log.info("OOF rows after stat filter: %d", len(oof))

    # ------------------------------------------------------------------
    # 2. Build player name map
    # ------------------------------------------------------------------
    pid_to_name = _build_pid_to_name()
    log.info("Player name map: %d entries", len(pid_to_name))

    # ------------------------------------------------------------------
    # 3. Compute rolling bias per (player_id, stat)
    # ------------------------------------------------------------------
    # For each row i, the window is the last WINDOW games STRICTLY BEFORE game_date[i].
    # We do this by groupby + expanding rolling on sorted data.
    #
    # Strategy: for each (player_id, stat) group sorted by date,
    # compute rolling(WINDOW, min_periods=MIN_PERIODS) on residuals.
    # Shift(1) ensures strict < asof_date (we use the current row's date as asof_date,
    # rolling is computed on residuals up to but not including the current row via shift).

    records = []

    for (player_id, stat), grp in oof.groupby(["player_id", "stat"], sort=False):
        grp = grp.sort_values("game_date").reset_index(drop=True)
        res = grp["residual"].values
        dates = grp["game_date"].values

        n = len(res)
        # For position i, window = res[max(0, i-WINDOW) : i]  (strict < current)
        for i in range(1, n):
            start = max(0, i - WINDOW)
            window_res = res[start:i]
            n_valid = np.sum(~np.isnan(window_res))
            if n_valid < MIN_PERIODS:
                continue

            window_clean = window_res[~np.isnan(window_res)]
            bias_l20 = float(np.mean(window_clean))
            sigma_resid = float(np.std(window_clean, ddof=1)) if len(window_clean) > 1 else 0.0
            bias_z_l20 = bias_l20 / (sigma_resid + 1e-6)
            shrink = n_valid / (n_valid + JS_K)
            bias_shift_applied = MULTIPLIER * shrink * bias_l20

            asof_str = str(pd.Timestamp(dates[i]).date())

            records.append({
                "player_id": int(player_id),
                "player_name": pid_to_name.get(int(player_id), f"pid_{player_id}"),
                "asof_date": asof_str,
                "stat": stat,
                "n_prior_games": int(n_valid),
                "bias_l20": round(bias_l20, 6),
                "bias_z_l20": round(bias_z_l20, 6),
                "sigma_resid": round(sigma_resid, 6),
                "bias_shift_applied": round(bias_shift_applied, 6),
                "residual_source": residual_source,
                "build_ts": datetime.now(timezone.utc).isoformat(),
            })

    df = pd.DataFrame(records)
    log.info("Raw calibration rows: %d", len(df))

    if asof_date_filter:
        df = df[df["asof_date"] == asof_date_filter].copy()
        log.info("After asof filter (%s): %d rows", asof_date_filter, len(df))

    if df.empty:
        log.warning("No calibration rows produced.")
        return df

    # ------------------------------------------------------------------
    # 4. Deduplicate: keep latest asof_date per (player_id, stat)
    #    for the "current" calibration table (useful for inference).
    #    We keep the full time-series in the parquet but also log stats.
    # ------------------------------------------------------------------
    n_players = df["player_id"].nunique()
    n_player_stats = df.groupby(["player_id", "stat"]).ngroups
    log.info(
        "Coverage: %d rows | %d unique players | %d player-stat pairs | source=%s",
        len(df), n_players, n_player_stats, residual_source,
    )

    # ------------------------------------------------------------------
    # 5. Write parquet
    # ------------------------------------------------------------------
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_OUT, index=False)
    log.info("Written: %s  (%d rows)", _OUT, len(df))

    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    df = build()
    if df.empty:
        print("RESULT: 0 rows — check logs")
        sys.exit(1)

    print("\n=== INT-69 Build Summary ===")
    print(f"Total rows     : {len(df):,}")
    print(f"Players        : {df['player_id'].nunique()}")
    print(f"Player-stats   : {df.groupby(['player_id','stat']).ngroups}")
    print(f"Residual source: {df['residual_source'].iloc[0]}")
    print(f"Date range     : {df['asof_date'].min()} -> {df['asof_date'].max()}")
    print("\nPer-stat mean bias_shift_applied:")
    print(df.groupby("stat")["bias_shift_applied"].describe()[["count","mean","std","min","max"]].round(4).to_string())
