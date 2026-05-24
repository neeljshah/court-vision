"""Tests for scripts/poll_line_movement.py (cycle 88g, loop 5).

Fully offline - no DK / FD / Action Network network calls. Mocks
`collect_props` + `refresh_action_network` via injection parameters.
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.poll_line_movement as pm  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _prop(player, stat, line, over_odds=-110, under_odds=-110):
    return {"player": player, "stat": stat, "line": line,
            "over_odds": over_odds, "under_odds": under_odds}


def _snap_dict(props):
    """Convert a props list into the diff_snapshots-ready map."""
    return {((p["player"]).lower().strip(), p["stat"].lower().strip()):
            {"line": float(p["line"]),
             "over_odds": int(p["over_odds"]),
             "under_odds": int(p["under_odds"])}
            for p in props}


# ── diff correctness ─────────────────────────────────────────────────────────

def test_diff_snapshots_computes_line_delta_and_move_type():
    """Line moves up 1.0 with odds unchanged -> move_type 'line'.
    Line same with odds shift -> 'odds_only'. Both -> 'both'.
    """
    prev = _snap_dict([
        _prop("Jokic", "pts", 28.5, -110, -110),
        _prop("Curry", "fg3m", 4.5, -120, +100),
        _prop("Tatum", "ast", 5.5, -110, -110),
    ])
    curr = _snap_dict([
        _prop("Jokic", "pts", 29.5, -110, -110),   # line up 1.0
        _prop("Curry", "fg3m", 4.5, -130, +110),   # odds shift only
        _prop("Tatum", "ast", 6.5, -120, -100),    # both
    ])
    rows = pm.diff_snapshots(prev, curr, "2026-05-24T17:00:00",
                              public_pct_lookup={})
    by_player = {r["player"]: r for r in rows}
    assert by_player["jokic"]["line_delta"] == "+1"
    assert by_player["jokic"]["move_type"] == "line"
    assert by_player["curry"]["line_delta"] == "+0"
    assert by_player["curry"]["move_type"] == "odds_only"
    assert by_player["tatum"]["move_type"] == "both"
    # Negative line delta formatting
    prev2 = _snap_dict([_prop("LeBron", "reb", 8.5)])
    curr2 = _snap_dict([_prop("LeBron", "reb", 7.5)])
    out = pm.diff_snapshots(prev2, curr2, "t", {})
    assert out[0]["line_delta"] == "-1"


def test_is_meaningful_threshold():
    """Sub-0.5 line moves with sub-10c odds shifts are suppressed."""
    # 0.4-line move + 5c odds shift -> NOT meaningful
    sub = {"line_delta": "+0.4", "prev_over_odds": -110,
           "new_over_odds": -115, "prev_under_odds": -110,
           "new_under_odds": -110}
    assert pm.is_meaningful(sub) is False
    # 0.5-line move -> meaningful
    edge = {"line_delta": "+0.5", "prev_over_odds": -110,
            "new_over_odds": -110, "prev_under_odds": -110,
            "new_under_odds": -110}
    assert pm.is_meaningful(edge) is True
    # 10c odds shift alone -> meaningful
    odds_only = {"line_delta": "+0", "prev_over_odds": -110,
                 "new_over_odds": -120, "prev_under_odds": -110,
                 "new_under_odds": -110}
    assert pm.is_meaningful(odds_only) is True


# ── RLM detection ────────────────────────────────────────────────────────────

def test_reverse_line_movement_detection_with_mocked_public_pct():
    """0.5+ line move + public_bets_pct < 60 -> RLM=Y.
    Same move with public_bets_pct >= 60 -> RLM=N (public is moving it).
    """
    prev = _snap_dict([
        _prop("Jokic", "pts", 28.5),
        _prop("Curry", "fg3m", 4.5),
    ])
    curr = _snap_dict([
        _prop("Jokic", "pts", 29.5),    # +1 line
        _prop("Curry", "fg3m", 5.5),    # +1 line
    ])
    public = {
        ("jokic", "pts"):  45.0,   # public NOT loading the over -> RLM
        ("curry", "fg3m"): 78.0,   # public IS loading the over -> just public action
    }
    rows = pm.diff_snapshots(prev, curr, "t", public)
    by_player = {r["player"]: r for r in rows}
    assert by_player["jokic"]["rlm"] == "Y"
    assert by_player["curry"]["rlm"] == "N"

    # Sub-threshold (0.5) line move is never RLM, regardless of public%
    prev3 = _snap_dict([_prop("Tatum", "reb", 8.5)])
    curr3 = _snap_dict([_prop("Tatum", "reb", 8.7)])   # +0.2 (below 0.5)
    rows3 = pm.diff_snapshots(prev3, curr3, "t", {("tatum", "reb"): 30.0})
    assert rows3[0]["rlm"] == "N"


# ── daemon loop ──────────────────────────────────────────────────────────────

def test_daemon_honors_interval_min_via_mocked_sleep():
    """Daemon calls sleep_fn(interval_sec) exactly once per poll iter."""
    calls = []

    def fake_sleep(sec):
        calls.append(sec)

    # Inject a no-op fetch so poll_once doesn't hit the network. The daemon
    # uses the real fetch_dk_props.collect_props but we override the module's
    # attribute for the duration of the test.
    real_collect = None
    try:
        import scripts.fetch_dk_props as fdp
        real_collect = fdp.collect_props
        fdp.collect_props = lambda books: []   # empty props -> trivial snapshot

        with tempfile.TemporaryDirectory() as tmp:
            snap_dir = os.path.join(tmp, "snapshots")
            log_dir  = tmp
            # Override module globals so poll_once writes into tmp.
            orig_snap, orig_log = pm._SNAP_DIR, pm._LOG_DIR
            pm._SNAP_DIR, pm._LOG_DIR = snap_dir, log_dir
            try:
                n = pm.run_daemon(books=["draftkings"], interval_min=5,
                                   sleep_fn=fake_sleep, max_iters=3)
            finally:
                pm._SNAP_DIR, pm._LOG_DIR = orig_snap, orig_log
    finally:
        if real_collect is not None:
            fdp.collect_props = real_collect

    assert n == 3
    # Daemon sleeps AFTER each poll except the last (max_iters guard).
    # 3 iterations -> 2 inter-poll sleeps each of 5 min = 300 s
    assert calls == [300, 300]


# ── snapshot path / accumulation ─────────────────────────────────────────────

def test_snapshot_path_includes_timestamp_so_files_accumulate():
    """Two polls 5 min apart write distinct paths, and the second can
    find the first via find_previous_snapshot."""
    with tempfile.TemporaryDirectory() as snap_dir:
        p1 = pm.snapshot_path("2026-05-24", "1700", snap_dir=snap_dir)
        p2 = pm.snapshot_path("2026-05-24", "1705", snap_dir=snap_dir)
        assert p1 != p2
        assert p1.endswith("2026-05-24_1700.csv")
        assert p2.endswith("2026-05-24_1705.csv")

        # Drop two real files and confirm previous-finder picks the earlier one
        pm.write_snapshot([_prop("Jokic", "pts", 28.5)], p1)
        pm.write_snapshot([_prop("Jokic", "pts", 29.5)], p2)
        prev = pm.find_previous_snapshot("2026-05-24", "1705",
                                          snap_dir=snap_dir)
        assert prev == p1
        # And for the very first poll of the day, there is no previous.
        none = pm.find_previous_snapshot("2026-05-24", "1700",
                                          snap_dir=snap_dir)
        assert none is None


# ── full poll_once end-to-end with mocked fetch + public lookup ──────────────

def test_poll_once_writes_log_and_flags_rlm(capsys):
    """End-to-end: 2 polls (mocked fetch returns different props each call),
    poll_once writes movement_log_<date>.csv with the RLM-flagged row.
    """
    polls = iter([
        [_prop("Jokic", "pts", 28.5),
         _prop("Curry", "fg3m", 4.5)],
        [_prop("Jokic", "pts", 30.0),       # +1.5 line
         _prop("Curry", "fg3m", 4.5,        # odds-only shift
               over_odds=-130, under_odds=+105)],
    ])

    def fake_fetch(books):
        return next(polls)

    def fake_public():
        return {("jokic", "pts"): 40.0,     # < 60 -> RLM
                ("curry", "fg3m"): 50.0}

    with tempfile.TemporaryDirectory() as tmp:
        snap_dir = os.path.join(tmp, "snapshots")
        # First poll: no diff yet. Force explicit HHMM stamps so both polls
        # write distinct snapshots regardless of wall-clock minute.
        snap1, rows1 = pm.poll_once(["draftkings"], date_str="2026-05-24",
                                      snap_dir=snap_dir, log_dir=tmp,
                                      fetch_fn=fake_fetch, public_fn=fake_public,
                                      hhmm="1700")
        assert rows1 == []
        snap2, rows2 = pm.poll_once(["draftkings"], date_str="2026-05-24",
                                      snap_dir=snap_dir, log_dir=tmp,
                                      fetch_fn=fake_fetch, public_fn=fake_public,
                                      hhmm="1705")
        assert snap1 != snap2
        # Two prop diffs: Jokic line, Curry odds_only.
        assert len(rows2) == 2
        by_player = {r["player"]: r for r in rows2}
        assert by_player["jokic"]["move_type"] == "line"
        assert by_player["jokic"]["rlm"] == "Y"     # +1.5 line, public 40 < 60
        assert by_player["curry"]["move_type"] == "odds_only"
        # Movement log file exists with both rows.
        log = os.path.join(tmp, "movement_log_2026-05-24.csv")
        assert os.path.exists(log)
        with open(log, encoding="utf-8") as fh:
            content = fh.read()
        assert "jokic" in content and "curry" in content
        # Stdout shows the RLM-STEAM marker for Jokic.
        captured = capsys.readouterr().out
        assert "RLM-STEAM" in captured
        assert "jokic" in captured


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
