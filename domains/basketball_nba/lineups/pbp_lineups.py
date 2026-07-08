"""Reconstruct 5-man on-court lineup STINTS per team per game from raw NBA
play-by-play substitution events (data/cache/team_system/pbp/*.json, 196
2025-26 games).

METHOD -- continuous walk, not a per-period fresh guess: period-1 on-court
set is seeded from the game's own box-score `starter` flag
(data/domains/basketball_nba/player_boxscores.parquet, verified present for
every 2025-26 game_id here); every later period simply CONTINUES the
previous period's ending on-court set, because the NBA feed logs
period-start bench changes as ordinary substitution events (verified on
0022500003.json: Q2 opens with 6 explicit sub-out/sub-in pairs at
PT12M00S, not a silent reset) -- so applying every substitution action in
actionNumber order across the whole game reconstructs every stint boundary,
period breaks included.

FALLBACK (only when the primary seed is unavailable or a period ever drifts
away from exactly 5 players -- missing box-score starter flag, an unpaired
sub, a mis-logged event): re-seed that period from the "acted before this
team's first sub of the period, OR was subbed out before ever being subbed
in" heuristic; if that ALSO misses 5, force the 5 earliest-acting personIds.
Every repair is recorded in the row's `quality` field (never a crash).

OUTPUT: one row per stint -- data/cache/team_system/lineups/stints_2025_26.parquet
  game_id, team_id, period, lineup_key (5 sorted personIds, comma-joined),
  start_s, end_s, elapsed_s (seconds within the period), pts_for, pts_against,
  quality (empty string when clean).

NETWORK: zero. Pure stdlib json + pandas over already-materialized files.
CLI: python -m domains.basketball_nba.lineups.pbp_lineups
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
from itertools import groupby
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_PBP_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "pbp"
_BOX_SRC = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_OUT_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "stints_2025_26.parquet"

_CLOCK_RE = re.compile(r"PT(\d+)M(\d+(?:\.\d+)?)S")


def _period_length_s(period: int) -> float:
    return 720.0 if period <= 4 else 300.0  # ponytail: fixed OT=300s, untested on a real OT game here


def _elapsed_s(period: int, clock: str) -> float:
    m = _CLOCK_RE.match(clock)
    remaining = float(m.group(1)) * 60.0 + float(m.group(2))
    return _period_length_s(period) - remaining


def _score_index(actions: list[dict[str, Any]]) -> tuple[list[int], list[tuple[int, int]]]:
    rows = sorted(
        ((a["actionNumber"], int(a["scoreHome"]), int(a["scoreAway"])) for a in actions if a.get("scoreHome") is not None),
        key=lambda t: t[0],
    )
    return [r[0] for r in rows], [(r[1], r[2]) for r in rows]


def _score_at(nums: list[int], scores: list[tuple[int, int]], action_number: int | None) -> tuple[int, int]:
    if action_number is None or not nums:
        return (0, 0)
    i = bisect.bisect_right(nums, action_number) - 1
    return scores[i] if i >= 0 else (0, 0)


def _box_starters(box_df: pd.DataFrame, game_id: str, team_tricode: str, known_person_ids: set[int]) -> set[int] | None:
    """Box-score `starter` flag, REJECTED unless all 5 ids are also seen in
    this team's own PBP actions -- guards against a real cross-source ID
    mismatch found in the ESPN-backfill box scores (a handful of players,
    e.g. Ben Saraf/BKN, carry a negative placeholder player_id there that
    does not match their real PBP personId; trusting it seeds a phantom
    'starter' PBP never subs out, cascading into a 6-man lineup)."""
    rows = box_df[(box_df["game_id"] == game_id) & (box_df["team"] == team_tricode)]
    starters = rows[rows["starter"] == True]["player_id"].astype(int).tolist()  # noqa: E712
    if len(starters) != 5 or not set(starters) <= known_person_ids:
        return None
    return set(starters)


def _heuristic_starters(period_team_actions: list[dict[str, Any]]) -> set[int]:
    subs = [a for a in period_team_actions if a["actionType"] == "substitution"]
    first_sub_num = min((a["actionNumber"] for a in subs), default=10 ** 9)
    non_sub = [a for a in period_team_actions if a["actionType"] != "substitution" and a.get("personId")]
    pre = {a["personId"] for a in non_sub if a["actionNumber"] < first_sub_num}
    first_sub_type: dict[int, str] = {}
    for s in sorted(subs, key=lambda x: x["actionNumber"]):
        first_sub_type.setdefault(s["personId"], s["subType"])
    starters = pre | {p for p, t in first_sub_type.items() if t == "out"}
    if len(starters) != 5:
        first_seen: dict[int, int] = {}
        for a in sorted(period_team_actions, key=lambda x: x["actionNumber"]):
            pid = a.get("personId")
            if pid and pid not in first_seen:
                first_seen[pid] = a["actionNumber"]
        starters = set(sorted(first_seen, key=lambda p: first_seen[p])[:5])
    return starters


def _make_stint(
    game_id: str, team_id: int, period: int, start_s: float, end_s: float,
    lineup: set[int], start_score: tuple[int, int], end_score: tuple[int, int], is_home: bool, quality: str,
) -> dict[str, Any]:
    pts_for = (end_score[0] - start_score[0]) if is_home else (end_score[1] - start_score[1])
    pts_against = (end_score[1] - start_score[1]) if is_home else (end_score[0] - start_score[0])
    return {
        "game_id": game_id,
        "team_id": team_id,
        "period": period,
        "lineup_key": ",".join(str(p) for p in sorted(lineup)),  # comma, not '-': a '-' collides with negative ids
        "n_on_court": len(lineup),
        "start_s": start_s,
        "end_s": end_s,
        "elapsed_s": end_s - start_s,
        "pts_for": pts_for,
        "pts_against": pts_against,
        "quality": quality,
    }


def build_team_stints(
    game_id: str, team_id: int, team_tricode: str, actions: list[dict[str, Any]],
    box_df: pd.DataFrame, is_home: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    nums, scores = _score_index(actions)
    periods = sorted(set(a["period"] for a in actions))
    lineup: set[int] | None = None
    stints: list[dict[str, Any]] = []
    notes: list[str] = []

    for period in periods:
        p_actions = sorted((a for a in actions if a["period"] == period), key=lambda x: x["actionNumber"])
        t_actions = [a for a in p_actions if a.get("teamId") == team_id]
        subs = [a for a in t_actions if a["actionType"] == "substitution"]

        if lineup is None or len(lineup) != 5:
            known_ids = {a["personId"] for a in t_actions if a.get("personId")}
            seed = _box_starters(box_df, game_id, team_tricode, known_ids) if period == periods[0] else None
            if seed is None:
                seed = _heuristic_starters(t_actions)
                notes.append(f"period{period}:heuristic_seed(n={len(seed)})")
            lineup = seed

        current = set(lineup)
        period_start_num = p_actions[0]["actionNumber"] if p_actions else None
        seg_start_s, seg_start_score = 0.0, _score_at(nums, scores, (period_start_num - 1) if period_start_num else None)
        stint_quality = "" if len(current) == 5 else f"period{period}:bad_seed_n={len(current)}"

        for clock_val, batch_iter in groupby(subs, key=lambda a: a["clock"]):
            batch = list(batch_iter)
            boundary_s = _elapsed_s(period, clock_val)
            boundary_num = max(a["actionNumber"] for a in batch)
            end_score = _score_at(nums, scores, boundary_num)
            stints.append(_make_stint(game_id, team_id, period, seg_start_s, boundary_s, current, seg_start_score, end_score, is_home, stint_quality))
            for a in batch:
                pid = a["personId"]
                if pid is None:  # unmapped sub (ESPN name-resolve miss): note it, never sorted()-crash on None
                    notes.append(f"period{period}:sub_unmapped_person")
                    continue
                if a["subType"] == "out":
                    if pid not in current:
                        notes.append(f"period{period}:sub_out_not_on_court({pid})")
                    current.discard(pid)
                else:
                    if pid in current:
                        notes.append(f"period{period}:sub_in_already_on_court({pid})")
                    current.add(pid)
            seg_start_s, seg_start_score = boundary_s, end_score
            stint_quality = "" if len(current) == 5 else f"period{period}:n_on_court={len(current)}"
            if stint_quality:
                notes.append(stint_quality)

        period_len = _period_length_s(period)
        final_score = _score_at(nums, scores, p_actions[-1]["actionNumber"]) if p_actions else seg_start_score
        stints.append(_make_stint(game_id, team_id, period, seg_start_s, period_len, current, seg_start_score, final_score, is_home, stint_quality))
        lineup = set(current)

    return stints, notes


def build_game_stints(game_json: dict[str, Any], box_df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[str]]:
    game_id = game_json["game"]["gameId"]
    actions = game_json["game"]["actions"]
    team_tricode = {a["teamId"]: a["teamTricode"] for a in actions if a.get("teamId")}
    box_game = box_df[box_df["game_id"] == game_id]
    home_rows = box_game[box_game["is_home"] == 1]
    home_tricode = home_rows["team"].iloc[0] if not home_rows.empty else None

    all_stints: list[dict[str, Any]] = []
    all_notes: list[str] = []
    for team_id, tricode in team_tricode.items():
        stints, notes = build_team_stints(game_id, team_id, tricode, actions, box_game, tricode == home_tricode)
        all_stints.extend(stints)
        all_notes.extend(f"{game_id}/{tricode}:{n}" for n in notes)
    return all_stints, all_notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconstruct NBA lineup stints from PBP")
    parser.add_argument("--out", type=str, default=str(_OUT_PATH))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--pbp-dir", type=str, default=None, help="override input dir (default: team_system/pbp)")
    args = parser.parse_args(argv)

    box_df = pd.read_parquet(_BOX_SRC)
    pbp_dir = Path(args.pbp_dir) if args.pbp_dir else _PBP_DIR
    files = sorted(pbp_dir.glob("*.json"))
    if args.limit:
        files = files[: args.limit]

    rows: list[dict[str, Any]] = []
    all_notes: list[str] = []
    n_repaired_games = 0
    for fp in files:
        try:
            game_json = json.loads(fp.read_text(encoding="utf-8"))
            stints, notes = build_game_stints(game_json, box_df)
            rows.extend(stints)
            if notes:
                n_repaired_games += 1
                all_notes.extend(notes)
        except Exception as e:  # noqa: BLE001 -- one bad game must not kill the batch
            all_notes.append(f"{fp.name}:FAILED:{e}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(out_path, index=False)
    print(f"games_parsed={len(files)} stint_rows={len(rows)} games_with_quality_notes={n_repaired_games}")
    for n in all_notes[:30]:
        print("  ", n)
    if len(all_notes) > 30:
        print(f"  ... {len(all_notes) - 30} more quality notes")
    print(f"wrote -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
