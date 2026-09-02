"""Per-file tests for scripts.platformkit.pm_trading.scoreboard.

Run ONLY this file (the full suite freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_scoreboard.py -q

Covers:
  - injected rows -> correct N / mean_clv_pct / pct_beat_close / true-vs-proxy / by-sport
  - flat-unit wins/losses/clv
  - empty ledger -> zeros / nulls, never a crash
  - push rows counted in N but excluded from flat_unit_clv decided set
  - rows without clv_pct excluded from settled count
  - write_scoreboard: atomic (tmp+os.replace), returns correct path, valid JSON
  - gate constants are present (N, CLV_LB, pct-beat-close; no ROI anywhere)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.pm_trading.scoreboard import (
    GATE_CLV_LB_PCT,
    GATE_MIN_N,
    GATE_PCT_BEAT_CLOSE,
    MIN_CLV_N,
    build_scoreboard,
    write_scoreboard,
)


def _settled_n(n: int, clv_pct: float = 1.0, **kw) -> List[Dict[str, Any]]:
    """n settled rows all carrying the same clv_pct (to exceed the small-N floor)."""
    return [_settled(clv_pct, **kw) for _ in range(n)]


# ---------------------------------------------------------------------------
# Helpers to build synthetic ledger rows
# ---------------------------------------------------------------------------

def _open_row(sport: str = "nba", matchup: str = "A@B") -> Dict[str, Any]:
    """An open (unsettled) row -- must be excluded from all CLV stats."""
    return {"status": "open", "sport": sport, "matchup": matchup,
            "side": "home", "taken_decimal": 1.90, "executed": False}


def _settled(
    clv_pct: float,
    sport: str = "nba",
    matchup: str = "A@B",
    outcome: str = "win",
    clv_is_proxy: bool = False,
) -> Dict[str, Any]:
    """A settled row with a real clv_pct value."""
    return {
        "status": "settled",
        "sport": sport,
        "matchup": matchup,
        "side": "home",
        "taken_decimal": 1.90,
        "executed": False,
        "clv_pct": clv_pct,
        "beat_close": clv_pct > 0.0,
        "outcome": outcome,
        "clv_is_proxy": clv_is_proxy,
    }


def _settled_no_close(sport: str = "nba", outcome: str = "win") -> Dict[str, Any]:
    """A settled row WITHOUT a clv_pct (no closing line found): excluded from CLV stats."""
    return {
        "status": "settled",
        "sport": sport,
        "matchup": "X@Y",
        "side": "home",
        "taken_decimal": 1.90,
        "executed": False,
        "clv_pct": None,
        "outcome": outcome,
    }


# ---------------------------------------------------------------------------
# Empty ledger
# ---------------------------------------------------------------------------

def test_empty_ledger_no_crash():
    board = build_scoreboard(rows=[])
    assert board["n_settled"] == 0
    # Below MIN_CLV_N (0 < 8): mean CLV is suppressed as INSUFFICIENT_DATA, never
    # a fabricated number; n_clv surfaces the (zero) true-close sample size.
    assert board["mean_clv_pct"] == "INSUFFICIENT_DATA"
    assert board["n_clv"] == 0
    assert board["min_clv_n"] == MIN_CLV_N
    assert board["pct_beat_close"] is None
    assert board["n_true_close"] == 0
    assert board["n_proxy_close"] == 0
    assert board["flat_unit_wins"] == 0
    assert board["flat_unit_losses"] == 0
    assert board["flat_unit_clv"] is None
    assert board["by_sport"] == {}
    assert "honest_note" in board
    assert "as_of" in board


def test_open_rows_excluded():
    """Open rows (status='open') must contribute nothing to settled stats."""
    rows = [_open_row(), _open_row(), _open_row()]
    board = build_scoreboard(rows=rows)
    assert board["n_settled"] == 0
    assert board["mean_clv_pct"] == "INSUFFICIENT_DATA"


def test_settled_no_close_excluded_from_clv_count():
    """Rows with clv_pct=None (no close found) are excluded from the CLV counts but
    still counted as real settled bets.

    Contract set by 8b297860b (2026-06-26): n_settled counts EVERY status='settled'
    row so the track record cannot under-report itself to zero; the no-close rows
    surface separately as n_no_close and contribute nothing to any CLV statistic.
    """
    rows = [_settled_no_close(), _settled_no_close()]
    board = build_scoreboard(rows=rows)
    assert board["n_settled"] == 2      # real settled bets, counted honestly
    assert board["n_no_close"] == 2     # ... and flagged as carrying no close
    # every CLV statistic stays empty: no close was captured, so none is computable
    assert board["n_clv"] == 0
    assert board["n_true_close"] == 0
    assert board["n_proxy_close"] == 0
    assert board["mean_clv_pct"] == "INSUFFICIENT_DATA"
    assert board["pct_beat_close"] is None
    assert board["flat_unit_clv"] is None


# ---------------------------------------------------------------------------
# N / mean / pct-beat-close
# ---------------------------------------------------------------------------

def test_n_settled_counts_all_settled_and_n_clv_counts_only_clv_rows():
    """n_settled is the settled population; n_clv/n_no_close split it by close capture."""
    rows = [
        _settled(2.5),          # settled + has clv_pct
        _settled(-1.0),         # settled + has clv_pct
        _open_row(),            # open -> excluded from every settled count
        _settled_no_close(),    # settled, no clv_pct -> in n_settled, not in n_clv
    ]
    board = build_scoreboard(rows=rows)
    assert board["n_settled"] == 3      # the three settled rows
    assert board["n_clv"] == 2          # only the two carrying a captured close
    assert board["n_no_close"] == 1
    # the CLV denominator is the clv subset (2), never the settled count (3)
    assert board["pct_beat_close"] == 50.0


def test_mean_clv_pct():
    # >= MIN_CLV_N rows so the real mean is reported (not suppressed by the floor).
    # 8 rows: six at 4.0, plus -2.0 and 2.0 -> mean = (6*4 - 2 + 2)/8 = 24/8 = 3.0
    rows = _settled_n(6, 4.0) + [_settled(-2.0), _settled(2.0)]
    board = build_scoreboard(rows=rows)
    assert board["n_settled"] == 8
    assert abs(board["mean_clv_pct"] - 3.0) < 1e-4
    assert board["n_clv"] == 8


def test_mean_clv_insufficient_data_below_floor():
    """Below MIN_CLV_N true closes, mean_clv_pct is INSUFFICIENT_DATA + n_clv surfaced."""
    rows = [_settled(4.0), _settled(-2.0), _settled(2.0)]  # n=3 < 8
    board = build_scoreboard(rows=rows)
    assert board["n_settled"] == 3
    assert board["mean_clv_pct"] == "INSUFFICIENT_DATA"
    assert board["n_clv"] == 3
    assert board["min_clv_n"] == MIN_CLV_N


def test_mean_clv_reported_at_exactly_floor():
    """Exactly MIN_CLV_N true closes is enough to report a real mean (>=, not >)."""
    rows = _settled_n(MIN_CLV_N, 2.0)
    board = build_scoreboard(rows=rows)
    assert board["n_clv"] == MIN_CLV_N
    assert board["mean_clv_pct"] == pytest.approx(2.0)


def test_pct_beat_close_all_positive():
    rows = [_settled(1.0), _settled(2.0), _settled(0.5)]
    board = build_scoreboard(rows=rows)
    assert board["pct_beat_close"] == pytest.approx(100.0)


def test_pct_beat_close_none_positive():
    rows = [_settled(-1.0), _settled(-0.5)]
    board = build_scoreboard(rows=rows)
    assert board["pct_beat_close"] == pytest.approx(0.0)


def test_pct_beat_close_mixed():
    # 2 positive, 2 negative -> 50%
    rows = [_settled(1.0), _settled(-1.0), _settled(2.0), _settled(-2.0)]
    board = build_scoreboard(rows=rows)
    assert board["pct_beat_close"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# True vs proxy close counts
# ---------------------------------------------------------------------------

def test_true_close_count():
    rows = [
        _settled(1.0, clv_is_proxy=False),   # true
        _settled(1.0, clv_is_proxy=False),   # true
        _settled(0.5, clv_is_proxy=True),    # proxy
    ]
    board = build_scoreboard(rows=rows)
    assert board["n_true_close"] == 2
    assert board["n_proxy_close"] == 1
    # n_clv is the TRUE-close count backing mean_clv_pct (proxy excluded).
    assert board["n_clv"] == 2


def test_proxy_rows_still_counted_in_n_settled():
    """Proxy CLV rows are included in n_settled -- they have a clv_pct."""
    rows = [_settled(1.0, clv_is_proxy=True), _settled(-1.0, clv_is_proxy=True)]
    board = build_scoreboard(rows=rows)
    assert board["n_settled"] == 2
    assert board["n_proxy_close"] == 2
    assert board["n_true_close"] == 0
    # No true close -> the mean yardstick has nothing to stand on.
    assert board["n_clv"] == 0
    assert board["mean_clv_pct"] == "INSUFFICIENT_DATA"


def test_proxy_close_excluded_from_mean_clv():
    """A proxy close must NOT contaminate the headline mean_clv_pct.

    MIN_CLV_N true closes at +2.0 plus one wildly positive proxy at +100.0: the
    reported mean must be exactly +2.0 (proxy excluded), n_clv stays the true count,
    and the proxy is still surfaced via n_proxy_close / n_settled.
    """
    rows = _settled_n(MIN_CLV_N, 2.0) + [_settled(100.0, clv_is_proxy=True)]
    board = build_scoreboard(rows=rows)
    assert board["mean_clv_pct"] == pytest.approx(2.0)   # NOT pulled up by the proxy
    assert board["n_clv"] == MIN_CLV_N                   # true-close count only
    assert board["n_proxy_close"] == 1
    assert board["n_settled"] == MIN_CLV_N + 1           # proxy still counted as settled


# ---------------------------------------------------------------------------
# Flat-unit record
# ---------------------------------------------------------------------------

def test_flat_unit_wins_and_losses():
    rows = [
        _settled(1.0, outcome="win"),
        _settled(-0.5, outcome="loss"),
        _settled(0.5, outcome="win"),
        _settled(0.0, outcome="push"),   # push: excluded from flat_unit_clv set
    ]
    board = build_scoreboard(rows=rows)
    assert board["flat_unit_wins"] == 2
    assert board["flat_unit_losses"] == 1


def test_flat_unit_clv_excludes_pushes():
    """flat_unit_clv is mean over won+lost rows only (push rows excluded)."""
    rows = [
        _settled(4.0, outcome="win"),
        _settled(-2.0, outcome="loss"),
        _settled(99.0, outcome="push"),  # push excluded from decided set
    ]
    board = build_scoreboard(rows=rows)
    # mean over win+loss: (4 + -2) / 2 = 1.0
    assert board["flat_unit_clv"] == pytest.approx(1.0)


def test_flat_unit_clv_none_when_only_pushes():
    rows = [_settled(1.0, outcome="push"), _settled(-1.0, outcome="push")]
    board = build_scoreboard(rows=rows)
    assert board["flat_unit_clv"] is None


# ---------------------------------------------------------------------------
# Per-sport breakdown
# ---------------------------------------------------------------------------

def test_by_sport_keys():
    rows = [
        _settled(1.0, sport="nba"),
        _settled(-1.0, sport="nba"),
        _settled(2.0, sport="mlb"),
    ]
    board = build_scoreboard(rows=rows)
    assert set(board["by_sport"].keys()) == {"nba", "mlb"}


def test_by_sport_nba_stats():
    rows = [
        _settled(3.0, sport="nba", outcome="win", clv_is_proxy=False),
        _settled(-1.0, sport="nba", outcome="loss", clv_is_proxy=True),
        _settled(2.0, sport="mlb", outcome="win", clv_is_proxy=False),
    ]
    board = build_scoreboard(rows=rows)
    nba = board["by_sport"]["nba"]
    assert nba["n"] == 2
    # mean_clv_pct is over TRUE-close rows only: the proxy (-1.0) is excluded, so the
    # mean is the lone true close (+3.0), NOT the proxy-contaminated (3 + -1)/2 = 1.0.
    assert abs(nba["mean_clv_pct"] - 3.0) < 1e-4
    # pct_beat_close stays over ALL settled rows in the sport (1 of 2 positive = 50%).
    assert nba["pct_beat_close"] == pytest.approx(50.0)
    assert nba["n_true_close"] == 1
    assert nba["n_proxy_close"] == 1
    assert nba["flat_unit_wins"] == 1
    assert nba["flat_unit_losses"] == 1


def test_by_sport_mlb_only_wins():
    rows = [
        _settled(1.0, sport="mlb", outcome="win", clv_is_proxy=False),
        _settled(2.0, sport="mlb", outcome="win", clv_is_proxy=False),
    ]
    board = build_scoreboard(rows=rows)
    mlb = board["by_sport"]["mlb"]
    assert mlb["n"] == 2
    assert mlb["flat_unit_wins"] == 2
    assert mlb["flat_unit_losses"] == 0
    assert mlb["pct_beat_close"] == pytest.approx(100.0)


def test_by_sport_empty_sport_bucket():
    """If a sport somehow has zero rows after filter, _sport_bucket must return zeros."""
    rows = [_settled(1.0, sport="nba")]
    board = build_scoreboard(rows=rows)
    # Only 'nba' should appear; no empty phantom buckets.
    assert list(board["by_sport"].keys()) == ["nba"]
    assert board["by_sport"]["nba"]["n"] == 1


# ---------------------------------------------------------------------------
# write_scoreboard -- atomic write
# ---------------------------------------------------------------------------

def test_write_scoreboard_creates_file(tmp_path: Path):
    dest = tmp_path / "frontend" / "grade_summary.json"
    result = write_scoreboard(out_path=dest)
    assert result == dest
    assert dest.exists()
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert "n_settled" in data
    assert "honest_note" in data


def test_write_scoreboard_is_valid_json_on_empty_ledger(tmp_path: Path, monkeypatch):
    """write_scoreboard with no real ledger rows must still produce parseable JSON.

    The canonical ledger is patched empty so the empty-ledger branch is exercised
    deterministically (independent of whatever is on disk).
    """
    import scripts.platformkit.pm_trading.scoreboard as _sb
    monkeypatch.setattr(_sb, "load_rows", lambda *a, **k: [])
    dest = tmp_path / "grade_summary.json"
    write_scoreboard(out_path=dest)
    parsed = json.loads(dest.read_text(encoding="utf-8"))
    assert parsed["n_settled"] == 0
    # Below the floor (0 < MIN_CLV_N) -> INSUFFICIENT_DATA, never a number.
    assert parsed["mean_clv_pct"] == "INSUFFICIENT_DATA"


def test_write_scoreboard_atomic_no_partial_file(tmp_path: Path, monkeypatch):
    """Simulate a mid-write failure: the destination must not contain a partial write."""
    dest = tmp_path / "grade_summary.json"

    # First write a clean file.
    write_scoreboard(out_path=dest)
    original_content = dest.read_text(encoding="utf-8")

    # Patch os.replace to raise, simulating a rename failure after the tmp write.
    import os as _os

    real_replace = _os.replace

    def _bad_replace(src, dst):
        # Remove the tmp file (simulate cleanup path) then raise.
        try:
            _os.unlink(src)
        except OSError:
            pass
        raise OSError("simulated replace failure")

    monkeypatch.setattr(_os, "replace", _bad_replace)

    with pytest.raises(OSError, match="simulated"):
        write_scoreboard(out_path=dest)

    # The original destination must be untouched (atomic guarantee).
    assert dest.read_text(encoding="utf-8") == original_content


def test_write_scoreboard_returns_path(tmp_path: Path):
    dest = tmp_path / "sub" / "grade_summary.json"
    returned = write_scoreboard(out_path=dest)
    assert returned == dest


# ---------------------------------------------------------------------------
# Gate constants sanity
# ---------------------------------------------------------------------------

def test_gate_constants_present_and_sane():
    """Pre-registered gate thresholds must exist; ROI must NOT appear in names."""
    assert GATE_MIN_N == 500
    assert GATE_CLV_LB_PCT == 0.0
    assert GATE_PCT_BEAT_CLOSE == 55.0


def test_no_roi_or_dollar_field_in_scoreboard():
    """grade_summary JSON must not contain any $/ROI top-level key -- honesty contract."""
    rows = [_settled(1.0), _settled(-0.5, outcome="loss")]
    board = build_scoreboard(rows=rows)
    # Check KEYS (field names), not text values (honest_note may discuss concepts).
    all_keys: list = list(board.keys())
    for sp_board in board.get("by_sport", {}).values():
        all_keys.extend(sp_board.keys())
    key_text = " ".join(all_keys).lower()
    for forbidden in ("roi", "dollar", "profit", "revenue", "pnl"):
        assert forbidden not in key_text, (
            "Found forbidden key %r in scoreboard field names: %s" % (forbidden, all_keys)
        )
