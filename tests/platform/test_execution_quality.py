"""tests/platform/test_execution_quality.py -- execution_quality scoreboard tests.

Synthetic ledger fixtures only (no real ledger I/O): bucket math, coverage %,
and the banned-token honesty guard. Mirrors the _strip_dollar / banned-key
convention already used by clv_ledger.py's _BANNED_KEYS and
pm_trading/test_scoreboard_venue.py's _BANNED set.

Run: python -m pytest tests/platform/test_execution_quality.py -q
"""
from __future__ import annotations

from scripts.platformkit.clv import execution_quality as EQ
from scripts.platformkit.clv import execution_quality_math as M

_BANNED = {"pnl", "roi", "dollar", "profit", "revenue", "bankroll"}


def _ledger_row(bet_id, channel, sport="mlb", venue=None, clv_status="no_close",
                 clv_pct=None, settled_at="2026-06-25T00:00:00Z"):
    r = {"bet_id": bet_id, "channel": channel, "status": "settled",
         "sport": sport, "clv_status": clv_status, "clv_pct": clv_pct,
         "settled_at": settled_at, "unit_result": 0.0}
    if venue is not None:
        r["venue"] = venue
    return r


# ---------------------------------------------------------------------------
# execution_quality_math: percentile / distribution / timing bucket math
# ---------------------------------------------------------------------------

def test_percentile_basic():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert M.percentile(vals, 0.0) == 1.0
    assert M.percentile(vals, 100.0) == 5.0
    assert M.percentile(vals, 50.0) == 3.0


def test_percentile_empty_is_none():
    assert M.percentile([], 50.0) is None


def test_clv_distribution_reports_mean_median_p10_p90():
    dist = M.clv_distribution([-10.0, -5.0, 0.0, 5.0, 10.0])
    assert dist["n"] == 5
    assert dist["mean"] == 0.0
    assert dist["median"] == 0.0
    assert dist["p10"] is not None and dist["p90"] is not None
    assert dist["p10"] < dist["p90"]


def test_clv_distribution_empty():
    dist = M.clv_distribution([])
    assert dist == {"n": 0, "mean": None, "median": None, "p10": None, "p90": None}


def test_timing_bucket_math_all_ranges():
    # 30h before -> 24h+_before
    assert M.timing_bucket(30.0) == "24h+_before"
    # 10h before -> 6-24h_before
    assert M.timing_bucket(10.0) == "6-24h_before"
    # 3h before -> 1-6h_before
    assert M.timing_bucket(3.0) == "1-6h_before"
    # 0.5h before -> 0-1h_before
    assert M.timing_bucket(0.5) == "0-1h_before"
    # negative (logged after commence) -> at_or_after_commence
    assert M.timing_bucket(-2.0) == "at_or_after_commence"
    # exactly at commence -> at_or_after_commence (boundary is inclusive-low)
    assert M.timing_bucket(0.0) == "at_or_after_commence"


def test_parse_iso_hours_before_positive_and_negative():
    # logged 2h before a 2026-06-25T02:00Z commence
    hrs = M.parse_iso_hours_before("2026-06-25T00:00:00Z", "2026-06-25T02:00:00Z")
    assert hrs is not None and abs(hrs - 2.0) < 1e-6
    # logged after commence -> negative
    hrs2 = M.parse_iso_hours_before("2026-06-25T03:00:00Z", "2026-06-25T02:00:00Z")
    assert hrs2 is not None and hrs2 < 0.0


def test_parse_iso_hours_before_malformed_is_none():
    assert M.parse_iso_hours_before("not-a-date", "2026-06-25T02:00:00Z") is None
    assert M.parse_iso_hours_before(None, None) is None


def test_entry_timing_from_graded_buckets_and_skips_bad_rows():
    rows = [
        {"logged_at": "2026-06-25T00:00:00Z", "commence_time": "2026-06-25T02:00:00Z"},  # 2h -> 1-6h
        {"logged_at": "2026-06-24T00:00:00Z", "commence_time": "2026-06-25T02:00:00Z"},  # 26h -> 24h+
        {"logged_at": None, "commence_time": None},  # unparseable -> skipped
    ]
    out = M.entry_timing_from_graded(rows)
    assert out["n_rows"] == 3
    assert out["n_timing_parsed"] == 2
    assert out["buckets"].get("1-6h_before") == 1
    assert out["buckets"].get("24h+_before") == 1


# ---------------------------------------------------------------------------
# execution_quality: coverage % + cell aggregation
# ---------------------------------------------------------------------------

def test_cell_stats_coverage_pct():
    rows = [
        _ledger_row("m1", "moneyline", clv_status="true_close", clv_pct=5.0),
        _ledger_row("m2", "moneyline", clv_status="true_close", clv_pct=-3.0),
        _ledger_row("m3", "moneyline", clv_status="no_close", clv_pct=None),
        _ledger_row("m4", "moneyline", clv_status="no_close", clv_pct=None),
    ]
    stats = EQ._cell_stats(rows)
    assert stats["n_settled"] == 4
    assert stats["n_measurable"] == 2
    assert stats["true_close_coverage_pct"] == 50.0
    assert stats["clv_distribution_pct"]["n"] == 2


def test_cell_stats_zero_coverage_when_no_close():
    rows = [_ledger_row("p%d" % i, "paper", clv_status="no_close") for i in range(5)]
    stats = EQ._cell_stats(rows)
    assert stats["n_measurable"] == 0
    assert stats["true_close_coverage_pct"] == 0.0
    assert stats["clv_distribution_pct"]["mean"] is None


def test_build_scoreboard_splits_by_phase_sport_venue():
    ledger = [
        _ledger_row("i1", "paper_ingame", sport="mlb", clv_status="no_close"),
        _ledger_row("p1", "paper_pm", sport="mlb", venue="kalshi",
                    clv_status="true_close", clv_pct=10.0),
        _ledger_row("p2", "paper_pm", sport="mlb", venue="kalshi",
                    clv_status="true_close", clv_pct=-2.0),
    ]
    report = EQ.build_scoreboard(ledger=ledger, graded_rows=[], prop_ledger_rows=[])
    cells = report["cells"]
    ingame_keys = [k for k in cells if cells[k]["phase"] == "ingame"]
    pregame_keys = [k for k in cells if cells[k]["phase"] == "pregame"]
    assert len(ingame_keys) == 1
    assert len(pregame_keys) == 1
    pm_cell = cells[pregame_keys[0]]
    assert pm_cell["venue"] == "kalshi"
    assert pm_cell["n_measurable"] == 2
    assert pm_cell["true_close_coverage_pct"] == 100.0


def test_build_scoreboard_reports_pregame_prediction_ledger_and_props_context():
    graded = [
        {"logged_at": "2026-06-25T00:00:00Z", "commence_time": "2026-06-25T02:00:00Z",
         "status": "settled", "clv_status": "no_close", "clv_pct": None},
    ]
    prop_rows = [{"status": "settled"}, {"status": "open"}]
    report = EQ.build_scoreboard(ledger=[], graded_rows=graded, prop_ledger_rows=prop_rows)
    pg = report["pregame_prediction_ledger"]
    assert pg["n_settled"] == 1
    assert pg["true_close_coverage_pct"] == 0.0
    assert pg["entry_timing"]["n_timing_parsed"] == 1
    sp = report["separate_props_ledger"]
    assert sp["n_settled"] == 1
    assert sp["n_total_rows"] == 2


def test_ingame_prop_reproduction_reports_guard_status():
    rep = EQ._ingame_prop_reproduction()
    assert rep["guard_module"] == "scripts.platformkit.improve.ingame_prop_clv_guard"
    assert isinstance(rep["guard_enabled"], bool)
    assert "-31.0%" in rep["note"]


# ---------------------------------------------------------------------------
# Honesty rail: no banned dollar/pnl/roi token anywhere in the output
# ---------------------------------------------------------------------------

def _check_no_banned_keys(d):
    if isinstance(d, dict):
        for key, val in d.items():
            for banned in _BANNED:
                assert banned not in str(key).lower(), (
                    "banned key %r found (banned token %r)" % (key, banned))
            _check_no_banned_keys(val)
    elif isinstance(d, list):
        for item in d:
            _check_no_banned_keys(item)


def test_output_has_no_banned_dollar_tokens():
    ledger = [
        _ledger_row("m1", "moneyline", clv_status="true_close", clv_pct=5.0),
        _ledger_row("i1", "paper_ingame", clv_status="no_close"),
    ]
    report = EQ.build_scoreboard(ledger=ledger, graded_rows=[], prop_ledger_rows=[])
    _check_no_banned_keys(report)
    EQ._assert_no_banned_tokens(report)  # module's own guard must also pass


def test_assert_no_banned_tokens_raises_on_violation():
    bad = {"channel_pnl": 1.0}
    try:
        EQ._assert_no_banned_tokens(bad)
        raised = False
    except AssertionError:
        raised = True
    assert raised


def test_render_md_runs_and_has_no_dollar_sign():
    ledger = [
        _ledger_row("m1", "moneyline", clv_status="true_close", clv_pct=5.0),
    ]
    report = EQ.build_scoreboard(ledger=ledger, graded_rows=[], prop_ledger_rows=[])
    md = EQ.render_md(report)
    assert "Execution Quality Scoreboard" in md
    assert "$" not in md
