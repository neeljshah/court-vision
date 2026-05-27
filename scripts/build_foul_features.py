"""
build_foul_features.py
----------------------
Build leak-free rolling foul-rate features from data/player_pf.parquet.

Features produced (all shift(1)-safe, no future leakage):
  pf_per_36_l5          – rolling(5) mean of per-36-min PF rate
  pf_per_36_l10         – rolling(10) mean of per-36-min PF rate
  foul_trouble_rate_l10 – rolling(10) fraction of games with pf >= 4
  last_game_pf          – previous game raw PF count
  min_l5                – rolling(5) mean minutes

Output: data/cache/foul_features.parquet
Keys:   player_id, game_id, game_date (+ team_abbreviation)
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
SRC  = ROOT / "data" / "player_pf.parquet"
DST  = ROOT / "data" / "cache" / "foul_features.parquet"


def build(src: Path = SRC, dst: Path = DST) -> pd.DataFrame:
    # ── Load ───────────────────────────────────────────────────────────────────
    df = pd.read_parquet(src)
    df["game_date"] = pd.to_datetime(df["game_date"])

    # Sort chronologically per player (stable sort preserves game_id ordering
    # within same date if ties exist)
    df = df.sort_values(["player_id", "game_date"], kind="stable").reset_index(drop=True)

    # ── Per-36 rate (NaN when min == 0 to avoid div-by-zero) ──────────────────
    df["pf_per_36"] = np.where(
        df["min"] > 0,
        df["pf"] / df["min"] * 36.0,
        np.nan,
    )

    # ── Rolling helpers (grouped by player) ───────────────────────────────────
    # shift(1) first so no current-game info leaks in.
    grp = df.groupby("player_id", sort=False)

    # shift(1) series
    pf_s1       = grp["pf"].shift(1)
    per36_s1    = grp["pf_per_36"].shift(1)
    min_s1      = grp["min"].shift(1)
    foul_flag_s1 = (grp["pf"].shift(1) >= 4).astype(float)

    # Rolling on the already-shifted series
    df["pf_per_36_l5"]          = per36_s1.groupby(df["player_id"]).transform(
                                      lambda s: s.rolling(5, min_periods=1).mean()
                                  )
    df["pf_per_36_l10"]         = per36_s1.groupby(df["player_id"]).transform(
                                      lambda s: s.rolling(10, min_periods=1).mean()
                                  )
    df["foul_trouble_rate_l10"] = foul_flag_s1.groupby(df["player_id"]).transform(
                                      lambda s: s.rolling(10, min_periods=1).mean()
                                  )
    df["last_game_pf"]          = pf_s1.values
    df["min_l5"]                = min_s1.groupby(df["player_id"]).transform(
                                      lambda s: s.rolling(5, min_periods=1).mean()
                                  )

    # ── Select output columns ─────────────────────────────────────────────────
    out_cols = [
        "player_id", "game_id", "game_date", "team_abbreviation",
        "pf_per_36_l5", "pf_per_36_l10",
        "foul_trouble_rate_l10", "last_game_pf", "min_l5",
    ]
    out = df[out_cols].copy()

    # ── Write ──────────────────────────────────────────────────────────────────
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(dst, index=False)

    return out


def report(out: pd.DataFrame) -> None:
    feature_cols = [
        "pf_per_36_l5", "pf_per_36_l10",
        "foul_trouble_rate_l10", "last_game_pf", "min_l5",
    ]
    print(f"\n=== foul_features.parquet ===")
    print(f"Rows: {len(out):,}")
    print(f"\nNull rates:")
    for col in feature_cols:
        n = out[col].isna().sum()
        pct = n / len(out) * 100
        print(f"  {col:<30} {n:>5} ({pct:.1f}%)")

    # Sample foul-prone players: Draymond Green=203110, Steven Adams=203500
    print("\nSample rows — foul-prone players (non-zero min games):")
    for pid, name in [(203110, "Draymond Green"), (203500, "Steven Adams")]:
        rows = out[(out["player_id"] == pid)].dropna(subset=["pf_per_36_l5"])
        if len(rows) == 0:
            # Fallback: any row for this player
            rows = out[out["player_id"] == pid]
        if len(rows) > 0:
            r = rows.iloc[-1]
            print(f"\n  {name} (id={pid}):")
            for col in ["game_date", "team_abbreviation"] + feature_cols:
                print(f"    {col:<30} {r[col]}")
        else:
            print(f"\n  {name}: not found in dataset")


if __name__ == "__main__":
    out = build()
    report(out)
    print(f"\nWritten to: {DST}")
