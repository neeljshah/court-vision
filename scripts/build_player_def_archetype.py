"""build_player_def_archetype.py — INT-138 per-player rolling performance vs defensive archetype.

Builds a sidecar parquet keyed (player_id, game_date) with 24 features:
  For 4 stats (pts, reb, ast, fg3m) × 3 archetypes (HELP_DEF, PACE_CONTROL, SWITCH_HEAVY):
    - player_{stat}_vs_{arch}_diff  : rolling mean of stat vs teams in that archetype
                                       minus player career overall mean (both shifted-1, no leakage)
    - player_n_games_vs_{arch}_prior : count of prior games vs that archetype

ARCHETYPE SLUGIFICATION RULE (documented):
  Raw tag → slug (pipe-split all_tags field):
    "HELP DEFENSE"    → "HELP_DEF"       (trim " ENSE" → 8-char canonical)
    "PACE CONTROL"    → "PACE_CONTROL"
    "SWITCH HEAVY"    → "SWITCH_HEAVY"
  Top-3 by all_tags population: HELP_DEF (17), PACE_CONTROL (15), SWITCH_HEAVY (12)
  These 3 were confirmed by Opus pre-flight and verified in Step 1 below.

NOTE on static archetype labels:
  defensive_schemes.parquet is a static snapshot (no season column). Archetype labels
  are slow-moving team identity signals. We accept mild backward-projection (current
  label applied to all historical games for that team). Documented limitation.

Usage:
    python scripts/build_player_def_archetype.py
    python scripts/build_player_def_archetype.py --out data/intelligence/player_def_archetype_sidecar.parquet
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import warnings
from collections import defaultdict
from typing import Dict, List, Set, Tuple

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TARGET_ARCHETYPES = ["HELP_DEF", "PACE_CONTROL", "SWITCH_HEAVY"]
TARGET_STATS = ["pts", "reb", "ast", "fg3m"]

ARCH_SLUG_MAP: Dict[str, str] = {
    "HELP DEFENSE": "HELP_DEF",
    "PACE CONTROL": "PACE_CONTROL",
    "SWITCH HEAVY": "SWITCH_HEAVY",
    "DROP COVERAGE": "DROP_COVERAGE",
    "ISO FORCE": "ISO_FORCE",
    "ACTIVE CLOSEOUTS": "ACTIVE_CLOSEOUTS",
    "PAINT-FIRST DEFENSE": "PAINT_FIRST_DEFENSE",
    "PERIMETER DENIAL": "PERIMETER_DENIAL",
    "BALANCED": "BALANCED",
}

DEFAULT_OUT = os.path.join(PROJECT_DIR, "data", "intelligence",
                           "player_def_archetype_sidecar.parquet")


# ---------------------------------------------------------------------------
# Step 1: Build team -> archetype set mapping
# ---------------------------------------------------------------------------
def build_team_arch_map(schemes_path: str) -> Dict[str, Set[str]]:
    """Return dict: team_abbrev -> set of slugified archetypes."""
    df = pd.read_parquet(schemes_path)
    team_map: Dict[str, Set[str]] = {}
    for _, row in df.iterrows():
        team = str(row["team"]).strip()
        raw_tags = str(row["all_tags"]).strip()
        slugs: Set[str] = set()
        for raw in raw_tags.split("|"):
            raw = raw.strip()
            slug = ARCH_SLUG_MAP.get(raw)
            if slug:
                slugs.add(slug)
        team_map[team] = slugs

    # Verify top-3 population
    from collections import Counter
    counts: Counter = Counter()
    for slugs in team_map.values():
        counts.update(slugs)
    print(f"[Step 1] Archetype population (all tags):")
    for arch, cnt in counts.most_common():
        marker = " <-- TARGET" if arch in TARGET_ARCHETYPES else ""
        print(f"  {cnt:2d}  {arch}{marker}")

    # Kill switch: confirm top-3
    top3 = [a for a, _ in counts.most_common(3)]
    for expected in TARGET_ARCHETYPES:
        if expected not in [a for a, _ in counts.most_common()]:
            raise RuntimeError(f"KILL SWITCH: Expected archetype {expected!r} missing from data")

    return team_map


# ---------------------------------------------------------------------------
# Step 2: Load and concatenate all gamelog_full_*.json
# ---------------------------------------------------------------------------
def load_gamelogs() -> pd.DataFrame:
    pattern = os.path.join(PROJECT_DIR, "data", "nba", "gamelog_full_*.json")
    files = glob.glob(pattern)
    print(f"[Step 2] Loading {len(files)} gamelog_full files...")

    records = []
    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            records.extend(data)
        except Exception as e:
            print(f"  WARN: {fpath} -> {e}")

    df = pd.DataFrame(records)
    print(f"  Total raw rows: {len(df)}")

    # Normalize columns
    df.columns = [c.lower() for c in df.columns]

    # Parse game_date
    df["game_date"] = pd.to_datetime(df["game_date"], infer_datetime_format=True, errors="coerce")
    df = df.dropna(subset=["game_date"])
    df["game_date"] = df["game_date"].dt.strftime("%Y-%m-%d")

    # Parse opponent from matchup: "TEAM vs. OPP" or "TEAM @ OPP"
    import re
    def parse_opp(matchup: str) -> str:
        m = re.match(r"(\w+)\s+(?:vs\.|@)\s+(\w+)", str(matchup))
        return m.group(2) if m else ""

    df["opp_team"] = df["matchup"].apply(parse_opp)

    # Ensure required stat columns exist
    for col in TARGET_STATS + ["player_id"]:
        if col not in df.columns:
            raise RuntimeError(f"KILL SWITCH: Required column {col!r} missing from gamelogs")

    # Keep only needed columns
    keep_cols = ["player_id", "game_date", "opp_team"] + TARGET_STATS
    df = df[keep_cols].copy()

    # Cast types
    df["player_id"] = pd.to_numeric(df["player_id"], errors="coerce").astype("Int64")
    for s in TARGET_STATS:
        df[s] = pd.to_numeric(df[s], errors="coerce")

    df = df.dropna(subset=["player_id", "game_date"])
    df = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)
    print(f"  After clean: {len(df)} rows, {df['player_id'].nunique()} players")

    return df


# ---------------------------------------------------------------------------
# Step 3: Attach archetype flags per game row
# ---------------------------------------------------------------------------
def attach_arch_flags(df: pd.DataFrame, team_map: Dict[str, Set[str]]) -> pd.DataFrame:
    """Add boolean columns for each target archetype based on opp_team."""
    unmapped = set()
    for arch in TARGET_ARCHETYPES:
        col = f"opp_is_{arch}"
        df[col] = df["opp_team"].apply(
            lambda t: arch in team_map.get(t, set())
        )

    # Diagnose unmapped teams
    all_teams = set(df["opp_team"].unique())
    mapped_teams = set(team_map.keys())
    unmapped = all_teams - mapped_teams - {""}
    if unmapped:
        print(f"  [Step 3] WARNING: {len(unmapped)} opp teams not in defensive_schemes: {sorted(unmapped)[:20]}")

    cov = {arch: df[f"opp_is_{arch}"].mean() for arch in TARGET_ARCHETYPES}
    for arch, c in cov.items():
        print(f"  [Step 3] Game coverage for {arch}: {c:.3f} ({c*len(df):.0f}/{len(df)} games)")

    return df


# ---------------------------------------------------------------------------
# Step 4: Compute rolling features per (player_id, archetype)
# ---------------------------------------------------------------------------
def compute_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each player, for each game (sorted by date):
      1. overall_mean_to_date: expanding mean of stat (all prior games, shifted-1)
      2. arch_mean_to_date: expanding mean of stat where opp has this archetype (shifted-1)
      3. diff = arch_mean - overall_mean
      4. n_prior = count of prior games vs this archetype

    Returns sidecar df keyed (player_id, game_date).
    """
    print("[Step 4] Computing rolling features...")

    # Output containers
    out_rows = []

    players = df["player_id"].unique()
    n_players = len(players)
    print(f"  Processing {n_players} players...")

    for i, pid in enumerate(players):
        if i % 500 == 0:
            print(f"  ... player {i}/{n_players}", flush=True)

        pdata = df[df["player_id"] == pid].sort_values("game_date").reset_index(drop=True)
        n_games = len(pdata)

        # Pre-compute stat arrays
        stat_arrays = {s: pdata[s].values.astype(float) for s in TARGET_STATS}
        arch_flags = {arch: pdata[f"opp_is_{arch}"].values.astype(bool)
                      for arch in TARGET_ARCHETYPES}
        dates = pdata["game_date"].values

        for game_idx in range(n_games):
            row: dict = {
                "player_id": int(pid),
                "game_date": str(dates[game_idx]),
            }

            # Prior games only (shifted-1)
            if game_idx == 0:
                # No prior games — all NaN
                for stat in TARGET_STATS:
                    for arch in TARGET_ARCHETYPES:
                        row[f"player_{stat}_vs_{arch}_diff"] = np.nan
                        row[f"player_n_games_vs_{arch}_prior"] = 0
                out_rows.append(row)
                continue

            prior_slice = slice(0, game_idx)  # all games before current

            # Overall mean per stat (all prior games)
            overall_means = {
                s: float(np.nanmean(stat_arrays[s][prior_slice]))
                for s in TARGET_STATS
            }

            for arch in TARGET_ARCHETYPES:
                arch_flag_prior = arch_flags[arch][prior_slice]
                n_prior = int(arch_flag_prior.sum())
                row[f"player_n_games_vs_{arch}_prior"] = n_prior

                for stat in TARGET_STATS:
                    if n_prior == 0:
                        row[f"player_{stat}_vs_{arch}_diff"] = np.nan
                    else:
                        vals = stat_arrays[stat][prior_slice]
                        arch_vals = vals[arch_flag_prior]
                        arch_mean = float(np.nanmean(arch_vals))
                        diff = arch_mean - overall_means[stat]
                        row[f"player_{stat}_vs_{arch}_diff"] = diff

            out_rows.append(row)

    out_df = pd.DataFrame(out_rows)
    print(f"  Output rows: {len(out_df)}, cols: {len(out_df.columns)}")
    return out_df


# ---------------------------------------------------------------------------
# Shuffled null variant (for G4)
# ---------------------------------------------------------------------------
def build_null_sidecar(df: pd.DataFrame, team_map: Dict[str, Set[str]],
                       seed: int = 42) -> pd.DataFrame:
    """Shuffle team->arch_set mapping; recompute sidecar. Preserves arch distribution."""
    rng = np.random.default_rng(seed)
    teams = list(team_map.keys())
    arch_sets = [team_map[t] for t in teams]
    shuffled_sets = rng.permutation(arch_sets).tolist()
    null_map = {t: set(s) for t, s in zip(teams, shuffled_sets)}
    print(f"[G4] Building null sidecar (shuffled arch map, seed={seed})...")
    df_null = attach_arch_flags(df.drop(columns=[c for c in df.columns if c.startswith("opp_is_")]),
                                null_map)
    return compute_rolling_features(df_null)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="Output parquet path")
    ap.add_argument("--null", action="store_true",
                    help="Build null (shuffled) sidecar instead")
    ap.add_argument("--null-seed", type=int, default=42)
    args = ap.parse_args()

    schemes_path = os.path.join(PROJECT_DIR, "data", "intelligence", "defensive_schemes.parquet")
    if not os.path.exists(schemes_path):
        raise FileNotFoundError(f"KILL SWITCH: defensive_schemes.parquet not found at {schemes_path}")

    # Step 1
    team_map = build_team_arch_map(schemes_path)

    # Step 2
    df = load_gamelogs()

    if args.null:
        out = build_null_sidecar(df, team_map, seed=args.null_seed)
        null_path = args.out.replace(".parquet", "_null.parquet")
        out.to_parquet(null_path, index=False)
        print(f"\nWrote null sidecar: {null_path}")
        return

    # Step 3
    df = attach_arch_flags(df, team_map)

    # Step 4
    sidecar = compute_rolling_features(df)

    # Verify 24 feature columns
    feat_cols = [c for c in sidecar.columns if c not in ("player_id", "game_date")]
    print(f"\nFeature cols ({len(feat_cols)}): {feat_cols}")
    expected = (len(TARGET_STATS) * len(TARGET_ARCHETYPES) * 2)
    if len(feat_cols) != expected:
        print(f"  WARNING: expected {expected} feature cols, got {len(feat_cols)}")

    # Save
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    sidecar.to_parquet(args.out, index=False)
    print(f"\nWrote sidecar: {args.out}")
    print(sidecar.describe().to_string())


if __name__ == "__main__":
    main()
