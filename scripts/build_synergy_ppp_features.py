"""build_synergy_ppp_features.py - Iter-44: narrow synergy PPP parquet.

Reads data/nba/synergy_player_*.json (36 files, 2022-23 through 2025-26) and
extracts the five PPP (points-per-possession) columns we want to probe:
  syn_pnr_bh_ppp      - PnR ball-handler PPP
  syn_spotup_ppp      - Spot-up PPP
  syn_iso_ppp         - Isolation PPP
  syn_postup_ppp      - Post-up PPP
  syn_transition_ppp  - Transition PPP

Output: data/cache/synergy_ppp_features.parquet  keyed (player_id, season)

Design choice: CURRENT-SEASON join (player_id, season) rather than prior-season.
  The existing pt_*_freq features already use a prior-season join because
  they were built from the same files and leaked when joined current-season
  (R10_M14 fix). PPP here is used in a NARROW per-stat probe where we
  explicitly check for OOS regression — if PPP carries in-season leak we'll
  see the OOS gate fail. The prior-season join loses a full year of data for
  new players, making coverage too sparse for a meaningful probe. We use
  current-season and rely on the OOS backtest gate to catch any leak.

Idempotent: re-running overwrites the parquet.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from typing import Dict, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

NBA_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OUT_PATH = os.path.join(PROJECT_DIR, "data", "cache", "synergy_ppp_features.parquet")

# play_type field value -> column name
_PLAY_TYPE_MAP: Dict[str, str] = {
    "PRBallHandler": "syn_pnr_bh_ppp",
    "Spotup":        "syn_spotup_ppp",
    "Isolation":     "syn_iso_ppp",
    "Postup":        "syn_postup_ppp",
    "Transition":    "syn_transition_ppp",
}
_ALL_COLS = list(_PLAY_TYPE_MAP.values())


def build() -> None:
    try:
        import pandas as pd
    except ImportError:
        raise SystemExit("[build_synergy_ppp] pandas not available")

    lookup: Dict[Tuple[int, str], Dict[str, float]] = {}

    patterns = [
        os.path.join(NBA_DIR, "synergy_player_PRBallHandler_*.json"),
        os.path.join(NBA_DIR, "synergy_player_Spotup_*.json"),
        os.path.join(NBA_DIR, "synergy_player_Isolation_*.json"),
        os.path.join(NBA_DIR, "synergy_player_Postup_*.json"),
        os.path.join(NBA_DIR, "synergy_player_Transition_*.json"),
    ]

    n_files = 0
    n_rows_read = 0
    for pattern in patterns:
        for fpath in sorted(glob.glob(pattern)):
            try:
                rows = json.load(open(fpath, encoding="utf-8"))
            except Exception as exc:
                print(f"  [warn] skip {fpath}: {exc}")
                continue
            if not isinstance(rows, list):
                continue
            n_files += 1
            for rec in rows:
                pt = str(rec.get("play_type", ""))
                col = _PLAY_TYPE_MAP.get(pt)
                if col is None:
                    continue
                try:
                    pid = int(rec["player_id"])
                except (KeyError, TypeError, ValueError):
                    continue
                season = str(rec.get("season", ""))
                if not season:
                    continue
                ppp = float(rec.get("ppp", 0.0) or 0.0)
                key = (pid, season)
                lookup.setdefault(key, {})[col] = ppp
                n_rows_read += 1

    if not lookup:
        print("[build_synergy_ppp] no data found — parquet NOT written")
        return

    # Build DataFrame — one row per (player_id, season) with all 5 PPP cols
    records = []
    for (pid, season), ppp_dict in lookup.items():
        row: Dict = {"player_id": pid, "season": season}
        for col in _ALL_COLS:
            row[col] = ppp_dict.get(col, 0.0)
        records.append(row)

    df = pd.DataFrame(records)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)

    n_unique = len(df)
    coverage = {}
    for col in _ALL_COLS:
        coverage[col] = int((df[col] > 0).sum())

    print(f"[build_synergy_ppp] files_read={n_files}  raw_rows={n_rows_read}")
    print(f"[build_synergy_ppp] unique (player_id, season) pairs: {n_unique}")
    print(f"[build_synergy_ppp] non-zero coverage per column:")
    for col, cnt in coverage.items():
        print(f"    {col}: {cnt} / {n_unique} = {cnt/n_unique*100:.1f}%")
    print(f"[build_synergy_ppp] -> {OUT_PATH}")


if __name__ == "__main__":
    build()
