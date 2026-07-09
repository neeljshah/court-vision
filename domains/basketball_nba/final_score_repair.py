"""domains.basketball_nba.final_score_repair -- OT final-score truncation fix.

BUG (found by composite v2, commit 7b5ad29a): for OT games, BOTH
player_boxscores.parquet AND espn_boxscores.parquet record the TIED
end-of-regulation score as the final, not the true OT-inclusive final.

ROOT CAUSE (OURS, not upstream): scripts/fetch_per_quarter_boxscores.py
hardcodes ``_PERIODS = (1, 2, 3, 4)`` -- it fetches exactly 4 quarters per
game and NEVER requests period 5+ (OT) from the NBA stats API, which fully
supports it. Every game whose quarter_box cache is period-1..4-only (no q0
full-game file) is therefore missing all OT scoring for every player AND
the team total. A separate, already-existing full-game ESPN backfill
(ingest_espn_player_box.py, writes "_q0.json") IS OT-safe (ESPN's full-game
total already includes OT) but has only been run for 2023-24 and part of
2025-26 -- 2024-25 (1225 games, 60 confirmed OT games) has NO q0 coverage
and cannot be corrected at the per-player stat-line level without a new
network fetch (out of scope here, no network).

This module provides a LOCAL, network-free repair for the TEAM-level final
score / game outcome only, using the raw pbp action log already cached
under data/cache/team_system/pbp*/ (the same source composite v2 uses for
exact score attribution). Every action carries cumulative
(scoreHome, scoreAway); the last scored action of the game IS the true
final, OT included. This does NOT recover per-player OT stat splits --
that would need the missing network fetch. See docs/research/organization-
sprint/ for the proposed fetcher fix (add period 5+ fetching).

CLI:  python -m domains.basketball_nba.final_score_repair
Test: python -m pytest domains/basketball_nba/test_final_score_repair.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PBP_DIRS = {
    "2023-24": _REPO_ROOT / "data" / "cache" / "team_system" / "pbp_2023_24",
    "2024-25": _REPO_ROOT / "data" / "cache" / "team_system" / "pbp_2024_25",
    "2025-26": _REPO_ROOT / "data" / "cache" / "team_system" / "pbp",
}
_GAMES_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_BOX_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_OUT_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "game_finals_corrected.parquet"

OUTPUT_COLS = (
    "game_id", "season", "home_team", "away_team",
    "home_pts_true", "away_pts_true", "home_win_true", "is_ot",
    "box_home_pts", "box_away_pts", "was_truncated",
)


def _pbp_path_for(game_id: str) -> Optional[Path]:
    """Find the pbp json for game_id by trying every known season dir.

    game_id season prefix (e.g. "0022300...") is not directly mapped to a
    dir name, so this just checks each dir for the filename (cheap: 3
    stat calls, no directory scan).
    """
    for d in _PBP_DIRS.values():
        fp = d / f"{game_id}.json"
        if fp.exists():
            return fp
    return None


def reconstruct_final_from_pbp(game_id: str) -> Optional[Tuple[int, int, bool]]:
    """Return (true_home_pts, true_away_pts, is_ot) from the raw pbp action
    log, or None if no pbp file is cached for this game_id."""
    fp = _pbp_path_for(str(game_id))
    if fp is None:
        return None
    try:
        gj = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    actions = (gj.get("game") or {}).get("actions") or []
    score_actions = [a for a in actions if a.get("scoreHome") is not None]
    if not score_actions:
        return None
    periods = {a.get("period") for a in actions}
    is_ot = any(isinstance(p, int) and p > 4 for p in periods)
    last = score_actions[-1]
    try:
        return int(last["scoreHome"]), int(last["scoreAway"]), is_ot
    except (TypeError, ValueError, KeyError):
        return None


def build_corrected_finals(out_path: Optional[str] = None) -> Path:
    """Build the authoritative finals lookup for every game with a cached
    pbp file, cross-checked against player_boxscores' summed pts so
    callers can see which rows were truncated (was_truncated=True).

    Consumers wanting a correct home_win / margin for OT games should join
    on game_id against this table instead of summing player_boxscores or
    reading espn_boxscores home_score/away_score directly.
    """
    dest = Path(out_path) if out_path is not None else _OUT_PARQUET
    games = pd.read_parquet(_GAMES_PARQUET)[["game_id", "season", "home_team", "away_team"]]
    games["game_id"] = games["game_id"].astype(str)

    box_pts = pd.DataFrame(columns=["game_id", "team", "is_home", "pts"])
    if _BOX_PARQUET.exists():
        box = pd.read_parquet(_BOX_PARQUET, columns=["game_id", "team", "is_home", "pts"])
        box_pts = box.groupby(["game_id", "team", "is_home"])["pts"].sum().reset_index()

    rows = []
    for r in games.itertuples(index=False):
        recon = reconstruct_final_from_pbp(r.game_id)
        if recon is None:
            continue
        th, ta, is_ot = recon
        g = box_pts[box_pts["game_id"] == r.game_id]
        hr = g[(g["is_home"] == True) | (g["is_home"] == 1.0)]  # noqa: E712
        ar = g[(g["is_home"] == False) | (g["is_home"] == 0.0)]  # noqa: E712
        bh = float(hr["pts"].iloc[0]) if not hr.empty else None
        ba = float(ar["pts"].iloc[0]) if not ar.empty else None
        truncated = bh is not None and ba is not None and (bh != th or ba != ta)
        rows.append({
            "game_id": r.game_id, "season": r.season,
            "home_team": r.home_team, "away_team": r.away_team,
            "home_pts_true": th, "away_pts_true": ta,
            "home_win_true": float(th > ta), "is_ot": bool(is_ot),
            "box_home_pts": bh, "box_away_pts": ba,
            "was_truncated": bool(truncated),
        })

    df = pd.DataFrame(rows, columns=list(OUTPUT_COLS))
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(str(dest), index=False)
    return dest


if __name__ == "__main__":
    dest = build_corrected_finals()
    df = pd.read_parquet(str(dest))
    n_ot = int(df["is_ot"].sum())
    n_trunc = int(df["was_truncated"].sum())
    print(f"Wrote {dest}")
    print(f"Games with pbp-reconstructed finals: {len(df)}")
    print(f"OT games: {n_ot} | truncated (parquet had tied reg-time score): {n_trunc}")
    print("Descriptive only; NO edge claimed.")
