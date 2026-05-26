"""tests/test_line_move_detector.py — unit tests for scripts/line_move_detector.py."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime

import pandas as pd
import pytest

# Load module from scripts/ since it's a CLI not a package
HERE = os.path.dirname(os.path.abspath(__file__))
LMD_PATH = os.path.join(os.path.dirname(HERE), "scripts", "line_move_detector.py")
spec = importlib.util.spec_from_file_location("line_move_detector", LMD_PATH)
lmd = importlib.util.module_from_spec(spec)
sys.modules["line_move_detector"] = lmd
spec.loader.exec_module(lmd)  # type: ignore


# ---------------------------------------------------------------------------
# 1. Line-delta math via classify_move
# ---------------------------------------------------------------------------
def test_classify_line_up_breaches_threshold():
    tags = lmd.classify_move(line_delta=0.5, odds_delta_pct=0.0,
                             threshold_line=0.5, threshold_odds_pct=10.0)
    assert "LINE_UP" in tags
    assert "LINE_DOWN" not in tags


def test_classify_line_down_below_threshold_skipped():
    tags = lmd.classify_move(line_delta=-0.4, odds_delta_pct=None,
                             threshold_line=0.5, threshold_odds_pct=10.0)
    assert tags == []


def test_classify_line_down_at_threshold():
    tags = lmd.classify_move(line_delta=-0.5, odds_delta_pct=None,
                             threshold_line=0.5, threshold_odds_pct=10.0)
    assert tags == ["LINE_DOWN"]


def test_classify_zero_delta_with_zero_threshold_is_noop():
    """A literal zero shift must not classify as a move, even if the threshold
    is zero (sanity probing)."""
    tags = lmd.classify_move(line_delta=0.0, odds_delta_pct=0.0,
                             threshold_line=0.0, threshold_odds_pct=0.0)
    assert tags == []


# ---------------------------------------------------------------------------
# 2. Odds-pct math
# ---------------------------------------------------------------------------
def test_american_implied_prob_basic():
    # -110 ≈ 0.5238
    assert abs(lmd.american_to_implied_prob(-110) - 0.5238) < 0.001
    # +110 ≈ 0.4762
    assert abs(lmd.american_to_implied_prob(110) - 0.4762) < 0.001
    # Invalid
    assert lmd.american_to_implied_prob("") is None
    assert lmd.american_to_implied_prob(0) is None


def test_odds_pct_delta_tighten_loosen():
    # -110 -> -150 = price got worse for over bettor (implied prob UP)
    d = lmd.odds_pct_delta(-110, -150)
    assert d is not None and d > 10  # >10% tighten
    tags = lmd.classify_move(line_delta=None, odds_delta_pct=d,
                             threshold_line=0.5, threshold_odds_pct=10.0)
    assert "ODDS_TIGHTEN" in tags

    # -150 -> -110 = price got better (loosen)
    d2 = lmd.odds_pct_delta(-150, -110)
    assert d2 is not None and d2 < -10
    tags2 = lmd.classify_move(line_delta=None, odds_delta_pct=d2,
                              threshold_line=0.5, threshold_odds_pct=10.0)
    assert "ODDS_LOOSEN" in tags2


def test_odds_pct_below_threshold_no_event():
    d = lmd.odds_pct_delta(-110, -115)  # tiny shift
    tags = lmd.classify_move(line_delta=None, odds_delta_pct=d,
                             threshold_line=0.5, threshold_odds_pct=10.0)
    assert tags == []


# ---------------------------------------------------------------------------
# 3. End-to-end detect_moves
# ---------------------------------------------------------------------------
def _df(rows):
    return pd.DataFrame(rows, columns=[
        "captured_at", "book", "game_id", "player_id", "player_name",
        "stat", "line", "over_price", "under_price", "start_time",
    ])


def test_detect_moves_line_jump():
    df = _df([
        ["2026-05-26T10:00:00", "fd", "1", "1", "LeBron James", "pts", 25.5, -110, -110, ""],
        ["2026-05-26T10:01:00", "fd", "1", "1", "LeBron James", "pts", 26.5, -110, -110, ""],
    ])
    events = lmd.detect_moves(df, threshold_line=0.5, threshold_odds_pct=10.0)
    assert len(events) == 1
    ev = events[0]
    assert ev["book"] == "fd"
    assert ev["line_delta"] == pytest.approx(1.0)
    assert "LINE_UP" in ev["tags"]


def test_detect_moves_ignores_single_snapshot_groups():
    df = _df([
        ["2026-05-26T10:00:00", "fd", "1", "1", "LeBron James", "pts", 25.5, -110, -110, ""],
    ])
    events = lmd.detect_moves(df, threshold_line=0.5, threshold_odds_pct=10.0)
    assert events == []


# ---------------------------------------------------------------------------
# 4. Cross-book consensus detection
# ---------------------------------------------------------------------------
def test_consensus_two_books_same_direction_within_window():
    df = _df([
        # fd: line UP
        ["2026-05-26T10:00:00", "fd",  "1", "1", "LeBron James", "pts", 25.5, -110, -110, ""],
        ["2026-05-26T10:01:00", "fd",  "1", "1", "LeBron James", "pts", 26.5, -110, -110, ""],
        # bov: line UP within 5 min
        ["2026-05-26T10:00:30", "bov", "1", "1", "LeBron James", "pts", 25.5, -110, -110, ""],
        ["2026-05-26T10:03:00", "bov", "1", "1", "LeBron James", "pts", 26.5, -110, -110, ""],
    ])
    events = lmd.detect_moves(df, threshold_line=0.5, threshold_odds_pct=10.0)
    events = lmd.tag_consensus(events, window_sec=300)
    assert len(events) == 2
    assert all(ev["consensus"] for ev in events)
    assert all("CONSENSUS_STEAM" in ev["tags"] for ev in events)


def test_consensus_not_set_when_directions_disagree():
    df = _df([
        ["2026-05-26T10:00:00", "fd",  "1", "1", "LeBron James", "pts", 25.5, -110, -110, ""],
        ["2026-05-26T10:01:00", "fd",  "1", "1", "LeBron James", "pts", 26.5, -110, -110, ""],  # UP
        ["2026-05-26T10:00:30", "bov", "1", "1", "LeBron James", "pts", 26.5, -110, -110, ""],
        ["2026-05-26T10:03:00", "bov", "1", "1", "LeBron James", "pts", 25.5, -110, -110, ""],  # DOWN
    ])
    events = lmd.detect_moves(df, threshold_line=0.5, threshold_odds_pct=10.0)
    events = lmd.tag_consensus(events, window_sec=300)
    assert len(events) == 2
    assert not any(ev["consensus"] for ev in events)


def test_consensus_not_set_outside_window():
    df = _df([
        ["2026-05-26T10:00:00", "fd",  "1", "1", "LeBron James", "pts", 25.5, -110, -110, ""],
        ["2026-05-26T10:01:00", "fd",  "1", "1", "LeBron James", "pts", 26.5, -110, -110, ""],
        ["2026-05-26T11:00:00", "bov", "1", "1", "LeBron James", "pts", 25.5, -110, -110, ""],
        ["2026-05-26T11:01:00", "bov", "1", "1", "LeBron James", "pts", 26.5, -110, -110, ""],
    ])
    events = lmd.detect_moves(df, threshold_line=0.5, threshold_odds_pct=10.0)
    events = lmd.tag_consensus(events, window_sec=300)
    assert not any(ev["consensus"] for ev in events)


# ---------------------------------------------------------------------------
# 5. Dedup of same event across daemon iterations
# ---------------------------------------------------------------------------
def test_dedup_event_keys_stable(tmp_path):
    cache = tmp_path / "line_moves_2026-05-26.json"
    ev = {
        "book": "fd", "name_key": "lebron james", "stat": "pts",
        "ts_from": "2026-05-26T10:00:00", "ts_to": "2026-05-26T10:01:00",
        "player_name": "LeBron James",
        "line_from": 25.5, "line_to": 26.5, "line_delta": 1.0,
        "odds_from": -110, "odds_to": -110, "odds_pct_delta": 0.0,
        "tags": ["LINE_UP"], "consensus": False,
    }
    lmd.append_events(str(cache), [ev])
    keys1 = lmd.load_existing_event_keys(str(cache))
    assert lmd.event_dedup_key(ev) in keys1
    # Second pass over the same data should be a no-op
    pre_size = cache.stat().st_size
    new_keys = [k for k in [lmd.event_dedup_key(ev)] if k not in keys1]
    assert new_keys == []
    # File not appended
    assert cache.stat().st_size == pre_size


def test_run_once_creates_artifacts(tmp_path):
    lines_dir = tmp_path / "lines"
    cache_dir = tmp_path / "cache"
    vault = tmp_path / "vault" / "line_moves.md"
    lines_dir.mkdir()
    cache_dir.mkdir()
    df = _df([
        ["2026-05-26T10:00:00", "fd", "1", "1", "LeBron James", "pts", 25.5, -110, -110, ""],
        ["2026-05-26T10:01:00", "fd", "1", "1", "LeBron James", "pts", 26.5, -110, -110, ""],
    ])
    df.to_csv(lines_dir / "2026-05-26_fd.csv", index=False)
    summary = lmd.run_once("2026-05-26", 0.5, 10.0,
                           lines_dir=str(lines_dir),
                           cache_dir=str(cache_dir),
                           vault_path=str(vault))
    assert summary["events_new"] == 1
    # Re-run should dedup
    summary2 = lmd.run_once("2026-05-26", 0.5, 10.0,
                            lines_dir=str(lines_dir),
                            cache_dir=str(cache_dir),
                            vault_path=str(vault))
    assert summary2["events_new"] == 0
    assert vault.exists()
    cache_file = cache_dir / "line_moves_2026-05-26.json"
    assert cache_file.exists()
    with open(cache_file) as f:
        lines = [ln for ln in f if ln.strip()]
    assert len(lines) == 1
