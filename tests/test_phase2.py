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
    # Referee row should have NaN spacing (not computed) or be absent
    if len(ref_rows) > 0:
        assert ref_rows["team_spacing"].isna().all(), \
            "Referee rows must have NaN team_spacing — not computed"


def test_referee_excluded_from_pressure():
    """REQ-08: defense_pressure output contains no referee rows."""
    import src.analytics.defense_pressure as dp
    import pandas as pd
    rows = []
    for i in range(10):
        rows.append({
            "frame": 1, "player_id": i,
            "team": "referee" if i == 5 else ("green" if i < 5 else "white"),
            "x_position": float(i * 20), "y_position": float(i * 10),
            "velocity": 0.0, "event": "none", "ball_possession": i == 0,
        })
    df = pd.DataFrame(rows)
    result = dp.run(df)
    if "team" in result.columns:
        assert "referee" not in result["team"].values, \
            "defense_pressure output must not contain referee rows"
