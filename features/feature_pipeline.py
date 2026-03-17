"""Feature pipeline CLI — Phase 2 integration module.

Queries tracking_coordinates for a given game, detects possession
boundaries and shot events (DB-03), then runs all feature modules
and writes results to the Phase 2 database tables.

Usage:
    python -m features.feature_pipeline --game-id <UUID>
"""

import argparse
import json
import logging
import math
import sys
import uuid

from tracking.database import get_connection
from features.spacing import compute_spacing
from features.defensive_pressure import compute_defensive_pressure
from features.off_ball_events import detect_off_ball_events
from features.pick_and_roll import detect_pick_and_roll
from features.passing_network import build_passing_network, export_network_graph
from features.momentum import compute_momentum
from features.play_recognition import detect_plays
from features.defensive_scheme import analyze_defensive_scheme
from features.space_control import compute_space_control
from features.drive_analysis import detect_drives
from features.shot_creation import classify_shot_creation
from features.rebound_positioning import estimate_rebound_positioning
from features.game_flow import compute_game_flow
from features.micro_timing import compute_micro_timing
from features.lineup_synergy import compute_lineup_synergy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Basket geometry constants (court feet)
# NBA baskets at x=4.75 and x=89.25, y=25.0
# ---------------------------------------------------------------------------
LEFT_BASKET_X_FT   = 4.75
RIGHT_BASKET_X_FT  = 89.25
BASKET_Y_FT        = 25.0
BASKET_ZONE_X_FT   = 12.0   # ball must be within 12ft of baseline to count
BASKET_ZONE_Y_FT   = 15.0   # ball must be within 15ft of court centerline

# Ball speed in ft/s (Kalman filter tracks in court feet)
SHOT_SPEED_THRESHOLD       = 8.0   # ft/s — minimum ball speed for a shot attempt
POSSESSION_SPEED_THRESHOLD = 3.0   # ft/s — ball essentially stationary = possession reset
POSSESSION_HELD_FRAMES     = 5     # consecutive slow frames = ball held


# ---------------------------------------------------------------------------
# Step 0a: Possession boundary detection
# ---------------------------------------------------------------------------

def _detect_possession_boundaries(
    ball_rows: list[dict],
    game_id: str,
    cursor,
) -> int:
    """Detect possession boundaries from ball tracking rows and INSERT into possessions.

    A new possession starts when the ball speed drops below POSSESSION_SPEED_THRESHOLD
    for POSSESSION_HELD_FRAMES or more consecutive frames (ball held/reset).

    Args:
        ball_rows: List of ball frame dicts with keys frame_number, speed, x, y.
        game_id: UUID string for the game.
        cursor: Active psycopg2 cursor.

    Returns:
        Number of possession rows inserted.
    """
    if not ball_rows:
        return 0

    # Smooth ball speed with a 5-frame moving average to reduce tracking noise
    speeds = [r["speed"] for r in ball_rows]
    window = 5
    smoothed = []
    for i in range(len(speeds)):
        lo = max(0, i - window // 2)
        hi = min(len(speeds), i + window // 2 + 1)
        smoothed.append(sum(speeds[lo:hi]) / (hi - lo))
    for i, row in enumerate(ball_rows):
        row = dict(row)
        row["speed"] = smoothed[i]
        ball_rows[i] = row

    # Find "held" frame runs — runs of >= POSSESSION_HELD_FRAMES slow frames
    slow_run_start: int | None = None
    slow_run_len = 0
    boundary_frames: list[int] = []  # frame numbers where possession starts

    for i, row in enumerate(ball_rows):
        if row["speed"] < POSSESSION_SPEED_THRESHOLD:
            if slow_run_start is None:
                slow_run_start = i
            slow_run_len += 1
            if slow_run_len == POSSESSION_HELD_FRAMES:
                # Mark the frame at the start of the slow run as a boundary
                boundary_frames.append(ball_rows[slow_run_start]["frame_number"])
        else:
            slow_run_start = None
            slow_run_len = 0

    if not boundary_frames:
        return 0

    # Build possession pairs from consecutive boundaries
    # Add the first frame as implicit start and last frame as implicit end
    all_boundaries = [ball_rows[0]["frame_number"]] + boundary_frames
    last_frame = ball_rows[-1]["frame_number"]

    inserted = 0
    for i, start_frame in enumerate(all_boundaries):
        if i + 1 < len(all_boundaries):
            end_frame = all_boundaries[i + 1] - 1
        else:
            end_frame = last_frame

        if end_frame <= start_frame:
            continue

        cursor.execute(
            """
            INSERT INTO possessions (id, game_id, team, start_frame, end_frame, outcome)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, NULL)
            ON CONFLICT DO NOTHING
            """,
            (game_id, "unknown", start_frame, end_frame),
        )
        inserted += 1

    return inserted


# ---------------------------------------------------------------------------
# Step 0b: Shot event detection
# ---------------------------------------------------------------------------

def _detect_shot_events(
    ball_rows: list[dict],
    game_id: str,
    cursor,
) -> int:
    """Detect shot events from ball tracking rows and INSERT into shot_logs.

    A shot is detected when ball speed > SHOT_SPEED_THRESHOLD and ball y-position
    is within BASKET_Y_TOLERANCE of BASKET_Y.

    For each detected shot, we query the nearest player at that frame_number to
    assign player_id.

    Args:
        ball_rows: List of ball frame dicts with frame_number, speed, x, y, direction_degrees.
        game_id: UUID string for the game.
        cursor: Active psycopg2 cursor.

    Returns:
        Number of shot_log rows inserted.
    """
    if not ball_rows:
        return 0

    inserted = 0
    last_shot_frame = -45  # cooldown: minimum 45 frames (~1.5s) between shots

    for row in ball_rows:
        speed = row.get("speed", 0.0) or 0.0
        frame_number = row.get("frame_number", 0)
        direction_degrees = row.get("direction_degrees")

        # All spatial checks in court feet
        bx_ft = float(row.get("x_ft") or row.get("x") or 0.0)
        by_ft = float(row.get("y_ft") or row.get("y") or 0.0)
        bx    = float(row.get("x", bx_ft) or bx_ft)
        by    = float(row.get("y", by_ft) or by_ft)

        # Speed threshold (ft/s)
        if speed <= SHOT_SPEED_THRESHOLD:
            continue

        # Cooldown: skip if a shot was already detected within the last 45 frames
        if frame_number - last_shot_frame < 45:
            continue

        # Ball must be near one of the two baskets
        near_left  = bx_ft < (LEFT_BASKET_X_FT  + BASKET_ZONE_X_FT)
        near_right = bx_ft > (RIGHT_BASKET_X_FT - BASKET_ZONE_X_FT)
        if not (near_left or near_right):
            continue

        # Ball must be within court width bounds (not a wildly off-court reading)
        if not (BASKET_Y_FT - BASKET_ZONE_Y_FT < by_ft < BASKET_Y_FT + BASKET_ZONE_Y_FT):
            continue

        # Shot type by distance from nearest basket
        left_dist  = math.sqrt((bx_ft - LEFT_BASKET_X_FT)**2  + (by_ft - BASKET_Y_FT)**2)
        right_dist = math.sqrt((bx_ft - RIGHT_BASKET_X_FT)**2 + (by_ft - BASKET_Y_FT)**2)
        basket_dist = min(left_dist, right_dist)
        shot_type = "3pt" if basket_dist > 22.0 else "2pt"

        # player_id not yet resolved (requires jersey OCR); leave NULL
        cursor.execute(
            """
            INSERT INTO shot_logs
                (id, game_id, player_id, frame_number, x, y, x_ft, y_ft, shot_type, made,
                 defender_distance, shot_angle)
            VALUES (gen_random_uuid(), %s, NULL, %s, %s, %s, %s, %s, %s, NULL, NULL, %s)
            ON CONFLICT DO NOTHING
            """,
            (game_id, frame_number, bx, by, bx_ft, by_ft, shot_type, direction_degrees),
        )
        inserted += 1
        last_shot_frame = frame_number

    return inserted


# ---------------------------------------------------------------------------
# Step 2: Spacing metrics
# ---------------------------------------------------------------------------

def _run_spacing_step(
    frames_by_number: dict[int, list[dict]],
    game_id: str,
    cursor,
    frame_sample_rate: int = 5,
) -> int:
    """Compute spacing metrics and batch-INSERT into feature_vectors.

    Returns number of rows written.
    """
    sorted_frames = sorted(frames_by_number.keys())
    sampled = sorted_frames[::frame_sample_rate]
    inserted = 0

    for fn in sampled:
        frame = frames_by_number[fn]
        players = [r for r in frame if r.get("object_type") != "ball"]
        if not players:
            continue

        positions = [(float(r["x"]), float(r["y"])) for r in players]
        timestamp_ms = float(players[0].get("timestamp_ms", 0.0))

        metrics = compute_spacing(positions, game_id, "", fn, timestamp_ms)

        cursor.execute(
            """
            INSERT INTO feature_vectors
                (id, game_id, frame_number, timestamp_ms,
                 convex_hull_area, avg_inter_player_dist,
                 nearest_defender_dist, closing_speed)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, NULL, NULL)
            ON CONFLICT DO NOTHING
            """,
            (
                game_id,
                fn,
                timestamp_ms,
                metrics.convex_hull_area,
                metrics.avg_inter_player_distance,
            ),
        )
        inserted += 1

    return inserted


# ---------------------------------------------------------------------------
# Step 3: Defensive pressure
# ---------------------------------------------------------------------------

def _run_defensive_pressure_step(
    frames_by_number: dict[int, list[dict]],
    game_id: str,
    cursor,
    frame_sample_rate: int = 5,
) -> int:
    """Compute defensive pressure and INSERT/UPDATE feature_vectors.

    Returns number of rows processed.
    """
    sorted_frames = sorted(frames_by_number.keys())
    sampled = sorted_frames[::frame_sample_rate]
    prev_distances: dict[int, float] = {}
    processed = 0

    for fn in sampled:
        frame = frames_by_number[fn]
        player_rows = [r for r in frame if r.get("object_type") != "ball"]
        if not player_rows:
            continue

        timestamp_ms = float(player_rows[0].get("timestamp_ms", 0.0))

        pressure_list = compute_defensive_pressure(
            player_rows, game_id, fn, timestamp_ms, prev_distances
        )

        for pressure in pressure_list:
            # Try UPDATE first; if no row exists, INSERT with NULL spacing columns
            cursor.execute(
                """
                UPDATE feature_vectors
                SET nearest_defender_dist = %s,
                    closing_speed = %s
                WHERE game_id = %s AND frame_number = %s
                """,
                (
                    pressure.nearest_defender_distance,
                    pressure.closing_speed,
                    game_id,
                    fn,
                ),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    """
                    INSERT INTO feature_vectors
                        (id, game_id, frame_number, timestamp_ms,
                         convex_hull_area, avg_inter_player_dist,
                         nearest_defender_dist, closing_speed)
                    VALUES (gen_random_uuid(), %s, %s, %s, NULL, NULL, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        game_id,
                        fn,
                        timestamp_ms,
                        pressure.nearest_defender_distance,
                        pressure.closing_speed,
                    ),
                )

        processed += len(pressure_list)

    return processed


# ---------------------------------------------------------------------------
# Step 4: Off-ball events
# ---------------------------------------------------------------------------

def _run_off_ball_step(
    frames_by_number: dict[int, list[dict]],
    ball_by_frame: dict[int, dict | None],
    game_id: str,
    cursor,
    window_size: int = 10,
    stride: int = 5,
) -> int:
    """Detect off-ball events and INSERT into detected_events.

    Returns number of events inserted.
    """
    sorted_frames = sorted(frames_by_number.keys())
    inserted = 0

    for i in range(0, max(1, len(sorted_frames) - window_size + 1), stride):
        window_fn = sorted_frames[i: i + window_size]
        if not window_fn:
            continue

        window_frames = [
            [r for r in frames_by_number[fn] if r.get("object_type") != "ball"]
            for fn in window_fn
        ]
        last_fn = window_fn[-1]
        ball_pos = ball_by_frame.get(last_fn)

        events = detect_off_ball_events(window_frames, game_id, ball_pos)

        for ev in events:
            cursor.execute(
                """
                INSERT INTO detected_events
                    (id, game_id, event_type, track_id, frame_number,
                     confidence, metadata)
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, NULL)
                ON CONFLICT DO NOTHING
                """,
                (
                    game_id,
                    ev.event_type,
                    ev.track_id,
                    ev.frame_number,
                    ev.confidence,
                ),
            )
            inserted += 1

    return inserted


# ---------------------------------------------------------------------------
# Step 5: Pick-and-roll
# ---------------------------------------------------------------------------

def _run_pick_and_roll_step(
    frames_by_number: dict[int, list[dict]],
    game_id: str,
    cursor,
    window_size: int = 10,
    stride: int = 5,
) -> int:
    """Detect pick-and-roll events and INSERT into detected_events.

    Returns number of events inserted.
    """
    sorted_frames = sorted(frames_by_number.keys())
    inserted = 0

    for i in range(0, max(1, len(sorted_frames) - window_size + 1), stride):
        window_fn = sorted_frames[i: i + window_size]
        if not window_fn:
            continue

        window_frames = [
            [r for r in frames_by_number[fn] if r.get("object_type") != "ball"]
            for fn in window_fn
        ]

        events = detect_pick_and_roll(window_frames, game_id)

        for ev in events:
            metadata = json.dumps({"screener_track_id": ev.screener_track_id})
            cursor.execute(
                """
                INSERT INTO detected_events
                    (id, game_id, event_type, track_id, frame_number,
                     confidence, metadata)
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    game_id,
                    "pick_and_roll",
                    ev.ball_handler_track_id,
                    ev.frame_number,
                    1.0,
                    metadata,
                ),
            )
            inserted += 1

    return inserted


# ---------------------------------------------------------------------------
# Step 6: Passing network
# ---------------------------------------------------------------------------

def _run_passing_network_step(
    frames_by_number: dict[int, list[dict]],
    ball_by_frame: dict[int, dict | None],
    game_id: str,
    cursor,
) -> int:
    """Build passing network per possession and log edges to stdout.

    Returns total number of edges logged.
    """
    sorted_frames = sorted(frames_by_number.keys())

    # Query possessions for this game
    cursor.execute(
        """
        SELECT id, team, start_frame, end_frame
        FROM possessions
        WHERE game_id = %s
        ORDER BY start_frame
        """,
        (game_id,),
    )
    possessions = cursor.fetchall()

    total_edges = 0

    if possessions:
        for poss_id, team, start_frame, end_frame in possessions:
            # Collect frames within this possession's range
            poss_fns = [fn for fn in sorted_frames if start_frame <= fn <= end_frame]
            if not poss_fns:
                continue

            possession_frames = [
                [r for r in frames_by_number[fn] if r.get("object_type") != "ball"]
                for fn in poss_fns
            ]
            ball_frames = [ball_by_frame.get(fn) for fn in poss_fns]

            edges = build_passing_network(
                possession_frames, game_id, str(poss_id), ball_frames
            )

            for edge in edges:
                print(json.dumps({
                    "game_id": edge.game_id,
                    "possession_id": edge.possession_id,
                    "from_track_id": edge.from_track_id,
                    "to_track_id": edge.to_track_id,
                    "count": edge.count,
                }))
                total_edges += 1
    else:
        # No possessions detected — treat full game as one possession
        possession_frames = [
            [r for r in frames_by_number[fn] if r.get("object_type") != "ball"]
            for fn in sorted_frames
        ]
        ball_frames = [ball_by_frame.get(fn) for fn in sorted_frames]

        edges = build_passing_network(
            possession_frames, game_id, "game-level", ball_frames
        )
        for edge in edges:
            print(json.dumps({
                "game_id": edge.game_id,
                "possession_id": edge.possession_id,
                "from_track_id": edge.from_track_id,
                "to_track_id": edge.to_track_id,
                "count": edge.count,
            }))
            total_edges += 1

    return total_edges


# ---------------------------------------------------------------------------
# Step 7: Momentum
# ---------------------------------------------------------------------------

def _run_momentum_step(game_id: str, cursor) -> int:
    """Query shot_logs, compute momentum snapshots, INSERT into momentum_snapshots.

    Returns number of rows inserted.
    """
    cursor.execute(
        """
        SELECT player_id, frame_number, x, y, shot_type, made
        FROM shot_logs
        WHERE game_id = %s
        ORDER BY frame_number
        """,
        (game_id,),
    )
    shot_rows = cursor.fetchall()

    if not shot_rows:
        logger.warning("No shot_logs rows for game_id=%s; skipping momentum step", game_id)
        return 0

    # Build shot_event dicts; team is unknown without possession data
    shot_events = []
    for i, (player_id, frame_number, x, y, shot_type, made) in enumerate(shot_rows):
        shot_events.append({
            "team": "unknown",
            "made": bool(made) if made is not None else False,
            "possession_num": i,  # treat each shot as its own possession index
            "timestamp_ms": float(frame_number) * 33.33,  # approx ms from frame at 30fps
            "game_id": game_id,
        })

    snapshots = compute_momentum(shot_events, game_id)

    inserted = 0
    for snap in snapshots:
        cursor.execute(
            """
            INSERT INTO momentum_snapshots
                (id, game_id, segment_id, scoring_run, possession_streak,
                 swing_point, timestamp_ms)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                game_id,
                snap.segment_id,
                snap.scoring_run,
                snap.possession_streak,
                snap.swing_point,
                snap.timestamp_ms,
            ),
        )
        inserted += 1

    return inserted


# ---------------------------------------------------------------------------
# Main pipeline runner
# ---------------------------------------------------------------------------

def _check_homography_valid(ball_rows: list[dict]) -> bool:
    """Return True if x_ft values are within valid NBA court bounds (0-94 ft)."""
    if not ball_rows:
        return False
    ft_vals = [r["x_ft"] for r in ball_rows if r.get("x_ft") is not None]
    if not ft_vals:
        return False
    return -5.0 <= min(ft_vals) and max(ft_vals) <= 99.0


def run_feature_pipeline(game_id: str) -> None:
    """Execute the full feature pipeline for a game.

    Steps:
        0a. Detect possession boundaries → INSERT into possessions
        0b. Detect shot events → INSERT into shot_logs
        1.  Query tracking_coordinates
        2.  Spacing metrics → INSERT into feature_vectors
        3.  Defensive pressure → INSERT/UPDATE feature_vectors
        4.  Off-ball events → INSERT into detected_events
        5.  Pick-and-roll events → INSERT into detected_events
        6.  Passing network → log to stdout (JSON lines)
        7.  Momentum snapshots → INSERT into momentum_snapshots

    Args:
        game_id: UUID string of the game to process.
    """
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # -----------------------------------------------------------
                # Step 0a: Possession boundary detection
                # -----------------------------------------------------------
                cur.execute(
                    """
                    SELECT frame_number, timestamp_ms, x, y, COALESCE(x_ft, x) as x_ft, COALESCE(y_ft, y) as y_ft, speed, direction_degrees
                    FROM tracking_coordinates
                    WHERE game_id = %s AND object_type = 'ball'
                    ORDER BY frame_number
                    """,
                    (game_id,),
                )
                ball_rows_raw = cur.fetchall()

                if not ball_rows_raw:
                    logger.warning(
                        "No ball rows in tracking_coordinates for game_id=%s; "
                        "skipping possession and shot detection",
                        game_id,
                    )
                    ball_rows = []
                else:
                    ball_rows = [
                        {
                            "frame_number": r[0],
                            "timestamp_ms": r[1],
                            "x": r[2],
                            "y": r[3],
                            "x_ft": r[4],
                            "y_ft": r[5],
                            "speed": r[6] or 0.0,
                            "direction_degrees": r[7],
                        }
                        for r in ball_rows_raw
                    ]

                homography_valid = _check_homography_valid(ball_rows)
                if not homography_valid:
                    print("[Warning] Homography invalid or out of court bounds — "
                          "shot/drive/possession detection skipped (coordinates not in feet).")

                poss_count = _detect_possession_boundaries(ball_rows, game_id, cur) if homography_valid else 0
                print(f"[Step 0a] possession boundaries: records_processed={len(ball_rows)}, records_written={poss_count}")

                # -----------------------------------------------------------
                # Step 0b: Shot event detection
                # -----------------------------------------------------------
                shot_count = _detect_shot_events(ball_rows, game_id, cur) if homography_valid else 0
                print(f"[Step 0b] shot events: records_processed={len(ball_rows)}, records_written={shot_count}")

                # -----------------------------------------------------------
                # Step 1: Query full tracking_coordinates
                # -----------------------------------------------------------
                cur.execute(
                    """
                    SELECT frame_number, timestamp_ms,
                           COALESCE(x_ft, x) AS x, COALESCE(y_ft, y) AS y,
                           velocity_x, velocity_y, speed, direction_degrees,
                           object_type, track_id
                    FROM tracking_coordinates
                    WHERE game_id = %s
                    ORDER BY frame_number, object_type
                    """,
                    (game_id,),
                )
                all_rows = cur.fetchall()

                # Organize by frame number
                frames_by_number: dict[int, list[dict]] = {}
                ball_by_frame: dict[int, dict | None] = {}

                for r in all_rows:
                    fn = r[0]
                    row_dict = {
                        "frame_number": r[0],
                        "timestamp_ms": r[1],
                        "x": r[2],  # court feet (COALESCE x_ft, x)
                        "y": r[3],  # court feet (COALESCE y_ft, y)
                        "velocity_x": r[4],
                        "velocity_y": r[5],
                        "speed": r[6] or 0.0,
                        "direction_degrees": r[7],
                        "object_type": r[8],
                        "track_id": r[9],
                        "team": None,  # team assignment deferred to future phase
                    }
                    frames_by_number.setdefault(fn, []).append(row_dict)
                    if r[8] == "ball":
                        ball_by_frame[fn] = {"x": r[2], "y": r[3]}

                total_frames = len(frames_by_number)
                sorted_frames = sorted(frames_by_number.keys())
                print(f"[Step 1] loaded tracking data: frames={total_frames}, rows={len(all_rows)}")

                # -----------------------------------------------------------
                # Step 2: Spacing metrics
                # -----------------------------------------------------------
                spacing_count = _run_spacing_step(frames_by_number, game_id, cur)
                print(f"[Step 2] spacing metrics: records_processed={total_frames}, records_written={spacing_count}")

                # -----------------------------------------------------------
                # Step 3: Defensive pressure
                # -----------------------------------------------------------
                pressure_count = _run_defensive_pressure_step(frames_by_number, game_id, cur)
                print(f"[Step 3] defensive pressure: records_processed={total_frames}, records_written={pressure_count}")

                # -----------------------------------------------------------
                # Step 4: Off-ball events
                # -----------------------------------------------------------
                off_ball_count = _run_off_ball_step(frames_by_number, ball_by_frame, game_id, cur)
                print(f"[Step 4] off-ball events: records_processed={total_frames}, records_written={off_ball_count}")

                # -----------------------------------------------------------
                # Step 5: Pick-and-roll
                # -----------------------------------------------------------
                pnr_count = _run_pick_and_roll_step(frames_by_number, game_id, cur)
                print(f"[Step 5] pick-and-roll: records_processed={total_frames}, records_written={pnr_count}")

                # -----------------------------------------------------------
                # Step 6: Passing network (stdout only, no DB write in Phase 2)
                # -----------------------------------------------------------
                edge_count = _run_passing_network_step(
                    frames_by_number, ball_by_frame, game_id, cur
                )
                print(f"[Step 6] passing network: records_processed={total_frames}, records_written={edge_count}")

                # -----------------------------------------------------------
                # Step 7: Momentum
                # -----------------------------------------------------------
                momentum_count = _run_momentum_step(game_id, cur)
                print(f"[Step 7] momentum snapshots: records_processed=N/A, records_written={momentum_count}")

                # -----------------------------------------------------------
                # Step 8: Play Recognition
                # -----------------------------------------------------------
                play_count = 0
                cur.execute("SELECT id, start_frame, end_frame FROM possessions WHERE game_id = %s ORDER BY start_frame", (game_id,))
                possession_rows = cur.fetchall()
                for poss_id, start_f, end_f in possession_rows:
                    if end_f is None:
                        continue
                    plays = detect_plays(frames_by_number, start_f, end_f, game_id)
                    for play in plays:
                        cur.execute("""
                            INSERT INTO play_detections
                                (game_id, play_type, play_start_frame, play_end_frame,
                                 primary_track_ids, confidence)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                        """, (game_id, play.play_type, int(play.play_start_frame),
                              int(play.play_end_frame),
                              [int(t) for t in play.primary_track_ids],
                              float(play.confidence)))
                        play_count += 1
                print(f"[Step 8] play recognition: records_written={play_count}")

                # -----------------------------------------------------------
                # Step 9: Defensive Scheme Detection
                # -----------------------------------------------------------
                scheme_count = 0
                for poss_id, start_f, end_f in possession_rows:
                    if end_f is None:
                        continue
                    poss_fns = [fn for fn in sorted_frames if start_f <= fn <= end_f]
                    snapshots = analyze_defensive_scheme(frames_by_number, poss_fns)
                    for snap in snapshots:
                        cur.execute("""
                            INSERT INTO defensive_schemes
                                (game_id, possession_id, frame_number, scheme_label,
                                 switch_frequency, help_frequency, paint_collapse_frequency,
                                 weakside_rotation_speed, cohesion_score)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (game_id, str(poss_id), int(snap.frame_number), snap.scheme_label,
                              float(snap.switch_frequency), float(snap.help_frequency),
                              float(snap.paint_collapse_frequency),
                              float(snap.weakside_rotation_speed),
                              float(snap.cohesion_score)))
                        scheme_count += 1
                print(f"[Step 9] defensive schemes: records_written={scheme_count}")

                # -----------------------------------------------------------
                # Step 10: Drive Analysis
                # -----------------------------------------------------------
                drives = detect_drives(frames_by_number, sorted_frames) if homography_valid else []
                drive_count = 0
                for drive in drives:
                    cur.execute("""
                        INSERT INTO drive_events
                            (game_id, track_id, start_frame, end_frame,
                             drive_angle_to_rim, penetration_depth, defender_beaten,
                             help_arrival_frames, outcome,
                             blow_by_probability, drive_kick_probability, foul_probability)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (game_id, int(drive.track_id), int(drive.start_frame), int(drive.end_frame),
                          float(drive.drive_angle_to_rim), float(drive.penetration_depth),
                          bool(drive.defender_beaten),
                          int(drive.help_arrival_frames) if drive.help_arrival_frames is not None else None,
                          drive.outcome,
                          float(drive.blow_by_probability), float(drive.drive_kick_probability),
                          float(drive.foul_probability)))
                    drive_count += 1
                print(f"[Step 10] drive events: records_written={drive_count}")

                # -----------------------------------------------------------
                # Step 11: Shot Creation + Rebound Positioning
                # -----------------------------------------------------------
                cur.execute("""
                    SELECT id, frame_number, x_ft, y_ft, player_id
                    FROM shot_logs WHERE game_id = %s
                """, (game_id,))
                shot_rows_full = cur.fetchall()

                creation_count = 0
                rebound_count = 0

                # Build possession start lookup by frame number
                poss_by_frame = {}
                for poss_id, start_f, end_f in possession_rows:
                    if end_f is None:
                        continue
                    for fn in range(start_f, end_f + 1):
                        poss_by_frame[fn] = (poss_id, start_f)

                for shot_id, shot_fn, sx_ft, sy_ft, _ in shot_rows_full:
                    if shot_fn not in frames_by_number:
                        continue

                    # Shot creation
                    frame_players = [r for r in frames_by_number.get(shot_fn, [])
                                     if r.get("object_type") == "player"]
                    if frame_players:
                        ball = next((r for r in frames_by_number.get(shot_fn, [])
                                     if r.get("object_type") == "ball"), None)
                        shooter_id = None
                        if ball:
                            bpos = (ball.get("x_ft", ball["x"]), ball.get("y_ft", ball["y"]))
                            nearest = min(frame_players, key=lambda p: (
                                (p.get("x_ft", p["x"]) - bpos[0])**2 +
                                (p.get("y_ft", p["y"]) - bpos[1])**2
                            ))
                            shooter_id = nearest["track_id"]

                        if shooter_id is not None:
                            poss_start = poss_by_frame.get(shot_fn, (None, shot_fn - 90))[1]
                            creation = classify_shot_creation(
                                shot_fn, shooter_id, poss_start, frames_by_number
                            )
                            cur.execute("""
                                INSERT INTO shot_creation_events
                                    (game_id, shot_log_id, creation_type,
                                     creation_difficulty, creation_space, creation_time)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT DO NOTHING
                            """, (game_id, str(shot_id), creation.creation_type,
                                  float(creation.creation_difficulty),
                                  float(creation.creation_space),
                                  float(creation.creation_time)))
                            creation_count += 1

                    # Rebound positioning
                    sx = sx_ft if sx_ft else 47.0
                    sy = sy_ft if sy_ft else 25.0
                    rebounds = estimate_rebound_positioning(shot_fn, frames_by_number, sx, sy)
                    for reb in rebounds:
                        cur.execute("""
                            INSERT INTO rebound_events
                                (game_id, frame_number, rebounding_track_id,
                                 rebound_probability, positioning_advantage,
                                 boxout_success, offensive_crash)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (game_id, int(reb.frame_number), int(reb.track_id),
                              float(reb.rebound_probability), float(reb.positioning_advantage),
                              bool(reb.boxout_success), bool(reb.offensive_crash)))
                        rebound_count += 1

                print(f"[Step 11] shot creation: {creation_count}, rebound events: {rebound_count}")

                # -----------------------------------------------------------
                # Step 12: Game Flow
                # -----------------------------------------------------------
                flow_count = 0
                possession_outcomes = []
                for _, start_f, end_f in possession_rows:
                    if end_f is None:
                        continue
                    duration = end_f - start_f
                    scored = any(
                        start_f <= s[1] <= end_f for s in shot_rows_full if s[3]
                    ) if shot_rows_full else False
                    possession_outcomes.append({"scored": scored, "duration_frames": duration})

                    flow = compute_game_flow(
                        possession_outcomes, start_f,
                        possession_number=len(possession_outcomes),
                    )
                    cur.execute("""
                        INSERT INTO game_flow
                            (game_id, frame_number, momentum_index,
                             scoring_run_probability, possession_pressure_index,
                             comeback_probability, offensive_flow_score)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (game_id, int(flow.frame_number), float(flow.momentum_index),
                          float(flow.scoring_run_probability),
                          float(flow.possession_pressure_index),
                          float(flow.comeback_probability),
                          float(flow.offensive_flow_score)))
                    flow_count += 1
                print(f"[Step 12] game flow: records_written={flow_count}")

                # -----------------------------------------------------------
                # Step 13: Micro Timing
                # -----------------------------------------------------------
                timing_events = compute_micro_timing(frames_by_number, sorted_frames)
                timing_count = 0
                for ev in timing_events:
                    cur.execute("""
                        INSERT INTO micro_timing_events
                            (game_id, track_id, frame_number, event_type,
                             catch_to_shot_time, catch_to_drive_time, catch_to_pass_time,
                             screen_to_drive_time, decision_latency)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (game_id,
                          int(ev.track_id) if ev.track_id is not None else None,
                          int(ev.frame_number), ev.event_type,
                          float(ev.catch_to_shot_time) if ev.catch_to_shot_time is not None else None,
                          float(ev.catch_to_drive_time) if ev.catch_to_drive_time is not None else None,
                          float(ev.catch_to_pass_time) if ev.catch_to_pass_time is not None else None,
                          float(ev.screen_to_drive_time) if ev.screen_to_drive_time is not None else None,
                          float(ev.decision_latency) if ev.decision_latency is not None else None))
                    timing_count += 1
                print(f"[Step 13] micro timing: records_written={timing_count}")

                # -----------------------------------------------------------
                # Step 14: Lineup Synergy
                # -----------------------------------------------------------
                synergy_snapshots = compute_lineup_synergy(frames_by_number, sorted_frames)
                synergy_count = 0
                for snap in synergy_snapshots:
                    cur.execute("""
                        INSERT INTO lineup_synergy
                            (game_id, frame_number, track_ids,
                             spacing_quality, ball_movement_score,
                             defensive_cohesion, offensive_gravity, synergy_index)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (game_id, int(snap.frame_number),
                          [int(t) for t in snap.track_ids],
                          float(snap.spacing_quality), float(snap.ball_movement_score),
                          float(snap.defensive_cohesion), float(snap.offensive_gravity),
                          float(snap.synergy_index)))
                    synergy_count += 1
                print(f"[Step 14] lineup synergy: records_written={synergy_count}")

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="features.feature_pipeline",
        description=(
            "NBA AI feature pipeline — processes a game and writes all "
            "Phase 2 features (spacing, defensive pressure, off-ball events, "
            "pick-and-roll, passing network, momentum) to the database."
        ),
    )
    parser.add_argument(
        "--game-id",
        required=True,
        metavar="UUID",
        help="UUID of the game to process (must exist in tracking_coordinates)",
    )
    return parser


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    parser = _build_parser()
    args = parser.parse_args()
    run_feature_pipeline(args.game_id)
