"""Reconstruct 5-woman on-court lineup STINTS per team per game from raw WNBA
play-by-play substitution events (data/domains/wnba/cdn_backfill/<gameId>/
playbyplay.json, 168 2026 games) -- an adapter over the NBA stint-reconstruction
engine (domains.basketball_nba.lineups.pbp_lineups), per the field-mapping
census in ../PBP_CENSUS.md: WNBA PBP carries the exact same action fields
(actionType/personId/actionNumber/clock/period/teamId/teamTricode/subType) the
NBA engine already walks, so the substitution-walk/heuristic-repair machinery
(build_team_stints, _box_starters, _heuristic_starters, _elapsed_s) is reused
UNMODIFIED via import. Three seams differ and are adapted here, nothing else:

  1. quarter length -- WNBA plays 4x10min (600s) quarters, not NBA's 12min
     (720s); OT is 5min (300s) in both. Patched via a module-level monkeypatch
     of pbp_lineups._period_length_s -- build_team_stints/_elapsed_s look up
     that name in pbp_lineups' own globals at call time, so patching the
     imported module's attribute (never editing its file) changes what both
     functions see for the duration of one build call.
  2. box-score starter seed -- WNBA's player_boxscores.parquet has
     started:bool + team_id (numeric, matches PBP teamId directly) where
     NBA's box has starter:"1"/"0" (string) matched against a team tricode.
     _adapt_box_df() reshapes into the exact columns _box_starters already
     expects (game_id, team, starter, player_id); team_id (not tricode) is
     then threaded through every build_team_stints call as the positional
     "team_tricode" argument, so the untouched NBA predicate
     (box_df["team"] == team_tricode) lines up on the WNBA numeric id.
  3. no separate games.parquet -- home/away + game_date both already live on
     every row of player_boxscores.parquet (is_home, game_date), so no
     NBA-style games.parquet lookup is built or needed.

OUTPUT: data/cache/team_system/lineups/stints_wnba_2026.parquet, SAME schema
as the NBA stint table (game_id, team_id, period, lineup_key, n_on_court,
start_s, end_s, elapsed_s, pts_for, pts_against, quality) so on_off/gravity_
spacing/lineup_matchups all read it unchanged once pointed at this path.

NETWORK: zero. CLI: python -m domains.basketball_wnba.lineups.pbp_lineups_wnba
Per-file test: python -m pytest domains/basketball_wnba/lineups/test_pbp_lineups_wnba.py -q
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

import domains.basketball_nba.lineups.pbp_lineups as nba_pbp

REPO_ROOT = Path(__file__).resolve().parents[3]
_PBP_DIR = REPO_ROOT / "data" / "domains" / "wnba" / "cdn_backfill"
_BOX_SRC = REPO_ROOT / "data" / "domains" / "wnba" / "player_boxscores.parquet"
_OUT_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "stints_wnba_2026.parquet"

_QUARTER_S = 600.0  # WNBA: 4x10-min quarters (NBA is 12-min/720s)
_OT_S = 300.0       # WNBA OT is 5-min, same length as NBA's


def _wnba_period_length_s(period: int) -> float:
    return _QUARTER_S if period <= 4 else _OT_S


def _adapt_box_df(box_df: pd.DataFrame) -> pd.DataFrame:
    """Reshape the WNBA box into the exact columns pbp_lineups._box_starters
    (unmodified, imported) reads: game_id, team, starter, player_id."""
    out = box_df.copy()
    out["game_id"] = out["game_id"].astype(str)
    out["team"] = out["team_id"].astype("int64").astype(str)
    out["starter"] = out["started"]
    out["player_id"] = out["player_id"].astype("int64")
    return out


def build_game_stints_wnba(game_json: dict[str, Any], box_df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[str]]:
    """WNBA counterpart of pbp_lineups.build_game_stints: keys teams by
    numeric team_id (WNBA box has no tricode column) instead of tricode, and
    reads home/away off the box's own is_home column instead of a separate
    games.parquet. Delegates the actual stint walk, unmodified, to the
    imported build_team_stints for every team in the game."""
    game_id = str(game_json["game"]["gameId"])
    actions = game_json["game"]["actions"]
    team_ids = sorted({a["teamId"] for a in actions if a.get("teamId")})
    box_game = box_df[box_df["game_id"] == game_id]
    home_rows = box_game[box_game["is_home"] == True]  # noqa: E712
    home_team_id = int(home_rows["team_id"].iloc[0]) if not home_rows.empty else None

    orig_period_len = nba_pbp._period_length_s
    nba_pbp._period_length_s = _wnba_period_length_s
    try:
        all_stints: list[dict[str, Any]] = []
        all_notes: list[str] = []
        for team_id in team_ids:
            stints, notes = nba_pbp.build_team_stints(
                game_id, team_id, str(team_id), actions, box_game, team_id == home_team_id,
            )
            all_stints.extend(stints)
            all_notes.extend(f"{game_id}/{team_id}:{n}" for n in notes)
    finally:
        nba_pbp._period_length_s = orig_period_len
    return all_stints, all_notes


def coverage_invariant(stints_df: pd.DataFrame) -> pd.DataFrame:
    """Per (game_id, team_id): pct of the team's expected game-clock
    (4x600s + 300s per OT period actually played) covered by CLEAN
    (n_on_court==5) stints."""
    rows = []
    for (gid, tid), grp in stints_df.groupby(["game_id", "team_id"]):
        periods = sorted(set(grp["period"]))
        expected_s = sum(_wnba_period_length_s(p) for p in periods)
        clean_s = grp.loc[grp["n_on_court"] == 5, "elapsed_s"].sum()
        rows.append({
            "game_id": gid, "team_id": tid, "expected_s": expected_s,
            "clean_s": round(clean_s, 1),
            "pct_clean": round(clean_s / expected_s, 4) if expected_s else float("nan"),
        })
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconstruct WNBA lineup stints from PBP")
    parser.add_argument("--out", type=str, default=str(_OUT_PATH))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--pbp-dir", type=str, default=None, help="override input dir (default: wnba/cdn_backfill)")
    args = parser.parse_args(argv)

    box_df = _adapt_box_df(pd.read_parquet(_BOX_SRC))
    pbp_dir = Path(args.pbp_dir) if args.pbp_dir else _PBP_DIR
    game_dirs = sorted(d for d in pbp_dir.iterdir() if d.is_dir() and (d / "playbyplay.json").exists())
    if args.limit:
        game_dirs = game_dirs[: args.limit]

    rows: list[dict[str, Any]] = []
    all_notes: list[str] = []
    n_repaired_games = 0
    for d in game_dirs:
        try:
            game_json = json.loads((d / "playbyplay.json").read_text(encoding="utf-8"))
            stints, notes = build_game_stints_wnba(game_json, box_df)
            rows.extend(stints)
            if notes:
                n_repaired_games += 1
                all_notes.extend(notes)
        except Exception as e:  # noqa: BLE001 -- one bad game must not kill the batch
            all_notes.append(f"{d.name}:FAILED:{e}")

    stints_df = pd.DataFrame(rows)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stints_df.to_parquet(out_path, index=False)
    print(f"games_parsed={len(game_dirs)} stint_rows={len(rows)} games_with_quality_notes={n_repaired_games}")
    for n in all_notes[:30]:
        print("  ", n)
    if len(all_notes) > 30:
        print(f"  ... {len(all_notes) - 30} more quality notes")

    if not stints_df.empty:
        cov = coverage_invariant(stints_df)
        flagged = cov[cov["pct_clean"] < 0.90]
        print(
            f"coverage invariant: mean_pct_clean={cov['pct_clean'].mean():.4f} "
            f"median={cov['pct_clean'].median():.4f} flagged(<90pct)={len(flagged)}/{len(cov)}"
        )
        for _, row in flagged.sort_values("pct_clean").head(20).iterrows():
            print(f"  FLAG game_id={row['game_id']} team_id={row['team_id']} pct_clean={row['pct_clean']}")
    print(f"wrote -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
