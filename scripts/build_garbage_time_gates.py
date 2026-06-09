"""
INT-56: Garbage-Time Gating Signal (F3)
D2 rule: PBP-based, per-game blowout gate for filtering garbage-time minutes.

INFRASTRUCTURE NOTE: Opus expects ~0% marginal MAE improvement because
minutes_played in form features already handles bench-heavy noise. This
parquet is INFRASTRUCTURE for a future consumer, NOT a ship candidate.
"""

import json
import re
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PBP_DIR = ROOT / "data" / "nba"
OUT_DIR = ROOT / "data" / "intelligence"
LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)
log = logging.getLogger("build_garbage_time_gates")


# ---------------------------------------------------------------------------
# Pre-built player-id resolution lookups (loaded once at module level)
# ---------------------------------------------------------------------------

def _build_player_id_lookups() -> Tuple[Dict, Dict]:
    """
    Build two lookup dicts for resolving PBP last_name -> player_id:

    per_game_lookup : {(game_id, last_name): player_id}
        Built from player_adv_stats.parquet (covers 22/23/24 seasons).
        Only includes unambiguous cases where exactly ONE player_id has
        that last_name in that game.

    global_fallback : {last_name: player_id}
        Built from player_positions.parquet.
        Only includes last names that are globally unique across all 850 players.
    """
    per_game: Dict = {}
    global_fb: Dict = {}

    # --- player_positions global fallback ---
    pos_path = ROOT / "data" / "player_positions.parquet"
    if pos_path.exists():
        try:
            df_pos = pd.read_parquet(pos_path)
            df_pos["last_name"] = df_pos["display_name"].str.split().str.get(-1)
            counts = df_pos["last_name"].value_counts()
            unique_lasts = counts[counts == 1].index
            global_fb = (
                df_pos[df_pos["last_name"].isin(unique_lasts)]
                .set_index("last_name")["player_id"]
                .to_dict()
            )
            log.info("global_fallback: %d unique-last-name entries", len(global_fb))
        except Exception as exc:
            log.warning("Could not load player_positions for global fallback: %s", exc)
    else:
        log.warning("player_positions.parquet not found; global fallback disabled")

    # --- per-game lookup from player_adv_stats ---
    adv_path = ROOT / "data" / "player_adv_stats.parquet"
    if adv_path.exists() and pos_path.exists():
        try:
            df_adv = pd.read_parquet(adv_path, columns=["player_id", "game_id"])
            df_pos2 = pd.read_parquet(pos_path, columns=["player_id", "display_name"])
            df_pos2["last_name"] = df_pos2["display_name"].str.split().str.get(-1)
            merged = df_adv.merge(df_pos2[["player_id", "last_name"]], on="player_id", how="left")
            merged = merged.dropna(subset=["last_name"])
            # Keep only (game_id, last_name) combos with exactly one player_id
            cnts = merged.groupby(["game_id", "last_name"])["player_id"].nunique()
            uniq_idx = cnts[cnts == 1].index
            # Get first occurrence of each unambiguous (game_id, last_name) pair
            per_game_df = (
                merged.drop_duplicates(subset=["game_id", "last_name"])
                .set_index(["game_id", "last_name"])["player_id"]
                .loc[uniq_idx]
            )
            per_game = per_game_df.to_dict()
            log.info("per_game_lookup: %d (game_id, last_name) -> player_id entries", len(per_game))
        except Exception as exc:
            log.warning("Could not build per_game_lookup from player_adv_stats: %s", exc)
    else:
        log.warning("player_adv_stats.parquet not found; per-game lookup disabled")

    return per_game, global_fb


# Load lookups once at import time
_PER_GAME_LOOKUP: Dict = {}
_GLOBAL_FALLBACK: Dict = {}


def _ensure_lookups_loaded() -> None:
    """Lazily populate module-level lookup dicts on first call."""
    global _PER_GAME_LOOKUP, _GLOBAL_FALLBACK
    if not _PER_GAME_LOOKUP and not _GLOBAL_FALLBACK:
        _PER_GAME_LOOKUP, _GLOBAL_FALLBACK = _build_player_id_lookups()


def resolve_player_id(game_id: str, last_name: str, roster_map: Dict) -> Optional[int]:
    """
    Resolve a PBP last_name token to a player_id using three sources in priority order:
      1. roster_map from boxscore (exact, highest quality)
      2. per_game_lookup from player_adv_stats (per-game unambiguous)
      3. global_fallback from player_positions (globally unique last names)
    Returns player_id (int) or None if unresolvable.
    """
    # 1. Boxscore roster (may be keyed by last token of full name)
    info = roster_map.get(last_name)
    if info:
        pid = info.get("player_id")
        if pid and int(pid) > 0:
            return int(pid)

    # 2. Per-game lookup
    pid = _PER_GAME_LOOKUP.get((game_id, last_name))
    if pid:
        return int(pid)

    # 3. Global fallback
    pid = _GLOBAL_FALLBACK.get(last_name)
    if pid:
        return int(pid)

    return None


GT_DEF_VERSION = "D2_v1"
BUILD_DATE = str(date.today())

# ---------------------------------------------------------------------------
# Home-team lookup from schedule files
# ---------------------------------------------------------------------------

def build_home_team_lookup() -> Dict[str, str]:
    """Return {game_id: home_team_abbrev} from all schedule json files."""
    sched_dir = PBP_DIR / "schedule"
    lookup: Dict[str, str] = {}
    if not sched_dir.exists():
        log.warning("Schedule dir missing; home_team will be 'UNK' for all games")
        return lookup

    for fp in sched_dir.glob("schedule_*_v2.json"):
        # filename: schedule_ATL_2022-23_v2.json
        parts = fp.stem.split("_")
        if len(parts) < 2:
            continue
        team = parts[1]
        try:
            records = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for rec in records:
            gid = str(rec.get("game_id", ""))
            is_home = bool(rec.get("home", False))
            if is_home and gid and gid not in lookup:
                lookup[gid] = team
    log.info("Home-team lookup: %d game_ids", len(lookup))
    return lookup


def build_game_date_lookup() -> Dict[str, str]:
    """Return {game_id: date_str} from schedule files."""
    sched_dir = PBP_DIR / "schedule"
    lookup: Dict[str, str] = {}
    if not sched_dir.exists():
        return lookup
    for fp in sched_dir.glob("schedule_*_v2.json"):
        try:
            records = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for rec in records:
            gid = str(rec.get("game_id", ""))
            dt = str(rec.get("date", ""))
            if gid and dt and gid not in lookup:
                lookup[gid] = dt
    return lookup


# ---------------------------------------------------------------------------
# Boxscore roster loader
# ---------------------------------------------------------------------------

def load_boxscore_roster(game_id: str) -> Tuple[Dict[str, dict], Dict[str, str]]:
    """
    Returns:
      roster_map: {last_name -> player dict with keys player_id, player_name, team, starter}
      starters: {team_abbrev -> set of last_name}

    Handles two boxscore schema versions:
      - Old (22/23/24 early): has "starter" boolean field
      - New (24/25+): has "start_position" string field ("F"/"G"/"C"/"" for bench)

    The boxscore is looked up in PBP_DIR (data/nba/).
    If no boxscore file exists, returns ({}, {}) — caller falls back to
    per_game_lookup / global_fallback for player_id resolution.
    """
    bs_path = PBP_DIR / f"boxscore_{game_id}.json"
    if not bs_path.exists():
        return {}, {}

    try:
        data = json.loads(bs_path.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}

    players = data.get("players", [])
    roster_map: Dict[str, dict] = {}
    starters: Dict[str, set] = {}

    for p in players:
        name = p.get("player_name", "")
        team = p.get("team_abbreviation", "")
        pid = p.get("player_id", 0)

        # Detect schema version and resolve starter flag
        if "starter" in p:
            # Old schema: boolean
            is_starter = bool(p["starter"])
        else:
            # New schema: start_position is "F"/"G"/"C" for starters, "" for bench
            start_pos = str(p.get("start_position", "") or "")
            is_starter = len(start_pos) > 0

        # Also require they actually played (min > 0) to be considered a starter
        min_val = p.get("min", None)
        if min_val is not None:
            try:
                # min may be "24:22" string or float
                min_str = str(min_val)
                if ":" in min_str:
                    parts = min_str.split(":")
                    minutes = float(parts[0]) + float(parts[1]) / 60.0
                else:
                    minutes = float(min_str) if min_str else 0.0
                if minutes <= 0:
                    is_starter = False
            except (ValueError, TypeError):
                pass

        last = name.split()[-1] if name else ""
        if last:
            roster_map[last] = {
                "player_id": int(pid) if pid else 0,
                "player_name": name,
                "team": team,
                "starter": is_starter,
            }
            if is_starter:
                starters.setdefault(team, set()).add(last)

    return roster_map, starters


# ---------------------------------------------------------------------------
# PBP loader + score parsing
# ---------------------------------------------------------------------------

def parse_score(score_str: str, home_team_first: bool = True) -> Tuple[int, int]:
    """Parse 'A-B' score string -> (home, away). Format is always home-away."""
    try:
        parts = score_str.split("-")
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except (ValueError, AttributeError):
        pass
    return 0, 0


def load_game_pbp(game_id: str) -> Optional[pd.DataFrame]:
    """Load all available period PBP files and return merged DataFrame sorted by (period, clock)."""
    rows = []
    for period in range(1, 15):  # 1-4 regular + OT up to 10
        fp = PBP_DIR / f"pbp_{game_id}_p{period}.json"
        if not fp.exists():
            if period <= 4:
                return None  # require p1-p4
            break
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            log.warning("Failed to parse %s", fp)
            return None
        rows.extend(data)

    if not rows:
        return None

    df = pd.DataFrame(rows)
    # Ensure required columns exist
    for col in ["period", "game_clock_sec", "event_type", "event_desc",
                "player_name", "team_abbrev", "score", "score_margin"]:
        if col not in df.columns:
            df[col] = "" if col in ("event_desc", "player_name", "team_abbrev", "score", "score_margin") else 0

    df["period"] = pd.to_numeric(df["period"], errors="coerce").fillna(0).astype(int)
    df["game_clock_sec"] = pd.to_numeric(df["game_clock_sec"], errors="coerce").fillna(0).astype(float)
    df["event_type"] = pd.to_numeric(df["event_type"], errors="coerce").fillna(-1).astype(int)

    df = df.sort_values(["period", "game_clock_sec"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Score forward-fill and margin computation
# ---------------------------------------------------------------------------

def build_running_scores(df: pd.DataFrame, home_team: str) -> pd.DataFrame:
    """
    Parse score column into (score_home, score_away), forward-fill blanks.
    score_margin in PBP is unsigned absolute, so we derive leading_team from score.
    """
    df = df.copy()
    # Parse score string where format is "home-away"
    scores = df["score"].astype(str).str.split("-", expand=True)
    df["score_home"] = pd.to_numeric(scores[0], errors="coerce")
    df["score_away"] = pd.to_numeric(scores[1], errors="coerce")

    # Forward-fill: carry last known score forward
    df["score_home"] = df["score_home"].ffill().fillna(0).astype(int)
    df["score_away"] = df["score_away"].ffill().fillna(0).astype(int)

    df["margin_abs"] = (df["score_home"] - df["score_away"]).abs().astype(int)

    # leading_team: home_team if home > away, else derive from event context
    df["leading_team"] = home_team  # default
    mask_away_leads = df["score_away"] > df["score_home"]
    mask_tied = df["score_home"] == df["score_away"]
    # We need the away team — take from team_abbrev of non-home events if possible
    # For now mark TIED / home_team / away
    # We'll fill away_team properly using the two distinct team_abbrevs seen
    teams = df.loc[df["team_abbrev"].str.len() == 3, "team_abbrev"].unique()
    away_team = next((t for t in teams if t != home_team), "AWAY")

    df.loc[mask_away_leads, "leading_team"] = away_team
    df.loc[mask_tied, "leading_team"] = "TIED"

    return df, home_team, away_team


# ---------------------------------------------------------------------------
# D2 Garbage-time rule
# ---------------------------------------------------------------------------

def compute_clock_rem(period: int, game_clock_sec: float) -> float:
    """Seconds remaining in period. PBP clock = seconds elapsed in period."""
    if period <= 4:
        return max(0.0, 720.0 - game_clock_sec)
    else:
        return max(0.0, 300.0 - game_clock_sec)


def apply_d2_rule(df: pd.DataFrame) -> pd.DataFrame:
    """Apply D2 garbage-time rule row-wise; returns df with is_garbage_time_raw column."""
    df = df.copy()
    periods = df["period"].values
    clocks = df["game_clock_sec"].values
    margins = df["margin_abs"].values

    n = len(df)
    gt_raw = np.zeros(n, dtype=bool)

    for i in range(n):
        p = int(periods[i])
        clk = float(clocks[i])
        m = int(margins[i])
        rem = compute_clock_rem(p, clk)

        if p == 4:
            if (m >= 20 and rem <= 360) or (m >= 25 and rem <= 720) or (m >= 30):
                gt_raw[i] = True
        elif p == 3:
            if m >= 30 and rem <= 180:
                gt_raw[i] = True
        # OT: do not flag (garbage-time in OT is rare and anomalous)

    df["is_garbage_time_raw"] = gt_raw
    return df


def apply_no_comeback_sanity(df: pd.DataFrame) -> pd.DataFrame:
    """
    Forward-scan sanity: if margin drops below 15 after a GT-flagged row
    before end of game, retroactively flip is_garbage_time=False for all
    rows before and up to that comeback event.
    """
    df = df.copy()
    gt = df["is_garbage_time_raw"].values.copy()
    margins = df["margin_abs"].values
    n = len(df)

    # Find the last index where margin < 15 in Q4 / OT
    periods = df["period"].values
    last_comeback_idx = -1
    for i in range(n):
        if periods[i] >= 4 and margins[i] < 15:
            last_comeback_idx = i

    if last_comeback_idx >= 0:
        # Flip everything before that point to False
        gt[:last_comeback_idx + 1] = False

    df["is_garbage_time"] = gt
    return df


# ---------------------------------------------------------------------------
# GT segment entry/exit tracking
# ---------------------------------------------------------------------------

def compute_entry_exit(df: pd.DataFrame) -> pd.DataFrame:
    """Add gt_entry_clock_sec and gt_exit_clock_sec columns."""
    df = df.copy()
    df["gt_entry_clock_sec"] = np.nan
    df["gt_exit_clock_sec"] = np.nan

    gt = df["is_garbage_time"].values
    clocks = df["game_clock_sec"].values
    periods = df["period"].values
    n = len(df)

    in_gt = False
    for i in range(n):
        if gt[i] and not in_gt:
            df.at[i, "gt_entry_clock_sec"] = clocks[i]
            in_gt = True
        elif not gt[i] and in_gt:
            df.at[i - 1, "gt_exit_clock_sec"] = clocks[i - 1]
            in_gt = False

    if in_gt:
        df.at[n - 1, "gt_exit_clock_sec"] = clocks[n - 1]

    return df


# ---------------------------------------------------------------------------
# Player on-floor tracker
# ---------------------------------------------------------------------------

SUB_RE = re.compile(r"SUB:\s*(\S+.*?)\s+FOR\s+(\S+.*?)$", re.IGNORECASE)


def track_player_minutes(
    df: pd.DataFrame,
    game_id: str,
    game_date: str,
    home_team: str,
    away_team: str,
    roster_map: Dict[str, dict],
    starters: Dict[str, set],
) -> pd.DataFrame:
    """
    Walk PBP rows; track on-floor players per team via SUB events.
    Compute minutes_played_total, minutes_in_gt, gt_entry_count.
    Attribute in-GT stats to player_name.
    Returns per-(game_id, player_id) aggregate DataFrame.
    """
    # Initialise on-floor roster from boxscore starters
    # Format: {team_abbrev: set of last_names}
    on_floor: Dict[str, set] = {}
    for team, s_set in starters.items():
        # Take the first 5 starters per team
        on_floor[team] = set(list(s_set)[:5])

    # If starters not in boxscore, initialise empty
    if home_team not in on_floor:
        on_floor[home_team] = set()
    if away_team not in on_floor:
        on_floor[away_team] = set()

    # Per-player accumulators
    # key: last_name, value: dict of stats
    player_stats: Dict[str, dict] = {}

    def get_player(last_name: str, team: str) -> dict:
        if last_name not in player_stats:
            # Resolve player_id: boxscore roster first, then per-game lookup, then global fallback
            pid = resolve_player_id(game_id, last_name, roster_map)
            info = roster_map.get(last_name, {})
            player_stats[last_name] = {
                # Use NaN (not 0) when player_id cannot be resolved — consumers can filter
                "player_id": pid if pid is not None else float("nan"),
                "player_name": info.get("player_name", last_name),
                "team": info.get("team", team),
                "primary_starter_flag": bool(info.get("starter", False)),
                "minutes_played_total": 0.0,
                "minutes_in_gt": 0.0,
                "gt_entry_count": 0,
                "points_in_gt": 0,
                "fga_in_gt": 0,
                "fgm_in_gt": 0,
                "ast_in_gt": 0,
                "reb_in_gt": 0,
                "tov_in_gt": 0,
                "stl_in_gt": 0,
                "blk_in_gt": 0,
                "fg3m_in_gt": 0,
                "_in_gt": False,
            }
        return player_stats[last_name]

    def all_on_floor():
        result = {}
        for team, players in on_floor.items():
            for last in players:
                result[last] = team
        return result

    prev_clock = 0.0
    prev_period = 1
    prev_gt = False
    n_sub_fail = 0
    n_sub_total = 0

    for idx, row in df.iterrows():
        period = int(row["period"])
        clock = float(row["game_clock_sec"])
        evt = int(row["event_type"])
        desc = str(row["event_desc"])
        player = str(row.get("player_name", ""))
        team = str(row.get("team_abbrev", ""))
        gt = bool(row["is_garbage_time"])

        # Compute time delta (clock increases within period)
        if period == prev_period:
            dt_sec = max(0.0, clock - prev_clock)
        else:
            # Period boundary — accumulate remainder of old period
            if prev_period <= 4:
                dt_sec = max(0.0, 720.0 - prev_clock)
            else:
                dt_sec = max(0.0, 300.0 - prev_clock)
            prev_clock = 0.0

        dt_min = dt_sec / 60.0

        # Accumulate time to on-floor players
        current_floor = all_on_floor()
        for last, plr_team in current_floor.items():
            p = get_player(last, plr_team)
            p["minutes_played_total"] += dt_min
            if prev_gt:
                p["minutes_in_gt"] += dt_min

        # Track GT entry counts
        if gt and not prev_gt:
            for last in list(current_floor.keys()):
                get_player(last, current_floor[last])["gt_entry_count"] += 1

        # Handle substitution (event_type=8)
        if evt == 8:
            n_sub_total += 1
            m = SUB_RE.match(desc)
            if m:
                enters_last = m.group(1).strip().split()[-1]  # last name
                exits_last = m.group(2).strip().split()[-1]
                sub_team = team if team in on_floor else None
                if sub_team:
                    if exits_last in on_floor[sub_team]:
                        on_floor[sub_team].discard(exits_last)
                    on_floor[sub_team].add(enters_last)
                    # Ensure both players exist in tracker
                    get_player(enters_last, sub_team)
                    get_player(exits_last, sub_team)
                else:
                    n_sub_fail += 1
            else:
                n_sub_fail += 1

        # Attribute stats for GT events
        if gt and player:
            last = player.split()[-1] if player else ""
            if last:
                p = get_player(last, team)
                # Made FG (event_type=1)
                if evt == 1:
                    p["fgm_in_gt"] += 1
                    p["fga_in_gt"] += 1
                    # Points from desc
                    pts_m = re.search(r"\((\d+)\s*PTS\)", desc)
                    if pts_m:
                        pass  # We'll count below via FT logic
                    # Check for 3-pointer
                    if "3PT" in desc or "3-pointer" in desc.lower() or "3pt" in desc.lower():
                        p["fg3m_in_gt"] += 1
                    # crude points: 3 if 3pt else 2
                    if "3PT" in desc or "3-pointer" in desc.lower():
                        p["points_in_gt"] += 3
                    else:
                        p["points_in_gt"] += 2
                # Missed FG (event_type=2)
                elif evt == 2:
                    p["fga_in_gt"] += 1
                # Free throw (event_type=3)
                elif evt == 3:
                    if "MISS" not in desc.upper():
                        p["points_in_gt"] += 1
                # Rebound (event_type=4)
                elif evt == 4:
                    p["reb_in_gt"] += 1
                # Turnover (event_type=5)
                elif evt == 5:
                    p["tov_in_gt"] += 1
                # Assist: detected from made FG desc "X (N AST)"
                # event_type=1 desc like "Tatum 3PT Jump Shot (37 PTS 10 AST)"
                # We parse AST from desc on made FG
                elif evt == 1:
                    ast_m = re.search(r"\(.*?(\d+)\s*AST\)", desc)
                    if ast_m:
                        # The assister is NOT the scorer — look for "(N AST)" pattern
                        pass

        # AST: separate pass — event_type=1 (made FG) desc often contains assister
        # Format: "Tatum 3PT Jump Shot (5 PTS) (Holiday 1 AST)" — assister in parentheses
        if gt and evt == 1:
            ast_m = re.search(r"\((\w+)\s+\d+\s*AST\)", desc)
            if ast_m:
                assister_last = ast_m.group(1)
                # determine team from on_floor
                ast_team = current_floor.get(assister_last, team)
                get_player(assister_last, ast_team)["ast_in_gt"] += 1

        # STL: event_type=6 with "STEAL" in desc, player_name = stealer
        if gt and evt == 6 and "STEAL" in desc.upper():
            last = player.split()[-1] if player else ""
            if last:
                get_player(last, team)["stl_in_gt"] += 1

        # BLK: event_type=0 with "BLOCK" in desc
        if gt and evt == 0 and "BLOCK" in desc.upper():
            last = player.split()[-1] if player else ""
            if last:
                get_player(last, team)["blk_in_gt"] += 1

        prev_clock = clock
        prev_period = period
        prev_gt = gt

    parse_failure_rate = n_sub_fail / n_sub_total if n_sub_total > 0 else 0.0
    if n_sub_total > 0 and parse_failure_rate > 0.15:
        log.warning(
            "game %s: sub parse failure rate %.1f%% (%d/%d) — minute attribution degraded",
            game_id, 100 * parse_failure_rate, n_sub_fail, n_sub_total
        )

    # Compute per-game player_id resolution rate for quality column
    n_total_players = len(player_stats)
    n_resolved = sum(
        1 for p in player_stats.values()
        if p["player_id"] is not None and not (isinstance(p["player_id"], float) and np.isnan(p["player_id"]))
    )
    pid_resolve_rate = n_resolved / n_total_players if n_total_players > 0 else 0.0

    # Build DataFrame
    records = []
    for last, p in player_stats.items():
        total = p["minutes_played_total"]
        gt_min = p["minutes_in_gt"]
        records.append({
            "game_id": game_id,
            "game_date": game_date,
            "player_id": p["player_id"],
            "player_name": p["player_name"],
            "team": p["team"],
            "minutes_played_total": round(total, 3),
            "minutes_in_gt": round(gt_min, 3),
            "pct_minutes_in_gt": round(gt_min / total, 4) if total > 0 else 0.0,
            "gt_entry_count": p["gt_entry_count"],
            "primary_starter_flag": p["primary_starter_flag"],
            "points_in_gt": p["points_in_gt"],
            "fga_in_gt": p["fga_in_gt"],
            "fgm_in_gt": p["fgm_in_gt"],
            "ast_in_gt": p["ast_in_gt"],
            "reb_in_gt": p["reb_in_gt"],
            "tov_in_gt": p["tov_in_gt"],
            "stl_in_gt": p["stl_in_gt"],
            "blk_in_gt": p["blk_in_gt"],
            "fg3m_in_gt": p["fg3m_in_gt"],
            # Quality columns: consumer can filter games with high failure rate
            "parse_failure_rate": round(parse_failure_rate, 4),
            "pid_resolve_rate": round(pid_resolve_rate, 4),
        })

    if not records:
        return pd.DataFrame()

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Per-game processing
# ---------------------------------------------------------------------------

def process_game(
    game_id: str,
    home_team: str,
    game_date: str,
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Returns (segments_df, player_agg_df) or (None, None) on failure.
    """
    df = load_game_pbp(game_id)
    if df is None:
        return None, None

    df, ht, at = build_running_scores(df, home_team)
    df["clock_rem"] = df.apply(
        lambda r: compute_clock_rem(int(r["period"]), float(r["game_clock_sec"])), axis=1
    )

    df = apply_d2_rule(df)
    df = apply_no_comeback_sanity(df)
    df = compute_entry_exit(df)

    # Build segments parquet rows
    seg_cols = [
        "period", "game_clock_sec", "clock_rem",
        "score_home", "score_away", "margin_abs", "leading_team",
        "is_garbage_time", "gt_entry_clock_sec", "gt_exit_clock_sec",
    ]
    seg_df = df[seg_cols].copy()
    seg_df.insert(0, "game_id", game_id)

    # Player aggregation
    roster_map, starters = load_boxscore_roster(game_id)
    player_df = track_player_minutes(df, game_id, game_date, ht, at, roster_map, starters)

    return seg_df, player_df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Building player-id resolution lookups...")
    _ensure_lookups_loaded()

    log.info("Building home-team and game-date lookups...")
    home_lookup = build_home_team_lookup()
    date_lookup = build_game_date_lookup()

    # Discover games: require p1.json (p2-p4 checked inside load_game_pbp)
    p1_files = sorted(PBP_DIR.glob("pbp_*_p1.json"))
    game_ids = []
    for fp in p1_files:
        gid = fp.stem[4:-3]  # strip "pbp_" prefix and "_p1" suffix
        # Only process numeric game IDs (00XXXXXXX format)
        if gid.startswith("00") and gid.isdigit():
            game_ids.append(gid)

    log.info("Discovered %d numeric game IDs with p1 file", len(game_ids))

    all_segments: List[pd.DataFrame] = []
    all_player_agg: List[pd.DataFrame] = []

    n_ok = 0
    n_with_segments = 0
    n_fail = 0

    for i, gid in enumerate(game_ids):
        if i % 200 == 0:
            log.info("Processing game %d / %d ...", i, len(game_ids))

        home_team = home_lookup.get(gid, "UNK")
        game_date = date_lookup.get(gid, "")

        try:
            seg_df, player_df = process_game(gid, home_team, game_date)
        except Exception as e:
            log.warning("game %s failed: %s", gid, e)
            n_fail += 1
            continue

        if seg_df is None:
            n_fail += 1
            continue

        n_ok += 1

        has_gt = bool(seg_df["is_garbage_time"].any())
        if has_gt:
            n_with_segments += 1

        all_segments.append(seg_df)
        if player_df is not None and not player_df.empty:
            all_player_agg.append(player_df)

    log.info(
        "Processed: %d OK, %d failed. GT segments present: %d / %d (%.1f%%)",
        n_ok, n_fail, n_with_segments, n_ok,
        100 * n_with_segments / n_ok if n_ok else 0,
    )

    if n_with_segments / max(n_ok, 1) < 0.80:
        log.warning(
            "Coverage below 80%%: only %d/%d games have GT segments",
            n_with_segments, n_ok
        )

    # Concatenate and write
    if not all_segments:
        log.error("No segment data produced. Aborting.")
        sys.exit(1)

    seg_out = pd.concat(all_segments, ignore_index=True)
    seg_out["build_date"] = BUILD_DATE
    seg_out["n_games"] = n_ok
    seg_out["gt_definition_version"] = GT_DEF_VERSION

    seg_path = OUT_DIR / "garbage_time_segments.parquet"
    seg_out.to_parquet(seg_path, index=False)
    log.info("Wrote %s: %d rows, %d cols", seg_path, len(seg_out), len(seg_out.columns))

    if all_player_agg:
        plr_out = pd.concat(all_player_agg, ignore_index=True)
        plr_out["build_date"] = BUILD_DATE
        plr_out["gt_definition_version"] = GT_DEF_VERSION

        plr_path = OUT_DIR / "garbage_time_player_aggregates.parquet"
        plr_out.to_parquet(plr_path, index=False)
        log.info("Wrote %s: %d rows, %d cols", plr_path, len(plr_out), len(plr_out.columns))
    else:
        log.warning("No player aggregate data produced.")
        plr_out = pd.DataFrame()

    # ---------------------------------------------------------------------------
    # Build-only QA
    # ---------------------------------------------------------------------------
    log.info("\n=== BUILD QA ===")

    if not plr_out.empty and "pct_minutes_in_gt" in plr_out.columns:
        pct = plr_out["pct_minutes_in_gt"]
        med = pct.median()
        p95 = pct.quantile(0.95)
        p99 = pct.quantile(0.99)
        log.info("pct_minutes_in_gt: median=%.4f  p95=%.4f  p99=%.4f", med, p95, p99)

        # Sanity checks
        if not (0 <= med <= 0.05):
            log.warning("Median pct_minutes_in_gt=%.4f expected near 0", med)
        if not (0.10 <= p95 <= 0.35):
            log.warning("p95 pct_minutes_in_gt=%.4f expected in [0.10, 0.30]", p95)
        if p99 < 0.40:
            log.warning("p99 pct_minutes_in_gt=%.4f expected >= 0.40", p99)

    # Spot-check 5 random games with GT segments
    gt_games = seg_out[seg_out["is_garbage_time"]]["game_id"].unique()
    if len(gt_games) >= 5:
        import random
        random.seed(42)
        sample_ids = random.sample(list(gt_games), 5)
        log.info("Spot-check games: %s", sample_ids)
        for gid in sample_ids:
            g = seg_out[(seg_out["game_id"] == gid) & (seg_out["is_garbage_time"])]
            min_period = g["period"].min()
            max_margin = g["margin_abs"].max()
            gt_count = len(g)
            log.info(
                "  game %s: GT rows=%d, min_period=%d, max_margin=%d",
                gid, gt_count, min_period, max_margin
            )
            if min_period < 3:
                log.warning("  WARN: GT in period %d (expected >=3)", min_period)
            if max_margin < 20:
                log.warning("  WARN: max GT margin=%d (expected >=20)", max_margin)

    # Known-blowout check: final_margin >= 30 should have >= 5 min GT
    if not plr_out.empty:
        # Use final scores from segments
        final_margins = (
            seg_out.sort_values(["game_id", "period", "game_clock_sec"])
            .groupby("game_id")
            .last()["margin_abs"]
        )
        blowout_ids = final_margins[final_margins >= 30].index.tolist()
        if blowout_ids:
            plr_blowout = plr_out[plr_out["game_id"].isin(blowout_ids)]
            blowout_gt_min = plr_blowout.groupby("game_id")["minutes_in_gt"].sum()
            n_sufficient = (blowout_gt_min >= 5).sum()
            log.info(
                "Blowout games (final margin>=30): %d total, %d have >=5 total GT player-minutes (%.1f%%)",
                len(blowout_ids), n_sufficient,
                100 * n_sufficient / len(blowout_ids) if blowout_ids else 0,
            )

    log.info("=== DONE ===")
    log.info("Segments parquet: %s (%d rows)", seg_path, len(seg_out))
    if not plr_out.empty:
        log.info("Player agg parquet: %s (%d rows)", plr_path, len(plr_out))


if __name__ == "__main__":
    main()
