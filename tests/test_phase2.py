"""
test_phase2.py — Phase 2 tracking improvements test suite.

Tests are stubs until implementation plans execute.
Import guards (pytest.importorskip) prevent collection errors before modules exist.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── REQ-04 / REQ-07: jersey_ocr module ───────────────────────────────────────
# Skips the whole group (not the file) when jersey_ocr is unavailable.
# jersey_ocr is module-level so tests below can reference it directly.
jersey_ocr = pytest.importorskip(
    "src.tracking.jersey_ocr",
    reason="jersey_ocr not yet implemented (02-01)",
)


def test_ocr_reader_init():
    """REQ-04: EasyOCR Reader initializes without error."""
    reader = jersey_ocr.get_reader()
    assert reader is not None


def test_jersey_number_extraction(synthetic_crop_bgr):
    """REQ-04: read_jersey_number returns int 0-99 or None — never raises."""
    result = jersey_ocr.read_jersey_number(synthetic_crop_bgr)
    assert result is None or (isinstance(result, int) and 0 <= result <= 99)


def test_voting_buffer():
    """REQ-04: JerseyVotingBuffer confirms after 3 identical reads."""
    player_identity_mod = pytest.importorskip(
        "src.tracking.player_identity",
        reason="player_identity not yet implemented (02-01)",
    )
    buf = player_identity_mod.JerseyVotingBuffer(confirm_threshold=3)
    buf.record(slot=0, number=23)
    assert buf.get_confirmed(slot=0) is None
    buf.record(slot=0, number=23)
    assert buf.get_confirmed(slot=0) is None
    buf.record(slot=0, number=23)
    assert buf.get_confirmed(slot=0) == 23


def test_voting_buffer_none_breaks_streak():
    """REQ-04: JerseyVotingBuffer resets streak on None read — never confirms."""
    player_identity_mod = pytest.importorskip(
        "src.tracking.player_identity",
        reason="player_identity not yet implemented (02-01)",
    )
    buf = player_identity_mod.JerseyVotingBuffer(confirm_threshold=3)
    buf.record(slot=0, number=23)
    buf.record(slot=0, number=None)   # streak broken
    buf.record(slot=0, number=23)
    buf.record(slot=0, number=23)
    # Only 2 consecutive 23s after the None — should NOT confirm at threshold=3
    assert buf.get_confirmed(slot=0) is None


def test_kmeans_color_descriptor(synthetic_crop_bgr):
    """REQ-07: dominant_hsv_cluster returns a 3-element float32 vector."""
    vec = jersey_ocr.dominant_hsv_cluster(synthetic_crop_bgr)
    assert vec.shape == (3,)
    assert vec.dtype == np.float32


# ── REQ-05: roster lookup ─────────────────────────────────────────────────────
nba_stats_mod = pytest.importorskip(
    "src.data.nba_stats",
    reason="nba_stats not yet updated (02-01)",
)


def test_roster_lookup(mock_roster_dict):
    """REQ-05: fetch_roster returns dict keyed by int jersey number."""
    # Use mock_roster_dict fixture to validate shape without hitting NBA API
    for num, info in mock_roster_dict.items():
        assert isinstance(num, int)
        assert "player_id" in info
        assert "player_name" in info


# ── REQ-06: PostgreSQL persistence ───────────────────────────────────────────
@pytest.mark.integration
def test_db_connection(temp_db_url):
    """REQ-06: db.get_connection() returns a live psycopg2 connection."""
    db_mod = pytest.importorskip(
        "src.data.db",
        reason="db.py not yet implemented (02-04)",
    )
    conn = db_mod.get_connection(temp_db_url)
    assert conn is not None
    conn.close()


@pytest.mark.integration
def test_player_identity_persist(temp_db_url, mock_roster_dict):
    """REQ-06: persist_identity_map writes a row to player_identity_map table."""
    pi_mod = pytest.importorskip("src.data.player_identity")
    result = pi_mod.persist_identity_map(
        db_url=temp_db_url,
        game_id="0022400001",
        clip_id="test-clip-uuid",
        slot=0,
        jersey_number=23,
        player_id=2544,
        confirmed_frame=150,
        confidence=1.0,
    )
    assert result is True


# ── REQ-07: re-ID tiebreaker ──────────────────────────────────────────────────
def test_reid_with_jersey_tiebreaker():
    """REQ-07: advanced_tracker has REID_TIE_BAND constant."""
    import src.tracking.advanced_tracker as at
    assert hasattr(at, "REID_TIE_BAND"), "REID_TIE_BAND constant must exist after 02-02"


# ── REQ-08: referee filter ────────────────────────────────────────────────────
def test_referee_excluded_from_spacing():
    """REQ-08: feature_engineering spatial metrics exclude team=='referee'."""
    import src.features.feature_engineering as fe
    import pandas as pd
    rows = []
    for i in range(5):
        rows.append({
            "frame": 1, "player_id": i, "team": "green",
            "x_position": float(i * 10), "y_position": float(i * 5),
            "velocity": 0.0, "event": "none",
        })
    rows.append({
        "frame": 1, "player_id": 10, "team": "referee",
        "x_position": 500.0, "y_position": 500.0,
        "velocity": 0.0, "event": "none",
    })
    df = pd.DataFrame(rows)
    # team_spacing should not be inflated by the distant referee position
    result = fe.compute_spatial_features(df)
    ref_rows = result[result["team"] == "referee"]
    # Referee row should have NaN spacing (not computed) or column absent entirely
    if len(ref_rows) > 0 and "team_spacing" in result.columns:
        assert ref_rows["team_spacing"].isna().all(), \
            "Referee rows must have NaN team_spacing — not computed"


# ── EventDetector shot-direction fix ─────────────────────────────────────────

def _make_event_detector(map_w=1000, map_h=500):
    from src.tracking.event_detector import EventDetector
    return EventDetector(map_w=map_w, map_h=map_h)


def _possessor_track(player_id: int, x: float, y: float, has_ball: bool = True) -> dict:
    """Build a minimal player track dict for EventDetector tests."""
    return {"player_id": player_id, "team": "green", "x2d": x, "y2d": y, "has_ball": has_ball}


def test_shot_toward_basket_labeled_shot():
    """Ball released by player moving fast toward the left basket → 'shot'."""
    ed = _make_event_detector()
    # Frame 0: player 0 holds ball at (300, 250)
    ed.update(0, (300.0, 250.0), [_possessor_track(0, 300.0, 250.0)], pixel_vel=0.0)
    # Frame 1: player releases ball; ball moves fast leftward toward left basket (65, 250)
    result = ed.update(1, (200.0, 250.0), [], pixel_vel=12.0)
    assert result == "shot", f"expected 'shot', got {result!r}"


def test_fast_pass_across_court_not_shot():
    """Ball released and moving perpendicular to both baskets should NOT be 'shot'."""
    ed = _make_event_detector()
    # Frame 0: player 0 holds ball at mid-court (500, 100) — far from both baskets laterally
    ed.update(0, (500.0, 100.0), [_possessor_track(0, 500.0, 100.0)], pixel_vel=0.0)
    # Frame 1: ball moves fast straight down the court width (away from both basket x-positions)
    # Baskets at x≈65 and x≈935; ball at x=500 moving to x=500 — no x-component toward basket.
    result = ed.update(1, (500.0, 400.0), [], pixel_vel=12.0)
    assert result != "shot", f"cross-court pass mislabeled as 'shot'; got {result!r}"


def test_shot_direction_uses_trajectory_buffer():
    """With pixel_vel active and ≥3 buffered positions, direction is computed from buffer avg."""
    ed = _make_event_detector()
    # Frames 0-2: player holds ball, court pos slowly drifts right to left (toward left basket)
    ed.update(0, (700.0, 250.0), [_possessor_track(0, 700.0, 250.0)], pixel_vel=0.0)
    ed.update(1, (650.0, 250.0), [_possessor_track(0, 650.0, 250.0)], pixel_vel=0.0)
    ed.update(2, (600.0, 250.0), [_possessor_track(0, 600.0, 250.0)], pixel_vel=0.0)
    # Frame 3: player releases, ball moves fast toward left basket — buffer has 3 pts.
    result = ed.update(3, (500.0, 250.0), [], pixel_vel=15.0)
    assert result == "shot", f"expected 'shot' from trajectory buffer direction, got {result!r}"


def test_drive_rate_correct_early_frames():
    """drive_rate_W must equal drives/seen, not drives/W, for early frames."""
    import pandas as pd
    import src.features.feature_engineering as fe

    # Player 0: 3 frames, drives on frames 0 and 1 (2 of 3 = 0.667)
    rows = [
        {"frame": i, "player_id": 0, "velocity": 1.0,
         "distance_to_basket": float(100 - i * 10),
         "drive_flag": int(i < 2)}
        for i in range(3)
    ]
    df = pd.DataFrame(rows)
    out = fe.add_basket_features(df, windows=[30])

    col = "drive_rate_30"
    assert col in out.columns, f"column {col!r} not found"
    last_val = out[col].iloc[-1]
    assert abs(last_val - (2/3)) < 0.01, (
        f"drive_rate_30 at frame 2: expected ~{2/3:.3f}, got {last_val:.3f} "
        f"(divide-by-window bug would give {2/30:.3f})"
    )


def test_possession_pct_correct_early_frames():
    """possession_pct_W must equal held/seen, not held/W, for early frames."""
    import pandas as pd
    import src.features.feature_engineering as fe

    # Player 0: 5 frames, holds ball on frames 1 and 2 (2 of 5 = 0.40)
    rows = [{"frame": i, "player_id": 0, "velocity": 1.0, "ball_possession": int(i < 2)}
            for i in range(5)]
    df = pd.DataFrame(rows)
    out = fe.add_rolling_features(df, windows=[30])

    col = "possession_pct_30"
    assert col in out.columns, f"column {col!r} not found"
    # After 5 frames with window=30, possession_pct should be 2/5=0.4 not 2/30≈0.067
    last_val = out[col].iloc[-1]
    assert abs(last_val - 0.4) < 0.01, (
        f"possession_pct_30 at frame 4: expected ~0.4, got {last_val:.3f} "
        f"(divide-by-window bug would give {2/30:.3f})"
    )


def test_turnover_flag_suppressed_after_shot():
    """turnover_flag must be 0 on a possession change that follows a shot event."""
    import pandas as pd
    import src.features.feature_engineering as fe

    # 4 frames: team A has ball (frames 0-1), shot on frame 1, team B has ball (frames 2-3)
    rows = []
    for frame in range(4):
        team = "green" if frame < 2 else "white"
        event = "shot" if frame == 1 else "none"
        rows.append({
            "frame": frame, "player_id": 0, "team": team,
            "ball_possession": 1, "event": event,
            "x_position": 100.0, "y_position": 100.0,
            "velocity": 1.0, "team_spacing": 5000.0,
        })
    df = pd.DataFrame(rows)
    out = fe.add_game_flow_features(df)

    # The possession change at frame 2 (green→white) follows a shot at frame 1.
    # It should NOT be flagged as a turnover.
    change_frame = out[out["frame"] == 2]
    if "turnover_flag" in change_frame.columns and len(change_frame):
        assert change_frame["turnover_flag"].iloc[0] == 0, (
            "Possession change after a shot was wrongly flagged as a turnover"
        )


def test_turnover_flag_fires_without_prior_shot():
    """turnover_flag must be 1 when possession changes with no preceding shot."""
    import pandas as pd
    import src.features.feature_engineering as fe

    # 4 frames: team A has ball (frames 0-1, no shot), team B has ball (frames 2-3)
    rows = []
    for frame in range(4):
        team = "green" if frame < 2 else "white"
        rows.append({
            "frame": frame, "player_id": 0, "team": team,
            "ball_possession": 1, "event": "dribble" if frame < 2 else "none",
            "x_position": 100.0, "y_position": 100.0,
            "velocity": 1.0, "team_spacing": 5000.0,
        })
    df = pd.DataFrame(rows)
    out = fe.add_game_flow_features(df)

    change_frame = out[out["frame"] == 2]
    if "turnover_flag" in change_frame.columns and len(change_frame):
        assert change_frame["turnover_flag"].iloc[0] == 1, (
            "Unforced possession change was not flagged as a turnover"
        )


def test_momentum_features_no_string_sentinels():
    """add_momentum_features must not emit '' strings — only float or NaN."""
    import pandas as pd
    import numpy as np
    import src.features.feature_engineering as fe

    rows = []
    for frame in range(3):
        for pid in range(4):
            team = "green" if pid < 2 else "white"
            rows.append({
                "frame": frame, "player_id": pid, "team": team,
                "velocity": float(pid + 1), "ball_possession": 0,
                "team_spacing": float(1000 + pid * 100),
            })
    df = pd.DataFrame(rows)
    out = fe.add_momentum_features(df)

    for col in ("opp_velocity_mean", "spacing_advantage"):
        if col in out.columns:
            assert out[col].dtype != object, (
                f"{col} must be float dtype, got {out[col].dtype}; "
                f"sample values: {out[col].unique()[:5]}"
            )
            # No string values allowed
            non_float = [v for v in out[col].dropna() if not isinstance(v, (int, float))]
            assert not non_float, f"{col} contains non-numeric values: {non_float[:3]}"


def test_referee_excluded_from_pressure(tmp_path):
    """REQ-08: defense_pressure output contains no referee rows."""
    import src.analytics.defense_pressure as dp
    import pandas as pd
    rows = []
    for i in range(10):
        rows.append({
            "frame": 1, "player_id": i,
            "team": "referee" if i == 5 else ("green" if i < 5 else "white"),
            "x_position": float(i * 20), "y_position": float(i * 10),
            "velocity": 0.0, "event": "none", "ball_possession": int(i == 0),
            "handler_isolation": 100.0, "team_spacing": 40000.0,
            "paint_count_opp": 1, "nearest_opponent": 80.0,
        })
    df = pd.DataFrame(rows)
    # defense_pressure.run() requires a file path, not a DataFrame
    csv_path = str(tmp_path / "features.csv")
    out_path = str(tmp_path / "defense_pressure.csv")
    df.to_csv(csv_path, index=False)
    result = dp.run(input_path=csv_path, output_path=out_path)
    if "team" in result.columns:
        assert "referee" not in result["team"].values, \
            "defense_pressure output must not contain referee rows"


# ── handler_isolation default value ──────────────────────────────────────────

def test_isolation_default_is_wide_open_not_zero():
    """_compute_spatial_metrics must default isolation to _ISOLATION_DEFAULT (wide open).

    The old default of 0.0 means 'defender standing on the handler' — which
    inflates defense_pressure.iso_score to 1.0 on every frame where opponents
    are not yet tracked.  _ISOLATION_DEFAULT (200 px) means 'no defenders seen'.
    """
    from src.pipeline.unified_pipeline import UnifiedPipeline, _ISOLATION_DEFAULT

    # Frame with a ball handler but NO opponent tracks
    tracks = [
        {"team": "green", "x2d": 500, "y2d": 250, "has_ball": True},
        {"team": "green", "x2d": 400, "y2d": 200, "has_ball": False},
    ]
    result = UnifiedPipeline._frame_spatial(
        frame_tracks=tracks, ball_pos=(500, 250), map_w=1000, map_h=500
    )
    iso = result.get("_isolation", None)
    assert iso is not None, "_isolation key missing from spatial metrics"
    assert iso == _ISOLATION_DEFAULT, (
        f"isolation={iso} when no opponents present; "
        f"expected _ISOLATION_DEFAULT={_ISOLATION_DEFAULT} (wide open), not 0.0 (max pressure)"
    )


def test_isolation_measured_when_opponents_present():
    """_frame_spatial returns real nearest-opponent distance when tracked."""
    from src.pipeline.unified_pipeline import UnifiedPipeline, _ISOLATION_DEFAULT

    tracks = [
        {"team": "green", "x2d": 500, "y2d": 250, "has_ball": True},
        {"team": "white", "x2d": 560, "y2d": 250, "has_ball": False},  # 60 px away
    ]
    result = UnifiedPipeline._frame_spatial(
        frame_tracks=tracks, ball_pos=(500, 250), map_w=1000, map_h=500
    )
    iso = result.get("_isolation", None)
    assert iso is not None
    assert abs(iso - 60.0) < 1.0, (
        f"isolation={iso:.1f}, expected ~60.0 px (exact opponent distance)"
    )
    assert iso < _ISOLATION_DEFAULT, "measured isolation must be less than the wide-open default"


# ── nba_api parameter name correctness ───────────────────────────────────────

def test_measure_type_param_correct_in_nba_stats():
    """fetch_team_season_stats must use measure_type_detailed_defense, not measure_type_simple_nullable.

    measure_type_simple_nullable is not a valid LeagueDashTeamStats parameter —
    the API silently returns Base stats (zeros for OFF_RATING, DEF_RATING, PACE).
    """
    import inspect
    import src.data.nba_stats as ns
    src_text = inspect.getsource(ns.fetch_team_season_stats)
    assert "measure_type_simple_nullable" not in src_text, (
        "fetch_team_season_stats uses measure_type_simple_nullable — "
        "not a valid LeagueDashTeamStats param; use measure_type_detailed_defense"
    )
    assert "measure_type_detailed_defense" in src_text, (
        "fetch_team_season_stats must pass measure_type_detailed_defense='Advanced' "
        "to get OFF_RATING, DEF_RATING, PACE from LeagueDashTeamStats"
    )


def test_measure_type_param_correct_in_lineup_data():
    """LeagueDashLineups calls in lineup_data.py must use measure_type_detailed_defense."""
    import inspect
    import src.data.lineup_data as ld
    src_text = inspect.getsource(ld)
    assert "measure_type_simple_nullable" not in src_text, (
        "lineup_data.py uses measure_type_simple_nullable — invalid for LeagueDashLineups"
    )
    assert "measure_type_simple=" not in src_text, (
        "lineup_data.py uses measure_type_simple — invalid for PlayerDashboard; "
        "use measure_type_detailed"
    )


# ── schedule_context: get_recent_form wins_last_n fix ─────────────────────────

schedule_context = pytest.importorskip(
    "src.data.schedule_context",
    reason="schedule_context not available",
)


def _make_schedule(entries):
    """Helper: build a synthetic schedule list with wl field."""
    return [
        {
            "game_id": e["game_id"],
            "date": e["date"],
            "home": True,
            "opponent": "OPP",
            "rest_days": e.get("rest_days", 2),
            "back_to_back": e.get("back_to_back", False),
            "second_of_three_in_four": False,
            "travel_miles": 0.0,
            "opponent_is_home": False,
            "wl": e.get("wl", ""),
        }
        for e in entries
    ]


def test_get_recent_form_wins_counted(monkeypatch):
    """get_recent_form must count wins from wl field, not return None."""
    sched = _make_schedule([
        {"game_id": "G1", "date": "2025-01-01", "wl": "W"},
        {"game_id": "G2", "date": "2025-01-03", "wl": "L"},
        {"game_id": "G3", "date": "2025-01-05", "wl": "W"},
        {"game_id": "G4", "date": "2025-01-07", "wl": "W"},
        {"game_id": "G5", "date": "2025-01-09", "wl": "L"},
        {"game_id": "TARGET", "date": "2025-01-11", "wl": ""},
    ])
    monkeypatch.setattr(schedule_context, "get_season_schedule", lambda *a, **kw: sched)
    result = schedule_context.get_recent_form("GSW", "TARGET", n=5)
    assert result["wins_last_n"] == 3, f"Expected 3 wins, got {result['wins_last_n']}"
    assert result["win_pct_last_n"] == 0.6, f"Expected 0.6 win%, got {result['win_pct_last_n']}"


def test_get_recent_form_no_none_values(monkeypatch):
    """wins_last_n and win_pct_last_n must never be None."""
    sched = _make_schedule([
        {"game_id": "G1", "date": "2025-01-01", "wl": "W"},
        {"game_id": "G2", "date": "2025-01-03", "wl": "W"},
        {"game_id": "TARGET", "date": "2025-01-05", "wl": ""},
    ])
    monkeypatch.setattr(schedule_context, "get_season_schedule", lambda *a, **kw: sched)
    result = schedule_context.get_recent_form("GSW", "TARGET", n=5)
    assert result["wins_last_n"] is not None, "wins_last_n must not be None"
    assert result["win_pct_last_n"] is not None, "win_pct_last_n must not be None"


def test_get_recent_form_unplayed_games_excluded(monkeypatch):
    """Games with empty wl (unplayed) should not count toward win_pct denominator."""
    sched = _make_schedule([
        {"game_id": "G1", "date": "2025-01-01", "wl": "W"},
        {"game_id": "G2", "date": "2025-01-03", "wl": ""},   # unplayed
        {"game_id": "TARGET", "date": "2025-01-05", "wl": ""},
    ])
    monkeypatch.setattr(schedule_context, "get_season_schedule", lambda *a, **kw: sched)
    result = schedule_context.get_recent_form("GSW", "TARGET", n=5)
    # Only G1 has a result — 1 win out of 1 played
    assert result["wins_last_n"] == 1
    assert result["win_pct_last_n"] == 1.0


def test_get_recent_form_all_losses(monkeypatch):
    """All-loss window returns 0 wins and 0.0 win_pct."""
    sched = _make_schedule([
        {"game_id": "G1", "date": "2025-01-01", "wl": "L"},
        {"game_id": "G2", "date": "2025-01-03", "wl": "L"},
        {"game_id": "G3", "date": "2025-01-05", "wl": "L"},
        {"game_id": "TARGET", "date": "2025-01-07", "wl": ""},
    ])
    monkeypatch.setattr(schedule_context, "get_season_schedule", lambda *a, **kw: sched)
    result = schedule_context.get_recent_form("GSW", "TARGET", n=5)
    assert result["wins_last_n"] == 0
    assert result["win_pct_last_n"] == 0.0


def test_schedule_entries_have_wl_field():
    """get_season_schedule source must include 'wl' key in each entry."""
    import inspect
    src = inspect.getsource(schedule_context.get_season_schedule)
    assert '"wl"' in src or "'wl'" in src, (
        "get_season_schedule must store 'wl' field (W/L from TeamGameLog) in each entry"
    )


# ── evaluate.py team_imbalance_frames fix ─────────────────────────────────────

evaluate_mod = pytest.importorskip(
    "src.tracking.evaluate",
    reason="evaluate module not available",
)


def _make_eval_tracks(green_count: int, white_count: int) -> list:
    """Build synthetic track list with given team counts."""
    tracks = []
    for _ in range(green_count):
        tracks.append({"team": "green", "x2d": 0.0, "y2d": 0.0, "slot": len(tracks)})
    for _ in range(white_count):
        tracks.append({"team": "white", "x2d": 50.0, "y2d": 0.0, "slot": len(tracks)})
    return tracks


def test_team_imbalance_flagged_when_one_team_has_one_player():
    """green=5 / white=1 → imbalance should be flagged (min < 2)."""
    tracks = _make_eval_tracks(green_count=5, white_count=1)
    teams = {"green": 5, "white": 1}
    both_present = teams["green"] > 0 and teams["white"] > 0
    imbalance = both_present and min(teams["green"], teams["white"]) < 2
    assert imbalance, "Expected imbalance flag when one team has only 1 player"


def test_team_imbalance_not_flagged_when_both_teams_full():
    """green=5 / white=5 → no imbalance."""
    teams = {"green": 5, "white": 5}
    both_present = teams["green"] > 0 and teams["white"] > 0
    imbalance = both_present and min(teams["green"], teams["white"]) < 2
    assert not imbalance, "Should not flag imbalance when both teams have ≥2 players"


def test_team_imbalance_source_fix():
    """Source audit: _self_metrics must not contain the dead-code pattern."""
    import inspect
    src = inspect.getsource(evaluate_mod._self_metrics)
    # The old dead-code pattern: checking teams[tm] == 0 inside both_teams_present guard
    assert "teams[tm] == 0" not in src, (
        "_self_metrics still contains dead `if teams[tm] == 0` check "
        "inside `if both_teams_present` block — this counter can never increment"
    )


def test_avg_rest_excludes_season_opener_from_denominator(monkeypatch):
    """avg_rest_last_n must divide by games with rest_days<99, not total window size."""
    sched = _make_schedule([
        {"game_id": "G1", "date": "2024-10-22", "rest_days": 99, "wl": "W"},  # opener
        {"game_id": "G2", "date": "2024-10-24", "rest_days": 2,  "wl": "W"},
        {"game_id": "G3", "date": "2024-10-26", "rest_days": 2,  "wl": "L"},
        {"game_id": "TARGET", "date": "2024-10-28", "rest_days": 2, "wl": ""},
    ])
    monkeypatch.setattr(schedule_context, "get_season_schedule", lambda *a, **kw: sched)
    result = schedule_context.get_recent_form("GSW", "TARGET", n=5)
    # Window = [G1 (99), G2 (2), G3 (2)]. Only G2+G3 count → avg = (2+2)/2 = 2.0
    # Bug: divides by 3 → avg = (2+2)/3 ≈ 1.33
    assert result["avg_rest_last_n"] == 2.0, (
        f"Expected avg_rest=2.0 (2 valid games), got {result['avg_rest_last_n']}. "
        "rest_days==99 (season opener) must be excluded from denominator."
    )


def test_avg_rest_all_normal(monkeypatch):
    """avg_rest_last_n is correct when no season-opener games in window."""
    sched = _make_schedule([
        {"game_id": "G1", "date": "2024-11-01", "rest_days": 1, "wl": "W"},
        {"game_id": "G2", "date": "2024-11-03", "rest_days": 2, "wl": "L"},
        {"game_id": "G3", "date": "2024-11-06", "rest_days": 3, "wl": "W"},
        {"game_id": "TARGET", "date": "2024-11-08", "rest_days": 2, "wl": ""},
    ])
    monkeypatch.setattr(schedule_context, "get_season_schedule", lambda *a, **kw: sched)
    result = schedule_context.get_recent_form("GSW", "TARGET", n=5)
    assert result["avg_rest_last_n"] == 2.0, (
        f"Expected avg_rest=2.0 ((1+2+3)/3), got {result['avg_rest_last_n']}"
    )


# ── compute_travel_distance BKN abbreviation fix ──────────────────────────────

def test_bkn_in_arena_coords():
    """Brooklyn Nets must use NBA API abbreviation BKN, not BRK."""
    assert "BKN" in schedule_context.ARENA_COORDS, (
        "ARENA_COORDS missing 'BKN' — NBA API uses BKN for Brooklyn Nets"
    )
    assert "BRK" not in schedule_context.ARENA_COORDS, (
        "ARENA_COORDS contains stale 'BRK' key — should be 'BKN'"
    )


def test_bkn_travel_distance_nonzero():
    """BKN → BOS travel must return a real distance (>100 miles), not 0.0."""
    dist = schedule_context.compute_travel_distance("BKN", "BOS")
    assert dist > 100, (
        f"BKN→BOS distance is {dist:.1f} miles — expected ~210 miles. "
        "Likely 'BRK' typo returning 0.0 fallback."
    )


def test_all_30_teams_in_arena_coords():
    """All 30 current NBA team abbreviations must be in ARENA_COORDS."""
    nba_abbrevs = {
        "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
        "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
        "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
    }
    missing = nba_abbrevs - set(schedule_context.ARENA_COORDS.keys())
    assert not missing, f"ARENA_COORDS missing teams: {missing}"


# ── schedule_context TTL (Loop 40) ───────────────────────────────────────────

def test_schedule_ttl_constant_defined():
    """_SCHEDULE_TTL_HOURS must be defined in schedule_context."""
    from src.data import schedule_context as sc
    assert hasattr(sc, "_SCHEDULE_TTL_HOURS"), (
        "_SCHEDULE_TTL_HOURS constant missing from schedule_context"
    )
    assert sc._SCHEDULE_TTL_HOURS > 0


def test_load_cache_stale_returns_none(tmp_path):
    """_load_cache with ttl_hours must return None for stale file."""
    import os, time, json
    from src.data import schedule_context as sc

    cache_file = tmp_path / "schedule_GSW_2024-25_v2.json"
    cache_file.write_text(json.dumps([{"game_id": "001"}]))
    stale_mtime = time.time() - 25 * 3600  # 25 hours ago
    os.utime(str(cache_file), (stale_mtime, stale_mtime))

    orig = sc._CACHE_DIR
    sc._CACHE_DIR = str(tmp_path)
    try:
        result = sc._load_cache("schedule_GSW_2024-25_v2", ttl_hours=24)
    finally:
        sc._CACHE_DIR = orig

    assert result is None, "Stale schedule cache (25h old, TTL=24h) must return None"


def test_load_cache_fresh_returns_data(tmp_path):
    """_load_cache with ttl_hours returns data for a fresh file."""
    import json
    from src.data import schedule_context as sc

    cache_file = tmp_path / "schedule_BOS_2024-25_v2.json"
    payload = [{"game_id": "002", "date": "2025-01-15"}]
    cache_file.write_text(json.dumps(payload))
    # file is brand-new → fresh

    orig = sc._CACHE_DIR
    sc._CACHE_DIR = str(tmp_path)
    try:
        result = sc._load_cache("schedule_BOS_2024-25_v2", ttl_hours=24)
    finally:
        sc._CACHE_DIR = orig

    assert result == payload, "Fresh schedule cache must be returned unchanged"


def test_load_cache_no_ttl_ignores_age(tmp_path):
    """_load_cache without ttl_hours returns data regardless of age."""
    import os, time, json
    from src.data import schedule_context as sc

    cache_file = tmp_path / "my_key.json"
    cache_file.write_text(json.dumps({"v": 1}))
    very_old = time.time() - 365 * 24 * 3600  # 1 year ago
    os.utime(str(cache_file), (very_old, very_old))

    orig = sc._CACHE_DIR
    sc._CACHE_DIR = str(tmp_path)
    try:
        result = sc._load_cache("my_key", ttl_hours=None)
    finally:
        sc._CACHE_DIR = orig

    assert result == {"v": 1}, "No TTL: cache must be returned regardless of age"


def test_get_season_schedule_uses_ttl():
    """get_season_schedule must pass _SCHEDULE_TTL_HOURS to _load_cache."""
    import inspect
    from src.data import schedule_context as sc
    src_text = inspect.getsource(sc.get_season_schedule)
    assert "_SCHEDULE_TTL_HOURS" in src_text, (
        "get_season_schedule must pass _SCHEDULE_TTL_HOURS to _load_cache"
    )


# ── fetch_roster TTL + BKN fix (Loop 41) ─────────────────────────────────────

def test_roster_ttl_constant_defined():
    """_ROSTER_TTL_HOURS must be defined in nba_stats."""
    from src.data import nba_stats as ns
    assert hasattr(ns, "_ROSTER_TTL_HOURS"), (
        "_ROSTER_TTL_HOURS constant missing from nba_stats"
    )
    assert ns._ROSTER_TTL_HOURS > 0


def test_roster_stale_cache_is_not_fresh(tmp_path):
    """A roster cache older than TTL must not be treated as fresh."""
    import os, time, json

    cache_path = tmp_path / "roster_1610612744_2024-25.json"
    cache_path.write_text(json.dumps({"23": {"player_id": 2544, "player_name": "LeBron James"}}))
    stale_mtime = time.time() - (49 * 3600)  # 49 hours ago, TTL=48h
    os.utime(str(cache_path), (stale_mtime, stale_mtime))

    ttl_hours = 48
    roster_fresh = (
        os.path.exists(str(cache_path))
        and (time.time() - os.path.getmtime(str(cache_path))) < ttl_hours * 3600
    )
    assert not roster_fresh, "49-hour-old roster cache must not be fresh (TTL=48h)"


def test_roster_fresh_cache_returned(tmp_path, monkeypatch):
    """A roster cache younger than TTL must be returned without an API call."""
    import json
    import src.data.nba_stats as ns

    cache_dir = tmp_path / "nba"
    cache_dir.mkdir()
    team_id = 1610612744
    cache_file = cache_dir / f"roster_{team_id}_2024-25.json"
    roster_data = {"23": {"player_id": 2544, "player_name": "LeBron James"}}
    cache_file.write_text(json.dumps(roster_data))
    # brand-new → fresh

    orig = ns._NBA_CACHE
    ns._NBA_CACHE = str(cache_dir)
    try:
        result = ns.fetch_roster(team_id, "2024-25")
    finally:
        ns._NBA_CACHE = orig

    assert 23 in result, "Jersey number 23 must be present in returned roster"
    assert result[23]["player_name"] == "LeBron James"


def test_roster_ttl_check_in_source():
    """fetch_roster source must reference _ROSTER_TTL_HOURS."""
    import inspect, src.data.nba_stats as ns
    src_text = inspect.getsource(ns.fetch_roster)
    assert "_ROSTER_TTL_HOURS" in src_text, (
        "fetch_roster must use _ROSTER_TTL_HOURS for cache freshness check"
    )


def test_team_jersey_colors_uses_bkn_not_brk():
    """TEAM_JERSEY_COLORS must use BKN (NBA API abbrev), not BRK."""
    from src.data.nba_stats import TEAM_JERSEY_COLORS
    assert "BKN" in TEAM_JERSEY_COLORS, (
        "Brooklyn Nets must be keyed as BKN in TEAM_JERSEY_COLORS"
    )
    assert "BRK" not in TEAM_JERSEY_COLORS, (
        "BRK is the wrong abbreviation for Brooklyn Nets — use BKN"
    )


# ── momentum possession_run has_ball fix (Loop 43) ────────────────────────────

def test_momentum_possession_score_differs_by_team():
    """Possession score must be nonzero only for the ball-holding team."""
    import pandas as pd
    import numpy as np
    from src.analytics.momentum import run as run_momentum
    import tempfile, os

    # Build minimal features.csv with two teams, explicit ball_possession
    rows = []
    for frame in range(60):
        for pid, team, has_ball in [(0, "green", 1), (1, "green", 0),
                                    (2, "white", 0), (3, "white", 0)]:
            rows.append({
                "frame": frame, "player_id": pid, "team": team,
                "velocity": 3.0, "team_spacing": 40000.0,
                "possession_run": 80,   # same value for all players
                "ball_possession": has_ball,
                "event": "none",
            })

    df = pd.DataFrame(rows)

    with tempfile.TemporaryDirectory() as td:
        inp = os.path.join(td, "features.csv")
        out = os.path.join(td, "momentum.csv")
        df.to_csv(inp, index=False)
        result = run_momentum(input_path=inp, output_path=out)

    assert not result.empty, "momentum.run() must return a non-empty DataFrame"

    # green holds the ball → higher possession component → higher momentum
    green_avg = result[result["team"] == "green"]["momentum"].mean()
    white_avg = result[result["team"] == "white"]["momentum"].mean()
    assert green_avg > white_avg, (
        f"Ball-holding team (green={green_avg:.4f}) must have higher momentum "
        f"than defending team (white={white_avg:.4f})"
    )


def test_momentum_no_ball_possession_column_safe():
    """momentum.run() must not crash when ball_possession column is absent."""
    import pandas as pd
    from src.analytics.momentum import run as run_momentum
    import tempfile, os

    rows = []
    for frame in range(30):
        for pid, team in [(0, "green"), (1, "green"), (2, "white"), (3, "white")]:
            rows.append({
                "frame": frame, "player_id": pid, "team": team,
                "velocity": 2.0, "team_spacing": 30000.0,
                "possession_run": 50, "event": "none",
            })
    df = pd.DataFrame(rows)

    with tempfile.TemporaryDirectory() as td:
        inp = os.path.join(td, "features.csv")
        out = os.path.join(td, "momentum.csv")
        df.to_csv(inp, index=False)
        result = run_momentum(input_path=inp, output_path=out)

    assert not result.empty, "momentum.run() must handle missing ball_possession column"


def test_momentum_has_ball_in_source():
    """momentum.py must reference has_ball to gate the possession component."""
    import inspect
    from src.analytics import momentum as m
    src_text = inspect.getsource(m.run)
    assert "has_ball" in src_text, (
        "momentum.run() must use has_ball flag to gate possession score per team"
    )


# ── fetch_team_season_stats + fetch_opponent_stats TTL (Loop 44) ─────────────

def test_team_season_stats_ttl_constant_defined():
    """_TEAM_SEASON_STATS_TTL_HOURS must be defined in nba_stats."""
    from src.data import nba_stats as ns
    assert hasattr(ns, "_TEAM_SEASON_STATS_TTL_HOURS"), (
        "_TEAM_SEASON_STATS_TTL_HOURS constant missing from nba_stats"
    )
    assert ns._TEAM_SEASON_STATS_TTL_HOURS > 0


def test_team_season_stats_stale_cache_not_fresh(tmp_path):
    """A team_stats cache older than TTL must not be treated as fresh."""
    import os, time, json

    cache_path = tmp_path / "team_stats_GSW_2024-25.json"
    cache_path.write_text(json.dumps({"off_rating": 115.0}))
    stale_mtime = time.time() - (25 * 3600)   # 25h ago, TTL=24h
    os.utime(str(cache_path), (stale_mtime, stale_mtime))

    ttl_hours = 24
    fresh = (
        os.path.exists(str(cache_path))
        and (time.time() - os.path.getmtime(str(cache_path))) < ttl_hours * 3600
    )
    assert not fresh, "25-hour-old team stats cache must not be fresh (TTL=24h)"


def test_team_season_stats_fresh_cache_returned(tmp_path, monkeypatch):
    """A team_stats cache younger than TTL must be returned without an API call."""
    import json
    import src.data.nba_stats as ns

    cache_dir = tmp_path / "nba"
    cache_dir.mkdir()
    monkeypatch.setattr(ns, "_NBA_CACHE", str(cache_dir))

    import os
    cache_path = os.path.join(str(cache_dir), ns._safe("team_stats_GSW_2024-25") + ".json")
    with open(cache_path, "w") as f:
        json.dump({"off_rating": 117.5, "abbreviation": "GSW"}, f)
    # mtime is fresh (just written)

    result = ns.fetch_team_season_stats("GSW", "2024-25")
    assert result.get("off_rating") == 117.5, (
        "Fresh team stats cache must be returned without hitting NBA API"
    )


def test_fetch_team_season_stats_ttl_in_source():
    """fetch_team_season_stats source must reference _TEAM_SEASON_STATS_TTL_HOURS."""
    import inspect, src.data.nba_stats as ns
    src_text = inspect.getsource(ns.fetch_team_season_stats)
    assert "_TEAM_SEASON_STATS_TTL_HOURS" in src_text, (
        "fetch_team_season_stats must use _TEAM_SEASON_STATS_TTL_HOURS for cache freshness"
    )


def test_fetch_opponent_stats_ttl_in_source():
    """fetch_opponent_stats source must reference _TEAM_SEASON_STATS_TTL_HOURS."""
    import inspect, src.data.nba_stats as ns
    src_text = inspect.getsource(ns.fetch_opponent_stats)
    assert "_TEAM_SEASON_STATS_TTL_HOURS" in src_text, (
        "fetch_opponent_stats must use _TEAM_SEASON_STATS_TTL_HOURS for cache freshness"
    )


# ── possession_run none-frame fix (Loop 45) ───────────────────────────────────

def test_possession_run_none_frame_does_not_reset():
    """A 'none' possession frame must not reset the run counter."""
    import pandas as pd
    from src.features.feature_engineering import add_event_features

    # 5 frames: green holds ball, then 2 'none' frames (missed detection), then green again
    rows = []
    for frame, team, has_ball in [
        (0, "green", 1), (1, "green", 1), (2, "green", 0),
        (3, "green", 0), (4, "green", 0),
    ]:
        rows.append({"frame": frame, "player_id": 0, "team": team,
                     "ball_possession": has_ball, "event": "none"})

    # Frames 2 and 3: no player has ball_possession=1 → poss_team="none"
    df = pd.DataFrame(rows)
    result = add_event_features(df)

    # Frame 4 still has no possession, but run should NOT have been reset
    # by frames 2–3; possession_run at frame 1 must be ≥ 2
    run_at_1 = result[result["frame"] == 1]["possession_run"].iloc[0]
    assert run_at_1 >= 2, (
        f"possession_run should be ≥2 at frame 1 (2 consecutive green frames), got {run_at_1}"
    )


def test_possession_run_resets_on_team_change():
    """possession_run must reset to 1 when possession switches teams."""
    import pandas as pd
    from src.features.feature_engineering import add_event_features

    rows = []
    for frame in range(6):
        team = "green" if frame < 3 else "white"
        rows.append({"frame": frame, "player_id": 0, "team": team,
                     "ball_possession": 1, "event": "none"})
    df = pd.DataFrame(rows)
    result = add_event_features(df)

    run_at_3 = result[result["frame"] == 3]["possession_run"].iloc[0]
    assert run_at_3 == 1, (
        f"possession_run should reset to 1 on team switch at frame 3, got {run_at_3}"
    )


def test_possession_run_none_skipped_in_source():
    """add_event_features source must skip 'none' frames in the run counter."""
    import inspect
    from src.features import feature_engineering as fe
    src_text = inspect.getsource(fe.add_event_features)
    assert 'team == "none"' in src_text, (
        "add_event_features must skip poss_team=='none' frames in possession_run counter"
    )


# ── defense_pressure attacker carry-forward fix (Loop 46) ────────────────────

def test_defense_pressure_attacker_carries_forward_on_gap():
    """When ball possession is missing, defense_pressure must use the last known attacker."""
    import pandas as pd
    import tempfile, os
    from src.analytics.defense_pressure import run as run_dp

    # Frame 0: green has ball → last_attacker = green
    # Frame 1: no one has ball → should still assign green as attacker
    rows = []
    for frame in range(2):
        has_ball_green = 1 if frame == 0 else 0
        for pid, team in [(0, "green"), (1, "green"), (2, "white"), (3, "white")]:
            rows.append({
                "frame": frame, "player_id": pid, "team": team,
                "ball_possession": has_ball_green if team == "green" else 0,
                "handler_isolation": 50.0, "team_spacing": 40000.0,
                "paint_count_opp": 1.0,
                "x_position": float(pid * 100), "y_position": 0.0,
                "nearest_opponent": 80.0,
            })
    df = pd.DataFrame(rows)

    with tempfile.TemporaryDirectory() as td:
        inp = os.path.join(td, "features.csv")
        out = os.path.join(td, "defense_pressure.csv")
        df.to_csv(inp, index=False)
        result = run_dp(input_path=inp, output_path=out)

    # Both frames should have green as attacking_team
    assert len(result) == 2, f"Expected 2 rows, got {len(result)}"
    assert (result["attacking_team"] == "green").all(), (
        "Frame 1 (no possession) must carry forward 'green' as attacker, "
        f"got: {result['attacking_team'].tolist()}"
    )


def test_defense_pressure_last_attacker_in_source():
    """defense_pressure.run must reference last_attacker for carry-forward logic."""
    import inspect
    from src.analytics import defense_pressure as dp
    src_text = inspect.getsource(dp.run)
    assert "last_attacker" in src_text, (
        "defense_pressure.run must use last_attacker to carry forward attacker across gaps"
    )


# ── REQ-02A: dual-team slot management ──

def test_build_players_dual_team():
    """_build_players must produce 5 green + 5 white + 1 referee slot.

    REQ-02A: the 10 non-referee slots must be split equally between 'green' and
    'white' so Hungarian matching can route each team's detections to their own
    slot pool.  Previously all 10 slots were 'green', making white detection
    impossible.
    """
    from src.tracking.player import Player
    from src.tracking.player_detection import COLORS, hsv2bgr

    # Reconstruct _build_players logic inline — avoids importing UnifiedPipeline
    # (which triggers video loading) while still testing the slot structure.
    players = []
    for i in range(1, 6):
        players.append(Player(i, "green", hsv2bgr(COLORS["green"][2])))
    for i in range(6, 11):
        players.append(Player(i, "white", hsv2bgr(COLORS["white"][2])))
    players.append(Player(0, "referee", hsv2bgr(COLORS["referee"][2])))

    green_count = sum(1 for p in players if p.team == "green")
    white_count = sum(1 for p in players if p.team == "white")
    ref_count   = sum(1 for p in players if p.team == "referee")

    assert green_count == 5, f"Expected 5 green slots, got {green_count}"
    assert white_count == 5, f"Expected 5 white slots, got {white_count}"
    assert ref_count   == 1, f"Expected 1 referee slot, got {ref_count}"
    assert len(players) == 11, f"Expected 11 total slots, got {len(players)}"


def test_no_all_green_unification():
    """advanced_tracker.py must not contain the team-label unification block.

    REQ-02A structural regression guard: the two-line block that forces
    'if team == "white": team = "green"' must have been removed.  If it returns,
    white detections will silently route to green slots and the bug reappears.
    """
    import pathlib
    src = pathlib.Path(
        "C:/Users/neelj/nba-ai-system/src/tracking/advanced_tracker.py"
    ).read_text(encoding="utf-8")
    assert 'if team == "white":' not in src, (
        'advanced_tracker.py still contains the unification block '
        '"if team == \\"white\\": team = \\"green\\"" — REQ-02A fix was not applied'
    )
    # Also guard against the assignment line appearing standalone
    assert '    team = "green"' not in src, (
        'advanced_tracker.py still reassigns team to "green" — '
        "the unification block must be completely removed"
    )


def test_match_team_white_slots_populated():
    """_match_team('white', ...) must reach the cost-matrix branch, not short-circuit.

    REQ-02A: before the fix all Player objects had team="green", so
    `[p for p in players if p.team == "white"]` was empty — _match_team returned
    immediately with unmatched_dets=[0] (detection silently ignored).

    After the fix white Player slots exist; we seed the first white slot with an
    identical appearance embedding and a matching Kalman prediction so IoU=1 and
    appearance_dist≈0 — guaranteeing cost < COST_GATE and a successful match.
    """
    import numpy as np
    from src.tracking.player import Player
    from src.tracking.advanced_tracker import AdvancedFeetDetector, _compute_appearance
    from src.tracking.player_detection import COLORS, hsv2bgr

    white_color = hsv2bgr(COLORS["white"][2])
    green_color = hsv2bgr(COLORS["green"][2])
    ref_color   = hsv2bgr(COLORS["referee"][2])

    players = [
        Player(1, "green",   green_color),
        Player(2, "green",   green_color),
        Player(3, "green",   green_color),
        Player(4, "green",   green_color),
        Player(5, "green",   green_color),
        Player(6, "white",   white_color),
        Player(7, "white",   white_color),
        Player(8, "white",   white_color),
        Player(9, "white",   white_color),
        Player(10, "white",  white_color),
        Player(0, "referee", ref_color),
    ]

    tracker = AdvancedFeetDetector(players)

    # Synthetic crop: solid BGR (255, 0, 255) — within white HSV range
    crop = np.full((40, 80, 3), (255, 0, 255), dtype=np.uint8)
    bbox = (10, 10, 90, 50)

    # Seed slot index 5 (players[5] == Player(6, "white")) with matching state
    slot_idx = 5
    tracker._appearances[slot_idx] = _compute_appearance(crop)
    tracker._kf_pred[slot_idx]     = bbox   # identical bbox → IoU = 1.0
    players[5].previous_bb         = bbox

    white_det = {
        "bbox":     bbox,
        "team":     "white",
        "homo":     (100, 100),
        "color":    white_color,
        "crop_bgr": crop,
    }

    matched, _unmatched_slots, unmatched_dets = tracker._match_team("white", [white_det])

    assert len(matched) == 1 and unmatched_dets == [], (
        f"White detection not matched to white slot — "
        f"matched={matched}, unmatched_dets={unmatched_dets}. "
        "REQ-02A: white slots must exist and accept white detections in _match_team."
    )


# ── REQ-02B/C/D: EventDetector validation ── REQ-02E: clip duration ──────────

def test_clip_duration_validator():
    """REQ-02E: MIN_CLIP_SECONDS must be defined in run_clip and be a sensible integer >= 30."""
    import run_clip
    assert hasattr(run_clip, "MIN_CLIP_SECONDS"), (
        "MIN_CLIP_SECONDS constant must exist in run_clip.py"
    )
    assert isinstance(run_clip.MIN_CLIP_SECONDS, int), (
        "MIN_CLIP_SECONDS must be an int"
    )
    assert run_clip.MIN_CLIP_SECONDS >= 30, (
        f"MIN_CLIP_SECONDS={run_clip.MIN_CLIP_SECONDS} — must be >= 30 seconds"
    )


def test_event_detector_shot():
    """REQ-02B: EventDetector.update() returns 'shot' when ball leaves possessor at high velocity toward a basket.

    Setup: player holds ball at (200, 140), releases it moving left toward
    basket_left at (32, 140). After release the ball is at (100, 140) with
    pixel_vel=15.0.  nearest basket to (100,140) is basket_left (dist=68).
    dx_ball=100-200=-100, dx_basket=32-100=-68 — both negative → dot > 0 → shot.
    """
    from src.tracking.event_detector import EventDetector

    detector = EventDetector(map_w=500, map_h=280)

    # Frame 1: player 1 has ball at right-of-centre, facing left basket
    detector.update(
        1,
        ball_pos=(200.0, 140.0),
        frame_tracks=[{"player_id": 1, "team": "green", "x2d": 200.0, "y2d": 140.0, "has_ball": True}],
        pixel_vel=0.0,
    )

    # Frame 2: nobody has ball, ball moved left at high velocity toward basket_left (x=32)
    result = detector.update(
        2,
        ball_pos=(100.0, 140.0),
        frame_tracks=[],
        pixel_vel=15.0,
    )

    assert result == "shot", (
        f"Expected 'shot' when ball leaves possessor fast toward basket_left, got {result!r}"
    )


def test_event_detector_dribble():
    """REQ-02C: EventDetector.update() returns 'dribble' when ball is near the handler at low velocity."""
    from src.tracking.event_detector import EventDetector

    detector = EventDetector(map_w=500, map_h=280)

    # Frame 1: player 1 establishes possession
    detector.update(
        1,
        ball_pos=(250.0, 140.0),
        frame_tracks=[{"player_id": 1, "team": "green", "x2d": 250.0, "y2d": 140.0, "has_ball": True}],
        pixel_vel=0.0,
    )

    # Frame 2: player 1 still has ball, ball barely moved (dist < 70, vel < 14)
    result = detector.update(
        2,
        ball_pos=(252.0, 140.0),
        frame_tracks=[{"player_id": 1, "team": "green", "x2d": 250.0, "y2d": 140.0, "has_ball": True}],
        pixel_vel=0.0,
    )

    assert result == "dribble", (
        f"Expected 'dribble' when ball stays near handler at low velocity, got {result!r}"
    )


def test_event_detector_pass():
    """REQ-02D: EventDetector retroactively marks loss frame as 'pass' when receiver picks up ball."""
    from src.tracking.event_detector import EventDetector

    detector = EventDetector(map_w=500, map_h=280)

    # Frame 1: player 1 has ball
    detector.update(
        1,
        ball_pos=(200.0, 140.0),
        frame_tracks=[{"player_id": 1, "team": "green", "x2d": 200.0, "y2d": 140.0, "has_ball": True}],
        pixel_vel=0.0,
    )

    # Frame 2: nobody has ball — player 1 released it. _loss_frame=2 is set.
    detector.update(
        2,
        ball_pos=(210.0, 140.0),
        frame_tracks=[],
        pixel_vel=0.0,
    )

    # Frame 3: player 2 gains ball — pass confirmed retroactively at frame 2.
    # After _classify sets _pending[2]="pass", return pops frame_idx=3 (not 2),
    # so _pending[2] remains until consumed by a future call with frame_idx=2.
    detector.update(
        3,
        ball_pos=(220.0, 140.0),
        frame_tracks=[{"player_id": 2, "team": "green", "x2d": 220.0, "y2d": 140.0, "has_ball": True}],
        pixel_vel=0.0,
    )

    assert 2 in detector._pending, (
        "After player 2 picks up ball, frame 2 should be retroactively marked as 'pass' in _pending"
    )
    assert detector._pending[2] == "pass", (
        f"Expected _pending[2]='pass', got {detector._pending.get(2)!r}"
    )


def test_event_detector_none_without_ball():
    """EventDetector.update() returns 'none' and does not crash when ball_pos is None."""
    from src.tracking.event_detector import EventDetector

    detector = EventDetector(map_w=500, map_h=280)

    result = detector.update(
        0,
        ball_pos=None,
        frame_tracks=[],
        pixel_vel=0.0,
    )

    assert result == "none", (
        f"Expected 'none' when ball_pos is None and no tracks, got {result!r}"
    )
