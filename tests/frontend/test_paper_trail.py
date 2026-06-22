"""Per-file test: frontend.paper_trail -- collapse, executed invariant, empty-ledger safety.

Run: python -m pytest tests/frontend/test_paper_trail.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from frontend.paper_trail import clv_summary, read_trail


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _write_ledger(path: Path, rows: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


def _open_row(matchup: str = "NYK@SAS", sport: str = "nba", ts: str = "2026-06-18T22:00:00+00:00") -> dict:
    return {
        "ts": ts,
        "sport": sport,
        "matchup": matchup,
        "side": "away",
        "taken_book": "espn:DraftKings",
        "taken_decimal": 2.6,
        "model_prob": 0.4145,
        "stake_units": 1.0,
        "market_type": "moneyline",
        "status": "open",
        "executed": False,
    }


def _settled_row(matchup: str = "NYK@SAS", sport: str = "nba",
                 ts: str = "2026-06-18T22:00:00+00:00") -> dict:
    base = _open_row(matchup, sport, ts)
    base.update({
        "status": "settled",
        "executed": False,
        "settled_at": "2026-06-18T23:00:00+00:00",
        "clv_pct": None,
        "beat_close": None,
        "clv_is_proxy": False,  # no-close settle: EXPLICIT False (PE-P0-03)
        "clv_status": "no_close",
        "clv_note": "no closing line captured; CLV unavailable (win/loss only)",
        "graded": True,
        "outcome": "win",
        "home_score": 90,
        "away_score": 94,
        "unit_result": 1.6,
        "settle_key": "nba|NYK@SAS|away|espn:DraftKings|2.6|" + ts,
    })
    return base


# ---------------------------------------------------------------------------
# Tests: empty / missing ledger
# ---------------------------------------------------------------------------

def test_read_trail_missing_ledger(tmp_path):
    """Missing ledger must return empty list, never raise."""
    trail = read_trail(ledger_path=tmp_path / "nonexistent.jsonl")
    assert trail == []


def test_clv_summary_missing_ledger(tmp_path):
    """Missing ledger -> n_bets=0 sentinel, never raise."""
    summary = clv_summary(ledger_path=tmp_path / "nonexistent.jsonl")
    assert summary["n_bets"] == 0
    assert summary["pct_beat_close"] is None
    assert summary["mean_clv_pct"] is None


def test_read_trail_corrupt_ledger(tmp_path):
    """Corrupt ledger -> empty trail, never raise."""
    p = tmp_path / "corrupt.jsonl"
    p.write_text("not json at all\n", encoding="utf-8")
    trail = read_trail(ledger_path=p)
    assert trail == []


# ---------------------------------------------------------------------------
# Tests: collapse open->settled
# ---------------------------------------------------------------------------

def test_collapse_open_only(tmp_path):
    """An open-only bet stays open; exactly one row returned."""
    p = _write_ledger(tmp_path / "ledger.jsonl", [_open_row()])
    trail = read_trail(ledger_path=p)
    assert len(trail) == 1
    row = trail[0]
    assert row["status"] == "open"
    assert row["executed"] is False


def test_collapse_open_then_settled(tmp_path):
    """Open + settled twin for the same bet collapses to ONE settled row."""
    rows = [_open_row(), _settled_row()]
    p = _write_ledger(tmp_path / "ledger.jsonl", rows)
    trail = read_trail(ledger_path=p)
    # Exactly one bet
    assert len(trail) == 1
    row = trail[0]
    assert row["status"] == "settled"
    assert row["graded"] is True
    assert row["outcome"] == "win"


def test_collapse_two_distinct_bets(tmp_path):
    """Two distinct bets (different matchup) stay as two rows."""
    rows = [
        _open_row("NYK@SAS", "nba", "2026-06-18T22:00:00+00:00"),
        _open_row("BOS@MIA", "nba", "2026-06-18T22:01:00+00:00"),
    ]
    p = _write_ledger(tmp_path / "ledger.jsonl", rows)
    trail = read_trail(ledger_path=p)
    assert len(trail) == 2


def test_collapse_settled_comes_before_open(tmp_path):
    """Settled bets sort before open bets in the returned list."""
    open1 = _open_row("BOS@MIA", "nba", "2026-06-18T22:01:00+00:00")
    open2 = _open_row("NYK@SAS", "nba", "2026-06-18T22:00:00+00:00")
    settled2 = _settled_row("NYK@SAS", "nba", "2026-06-18T22:00:00+00:00")
    rows = [open1, open2, settled2]
    p = _write_ledger(tmp_path / "ledger.jsonl", rows)
    trail = read_trail(ledger_path=p)
    assert len(trail) == 2
    # settled row must come first
    assert trail[0]["status"] == "settled"
    assert trail[1]["status"] == "open"


# ---------------------------------------------------------------------------
# Tests: executed invariant
# ---------------------------------------------------------------------------

def test_executed_always_false_open(tmp_path):
    """executed is ALWAYS False on every trail row (paper-only invariant)."""
    # Even if the raw row carries executed=True (should never happen), the
    # trail module always outputs False.
    row = _open_row()
    row["executed"] = True  # tamper
    p = _write_ledger(tmp_path / "ledger.jsonl", [row])
    trail = read_trail(ledger_path=p)
    assert trail[0]["executed"] is False


def test_executed_always_false_settled(tmp_path):
    """Settled row also has executed=False."""
    p = _write_ledger(tmp_path / "ledger.jsonl", [_settled_row()])
    trail = read_trail(ledger_path=p)
    assert trail[0]["executed"] is False


# ---------------------------------------------------------------------------
# Tests: field shapes
# ---------------------------------------------------------------------------

def test_trail_row_has_expected_fields(tmp_path):
    """Every trail row has all required fields for the React panel."""
    required = {
        "game_id", "matchup", "sport", "side", "market_type", "line",
        "taken_book", "taken_decimal", "model_prob", "model_ev", "tier",
        "stake_units", "status", "graded", "outcome", "clv_pct", "beat_close",
        "clv_is_proxy", "clv_status", "clv_unavailable", "clv_note", "executed",
        "ts", "settled_at",
    }
    p = _write_ledger(tmp_path / "ledger.jsonl", [_open_row()])
    trail = read_trail(ledger_path=p)
    missing = required - set(trail[0].keys())
    assert not missing, "Missing fields: %s" % missing


def test_no_dollar_fields(tmp_path):
    """HONESTY: no dollar / roi / profit / pnl / bankroll / bare-stake key on rows.

    stake_units (a UNIT count) IS allowed; a bare 'stake' / 'pnl' / 'roi' is not.
    """
    # Even if a legacy raw row still carries $ keys, the trail row must not.
    legacy = _open_row()
    legacy["stake"] = 315.41  # legacy dollar field on the raw ledger
    settled = _settled_row()
    settled["pnl"] = 25.34  # legacy dollar pnl on the raw ledger
    p = _write_ledger(tmp_path / "ledger.jsonl", [legacy, settled])
    trail = read_trail(ledger_path=p)
    assert trail, "expected at least one trail row"
    banned_exact = {"stake", "pnl", "total_pnl", "total_stake", "paper_roi",
                    "roi", "bankroll", "profit", "dollars"}
    for row in trail:
        keys_lower = {k.lower() for k in row}
        assert not (banned_exact & keys_lower), (
            "banned $ keys on trail row: %s" % (banned_exact & keys_lower))
        for sub in ("dollar",):
            assert not any(sub in k for k in keys_lower)


def test_model_ev_computed(tmp_path):
    """model_ev = model_prob * taken_decimal - 1 (EV per unit, not dollars)."""
    p = _write_ledger(tmp_path / "ledger.jsonl", [_open_row()])
    trail = read_trail(ledger_path=p)
    row = trail[0]
    assert row["model_prob"] == pytest.approx(0.4145)
    assert row["taken_decimal"] == pytest.approx(2.6)
    expected_ev = 0.4145 * 2.6 - 1.0
    assert row["model_ev"] == pytest.approx(expected_ev, rel=1e-5)


def test_no_close_is_void_not_proxy(tmp_path):
    """PE-P0-03: a NO-close settle (clv_pct=null, clv_is_proxy=False) must render
    VOID/pending -- NEVER an inferred '(proxy)' label (fabricated confidence)."""
    row = _settled_row()
    row["clv_is_proxy"] = False  # grader sets this EXPLICITLY on a no-close settle
    row["clv_status"] = "no_close"
    p = _write_ledger(tmp_path / "ledger.jsonl", [row])
    trail = read_trail(ledger_path=p)
    out = trail[0]
    assert out["clv_pct"] is None
    assert out["clv_is_proxy"] is False, "no-close must NOT be labelled proxy"
    assert out["clv_unavailable"] is True
    assert out["clv_status"] == "no_close"


def test_explicit_proxy_flag_is_respected(tmp_path):
    """A genuinely proxy-settled row (clv_is_proxy=True from the grader) is True."""
    row = _settled_row()
    row.update({"clv_pct": 1.23, "beat_close": True, "clv_is_proxy": True,
                "clv_status": "proxy"})
    p = _write_ledger(tmp_path / "ledger.jsonl", [row])
    out = read_trail(ledger_path=p)[0]
    assert out["clv_is_proxy"] is True
    assert out["clv_unavailable"] is False
    assert out["clv_pct"] == pytest.approx(1.23)


def test_clv_summary_structure(tmp_path):
    """clv_summary returns the expected top-level keys."""
    p = _write_ledger(tmp_path / "ledger.jsonl", [_settled_row()])
    summary = clv_summary(ledger_path=p)
    required_keys = {
        "n_bets", "pct_beat_close", "mean_clv_pct",
        "clv_is_proxy", "by_sport", "note",
    }
    missing = required_keys - set(summary.keys())
    assert not missing, "Missing summary keys: %s" % missing


def test_clv_summary_proxy_flagged(tmp_path):
    """clv_is_proxy=True in summary ONLY when a settled row was EXPLICITLY proxy."""
    proxy_row = _settled_row()
    proxy_row.update({"clv_pct": 0.5, "clv_is_proxy": True, "clv_status": "proxy"})
    p = _write_ledger(tmp_path / "ledger.jsonl", [proxy_row])
    summary = clv_summary(ledger_path=p)
    assert summary["clv_is_proxy"] is True


def test_clv_summary_no_close_not_proxy(tmp_path):
    """PE-P0-03: a no-close settle is counted as n_no_close, NOT as proxy."""
    row = _settled_row()
    row["clv_is_proxy"] = False  # explicit: no close, not a proxy
    p = _write_ledger(tmp_path / "ledger.jsonl", [row])
    summary = clv_summary(ledger_path=p)
    assert summary["clv_is_proxy"] is False
    assert summary["n_no_close"] == 1


# ---------------------------------------------------------------------------
# Tests: synthetic/malformed row filter (PT-SYNTH)
# ---------------------------------------------------------------------------

def _synthetic_test_sport_row() -> dict:
    """Row whose sport starts with 'test_' -- must be filtered at read time."""
    row = _open_row()
    row["sport"] = "test_none_path_no_raise"
    return row


def _synthetic_short_game_id_row() -> dict:
    """Row with a game_id shorter than _MIN_GAME_ID_LEN=3 -- malformed, filter it."""
    row = _open_row()
    row["game_id"] = "gg"  # len=2 < 3
    return row


def _real_row() -> dict:
    """A valid, non-synthetic row that MUST pass through the filter."""
    return _open_row("LAL@GSW", "nba", "2026-06-19T02:00:00+00:00")


def test_synthetic_sport_row_filtered_from_trail(tmp_path):
    """Rows with sport starting with 'test_' must NEVER appear in read_trail output."""
    rows = [_synthetic_test_sport_row(), _real_row()]
    p = _write_ledger(tmp_path / "ledger.jsonl", rows)
    trail = read_trail(ledger_path=p)
    sports = [r["sport"] for r in trail]
    assert not any(s.startswith("test_") for s in sports), (
        "synthetic test_ sport row leaked into trail: %s" % sports
    )
    # The real row must still be present
    assert len(trail) == 1
    assert trail[0]["sport"] == "nba"


def test_short_game_id_row_filtered_from_trail(tmp_path):
    """Rows with game_id shorter than _MIN_GAME_ID_LEN=3 must NEVER appear in read_trail."""
    rows = [_synthetic_short_game_id_row(), _real_row()]
    p = _write_ledger(tmp_path / "ledger.jsonl", rows)
    trail = read_trail(ledger_path=p)
    # 'gg' row must be gone; real row survives
    assert len(trail) == 1
    assert trail[0]["sport"] == "nba"


def test_mixed_synthetic_and_real_yields_only_real(tmp_path):
    """A ledger mixing sport=test_* rows, short game_id rows, and real rows
    must yield ONLY the real rows from both read_trail and _load_raw."""
    from frontend.paper_trail import _load_raw
    rows = [
        _synthetic_test_sport_row(),   # sport=test_none_path_no_raise -- FILTERED
        _synthetic_short_game_id_row(),  # game_id='gg' -- FILTERED
        _real_row(),                   # valid -- PASSES
    ]
    p = _write_ledger(tmp_path / "ledger.jsonl", rows)

    # _load_raw must expose 0 synthetic rows
    raw = _load_raw(ledger_path=p)
    assert len(raw) == 1
    assert raw[0]["sport"] == "nba"

    # read_trail must yield 0 of the synthetic rows
    trail = read_trail(ledger_path=p)
    assert len(trail) == 1
    assert trail[0]["sport"] == "nba"
    assert not any(r["sport"].startswith("test_") for r in trail)


def test_filter_does_not_drop_real_settled_row(tmp_path):
    """Real settled rows must survive the synthetic filter unchanged."""
    rows = [_settled_row()]  # sport='nba', no game_id field on raw row
    p = _write_ledger(tmp_path / "ledger.jsonl", rows)
    trail = read_trail(ledger_path=p)
    assert len(trail) == 1
    assert trail[0]["status"] == "settled"
    assert trail[0]["sport"] == "nba"


def test_open_rows_newest_first(tmp_path):
    """Within the open bucket, the most recently-placed bet comes first so a freshly-fired
    in-game position surfaces at the top (not buried under the read cap)."""
    rows = [
        _open_row("OLD@GAME", "soccer_intl", "2026-06-22T10:00:00+00:00"),
        _open_row("MID@GAME", "soccer_intl", "2026-06-22T12:00:00+00:00"),
        _open_row("NEW@GAME", "soccer_intl", "2026-06-22T17:30:00+00:00"),
    ]
    p = _write_ledger(tmp_path / "ledger.jsonl", rows)
    trail = read_trail(ledger_path=p)
    assert [r["matchup"] for r in trail] == ["NEW@GAME", "MID@GAME", "OLD@GAME"]


def test_settled_before_open_still_holds_with_recency(tmp_path):
    """Settled-before-open contract holds even though a newer OPEN bet exists."""
    settled_old = _settled_row("AAA@BBB", "nba", "2026-06-18T22:00:00+00:00")
    open_new = _open_row("CCC@DDD", "nba", "2026-06-22T22:00:00+00:00")
    p = _write_ledger(tmp_path / "ledger.jsonl", [open_new, settled_old])
    trail = read_trail(ledger_path=p)
    assert trail[0]["status"] == "settled" and trail[1]["status"] == "open"
