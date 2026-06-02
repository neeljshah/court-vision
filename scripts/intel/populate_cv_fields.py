#!/usr/bin/env python3
"""populate_cv_fields.py — Join season-aggregate CV behavioral data into the
reserved _cv_fields slots of all atlas_player_*.parquet files.

DESCRIPTIVE INTELLIGENCE ONLY — not a model feature.  Confidence is capped at
"med" because CV data comes from broadcast tracking (pixel-space issues, sparse
n_games).

Unit notes for the mapping table:
  - cvb_avg_dist_to_basket  is in FEET  (uses dist_to_basket_ft columns).
  - cvb_near_basket_pct, cvb_paint_time_pct, cvb_close_to_basket_pct = fractions.
  - cvb_paint_pressure_own/opp = fractions.
  - cvb_jump_frequency = fraction of frames with jump detected.
  - cvb_avg_defender_dist, cvb_avg_spacing, cvb_off_ball_dist, cvb_avg_velocity
    are in PIXEL units — NOT feet or ft/s — so they are conservatively EXCLUDED
    from all atlas slots that declare unit="ft", "ft/s", or "ft²".
  - cvb_contested_shot_pct, cvb_dribbles_per100, cvb_passes_per100,
    cvb_velocity_q4_dropoff, cvb_off_ball_dist_std are all-null in the current
    aggregate and cannot contribute.

Usage:
    python scripts/intel/populate_cv_fields.py
    python scripts/intel/populate_cv_fields.py --as-of 2026-05-31
    python scripts/intel/populate_cv_fields.py --dry-run
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

CV_SRC = ROOT / "data" / "player_cv_per_player.parquet"
ATLAS_GLOB = ROOT / "data" / "cache"

# ---------------------------------------------------------------------------
# Mapping table: atlas slot_name -> cvb_field  (EXACT slot names only)
# Only slots whose unit/semantics genuinely match a non-null cvb_ field.
# Slots left out are documented in UNFILLED_REASONS below.
#
# Rule for dtype="dist": we only have a mean (no p25/p75), so we emit
#   {"mean": <v>, "p25": null, "p75": null}
# For dtype="float": emit the scalar float value.
# ---------------------------------------------------------------------------
SLOT_TO_CVB: dict[str, str] = {
    # --- paint / rim / near-basket fraction slots ---
    # cvb_near_basket_pct  = fraction of frames with player near basket (ft-space)
    # cvb_paint_time_pct   = fraction of frames player is inside paint (ft-space)
    # cvb_close_to_basket_pct = relative quintile fraction (only 9 players have it)
    # cvb_avg_dist_to_basket  = mean distance to basket IN FEET

    # rebounding_profile
    "rebound_distance": "cvb_avg_dist_to_basket",   # mean distance to basket ft
    "vertical": "cvb_jump_frequency",               # jump frequency proxy

    # rebounding_profile: boxout_position = dist dtype, no matching cvb field -> NULL

    # defensive_profile
    # defender_distance_allowed expects ft from defender->matchup distance (pixel-space, excluded)
    # contest_rate expects fraction 0-1 of opponent FGA contested -> cvb_contested_shot_pct all-null
    # closeout_quality composite -> no matching cvb field

    # shot_profile
    # defender_distance_dist expects ft distribution (pixel-space, excluded)
    # contest_level -> cvb_contested_shot_pct all-null
    # dribbles_before -> cvb_dribbles_per100 all-null
    # closeout_speed expects ft/s defender speed -> no matching cvb field
    # release_time expects seconds -> no matching cvb field
    # shot_arc expects degrees -> no matching cvb field
    # spacing_around expects ft² (pixel-space, excluded)

    # spacing_gravity
    # avg_defender_attention = fraction off-ball time defender within 6ft
    #   -> cvb_paint_pressure_opp is closest (fraction of time opp in paint) -- NOT same thing, leave null
    # off_ball_movement = ft/s off-ball velocity -> pixel-space, excluded

    # durability_load
    # fatigue_velocity_trend = ft/s per game decline -> not matched (fatigue_score is cumulative pixels)
    # sprint_rate = fraction possessions reaching sprint speed -> no matching cvb field

    # form_streak_dynamics
    # fatigue_velocity_trend = ft/s delta -> not matched
    # spacing_context_streak = ratio hot vs cold team spacing -> no matching cvb field

    # quarter_shape_fatigue
    # speed_decay = ft/s Q4-Q1 delta -> cvb_velocity_q4_dropoff all-null
    # late_game_lift = fraction Q4 velocity burst -> no matching cvb field

    # situational_splits
    # cv_clutch_velocity = ft/s clutch minus mean -> pixel-space
    # cv_b2b_fatigue_score = fatigue_score on b2b -> same as cvb_fatigue_score (cumulative pixels, not ft/s)
    # cv_home_spacing_delta = ft² delta -> pixel-space
    # cv_blowout_drive_rate = drives per possession -> no matching cvb field

    # scoring_creation
    # drive_speed = ft/s -> pixel-space
    # rim_pressure = composite index (0-1) -> cvb_paint_pressure_opp is close:
    #   "fraction of time opponent in paint" = pressure on this player's drives
    "rim_pressure": "cvb_paint_pressure_opp",       # fraction of frames opp in paint near this player

    # foul_drawing
    # contact_seek_rate = fraction -> no matching cvb field

    # foul_tendency
    # contest_proximity_at_foul = ft -> pixel-space
    # foul_body_angle = degrees -> no matching cvb field
    # spacing_at_foul_commit = ft² -> pixel-space

    # catch_shoot_vs_pullup
    # openness_on_cs = ft defender distance -> pixel-space
    # dribbles_pre_pull -> cvb_dribbles_per100 all-null

    # clutch_scoring
    # clutch_defender_distance = ft -> pixel-space

    # isolation_profile
    # defender_distance_iso = ft -> pixel-space
    # blow_by_rate = fraction -> no matching cvb field

    # transition_scoring
    # sprint_speed_transition = ft/s -> pixel-space

    # pick_and_roll_profile
    # screen_navigation = composite score -> no matching cvb field
    # pocket_pass_window = fraction -> no matching cvb field

    # playmaking_network
    # pass_velocity = ft/s -> pixel-space
    # gravity_drawn = fraction -> cvb_paint_pressure_own (fraction own-team in paint) is NOT same

    # post_up_profile
    # seal_depth = ft from basket -> cvb_avg_dist_to_basket (ft, valid mapping)
    "seal_depth": "cvb_avg_dist_to_basket",         # mean dist to basket in ft

    # pace_fit
    # cv_spacing_fast/slow = ft² -> pixel-space
    # cv_drive_freq_fast = per_100_poss -> no matching cvb
    # cv_off_ball_speed_fast/slow = ft/s -> pixel-space

    # matchup_splits
    # cv_defender_closeout_vs_pos = dist ft/s -> pixel-space/no matching
    # cv_contest_rate_vs_pos = dist fraction -> cvb_contested_shot_pct all-null
    # cv_drive_success_vs_scheme = dist -> no matching
    # cv_spacing_vs_scheme = dist ft² -> pixel-space

    # score_margin_splits
    # cv_usage_leading/trailing = fraction -> no matching
    # cv_drive_rate_trailing = drives/min -> no matching

    # usage_role: all cv fields -> no matching cvb fields (ball-handler pct, iso freq etc)

    # vs_scheme_splits: contest_vs_scheme = dist ft -> pixel-space

    # rest_b2b_splits: speed_decay_b2b = ft/s -> pixel-space

    # turnover_profile
    # ball_handler_speed_at_tov = ft/s -> pixel-space
    # defender_proximity_at_tov = ft -> pixel-space
    # spacing_at_tov_commit = ft² -> pixel-space

    # ft_profile: arc/speed/spread all ball-trajectory -> no matching cvb
    # monthly_form: 0 slots
    # shot_clock_scoring: contest_by_clock = dist -> cvb_contested_shot_pct all-null
}

# Additional paint-fraction slot names that map to cvb_paint_time_pct
# (any slot whose description/name implies "paint occupancy fraction"):
# Currently handled via exact slot names above; these need manual extension
# if new atlas parquets add paint-fraction slots with other names.

UNFILLED_REASONS: dict[str, str] = {
    "cvb_avg_defender_dist": "pixel units (not feet); atlas slots expect ft",
    "cvb_avg_spacing": "pixel area (not ft²); atlas slots expect ft²",
    "cvb_off_ball_dist": "pixel units (not feet); atlas slots expect ft",
    "cvb_avg_velocity": "pixel/frame units (not ft/s); atlas slots expect ft/s",
    "cvb_contested_shot_pct": "all-null in current season aggregate",
    "cvb_dribbles_per100": "all-null in current season aggregate",
    "cvb_passes_per100": "all-null in current season aggregate",
    "cvb_velocity_q4_dropoff": "all-null in current season aggregate",
    "cvb_off_ball_dist_std": "all-null in current season aggregate",
    "cvb_contest_arm_mean": "sparse (n=47); no exact atlas slot match",
    "cvb_contest_arm_nonzero_pct": "sparse (n=47); nearest slot (contest_rate) needs fraction of FGA, not arm-raise pct",
    "cvb_paint_pressure_own": "fraction own team in paint — descriptively ambiguous; only rim_pressure slot filled via cvb_paint_pressure_opp",
    "cvb_fatigue_score": "cumulative distance (pixel×frame units), not per-game ft/s delta that fatigue_velocity_trend slots expect",
    "cvb_pose_coverage_pct": "data-quality coverage metric, not a behavioral signal",
    "cvb_paint_time_pct": "no exact slot match; paint_time_pct is per-player paint occupancy but no atlas slot is named for it directly",
    "cvb_near_basket_pct": "no exact atlas slot uses fraction-of-frames-near-basket as its primary signal",
    "cvb_close_to_basket_pct": "sparse (n=9 players); no exact atlas slot match",
}


def _conf(n_games: int) -> str:
    """Confidence tier, capped at med (CV behavioral data is descriptive)."""
    if n_games >= 5:
        return "med"
    return "low"


def _round4(v: Any) -> Any:
    if isinstance(v, float) and np.isfinite(v):
        return round(v, 4)
    return v


def _fill_slot(
    slot_name: str,
    dtype: str,
    cvb_val: Any,
) -> Any:
    """Return the value to place in slot["value"], or None if not fillable."""
    if cvb_val is None or (isinstance(cvb_val, float) and not np.isfinite(cvb_val)):
        return None
    if dtype == "dist":
        return {"mean": _round4(float(cvb_val)), "p25": None, "p75": None}
    return _round4(float(cvb_val))


def _build_cv_lookup(cv_path: Path) -> dict[int, dict]:
    """Return {nba_player_id: {cvb_col: value, n_games: int, ...}}."""
    cv = pd.read_parquet(cv_path)
    cv = cv[cv["nba_player_id"].notna()].copy()
    cv["nba_player_id"] = cv["nba_player_id"].astype(int)
    lookup: dict[int, dict] = {}
    for _, row in cv.iterrows():
        pid = int(row["nba_player_id"])
        lookup[pid] = row.to_dict()
    return lookup


def _populate_row(
    cv_row: Optional[dict],
    cv_fields_json: str,
    as_of: str,
) -> str:
    """Return new _cv_fields JSON string for one atlas row."""
    parsed: dict = json.loads(cv_fields_json)

    if cv_row is None:
        # Player not in CV — return unchanged
        return cv_fields_json

    n_games = int(cv_row.get("n_games", 0))
    filled: list[str] = []

    for slot_name, cvb_field in SLOT_TO_CVB.items():
        if slot_name not in parsed:
            continue  # slot doesn't exist in this parquet's schema
        slot_meta = parsed[slot_name]
        dtype = slot_meta.get("dtype", "float")
        raw_val = cv_row.get(cvb_field)
        val = _fill_slot(slot_name, dtype, raw_val)
        if val is not None:
            slot_meta["value"] = val
            filled.append(slot_name)

    parsed["_cv_meta"] = {
        "source": "player_cv_per_player.parquet",
        "n_games": n_games,
        "confidence": _conf(n_games),
        "as_of": as_of,
        "filled_slots": filled,
    }
    return json.dumps(parsed, ensure_ascii=False)


def populate_parquet(
    path: Path,
    cv_lookup: dict[int, dict],
    as_of: str,
    dry_run: bool = False,
) -> dict:
    """Populate _cv_fields for one atlas parquet. Return stats dict."""
    df = pd.read_parquet(path)
    original_cols = list(df.columns)
    original_rows = len(df)

    if "_cv_fields" not in df.columns or "player_id" not in df.columns:
        return {"skipped": True, "reason": "missing _cv_fields or player_id column"}

    # Safety check: column set and row count must not change
    assert list(df.columns) == original_cols
    assert len(df) == original_rows

    new_cv = []
    players_touched = 0
    slots_filled_total = 0
    slot_fill_counts: dict[str, int] = {}

    for _, row in df.iterrows():
        pid = int(row["player_id"])
        cv_row = cv_lookup.get(pid)
        new_json = _populate_row(cv_row, row["_cv_fields"], as_of)
        new_cv.append(new_json)
        if cv_row is not None:
            parsed = json.loads(new_json)
            meta = parsed.get("_cv_meta", {})
            filled = meta.get("filled_slots", [])
            if filled:
                players_touched += 1
                slots_filled_total += len(filled)
                for s in filled:
                    slot_fill_counts[s] = slot_fill_counts.get(s, 0) + 1

    df = df.copy()
    df["_cv_fields"] = new_cv

    # Final safety assertions
    assert list(df.columns) == original_cols, "Column set changed!"
    assert len(df) == original_rows, "Row count changed!"

    if not dry_run:
        df.to_parquet(path, index=False)

    return {
        "skipped": False,
        "players_in_atlas": original_rows,
        "players_touched": players_touched,
        "slots_filled_total": slots_filled_total,
        "slot_fill_counts": slot_fill_counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate CV fields in atlas parquets")
    parser.add_argument(
        "--as-of",
        default=date.today().isoformat(),
        help="ISO date stamp for provenance (default: today)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and map but do not write parquets",
    )
    args = parser.parse_args()

    cv_lookup = _build_cv_lookup(CV_SRC)
    print(f"CV source: {len(cv_lookup)} players with valid nba_player_id")
    print(f"As-of: {args.as_of}")
    print(f"Dry-run: {args.dry_run}")
    print()

    atlas_files = sorted(ATLAS_GLOB.glob("atlas_player_*.parquet"))
    print(f"Found {len(atlas_files)} atlas_player parquets\n")

    summary_rows = []
    total_players_touched = 0
    total_slots_filled = 0

    slot_fill_counts: dict[str, int] = {}

    for path in atlas_files:
        section = path.stem.replace("atlas_player_", "")
        result = populate_parquet(path, cv_lookup, args.as_of, dry_run=args.dry_run)
        if result.get("skipped"):
            print(f"  SKIPPED {section}: {result['reason']}")
            continue

        touched = result["players_touched"]
        filled = result["slots_filled_total"]
        total_players_touched += touched
        total_slots_filled += filled

        # Accumulate per-slot counts from the in-memory result
        for slot, cnt in result.get("slot_fill_counts", {}).items():
            slot_fill_counts[slot] = slot_fill_counts.get(slot, 0) + cnt

        status = "DRY" if args.dry_run else "WROTE"
        print(
            f"  [{status}] {section}: "
            f"{touched}/{result['players_in_atlas']} players touched, "
            f"{filled} slot-fills"
        )
        summary_rows.append(
            (section, result["players_in_atlas"], touched, filled)
        )

    print()
    print("=" * 60)
    print(f"TOTAL: {total_players_touched} players touched across all sections")
    print(f"TOTAL: {total_slots_filled} slot-fill operations")
    print()

    # Report which slots were filled
    if slot_fill_counts:
        print("Slots filled (across all parquets):")
        for slot, cnt in sorted(slot_fill_counts.items(), key=lambda x: -x[1]):
            print(f"  {slot}: {cnt} players")
    print()

    # Report slots that stayed null everywhere
    all_mapped_slots = set(SLOT_TO_CVB.keys())
    unfilled_slots = all_mapped_slots - set(slot_fill_counts.keys())
    print("Mapped slots with zero fills (cvb data was null for all players):")
    for s in sorted(unfilled_slots):
        print(f"  {s} <- {SLOT_TO_CVB[s]}")
    print()

    print("CVB fields NOT mapped to any atlas slot (data gaps):")
    for field, reason in sorted(UNFILLED_REASONS.items()):
        print(f"  {field}: {reason}")


if __name__ == "__main__":
    main()
