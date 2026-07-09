"""Bullpen-state reconstruction from GUMBO live ticks (edge queue item 1, rung 8).

`bullpen_used` does not exist as a tick field (only a schema comment). This module
reconstructs it from the fields that DO exist at 100% coverage across all 70 games in
data/domains/mlb/gumbo_live/*.jsonl: `pitcher_id` (who is on the mound this tick) and
`pitcher_pitches` (that pitcher's own cumulative pitch count -- resets to 0 whenever
`pitcher_id` changes). No fabrication: this is a direct read of already-present fields,
not a fitted or heuristic proxy.

Convention (standard baseball): `half == "Top"` -> away team bats, HOME team pitches.
`half == "Bottom"` -> home team bats, AWAY team pitches. So `pitcher_id` on a Top row
is the home pitcher; on a Bottom row it is the away pitcher.

Per-tick output columns:
  game_pk, ts, inning, half, pitching_side ("home"/"away"), current_pitcher_id,
  current_pitcher_pitches (fatigue proxy, needs no reconstruction -- passthrough of
  `pitcher_pitches`), pitchers_used_so_far (count of distinct pitcher_ids the pitching
  side has used up to and including this tick), relievers_used_so_far
  (pitchers_used_so_far - 1; 0 while the starter is still in).

HAND-VERIFIED (see tests/domains/mlb/test_rung8_state.py): for game_pk 822710, the
reconstructed pitcher-change sequence matches
data/domains/mlb/gumbo_live/_poller_state.json's real boxscore.teams.{home,away}.pitchers
list exactly (home: 656492 -> 687377 -> 664875; away: 681293 -> 695001 -> 663878 -> 664299).

PURE pandas. No src/kernel/api imports. ASCII only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[4]
_GUMBO_DIR = _REPO_ROOT / "data" / "domains" / "mlb" / "gumbo_live"


def load_game_ticks(game_pk: int, gumbo_dir: Path = _GUMBO_DIR) -> pd.DataFrame:
    """Load and time-sort one game's raw GUMBO ticks into a DataFrame."""
    path = gumbo_dir / f"{game_pk}.jsonl"
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # `captured_at` (ISO 8601, 100% coverage) is the reliable sort key -- the raw `ts`
    # field uses a non-ISO "YYYYMMDD_HHMMSS" GUMBO-internal format and is kept as-is.
    df["captured_at"] = pd.to_datetime(df["captured_at"])
    return df.sort_values("captured_at").reset_index(drop=True)


_HALF_TO_SIDE = {"top": "home", "bottom": "away"}  # who is PITCHING on that half


def reconstruct_bullpen_state(ticks: pd.DataFrame) -> pd.DataFrame:
    """Add pitching-side + reconstructed bullpen-usage columns to a ticks frame.

    `ticks` must be time-sorted (as returned by `load_game_ticks`) and carry
    game_pk, captured_at, inning, half, pitcher_id, pitcher_pitches.

    `half` takes 4 raw GUMBO values: Top/Bottom (live, a batter is up) and
    Middle/End (between half-innings -- no side is actively pitching a batter).
    Only Top/Bottom rows get a `pitching_side` and a reconstructed bullpen count;
    Middle/End rows are kept in the output but left NaN on those two columns
    (there is no well-defined "current pitcher" mid-transition, and mapping them
    to either side by string prefix silently mixed home/away pitcher_ids in an
    earlier version of this function -- verified via the game_pk 822710 boxscore
    cross-check, see tests/domains/mlb/test_rung8_state.py).
    """
    if ticks.empty:
        return ticks.copy()

    df = ticks.copy()
    df["pitching_side"] = df["half"].astype(str).str.lower().map(_HALF_TO_SIDE)
    df["current_pitcher_id"] = df["pitcher_id"].where(df["pitching_side"].notna())
    df["current_pitcher_pitches"] = df["pitcher_pitches"].where(df["pitching_side"].notna())

    live = df[df["pitching_side"].notna()]
    out_frames = []
    for side, grp in live.groupby("pitching_side", sort=False):
        grp = grp.sort_values("captured_at").copy()
        # distinct pitcher_ids seen so far, in order of first appearance for this side.
        first_seen_rank = (
            grp["current_pitcher_id"]
            .drop_duplicates()
            .reset_index(drop=True)
        )
        rank_map = {pid: i + 1 for i, pid in enumerate(first_seen_rank)}
        grp["pitchers_used_so_far"] = grp["current_pitcher_id"].map(rank_map)
        out_frames.append(grp)

    live_result = pd.concat(out_frames) if out_frames else live.assign(pitchers_used_so_far=pd.Series(dtype="float64"))
    dead = df[df["pitching_side"].isna()].copy()
    dead["pitchers_used_so_far"] = pd.NA

    result = pd.concat([live_result, dead]).sort_values("captured_at").reset_index(drop=True)
    result["relievers_used_so_far"] = result["pitchers_used_so_far"] - 1
    return result


def pitcher_change_sequence(ticks_with_state: pd.DataFrame, side: str) -> list:
    """Ordered list of distinct pitcher_ids used by `side` ("home"/"away"),
    in first-appearance order -- for hand-verification against a boxscore."""
    sub = ticks_with_state[ticks_with_state["pitching_side"] == side].sort_values("captured_at")
    seen: list = []
    for pid in sub["current_pitcher_id"]:
        if not seen or seen[-1] != pid:
            if pid not in seen:
                seen.append(pid)
    return seen


__all__ = [
    "load_game_ticks",
    "reconstruct_bullpen_state",
    "pitcher_change_sequence",
]
