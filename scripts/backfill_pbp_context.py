"""
backfill_pbp_context.py -- Fill scoreboard, shot_clock, player_name, and team_abbrev
from locally-cached NBA PBP data.

For each game_id:
1. Auto-detects clip-to-game-clock offset via made-shot timing alignment.
2. Writes team_colors.json (jersey color -> NBA team abbrev).
3. Updates shot_log.csv with player_name + team_abbrev per shot.
4. Writes game_context.csv (frame-level: period, score_home, score_away,
   score_margin, shot_clock_est, game_clock_sec).
5. Patches features.csv scoreboard_period, scoreboard_score_diff,
   shot_clock_est columns in-place (chunked, handles 2GB+ files).

Usage:
    python scripts/backfill_pbp_context.py --game 0022401123
    python scripts/backfill_pbp_context.py        # all games with PBP cache
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKING_DIR = os.path.join(PROJECT_DIR, "data", "tracking")
NBA_CACHE    = os.path.join(PROJECT_DIR, "data", "nba")
GAMES_DIR    = os.path.join(PROJECT_DIR, "data", "games")

_SHOT_WINDOW  = 4.0   # seconds tolerance for CV-shot <-> PBP-shot match
_PERIOD_LEN   = 720   # seconds per quarter
_OT_LEN       = 300   # seconds per OT period
_DEFAULT_SC   = 24.0  # default shot clock at possession start


# ---------------------------------------------------------------------------
# PBP helpers
# ---------------------------------------------------------------------------

def _period_start_sec(period: int) -> int:
    """Absolute game seconds at the start of a period (1-indexed)."""
    if period <= 4:
        return (period - 1) * _PERIOD_LEN
    # OT: period 5 starts at 4*720 = 2880s, each OT is 300s
    return 4 * _PERIOD_LEN + (period - 5) * _OT_LEN


def _period_len(period: int) -> int:
    return _OT_LEN if period > 4 else _PERIOD_LEN


def load_pbp(game_id: str) -> list[dict]:
    """Load all cached per-period PBP events for a game."""
    events: list[dict] = []
    for q in range(1, 9):  # up to 4 OT periods
        path = os.path.join(NBA_CACHE, f"pbp_{game_id}_p{q}.json")
        if not os.path.exists(path):
            break
        with open(path) as f:
            events.extend(json.load(f))
    return events


def build_timeline(events: list[dict]) -> dict:
    """
    Build dense per-second lookup arrays from PBP events.

    Returns dict with numpy arrays indexed by absolute game_sec:
        period, score_home, score_away, shot_clock_est
    """
    # Find max game second
    max_sec = max(
        _period_start_sec(e["period"]) + e["game_clock_sec"]
        for e in events
    )
    n = max_sec + 1

    period_arr  = np.zeros(n, dtype=np.int8)
    sh_arr      = np.zeros(n, dtype=np.int16)
    sa_arr      = np.zeros(n, dtype=np.int16)
    sc_arr      = np.full(n, _DEFAULT_SC, dtype=np.float32)

    # Sort events chronologically
    events_sorted = sorted(
        events,
        key=lambda e: _period_start_sec(e["period"]) + e["game_clock_sec"]
    )

    # Fill period array: each second gets its quarter number
    for e in events_sorted:
        abs_sec = _period_start_sec(e["period"]) + e["game_clock_sec"]
        period_arr[abs_sec] = e["period"]

    # Forward-fill period (seconds between events inherit the period)
    cur_period = 1
    for i in range(n):
        if period_arr[i] > 0:
            cur_period = int(period_arr[i])
        period_arr[i] = cur_period

    # Fill score arrays: forward-fill from score-carrying events
    cur_sh, cur_sa = 0, 0
    for e in events_sorted:
        score_str = e.get("score", "")
        if score_str and "-" in score_str:
            parts = score_str.split("-")
            try:
                cur_sh = int(parts[0])
                cur_sa = int(parts[1])
            except ValueError:
                pass
        abs_sec = _period_start_sec(e["period"]) + e["game_clock_sec"]
        sh_arr[abs_sec] = cur_sh
        sa_arr[abs_sec] = cur_sa

    # Forward-fill score arrays
    for i in range(1, n):
        if sh_arr[i] == 0 and sa_arr[i] == 0 and i > 0:
            sh_arr[i] = sh_arr[i - 1]
            sa_arr[i] = sa_arr[i - 1]

    # Shot clock: resets to 24 on possession-starting events, then decrements
    # Possession-starting events: made FG (1), turnover (5), foul (6),
    # end-of-period (13), jump ball (10), violation (7)
    _SC_RESET_TYPES = {1, 5, 6, 7, 10, 13}
    _SC_RESET_OREB  = {4}  # offensive rebound -> 14s reset (post-2018 rule)

    # Build list of (abs_sec, reset_value)
    sc_resets: list[tuple[int, float]] = [(0, _DEFAULT_SC)]
    for e in events_sorted:
        ev = e.get("event_type", 0)
        abs_sec = _period_start_sec(e["period"]) + e["game_clock_sec"]
        if ev in _SC_RESET_TYPES:
            sc_resets.append((abs_sec, _DEFAULT_SC))
        elif ev in _SC_RESET_OREB:
            # Only treat as 14s reset if it's an offensive rebound
            desc = e.get("event_desc", "").lower()
            if "off" in desc or "offensive" in desc:
                sc_resets.append((abs_sec, 14.0))

    # Fill shot_clock array by interpolating between resets
    sc_resets.append((n, _DEFAULT_SC))  # sentinel
    for i in range(len(sc_resets) - 1):
        reset_sec, reset_val = sc_resets[i]
        next_reset_sec, _ = sc_resets[i + 1]
        for s in range(reset_sec, min(next_reset_sec, n)):
            elapsed = s - reset_sec
            sc_arr[s] = max(0.0, reset_val - elapsed)

    return {
        "period":     period_arr,
        "score_home": sh_arr,
        "score_away": sa_arr,
        "shot_clock": sc_arr,
        "max_sec":    max_sec,
    }


# ---------------------------------------------------------------------------
# Clip offset detection
# ---------------------------------------------------------------------------

def detect_clip_offset(
    shot_log_path: str,
    pbp_events: list[dict],
    fps: float,
    max_game_sec: int,
    clip_duration_sec: float,
) -> float:
    """
    Find clip_start_sec by maximising CV-shot <-> PBP-shot matches.

    Vectorised numpy search over 0.5s steps; returns best offset.
    Falls back to 0.0 if shot_log is empty or has no made shots.
    """
    if not os.path.exists(shot_log_path):
        return 0.0

    shots_df = pd.read_csv(shot_log_path)
    made = shots_df[shots_df["made"] == 1.0]["timestamp"].dropna().values
    if len(made) == 0:
        made = shots_df["timestamp"].dropna().values
    if len(made) == 0:
        return 0.0

    pbp_made_ts = np.array(sorted(
        _period_start_sec(e["period"]) + e["game_clock_sec"]
        for e in pbp_events if e["event_type"] == 1
    ), dtype=np.float64)
    if len(pbp_made_ts) == 0:
        return 0.0

    max_offset = max(0, max_game_sec - int(clip_duration_sec))
    offsets = np.arange(0, max_offset + 1, 0.5)
    print(f"  Searching {len(offsets)} offsets (0 - {max_offset}s)...")

    # Vectorised: for each offset, compute min distance from each CV shot to any PBP shot
    # Shape: (n_offsets, n_cv_shots)
    shifted = made[np.newaxis, :] + offsets[:, np.newaxis]  # (n_offsets, n_cv)
    # For each shifted shot, find min distance to any PBP shot
    # Shape: (n_offsets, n_cv, n_pbp) -> min over pbp axis
    diffs = np.abs(shifted[:, :, np.newaxis] - pbp_made_ts[np.newaxis, np.newaxis, :])
    min_dists = diffs.min(axis=2)  # (n_offsets, n_cv)
    match_counts = (min_dists <= _SHOT_WINDOW).sum(axis=1)  # (n_offsets,)

    best_idx = int(np.argmax(match_counts))
    best_offset = float(offsets[best_idx])
    best_count = int(match_counts[best_idx])
    print(f"  Best offset: {best_offset}s -> {best_count}/{len(made)} shots matched")
    return best_offset


# ---------------------------------------------------------------------------
# Team color mapping
# ---------------------------------------------------------------------------

def resolve_team_colors(
    shot_log_path: str,
    pbp_events: list[dict],
    clip_offset: float,
    manifest: dict,
) -> dict[str, str]:
    """
    Determine which jersey color (green/white) maps to which team abbreviation.

    Strategy: For CV made shots matched to PBP made shots, check what team
    the PBP attributes the shot to. Build a vote table and take the majority.
    Falls back to manifest home/away if no votes.
    """
    if not os.path.exists(shot_log_path):
        return {}

    shots_df = pd.read_csv(shot_log_path)
    made = shots_df[shots_df["made"] == 1.0].copy()
    if made.empty:
        return {}

    pbp_made = [
        e for e in pbp_events if e["event_type"] == 1 and e.get("team_abbrev")
    ]

    votes: dict[str, dict[str, int]] = {}  # color -> {abbrev: count}

    for _, row in made.iterrows():
        ts = float(row["timestamp"]) + clip_offset
        color = str(row.get("team", "")).strip()
        if not color:
            continue
        # Find matching PBP event
        best_ev, best_dt = None, _SHOT_WINDOW + 1
        for ev in pbp_made:
            ev_ts = _period_start_sec(ev["period"]) + ev["game_clock_sec"]
            dt = abs(ev_ts - ts)
            if dt < best_dt:
                best_dt = dt
                best_ev = ev
        if best_ev and best_dt <= _SHOT_WINDOW:
            abbrev = best_ev["team_abbrev"]
            if color not in votes:
                votes[color] = {}
            votes[color][abbrev] = votes[color].get(abbrev, 0) + 1

    home = manifest.get("home", "")
    away = manifest.get("away", "")

    # Build vote-based map
    vote_map: dict[str, str] = {}
    for color, counts in votes.items():
        best_abbrev = max(counts, key=counts.get)
        vote_map[color] = best_abbrev
        print(f"  Color '{color}' -> {best_abbrev} (votes: {counts})")

    # Sanity-check: both colors must map to DIFFERENT teams.
    # If ambiguous (tie or both same), fall back to NBA convention:
    #   white = home team, any non-white color = away team.
    color_map: dict[str, str] = {}
    mapped_teams = set(vote_map.values())
    if len(mapped_teams) < len(vote_map) or (home and away and mapped_teams == {home} or mapped_teams == {away}):
        print(f"  Ambiguous votes -- using NBA convention: white={home}, non-white={away}")
        for color in vote_map:
            color_map[color] = home if color == "white" else away
    else:
        color_map = vote_map

    # Fill any missing colors seen in tracking data
    if home and away:
        for color in ["white", "green", "blue", "red", "black", "gray"]:
            if color not in color_map:
                color_map[color] = home if color == "white" else away

    return color_map


# ---------------------------------------------------------------------------
# Per-game processing
# ---------------------------------------------------------------------------

def process_game(game_id: str, skip_features: bool = False, backup_features: bool = False) -> None:
    print(f"\n{'='*60}")
    print(f"Game: {game_id}")

    # Load PBP
    events = load_pbp(game_id)
    if not events:
        print(f"  No PBP cache found -- skipping")
        return
    print(f"  PBP events: {len(events)}")

    timeline = build_timeline(events)
    max_sec   = int(timeline["max_sec"])

    # Load manifest
    manifest_path = os.path.join(GAMES_DIR, game_id, "manifest.json")
    manifest: dict = {}
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
    print(f"  Home: {manifest.get('home','?')}  Away: {manifest.get('away','?')}")

    tracking_dir = os.path.join(TRACKING_DIR, game_id)
    shot_log_path = os.path.join(tracking_dir, "shot_log.csv")
    features_path = os.path.join(tracking_dir, "features.csv")
    ball_path     = os.path.join(tracking_dir, "ball_tracking.csv")

    # Infer FPS from ball_tracking or features
    fps = 30.0
    if os.path.exists(ball_path):
        bt = pd.read_csv(ball_path, usecols=["frame", "timestamp"]).dropna()
        if len(bt) > 1 and bt["timestamp"].max() > 0:
            fps = round(bt["frame"].max() / bt["timestamp"].max(), 2)
    print(f"  FPS: {fps}")

    # Infer clip duration
    clip_duration = 0.0
    if os.path.exists(ball_path):
        bt = pd.read_csv(ball_path, usecols=["timestamp"]).dropna()
        clip_duration = float(bt["timestamp"].max())
    print(f"  Clip duration: {clip_duration:.1f}s")

    # --- 1. Detect clip offset ---
    clip_offset = detect_clip_offset(
        shot_log_path, events, fps, max_sec, clip_duration
    )
    print(f"  Clip offset: {clip_offset}s "
          f"(clip covers game seconds {clip_offset:.0f} - {clip_offset+clip_duration:.0f})")

    # --- 2. Resolve team colors ---
    print("  Resolving team colors...")
    color_map = resolve_team_colors(shot_log_path, events, clip_offset, manifest)
    if color_map:
        colors_path = os.path.join(tracking_dir, "team_colors.json")
        with open(colors_path, "w") as f:
            json.dump(color_map, f, indent=2)
        print(f"  Written: team_colors.json -> {color_map}")
    else:
        print("  Could not resolve team colors")

    # --- 3. Update shot_log: player_name, team_abbrev, pbp_game_clock ---
    if os.path.exists(shot_log_path):
        _patch_shot_log(shot_log_path, events, clip_offset, color_map)

    # --- 4. Write game_context.csv ---
    if os.path.exists(ball_path):
        _write_game_context(game_id, tracking_dir, timeline, fps, clip_offset, clip_duration)

    # --- 5. Patch features.csv columns ---
    if not skip_features and os.path.exists(features_path):
        _patch_features(features_path, timeline, fps, clip_offset, color_map,
                        backup=backup_features)
    elif skip_features:
        print("  features.csv patch skipped (--skip-features)")

    print(f"  Done: {game_id}")


def _game_sec_to_context(abs_sec: int, timeline: dict) -> tuple[int, int, int, float]:
    """Return (period, score_home, score_away, shot_clock) for a game second."""
    idx = max(0, min(abs_sec, int(timeline["max_sec"])))
    return (
        int(timeline["period"][idx]),
        int(timeline["score_home"][idx]),
        int(timeline["score_away"][idx]),
        float(timeline["shot_clock"][idx]),
    )


def _patch_shot_log(
    shot_log_path: str,
    events: list[dict],
    clip_offset: float,
    color_map: dict[str, str],
) -> None:
    """Add player_name, team_abbrev, pbp_game_clock to shot_log.csv."""
    shots_df = pd.read_csv(shot_log_path)
    if shots_df.empty:
        return

    fg_events = [e for e in events if e["event_type"] in (1, 2)]

    def _match_shot(row):
        ts = float(row.get("timestamp", 0)) + clip_offset
        best_ev, best_dt = None, _SHOT_WINDOW + 1
        for ev in fg_events:
            ev_ts = _period_start_sec(ev["period"]) + ev["game_clock_sec"]
            dt = abs(ev_ts - ts)
            if dt < best_dt:
                best_dt = dt
                best_ev = ev
        if best_ev and best_dt <= _SHOT_WINDOW:
            return pd.Series({
                "player_name":    best_ev.get("player_name", ""),
                "team_abbrev":    best_ev.get("team_abbrev", ""),
                "pbp_game_clock": _period_start_sec(best_ev["period"]) + best_ev["game_clock_sec"],
            })
        color = str(row.get("team", ""))
        return pd.Series({
            "player_name":    "",
            "team_abbrev":    color_map.get(color, "UNK"),
            "pbp_game_clock": None,
        })

    matched = shots_df.apply(_match_shot, axis=1)
    shots_df["player_name"]    = matched["player_name"]
    shots_df["team_abbrev"]    = matched["team_abbrev"]
    shots_df["pbp_game_clock"] = matched["pbp_game_clock"]

    # Apply color_map to team column if team_abbrev still blank
    if color_map:
        mask = shots_df["team_abbrev"].isin(["", "UNK"])
        shots_df.loc[mask, "team_abbrev"] = (
            shots_df.loc[mask, "team"].map(color_map).fillna("UNK")
        )

    shutil.copy2(shot_log_path, shot_log_path + ".bak3")
    shots_df.to_csv(shot_log_path, index=False)

    named   = (shots_df["player_name"] != "").sum()
    abbrevs = shots_df["team_abbrev"].value_counts().to_dict()
    print(f"  shot_log: {named}/{len(shots_df)} player_names resolved, team_abbrevs: {abbrevs}")


def _write_game_context(
    game_id: str,
    tracking_dir: str,
    timeline: dict,
    fps: float,
    clip_offset: float,
    clip_duration: float,
) -> None:
    """Write game_context.csv: one row per second of the clip."""
    rows = []
    for sec in range(int(clip_duration) + 1):
        game_sec = int(sec + clip_offset)
        period, sh, sa, sc = _game_sec_to_context(game_sec, timeline)
        # Nearest frame at this second
        frame_approx = int(sec * fps)
        rows.append({
            "frame_approx":    frame_approx,
            "video_sec":       sec,
            "game_clock_sec":  game_sec,
            "period":          period,
            "score_home":      sh,
            "score_away":      sa,
            "score_margin":    sh - sa,
            "shot_clock_est":  round(sc, 1),
        })
    out_path = os.path.join(tracking_dir, "game_context.csv")
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"  Written: game_context.csv ({len(rows)} rows)")


def _patch_features(
    features_path: str,
    timeline: dict,
    fps: float,
    clip_offset: float,
    color_map: dict[str, str],
    backup: bool = False,
) -> None:
    """Overwrite scoreboard_period, scoreboard_score_diff, shot_clock_est in features.csv."""
    tmp_path = features_path + ".patching"
    chunk_size = 500_000
    first_chunk = True
    total_rows = 0

    file_mb = os.path.getsize(features_path) / 1024 / 1024
    print(f"  Patching features.csv ({file_mb:.0f} MB, chunked {chunk_size//1000}K rows)...")

    for chunk in pd.read_csv(features_path, chunksize=chunk_size, low_memory=False):
        if "frame" not in chunk.columns:
            print("  features.csv has no 'frame' column -- skipping")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return
        if "timestamp" in chunk.columns:
            video_sec = chunk["timestamp"].astype(float)
        else:
            video_sec = chunk["frame"].astype(float) / fps

        game_sec = (video_sec + clip_offset).clip(0, timeline["max_sec"]).astype(int).values

        chunk["scoreboard_period"]     = timeline["period"][game_sec]
        chunk["scoreboard_score_diff"] = (
            timeline["score_home"][game_sec].astype(int) -
            timeline["score_away"][game_sec].astype(int)
        )
        chunk["shot_clock_est"] = np.round(timeline["shot_clock"][game_sec], 1)

        if color_map and "team" in chunk.columns and "team_abbrev" in chunk.columns:
            unk_mask = chunk["team_abbrev"].isin(["UNK", "", None]) | chunk["team_abbrev"].isna()
            chunk.loc[unk_mask, "team_abbrev"] = (
                chunk.loc[unk_mask, "team"].map(color_map).fillna("UNK")
            )

        chunk.to_csv(tmp_path, mode="a" if not first_chunk else "w",
                     header=first_chunk, index=False)
        first_chunk = False
        total_rows += len(chunk)
        print(f"    {total_rows:,} rows written...", flush=True)

    if os.path.exists(tmp_path):
        if backup:
            shutil.copy2(features_path, features_path + ".bak")
        os.replace(tmp_path, features_path)
        print(f"  features.csv patched: {total_rows:,} rows")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", nargs="*", help="Game IDs (default: all with PBP cache)")
    parser.add_argument("--skip-features", action="store_true",
                        help="Skip patching features.csv (faster, use when only shot_log matters)")
    parser.add_argument("--backup-features", action="store_true",
                        help="Back up features.csv before patching (adds time for large files)")
    args = parser.parse_args()

    if args.game:
        game_ids = args.game
    else:
        # Auto-discover: any game_id that has pbp_*_p1.json cached
        game_ids = []
        for fname in os.listdir(NBA_CACHE):
            if fname.startswith("pbp_") and fname.endswith("_p1.json"):
                gid = fname[len("pbp_"):-len("_p1.json")]
                if os.path.isdir(os.path.join(TRACKING_DIR, gid)):
                    game_ids.append(gid)
        game_ids = sorted(set(game_ids))

    print(f"Processing {len(game_ids)} game(s): {game_ids}")
    for gid in game_ids:
        try:
            process_game(gid, skip_features=args.skip_features,
                         backup_features=args.backup_features)
        except Exception as e:
            print(f"  ERROR on {gid}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
