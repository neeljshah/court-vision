"""NBA lineup-vs-lineup matchup segments -- first cross-team consumer of the
stint keystone (data/cache/team_system/lineups/stints_<season>.parquet,
built by pbp_lineups.py).

METHOD: for each (game_id, period), intersect the home and away teams'
CLEAN (n_on_court==5) stint intervals -- a standard two-pointer interval
merge, since each team's own stints are sorted and non-overlapping in time
-- to get 5-on-5 matchup segments (lineup_key_a vs lineup_key_b, overlap_s).
Segments for the same lineup pairing are then summed across periods into
one row per (game, lineup_key_a, lineup_key_b).

POINTS APPORTIONMENT (approximation): a stint's pts_for is a total for the
WHOLE stint, not attributed to sub-segments within it. A segment's points
are apportioned proportionally by its share of the parent stint's elapsed
time: pts_segment = stint.pts_for * overlap_s / stint.elapsed_s.
# ponytail: proportional time-apportionment, not event-level attribution --
# scoring is not uniform in time within a stint. Upgrade path: join
# play-by-play score events straight to segments (like on_off.py's
# attach_lineup_to_shots) for exact per-segment scoring.

team_id_a/team_id_b = the two team_ids in the game sorted ascending (an
arbitrary but deterministic tie-break -- NOT home/away).

OUTPUT: data/cache/team_system/lineups/lineup_matchups_<season>.parquet
  game_id, game_date, team_id_a, team_id_b, lineup_key_a, lineup_key_b,
  overlap_s, pts_a, pts_b.

MULTI-SEASON LANDMINE: unlike pbp_lineups.py this file has no season
auto-detection. --stints/--out default to the 2025-26 paths only; running
against 2023-24 / 2024-25 REQUIRES both flags passed explicitly, or you
silently re-process 2025-26 data under a different label.

NETWORK: zero. CLI: python -m domains.basketball_nba.lineups.lineup_matchups
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_GAMES_SRC = REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_STINTS_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
_OUT_COLS = ["game_id", "game_date", "team_id_a", "team_id_b", "lineup_key_a", "lineup_key_b", "overlap_s", "pts_a", "pts_b"]


def _period_length_s(period: int) -> float:
    return 720.0 if period <= 4 else 300.0  # ponytail: fixed OT=300s, same assumption as pbp_lineups.py


def intersect_stints(stints_a: list[dict[str, Any]], stints_b: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Two-pointer interval-merge of two teams' stints within one period
    (each input list already sorted by start_s, non-overlapping) -> overlap
    segments with time-apportioned points. No overlap -> no segment."""
    segments: list[dict[str, Any]] = []
    i = j = 0
    while i < len(stints_a) and j < len(stints_b):
        a, b = stints_a[i], stints_b[j]
        start, end = max(a["start_s"], b["start_s"]), min(a["end_s"], b["end_s"])
        if start < end:
            overlap_s = end - start
            pts_a = a["pts_for"] * overlap_s / a["elapsed_s"] if a["elapsed_s"] > 0 else 0.0
            pts_b = b["pts_for"] * overlap_s / b["elapsed_s"] if b["elapsed_s"] > 0 else 0.0
            segments.append({
                "lineup_key_a": a["lineup_key"], "lineup_key_b": b["lineup_key"],
                "overlap_s": overlap_s, "pts_a": pts_a, "pts_b": pts_b,
            })
        if a["end_s"] < b["end_s"]:
            i += 1
        elif b["end_s"] < a["end_s"]:
            j += 1
        else:
            i += 1
            j += 1
    return segments


def build_game_matchups(stints_df: pd.DataFrame) -> pd.DataFrame:
    """Per-(game, period) matchup segments across the whole stints table,
    before cross-period aggregation. One row per overlap segment."""
    rows: list[dict[str, Any]] = []
    for game_id, g_grp in stints_df.groupby("game_id"):
        team_ids = sorted(g_grp["team_id"].unique())
        if len(team_ids) != 2:
            continue  # ponytail: skip a game that isn't exactly 2 teams rather than guess a pairing
        team_a, team_b = team_ids
        for period, p_grp in g_grp.groupby("period"):
            stints_a = p_grp[(p_grp["team_id"] == team_a) & (p_grp["n_on_court"] == 5)].sort_values("start_s").to_dict("records")
            stints_b = p_grp[(p_grp["team_id"] == team_b) & (p_grp["n_on_court"] == 5)].sort_values("start_s").to_dict("records")
            if not stints_a or not stints_b:
                continue
            for seg in intersect_stints(stints_a, stints_b):
                seg["game_id"], seg["team_id_a"], seg["team_id_b"] = game_id, team_a, team_b
                rows.append(seg)
    return pd.DataFrame(rows, columns=["game_id", "team_id_a", "team_id_b", "lineup_key_a", "lineup_key_b", "overlap_s", "pts_a", "pts_b"])


def aggregate_matchups(seg_df: pd.DataFrame, games_df: pd.DataFrame) -> pd.DataFrame:
    """Sums segments sharing a lineup pairing across periods into one row
    per game, and attaches the GAME-DATED game_date via games.parquet."""
    if seg_df.empty:
        return pd.DataFrame(columns=_OUT_COLS)
    agg = seg_df.groupby(
        ["game_id", "team_id_a", "team_id_b", "lineup_key_a", "lineup_key_b"], as_index=False
    ).agg(overlap_s=("overlap_s", "sum"), pts_a=("pts_a", "sum"), pts_b=("pts_b", "sum"))
    date_by_gid = dict(zip(games_df["game_id"].astype(str), games_df["date"]))
    agg["game_date"] = agg["game_id"].astype(str).map(date_by_gid)
    agg["overlap_s"] = agg["overlap_s"].round(2)
    agg["pts_a"] = agg["pts_a"].round(3)
    agg["pts_b"] = agg["pts_b"].round(3)
    return agg[_OUT_COLS]


def sanity_check(seg_df: pd.DataFrame, stints_df: pd.DataFrame) -> pd.DataFrame:
    """Per-game invariant: summed overlap_s across all matchup segments
    should approximate the game's total clock length (both teams have a
    clean 5-man lineup on the floor almost the entire game, so the overlap
    segments partition the game clock once, not twice). Flags games whose
    total deviates from the periods-played length by more than 10%."""
    if seg_df.empty:
        return pd.DataFrame(columns=["game_id", "overlap_total_s", "expected_s", "pct_diff"])
    overlap_by_game = seg_df.groupby("game_id")["overlap_s"].sum()
    periods_by_game = stints_df.groupby("game_id")["period"].apply(lambda p: sorted(set(p)))
    rows = []
    for gid, overlap_total in overlap_by_game.items():
        expected = sum(_period_length_s(p) for p in periods_by_game.get(gid, []))
        pct_diff = (overlap_total - expected) / expected if expected > 0 else float("nan")
        rows.append({"game_id": gid, "overlap_total_s": round(overlap_total, 1), "expected_s": expected, "pct_diff": round(pct_diff, 4)})
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build NBA lineup-vs-lineup matchup segments from stint tables")
    parser.add_argument("--stints", type=str, default=str(_STINTS_DIR / "stints_2025_26.parquet"))
    parser.add_argument("--pbp-dir", type=str, default=None, help="unused -- accepted for CLI parity with pbp_lineups.py/on_off.py")
    parser.add_argument("--out", type=str, default=str(_STINTS_DIR / "lineup_matchups_2025_26.parquet"))
    args = parser.parse_args(argv)

    stints_df = pd.read_parquet(args.stints)
    games_df = pd.read_parquet(_GAMES_SRC)

    seg_df = build_game_matchups(stints_df)
    result = aggregate_matchups(seg_df, games_df)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out_path, index=False)

    invariant_df = sanity_check(seg_df, stints_df)
    n_games = int(invariant_df["game_id"].nunique()) if not invariant_df.empty else 0
    flagged = invariant_df[invariant_df["pct_diff"].abs() > 0.10] if not invariant_df.empty else invariant_df
    print(f"games={n_games} matchup_rows={len(result)} -> {out_path}")
    if not invariant_df.empty:
        print(
            f"overlap/game-length invariant: mean_pct_diff={invariant_df['pct_diff'].mean():.4f} "
            f"median={invariant_df['pct_diff'].median():.4f} flagged(>10pct)={len(flagged)}/{n_games}"
        )
        for _, row in flagged.head(20).iterrows():
            print(f"  FLAG game_id={row['game_id']} overlap_s={row['overlap_total_s']} expected_s={row['expected_s']} pct_diff={row['pct_diff']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
