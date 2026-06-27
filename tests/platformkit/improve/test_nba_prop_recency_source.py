"""tests.platformkit.improve.test_nba_prop_recency_source -- P1-5 acceptance tests.

Acceptance criteria (BACKLOG.md P1-5):
  (a) rows date-sorted ascending; (b) outcome in {0,1}; (c) thin/absent stat -> [];
  (d) no future-row leak; (e) FLAG OFF no sentinel; (f) playoff rows excluded;
  (g) p0 in (0,1); (h) row shape has {ts,p0,outcome,stat,player};
  (i) p0 is decoupled from outcome (non-degenerate calibration base).

Per-file only.  Synthetic parquet in tmp_path.  ASCII; stdlib+numpy+pandas.
"""
from __future__ import annotations

import pathlib
import sys
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pytest

PROJECT_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve.nba_prop_recency_source import (
    load_nba_oof_as_settled,
    available_stats,
    _PLAYOFF_PREFIXES,
    _SIGMA_FLOOR,
    _PRIOR_P0,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {"ts", "p0", "outcome", "stat", "player"}
_FORBIDDEN_KEYS = {"$", "roi", "pnl", "dollar", "edge"}

_REGULAR_PREFIXES = ("0022", "0021", "0020")


def _make_parquet(tmp_path: pathlib.Path,
                  rows: List[Dict[str, Any]]) -> pathlib.Path:
    """Write rows as a parquet and return the path."""
    df = pd.DataFrame(rows)
    path = tmp_path / "pregame_oof.parquet"
    df.to_parquet(path, index=False)
    return path


def _make_row(game_id: str = "0022300001",
              player_id: int = 1,
              stat: str = "pts",
              oof_pred: float = 20.0,
              actual: float = 25.0,
              game_date: str = "2024-01-01",
              fold: int = 1,
              season: str = "2023-24") -> Dict[str, Any]:
    return dict(game_id=game_id, player_id=player_id, stat=stat,
                oof_pred=oof_pred, actual=actual, game_date=game_date,
                fold=fold, season=season)


def _nba_rows(n: int = 40, stat: str = "pts") -> List[Dict[str, Any]]:
    """Generate n regular-season OOF rows with varied dates and predictions."""
    rows = []
    for i in range(n):
        month = (i % 6) + 1
        day = (i % 28) + 1
        date = f"2024-{month:02d}-{day:02d}"
        rows.append(_make_row(
            game_id=f"002230{i:04d}",
            player_id=i + 1,
            stat=stat,
            oof_pred=10.0 + (i % 10),
            actual=12.0 + (i % 8),
            game_date=date,
        ))
    return rows


def _has_forbidden_key(d: Any) -> bool:
    if isinstance(d, dict):
        for k, v in d.items():
            if any(tok in str(k).lower() for tok in _FORBIDDEN_KEYS):
                return True
            if _has_forbidden_key(v):
                return True
    if isinstance(d, list):
        return any(_has_forbidden_key(x) for x in d)
    return False


# ---------------------------------------------------------------------------
# (a) Rows date-sorted ascending
# ---------------------------------------------------------------------------

def test_rows_sorted_ascending(tmp_path):
    """Output rows must be in ascending game_date order."""
    raw = _nba_rows(30, stat="pts")
    # Shuffle the rows so the parquet is not pre-sorted.
    rng = np.random.default_rng(seed=0)
    idxs = rng.permutation(len(raw)).tolist()
    shuffled = [raw[i] for i in idxs]
    path = _make_parquet(tmp_path, shuffled)

    rows = load_nba_oof_as_settled(stat="pts", oof_path=path)
    assert len(rows) >= 2, "Expected rows in output"
    dates = [r["ts"] for r in rows]
    assert dates == sorted(dates), "Rows must be sorted ascending by ts"


# ---------------------------------------------------------------------------
# (b) outcome always in {0, 1}
# ---------------------------------------------------------------------------

def test_outcome_binary(tmp_path):
    """All outcome values must be exactly 0 or 1."""
    # Mix cases: actual > oof_pred, actual == oof_pred, actual < oof_pred.
    rows = [
        _make_row(game_date="2024-01-01", oof_pred=20.0, actual=25.0),  # over
        _make_row(game_date="2024-01-02", oof_pred=20.0, actual=20.0),  # equal -> 0
        _make_row(game_date="2024-01-03", oof_pred=20.0, actual=15.0),  # under
        _make_row(game_date="2024-01-04", oof_pred=0.5, actual=0.0),    # under
    ]
    path = _make_parquet(tmp_path, rows)
    out = load_nba_oof_as_settled(stat="pts", oof_path=path)
    assert len(out) > 0, "Should have output rows"
    for r in out:
        assert r["outcome"] in (0, 1), f"outcome must be 0 or 1, got {r['outcome']}"


# ---------------------------------------------------------------------------
# (c) Thin or absent stat -> [] (no exception)
# ---------------------------------------------------------------------------

def test_absent_stat_returns_empty(tmp_path):
    """Requesting a stat not in the parquet returns [] without raising."""
    path = _make_parquet(tmp_path, _nba_rows(10, stat="pts"))
    result = load_nba_oof_as_settled(stat="blk", oof_path=path)
    assert result == [], "Absent stat must return empty list"


def test_thin_stat_min_rows(tmp_path):
    """min_rows guard returns [] when corpus is smaller than the threshold."""
    path = _make_parquet(tmp_path, _nba_rows(5, stat="ast"))
    # Request more rows than available.
    result = load_nba_oof_as_settled(stat="ast", oof_path=path, min_rows=10)
    assert result == [], "Should return [] when fewer rows than min_rows"


def test_missing_parquet_returns_empty(tmp_path):
    """Missing parquet file returns [] without raising."""
    missing = tmp_path / "does_not_exist.parquet"
    result = load_nba_oof_as_settled(oof_path=missing)
    assert result == [], "Missing file must return []"


# ---------------------------------------------------------------------------
# (d) No future-row leak: rows strictly ordered, p0 not derived from full corpus
# ---------------------------------------------------------------------------

def test_no_future_row_leak_ordering(tmp_path):
    """Walk-forward order: each row's ts must not follow the next row's ts."""
    path = _make_parquet(tmp_path, _nba_rows(40, stat="reb"))
    rows = load_nba_oof_as_settled(stat="reb", oof_path=path)
    assert len(rows) >= 2
    for i in range(len(rows) - 1):
        assert rows[i]["ts"] <= rows[i + 1]["ts"], (
            f"Row {i} ts={rows[i]['ts']} > row {i+1} ts={rows[i+1]['ts']}: "
            "not ascending"
        )


def test_p0_constant_across_all_rows(tmp_path):
    """p0 must be the same constant for all rows (uniform prior, no future leak).

    When no independent market line exists, sigma estimated from the full corpus
    leaks residual spread from future rows into early-row p0 values.  The only
    honest fix is a constant prior.  This test guards that invariant.
    """
    # Use rows with wildly different residuals to provoke any sigma-based variation.
    rows = [
        _make_row(player_id=1, game_date="2024-01-01", oof_pred=20.0, actual=100.0),
        _make_row(player_id=2, game_date="2024-01-02", oof_pred=20.0, actual=0.0),
        _make_row(player_id=3, game_date="2024-01-03", oof_pred=20.0, actual=20.0),
        _make_row(player_id=4, game_date="2024-01-04", oof_pred=20.0, actual=21.0),
        _make_row(player_id=5, game_date="2024-01-05", oof_pred=20.0, actual=19.0),
    ]
    path = _make_parquet(tmp_path, rows)
    out = load_nba_oof_as_settled(stat="pts", oof_path=path)
    assert len(out) > 0
    p0_values = [r["p0"] for r in out]
    # All p0 values must be identical (the constant prior).
    assert len(set(p0_values)) == 1, (
        f"p0 must be constant across all rows; got distinct values: {set(p0_values)}"
    )
    assert p0_values[0] == pytest.approx(_PRIOR_P0, abs=1e-9), (
        f"p0 must equal _PRIOR_P0={_PRIOR_P0}, got {p0_values[0]}"
    )


# ---------------------------------------------------------------------------
# (i) p0 is decoupled from outcome -- core anti-tautology guard
# ---------------------------------------------------------------------------

def test_p0_decoupled_from_outcome(tmp_path):
    """p0 must NOT be a deterministic function of outcome.

    The tautological pattern: p0 = Phi(residual/sigma) where residual =
    actual - oof_pred means p0 > 0.5 iff outcome == 1 exactly.  This test
    asserts that rows with outcome==1 and outcome==0 both receive the SAME
    p0 value (the uniform prior 0.5), demonstrating non-degeneracy.
    """
    rows = [
        # outcome = 1 (actual > oof_pred)
        _make_row(player_id=1, game_date="2024-01-01", oof_pred=10.0, actual=20.0),
        _make_row(player_id=2, game_date="2024-01-02", oof_pred=10.0, actual=15.0),
        # outcome = 0 (actual <= oof_pred)
        _make_row(player_id=3, game_date="2024-01-03", oof_pred=10.0, actual=5.0),
        _make_row(player_id=4, game_date="2024-01-04", oof_pred=10.0, actual=10.0),
    ]
    path = _make_parquet(tmp_path, rows)
    out = load_nba_oof_as_settled(stat="pts", oof_path=path)
    assert len(out) == 4

    by_player = {r["player"]: r for r in out}
    # Rows with outcome=1 must have the same p0 as rows with outcome=0.
    p0_over  = {by_player["1"]["p0"], by_player["2"]["p0"]}
    p0_under = {by_player["3"]["p0"], by_player["4"]["p0"]}
    assert p0_over == p0_under, (
        f"p0 differs between over/under groups: over={p0_over} under={p0_under}; "
        "this indicates tautological calibration (p0 is a function of outcome)"
    )
    # Confirm both groups are at the constant prior.
    for r in out:
        assert r["p0"] == pytest.approx(_PRIOR_P0, abs=1e-9), (
            f"p0={r['p0']} != _PRIOR_P0={_PRIOR_P0}"
        )


def test_p0_not_gt_half_for_overs_only(tmp_path):
    """When ALL rows are overs, p0 must still be 0.5 (not > 0.5).

    The tautological implementation would set p0 > 0.5 for every over row.
    The correct implementation must produce p0 = 0.5 regardless of outcome.
    """
    rows = [
        _make_row(player_id=i, game_date=f"2024-01-{i:02d}",
                  oof_pred=10.0, actual=20.0)
        for i in range(1, 11)
    ]
    path = _make_parquet(tmp_path, rows)
    out = load_nba_oof_as_settled(stat="pts", oof_path=path)
    assert len(out) == 10
    for r in out:
        assert r["outcome"] == 1
        assert r["p0"] == pytest.approx(_PRIOR_P0, abs=1e-9), (
            f"p0={r['p0']} should be {_PRIOR_P0} even for all-over corpus"
        )


def test_p0_not_lt_half_for_unders_only(tmp_path):
    """When ALL rows are unders, p0 must still be 0.5 (not < 0.5).

    The tautological implementation would set p0 < 0.5 for every under row.
    """
    rows = [
        _make_row(player_id=i, game_date=f"2024-01-{i:02d}",
                  oof_pred=20.0, actual=5.0)
        for i in range(1, 11)
    ]
    path = _make_parquet(tmp_path, rows)
    out = load_nba_oof_as_settled(stat="pts", oof_path=path)
    assert len(out) == 10
    for r in out:
        assert r["outcome"] == 0
        assert r["p0"] == pytest.approx(_PRIOR_P0, abs=1e-9), (
            f"p0={r['p0']} should be {_PRIOR_P0} even for all-under corpus"
        )


# ---------------------------------------------------------------------------
# (e) FLAG OFF: no sentinel, no registry write
# ---------------------------------------------------------------------------

def test_flag_off_no_sentinel_created(tmp_path):
    """load_nba_oof_as_settled must NOT create a PIPELINE_ENABLED sentinel."""
    sentinel = tmp_path / "data" / "cache" / "improve" / "PIPELINE_ENABLED"
    path = _make_parquet(tmp_path, _nba_rows(10, stat="pts"))
    load_nba_oof_as_settled(stat="pts", oof_path=path)
    assert not sentinel.exists(), "Must not create PIPELINE_ENABLED sentinel"


def test_no_forbidden_keys_in_output(tmp_path):
    """No $ / roi / pnl / edge key in any output row."""
    path = _make_parquet(tmp_path, _nba_rows(10, stat="pts"))
    rows = load_nba_oof_as_settled(stat="pts", oof_path=path)
    for r in rows:
        assert not _has_forbidden_key(r), f"Forbidden key found in row: {r}"


# ---------------------------------------------------------------------------
# (f) Playoff rows excluded
# ---------------------------------------------------------------------------

def test_playoff_rows_excluded(tmp_path):
    """Rows with playoff game_id prefix must not appear in output."""
    regular = _nba_rows(20, stat="pts")
    playoff = [
        _make_row(game_id="0041400101", player_id=9001, game_date="2024-05-01",
                  stat="pts", oof_pred=20.0, actual=28.0),
        _make_row(game_id="0042400201", player_id=9002, game_date="2024-06-01",
                  stat="pts", oof_pred=22.0, actual=18.0),
        _make_row(game_id="0043400301", player_id=9003, game_date="2024-06-15",
                  stat="pts", oof_pred=25.0, actual=30.0),
    ]
    path = _make_parquet(tmp_path, regular + playoff)
    rows = load_nba_oof_as_settled(stat="pts", oof_path=path)
    reg_dir = tmp_path / "reg"
    reg_dir.mkdir(parents=True, exist_ok=True)
    rows_regular = load_nba_oof_as_settled(
        stat="pts", oof_path=_make_parquet(reg_dir, regular))
    assert len(rows) == len(rows_regular), (
        f"Playoff rows leaked in: full={len(rows)}, regular-only={len(rows_regular)}"
    )


# ---------------------------------------------------------------------------
# (g) p0 always in (0, 1) open interval
# ---------------------------------------------------------------------------

def test_p0_in_open_interval(tmp_path):
    """p0 must be strictly between 0 and 1 (no hard zeros or ones)."""
    # Include extreme cases: very large positive and negative residuals.
    extreme_rows = [
        _make_row(game_date="2024-01-01", oof_pred=0.0, actual=100.0),  # big positive
        _make_row(game_date="2024-01-02", oof_pred=100.0, actual=0.0),  # big negative
        _make_row(game_date="2024-01-03", oof_pred=20.0, actual=20.0),  # zero residual
    ] + _nba_rows(30, stat="pts")
    path = _make_parquet(tmp_path, extreme_rows)
    rows = load_nba_oof_as_settled(stat="pts", oof_path=path)
    assert len(rows) > 0
    for r in rows:
        assert 0.0 < r["p0"] < 1.0, f"p0={r['p0']} out of open interval (0,1)"


# ---------------------------------------------------------------------------
# (h) Row shape: required keys present
# ---------------------------------------------------------------------------

def test_row_shape(tmp_path):
    """Every output row must contain all required keys: ts, p0, outcome, stat, player."""
    path = _make_parquet(tmp_path, _nba_rows(15, stat="ast"))
    rows = load_nba_oof_as_settled(stat="ast", oof_path=path)
    assert len(rows) > 0, "Should produce rows for non-thin stat"
    for r in rows:
        missing = _REQUIRED_KEYS - set(r.keys())
        assert not missing, f"Missing keys {missing} in row: {r}"


# ---------------------------------------------------------------------------
# available_stats
# ---------------------------------------------------------------------------

def test_available_stats(tmp_path):
    """available_stats returns sorted list of stat names in the parquet."""
    data = _nba_rows(5, stat="pts") + _nba_rows(5, stat="ast")
    path = _make_parquet(tmp_path, data)
    stats = available_stats(oof_path=path)
    assert "pts" in stats
    assert "ast" in stats
    assert stats == sorted(stats), "available_stats must be sorted"


def test_available_stats_missing_file(tmp_path):
    """available_stats returns [] when file is missing."""
    result = available_stats(oof_path=tmp_path / "nope.parquet")
    assert result == []


# ---------------------------------------------------------------------------
# Integration: verify over/under outcome semantics (decoupled from p0)
# ---------------------------------------------------------------------------

def test_over_under_semantics(tmp_path):
    """Rows where actual > oof_pred get outcome=1; equal or below get outcome=0.

    Note: p0 is constant at _PRIOR_P0 regardless of over/under status.
    The over/under result is captured ONLY in the outcome field, not in p0.
    """
    # Use high player_ids to avoid dedup collision with _nba_rows (which uses 1..35).
    spec_rows = [
        _make_row(player_id=9001, game_date="2027-01-01", oof_pred=20.0, actual=25.0),
        _make_row(player_id=9002, game_date="2027-01-02", oof_pred=20.0, actual=19.9),
        _make_row(player_id=9003, game_date="2027-01-03", oof_pred=20.0, actual=20.0),
        _make_row(player_id=9004, game_date="2027-01-04", oof_pred=5.0,  actual=8.0),
        _make_row(player_id=9005, game_date="2027-01-05", oof_pred=5.0,  actual=3.0),
    ]
    rows = _nba_rows(35, stat="pts") + spec_rows
    path = _make_parquet(tmp_path, rows)
    out = load_nba_oof_as_settled(stat="pts", oof_path=path)
    # Index by player field (str of player_id) to avoid ts-collision ambiguity.
    by_player = {r["player"]: r for r in out}
    assert by_player["9001"]["outcome"] == 1, "25 > 20 -> over"
    assert by_player["9002"]["outcome"] == 0, "19.9 < 20 -> under"
    assert by_player["9003"]["outcome"] == 0, "20 == 20 -> not strictly over"
    assert by_player["9004"]["outcome"] == 1, "8 > 5 -> over"
    assert by_player["9005"]["outcome"] == 0, "3 < 5 -> under"
    # p0 must be constant regardless of outcome.
    for pid in ["9001", "9002", "9003", "9004", "9005"]:
        assert by_player[pid]["p0"] == pytest.approx(_PRIOR_P0, abs=1e-9), (
            f"player {pid}: p0={by_player[pid]['p0']} != _PRIOR_P0={_PRIOR_P0}"
        )
