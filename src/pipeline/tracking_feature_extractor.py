"""
tracking_feature_extractor.py — CV-derived per-player per-game feature extractor.

Reads data/tracking/{game_id}/ CSV outputs and returns a feature dict suitable
for injection into the ML feature pipeline (feature_pipeline.py).

Computed features per player (all float, 0.0 when insufficient data):
  avg_defender_distance    mean defender distance (feet) from shot_log
  shot_zone_paint_pct      % of shots from paint zone
  shot_zone_mid_range_pct  % from mid_range
  shot_zone_3pt_pct        % from 3pt_arc or corner_3
  contested_shot_rate      % of shots with defender_distance < 5 feet
  avg_spacing              mean team_spacing from shot_log
  shots_per_possession     total shots / total possessions
  made_pct                 % of shots with made == 1 (when enriched)
  avg_shot_clock_at_shot   mean shot_clock_est at shot frames (from scoreboard_log)
  possession_duration_avg  mean possession duration in sec
  play_type_transition_pct % of possessions that are transition/fast_break
  play_type_drive_pct      % of possessions that are drive
  play_type_isolation_pct  % of possessions that are isolation-type (half_court)
  play_type_post_pct       % of possessions that are post_up
  avg_contest_arm_angle    mean defender arm angle when contesting (degrees)
  avg_closeout_speed       mean defender closeout velocity
  avg_fatigue_proxy        mean player fatigue indicator
  catch_shoot_pct          fraction of shots as catch-and-shoot
  avg_dribble_count        mean pre-shot dribbles
  second_chance_rate       fraction of shots off offensive rebound
  avg_shot_distance        mean shot distance (feet)

  -- P1 Tier-1 features (per-frame mining) --
  potential_assists        # passes leading to teammate shot within 60 frames
  touches_per_game         # distinct possession_ids with ball_possession==1
  paint_dwell_pct          fraction of player's frames within 8 ft of basket
  defender_approach_speed  mean rate-of-change of nearest_opponent dist in 6
                           frames before each shot (negative = defender closing)
  preshot_velocity_peak    mean max velocity in 30 frames before each shot

Public API
----------
    extract(game_id, data_root) -> Dict[player_id, Dict[str, float]]
    merge_into_features(features_df, cv_dict) -> pd.DataFrame
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from typing import Dict, Optional

_CONTESTED_FT = 5.0                 # feet — contested if defender within 5 ft
_PX_TO_FT = 940.0 / 50.0           # pixels per foot on 940×500 court map (18.8 px/ft)
_PIXEL_SCALE_THRESHOLD = 100.0      # max(defender_distance / spacing / shot_distance) > this → values are in pixels

# Tier-1 quality gates
_MIN_SLOT_FRAMES = 100              # minimum tracked frames to compute motion features
_MIN_X_STD_PX = 50.0               # x_position std must exceed this for motion features
# Frame-number windows.  tracking_data is sampled 1-in-6 from 60fps source,
# so frame numbers increment by 6 per row.
# "60 source frames" at 7.5fps effective = ~8s = frame-number delta 60.
# "6 sampled rows pre-shot" = 36 frame-number units (6 rows x 6).
# "30 sampled rows pre-shot" = 180 frame-number units (30 rows x 6).
_PASS_SHOT_WINDOW = 60              # frame-number units for pass->shot precursor
_PRE_SHOT_VELOCITY_WINDOW = 180    # frame-number units for preshot_velocity_peak
_PRE_SHOT_DEFENDER_WINDOW = 36     # frame-number units for defender_approach_speed
_PAINT_DIST_FT = 8.0               # dist_to_basket_ft threshold for paint dwell

# fatigue_proxy is a cumulative player-movement counter (pixel-distance traveled).
# Values can reach 100K+. We normalize to [0, 1] per game by dividing by the
# game-level max.  This is intentionally NOT pixel-rescaled — the unit is
# arbitrary and only the relative magnitude within a game carries signal.
# NOTE: audit (2026-05-28) confirmed this by observing ~80% monotone-increasing
# sequences across shots, confirming a cumulative accumulator pattern.
_FATIGUE_NORMALIZE = True           # divide each game's fatigue values by game max

# Default data root (override via data_root parameter)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_DATA_ROOT = os.path.join(_PROJECT_ROOT, "data")


def _drive_pct_by_team(tracking_path: str) -> Dict[str, Optional[float]]:
    """Bug 30 fix (2026-05-29): compute play_type_drive_pct from raw drive_flag.

    Reads tracking_data.csv and groups by (possession_id, team). A possession
    is considered a "drive possession" if any frame within it has drive_flag=1.

    Indexes results under BOTH the tracker color ("green"/"white") and the NBA
    abbreviation ("DEN"/"PHX") for the same possession set, so downstream callers
    can look up by whichever key their possessions.csv / shot_log.csv uses.

    Returns {team_key: drive_pct_or_None}:
      - team_key is either the tracker color or NBA abbreviation
      - value is the float drive % rounded to 3 decimals, or None when:
          - tracking_data.csv is missing
          - team has zero possessions in tracking_data

    Previous behavior (line 675): hardcoded to None because possessions.csv has
    no play_type=drive entries — PlayTypeClassifier doesn't emit "drive". But
    drive_flag IS populated per-frame in tracking_data.csv (see
    unified_pipeline.py:2628), so we aggregate it directly.
    """
    if not os.path.exists(tracking_path):
        return {}

    # Keyed by (color, abbrev) tuple so the same possession set is counted once
    # but indexed under both team labels for downstream lookup flexibility.
    team_total: Dict[tuple, set] = defaultdict(set)
    team_drive: Dict[tuple, set] = defaultdict(set)
    try:
        with open(tracking_path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or "drive_flag" not in reader.fieldnames:
                return {}
            for row in reader:
                poss_id = str(row.get("possession_id", "")).strip()
                color = str(row.get("team", "")).strip()
                abbrev = str(row.get("team_abbrev", "")).strip()
                if not poss_id or poss_id in ("nan", "0", ""):
                    continue
                if not color and not abbrev:
                    continue
                key = (color, abbrev)
                team_total[key].add(poss_id)
                drive_flag = str(row.get("drive_flag", "0")).strip()
                if drive_flag in ("1", "1.0", "True", "true"):
                    team_drive[key].add(poss_id)
    except Exception:
        return {}

    result: Dict[str, Optional[float]] = {}
    for (color, abbrev), totals in team_total.items():
        n_total = len(totals)
        if n_total <= 0:
            val: Optional[float] = None
        else:
            n_drive = len(team_drive.get((color, abbrev), set()))
            val = round(n_drive / n_total, 3)
        # Index under both labels — caller may pass either color or abbrev.
        # Don't index empty strings.
        if color:
            # If two (color, abbrev) tuples share the same color (shouldn't happen
            # in a 2-team game, but safe), use the larger possession count.
            if color not in result or (val is not None and (result.get(color) is None or val > 0)):
                result[color] = val
        if abbrev and abbrev not in ("UNK", "nan"):
            if abbrev not in result or (val is not None and (result.get(abbrev) is None or val > 0)):
                result[abbrev] = val
    return result


def _compute_tier1_features(
    game_dir: str,
) -> Dict[int, Dict[str, float]]:
    """
    Compute 5 Tier-1 per-frame features for each tracker slot (player_id).

    Reads tracking_data.csv once and computes:
      potential_assists        -- pass->teammate-shot precursor count
      touches_per_game         -- distinct possession_ids with ball held
      paint_dwell_pct          -- fraction of frames within 8 ft of basket
      defender_approach_speed  -- mean nearest_opponent delta-per-frame pre-shot
      preshot_velocity_peak    -- mean max velocity in 30 frames before shot

    Quality gates (phantom-slot filtering):
      - Motion features (#3, #4, #5) require slot_frames >= 100 AND
        x_position.std() > 50 px.  Phantom (stationary re-ID-failed) slots
        get 0.0 for those features.
      - Touch count (#2) requires slot_frames >= 100 (possession assignment is
        unreliable for phantom slots).
      - Assist precursor (#1) has no gate (passes are rare events, not mass frames).

    Returns:
        Dict mapping slot_id (int) -> {feature_name: float}.
        Returns {} if tracking_data.csv not found.
    """
    tracking_path = os.path.join(game_dir, "tracking_data.csv")
    if not os.path.exists(tracking_path):
        return {}

    # ---- Load tracking_data.csv ------------------------------------------------
    # We parse manually (CSV reader) to avoid a pandas import at module load,
    # and to stay consistent with the rest of this file.  Only the columns we
    # need are kept in memory.
    slots: Dict[int, dict] = {}   # slot_id -> aggregated data

    try:
        with open(tracking_path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    slot = int(row.get("player_id", 0) or 0)
                    if not slot:
                        continue

                    if slot not in slots:
                        slots[slot] = {
                            "frames": 0,
                            "x_positions": [],
                            "event_frames": [],        # (frame, event, team)
                            "dist_to_basket_ft": [],
                            "ball_possession_poss": set(),  # distinct possession_ids
                            "velocity_arr": [],         # (frame, velocity)
                            "nearest_opp_arr": [],      # (frame, nearest_opponent)
                        }

                    d = slots[slot]
                    d["frames"] += 1

                    # x_position for phantom-slot gate
                    xp = row.get("x_position", "")
                    if xp not in ("", None, "nan"):
                        try:
                            d["x_positions"].append(float(xp))
                        except (ValueError, TypeError):
                            pass

                    # event for pass/shot precursor
                    ev = str(row.get("event", "")).strip().lower()
                    team = str(row.get("team", "")).strip().lower()
                    fr_raw = row.get("frame", "")
                    fr = int(fr_raw) if fr_raw not in ("", None) else -1
                    if ev in ("pass", "shot") and fr >= 0:
                        d["event_frames"].append((fr, ev, team))

                    # dist_to_basket_ft for paint_dwell_pct
                    dft = row.get("dist_to_basket_ft", "")
                    if dft not in ("", None, "nan"):
                        try:
                            d["dist_to_basket_ft"].append(float(dft))
                        except (ValueError, TypeError):
                            pass

                    # ball_possession + possession_id for touches_per_game
                    bp = row.get("ball_possession", "")
                    poss_id = row.get("possession_id", "")
                    if bp not in ("", None):
                        try:
                            if int(float(bp)) == 1 and poss_id not in ("", None):
                                d["ball_possession_poss"].add(str(poss_id))
                        except (ValueError, TypeError):
                            pass

                    # velocity for preshot_velocity_peak
                    vel = row.get("velocity", "")
                    if vel not in ("", None, "nan") and fr >= 0:
                        try:
                            d["velocity_arr"].append((fr, float(vel)))
                        except (ValueError, TypeError):
                            pass

                    # nearest_opponent for defender_approach_speed
                    no = row.get("nearest_opponent", "")
                    if no not in ("", None, "nan") and fr >= 0:
                        try:
                            d["nearest_opp_arr"].append((fr, float(no)))
                        except (ValueError, TypeError):
                            pass

                except (ValueError, TypeError):
                    continue

    except Exception:
        return {}

    if not slots:
        return {}

    # ---- Compute per-slot quality gates ----------------------------------------
    import math

    def _std(vals):
        if len(vals) < 2:
            return 0.0
        n = len(vals)
        mean = sum(vals) / n
        return math.sqrt(sum((v - mean) ** 2 for v in vals) / n)

    slot_quality: Dict[int, bool] = {}   # True = passes motion gate
    for slot, d in slots.items():
        passes_frame_gate = d["frames"] >= _MIN_SLOT_FRAMES
        passes_std_gate = _std(d["x_positions"]) > _MIN_X_STD_PX
        slot_quality[slot] = passes_frame_gate and passes_std_gate

    # ---- Detect nearest_opponent scale: pixels vs feet -------------------------
    # A subset of games (especially 2024-25 season) store nearest_opponent in
    # pixels rather than feet.  Court is ~940 px wide = 50 ft → max in feet is
    # ~91 ft.  If the median nearest_opponent across all good slots exceeds 200,
    # the values are in pixels and need rescaling.
    all_nop_vals = [
        v for slot, d in slots.items()
        if slot_quality[slot]
        for _, v in d["nearest_opp_arr"]
    ]
    _nop_scale = 1.0  # default: already in feet
    if all_nop_vals:
        sorted_nop = sorted(all_nop_vals)
        nop_median = sorted_nop[len(sorted_nop) // 2]
        if nop_median > 200:
            # Values are in pixels — rescale to feet
            _nop_scale = 1.0 / _PX_TO_FT  # 1 px / (18.8 px/ft) = ft

    # Build frame-indexed lookups for pre-shot window computations.
    # Maps slot -> {frame: velocity} and slot -> {frame: nearest_opponent}
    # Only for slots that pass the quality gate (to save memory on phantom slots).
    vel_by_frame: Dict[int, Dict[int, float]] = {}
    nop_by_frame: Dict[int, Dict[int, float]] = {}
    for slot, d in slots.items():
        if slot_quality[slot]:
            vel_by_frame[slot] = {fr: v for fr, v in d["velocity_arr"]}
            nop_by_frame[slot] = {fr: v * _nop_scale for fr, v in d["nearest_opp_arr"]}

    # ---- Feature 1: potential_assists ------------------------------------------
    # For each PASS event, check if a SAME-TEAM shot occurs within 60 frames.
    # Collect all pass rows and all shot rows across all slots.
    all_passes = []   # (frame, slot, team)
    all_shots  = []   # (frame, slot, team)
    for slot, d in slots.items():
        for (fr, ev, team) in d["event_frames"]:
            if ev == "pass":
                all_passes.append((fr, slot, team))
            elif ev == "shot":
                all_shots.append((fr, slot, team))

    # Sort shots by frame for fast lookups
    all_shots_sorted = sorted(all_shots, key=lambda x: x[0])
    shot_frames_sorted = [s[0] for s in all_shots_sorted]

    potential_assists: Dict[int, int] = defaultdict(int)
    for pass_fr, pass_slot, pass_team in all_passes:
        # Binary search: first shot frame > pass_fr
        lo, hi = 0, len(shot_frames_sorted)
        while lo < hi:
            mid = (lo + hi) // 2
            if shot_frames_sorted[mid] <= pass_fr:
                lo = mid + 1
            else:
                hi = mid
        # Iterate shots in [pass_fr+1, pass_fr+WINDOW] same team, different slot
        for i in range(lo, len(all_shots_sorted)):
            sh_fr, sh_slot, sh_team = all_shots_sorted[i]
            if sh_fr > pass_fr + _PASS_SHOT_WINDOW:
                break
            if sh_team == pass_team and sh_slot != pass_slot:
                potential_assists[pass_slot] += 1
                break   # count at most 1 potential assist per pass

    # ---- Feature 2: touches_per_game -------------------------------------------
    # Apply full quality gate (frames + x_std): phantom slots get ball_possession==1
    # erroneously assigned in the short-clip sample, so we require motion evidence.
    # Bug 34 fix 2026-05-28: previously `min(touches, 150)` capped real-NBA-impossible
    # values at exactly 150.0 (NBA all-time leader = 95 / game). Created the fake
    # Dejounte Murray z=+15.76 anomaly in Anomaly_Atlas. Replace cap with None when
    # implausibly high — drops the value rather than silently asserting a fake max.
    _TOUCHES_MAX = 110   # tightened from 150; NBA leader ~95 + slack for clip-edge
    touches_per_game: Dict[int, int] = {}
    for slot, d in slots.items():
        if slot_quality[slot]:
            raw_touches = len(d["ball_possession_poss"])
            touches_per_game[slot] = raw_touches if raw_touches <= _TOUCHES_MAX else None
        else:
            touches_per_game[slot] = 0

    # ---- Feature 3: paint_dwell_pct --------------------------------------------
    paint_dwell_pct: Dict[int, float] = {}
    for slot, d in slots.items():
        dists = d["dist_to_basket_ft"]
        if slot_quality[slot] and dists:
            paint_dwell_pct[slot] = round(
                sum(1 for v in dists if v < _PAINT_DIST_FT) / len(dists), 3
            )
        else:
            paint_dwell_pct[slot] = 0.0

    # ---- Features 4 & 5: defender_approach_speed, preshot_velocity_peak --------
    # Collect shot frames per slot (from event_frames already parsed)
    shot_frames_by_slot: Dict[int, list] = defaultdict(list)
    for slot, d in slots.items():
        for (fr, ev, team) in d["event_frames"]:
            if ev == "shot":
                shot_frames_by_slot[slot].append(fr)

    defender_approach_speed: Dict[int, float] = {}
    preshot_velocity_peak: Dict[int, float] = {}

    for slot in slots:
        if not slot_quality[slot]:
            defender_approach_speed[slot] = 0.0
            preshot_velocity_peak[slot] = 0.0
            continue

        shot_frs = shot_frames_by_slot.get(slot, [])
        if not shot_frs:
            defender_approach_speed[slot] = 0.0
            preshot_velocity_peak[slot] = 0.0
            continue

        slot_nop = nop_by_frame.get(slot, {})
        slot_vel = vel_by_frame.get(slot, {})

        approach_speeds = []
        peak_velocities = []

        for shot_fr in shot_frs:
            # --- Feature 4: defender approach speed (6 frames before shot) ---
            pre_nop = [
                (fr, slot_nop[fr])
                for fr in range(shot_fr - _PRE_SHOT_DEFENDER_WINDOW, shot_fr)
                if fr in slot_nop
            ]
            if len(pre_nop) >= 3:
                first_fr, first_val = pre_nop[0]
                last_fr, last_val = pre_nop[-1]
                frame_span = last_fr - first_fr
                if frame_span > 0:
                    slope = (last_val - first_val) / frame_span
                    approach_speeds.append(slope)

            # --- Feature 5: preshot velocity peak (30 frames before shot) ---
            pre_vel = [
                slot_vel[fr]
                for fr in range(shot_fr - _PRE_SHOT_VELOCITY_WINDOW, shot_fr)
                if fr in slot_vel
            ]
            if len(pre_vel) >= 5:
                peak_velocities.append(max(pre_vel))

        defender_approach_speed[slot] = (
            round(sum(approach_speeds) / len(approach_speeds), 3)
            if approach_speeds else 0.0
        )
        # Bug 31 fix 2026-05-28: previously `min(raw_psv, 40.0)` capped 308 of 332
        # nonzero rows (93%) at exactly 40.0, producing fake bench/starter signals
        # in INT-44 (player 1642847 t=-3.0 starter-vs-bench was entirely a clip
        # artifact). Replace min-clip with NaN-on-implausible: drop the value when
        # it exceeds the physical cap; downstream registry filters NaN out.
        # NBA all-time speed record is ~33 ft/s; pixel-velocity errors push above.
        _PRESHOT_VEL_MAX = 35.0   # tightened from 40.0 to keep noise out
        raw_psv = (
            round(sum(peak_velocities) / len(peak_velocities), 3)
            if peak_velocities else 0.0
        )
        # Drop implausibly-high values to NaN rather than clipping (so they're
        # recognizable as missing in audits, not as legitimate peak performance).
        preshot_velocity_peak[slot] = raw_psv if raw_psv <= _PRESHOT_VEL_MAX else None

    # ---- Assemble result -------------------------------------------------------
    # potential_assists: zero out phantom slots — tracker assigns pass events to
    # stationary phantom IDs just as it does ball_possession; without motion
    # confirmation the count is uninformative noise.
    result: Dict[int, Dict[str, float]] = {}
    for slot in slots:
        passes_gate = slot_quality[slot]
        result[slot] = {
            "potential_assists":       round(float(potential_assists.get(slot, 0)) if passes_gate else 0.0, 3),
            "touches_per_game":        round(float(touches_per_game.get(slot, 0)), 3),
            "paint_dwell_pct":         paint_dwell_pct.get(slot, 0.0),
            "defender_approach_speed": defender_approach_speed.get(slot, 0.0),
            "preshot_velocity_peak":   preshot_velocity_peak.get(slot, 0.0),
        }

    return result


def extract(
    game_id: str,
    data_root: Optional[str] = None,
) -> Dict[int, Dict[str, float]]:
    """
    Extract CV-derived per-player features for one processed game.

    Args:
        game_id:   NBA game ID (e.g. "0022400625").
        data_root: Root of the data directory tree. Defaults to project data/.
                   The function looks for files under {data_root}/tracking/{game_id}/.

    Returns:
        Dict mapping player_id (int) → dict of feature_name → float.
        Returns {} if no tracking data found for this game.
    """
    root   = data_root or _DEFAULT_DATA_ROOT
    gdir   = os.path.join(root, "tracking", game_id)
    if not os.path.isdir(gdir):
        # Also try flat layout (legacy: data/tracking_data.csv without game subdir)
        gdir = root

    shot_path  = os.path.join(gdir, "shot_log.csv")
    poss_path  = os.path.join(gdir, "possessions.csv")
    sb_path    = os.path.join(gdir, "scoreboard_log.csv")
    tracking_path = os.path.join(gdir, "tracking_data.csv")  # Bug 30 fix 2026-05-29

    # ── Compute Tier-1 per-frame features (tracking_data.csv) ────────────────
    tier1_by_slot = _compute_tier1_features(gdir)

    if not os.path.exists(shot_path) and not os.path.exists(poss_path):
        return {}

    # ── Shot log features ─────────────────────────────────────────────────────
    shot_stats: Dict[int, dict] = defaultdict(lambda: {
        "def_dists": [], "zones": [], "made": [], "spacings": [],
        # new CV-moat columns
        "arm_angles": [], "closeout_speeds": [], "fatigue_proxies": [],
        "catch_shoot": [], "dribble_counts": [], "second_chances": [],
        "shot_distances": [],
    })

    if os.path.exists(shot_path):
        with open(shot_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    pid_raw = row.get("player_id", "")
                    if not str(pid_raw).strip().lstrip("-").isdigit():
                        continue
                    pid = int(pid_raw)
                    s   = shot_stats[pid]
                    dd  = row.get("defender_distance", "")
                    if dd not in ("", None):
                        s["def_dists"].append(float(dd))
                    zone = str(row.get("court_zone", "")).strip()
                    if zone:
                        s["zones"].append(zone)
                    made_val = row.get("made", "")
                    if made_val not in ("", None):
                        s["made"].append(int(made_val))
                    sp = row.get("team_spacing", "")
                    if sp not in ("", None):
                        s["spacings"].append(float(sp))
                    # new CV-moat columns
                    for col, key in [
                        ("contest_arm_angle", "arm_angles"),
                        ("closeout_speed", "closeout_speeds"),
                        ("fatigue_proxy", "fatigue_proxies"),
                        ("shot_distance", "shot_distances"),
                        ("dribble_count", "dribble_counts"),
                    ]:
                        v = row.get(col, "")
                        if v not in ("", None, "nan"):
                            try:
                                s[key].append(float(v))
                            except (ValueError, TypeError):
                                pass
                    for col, key in [
                        ("catch_and_shoot", "catch_shoot"),
                        ("second_chance", "second_chances"),
                    ]:
                        v = row.get(col, "")
                        if v not in ("", None, "nan"):
                            try:
                                s[key].append(int(float(v)))
                            except (ValueError, TypeError):
                                pass
                except (ValueError, TypeError):
                    continue

    # ── Detect pixel vs feet scale per game and rescale ──────────────────────
    # Helper: rescale a named list-key across all shot_stats if game max > threshold.
    # If values are wildly mixed-magnitude within a single player (>10x ratio
    # between min and max for same player), log a warning and still apply the
    # per-game-max heuristic.
    def _rescale_if_pixels(key: str, threshold: float = _PIXEL_SCALE_THRESHOLD) -> None:
        import math
        all_vals = [v for s in shot_stats.values() for v in s.get(key, [])]
        if not all_vals:
            return
        game_max = max(all_vals)
        if game_max <= threshold:
            return   # already in feet — no action needed

        # If game_max is extremely large (> 50K px), the values may be squared
        # pixel distances (e.g. team_spacing stored as dist² in some game versions).
        # sqrt then rescale produces plausible feet values; plain divide does not.
        use_sqrt = game_max > 50_000

        # Check for mixed-magnitude within any single player
        for pid_s in shot_stats.values():
            pvs = pid_s.get(key, [])
            if len(pvs) >= 2:
                pmin, pmax = min(pvs), max(pvs)
                if pmin > 0 and pmax / pmin > 1000:
                    import warnings
                    warnings.warn(
                        f"[tracking_feature_extractor] {key} mixed-magnitude within "
                        f"player (min={pmin:.1f} max={pmax:.1f}) in game {game_id!r}; "
                        f"applying {'sqrt+' if use_sqrt else ''}per-game-max heuristic"
                    )
        if use_sqrt:
            for s in shot_stats.values():
                s[key] = [math.sqrt(v) / _PX_TO_FT for v in s.get(key, [])]
        else:
            for s in shot_stats.values():
                s[key] = [v / _PX_TO_FT for v in s.get(key, [])]

        # Bug 37/38 fix (2026-05-28): post-rescale validity caps.
        # Values that survive the pixel-vs-feet heuristic but land at physically
        # impossible feet values (homography blow-up, mixed coords in a single game)
        # are silenced as None so registry aggregation skips them rather than
        # propagating outliers into atlas means.
        #   spacings    : NBA court is 50 ft wide — cap at 60 ft (slack for diagonals)
        #   shot_distances: full court is 94 ft — cap at 94 ft
        #   def_dists   : defender can't be > half-court (47 ft) from shooter — cap at 50 ft
        _CAPS = {
            "spacings":       60.0,
            "shot_distances": 94.0,
            "def_dists":      50.0,
        }
        if key in _CAPS:
            cap = _CAPS[key]
            for s in shot_stats.values():
                s[key] = [v if v <= cap else None for v in s.get(key, [])]
                # Strip None so downstream list-mean helpers don't receive None entries;
                # caller code already handles empty lists gracefully.
                s[key] = [v for v in s[key] if v is not None]

    _rescale_if_pixels("def_dists")
    _rescale_if_pixels("spacings")
    _rescale_if_pixels("shot_distances")

    # ── Normalize fatigue_proxy per player (cumulative counter, not feet) ──────
    # Bug 4 fix (2026-05-28): game-wide max divide caused every player's value to
    # land near the same point when fatigue values cluster (all players ran similar
    # distances), producing the "exact same +1.65σ for many players" artifact in
    # downstream matchup z-scores.  Per-player z-score preserves the relative shape
    # of each player's shot-to-shot fatigue sequence while making players comparable.
    # A player with < 2 shots keeps raw values (z-score undefined); single-shot
    # players are left at 0.5 (neutral).
    if _FATIGUE_NORMALIZE:
        for s in shot_stats.values():
            fp_vals = s.get("fatigue_proxies", [])
            if len(fp_vals) < 2:
                # fewer than 2 shots: emit neutral 0.5 so downstream treats as unknown
                s["fatigue_proxies"] = [0.5] * len(fp_vals)
                continue
            import statistics as _stat
            mu  = _stat.mean(fp_vals)
            sig = _stat.pstdev(fp_vals)
            if sig > 0:
                # z-score then shift to [~0,~1] via sigmoid-like clamp: 0.5 + z/6
                # keeps most values in [0,1] (±3σ → [0,1]) without hard clipping
                s["fatigue_proxies"] = [
                    max(0.0, min(1.0, 0.5 + (v - mu) / (6.0 * sig))) for v in fp_vals
                ]
            else:
                s["fatigue_proxies"] = [0.5] * len(fp_vals)

    # ── Possession features ───────────────────────────────────────────────────
    poss_by_team: Dict[str, list] = defaultdict(list)

    if os.path.exists(poss_path):
        with open(poss_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                team = str(row.get("team", "")).strip()
                if not team:
                    continue
                dur = row.get("duration_sec", "")
                ptype = str(row.get("play_type", row.get("possession_type", ""))).strip()
                if dur not in ("", None):
                    try:
                        poss_by_team[team].append({
                            "dur": float(dur),
                            "play_type": ptype,
                        })
                    except (ValueError, TypeError):
                        pass

    # ── Shot-clock at shot frames ─────────────────────────────────────────────
    # Primary source: scoreboard_log.csv (frame → shot_clock lookup).
    # Fallback: shot_clock column directly in shot_log.csv (populated in most games).
    # scoreboard_log.csv is missing in 152/187 games — fallback is critical.

    # Build frame → shot_clock lookup from scoreboard_log when available
    sb_clock: Dict[int, float] = {}
    if os.path.exists(sb_path):
        with open(sb_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    sc = row.get("shot_clock", "")
                    fr = row.get("frame", "")
                    if sc not in ("", None) and fr not in ("", None):
                        val = float(sc)
                        if 0.0 <= val <= 30.0:   # sanity check: valid shot-clock range
                            sb_clock[int(fr)] = val
                except (ValueError, TypeError):
                    pass

    shot_clocks_by_pid: Dict[int, list] = defaultdict(list)

    if os.path.exists(shot_path) and sb_clock:
        # Scoreboard source: join by nearest frame within 3 seconds
        with open(shot_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    pid = int(row.get("player_id", 0) or 0)
                    fr  = int(row.get("frame", 0) or 0)
                    nearest_fr = min(sb_clock.keys(), key=lambda k: abs(k - fr))
                    if abs(nearest_fr - fr) <= 90:   # within 3 seconds at 30fps
                        shot_clocks_by_pid[pid].append(sb_clock[nearest_fr])
                except (ValueError, TypeError):
                    pass

    # Fallback: read shot_clock column directly from shot_log.csv when
    # scoreboard_log is missing OR produced no matches.
    if os.path.exists(shot_path) and not shot_clocks_by_pid:
        with open(shot_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    sc_raw = row.get("shot_clock", "")
                    if sc_raw in ("", None, "nan"):
                        continue
                    sc_val = float(sc_raw)
                    if not (0.0 <= sc_val <= 30.0):
                        continue   # skip sentinel / bad values
                    pid = int(row.get("player_id", 0) or 0)
                    if pid:
                        shot_clocks_by_pid[pid].append(sc_val)
                except (ValueError, TypeError):
                    pass

    # Count total shots per team (for shots_per_possession)
    shots_by_team: Dict[str, int] = defaultdict(int)
    if os.path.exists(shot_path):
        with open(shot_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                team = str(row.get("team", "")).strip()
                if team:
                    shots_by_team[team] += 1

    # ── Build per-player feature dict ─────────────────────────────────────────
    result: Dict[int, Dict[str, float]] = {}

    all_pids = set(shot_stats.keys()) | set(shot_clocks_by_pid.keys())

    # Bug 30 fix 2026-05-29: compute play_type_drive_pct from raw drive_flag per
    # possession (possessions.csv has no play_type=drive — PlayTypeClassifier
    # doesn't emit it — but drive_flag IS populated per-frame in tracking_data).
    drive_pct_by_team = _drive_pct_by_team(tracking_path)

    # For possession-level features, we average across all team possessions.
    # Build a mapping: tracker team (green/white) → possession stats.
    team_poss_feats: Dict[str, dict] = {}
    for team, poss_list in poss_by_team.items():
        durs = [p["dur"] for p in poss_list]
        types = [p["play_type"] for p in poss_list]
        n = len(poss_list)
        team_poss_feats[team] = {
            "possession_duration_avg":   round(sum(durs) / n, 2) if durs else 0.0,
            "play_type_transition_pct":  round(sum(1 for t in types if t in
                                              ("transition", "fast_break")) / n, 3)
                                          if n else 0.0,
            # Bug 30 fix 2026-05-29: was hardcoded None (Bug 35 workaround).
            # Now computed from per-frame drive_flag aggregated by possession_id.
            # Returns None when tracking_data.csv missing → registry still drops cell.
            "play_type_drive_pct":       drive_pct_by_team.get(team),
            "play_type_isolation_pct":   round(sum(1 for t in types if t in
                                              ("half_court", "isolation")) / n, 3)
                                          if n else 0.0,
            "play_type_post_pct":        round(sum(1 for t in types if t == "post_up") / n, 3)
                                          if n else 0.0,
            "total_possessions":         n,
        }

    for pid in all_pids:
        s    = shot_stats.get(pid, {})
        dds  = s.get("def_dists", [])        # already in feet (converted above if needed)
        zones = s.get("zones",   [])
        made  = s.get("made",    [])
        spcs  = s.get("spacings",[])
        scks  = shot_clocks_by_pid.get(pid, [])
        arm_angles       = s.get("arm_angles", [])
        closeout_speeds  = s.get("closeout_speeds", [])
        fatigue_proxies  = s.get("fatigue_proxies", [])
        catch_shoot      = s.get("catch_shoot", [])
        dribble_counts   = s.get("dribble_counts", [])
        second_chances   = s.get("second_chances", [])
        shot_distances   = s.get("shot_distances", [])

        n_shots = len(zones)
        zone_counts = defaultdict(int)
        for z in zones:
            zone_counts[z] += 1

        feats: Dict[str, float] = {
            # existing features — defender_distance now in feet
            "avg_defender_distance":   round(sum(dds) / len(dds), 1) if dds else 0.0,
            "shot_zone_paint_pct":     round(zone_counts.get("paint", 0) / n_shots, 3) if n_shots else 0.0,
            "shot_zone_mid_range_pct": round(zone_counts.get("mid_range", 0) / n_shots, 3) if n_shots else 0.0,
            "shot_zone_3pt_pct":       round((zone_counts.get("3pt_arc", 0)
                                              + zone_counts.get("corner_3", 0)) / n_shots, 3) if n_shots else 0.0,
            # contested = defender within 5 feet (applied to already-converted feet values)
            "contested_shot_rate":     round(sum(1 for d in dds if d < _CONTESTED_FT) / len(dds), 3)
                                       if dds else 0.0,
            "avg_spacing":             round(sum(spcs) / len(spcs), 1) if spcs else 0.0,
            "made_pct":                round(sum(made) / len(made), 3) if made else 0.0,
            # Bug 18 fix 2026-05-28: shot_clock_est OCR failures (Bug 20) leave 0.0
            # entries in scks even when n_shots>0. Filter zero entries; if all are
            # zero with shots present, emit None so the registry drops the row
            # (atlases will treat it as missing, not buzzer-beater zeros).
            "avg_shot_clock_at_shot":  (
                round(sum(v for v in scks if v > 0) / max(1, sum(1 for v in scks if v > 0)), 1)
                if any(v > 0 for v in scks) else (None if n_shots > 0 else 0.0)
            ),
            "n_shots_tracked":         float(n_shots),
            # new CV-moat features
            "avg_contest_arm_angle":   round(sum(arm_angles) / len(arm_angles), 3) if arm_angles else 0.0,
            # Bug 35: shot_log.csv has no closeout_speed column; the unified_pipeline
            # lookup rarely fires (R10 widened window still misses). Always-zero → None.
            "avg_closeout_speed":      round(sum(closeout_speeds) / len(closeout_speeds), 3) if closeout_speeds else None,
            "avg_fatigue_proxy":       round(sum(fatigue_proxies) / len(fatigue_proxies), 3) if fatigue_proxies else 0.0,
            "catch_shoot_pct":         round(sum(catch_shoot) / len(catch_shoot), 3) if catch_shoot else 0.0,
            "avg_dribble_count":       round(sum(dribble_counts) / len(dribble_counts), 3) if dribble_counts else 0.0,
            "second_chance_rate":      round(sum(second_chances) / len(second_chances), 3) if second_chances else 0.0,
            "avg_shot_distance":       round(sum(shot_distances) / len(shot_distances), 3) if shot_distances else 0.0,
        }

        # We need the player's team to look up possession features.
        # Best guess: from shot_log (tracker uses green/white team labels).
        player_team = ""
        if os.path.exists(shot_path):
            with open(shot_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        if int(row.get("player_id", -1) or -1) == pid:
                            player_team = str(row.get("team", "")).strip()
                            break
                    except (ValueError, TypeError):
                        pass

        pf = team_poss_feats.get(player_team, {})
        n_poss = pf.get("total_possessions", 0)
        feats.update({
            "shots_per_possession":     round(n_shots / n_poss, 3) if n_poss else 0.0,
            "possession_duration_avg":  pf.get("possession_duration_avg", 0.0),
            "play_type_transition_pct": pf.get("play_type_transition_pct", 0.0),
            "play_type_drive_pct":      pf.get("play_type_drive_pct", 0.0),
            "play_type_isolation_pct":  pf.get("play_type_isolation_pct", 0.0),
            "play_type_post_pct":       pf.get("play_type_post_pct", 0.0),
        })

        # ── Merge Tier-1 per-frame features ──────────────────────────────────
        # pid here is the slot_id from shot_log (tracker IDs 1-10).
        # tier1_by_slot is also keyed by slot_id (1-10).
        t1 = tier1_by_slot.get(pid, {})
        feats.update({
            "potential_assists":       t1.get("potential_assists",       0.0),
            "touches_per_game":        t1.get("touches_per_game",        0.0),
            "paint_dwell_pct":         t1.get("paint_dwell_pct",         0.0),
            "defender_approach_speed": t1.get("defender_approach_speed", 0.0),
            "preshot_velocity_peak":   t1.get("preshot_velocity_peak",   0.0),
        })

        result[pid] = feats

    # Also include slots from tier1 that have no shots but DO have frame data
    # (so touches_per_game / paint_dwell_pct are not lost for non-shooting slots).
    for slot_id, t1 in tier1_by_slot.items():
        if slot_id not in result:
            # No shot data for this slot — build a minimal feature dict
            result[slot_id] = {
                "avg_defender_distance":   0.0,
                "shot_zone_paint_pct":     0.0,
                "shot_zone_mid_range_pct": 0.0,
                "shot_zone_3pt_pct":       0.0,
                "contested_shot_rate":     0.0,
                "avg_spacing":             0.0,
                "made_pct":                0.0,
                "avg_shot_clock_at_shot":  0.0,
                "n_shots_tracked":         0.0,
                "avg_contest_arm_angle":   0.0,
                "avg_closeout_speed":      None,   # Bug 35: no source column
                "avg_fatigue_proxy":       0.0,
                "catch_shoot_pct":         0.0,
                "avg_dribble_count":       0.0,
                "second_chance_rate":      0.0,
                "avg_shot_distance":       0.0,
                "shots_per_possession":    0.0,
                "possession_duration_avg": 0.0,
                "play_type_transition_pct":0.0,
                "play_type_drive_pct":     None,   # Bug 35: never populated
                "play_type_isolation_pct": 0.0,
                "play_type_post_pct":      0.0,
                "potential_assists":       t1.get("potential_assists",       0.0),
                "touches_per_game":        t1.get("touches_per_game",        0.0),
                "paint_dwell_pct":         t1.get("paint_dwell_pct",         0.0),
                "defender_approach_speed": t1.get("defender_approach_speed", 0.0),
                "preshot_velocity_peak":   t1.get("preshot_velocity_peak",   0.0),
            }

    return result


def merge_into_features(
    features_df: "object",   # pd.DataFrame
    cv_dict: Dict[int, Dict[str, float]],
    player_id_col: str = "player_id",
) -> "object":
    """
    Merge CV feature dict into a features DataFrame.

    Args:
        features_df:   Existing features DataFrame.
        cv_dict:       Output of extract().
        player_id_col: Column in features_df holding integer player_id.

    Returns:
        DataFrame with new CV feature columns added (NaN where player not in cv_dict).
    """
    try:
        import pandas as pd
    except ImportError:
        return features_df

    if not cv_dict or features_df is None or len(features_df) == 0:
        return features_df

    cv_df = pd.DataFrame.from_dict(cv_dict, orient="index")
    cv_df.index.name = player_id_col
    cv_df = cv_df.reset_index()
    cv_df[player_id_col] = cv_df[player_id_col].astype(int)

    # Add cv_ prefix to distinguish from existing features
    rename_map = {c: f"cv_{c}" for c in cv_df.columns if c != player_id_col}
    cv_df = cv_df.rename(columns=rename_map)

    merged = features_df.merge(cv_df, on=player_id_col, how="left")
    n_with = merged[[c for c in merged.columns if c.startswith("cv_")]].notna().any(axis=1).sum()
    print(f"[tracking_feature_extractor] Merged {len(cv_dict)} CV feature sets "
          f"({n_with} feature rows enriched with CV data)")
    return merged
