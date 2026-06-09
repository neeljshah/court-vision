#!/usr/bin/env python3
"""build_pace_adjusted_cv.py -- INT-31: Pace-Adjusted CV Intelligence

Different teams play at very different paces (BOS ~96 vs MIA ~104 poss/game in 2025-26).
Raw CV volume features systematically favor players on fast-paced teams.

This script normalizes per-game CV volume accumulations to per-100-team-possessions,
enabling fair cross-team player comparisons.

Volume-dependent features adjusted:
    cvb_passes_per100 (frames) -> adj_passes_per_100poss
    cvb_dribbles_per100 (frames) -> adj_dribbles_per_100poss
    cvb_fatigue_score (cumulative distance) -> adj_fatigue_per_100poss
    minutes_proxy -> adj_minutes_per_100poss

Style/rate features NOT adjusted (already dimensionless):
    cvb_paint_time_pct, cvb_near_basket_pct, cvb_avg_dist_to_basket,
    cvb_avg_defender_dist, cvb_avg_spacing, cvb_contested_shot_pct,
    cvb_velocity_q4_dropoff, cvb_avg_velocity, etc.

Math:
    raw_volume_per_game * (100 / team_pace_per_game) = adj_volume_per_100_poss
    where team_pace = possessions per game (one team's half of total possessions)

Outputs:
    data/intelligence/pace_adjusted_cv.parquet
    data/intelligence/pace_adjusted_rankings.json
    vault/Intelligence/Pace_Adjusted_Atlas.md

Usage:
    python scripts/build_pace_adjusted_cv.py
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
INTEL = DATA / "intelligence"
VAULT = ROOT / "vault" / "Intelligence"

OUT_PARQUET = INTEL / "pace_adjusted_cv.parquet"
OUT_JSON    = INTEL / "pace_adjusted_rankings.json"
OUT_ATLAS   = VAULT / "Pace_Adjusted_Atlas.md"

TOP_N = 25  # ranks per metric
MIN_GAMES = 2  # min CV games to include player

# Volume features: (raw_col, raw_label, adj_label)
# The per100 cols are per 100 FRAMES (not possessions); we convert to raw total
# then normalize to per-100-team-possessions.
VOLUME_FEATURES = [
    ("cvb_passes_per100",   "raw_passes_per_game",   "adj_passes_per_100poss"),
    ("cvb_dribbles_per100", "raw_dribbles_per_game", "adj_dribbles_per_100poss"),
    ("cvb_fatigue_score",   "raw_fatigue_per_game",  "adj_fatigue_per_100poss"),
]

# Style/rate features -- already dimensionless, no pace adjustment needed
STYLE_FEATURES = [
    "cvb_paint_time_pct",
    "cvb_near_basket_pct",
    "cvb_avg_dist_to_basket",
    "cvb_avg_defender_dist",
    "cvb_avg_spacing",
    "cvb_avg_velocity",
    "cvb_contested_shot_pct",
    "cvb_velocity_q4_dropoff",
    "cvb_off_ball_dist",
    "cvb_paint_pressure_own",
    "cvb_paint_pressure_opp",
]


# ---------------------------------------------------------------------------
# Step 1 -- Per-team pace lookup from NBA API + team_advanced_stats backup
# ---------------------------------------------------------------------------

def _fetch_pace_from_api(seasons: list[str]) -> pd.DataFrame:
    """Fetch pace per team per season from NBA API.
    Returns DataFrame with (season, team_abbrev, pace) columns.
    """
    try:
        from nba_api.stats.endpoints import leaguedashteamstats
        from nba_api.stats.static import teams as nba_teams
    except ImportError:
        print("  [WARN] nba_api not available; falling back to team_advanced_stats")
        return pd.DataFrame()

    team_map = {t["id"]: t["abbreviation"] for t in nba_teams.get_teams()}
    rows = []
    for season in seasons:
        try:
            resp = leaguedashteamstats.LeagueDashTeamStats(
                season=season,
                per_mode_detailed="PerGame",
                measure_type_detailed_defense="Advanced",
                timeout=30,
            )
            df = resp.get_data_frames()[0]
            df["team_abbrev"] = df["TEAM_ID"].map(team_map)
            df["season"] = season
            rows.append(df[["season", "team_abbrev", "PACE", "POSS", "GP"]].rename(
                columns={"PACE": "team_pace", "POSS": "team_poss", "GP": "team_gp"}
            ))
            print(f"  [API] {season}: {len(df)} teams, "
                  f"pace {df['PACE'].min():.1f}-{df['PACE'].max():.1f}")
        except Exception as exc:
            print(f"  [WARN] {season} API fetch failed: {exc}")
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _load_pace_from_parquet(seasons: list[str]) -> pd.DataFrame:
    """Fallback: derive team pace from team_advanced_stats.parquet.
    This file only covers through 2024-25.
    """
    path = DATA / "team_advanced_stats.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["season"] = df["game_id"].astype(str).str[3:5].astype(int).apply(
        lambda x: f"20{x:02d}-{(x+1):02d}"
    )
    df = df[df["season"].isin(seasons)]
    agg = df.groupby(["season", "team_tricode"])["pace"].mean().reset_index()
    agg.columns = ["season", "team_abbrev", "team_pace"]
    agg["team_poss"] = np.nan
    agg["team_gp"] = np.nan
    return agg


def build_pace_lookup(seasons: list[str]) -> dict[tuple[str, str], float]:
    """Return {(season, team_abbrev): pace_per_game} mapping."""
    print("Step 1 -- Building team pace lookup...")
    api_df = _fetch_pace_from_api(seasons)
    fallback_df = _load_pace_from_parquet(seasons)

    if api_df.empty and fallback_df.empty:
        raise RuntimeError("No pace data available from API or parquet")

    # Prefer API data; supplement with parquet for any missing (season, team) pairs
    if not api_df.empty and not fallback_df.empty:
        api_keys = set(zip(api_df["season"], api_df["team_abbrev"]))
        fb = fallback_df[~fallback_df.apply(
            lambda r: (r["season"], r["team_abbrev"]) in api_keys, axis=1
        )]
        combined = pd.concat([api_df, fb], ignore_index=True)
    elif not api_df.empty:
        combined = api_df
    else:
        combined = fallback_df

    lookup = {
        (row["season"], row["team_abbrev"]): float(row["team_pace"])
        for _, row in combined.iterrows()
        if pd.notna(row["team_pace"])
    }
    print(f"  Pace lookup: {len(lookup)} (season, team) pairs across {len(seasons)} seasons")

    # Save for atlas reporting
    build_pace_lookup._raw_df = combined  # type: ignore[attr-defined]
    return lookup


# ---------------------------------------------------------------------------
# Step 2 -- Per-player team mapping from player_pf
# ---------------------------------------------------------------------------

def build_player_team_map() -> dict[tuple[int, str], str]:
    """Return {(nba_player_id, season): team_abbrev} using mode team per season.

    Uses player_pf which has player_id (NBA personId), game_date, team_abbreviation.
    """
    print("Step 2 -- Building player-team mapping...")
    path = DATA / "player_pf.parquet"
    if not path.exists():
        print("  [WARN] player_pf.parquet missing; team lookup will be limited")
        return {}
    df = pd.read_parquet(path)
    df["season"] = pd.to_datetime(df["game_date"]).apply(
        lambda d: f"{d.year}-{str(d.year+1)[2:]}" if d.month >= 10
        else f"{d.year-1}-{str(d.year)[2:]}"
    )
    grp = (
        df.groupby(["player_id", "season"])["team_abbreviation"]
        .agg(lambda s: s.mode().iat[0] if not s.mode().empty else None)
        .reset_index()
    )
    lookup = {
        (int(row["player_id"]), row["season"]): row["team_abbreviation"]
        for _, row in grp.iterrows()
        if pd.notna(row["team_abbreviation"])
    }
    print(f"  Player-team map: {len(lookup)} (player_id, season) pairs")
    return lookup


# ---------------------------------------------------------------------------
# Step 3 -- Load CV data and apply pace adjustment
# ---------------------------------------------------------------------------

def _season_from_game_id(gid: str) -> str:
    yr = int(str(gid)[3:5])
    return f"20{yr:02d}-{(yr+1):02d}"


def load_and_adjust(
    pace_lookup: dict[tuple[str, str], float],
    player_team_map: dict[tuple[int, str], str],
) -> pd.DataFrame:
    """Load player_cv_per_game.parquet, attach pace, compute adjusted features.

    Returns per-game adjusted DataFrame.
    """
    print("Step 3 -- Applying pace adjustment to CV data...")

    cv_pg = pd.read_parquet(DATA / "player_cv_per_game.parquet")
    cv_pg["season"] = cv_pg["game_id"].apply(_season_from_game_id)

    # Attach real team via nba_player_id + season
    def lookup_team(row):
        pid = row["nba_player_id"]
        if pd.isna(pid):
            return None
        return player_team_map.get((int(pid), row["season"]), None)

    cv_pg["real_team"] = cv_pg.apply(lookup_team, axis=1)

    # Attach team pace
    def lookup_pace(row):
        team = row["real_team"]
        season = row["season"]
        if team is None:
            return np.nan
        return pace_lookup.get((season, team), np.nan)

    cv_pg["team_pace"] = cv_pg.apply(lookup_pace, axis=1)

    n_total = len(cv_pg)
    n_with_pace = cv_pg["team_pace"].notna().sum()
    print(f"  Rows with pace data: {n_with_pace}/{n_total} "
          f"({100*n_with_pace/n_total:.1f}%)")

    # Compute raw volume per game and pace-adjusted per-100-possessions
    # For per100-FRAME cols: raw_per_game = rate_per100_frames * n_frames / 100
    for raw_col, raw_label, adj_label in VOLUME_FEATURES:
        if raw_col not in cv_pg.columns:
            cv_pg[raw_label] = np.nan
            cv_pg[adj_label] = np.nan
            continue

        if raw_col in ("cvb_passes_per100", "cvb_dribbles_per100"):
            # These are per 100 tracking frames; multiply by n_frames/100 to get total
            cv_pg[raw_label] = cv_pg[raw_col] * cv_pg["n_frames"] / 100.0
        else:
            # cvb_fatigue_score is already cumulative (total distance in pixels)
            cv_pg[raw_label] = cv_pg[raw_col]

        cv_pg[adj_label] = cv_pg[raw_label] * (100.0 / cv_pg["team_pace"])

    # Also adjust minutes_proxy (volume-dependent)
    cv_pg["adj_minutes_per_100poss"] = cv_pg["minutes_proxy"] * (100.0 / cv_pg["team_pace"])

    return cv_pg


# ---------------------------------------------------------------------------
# Step 4+5 -- Aggregate to per-player, build rankings, pace winners/victims
# ---------------------------------------------------------------------------

def aggregate_per_player(cv_pg: pd.DataFrame) -> pd.DataFrame:
    """Season-aggregate to one row per player. Use nba_player_id as key."""
    print("Step 4 -- Aggregating to per-player pace-adjusted stats...")

    agg_cols = (
        [raw for _, raw, _ in VOLUME_FEATURES]
        + [adj for _, _, adj in VOLUME_FEATURES]
        + ["adj_minutes_per_100poss", "team_pace"]
        + [c for c in STYLE_FEATURES if c in cv_pg.columns]
    )

    agg_spec: dict = {
        "game_id": "nunique",
        "real_team": lambda s: s.mode().iat[0] if not s.mode().empty else None,
        "season": lambda s: s.mode().iat[0] if not s.mode().empty else None,
        "player_name": lambda s: s.mode().iat[0] if not s.mode().empty else None,
        "team_pace": "mean",
    }
    for c in agg_cols:
        if c in cv_pg.columns and c not in ("real_team", "season", "player_name", "team_pace"):
            agg_spec[c] = "mean"

    valid = cv_pg[cv_pg["nba_player_id"].notna()].copy()
    valid["nba_player_id"] = valid["nba_player_id"].astype(int)

    agg = (
        valid.groupby("nba_player_id")
        .agg(agg_spec)
        .reset_index()
        .rename(columns={"game_id": "n_games"})
    )

    agg = agg[agg["n_games"] >= MIN_GAMES].copy()
    print(f"  Players with >= {MIN_GAMES} CV games: {len(agg)}")
    return agg


def build_rankings(agg: pd.DataFrame) -> dict:
    """Build top-N rankings per adjusted metric (raw vs adjusted comparison)."""
    print("Step 5 -- Building rankings and pace winners/victims...")

    rankings: dict = {}

    metric_configs = [
        ("adj_passes_per_100poss",   "raw_passes_per_game",   "Top 25 Playmakers (passes/100 poss)"),
        ("adj_dribbles_per_100poss", "raw_dribbles_per_game", "Top 25 Ball-Handlers (dribbles/100 poss)"),
        ("adj_fatigue_per_100poss",  "raw_fatigue_per_game",  "Top 25 Volume Players (fatigue/100 poss)"),
    ]

    for adj_col, raw_col, label in metric_configs:
        if adj_col not in agg.columns or raw_col not in agg.columns:
            continue

        sub = agg[["nba_player_id", "player_name", "real_team", "n_games",
                    "team_pace", raw_col, adj_col]].dropna(subset=[adj_col, raw_col])

        # Raw ranking
        sub = sub.copy()
        sub["raw_rank"] = sub[raw_col].rank(ascending=False).astype(int)
        sub["adj_rank"] = sub[adj_col].rank(ascending=False).astype(int)
        sub["rank_change"] = sub["raw_rank"] - sub["adj_rank"]  # positive = adj rank HIGHER

        top_adj = sub.nsmallest(TOP_N, "adj_rank")
        top_raw = sub.nsmallest(TOP_N, "raw_rank")

        # Pace winners: raw rank is higher (better) than adj rank -> fast team inflates them
        # rank_change < 0 -> dropped in adj (was ranked 5 raw, now 18 adj = rank_change = -13)
        # For "pace winners": raw_rank < adj_rank -> rank_change > 0 in raw_rank terms
        # Clarify: low rank = better. pace winner = raw_rank is LOWER (better) than adj_rank
        # meaning: raw_rank < adj_rank -> rank_change (raw - adj) < 0
        pace_winners = sub[sub["rank_change"] < 0].nsmallest(10, "rank_change").copy()
        pace_victims = sub[sub["rank_change"] > 0].nlargest(10, "rank_change").copy()

        def to_records(df, cols):
            return df[cols].rename(columns={
                raw_col: "raw_value", adj_col: "adj_value"
            }).to_dict(orient="records")

        rankings[adj_col] = {
            "label": label,
            "top25_by_adjusted": to_records(
                top_adj,
                ["player_name", "real_team", "n_games", "team_pace",
                 raw_col, adj_col, "raw_rank", "adj_rank", "rank_change"]
            ),
            "top25_by_raw": to_records(
                top_raw,
                ["player_name", "real_team", "n_games", "team_pace",
                 raw_col, adj_col, "raw_rank", "adj_rank", "rank_change"]
            ),
            "pace_winners": to_records(
                pace_winners,
                ["player_name", "real_team", "team_pace",
                 raw_col, adj_col, "raw_rank", "adj_rank", "rank_change"]
            ),
            "pace_victims": to_records(
                pace_victims,
                ["player_name", "real_team", "team_pace",
                 raw_col, adj_col, "raw_rank", "adj_rank", "rank_change"]
            ),
        }

    return rankings


# ---------------------------------------------------------------------------
# Step 6 -- Output
# ---------------------------------------------------------------------------

def write_outputs(
    cv_pg: pd.DataFrame,
    agg: pd.DataFrame,
    rankings: dict,
    pace_lookup_df: pd.DataFrame,
) -> None:
    """Write parquet, JSON, and Atlas markdown."""
    INTEL.mkdir(parents=True, exist_ok=True)
    VAULT.mkdir(parents=True, exist_ok=True)

    # ---- Parquet: per-player pace-adjusted stats ----
    parquet_cols = (
        ["nba_player_id", "player_name", "real_team", "season", "n_games", "team_pace"]
        + [raw for _, raw, _ in VOLUME_FEATURES]
        + [adj for _, _, adj in VOLUME_FEATURES]
        + ["adj_minutes_per_100poss"]
        + [c for c in STYLE_FEATURES if c in agg.columns]
    )
    parquet_cols = [c for c in parquet_cols if c in agg.columns]
    out_pq = agg[parquet_cols].copy()
    out_pq.to_parquet(OUT_PARQUET, index=False)
    print(f"  Wrote {OUT_PARQUET} ({len(out_pq)} rows)")

    # ---- JSON: rankings ----
    # Round floats for readability
    def round_records(records):
        cleaned = []
        for r in records:
            cleaned.append({
                k: (round(v, 3) if isinstance(v, float) else v)
                for k, v in r.items()
            })
        return cleaned

    json_out: dict = {}
    for metric, data in rankings.items():
        json_out[metric] = {
            k: round_records(v) if isinstance(v, list) else v
            for k, v in data.items()
        }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_out, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Wrote {OUT_JSON}")

    # ---- Atlas markdown ----
    _write_atlas(agg, rankings, pace_lookup_df, cv_pg)
    print(f"  Wrote {OUT_ATLAS}")


def _write_atlas(
    agg: pd.DataFrame,
    rankings: dict,
    pace_df: pd.DataFrame,
    cv_pg: pd.DataFrame,
) -> None:
    """Generate vault/Intelligence/Pace_Adjusted_Atlas.md."""
    n_players = len(agg)
    seasons = sorted(cv_pg["season"].unique())

    # League pace stats per season
    season_pace_stats = {}
    for season in seasons:
        sub = pace_df[pace_df["season"] == season].dropna(subset=["team_pace"])
        if sub.empty:
            continue
        fastest = sub.nlargest(3, "team_pace")[["team_abbrev", "team_pace"]]
        slowest = sub.nsmallest(3, "team_pace")[["team_abbrev", "team_pace"]]
        season_pace_stats[season] = {
            "fastest": fastest.to_dict(orient="records"),
            "slowest": slowest.to_dict(orient="records"),
            "mean": float(sub["team_pace"].mean()),
        }

    lines = ["# Pace-Adjusted CV Atlas", "", "## Methodology", ""]
    lines += [
        "Per-100-team-possessions normalization for volume CV features. "
        "Allows fair cross-team player comparisons regardless of team pace.",
        "",
        "**Volume features adjusted** (raw per-game -> per 100 team possessions):",
        "- `cvb_passes_per100` (frames) -> `adj_passes_per_100poss`",
        "- `cvb_dribbles_per100` (frames) -> `adj_dribbles_per_100poss`",
        "- `cvb_fatigue_score` (cumulative dist) -> `adj_fatigue_per_100poss`",
        "",
        "**Style features NOT adjusted** (already dimensionless rates):",
        "- paint_time_pct, near_basket_pct, avg_dist_to_basket, avg_defender_dist,",
        "  avg_spacing, contested_shot_pct, velocity_q4_dropoff",
        "",
        "**Formula:** `adj_stat = raw_per_game * (100 / team_pace_per_game)`",
        "",
        "## Coverage", "",
        f"- Players with >= {MIN_GAMES} CV games: **{n_players}**",
        f"- Seasons: {', '.join(seasons)}",
        "",
    ]

    # League pace by season
    lines.append("## League Pace Baselines")
    for season, stats in season_pace_stats.items():
        fastest_str = ", ".join(
            f"{r['team_abbrev']} ({r['team_pace']:.1f})" for r in stats["fastest"]
        )
        slowest_str = ", ".join(
            f"{r['team_abbrev']} ({r['team_pace']:.1f})" for r in stats["slowest"]
        )
        lines += [
            f"",
            f"### {season}",
            f"- League mean pace: **{stats['mean']:.1f}** poss/game",
            f"- Fastest teams: {fastest_str}",
            f"- Slowest teams: {slowest_str}",
        ]

    # Top-25 tables per metric
    for metric, data in rankings.items():
        label = data["label"]
        adj_col = metric
        lines += ["", f"## {label}", ""]

        top25 = data["top25_by_adjusted"][:25]
        header = "| Rank | Player | Team | Pace | Adj/100poss | Raw/game | Raw rank | Rank change |"
        sep = "|------|--------|------|------|------------|----------|----------|-------------|"
        lines += [header, sep]
        for i, r in enumerate(top25, 1):
            chg = r.get("rank_change", 0)
            chg_str = f"+{chg}" if chg > 0 else str(chg)
            lines.append(
                f"| {i} | {r.get('player_name','?')} | {r.get('real_team','?')} | "
                f"{r.get('team_pace', 0):.1f} | {r.get('adj_value', 0):.2f} | "
                f"{r.get('raw_value', 0):.2f} | {r.get('raw_rank', '?')} | {chg_str} |"
            )

        # Pace winners
        winners = data["pace_winners"][:10]
        if winners:
            lines += [
                "", f"### Pace Winners -- fast team inflates raw rank",
                "*(Raw rank is better than adjusted rank -- playing fast over-credits them)*",
                "",
                "| Player | Team | Pace | Raw rank | Adj rank | Inflation |",
                "|--------|------|------|----------|----------|-----------|",
            ]
            for r in winners:
                raw_r = r.get("raw_rank", "?")
                adj_r = r.get("adj_rank", "?")
                chg = r.get("rank_change", 0)
                lines.append(
                    f"| {r.get('player_name','?')} | {r.get('real_team','?')} | "
                    f"{r.get('team_pace',0):.1f} | #{raw_r} | #{adj_r} | "
                    f"{abs(chg)} spots inflated |"
                )

        # Pace victims
        victims = data["pace_victims"][:10]
        if victims:
            lines += [
                "", f"### Pace Victims -- slow team hides true volume",
                "*(Adjusted rank is better than raw rank -- playing slow under-credits them)*",
                "",
                "| Player | Team | Pace | Raw rank | Adj rank | Under-credit |",
                "|--------|------|------|----------|----------|--------------|",
            ]
            for r in victims:
                raw_r = r.get("raw_rank", "?")
                adj_r = r.get("adj_rank", "?")
                chg = r.get("rank_change", 0)
                lines.append(
                    f"| {r.get('player_name','?')} | {r.get('real_team','?')} | "
                    f"{r.get('team_pace',0):.1f} | #{raw_r} | #{adj_r} | "
                    f"{chg} spots hidden |"
                )

    # Usage guide
    lines += [
        "", "## How to Use", "",
        "- **Cross-team comparison**: Use `adj_*` when comparing a DAL player to a BOS player -- "
        "the raw counts favor DAL (faster) even if BOS player creates more per possession.",
        "- **Prop betting**: When a fast-team player has inflated raw counts, "
        "check adj rank -- if they drop 10+ spots, the raw volume may not repeat if pace slows.",
        "- **Lineup analysis**: Combine with INT-1 fingerprints + INT-16 sizing -- "
        "pace-adjusted features tell you who truly dominates per possession regardless of team.",
        "- **Example**: 'This player is ranked #22 raw but #7 adjusted -- slow team hid his real volume'",
        "",
        "## Honest Caveats",
        "",
        "- Pace data from NBA API `leaguedashteamstats` (season-level average).",
        "- CV coverage skewed: 90% of rows are 2025-26, only ~10% earlier seasons.",
        "- Players on multiple teams in a season: mapped to most-frequent team (mode).",
        "- `cvb_passes_per100` and `cvb_dribbles_per100` are per 100 TRACKING FRAMES, "
        "not per 100 possessions; conversion to raw uses n_frames.",
        "- Style features (shot zones, catch-shoot, paint pct) are intentionally NOT adjusted.",
    ]

    OUT_ATLAS.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Step 7 -- Report
# ---------------------------------------------------------------------------

def print_report(agg: pd.DataFrame, rankings: dict, cv_pg: pd.DataFrame) -> None:
    print()
    print("=" * 65)
    print("INT-31 Pace-Adjusted CV -- Final Report")
    print("=" * 65)

    seasons = sorted(cv_pg["season"].unique())
    n_players = len(agg)
    n_teams = cv_pg["real_team"].dropna().nunique()

    print(f"\nCoverage")
    print(f"  Players adjusted: {n_players}")
    print(f"  Teams with pace data: {n_teams}")
    print(f"  Seasons: {', '.join(seasons)}")
    print(f"  CV game-player rows: {len(cv_pg)}")

    for metric, data in rankings.items():
        label = data["label"]
        print(f"\n--- {label} ---")

        # Top 5 pace winners
        winners = data["pace_winners"][:5]
        if winners:
            print("  Top 5 pace WINNERS (fast team inflates raw rank):")
            for r in winners:
                raw_r = r.get("raw_rank", "?")
                adj_r = r.get("adj_rank", "?")
                chg = abs(r.get("rank_change", 0))
                print(f"    {r.get('player_name','?')} ({r.get('real_team','?')}, "
                      f"pace={r.get('team_pace',0):.1f}): "
                      f"raw #{raw_r} -> adj #{adj_r} ({chg} spots dropped)")

        # Top 5 pace victims
        victims = data["pace_victims"][:5]
        if victims:
            print("  Top 5 pace VICTIMS (slow team hides true volume):")
            for r in victims:
                raw_r = r.get("raw_rank", "?")
                adj_r = r.get("adj_rank", "?")
                chg = r.get("rank_change", 0)
                print(f"    {r.get('player_name','?')} ({r.get('real_team','?')}, "
                      f"pace={r.get('team_pace',0):.1f}): "
                      f"raw #{raw_r} -> adj #{adj_r} (+{chg} spots up)")

    print(f"\nFiles")
    print(f"  {OUT_PARQUET}")
    print(f"  {OUT_JSON}")
    print(f"  {OUT_ATLAS}")

    print("\nHow to use")
    print("  Adjusted metrics enable fair cross-team comparisons.")
    print("  'adj_passes_per_100poss=18 for BOS player' == same playmaking")
    print("  rate as 'adj_passes_per_100poss=18 for MIA player'.")
    print("  Raw counts alone favor fast-team players by 5-10% systematically.")

    print("\nHonest caveats")
    print("  - 90% of CV rows are 2025-26; earlier seasons have sparse coverage.")
    print("  - Pace from NBA API season averages, not game-by-game.")
    print("  - Trade destinations: player mapped to mode team in season.")
    print("  - Style features (paint_pct, shot_zones) intentionally NOT adjusted.")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("INT-31: Pace-Adjusted CV Intelligence")
    print("=" * 50)

    # Load CV data to determine which seasons we need
    cv_pg = pd.read_parquet(DATA / "player_cv_per_game.parquet")
    cv_pg["season"] = cv_pg["game_id"].apply(_season_from_game_id)
    seasons_needed = sorted(cv_pg["season"].unique())
    print(f"CV data covers seasons: {seasons_needed}")

    # Step 1: Pace lookup
    pace_lookup = build_pace_lookup(seasons_needed)
    pace_df = getattr(build_pace_lookup, "_raw_df", pd.DataFrame())

    # Step 2: Player -> team map
    player_team_map = build_player_team_map()

    # Step 3: Load & adjust
    cv_pg_adj = load_and_adjust(pace_lookup, player_team_map)

    # Step 4: Aggregate per-player
    agg = aggregate_per_player(cv_pg_adj)

    # Step 5: Rankings
    rankings = build_rankings(agg)

    # Step 6: Output
    write_outputs(cv_pg_adj, agg, rankings, pace_df)

    # Step 7: Report
    print_report(agg, rankings, cv_pg_adj)

    return 0


if __name__ == "__main__":
    sys.exit(main())
