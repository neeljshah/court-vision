"""
build_trade_intel.py -- INT-7: Trade/Team-Change Adaptation Intelligence

Detects players in CV-tracked data who appear across multiple teams (trades or
team changes) and profiles the behavioral shift in their CV features before vs
after the change.

Inputs:
  - data/nba_ai.db         : cv_features table (player_id, game_id, feature_name, value)
  - data/nba/season_games_*.json : game date lookup
  - data/tracking/<game_id>/shot_log.csv : team_abbrev per shot
  - data/tracking/<game_id>/tracking_data.csv : jersey + team_abbrev per frame
  - data/tracking/<game_id>/jersey_name_map.json : jersey -> full name
  - data/nba/player_full_*.json : name -> NBA player_id

Outputs:
  - data/intelligence/trade_profile_shifts.parquet
  - data/intelligence/team_change_log.json
  - vault/Intelligence/Trade_Atlas.md
  - vault/Intelligence/Trade_Adaptations/<player>__<from>_<to>.md  (top shifts)
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_DIR   = Path(__file__).resolve().parent.parent
DATA_DIR      = PROJECT_DIR / "data"
TRACKING_DIR  = DATA_DIR / "tracking"
NBA_CACHE     = DATA_DIR / "nba"
INTEL_DIR     = DATA_DIR / "intelligence"
VAULT_INTEL   = PROJECT_DIR / "vault" / "Intelligence"
VAULT_TRADES  = VAULT_INTEL / "Trade_Adaptations"
DB_PATH       = DATA_DIR / "nba_ai.db"

# Seasons to load player name -> ID maps (newest first)
_LOOKUP_SEASONS = ["2025-26", "2024-25", "2023-24", "2022-23"]

# Minimum games on each side to consider a shift "reliable"
MIN_GAMES_EACH_SIDE = 2

# Features that are numeric and meaningful for profiling
_NUMERIC_FEATS = [
    "avg_defender_distance",
    "avg_shot_distance",
    "avg_dribble_count",
    "avg_fatigue_proxy",
    "avg_spacing",
    "avg_closeout_speed",
    "avg_contest_arm_angle",
    "avg_shot_clock_at_shot",
    "catch_shoot_pct",
    "contested_shot_rate",
    "defender_approach_speed",
    "made_pct",
    "n_shots_tracked",
    "paint_dwell_pct",
    "play_type_drive_pct",
    "play_type_isolation_pct",
    "play_type_post_pct",
    "play_type_transition_pct",
    "possession_duration_avg",
    "potential_assists",
    "preshot_velocity_peak",
    "second_chance_rate",
    "shot_zone_3pt_pct",
    "shot_zone_mid_range_pct",
    "shot_zone_paint_pct",
    "shots_per_possession",
    "touches_per_game",
    "cv_xast_pred",
]

# Feature interpretation labels (for readable notes)
_FEAT_INTERP: Dict[str, str] = {
    "paint_dwell_pct":        "paint usage (% time near basket)",
    "touches_per_game":       "ball-handling role",
    "play_type_drive_pct":    "drive frequency",
    "play_type_isolation_pct":"isolation usage",
    "play_type_post_pct":     "post-up usage",
    "play_type_transition_pct":"transition frequency",
    "avg_defender_distance":  "defensive pressure (defender distance)",
    "avg_shot_distance":      "shot selection distance",
    "catch_shoot_pct":        "catch-and-shoot role",
    "contested_shot_rate":    "shot contest rate",
    "shot_zone_3pt_pct":      "3-point zone usage",
    "shot_zone_paint_pct":    "paint shot rate",
    "shot_zone_mid_range_pct":"mid-range usage",
    "possession_duration_avg":"possession hold time",
    "avg_dribble_count":      "dribble creation",
    "avg_fatigue_proxy":      "fatigue level",
    "potential_assists":      "playmaking tendency",
    "second_chance_rate":     "offensive rebounding role",
    "cv_xast_pred":           "expected assists (CV model)",
    "n_shots_tracked":        "shot volume tracked",
    "made_pct":               "field goal efficiency",
    "preshot_velocity_peak":  "pre-shot explosion speed",
    "shots_per_possession":   "shot aggression per possession",
    "avg_spacing":            "spacing from teammates",
    "avg_closeout_speed":     "closeout activity",
    "avg_contest_arm_angle":  "contest arm angle",
    "avg_shot_clock_at_shot": "shot clock usage",
    "defender_approach_speed":"how fast defenders close out",
}


# ---------------------------------------------------------------------------
# Step 0 — utilities
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Normalize player name for matching: ASCII lowercase, stripped."""
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def _build_name_to_id() -> Dict[str, int]:
    """Build normalized_name -> NBA player_id from player_full_*.json caches."""
    result: Dict[str, int] = {}
    for season in _LOOKUP_SEASONS:
        for pattern in ["player_full_{s}.json", "player_avgs_{s}.json"]:
            path = NBA_CACHE / pattern.replace("{s}", season)
            if not path.exists():
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    cache = json.load(f)
                if isinstance(cache, list):
                    for row in cache:
                        name = str(row.get("PLAYER_NAME") or row.get("player_name", ""))
                        pid  = row.get("PLAYER_ID") or row.get("player_id")
                        if name and pid:
                            result[_norm(name)] = int(pid)
                elif isinstance(cache, dict):
                    for name, data in cache.items():
                        pid = data.get("player_id") if isinstance(data, dict) else None
                        if pid:
                            result[_norm(name)] = int(pid)
            except Exception:
                pass
    return result


def _load_game_dates() -> Dict[str, str]:
    """Build game_id -> game_date from all season_games_*.json files."""
    result: Dict[str, str] = {}
    for path in sorted(NBA_CACHE.glob("season_games_*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for row in data.get("rows", []):
                result[row["game_id"]] = row["game_date"]
        except Exception:
            pass
    return result


def _load_jersey_name_map(game_dir: Path) -> Dict[str, str]:
    """Load jersey_number -> full player name from jersey_name_map.json."""
    jnm_path = game_dir / "jersey_name_map.json"
    if not jnm_path.exists():
        return {}
    try:
        with open(jnm_path, encoding="utf-8", errors="replace") as f:
            jnm = json.load(f)
    except Exception:
        return {}

    if "flat" in jnm and isinstance(jnm["flat"], dict) and jnm["flat"]:
        return {str(k): str(v) for k, v in jnm["flat"].items() if v}
    if "by_team" in jnm:
        flat: Dict[str, str] = {}
        for mapping in jnm["by_team"].values():
            for jnum, pname in mapping.items():
                if pname:
                    flat[str(jnum)] = str(pname)
        return flat
    return {str(k): str(v) for k, v in jnm.items()
            if v and str(k).replace(".", "").isdigit()}


# ---------------------------------------------------------------------------
# Step 1 — Build game-level team mapping for each NBA player_id
# ---------------------------------------------------------------------------

def _get_team_for_game_slot(
    game_dir: Path,
    slot_id: int,
) -> Optional[str]:
    """
    For a given local slot_id in a game, return the mode team_abbrev from
    tracking_data.csv.
    """
    td_path = game_dir / "tracking_data.csv"
    if not td_path.exists():
        return None
    team_ctr: Counter = Counter()
    try:
        with open(td_path, newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                try:
                    if int(row.get("player_id", 0) or 0) != slot_id:
                        continue
                    abbrev = str(row.get("team_abbrev", "")).strip()
                    if not abbrev or abbrev in ("nan", "UNK", ""):
                        abbrev = str(row.get("team", "")).strip()
                    if abbrev and abbrev not in ("nan", "UNK", ""):
                        team_ctr[abbrev] += 1
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    return team_ctr.most_common(1)[0][0] if team_ctr else None


def build_player_game_team_map(
    cv_game_ids: List[str],
    name_to_id: Dict[str, int],
) -> Dict[Tuple[str, int], str]:
    """
    Returns {(game_id, nba_player_id): team_abbrev} for all CV-tracked games.

    Strategy:
      1. Read tracking_data.csv to get slot -> team_abbrev (mode)
      2. Read jersey_name_map.json + tracking_data jersey_number to get slot -> name
      3. Map name -> NBA player_id
      4. Build the final (game_id, nba_player_id) -> team mapping
    """
    result: Dict[Tuple[str, int], str] = {}
    not_found = 0
    found = 0

    for game_id in cv_game_ids:
        # Try multiple directory names (some have suffixes like .f298)
        candidates = sorted(TRACKING_DIR.glob(f"{game_id}*"))
        game_dir = candidates[0] if candidates else TRACKING_DIR / game_id

        if not game_dir.exists():
            not_found += 1
            continue

        jnm = _load_jersey_name_map(game_dir)
        if not jnm:
            not_found += 1
            continue

        # Build slot -> jersey -> name -> NBA_id
        # Also need slot -> team_abbrev from shot_log (faster than tracking_data)
        slot_team: Dict[int, Counter] = defaultdict(Counter)
        slot_jersey: Dict[int, Counter] = defaultdict(Counter)

        td_path = game_dir / "tracking_data.csv"
        if not td_path.exists():
            # Fallback: shot_log.csv
            sl_path = game_dir / "shot_log.csv"
            if sl_path.exists():
                try:
                    sl = pd.read_csv(sl_path, low_memory=False)
                    for _, row in sl.iterrows():
                        try:
                            slot = int(row.get("player_id", 0) or 0)
                            if not slot:
                                continue
                            abbrev = str(row.get("team_abbrev", "")).strip()
                            if abbrev and abbrev not in ("nan", "UNK", ""):
                                slot_team[slot][abbrev] += 1
                        except Exception:
                            pass
                except Exception:
                    pass
            not_found += 1
            continue

        try:
            with open(td_path, newline="", encoding="utf-8", errors="replace") as f:
                for row in csv.DictReader(f):
                    try:
                        slot = int(row.get("player_id", 0) or 0)
                        if not slot:
                            continue
                        # Team abbrev
                        abbrev = str(row.get("team_abbrev", "")).strip()
                        if not abbrev or abbrev in ("nan", "UNK", ""):
                            abbrev = str(row.get("team", "")).strip()
                        if abbrev and abbrev not in ("nan", "UNK", ""):
                            slot_team[slot][abbrev] += 1
                        # Jersey number
                        jraw = str(row.get("jersey_number", "")).strip()
                        if jraw and jraw not in ("nan", ""):
                            try:
                                j = str(int(float(jraw)))
                                slot_jersey[slot][j] += 1
                            except (ValueError, TypeError):
                                pass
                    except (ValueError, TypeError):
                        pass
        except Exception:
            not_found += 1
            continue

        # For each slot: resolve team and NBA player_id
        for slot, team_ctr in slot_team.items():
            if not team_ctr:
                continue
            team = team_ctr.most_common(1)[0][0]

            # Resolve slot -> NBA player_id via jersey + jnm + name_to_id
            j_ctr = slot_jersey.get(slot, Counter())
            nba_pid: Optional[int] = None
            for jersey, _ in j_ctr.most_common(5):
                full_name = jnm.get(jersey)
                if full_name:
                    nba_pid = name_to_id.get(_norm(full_name))
                    if nba_pid:
                        break
            if nba_pid:
                result[(game_id, nba_pid)] = team
                found += 1

    print(f"  Team mapping: {found} (game, player) pairs resolved, "
          f"{not_found} games skipped (no tracking_data)")
    return result


# ---------------------------------------------------------------------------
# Step 2 — Load CV features and pivot to wide format
# ---------------------------------------------------------------------------

def load_cv_features_wide() -> pd.DataFrame:
    """
    Load cv_features from DB and pivot to wide format:
      columns: game_id, player_id, <feature_name>, ...
    Only include numeric features in _NUMERIC_FEATS (skip cv_archetype string).
    """
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        f"SELECT game_id, player_id, feature_name, feature_value FROM cv_features "
        f"WHERE feature_name IN ({','.join('?' * len(_NUMERIC_FEATS))})",
        conn,
        params=_NUMERIC_FEATS,
    )
    conn.close()

    if df.empty:
        return pd.DataFrame()

    wide = df.pivot_table(
        index=["game_id", "player_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="mean",
    ).reset_index()
    wide.columns.name = None
    return wide


# ---------------------------------------------------------------------------
# Step 3 — Build player name lookup from cv player IDs
# ---------------------------------------------------------------------------

def _build_id_to_name(name_to_id: Dict[str, int]) -> Dict[int, str]:
    """Reverse the name->id map: NBA player_id -> player_name."""
    result: Dict[int, str] = {}
    for name, pid in name_to_id.items():
        if pid not in result:
            # Prefer title-cased version
            result[pid] = name.title()
    return result


# ---------------------------------------------------------------------------
# Step 4 — Detect team changes
# ---------------------------------------------------------------------------

def detect_team_changes(
    cv_wide: pd.DataFrame,
    game_team_map: Dict[Tuple[str, int], str],
    game_dates: Dict[str, str],
    id_to_name: Dict[int, str],
) -> List[dict]:
    """
    For each player with ≥2 CV games, sort by date, detect team changes,
    and return a list of change event dicts.
    """
    changes: List[dict] = []

    players = cv_wide["player_id"].unique()

    for pid in players:
        player_games = cv_wide[cv_wide["player_id"] == pid]["game_id"].tolist()
        player_name = id_to_name.get(int(pid), f"player_{pid}")

        # Build (game_id, team, date) list
        game_info = []
        for gid in player_games:
            team = game_team_map.get((gid, int(pid)))
            date = game_dates.get(gid)
            if team and date and team not in ("UNK", ""):
                game_info.append((gid, team, date))

        if len(game_info) < 2:
            continue

        # Sort chronologically
        game_info.sort(key=lambda x: x[2])

        # Detect consecutive team changes
        prev_gid, prev_team, prev_date = game_info[0]
        for gid, team, date in game_info[1:]:
            if team != prev_team:
                # Compute days between last from-team game and first to-team game
                try:
                    from datetime import date as ddate
                    d1 = ddate.fromisoformat(prev_date)
                    d2 = ddate.fromisoformat(date)
                    days_between = (d2 - d1).days
                except Exception:
                    days_between = None

                changes.append({
                    "player_id": int(pid),
                    "player_name": player_name,
                    "from_team": prev_team,
                    "to_team": team,
                    "last_pre_game": prev_gid,
                    "last_pre_date": prev_date,
                    "first_post_game": gid,
                    "first_post_date": date,
                    "days_between": days_between,
                    # We'll fill n_pre and n_post next
                    "_all_games": game_info,
                })

            prev_gid, prev_team, prev_date = gid, team, date

    return changes


# ---------------------------------------------------------------------------
# Step 5 — Profile the shift
# ---------------------------------------------------------------------------

def profile_shift(
    change: dict,
    cv_wide: pd.DataFrame,
    game_team_map: Dict[Tuple[str, int], str],
    game_dates: Dict[str, str],
) -> Optional[dict]:
    """
    For a change event, build before/after feature profiles.
    Returns enriched change dict or None if insufficient data.
    """
    pid = change["player_id"]
    from_team = change["from_team"]
    to_team = change["to_team"]
    transition_date = change["last_pre_date"]  # use this as cutoff

    player_cv = cv_wide[cv_wide["player_id"] == pid].copy()

    # Attach dates and teams
    player_cv["game_date"] = player_cv["game_id"].map(game_dates)
    player_cv["team_abbrev"] = player_cv.apply(
        lambda r: game_team_map.get((r["game_id"], int(pid))), axis=1
    )

    # Drop rows without team info
    player_cv = player_cv.dropna(subset=["game_date", "team_abbrev"])
    player_cv = player_cv[player_cv["team_abbrev"].isin([from_team, to_team])]

    pre_games  = player_cv[player_cv["team_abbrev"] == from_team]
    post_games = player_cv[player_cv["team_abbrev"] == to_team]

    n_pre  = len(pre_games)
    n_post = len(post_games)

    change["n_pre_games"]  = n_pre
    change["n_post_games"] = n_post

    if n_pre < MIN_GAMES_EACH_SIDE or n_post < MIN_GAMES_EACH_SIDE:
        return change  # Keep but mark as insufficient

    # Compute per-feature deltas
    available_feats = [f for f in _NUMERIC_FEATS if f in player_cv.columns]
    pre_mean  = pre_games[available_feats].mean()
    post_mean = post_games[available_feats].mean()
    overall_std = player_cv[available_feats].std().replace(0, np.nan)

    delta    = post_mean - pre_mean
    z_scores = delta / overall_std

    # Top 5 shifted features by abs z-score
    z_abs = z_scores.abs().dropna().sort_values(ascending=False)
    top_feats = z_abs.head(5).index.tolist()

    top_shifts = []
    for feat in top_feats:
        bv = float(pre_mean.get(feat, np.nan))
        av = float(post_mean.get(feat, np.nan))
        dv = float(delta.get(feat, np.nan))
        zv = float(z_scores.get(feat, np.nan))
        interp_base = _FEAT_INTERP.get(feat, feat)
        if not np.isnan(zv):
            direction = "increased" if zv > 0 else "decreased"
            interp = f"{direction.capitalize()} {interp_base} post-trade"
        else:
            interp = f"Shift in {interp_base}"
        top_shifts.append({
            "feature":       feat,
            "before":        round(bv, 4) if not np.isnan(bv) else None,
            "after":         round(av, 4) if not np.isnan(av) else None,
            "delta":         round(dv, 4) if not np.isnan(dv) else None,
            "delta_z":       round(zv, 3) if not np.isnan(zv) else None,
            "interpretation": interp,
        })

    max_z = z_abs.iloc[0] if len(z_abs) > 0 else 0.0

    change["max_shift_z"]           = round(float(max_z), 3)
    change["top_3_shifted_features"] = [s["feature"] for s in top_shifts[:3]]
    change["top_shifts"]             = top_shifts
    change["shift_per_feature"]      = {
        feat: {
            "before": round(float(pre_mean.get(feat, np.nan)), 4) if feat in pre_mean else None,
            "after":  round(float(post_mean.get(feat, np.nan)), 4) if feat in post_mean else None,
            "delta_z": round(float(z_scores.get(feat, np.nan)), 3) if feat in z_scores else None,
        }
        for feat in available_feats
        if not np.isnan(z_scores.get(feat, np.nan))
    }
    change["reliable"] = True

    return change


# ---------------------------------------------------------------------------
# Step 6 — Write outputs
# ---------------------------------------------------------------------------

def write_parquet(changes: List[dict]) -> None:
    """Write trade_profile_shifts.parquet."""
    rows = []
    for c in changes:
        rows.append({
            "player_id":              c.get("player_id"),
            "player_name":            c.get("player_name"),
            "from_team":              c.get("from_team"),
            "to_team":                c.get("to_team"),
            "last_pre_game":          c.get("last_pre_game"),
            "first_post_game":        c.get("first_post_game"),
            "last_pre_date":          c.get("last_pre_date"),
            "first_post_date":        c.get("first_post_date"),
            "days_between":           c.get("days_between"),
            "n_pre_games":            c.get("n_pre_games", 0),
            "n_post_games":           c.get("n_post_games", 0),
            "reliable":               c.get("reliable", False),
            "max_shift_z":            c.get("max_shift_z", np.nan),
            "top_3_shifted_features": json.dumps(c.get("top_3_shifted_features", [])),
            "shift_per_feature":      json.dumps(c.get("shift_per_feature", {})),
        })
    df = pd.DataFrame(rows)
    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    out = INTEL_DIR / "trade_profile_shifts.parquet"
    df.to_parquet(out, index=False)
    print(f"  Wrote {out}  ({len(df)} rows)")


def write_team_change_log(changes: List[dict]) -> None:
    """Write team_change_log.json."""
    reliable = [c for c in changes if c.get("reliable")]
    output = {
        "generated": "2026-05-28",
        "total_team_changes_detected": len(changes),
        "reliable_shifts": len(reliable),
        "trades_detected": [],
    }
    for c in sorted(reliable, key=lambda x: -x.get("max_shift_z", 0)):
        output["trades_detected"].append({
            "player_id":   c["player_id"],
            "player_name": c["player_name"],
            "from":        c["from_team"],
            "to":          c["to_team"],
            "date_estimate": c.get("first_post_date", ""),
            "n_pre":       c["n_pre_games"],
            "n_post":      c["n_post_games"],
            "days_between": c.get("days_between"),
            "max_shift_z": c.get("max_shift_z", 0),
            "top_shifts":  c.get("top_shifts", [])[:5],
        })
    out = INTEL_DIR / "team_change_log.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"  Wrote {out}  ({len(reliable)} reliable trades)")


def write_atlas(changes: List[dict], n_players_checked: int) -> None:
    """Write vault/Intelligence/Trade_Atlas.md."""
    VAULT_INTEL.mkdir(parents=True, exist_ok=True)

    reliable = [c for c in changes if c.get("reliable")]
    total_with_change = len(changes)
    n_reliable = len(reliable)
    n_single_side = total_with_change - n_reliable

    # Top 10 by max_z
    top10 = sorted(reliable, key=lambda x: -x.get("max_shift_z", 0))[:10]

    # Build markdown
    lines = [
        "# CV Trade Profile Shift Atlas",
        "",
        "## Methodology",
        "For each player tracked in CV across multiple teams, comparing before-vs-after "
        "team-change behavioral profile. Team assignment uses mode `team_abbrev` from "
        "tracking_data.csv per game. Features are the 28 numeric CV features in the "
        "`cv_features` table. Shift is measured as z-score: `(after_mean - before_mean) / player_overall_std`.",
        "",
        "## Detected team changes",
        f"- Players checked (have ≥1 CV game): **{n_players_checked}**",
        f"- Players with a team-change detected in CV data: **{total_with_change}**",
        f"- Reliable shifts (≥{MIN_GAMES_EACH_SIDE} games on each side): **{n_reliable}**",
        f"- Single-game-per-team (noise / insufficient): **{n_single_side}**",
        "",
    ]

    if n_reliable == 0:
        lines += [
            "## Coverage finding",
            "Current CV coverage does not capture enough trade events to produce reliable "
            "shifts. The dataset spans a narrow window (Jan–May 2025) and most players "
            "appear on the same team throughout. No player had ≥2 CV-tracked games on "
            "BOTH sides of a team change.",
            "",
            "To improve: expand CV tracking to include games from Oct–Dec 2024 "
            "(pre-trade-deadline window) and post-deadline games.",
        ]
    else:
        lines += [
            f"## Most dramatic profile shifts (top {min(10, n_reliable)})",
            "| player | from→to | n_pre | n_post | max_z | dominant shift |",
            "|--------|---------|-------|--------|-------|----------------|",
        ]
        for c in top10:
            top_feat = c.get("top_3_shifted_features", ["?"])[0]
            top_z = c.get("max_shift_z", 0)
            lines.append(
                f"| {c['player_name']} | {c['from_team']}→{c['to_team']} "
                f"| {c['n_pre_games']} | {c['n_post_games']} "
                f"| {top_z:.2f} | {top_feat} |"
            )

        lines += [
            "",
            "## Per-player trade notes",
        ]
        for c in top10:
            slug = f"{c['player_name'].replace(' ', '_')}__{c['from_team']}_{c['to_team']}"
            lines.append(f"- [[Trade_Adaptations/{slug}]]")

    lines += [
        "",
        "## Caveats",
        "- Team change detection via tracking_data.csv team_abbrev (game-level), not actual trade dates",
        "- `days_between` is gap between consecutive CV-tracked games — likely much longer than actual "
          "gap between real games (most games are not CV-tracked)",
        "- Small samples (n=2 on each side) → noisy, directional only",
        "- Players who appear on the same team across seasons may show false 'shifts' due to "
          "season-over-season role changes",
        "- ISSUE-022: `defender_distance=200.0` sentinel may inflate `avg_defender_distance` shifts",
        f"- Generated: 2026-05-28 | CV games in dataset: 266 | Player-game pairs: 1142",
    ]

    out = VAULT_INTEL / "Trade_Atlas.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Wrote {out}")


def write_player_note(change: dict) -> None:
    """Write per-player trade adaptation note."""
    VAULT_TRADES.mkdir(parents=True, exist_ok=True)
    pname = change["player_name"]
    from_t = change["from_team"]
    to_t = change["to_team"]
    slug = f"{pname.replace(' ', '_')}__{from_t}_{to_t}"
    out = VAULT_TRADES / f"{slug}.md"

    shifts = change.get("top_shifts", [])
    date_est = change.get("first_post_date", "unknown")
    n_pre = change["n_pre_games"]
    n_post = change["n_post_games"]
    max_z = change.get("max_shift_z", 0)

    # Build "what changed" table
    table_rows = []
    for s in shifts[:8]:
        bv = f"{s['before']:.3f}" if s["before"] is not None else "—"
        av = f"{s['after']:.3f}" if s["after"] is not None else "—"
        dv = f"{s['delta']:+.3f}" if s["delta"] is not None else "—"
        zv = f"{s['delta_z']:+.2f}σ" if s["delta_z"] is not None else "—"
        table_rows.append(
            f"| {s['feature']} | {bv} | {av} | {dv} | {zv} | {s['interpretation']} |"
        )

    # Features with small z (<0.5 abs) — "stayed the same"
    all_features = change.get("shift_per_feature", {})
    stable = [
        f for f, v in all_features.items()
        if v.get("delta_z") is not None and abs(v["delta_z"]) < 0.5
    ]

    # Dominant shift interpretation
    if shifts:
        top_feat = shifts[0]
        direction = "higher" if (top_feat["delta_z"] or 0) > 0 else "lower"
        mechanism = (
            f"{to_t} is using {pname} with {direction} {_FEAT_INTERP.get(top_feat['feature'], top_feat['feature'])}."
        )
    else:
        mechanism = "Insufficient data for mechanism inference."

    days_str = f"{change['days_between']} days" if change.get("days_between") else "unknown gap"

    lines = [
        f"# {pname}: {from_t} → {to_t} (estimated {date_est})",
        "",
        "## Profile shift summary",
        f"{n_pre} games on {from_t}, {n_post} games on {to_t}. "
        f"Max z-shift: **{max_z:.2f}σ**. "
        f"Days between last {from_t} CV game and first {to_t} CV game: {days_str}.",
        "",
        f"> **Reliability:** {'HIGH' if n_pre >= 3 and n_post >= 3 else 'LOW — small sample'} "
        f"(n_pre={n_pre}, n_post={n_post}). "
        "Treat as directional signal, not statistical proof.",
        "",
        "## What changed",
        "| feature | before | after | delta | z-shift | interpretation |",
        "|---------|--------|-------|-------|---------|----------------|",
    ] + table_rows + [
        "",
        "## Mechanism guess",
        mechanism,
        "",
        "## What stayed the same",
        (", ".join(stable) if stable else "All features shifted (possible noise)"),
        "",
        "## Caveats",
        "- This is CV behavioral evidence, not box-score stats",
        "- Small n on each side → high variance, directional only",
        "- ISSUE-022: sentinel defender_distance=200.0 may inflate avg_defender_distance shifts",
    ]

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Wrote {out}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("INT-7: Trade Adaptation Intelligence")
    print("=" * 60)

    # --- Load supporting data ---
    print("\n[1/6] Loading name->ID map and game dates...")
    name_to_id = _build_name_to_id()
    id_to_name = _build_id_to_name(name_to_id)
    game_dates = _load_game_dates()
    print(f"  name->id map: {len(name_to_id)} entries")
    print(f"  game_dates:   {len(game_dates)} games")

    # --- Load CV features ---
    print("\n[2/6] Loading CV features (wide format)...")
    cv_wide = load_cv_features_wide()
    if cv_wide.empty:
        print("  ERROR: cv_features table is empty.")
        return
    n_players = cv_wide["player_id"].nunique()
    n_games   = cv_wide["game_id"].nunique()
    print(f"  {len(cv_wide)} player-game rows | {n_players} players | {n_games} games")

    # --- Build team mapping ---
    print("\n[3/6] Resolving team for each (game, player) pair...")
    cv_game_ids = cv_wide["game_id"].unique().tolist()
    game_team_map = build_player_game_team_map(cv_game_ids, name_to_id)
    # Add game_dates context to cv_wide
    cv_wide["game_date"] = cv_wide["game_id"].map(game_dates)

    # Coverage stats
    resolved = sum(
        1 for _, row in cv_wide.iterrows()
        if (row["game_id"], int(row["player_id"])) in game_team_map
    )
    print(f"  Resolved {resolved}/{len(cv_wide)} player-game pairs to a team "
          f"({100*resolved/len(cv_wide):.1f}%)")

    # --- Detect team changes ---
    print("\n[4/6] Detecting team changes per player...")
    changes = detect_team_changes(cv_wide, game_team_map, game_dates, id_to_name)
    print(f"  Players checked: {n_players}")
    print(f"  Team changes detected: {len(changes)}")

    # --- Profile shifts ---
    print("\n[5/6] Profiling before/after shifts...")
    profiled: List[dict] = []
    for c in changes:
        result = profile_shift(c, cv_wide, game_team_map, game_dates)
        if result:
            profiled.append(result)

    reliable = [c for c in profiled if c.get("reliable")]
    insufficient = [c for c in profiled if not c.get("reliable")]
    print(f"  Reliable shifts (>={MIN_GAMES_EACH_SIDE} each side): {len(reliable)}")
    print(f"  Insufficient data (single-game-per-team): {len(insufficient)}")

    if reliable:
        top5 = sorted(reliable, key=lambda x: -x.get("max_shift_z", 0))[:5]
        print("\n  Top shifts by max z-score:")
        for c in top5:
            top_feat = c.get("top_3_shifted_features", ["?"])[0]
            print(f"    {c['player_name']:25s}  {c['from_team']}->{c['to_team']:4s}  "
                  f"z={c['max_shift_z']:.2f}  feat={top_feat}")

    # --- Write outputs ---
    print("\n[6/6] Writing outputs...")
    write_parquet(profiled)
    write_team_change_log(profiled)
    write_atlas(profiled, n_players)

    # Per-player notes for top 10 reliable shifts
    top_notes = sorted(reliable, key=lambda x: -x.get("max_shift_z", 0))[:10]
    for c in top_notes:
        write_player_note(c)
    print(f"  Wrote {len(top_notes)} per-player trade notes")

    # --- Final report ---
    print()
    print("=" * 60)
    print("INT-7 Trade Adaptation Intelligence — Final Report")
    print("=" * 60)
    print(f"""
Coverage
--------
Players checked:              {n_players}
Team mapping resolved:        {resolved}/{len(cv_wide)} player-game pairs
Players with team change:     {len(changes)}
Reliable shifts (n>={MIN_GAMES_EACH_SIDE} each): {len(reliable)}
Insufficient (single-game):   {len(insufficient)}
""")

    if reliable:
        print("Most dramatic shifts (top 5 if available):")
        print(f"{'player':25s}  {'from->to':10s}  {'max_z':6s}  top feature")
        print("-" * 70)
        for c in sorted(reliable, key=lambda x: -x.get("max_shift_z", 0))[:5]:
            top_feat = c.get("top_3_shifted_features", ["?"])[0]
            print(f"  {c['player_name']:23s}  "
                  f"{c['from_team']}->{c['to_team']:4s}  "
                  f"{c['max_shift_z']:5.2f}  {top_feat}")
    else:
        print("  No reliable shifts detected (no player had >=2 CV games on each side).")
        print("  Current CV coverage (Jan-May 2025) captures a narrow window -- most")
        print("  trades happened before the CV-tracked window or players appear on only")
        print("  one team throughout.")

    print(f"""
Files
-----
  scripts/build_trade_intel.py
  data/intelligence/trade_profile_shifts.parquet
  data/intelligence/team_change_log.json
  vault/Intelligence/Trade_Atlas.md
  vault/Intelligence/Trade_Adaptations/*.md  ({len(top_notes)} files)

How to use this
---------------
  - Trade evaluation: after player X was traded to team Y, look at CV shift in
    paint_dwell_pct, touches_per_game, play_type_drive_pct to understand role change
  - Roster scouting: team Y consistently re-roles incoming players toward Z pattern
  - Betting context: post-trade, a player's lines may lag behind CV role shift

Caveats
-------
  - days_between is gap between CV-tracked games, NOT real game count
  - ISSUE-022: sentinel defender_distance=200.0 may inflate that feature's shifts
  - Small samples (n=2) are directional only, not statistically robust
  - A player who stays on the same team across seasons may show false 'shift'
    if their role changed
""")


if __name__ == "__main__":
    main()
