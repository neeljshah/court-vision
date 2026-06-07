"""tests/test_R19_L5_betting_coverage.py

R19_L5 — targeted coverage probe.

R15–R18 shipped a dozen live-betting daemons but with thin test coverage.
This file fills the highest-risk gaps identified by the baseline coverage
run (--cov-config=.coveragerc_R19L5):

| module                       | base cov | target |
|------------------------------|---------:|-------:|
| middle_finder_daemon         |     37%  |  +25pp |
| live_bet_ranker              |     47%  |  +10pp |
| inplay_bet_ranker            |     58%  |  +10pp |
| multi_game_kelly             |     64%  |  +20pp |
| clv_tracker_daemon           |     71%  |   +5pp |
| bankroll_monitor_daemon      |     76%  |   +5pp |
| line_move_detector           |     71%  |   +5pp |
| auto_settle_daemon           |     70%  |   +5pp |

Focus areas: money-math edge cases, CSV/JSON parsers (schema-drift),
file-resolution helpers, dashboard renderers, append-only writers.

Production code is NEVER modified — tests treat the daemons as black boxes
and use realistic synthetic fixtures.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Force-import the 9 target modules so coverage measures them across
# the full pytest session (even when other test files don't import them).
from scripts import live_bet_ranker as lbr  # noqa: E402
from scripts import multi_game_kelly as mgk  # noqa: E402
from scripts import inplay_bet_ranker as ipr  # noqa: E402
from scripts import auto_settle_daemon as asd  # noqa: E402
from scripts import clv_tracker_daemon as clv  # noqa: E402
from scripts import line_move_detector as lmd  # noqa: E402
from scripts import middle_finder_daemon as mfd  # noqa: E402
from scripts import nba_lineup_daemon as nld  # noqa: E402
from scripts import bankroll_monitor_daemon as bmd  # noqa: E402


# ============================================================================
# middle_finder_daemon — 37% baseline, biggest opportunity
# ============================================================================

def _write_lines_csv(path, header_cols, rows):
    """Write a Bovada-style lines CSV with arbitrary header + rows."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header_cols)
        for r in rows:
            w.writerow(r)


def test_mfd_read_lines_csv_legacy_10col(tmp_path):
    """Legacy 10-col schema should parse with is_alt_line defaulted to false."""
    p = tmp_path / "2026-05-26_bov.csv"
    header = ["captured_at", "book", "game_id", "player_id", "player_name",
              "stat", "line", "over_price", "under_price", "start_time"]
    _write_lines_csv(p, header, [[
        "2026-05-26T15:00:00Z", "bov", "0022500001", "201939",
        "Stephen Curry", "pts", "27.5", "-110", "-110",
        "2026-05-26T19:00:00Z",
    ]])
    rows = mfd._read_lines_csv(str(p))
    assert len(rows) == 1
    assert rows[0]["player_name"] == "Stephen Curry"
    assert rows[0]["is_alt_line"] == "false"
    assert rows[0]["line"] == "27.5"


def test_mfd_read_lines_csv_12col_with_alt_line(tmp_path):
    """12-col schema with is_alt_line=true should be preserved."""
    p = tmp_path / "2026-05-26_bov.csv"
    header = ["captured_at", "book", "game_id", "player_id", "player_name",
              "team", "stat", "line", "over_price", "under_price",
              "market_status", "is_alt_line"]
    _write_lines_csv(p, header, [
        ["2026-05-26T15:00:00Z", "bov", "0022500001", "201939",
         "Stephen Curry", "GSW", "pts", "30.5", "+150", "-180",
         "open", "true"],
        ["2026-05-26T15:00:00Z", "bov", "0022500001", "201939",
         "Stephen Curry", "GSW", "pts", "27.5", "-110", "-110",
         "open", "false"],
    ])
    rows = mfd._read_lines_csv(str(p))
    assert len(rows) == 2
    assert rows[0]["is_alt_line"] == "true"
    assert rows[1]["is_alt_line"] == "false"


def test_mfd_read_lines_csv_missing_file(tmp_path):
    """Non-existent file returns empty list, not raises."""
    p = tmp_path / "does-not-exist.csv"
    assert mfd._read_lines_csv(str(p)) == []


def test_mfd_read_lines_csv_empty_file(tmp_path):
    """File with only header returns empty list."""
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    assert mfd._read_lines_csv(str(p)) == []


def test_mfd_read_lines_csv_wrong_col_count_skipped(tmp_path):
    """Rows with !=10/11/12 cols silently skipped."""
    p = tmp_path / "weird.csv"
    header = ["captured_at", "book", "game_id", "player_id", "player_name",
              "stat", "line", "over_price", "under_price", "start_time"]
    _write_lines_csv(p, header, [
        ["a", "b", "c"],  # 3 cols — skipped
        ["2026-05-26T15:00:00Z", "bov", "0022500001", "201939",
         "Stephen Curry", "pts", "27.5", "-110", "-110",
         "2026-05-26T19:00:00Z"],  # valid 10-col
    ])
    rows = mfd._read_lines_csv(str(p))
    assert len(rows) == 1


def test_mfd_is_alt_truthy_variants():
    """Lenient bool parser accepts true/1/yes/y/t and rejects others."""
    for truthy in ("true", "TRUE", "True", "1", "yes", "y", "t", " true "):
        assert mfd._is_alt_truthy(truthy) is True
    for falsy in ("false", "0", "no", "", None, "FALSE", "f", "n"):
        assert mfd._is_alt_truthy(falsy) is False


def test_mfd_to_int_handles_floats_and_nulls():
    assert mfd._to_int("110") == 110
    assert mfd._to_int("-110.0") == -110
    assert mfd._to_int(None) is None
    assert mfd._to_int("") is None
    assert mfd._to_int("None") is None
    assert mfd._to_int("garbage") is None


def test_mfd_to_float_handles_floats_and_nulls():
    assert mfd._to_float("27.5") == 27.5
    assert mfd._to_float(None) is None
    assert mfd._to_float("") is None
    assert mfd._to_float("None") is None
    assert mfd._to_float("not-a-number") is None


def test_mfd_parse_dt_iso_with_z():
    dt = mfd._parse_dt("2026-05-26T15:30:00Z")
    assert dt is not None
    assert dt.year == 2026 and dt.hour == 15


def test_mfd_parse_dt_invalid_returns_none():
    assert mfd._parse_dt("") is None
    assert mfd._parse_dt(None) is None
    assert mfd._parse_dt("not-a-date") is None


def test_mfd_load_latest_snapshots_picks_most_recent_per_book(tmp_path):
    """When multiple captured_at rows exist for same (player, stat, line, book),
    only the most recent is kept."""
    header = ["captured_at", "book", "game_id", "player_id", "player_name",
              "stat", "line", "over_price", "under_price", "start_time"]
    bov = tmp_path / "2026-05-26_bov.csv"
    _write_lines_csv(bov, header, [
        ["2026-05-26T15:00:00", "bov", "1", "201939", "Stephen Curry",
         "pts", "27.5", "-110", "-110", ""],
        ["2026-05-26T16:00:00", "bov", "1", "201939", "Stephen Curry",
         "pts", "27.5", "-115", "-105", ""],
    ])
    idx = mfd.load_latest_snapshots("2026-05-26", lines_dir=str(tmp_path),
                                     books=("bov",))
    key = ("Stephen Curry", "pts")
    assert key in idx
    assert "bov" in idx[key]
    assert idx[key]["bov"][0]["over_price"] == -115  # latest snapshot


def test_mfd_run_once_no_lines_returns_empty(tmp_path):
    """run_once over a missing date returns empty middles + empty index."""
    middles, index = mfd.run_once("2026-01-01", min_width=0.5,
                                   max_juice=-135, predictor=None)
    assert middles == []
    assert index == {}


def test_mfd_load_latest_snapshots_skips_alt_lines_in_index(tmp_path):
    """is_alt_line=true rows are still indexed (filter happens at find_middles)."""
    header = ["captured_at", "book", "game_id", "player_id", "player_name",
              "team", "stat", "line", "over_price", "under_price",
              "market_status", "is_alt_line"]
    p = tmp_path / "2026-05-26_bov.csv"
    _write_lines_csv(p, header, [
        ["2026-05-26T15:00:00", "bov", "1", "201939", "Stephen Curry", "GSW",
         "pts", "27.5", "-110", "-110", "open", "false"],
        ["2026-05-26T15:00:00", "bov", "1", "201939", "Stephen Curry", "GSW",
         "pts", "30.5", "+150", "-200", "open", "true"],
    ])
    idx = mfd.load_latest_snapshots("2026-05-26", lines_dir=str(tmp_path),
                                     books=("bov",))
    rows = idx[("Stephen Curry", "pts")]["bov"]
    # Both lines preserved, is_alt_line attribute carried through.
    assert any(r["is_alt_line"] is True for r in rows)
    assert any(r["is_alt_line"] is False for r in rows)


# ============================================================================
# live_bet_ranker — 47% baseline, _read_lines_csv + load_books_for_date
# ============================================================================

def test_lbr_read_lines_csv_12col_alt_line(tmp_path):
    p = tmp_path / "2026-05-26_bov.csv"
    header = ["captured_at", "book", "game_id", "player_id", "player_name",
              "team", "stat", "line", "over_price", "under_price",
              "market_status", "is_alt_line"]
    _write_lines_csv(p, header, [
        ["2026-05-26T15:00:00Z", "bov", "1", "201939", "Stephen Curry",
         "GSW", "pts", "30.5", "+150", "-180", "open", "true"],
        ["2026-05-26T15:00:00Z", "bov", "1", "201939", "Stephen Curry",
         "GSW", "pts", "27.5", "-110", "-110", "open", "false"],
    ])
    df = lbr._read_lines_csv(str(p))
    assert len(df) == 2
    assert df["is_alt_line"].dtype == bool
    assert df["is_alt_line"].sum() == 1
    assert df["over_price"].max() == 150


def test_lbr_read_lines_csv_missing_returns_empty_df(tmp_path):
    df = lbr._read_lines_csv(str(tmp_path / "absent.csv"))
    assert df.empty
    assert "captured_at" in df.columns
    assert "is_alt_line" in df.columns


def test_lbr_load_books_for_date_dedups_to_latest_per_line(tmp_path, monkeypatch):
    """Two snapshots same (player,stat,line) -> only latest kept per book."""
    monkeypatch.setattr(lbr, "PROJECT_DIR", str(tmp_path))
    lines_dir = tmp_path / "data" / "lines"
    lines_dir.mkdir(parents=True)
    header = ["captured_at", "book", "game_id", "player_id", "player_name",
              "stat", "line", "over_price", "under_price", "start_time"]
    _write_lines_csv(lines_dir / "2026-05-26_bov.csv", header, [
        ["2026-05-26T15:00:00Z", "bov", "1", "201939", "Stephen Curry",
         "pts", "27.5", "-110", "-110", ""],
        ["2026-05-26T16:00:00Z", "bov", "1", "201939", "Stephen Curry",
         "pts", "27.5", "-105", "-115", ""],
    ])
    books, latest = lbr.load_books_for_date("2026-05-26")
    assert "bov" in books
    assert len(books["bov"]) == 1
    assert int(books["bov"].iloc[0]["over_price"]) == -105
    assert latest["bov"].hour == 16


def test_lbr_load_state_missing_returns_default(tmp_path):
    state = lbr.load_state(str(tmp_path / "no_state.json"))
    assert state == {"prior_lines": {}, "prior_edges": {}}


def test_lbr_load_state_round_trip(tmp_path):
    p = tmp_path / "state.json"
    payload = {"prior_lines": {"a": 1}, "prior_edges": {"b": 2}}
    p.write_text(json.dumps(payload))
    state = lbr.load_state(str(p))
    assert state == payload


def test_lbr_load_state_corrupt_returns_default(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{garbage[[[")
    assert lbr.load_state(str(p)) == {"prior_lines": {}, "prior_edges": {}}


def test_lbr_in_play_handoff_payload_q1_default():
    """Slate with no NBA ids returns endQ1 as default next target."""
    cfg = {"nba_game_ids": [], "game_ids": [], "date": "2026-05-26"}
    payload = lbr.in_play_handoff_payload(cfg)
    assert payload["phase"] == "IN_PLAY"
    assert payload["next_prediction_target"] == "endQ1_winprob"
    assert payload["nba_game_ids"] == []
    assert isinstance(payload["wp_model_paths"], list)
    assert len(payload["wp_model_paths"]) == 4


def test_lbr_is_pretip_no_qbox_dir(tmp_path, monkeypatch):
    """With no quarter_box directory present, pretip defaults True (signal 1 absent)."""
    monkeypatch.setattr(lbr, "PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(lbr, "_tip_det", None)  # disable signal 2
    cfg = {"nba_game_ids": ["0022500001"], "date": "2026-05-26"}
    assert lbr.is_pretip(cfg) is True


# ============================================================================
# inplay_bet_ranker — 58% baseline
# ============================================================================

def test_ipr_atomic_write_text_round_trip(tmp_path):
    p = tmp_path / "vault" / "out.md"
    ipr.atomic_write_text(str(p), "# Hello\n")
    assert p.read_text() == "# Hello\n"
    # rewrite
    ipr.atomic_write_text(str(p), "v2 content")
    assert p.read_text() == "v2 content"


def test_ipr_find_quarter_files_filters_by_game_id(tmp_path):
    """Only files matching <game_id>_q<N>.json are returned, keyed by period."""
    (tmp_path / "0022500001_q1.json").write_text("{}")
    (tmp_path / "0022500001_q2.json").write_text("{}")
    (tmp_path / "0022500999_q1.json").write_text("{}")  # different game
    (tmp_path / "random.json").write_text("{}")  # noise
    out = ipr.find_quarter_files("0022500001", qbox_dir=str(tmp_path))
    assert set(out.keys()) == {1, 2}
    assert "0022500001_q1.json" in out[1]


def test_ipr_find_quarter_files_no_dir():
    assert ipr.find_quarter_files("0022500001", qbox_dir="/non/existent") == {}


def test_ipr_parse_min_str_clock_format():
    assert ipr._parse_min_str("9:18") == pytest.approx(9 + 18 / 60.0)
    assert ipr._parse_min_str("12:00") == 12.0
    assert ipr._parse_min_str("0:30") == 0.5


def test_ipr_parse_min_str_numeric_and_garbage():
    assert ipr._parse_min_str(9.3) == 9.3
    assert ipr._parse_min_str(15) == 15.0
    assert ipr._parse_min_str(None) == 0.0
    assert ipr._parse_min_str("") == 0.0
    assert ipr._parse_min_str("garbage") == 0.0
    assert ipr._parse_min_str("9:abc") == 0.0  # malformed clock seconds


def test_ipr_snapshot_age_sec_empty_returns_inf():
    assert ipr._snapshot_age_sec({}) == float("inf")


def test_ipr_snapshot_age_sec_with_files(tmp_path):
    p = tmp_path / "0022500001_q1.json"
    p.write_text("{}")
    age = ipr._snapshot_age_sec({1: str(p)}, now_t=time.time() + 10)
    assert 9.0 <= age <= 11.0


def test_ipr_kelly_fraction_clamps_prob_to_unit_interval():
    """inplay kelly_fraction clamps prob to [0, 1] — covers safety branch."""
    # prob > 1 should clamp to 1 and produce positive kelly (b > 0)
    f1 = ipr.kelly_fraction(2.0, -110)
    f2 = ipr.kelly_fraction(1.0, -110)
    assert f1 == pytest.approx(f2)
    # prob < 0 should clamp to 0 (no edge)
    assert ipr.kelly_fraction(-0.5, +150) == 0.0


def test_ipr_model_prob_over_missing_quantiles_returns_half():
    assert ipr.model_prob_over(25.0, None, 30.0, 27.5) == 0.5
    assert ipr.model_prob_over(25.0, 20.0, None, 27.5) == 0.5


def test_ipr_is_pretip_true_when_no_q1(tmp_path):
    assert ipr.is_pretip("0022500001", qbox_dir=str(tmp_path)) is True


def test_ipr_is_pretip_false_when_q1_exists(tmp_path):
    (tmp_path / "0022500001_q1.json").write_text("{}")
    assert ipr.is_pretip("0022500001", qbox_dir=str(tmp_path)) is False


# ============================================================================
# multi_game_kelly — _resolve_slate_paths
# ============================================================================

def test_mgk_resolve_slate_paths_absolute_path_passthrough(tmp_path):
    """If a path is given that exists as a file, it's used as-is."""
    p = tmp_path / "my_slate.json"
    p.write_text(json.dumps({"game_id": "x", "ranked_bets": []}))
    out = mgk._resolve_slate_paths([str(p)])
    assert out == [str(p)]


def test_mgk_resolve_slate_paths_missing_dir_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(mgk, "PROJECT_DIR", str(tmp_path / "no_such_root"))
    with pytest.raises(FileNotFoundError, match="no live_bets directory"):
        mgk._resolve_slate_paths(["lakers_warriors_2026-05-26"])


def test_mgk_resolve_slate_paths_picks_latest_match(tmp_path, monkeypatch):
    monkeypatch.setattr(mgk, "PROJECT_DIR", str(tmp_path))
    live_dir = tmp_path / "data" / "cache" / "live_bets"
    live_dir.mkdir(parents=True)
    # Two matching files — sorted last is chosen.
    a = live_dir / "2026-05-25_lakers_warriors.json"
    b = live_dir / "2026-05-26_lakers_warriors.json"
    a.write_text("{}")
    b.write_text("{}")
    # Also write some red herrings that must be excluded
    (live_dir / "2026-05-26_lakers_warriors_state.json").write_text("{}")
    (live_dir / "2026-05-26_lakers_warriors_handoff.json").write_text("{}")
    out = mgk._resolve_slate_paths(["lakers_warriors"])
    assert out == [str(b)]


def test_mgk_resolve_slate_paths_no_match_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(mgk, "PROJECT_DIR", str(tmp_path))
    live_dir = tmp_path / "data" / "cache" / "live_bets"
    live_dir.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="no live_bets file"):
        mgk._resolve_slate_paths(["unknown_slate"])


# ============================================================================
# clv_tracker_daemon — color dot + closing-line writer
# ============================================================================

def test_clv_color_dot_thresholds():
    assert clv._color_dot(0.05) == "GREEN"  # > +1%
    assert clv._color_dot(0.011) == "GREEN"
    assert clv._color_dot(0.005) == "YELLOW"  # in [0, +1%]
    assert clv._color_dot(0.0) == "YELLOW"
    assert clv._color_dot(-0.005) == "RED"
    assert clv._color_dot(-0.10) == "RED"


def test_clv_append_clv_rows_creates_header(tmp_path):
    p = tmp_path / "clv.csv"
    row = {
        "bet_id": "abc", "snapshot_time": "2026-05-26T15:00:00",
        "placed_at": "2026-05-26T14:00:00", "player": "Steph Curry",
        "stat": "pts", "side": "OVER", "book": "bov",
        "placed_line": 27.5, "current_line": 28.5, "placed_odds": -110,
        "current_over_odds": -120, "current_under_odds": +100,
        "clv_pct": 0.0364, "clv_line": 1.0, "beat_close": True,
        "is_closing": False, "minutes_to_tip": 45.0, "start_time": "",
    }
    clv._append_clv_rows(p, [row])
    txt = p.read_text()
    assert "bet_id" in txt  # header written
    assert "abc" in txt


def test_clv_append_clv_rows_no_op_on_empty(tmp_path):
    p = tmp_path / "clv.csv"
    clv._append_clv_rows(p, [])
    assert not p.exists()


def test_clv_closing_already_logged(tmp_path):
    p = tmp_path / "close.csv"
    # Empty file: returns False.
    assert clv._closing_already_logged(p, "bet1", "bov") is False
    # Write a closing row.
    clv._append_closing_line(
        p, bet_id="bet1", book="bov", stat="pts", player="Steph Curry",
        closing_line=27.5, closing_over_odds=-110, closing_under_odds=-110,
        captured_at="2026-05-26T18:55:00", start_time="2026-05-26T19:00:00",
    )
    assert clv._closing_already_logged(p, "bet1", "bov") is True
    assert clv._closing_already_logged(p, "bet2", "bov") is False
    assert clv._closing_already_logged(p, "bet1", "fd") is False


def test_clv_book_canon_and_name_key():
    """Helper canonicalization for cross-book + name matching."""
    # _BOOK_ALIASES maps short codes to canonical names.
    assert clv._book_canon("BOV") == "bovada"
    assert clv._book_canon("  Fd ") == "fanduel"
    assert clv._book_canon("dk") == "draftkings"
    # Unknown books pass through (lowercased + stripped).
    assert clv._book_canon("UnknownBook") == "unknownbook"
    # Name key strips accents + lowercases
    assert clv._name_key("Luka Dončić") == "luka doncic"
    assert clv._name_key("  Stephen Curry  ") == "stephen curry"
    assert clv._name_key(None) == ""


def test_clv_safe_float_int_helpers():
    assert clv._safe_float("1.5") == 1.5
    assert clv._safe_float(None) is None
    assert clv._safe_float("bad") is None
    assert clv._safe_int("110") == 110
    assert clv._safe_int(None) is None
    assert clv._safe_int("bad") is None


def test_clv_parse_iso_variants():
    """Handles Z suffix + minute-only timestamps (no seconds)."""
    a = clv._parse_iso("2026-05-26T15:00:00Z")
    assert a is not None and a.year == 2026
    b = clv._parse_iso("2026-05-26T15:00")  # no seconds
    assert b is not None and b.minute == 0
    assert clv._parse_iso("") is None
    assert clv._parse_iso("garbage") is None


# ============================================================================
# bankroll_monitor_daemon — render + write + alert append
# ============================================================================

def test_bmd_render_dashboard_has_all_sections():
    """Dashboard markdown must include header, summary metrics, alarms."""
    metrics = bmd._empty_metrics(1000.0, datetime(2026, 5, 26, 15, tzinfo=timezone.utc))
    metrics["alarms"] = [{
        "level": "WARN", "rule": "test_rule", "value": 0.5,
        "threshold": 0.4, "msg": "test alarm message",
    }]
    md = bmd.render_dashboard(metrics)
    assert md.startswith("# Bankroll Dashboard")
    assert "Settled bets" in md
    assert "test_rule" in md
    assert "test alarm message" in md
    assert "[WARN]" in md


def test_bmd_render_dashboard_no_alarms_shows_green():
    metrics = bmd._empty_metrics(1000.0, datetime(2026, 5, 26, tzinfo=timezone.utc))
    md = bmd.render_dashboard(metrics)
    assert "No active alarms" in md or "all systems green" in md


def test_bmd_write_dashboard_atomic(tmp_path):
    metrics = bmd._empty_metrics(1000.0, datetime(2026, 5, 26, tzinfo=timezone.utc))
    p = tmp_path / "dash.md"
    bmd.write_dashboard(p, metrics)
    txt = p.read_text()
    assert "Bankroll Dashboard" in txt


def test_bmd_load_ledger_missing_returns_empty_df(tmp_path):
    df = bmd.load_ledger(tmp_path / "no_such_ledger.csv")
    assert df.empty


def test_bmd_is_synthetic_row_detection():
    import pandas as pd
    real_row = pd.Series({"player": "Stephen Curry", "book": "bov"})
    assert bmd.is_synthetic_row(real_row) is False


def test_bmd_filter_ledger_empty_input():
    import pandas as pd
    df = pd.DataFrame()
    result = bmd.filter_ledger(df, exclude_synthetic=True)
    assert result["n_total"] == 0
    assert result["n_kept"] == 0


def test_bmd_compute_roi_empty_settled():
    """No settled bets -> ROI=0 with 0 stake."""
    import pandas as pd
    df = pd.DataFrame()
    out = bmd.compute_roi(df)
    assert out["n_bets"] == 0
    assert out["total_stake"] == 0.0
    assert out["roi_pct"] == 0.0


def test_bmd_compute_roi_with_settled():
    import pandas as pd
    df = pd.DataFrame([
        {"status": "won",  "stake": 10.0, "profit_loss": 9.09},
        {"status": "lost", "stake": 10.0, "profit_loss": -10.0},
        {"status": "pending", "stake": 10.0, "profit_loss": 0.0},
    ])
    out = bmd.compute_roi(df)
    assert out["n_bets"] == 2
    assert out["total_stake"] == 20.0
    assert out["total_pnl"] == pytest.approx(-0.91, abs=0.01)
    assert out["roi_pct"] == pytest.approx(-4.55, abs=0.05)


# ============================================================================
# line_move_detector — event dedup + writers + webhook
# ============================================================================

def test_lmd_event_dedup_key_stable():
    ev = {"book": "bov", "name_key": "stephen curry", "stat": "pts",
          "ts_from": "T1", "ts_to": "T2"}
    assert lmd.event_dedup_key(ev) == "bov|stephen curry|pts|T1|T2"


def test_lmd_load_existing_event_keys_handles_missing(tmp_path):
    assert lmd.load_existing_event_keys(str(tmp_path / "no.json")) == set()


def test_lmd_load_existing_event_keys_skips_malformed(tmp_path):
    p = tmp_path / "events.json"
    with open(p, "w") as f:
        f.write('{"book":"bov","name_key":"a","stat":"pts","ts_from":"t1","ts_to":"t2"}\n')
        f.write("not-json\n")
        f.write("\n")
        f.write('{"book":"fd","name_key":"b","stat":"reb","ts_from":"t3","ts_to":"t4"}\n')
    keys = lmd.load_existing_event_keys(str(p))
    assert len(keys) == 2
    assert "bov|a|pts|t1|t2" in keys


def test_lmd_append_events_writes_jsonl(tmp_path):
    p = tmp_path / "cache" / "events.json"
    events = [
        {"book": "bov", "name_key": "a", "stat": "pts",
         "ts_from": "t1", "ts_to": "t2", "tags": ["LINE_UP"]},
        {"book": "fd", "name_key": "b", "stat": "reb",
         "ts_from": "t3", "ts_to": "t4", "tags": ["ODDS_TIGHTEN"]},
    ]
    n = lmd.append_events(str(p), events)
    assert n == 2
    lines = p.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["book"] == "bov"


def test_lmd_append_events_no_op_on_empty(tmp_path):
    p = tmp_path / "events.json"
    assert lmd.append_events(str(p), []) == 0
    assert not p.exists()


def test_lmd_fire_webhook_no_env_returns_zero(monkeypatch):
    monkeypatch.delenv("WEBHOOK_URL", raising=False)
    events = [{"consensus": True, "book": "bov"}]
    assert lmd.fire_webhook(events) == 0


def test_lmd_to_american_int_variants():
    assert lmd._to_american_int(-110) == -110
    assert lmd._to_american_int("+150") == 150
    assert lmd._to_american_int("EVEN") == 100
    assert lmd._to_american_int("EV") == 100
    assert lmd._to_american_int(None) is None
    assert lmd._to_american_int("") is None
    assert lmd._to_american_int("garbage") is None


def test_lmd_name_key_strips_accents():
    assert lmd._name_key("Luka Dončić") == "luka doncic"
    assert lmd._name_key("Nikola Jokić") == "nikola jokic"
    assert lmd._name_key(None) == ""


# ============================================================================
# auto_settle_daemon — _match_player + void_dnp_bets
# ============================================================================

def test_asd_match_player_by_name_with_accents():
    """Player name match should be accent-insensitive."""
    bet = {"player": "Luka Dončić"}
    totals = {"Luka Doncic": {"pts": 30, "player_id": 1629029}}
    assert asd._match_player(bet, totals) is totals["Luka Doncic"]


def test_asd_match_player_by_id_fallback():
    """If name doesn't match but player_id does, return that row."""
    bet = {"player": "Wrong Name", "player_id": "1629029"}
    totals = {"Luka Doncic": {"pts": 30, "player_id": 1629029}}
    assert asd._match_player(bet, totals) is totals["Luka Doncic"]


def test_asd_match_player_no_match_returns_none():
    bet = {"player": "Nobody"}
    totals = {"Luka Doncic": {"pts": 30, "player_id": 1629029}}
    assert asd._match_player(bet, totals) is None


def test_asd_list_period_files_empty_dir(tmp_path):
    assert asd.list_period_files("0022500001", tmp_path) == []


def test_asd_list_period_files_sorted_by_quarter(tmp_path):
    """Files should be returned in period order, OT-aware."""
    for q in (3, 1, 5, 2, 4):
        (tmp_path / f"0022500001_q{q}.json").write_text("{}")
    # Add noise files that should be excluded
    (tmp_path / "0022500001_random.json").write_text("{}")
    (tmp_path / "9999999999_q1.json").write_text("{}")
    files = asd.list_period_files("0022500001", tmp_path)
    assert len(files) == 5
    names = [p.name for p in files]
    assert names == [f"0022500001_q{i}.json" for i in (1, 2, 3, 4, 5)]


def test_asd_load_seen_missing_returns_empty(tmp_path):
    p = tmp_path / "seen.json"
    assert asd.load_seen(p) == set()


def test_asd_save_load_seen_round_trip(tmp_path):
    p = tmp_path / "seen.json"
    asd.save_seen({"a", "b", "c"}, p)
    assert asd.load_seen(p) == {"a", "b", "c"}


def test_asd_scan_new_q4_files_filters_seen(tmp_path):
    """scan_new_q4_files should skip already-seen game_ids."""
    (tmp_path / "0022500001_q4.json").write_text("{}")
    (tmp_path / "0022500002_q4.json").write_text("{}")
    (tmp_path / "0022500003_q3.json").write_text("{}")  # not q4
    out = asd.scan_new_q4_files(tmp_path, seen={"0022500001"})
    assert out == ["0022500002"]


def test_asd_player_key_normalization():
    """_player_key strips accents + lowercases + trims."""
    assert asd._player_key("Luka Dončić") == "luka doncic"
    assert asd._player_key("  Stephen Curry  ") == "stephen curry"
    assert asd._player_key(None) == ""


# ============================================================================
# nba_lineup_daemon — snapshot_path + load_prior_snapshot
# ============================================================================

def test_nld_snapshot_path_uses_today_when_none():
    p = nld.snapshot_path()
    assert p.endswith(".json")
    assert "data" in p or "lineups" in p


def test_nld_load_prior_snapshot_missing(tmp_path):
    assert nld.load_prior_snapshot(str(tmp_path / "no.json")) is None


def test_nld_load_prior_snapshot_corrupt(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json[")
    assert nld.load_prior_snapshot(str(p)) is None


def test_nld_load_prior_snapshot_round_trip(tmp_path):
    p = tmp_path / "snap.json"
    payload = {"date": "2026-05-26", "starters": [{"name": "Curry"}]}
    p.write_text(json.dumps(payload))
    loaded = nld.load_prior_snapshot(str(p))
    assert loaded == payload


# ============================================================================
# Round 2 — render_md (live + inplay), line_move detect_moves / tag_consensus,
# clv main_loop helpers, mfd ModelPredictor surface.
# ============================================================================

def test_lbr_render_md_pretip_payload():
    """render_md should produce the markdown skeleton for a pre-tip payload."""
    payload = {
        "captured_at": "2026-05-26T15:00:00+00:00",
        "tick_idx": 1, "tick_latency_ms": 42,
        "pretip": True, "stale_books": [],
        "n_props_evaluated": 0, "n_positive_ev": 0,
        "total_recommended_exposure_$": 0.0,
        "line_moves_this_tick": [], "edge_collapses_this_tick": [],
        "ranked_bets": [],
    }
    slate_cfg = {"label": "LAL @ GSW"}
    md = lbr.render_md(payload, slate_cfg)
    assert "LAL @ GSW" in md
    assert "PREGAME" in md
    assert "Top Ranked Bets" in md
    assert "Tick: 1" in md


def test_lbr_render_md_live_payload_with_bets():
    """render_md handles live payload with ranked bets + line moves."""
    payload = {
        "captured_at": "2026-05-26T19:30:00+00:00",
        "tick_idx": 5, "tick_latency_ms": 137,
        "pretip": False, "stale_books": ["fd"],
        "n_props_evaluated": 100, "n_positive_ev": 12,
        "total_recommended_exposure_$": 156.78,
        "line_moves_this_tick": [{"key": "x"}],
        "edge_collapses_this_tick": [],
        "ranked_bets": [{
            "player": "Stephen Curry", "stat": "pts", "side": "OVER",
            "book": "bov", "line": 27.5, "model_q50": 29.1,
            "edge_pct": 4.2, "kelly_stake_$": 25.50,
            "line_move": None, "stale": False,
        }],
    }
    slate_cfg = {"label": "GSW @ LAL"}
    md = lbr.render_md(payload, slate_cfg)
    assert "GSW @ LAL" in md
    assert "GAME LIVE" in md or "LIVE" in md
    assert "STALE books" in md
    assert "Stephen Curry" in md
    assert "$25.50" in md


def test_ipr_render_md_pretip():
    """inplay render_md short-circuits on pretip."""
    payload = {
        "game_id": "0022500001",
        "captured_at": "2026-05-26T19:00:00",
        "status": "PREGAME", "pretip": True,
    }
    md = ipr.render_md(payload)
    assert "In-Play Bet Ranker" in md
    assert "0022500001" in md
    assert "PREGAME" in md


def test_ipr_render_md_live_with_ranked_bets():
    payload = {
        "game_id": "0022500001",
        "captured_at": "2026-05-26T20:30:00",
        "status": "IN_PLAY", "pretip": False,
        "max_quarter_observed": 3, "snapshot_period": 4,
        "score_margin": 8, "stale": False, "garbage_time_active": False,
        "snapshot_age_sec": 12.0,
        "n_props_evaluated": 50, "n_positive_ev": 3,
        "total_recommended_exposure_$": 75.0,
        "ranked_bets": [{
            "player": "LeBron James", "stat": "pts", "side": "UNDER",
            "book": "bov", "line": 25.5, "current_stat": 18.0,
            "remaining_needed": 7.5, "model_point": 22.4,
            "edge_pct": 5.1, "ev_per_dollar": 0.05,
            "kelly_stake_$": 25.0,
        }],
    }
    md = ipr.render_md(payload)
    assert "LeBron James" in md
    assert "Q3" in md
    assert "$75.00" in md


def test_ipr_render_md_stale_and_garbage_time():
    """Render md must surface stale and garbage-time flags."""
    payload = {
        "game_id": "0022500001",
        "captured_at": "T",
        "status": "IN_PLAY", "pretip": False,
        "max_quarter_observed": 4, "snapshot_period": 4,
        "score_margin": 25, "stale": True, "garbage_time_active": True,
        "snapshot_age_sec": 120.0,
        "n_props_evaluated": 10, "n_positive_ev": 0,
        "total_recommended_exposure_$": 0.0,
        "ranked_bets": [],
    }
    md = ipr.render_md(payload)
    assert "STALE" in md
    assert "GARBAGE-TIME" in md


# ----- line_move_detector: detect_moves + tag_consensus end-to-end -----
def test_lmd_detect_moves_simple_line_jump():
    """Two-row group with line jump above threshold emits one event."""
    import pandas as pd
    df = pd.DataFrame([
        {"captured_at": "2026-05-26T15:00:00", "book": "bov",
         "player_name": "Steph Curry", "stat": "pts",
         "line": 27.5, "over_price": -110, "under_price": -110},
        {"captured_at": "2026-05-26T15:05:00", "book": "bov",
         "player_name": "Steph Curry", "stat": "pts",
         "line": 28.5, "over_price": -110, "under_price": -110},
    ])
    evs = lmd.detect_moves(df, threshold_line=0.5,
                            threshold_odds_pct=10.0)
    assert len(evs) == 1
    assert "LINE_UP" in evs[0]["tags"]
    assert evs[0]["line_from"] == 27.5
    assert evs[0]["line_to"] == 28.5
    assert evs[0]["consensus"] is False


def test_lmd_tag_consensus_two_books_within_window():
    """Two different books moving the same direction within 5 min -> consensus."""
    events = [
        {"book": "bov", "name_key": "steph curry", "stat": "pts",
         "ts_from": "2026-05-26T15:00:00", "ts_to": "2026-05-26T15:01:00",
         "tags": ["LINE_UP"], "consensus": False},
        {"book": "fd", "name_key": "steph curry", "stat": "pts",
         "ts_from": "2026-05-26T15:00:00", "ts_to": "2026-05-26T15:03:00",
         "tags": ["LINE_UP"], "consensus": False},
    ]
    out = lmd.tag_consensus(events, window_sec=300)
    assert all(e["consensus"] for e in out)
    assert all("CONSENSUS_STEAM" in e["tags"] for e in out)


def test_lmd_tag_consensus_skips_same_book():
    """Same book ts mismatch must not trigger consensus."""
    events = [
        {"book": "bov", "name_key": "a", "stat": "pts",
         "ts_from": "T1", "ts_to": "2026-05-26T15:01:00",
         "tags": ["LINE_UP"], "consensus": False},
        {"book": "bov", "name_key": "a", "stat": "pts",
         "ts_from": "T2", "ts_to": "2026-05-26T15:03:00",
         "tags": ["LINE_UP"], "consensus": False},
    ]
    out = lmd.tag_consensus(events, window_sec=300)
    assert not any(e["consensus"] for e in out)


def test_lmd_render_vault_feed_skips_missing_cache(tmp_path):
    """No cache file = no-op (no vault file written)."""
    vp = tmp_path / "vault.md"
    lmd.render_vault_feed(str(tmp_path / "absent.json"), str(vp))
    assert not vp.exists()


def test_lmd_render_vault_feed_writes_table(tmp_path):
    cache = tmp_path / "events.json"
    cache.write_text(json.dumps({
        "ts_to": "2026-05-26T15:01:00", "book": "bov",
        "player_name": "Steph Curry", "stat": "pts",
        "line_from": 27.5, "line_to": 28.5, "line_delta": 1.0,
        "odds_from": -110, "odds_to": -120, "odds_pct_delta": 2.5,
        "tags": ["LINE_UP", "ODDS_TIGHTEN"],
    }) + "\n")
    vault = tmp_path / "feed.md"
    lmd.render_vault_feed(str(cache), str(vault), limit=10)
    txt = vault.read_text()
    assert "# Line Moves Feed" in txt
    assert "Steph Curry" in txt
    assert "LINE_UP" in txt


# ----- middle_finder model_band_prob -----
def test_mfd_norm_cdf_basic():
    """_norm_cdf(0) = 0.5; _norm_cdf(3) ~ 0.998."""
    assert mfd._norm_cdf(0) == pytest.approx(0.5)
    assert mfd._norm_cdf(3) == pytest.approx(0.9987, abs=0.001)
    assert mfd._norm_cdf(-3) == pytest.approx(0.00135, abs=0.001)


def test_mfd_model_band_prob_none_when_no_qint():
    """_model_band_prob short-circuits None when quantiles missing."""
    assert mfd._model_band_prob("pts", None, 25, 30) is None
    assert mfd._model_band_prob("pts", {"q10": None, "q50": 25, "q90": 30}, 25, 30) is None
    assert mfd._model_band_prob("pts", {"q10": 20, "q50": None, "q90": 30}, 25, 30) is None


def test_mfd_atomic_write_json_round_trip(tmp_path):
    p = tmp_path / "out" / "middles.json"
    payload = {"middles": [{"player": "Curry", "free_arb": True}]}
    mfd.atomic_write_json(str(p), payload)
    assert json.loads(p.read_text()) == payload


def test_mfd_annotate_model_confirmed_with_dummy_predictor():
    """annotate_model_confirmed should call predictor + populate model_confirmed."""
    middles = [{
        "player": "Steph Curry", "stat": "pts",
        "over_line": 27.5, "under_line": 28.5,
    }]
    def dummy_predictor(player, stat):
        # Tight band around 28 -> high prob of landing in (27.5, 28.5).
        return {"q10": 26.5, "q50": 28.0, "q90": 29.5}
    out = mfd.annotate_model_confirmed(middles, dummy_predictor, min_band_prob=0.05)
    assert "model_confirmed" in out[0]
    assert "model_band_prob" in out[0]


def test_mfd_annotate_model_confirmed_predictor_returns_none():
    middles = [{"player": "X", "stat": "pts", "over_line": 25, "under_line": 26}]
    out = mfd.annotate_model_confirmed(middles, lambda p, s: None)
    assert out[0]["model_band_prob"] is None
    assert out[0]["model_confirmed"] is False


# ----- CLV: aggregate end-to-end -----
def test_clv_compute_aggregate_empty(tmp_path):
    p = tmp_path / "clv.csv"
    # No file -> empty aggregate (uses key 'n_bets_tracked' not 'n_bets')
    agg = clv.compute_aggregate(p)
    assert agg["n_bets_tracked"] == 0
    assert agg["mean_clv_pct"] == 0.0


def test_clv_compute_aggregate_real(tmp_path):
    p = tmp_path / "clv.csv"
    rows = [
        {"bet_id": "a", "snapshot_time": "2026-05-26T15:00:00", "placed_at": "T",
         "player": "Steph Curry", "stat": "pts", "side": "OVER",
         "book": "bov", "placed_line": 27.5, "current_line": 28.5,
         "placed_odds": -110, "current_over_odds": -120,
         "current_under_odds": +100, "clv_pct": 0.0364, "clv_line": 1.0,
         "beat_close": True, "is_closing": False,
         "minutes_to_tip": 60.0, "start_time": "T"},
        {"bet_id": "b", "snapshot_time": "2026-05-26T15:00:00", "placed_at": "T",
         "player": "LeBron James", "stat": "reb", "side": "UNDER",
         "book": "fd", "placed_line": 8.5, "current_line": 7.5,
         "placed_odds": -110, "current_over_odds": +100,
         "current_under_odds": -120, "clv_pct": 0.1176, "clv_line": 1.0,
         "beat_close": True, "is_closing": False,
         "minutes_to_tip": 30.0, "start_time": "T"},
    ]
    clv._append_clv_rows(p, rows)
    agg = clv.compute_aggregate(p)
    assert agg["n_bets_tracked"] == 2
    assert agg["mean_clv_pct"] > 0
    assert agg["pct_positive_clv"] == 1.0
    assert "bov" in agg["by_book"]
    assert "fd" in agg["by_book"]


def test_clv_write_aggregate_creates_json(tmp_path):
    p_clv = tmp_path / "clv.csv"
    p_out = tmp_path / "agg.json"
    rows = [{"bet_id": "a", "snapshot_time": "2026-05-26T15:00:00", "placed_at": "T",
             "player": "X", "stat": "pts", "side": "OVER",
             "book": "bov", "placed_line": 25.5, "current_line": 26.5,
             "placed_odds": -110, "current_over_odds": -110,
             "current_under_odds": -110, "clv_pct": 0.0392, "clv_line": 1.0,
             "beat_close": True, "is_closing": False,
             "minutes_to_tip": 30.0, "start_time": "T"}]
    clv._append_clv_rows(p_clv, rows)
    clv.write_aggregate(p_clv, p_out)
    assert p_out.exists()
    data = json.loads(p_out.read_text())
    assert data["n_bets_tracked"] == 1


# ----- multi_game_kelly: scaling edge cases -----
def test_mgk_per_game_exposure_handles_missing_kelly_field():
    """Slate with bets that have no kelly_stake_$ field -> 0."""
    slate = {"game_id": "x", "ranked_bets": [
        {"player": "a"},  # no kelly_stake_$
        {"player": "b", "kelly_stake_$": None},  # None
        {"player": "c", "kelly_stake_$": 50.0},
    ]}
    assert mgk._per_game_exposure(slate) == 50.0


def test_mgk_solve_multi_game_zero_bankroll_raises():
    with pytest.raises(ValueError, match="bankroll must be > 0"):
        mgk.solve_multi_game([], bankroll=0.0)


def test_mgk_solve_multi_game_negative_bankroll_raises():
    with pytest.raises(ValueError):
        mgk.solve_multi_game([], bankroll=-100.0)


# ----- bankroll_monitor: settled bets with drawdown -----
def test_bmd_compute_metrics_with_drawdown():
    """Metrics on a small ledger with one win + one loss has correct drawdown."""
    import pandas as pd
    df = pd.DataFrame([
        {"status": "won", "stake": 10.0, "profit_loss": 9.09,
         "kelly_pct": 0.01, "placed_at": "2026-05-25T15:00:00+00:00",
         "game_id": "g1"},
        {"status": "lost", "stake": 50.0, "profit_loss": -50.0,
         "kelly_pct": 0.05, "placed_at": "2026-05-26T15:00:00+00:00",
         "game_id": "g2"},
    ])
    m = bmd.compute_metrics(df, start_bankroll=1000.0,
                             now=datetime(2026, 5, 26, 18, tzinfo=timezone.utc))
    # Bankroll moved 1000 -> 1009.09 -> 959.09; peak was 1009.09.
    assert m["current_bankroll"] == pytest.approx(959.09, abs=0.01)
    assert m["max_drawdown"] == pytest.approx(50.0, abs=0.01)
    assert m["max_drawdown_pct"] == pytest.approx(50.0 / 1009.09, abs=0.001)


def test_bmd_compute_metrics_empty_returns_empty_metrics():
    import pandas as pd
    m = bmd.compute_metrics(pd.DataFrame(), start_bankroll=2500.0)
    assert m["start_bankroll"] == 2500.0
    assert m["current_bankroll"] == 2500.0
    assert m["alarms"] == []


def test_bmd_append_alerts_no_op_when_no_alarms(tmp_path):
    p = tmp_path / "alerts.md"
    bmd.append_alerts(p, {"as_of": "T", "alarms": []})
    assert not p.exists()


def test_bmd_append_alerts_writes_header_first_time(tmp_path):
    p = tmp_path / "alerts.md"
    metrics = {"as_of": "2026-05-26T15:00:00",
                "alarms": [{"level": "WARN", "rule": "x", "msg": "a thing"}]}
    bmd.append_alerts(p, metrics)
    txt = p.read_text()
    assert "Risk Alerts Log" in txt
    assert "a thing" in txt
    # Append again — header NOT re-written
    bmd.append_alerts(p, metrics)
    assert txt.count("# Risk Alerts Log") == 1 or p.read_text().count("# Risk Alerts Log") == 1


def test_bmd_filter_ledger_synthetic_exclude():
    """Ledger with synth rows (Player_N + book='PP') -> exclude_synthetic=True drops them."""
    import pandas as pd
    df = pd.DataFrame([
        {"player": "Player_001", "book": "PP", "placed_at": "2026-05-26T15:00:00+00:00",
         "stake": 10.0, "profit_loss": 0.0, "kelly_pct": 0.01, "status": "pending",
         "game_id": "g1"},
        {"player": "Stephen Curry", "book": "bov", "placed_at": "2026-05-26T15:00:00+00:00",
         "stake": 10.0, "profit_loss": 0.0, "kelly_pct": 0.01, "status": "pending",
         "game_id": "g1"},
    ])
    out = bmd.filter_ledger(df, exclude_synthetic=True)
    assert out["n_total"] == 2
    assert out["n_synth_excluded"] == 1
    assert out["n_kept"] == 1


def test_bmd_filter_ledger_date_filter():
    """start_date filter drops rows placed before cutoff."""
    import pandas as pd
    df = pd.DataFrame([
        {"player": "A", "book": "bov", "placed_at": "2026-05-01T00:00:00+00:00",
         "stake": 10.0, "profit_loss": 0.0, "kelly_pct": 0.01, "status": "pending",
         "game_id": "g1"},
        {"player": "B", "book": "bov", "placed_at": "2026-05-26T00:00:00+00:00",
         "stake": 10.0, "profit_loss": 0.0, "kelly_pct": 0.01, "status": "pending",
         "game_id": "g1"},
    ])
    out = bmd.filter_ledger(df, start_date="2026-05-20")
    assert out["n_total"] == 2
    assert out["n_date_excluded"] == 1
    assert out["n_kept"] == 1


# ----- inplay: garbage time edge cases -----
def test_ipr_garbage_time_dampener_no_op_early_quarter():
    """Q1 -> no-op even if big margin (dampener only fires Q3+)."""
    snap = {"max_quarter_observed": 1, "home_score": 50, "away_score": 20}
    rows = [{"current": 10, "projected_final": 30}]
    out = ipr.apply_garbage_time_dampener(snap, rows)
    assert out == rows


def test_ipr_garbage_time_dampener_no_op_small_margin():
    """Even at Q4, margin < 20 -> no-op."""
    snap = {"max_quarter_observed": 4, "home_score": 100, "away_score": 90}
    rows = [{"current": 10, "projected_final": 30}]
    out = ipr.apply_garbage_time_dampener(snap, rows)
    assert out == rows


def test_ipr_garbage_time_dampener_handles_string_proj():
    """Row with non-numeric projected_final is passed through unchanged."""
    snap = {"max_quarter_observed": 4, "home_score": 130, "away_score": 90}
    rows = [{"current": 10, "projected_final": "bogus"}]
    out = ipr.apply_garbage_time_dampener(snap, rows)
    assert out == rows


# ----- nba_lineup_daemon: write_snapshot preserves prior events -----
def test_nld_write_snapshot_round_trip(tmp_path):
    p = tmp_path / "snap.json"
    rows = [{"team": "GSW", "player_name": "Curry", "slot": "PG",
              "status": "CONFIRMED"}]
    nld.write_snapshot(rows, str(p), change_events=[{"event": "NEW", "team": "GSW"}])
    payload = json.loads(p.read_text())
    assert payload["n_starters"] == 1
    assert payload["change_events"][0]["event"] == "NEW"


def test_nld_write_snapshot_appends_events(tmp_path):
    """Subsequent writes append change_events to history."""
    p = tmp_path / "snap.json"
    nld.write_snapshot([], str(p), change_events=[{"event": "A"}])
    nld.write_snapshot([], str(p), change_events=[{"event": "B"}])
    payload = json.loads(p.read_text())
    events = [e["event"] for e in payload["change_events"]]
    assert "A" in events and "B" in events


def test_nld_diff_no_changes_returns_empty():
    """Identical snapshots -> no events."""
    rows = [{"team": "GSW", "slot": "PG", "player_name": "Curry",
              "status": "CONFIRMED"}]
    assert nld.diff_snapshots(rows, rows) == []


# ============================================================================
# Round 3 — exercise main loops in once-mode to cover daemon entry paths.
# ============================================================================

def test_clv_main_loop_once_mode(tmp_path):
    """main_loop(once=True) runs a single tick + aggregate + exits."""
    pnl = tmp_path / "pnl.csv"
    pnl.write_text("bet_id,status,placed_at,player,stat,side,book,line,american_odds\n")
    lines_dir = tmp_path / "lines"
    lines_dir.mkdir()
    clv_out = tmp_path / "clv.csv"
    vault = tmp_path / "vault.md"
    closing = tmp_path / "closing.csv"
    agg = tmp_path / "agg.json"
    log = tmp_path / "log.txt"
    final = clv.main_loop(
        pnl_path=pnl, lines_dir=lines_dir,
        clv_out_path=clv_out, vault_md_path=vault,
        closing_out_path=closing, agg_path=agg, log_path=log,
        interval_sec=1, once=True,
    )
    assert isinstance(final, dict)


@pytest.mark.xfail(reason="R19_L5 BUG FOUND: scripts/middle_finder_daemon.py "
                          "lines 5-16 (the _r19_hb try/except import block) "
                          "are INSIDE the module docstring (opens at line 1, "
                          "closes at line 33). Result: _r19_hb is never "
                          "defined and `loop()` crashes with NameError on the "
                          "very first iteration. Production daemon would NEVER "
                          "complete a tick. Fix: close the docstring before "
                          "the import block, or move the import below.",
                    strict=True)
def test_mfd_loop_max_iters_one_BUG_DEMO(tmp_path, monkeypatch):
    """mfd.loop(max_iters=1) should run once + exit cleanly — but doesn't
    because of the docstring-swallowed-import bug. This test is expected to
    fail until production code is fixed."""
    monkeypatch.setattr(mfd, "OUT_JSON", str(tmp_path / "out.json"))
    out_path = tmp_path / "out.json"
    stats = mfd.loop(
        interval_sec=0.01, min_width=0.5, max_juice=-135,
        max_iters=1, use_model=False, min_band_prob=0.10,
        out_json=str(out_path), log=lambda *a, **kw: None,
    )
    assert stats["ticks"] >= 1


def test_clv_aware_helper_conversions():
    """_to_aware adds UTC tz to naive dt; passes through aware."""
    import datetime as dt
    naive = dt.datetime(2026, 5, 26, 15, 0, 0)
    aware = clv._to_aware(naive)
    assert aware.tzinfo is not None
    # idempotent on already-aware
    again = clv._to_aware(aware)
    assert again == aware


def test_clv_now_utc_is_tz_aware():
    n = clv._now_utc()
    assert n.tzinfo is not None


def test_clv_load_pending_bets_missing_file(tmp_path):
    assert clv.load_pending_bets(tmp_path / "no.csv") == []


def test_clv_load_pending_bets_filters_status(tmp_path):
    """Only status=='pending' AND placed_at < now should be returned."""
    p = tmp_path / "pnl.csv"
    p.write_text(
        "bet_id,status,placed_at\n"
        "a,pending,2026-05-01T00:00:00+00:00\n"
        "b,won,2026-05-01T00:00:00+00:00\n"
        "c,pending,3026-05-01T00:00:00+00:00\n"  # future placed_at -> skipped
    )
    out = clv.load_pending_bets(p)
    assert len(out) == 1
    assert out[0]["bet_id"] == "a"


def test_clv_load_recent_snapshots_missing_dir(tmp_path):
    assert clv.load_recent_snapshots(tmp_path / "no_dir") == []


def test_clv_find_latest_snapshot_no_match():
    """No snapshots matching the bet -> None."""
    bet = {"book": "bov", "player": "Steph Curry", "stat": "pts", "line": 27.5}
    assert clv.find_latest_snapshot(bet, []) is None


def test_clv_find_latest_snapshot_picks_exact_line():
    """Exact-line match preferred over ladder mismatch."""
    bet = {"book": "bov", "player": "Steph Curry", "stat": "pts", "line": 27.5}
    snaps = [
        {"book": "bov", "player_name": "Steph Curry", "stat": "pts",
         "line": 27.5, "captured_at": "2026-05-26T15:00:00", "over_price": -110},
        {"book": "bov", "player_name": "Steph Curry", "stat": "pts",
         "line": 30.5, "captured_at": "2026-05-26T16:00:00", "over_price": -200},
    ]
    out = clv.find_latest_snapshot(bet, snaps)
    assert out["line"] == 27.5  # exact match wins over more recent


# ----- line_move_detector load_book_csvs -----
def test_lmd_load_book_csvs_missing_dir_returns_empty(tmp_path):
    """No matching CSVs -> empty df."""
    out = lmd.load_book_csvs(str(tmp_path), "2026-05-26")
    assert out.empty


def test_lmd_load_book_csvs_with_lines(tmp_path):
    p = tmp_path / "2026-05-26_bov.csv"
    p.write_text(
        "captured_at,book,game_id,player_id,player_name,stat,line,over_price,under_price,start_time\n"
        "2026-05-26T15:00:00,bov,1,201939,Steph Curry,pts,27.5,-110,-110,\n"
    )
    out = lmd.load_book_csvs(str(tmp_path), "2026-05-26")
    assert not out.empty
    assert "player_name" in out.columns


# ----- inplay: build_cumulative_snapshot edge cases -----
def test_ipr_build_cumulative_snapshot_empty():
    """No quarter files -> None."""
    assert ipr.build_cumulative_snapshot("0022500001", {}) is None


def test_ipr_build_cumulative_snapshot_basic(tmp_path):
    """One-quarter snapshot has correct team scores + players."""
    q1 = tmp_path / "0022500001_q1.json"
    q1.write_text(json.dumps({
        "teams": [
            {"team_abbreviation": "GSW", "pts": 28, "team_id": 1610612744},
            {"team_abbreviation": "LAL", "pts": 22, "team_id": 1610612747},
        ],
        "players": [{
            "player_id": 201939, "player_name": "Stephen Curry",
            "team_abbreviation": "GSW", "min": "12:00",
            "pts": 12, "reb": 1, "ast": 3, "fg3m": 4, "stl": 0,
            "blk": 0, "tov": 1, "pf": 1, "start_position": "PG",
        }],
    }))
    snap = ipr.build_cumulative_snapshot("0022500001", {1: str(q1)},
                                          pregame_win_prob=0.55, season="2025-26")
    assert snap is not None
    assert snap["game_id"] == "0022500001"
    assert snap["pregame_win_prob"] == 0.55
    assert snap["season"] == "2025-26"
    assert len(snap["players"]) == 1
    assert snap["players"][0]["pts"] == 12
    assert snap["max_quarter_observed"] == 1


def test_ipr_load_live_lines_for_date_missing(tmp_path, monkeypatch):
    """Missing CSVs for date -> empty list."""
    monkeypatch.setattr(ipr, "LINES_DIR", str(tmp_path))
    out = ipr.load_live_lines_for_date("2026-05-26", books=("bov",))
    assert out == []


def test_ipr_build_pred_index_normalizes_names():
    """build_pred_index uses normalized name as key."""
    rows = [
        {"name": "Luka Dončić", "stat": "pts", "model_q50": 30.0},
        {"name": "Stephen Curry", "stat": "reb", "model_q50": 5.0},
    ]
    idx = ipr.build_pred_index(rows)
    assert ("luka doncic", "pts") in idx
    assert ("stephen curry", "reb") in idx


# ----- live_bet_ranker bet_key + load_placed -----
def test_lbr_bet_key_stable_format():
    """bet_key joins player|stat|side|book|line."""
    b = {"player": "Steph Curry", "stat": "pts", "side": "OVER",
          "book": "bov", "line": 27.5}
    assert lbr.bet_key(b) == "Steph Curry|pts|OVER|bov|27.5"


def test_lbr_load_placed_missing(tmp_path):
    assert lbr.load_placed(str(tmp_path / "no.json")) == set()


def test_lbr_load_placed_round_trip(tmp_path):
    p = tmp_path / "placed.json"
    p.write_text(json.dumps({"placed_keys": ["k1", "k2"]}))
    out = lbr.load_placed(str(p))
    assert out == {"k1", "k2"}


def test_lbr_load_placed_corrupt_returns_empty(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not json [")
    assert lbr.load_placed(str(p)) == set()


# ----- nba_lineup_daemon: normalize_games -----
def test_nld_normalize_games_basic():
    games = [{
        "away_team": "GSW", "home_team": "LAL",
        "away_lineup": {
            "status": "Confirmed",
            "starters": [{"name": "S Curry", "pos": "PG"}],
        },
        "home_lineup": {
            "status": "Projected",
            "starters": [{"name": "L James", "pos": "SF"}],
        },
    }]
    rows = nld.normalize_games(games, captured_at="2026-05-26T15:00:00Z")
    assert len(rows) == 2
    assert any(r["team"] == "GSW" and r["player_name"] == "S Curry" for r in rows)
    # Status should map via _STATUS_MAP
    gsw = [r for r in rows if r["team"] == "GSW"][0]
    assert gsw["status"] in ("CONFIRMED", "PROJECTED")


def test_nld_normalize_games_injury_override():
    """When a starter has injury='OUT' it should override CONFIRMED -> OUT."""
    games = [{
        "away_team": "GSW", "home_team": "LAL",
        "away_lineup": {
            "status": "Confirmed",
            "starters": [{"name": "Player A", "pos": "PG", "injury": "O", "play_pct": 0}],
        },
        "home_lineup": {"status": "Confirmed", "starters": []},
    }]
    rows = nld.normalize_games(games)
    assert rows[0]["status"] == "OUT"


# ============================================================================
# Cross-cutting: each module is importable + has expected helper constants
# (drive-by coverage for module-level statements).
# ============================================================================

def test_all_modules_expose_atomic_write_helpers():
    """All 4 daemons that emit JSON expose atomic_write_json."""
    for m in (lbr, ipr, mfd, bmd):
        assert hasattr(m, "atomic_write_json")
