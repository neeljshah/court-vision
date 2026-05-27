"""Build per-game-per-player quarter-resolved features from quarter_box JSON cache."""
from __future__ import annotations

import json
import logging
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logging.basicConfig(
    format="%(levelname)s %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
QUARTER_BOX_DIR = REPO_ROOT / "data" / "cache" / "quarter_box"
OUTPUT_PATH = REPO_ROOT / "data" / "cache" / "quarter_features.parquet"
GAME_DATE_SRC = REPO_ROOT / "data" / "rest_travel.parquet"


def parse_minutes(min_str: Any) -> float:
    """Convert 'MM:SS' string to float minutes."""
    if not min_str or not isinstance(min_str, str):
        return 0.0
    try:
        parts = str(min_str).strip().split(":")
        if len(parts) == 2:
            return int(parts[0]) + int(parts[1]) / 60.0
        return float(min_str)
    except (ValueError, AttributeError):
        return 0.0


def usage(fga: float, fta: float, to: float) -> float:
    return fga + 0.44 * fta + to


def team_possessions(fga: float, fta: float, oreb: float, to: float) -> float:
    """Proxy: team possessions = fga + 0.44*fta - oreb + to"""
    return max(fga + 0.44 * fta - oreb + to, 1.0)


def load_quarter(path: Path) -> Optional[Dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning("parse error %s: %s", path.name, e)
        return None


def season_from_game_id(game_id: str) -> str:
    try:
        yr = int(game_id[3:5])
        return f"20{yr:02d}-{(yr + 1):02d}"
    except (ValueError, IndexError):
        return "unknown"


def build_game_date_lookup() -> Dict[str, str]:
    df = pd.read_parquet(GAME_DATE_SRC, columns=["game_id", "game_date"])
    return df.drop_duplicates(subset="game_id").set_index("game_id")["game_date"].to_dict()


def process_game(game_id: str, quarters: Dict[int, Dict]) -> List[Dict]:
    """
    Returns one row per player from 4 quarters of data.
    quarters: {1: json_dict, 2: ..., 3: ..., 4: ...}
    """
    # Collect per-quarter player rows keyed by (player_id)
    player_quarters: Dict[int, Dict[int, Dict]] = {}  # player_id -> {q: row}
    # Collect per-quarter team rows keyed by team_id
    team_quarters: Dict[int, Dict[int, Dict]] = {}    # team_id -> {q: row}

    for q in (1, 2, 3, 4):
        data = quarters[q]
        for pr in data.get("players", []):
            pid = pr["player_id"]
            player_quarters.setdefault(pid, {})[q] = pr
        for tr in data.get("teams", []):
            tid = tr["team_id"]
            team_quarters.setdefault(tid, {})[q] = tr

    # ---- team-level aggregates ----

    def team_pts_q(tid: int, q: int) -> float:
        return float(team_quarters.get(tid, {}).get(q, {}).get("pts", 0))

    def team_stat(tid: int, q: int, key: str) -> float:
        return float(team_quarters.get(tid, {}).get(q, {}).get(key, 0))

    # Per-team: halftime_pace_shift and trailing_team tracking
    team_ids = list(team_quarters.keys())

    def team_score_through_q3(tid: int) -> float:
        return team_pts_q(tid, 1) + team_pts_q(tid, 2) + team_pts_q(tid, 3)

    # Determine trailing team at end of Q3
    trailing_team_id: Optional[int] = None
    if len(team_ids) == 2:
        s0 = team_score_through_q3(team_ids[0])
        s1 = team_score_through_q3(team_ids[1])
        if s0 < s1:
            trailing_team_id = team_ids[0]
        elif s1 < s0:
            trailing_team_id = team_ids[1]
        # tied -> no trailing team (NaN)

    # Compute trailing-team Q4 HHI of usage concentration
    trailing_hhi: Optional[float] = None
    if trailing_team_id is not None:
        t_q4_poss = team_possessions(
            team_stat(trailing_team_id, 4, "fga"),
            team_stat(trailing_team_id, 4, "fta"),
            team_stat(trailing_team_id, 4, "oreb"),
            team_stat(trailing_team_id, 4, "to"),
        )
        # Sum squared usage shares for all players on trailing team in Q4
        hhi_sum = 0.0
        players_on_trailing = [
            pid for pid, qmap in player_quarters.items()
            if qmap.get(4, {}).get("team_id") == trailing_team_id
        ]
        for pid in players_on_trailing:
            row4 = player_quarters[pid].get(4, {})
            u = usage(
                float(row4.get("fga", 0)),
                float(row4.get("fta", 0)),
                float(row4.get("to", 0)),
            )
            hhi_sum += (u / t_q4_poss) ** 2
        trailing_hhi = hhi_sum

    # ---- per-player rows ----
    rows = []
    for pid, qmap in player_quarters.items():
        # Need at least 1 quarter to include player
        ref = next(iter(qmap.values()))
        team_id = ref["team_id"]

        def p_stat(q: int, key: str) -> float:
            return float(qmap.get(q, {}).get(key, 0))

        def p_str(q: int, key: str) -> Any:
            return qmap.get(q, {}).get(key, "")

        q1_min = parse_minutes(p_str(1, "min"))
        q2_min = parse_minutes(p_str(2, "min"))
        q3_min = parse_minutes(p_str(3, "min"))
        q4_min = parse_minutes(p_str(4, "min"))
        total_min = max(q1_min + q2_min + q3_min + q4_min, 0.01)

        q1_pts = int(p_stat(1, "pts"))
        q2_pts = int(p_stat(2, "pts"))
        q3_pts = int(p_stat(3, "pts"))
        q4_pts = int(p_stat(4, "pts"))
        total_pts = q1_pts + q2_pts + q3_pts + q4_pts

        # q1_usg
        t_q1_poss = team_possessions(
            team_stat(team_id, 1, "fga"),
            team_stat(team_id, 1, "fta"),
            team_stat(team_id, 1, "oreb"),
            team_stat(team_id, 1, "to"),
        )
        q1_usg = usage(p_stat(1, "fga"), p_stat(1, "fta"), p_stat(1, "to")) / t_q1_poss

        # q3_starter_minutes
        start_pos_q3 = p_str(3, "start_position")
        q3_starter_min: Optional[float] = q3_min if start_pos_q3 != "" else None

        # halftime_pace_shift for this player's team
        h_shift = (
            team_pts_q(team_id, 3) + team_pts_q(team_id, 4)
            - team_pts_q(team_id, 1) - team_pts_q(team_id, 2)
        )

        # trailing_team_q4_usg_concentration
        if team_id == trailing_team_id and trailing_hhi is not None:
            ttq4_usg_conc: Optional[float] = trailing_hhi
        else:
            ttq4_usg_conc = None

        rows.append({
            "game_id": game_id,
            "player_id": pid,
            "player_name": ref.get("player_name", ""),
            "team_id": team_id,
            "q1_usg": round(q1_usg, 6),
            "q3_starter_minutes": q3_starter_min,
            "halftime_pace_shift": float(h_shift),
            "trailing_team_q4_usg_concentration": ttq4_usg_conc,
            "q1_minutes": round(q1_min, 4),
            "q4_minutes": round(q4_min, 4),
            "q1_pts": q1_pts,
            "q2_pts": q2_pts,
            "q3_pts": q3_pts,
            "q4_pts": q4_pts,
            "fourth_quarter_share_pts": round(q4_pts / max(1, total_pts), 6),
            "second_half_share_min": round((q3_min + q4_min) / total_min, 6),
        })
    return rows


def main() -> None:
    # Build game->date lookup
    game_date_map = build_game_date_lookup()
    log.info("Loaded %d game dates from rest_travel.parquet", len(game_date_map))

    # Discover all quarter_box game_ids
    all_q1 = sorted(QUARTER_BOX_DIR.glob("*_q1.json"))
    log.info("Found %d *_q1.json files -> max %d games", len(all_q1), len(all_q1))

    all_rows: List[Dict] = []
    skipped_games = 0

    for q1_path in all_q1:
        game_id = q1_path.name.replace("_q1.json", "")

        # Load all 4 quarters
        quarters: Dict[int, Dict] = {}
        for q in (1, 2, 3, 4):
            p = QUARTER_BOX_DIR / f"{game_id}_q{q}.json"
            if not p.exists():
                break
            data = load_quarter(p)
            if data is None:
                break
            quarters[q] = data

        if len(quarters) < 4:
            log.warning("SKIP %s — only %d quarters cached", game_id, len(quarters))
            skipped_games += 1
            continue

        try:
            rows = process_game(game_id, quarters)
        except Exception as e:
            log.warning("SKIP %s — processing error: %s", game_id, e)
            skipped_games += 1
            continue

        # Attach game_date and season
        game_date = game_date_map.get(game_id, None)
        season = season_from_game_id(game_id)
        for row in rows:
            row["game_date"] = game_date
            row["season"] = season

        all_rows.extend(rows)

    if not all_rows:
        log.error("No rows produced — aborting.")
        sys.exit(1)

    df = pd.DataFrame(all_rows)

    # Enforce dtypes
    int_cols = ["q1_pts", "q2_pts", "q3_pts", "q4_pts"]
    for c in int_cols:
        df[c] = df[c].astype(int)

    # Reorder columns
    col_order = [
        "game_id", "game_date", "season", "player_id", "player_name", "team_id",
        "q1_usg", "q3_starter_minutes", "halftime_pace_shift",
        "trailing_team_q4_usg_concentration",
        "q1_minutes", "q4_minutes",
        "q1_pts", "q2_pts", "q3_pts", "q4_pts",
        "fourth_quarter_share_pts", "second_half_share_min",
    ]
    df = df[col_order]

    # Write output atomically (write to temp then rename)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = OUTPUT_PATH.with_suffix(".tmp.parquet")
    df.to_parquet(tmp_path, index=False, engine="pyarrow")
    tmp_path.replace(OUTPUT_PATH)

    # Report
    total_rows = len(df)
    distinct_gp = df[["game_id", "player_id"]].drop_duplicates().shape[0]
    log.info("=== OUTPUT ===")
    log.info("Rows: %d", total_rows)
    log.info("Distinct (game_id, player_id): %d", distinct_gp)
    log.info("Games skipped (missing quarters): %d", skipped_games)
    log.info("Output: %s", OUTPUT_PATH)

    log.info("--- Null rates ---")
    null_rates = df.isnull().mean().sort_values(ascending=False)
    for col, rate in null_rates.items():
        if rate > 0:
            log.info("  %-45s %.2f%%", col, rate * 100)
    zero_nulls = null_rates[null_rates == 0]
    log.info("  %d columns have 0%% nulls", len(zero_nulls))


if __name__ == "__main__":
    main()
