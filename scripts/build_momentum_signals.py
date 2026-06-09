"""
INT-81: Player Momentum Signals
================================
Per (player_id, asof_date, stat): l3 vs l20 z-scored momentum with bucket labels.

Reads:  data/nba/gamelog_full_<pid>_<season>.json
Writes: data/intelligence/momentum_signals.parquet
        vault/Intelligence/INT-81_Momentum_Signals.md  (stub, full eval in eval script)

Usage:
    python scripts/build_momentum_signals.py [--seasons 2023-24 2024-25 2025-26]
"""
from __future__ import annotations

import glob
import io
import json
import sys
import warnings
from datetime import date
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
NBA_DIR = ROOT / "data" / "nba"
OUT_PARQUET = ROOT / "data" / "intelligence" / "momentum_signals.parquet"
VAULT_MD = ROOT / "vault" / "Intelligence" / "INT-81_Momentum_Signals.md"

OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
VAULT_MD.parent.mkdir(parents=True, exist_ok=True)

TODAY = date.today().isoformat()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
STAT_FIELD_MAP = {
    "pts": "pts", "reb": "reb", "ast": "ast",
    "fg3m": "fg3m", "stl": "stl", "blk": "blk", "tov": "tov",
}
MIN_PRIOR_L3 = 3      # skip if n_prior_games < 3
MIN_PRIOR_L20_MEAN = 5  # NaN baseline if fewer than 5 prior games
L3_N = 3
L20_N = 20
STD_FLOOR = 0.5
Z_CLIP = 5.0
DEFAULT_SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]


def momentum_bucket(z: float) -> str:
    if z < -2.0:
        return "VERY_COLD"
    elif z < -1.0:
        return "COLD"
    elif z <= 1.0:
        return "NEUTRAL"
    elif z <= 2.0:
        return "WARM"
    else:
        return "VERY_HOT"


def _parse_date(s: str) -> Optional[pd.Timestamp]:
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return pd.Timestamp(s)
        except Exception:
            pass
    return None


def load_gamelogs(seasons: List[str]) -> pd.DataFrame:
    """Load all gamelog_full_<pid>_<season>.json files for requested seasons."""
    records = []
    pattern_tpl = "gamelog_full_*_{season}.json"
    for season in seasons:
        pattern = str(NBA_DIR / pattern_tpl.format(season=season))
        files = glob.glob(pattern)
        for fp in files:
            try:
                with open(fp, encoding="utf-8") as f:
                    rows = json.load(f)
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    records.append({
                        "player_id": int(row.get("player_id", 0)),
                        "game_date": row.get("game_date", ""),
                        "min": float(row.get("min", 0) or 0),
                        "pts": float(row.get("pts", 0) or 0),
                        "reb": float(row.get("reb", 0) or 0),
                        "ast": float(row.get("ast", 0) or 0),
                        "fg3m": float(row.get("fg3m", 0) or 0),
                        "stl": float(row.get("stl", 0) or 0),
                        "blk": float(row.get("blk", 0) or 0),
                        "tov": float(row.get("tov", 0) or 0),
                        "season": season,
                    })
            except Exception as e:
                print(f"  [WARN] Failed to load {fp}: {e}")

    if not records:
        raise RuntimeError("No gamelog files found for requested seasons.")

    df = pd.DataFrame(records)
    df["game_date_parsed"] = pd.to_datetime(df["game_date"], format="%b %d, %Y", errors="coerce")
    bad = df["game_date_parsed"].isna().sum()
    if bad > 0:
        print(f"  [WARN] {bad} rows with unparseable game_date — dropping")
    df = df[df["game_date_parsed"].notna()].copy()
    df["game_date_str"] = df["game_date_parsed"].dt.strftime("%Y-%m-%d")

    # Strict: require MIN >= 1
    df = df[df["min"] >= 1].copy()

    print(f"  Gamelogs loaded: {len(df):,} rows | {df['player_id'].nunique()} players | seasons: {seasons}")
    return df.sort_values(["player_id", "game_date_parsed"]).reset_index(drop=True)


def compute_momentum(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each (player_id, game row), compute l3/l20 momentum using only prior games.
    Uses a vectorized approach per player.
    """
    results = []

    for pid, grp in df.groupby("player_id", sort=False):
        grp = grp.sort_values("game_date_parsed").reset_index(drop=True)
        n_games = len(grp)

        for stat in STATS:
            vals = grp[stat].values
            dates = grp["game_date_str"].values
            seasons = grp["season"].values

            for i in range(n_games):
                n_prior = i  # games before index i
                if n_prior < MIN_PRIOR_L3:
                    continue

                prior_vals = vals[:i]  # strict shift(1) — excludes game i

                l3_vals = prior_vals[-L3_N:]
                l3_actual = float(np.mean(l3_vals)) if len(l3_vals) == L3_N else np.nan

                if np.isnan(l3_actual):
                    continue

                l20_vals = prior_vals[-L20_N:]
                n_l20 = len(l20_vals)
                l20_baseline = float(np.mean(l20_vals)) if n_l20 >= MIN_PRIOR_L20_MEAN else np.nan
                l20_std_raw = float(np.std(l20_vals, ddof=1)) if n_l20 >= 2 else 0.0
                l20_std = max(float(l20_std_raw) if not np.isnan(l20_std_raw) else 0.0, STD_FLOOR)

                if np.isnan(l20_baseline):
                    momentum_z = np.nan
                    bucket = "NEUTRAL"
                else:
                    z = (l3_actual - l20_baseline) / l20_std
                    momentum_z = float(np.clip(z, -Z_CLIP, Z_CLIP))
                    bucket = momentum_bucket(momentum_z)

                asof_date = dates[i]  # the game date = asof for that row
                season = seasons[i]

                results.append({
                    "player_id": int(pid),
                    "asof_date": asof_date,
                    "stat": stat,
                    "l3_actual": round(l3_actual, 6),
                    "l20_baseline": round(l20_baseline, 6) if not np.isnan(l20_baseline) else np.nan,
                    "l20_std": round(l20_std, 6),
                    "momentum_z": round(momentum_z, 6) if not np.isnan(momentum_z) else np.nan,
                    "momentum_bucket": bucket,
                    "n_prior_games": int(n_prior),
                    "season": season,
                })

    out = pd.DataFrame(results)
    out = out.astype({
        "player_id": "int64",
        "n_prior_games": "int32",
    })
    return out


def write_vault_stub(nrows: int, n_players: int, seasons: List[str]) -> None:
    lines = [
        "# INT-81: Player Momentum Signals",
        "",
        "## Status",
        f"Build run: {TODAY}",
        f"Rows written: {nrows:,}",
        f"Players: {n_players}",
        f"Seasons: {', '.join(seasons)}",
        "",
        "## Methodology",
        "- `l3_actual` = mean of last 3 prior games (strict shift(1), MIN>=1)",
        "- `l20_baseline` = mean of last 20 prior games (NaN if <5 prior)",
        "- `l20_std` = std of last 20 prior, floor 0.5",
        "- `momentum_z` = (l3_actual - l20_baseline) / max(l20_std, 0.5), clipped [-5, +5]",
        "- Buckets: VERY_COLD(<-2), COLD(-2,-1), NEUTRAL(-1,+1), WARM(1,2), VERY_HOT(>2)",
        "- TOV: raw z stored; consumer inverts interpretation",
        "",
        "## Output",
        f"- `data/intelligence/momentum_signals.parquet` — partitioned by season",
        "",
        "## Eval",
        "Run `python scripts/eval_momentum_signals.py` for CLV gate check.",
        "",
        "---",
        f"*Built {TODAY} by INT-81: `scripts/build_momentum_signals.py`*",
    ]
    VAULT_MD.write_text("\n".join(lines), encoding="utf-8")


def main(seasons: Optional[List[str]] = None) -> None:
    if seasons is None:
        seasons = DEFAULT_SEASONS

    print(f"[INT-81] Loading gamelogs for seasons: {seasons}")
    df = load_gamelogs(seasons)

    print(f"[INT-81] Computing momentum signals...")
    signals = compute_momentum(df)

    print(f"[INT-81] Signals computed: {len(signals):,} rows")

    # Drop rows where momentum_z is NaN (l20_baseline was NaN)
    before = len(signals)
    signals = signals.dropna(subset=["momentum_z"]).copy()
    print(f"[INT-81] After dropping NaN momentum_z: {len(signals):,} rows (dropped {before - len(signals):,})")

    # Save parquet partitioned by season
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    signals.to_parquet(str(OUT_PARQUET), index=False)
    print(f"[INT-81] Saved -> {OUT_PARQUET}")

    # Bucket distribution
    print("\nBucket distribution:")
    for stat in STATS:
        stat_df = signals[signals["stat"] == stat]
        counts = stat_df["momentum_bucket"].value_counts()
        print(f"  {stat:5s}: " + " | ".join(f"{b}={counts.get(b,0)}" for b in
              ["VERY_COLD","COLD","NEUTRAL","WARM","VERY_HOT"]))

    write_vault_stub(len(signals), signals["player_id"].nunique(), seasons)
    print(f"[INT-81] Vault stub -> {VAULT_MD}")
    print(f"[INT-81] Done. Run eval_momentum_signals.py for CLV gate check.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="INT-81: Build player momentum signals")
    parser.add_argument(
        "--seasons", nargs="+", default=DEFAULT_SEASONS,
        help="Seasons to include (e.g. 2024-25 2025-26)"
    )
    args = parser.parse_args()
    main(seasons=args.seasons)
