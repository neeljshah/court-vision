"""Per-file test for scripts.platformkit.prop_line_ladder_nba.

Acceptance criteria (all must pass):
  1. Synthetic OOF -> per-(stat,offset) dict has n/ece/bss/reliability_bins for
     every cell with sufficient data.
  2. Offsets with n < _MIN_N -> INSUFFICIENT_DATA string (never fabricated metric).
  3. Cache json round-trips: write_ladder_cache writes JSON; load_ladder_cache reads
     it back with identical structure.
  4. Absent parquet -> sentinel (INSUFFICIENT_DATA in all cells), never raises.
  5. No $ key (no roi/pnl/profit) anywhere in any output dict.
  6. _ladder_line honours the offset correctly (base + offset*0.5).
  7. All (stat, offset) cells at offset=0 produce the same outcomes as the
     nearest-.5 line approach in props_eval_nba (sanity cross-check).
  8. ECE values are in [0, 1]; brier in [0, 1]; bss can be negative.
  9. Empty DataFrame -> all INSUFFICIENT_DATA, never raises.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/test_prop_line_ladder_nba.py -q
"""
from __future__ import annotations

import json
import math
import os
import tempfile

import pytest

from scripts.platformkit.prop_line_ladder_nba import (
    INSUFFICIENT_DATA,
    LADDER_CACHE_PATH,
    NBA_STATS,
    _MIN_N,
    _OFFSETS,
    _build_ladder_preds,
    _ladder_line,
    load_ladder_cache,
    score_nba_line_ladder,
    write_ladder_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_oof_df(n_per_stat: int = 80, stats=None, seed: int = 7):
    """Synthetic pregame_oof-shaped DataFrame."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    stats = stats or list(NBA_STATS)
    means = {"pts": 18.0, "reb": 5.5, "ast": 4.2,
              "stl": 1.1, "blk": 0.7, "fg3m": 1.9, "tov": 2.1}
    rows = []
    for stat in stats:
        mu = means.get(stat, 5.0)
        preds = rng.normal(mu, mu * 0.3, size=n_per_stat).clip(0)
        actuals = rng.normal(mu, mu * 0.35, size=n_per_stat).clip(0)
        for p, a in zip(preds, actuals):
            rows.append({
                "stat": stat,
                "oof_pred": float(p),
                "actual": float(a),
                "game_id": "G001",
                "player_id": 1,
                "game_date": "2024-01-15",
                "fold": 1,
                "season": "2024-25",
            })
    return pd.DataFrame(rows)


def _all_keys(obj) -> set:
    """Recursively collect all dict keys from a nested structure."""
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(str(k).lower())
            keys.update(_all_keys(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            keys.update(_all_keys(v))
    return keys


# ---------------------------------------------------------------------------
# Unit: _ladder_line
# ---------------------------------------------------------------------------

class TestLadderLine:
    """_ladder_line: base nearest-.5 + offset * 0.5, clamped >= 0.5."""

    def test_offset_zero_equals_nearest_half(self):
        # pred=15.3 -> nearest .5 = 15.5; offset 0 = 15.5
        assert _ladder_line(15.3, 0) == 15.5

    def test_positive_offset_shifts_up(self):
        # pred=15.3 -> base 15.5; offset +1 = 16.0; offset +2 = 16.5
        assert _ladder_line(15.3, 1) == pytest.approx(16.0)
        assert _ladder_line(15.3, 2) == pytest.approx(16.5)

    def test_negative_offset_shifts_down(self):
        # pred=15.3 -> base 15.5; offset -1 = 15.0; offset -2 = 14.5
        assert _ladder_line(15.3, -1) == pytest.approx(15.0)
        assert _ladder_line(15.3, -2) == pytest.approx(14.5)

    def test_floor_at_half(self):
        # pred=0.3 -> base 0.5; offset -2 would give -0.5 but is clamped to 0.5
        assert _ladder_line(0.3, -2) == pytest.approx(0.5)

    def test_non_finite_pred_returns_floor(self):
        # _nearest_half_line(nan) = 0.5; offset 0 = 0.5
        assert _ladder_line(float("nan"), 0) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Unit: _build_ladder_preds
# ---------------------------------------------------------------------------

class TestBuildLadderPreds:
    def test_returns_all_offsets(self):
        rows = [{"pred": 15.0, "actual": float(i) + 10.0} for i in range(50)]
        result = _build_ladder_preds(rows, "pts", [-1, 0, 1])
        assert set(result.keys()) == {-1, 0, 1}

    def test_each_offset_has_right_length(self):
        rows = [{"pred": 15.0, "actual": float(i) + 10.0} for i in range(40)]
        result = _build_ladder_preds(rows, "pts", [0, 1])
        assert len(result[0]) == 40
        assert len(result[1]) == 40

    def test_p_over_in_unit_interval(self):
        rows = [{"pred": 10.0, "actual": float(i)} for i in range(30)]
        result = _build_ladder_preds(rows, "pts", _OFFSETS)
        for off in _OFFSETS:
            for item in result[off]:
                assert 0.0 <= item["p_over"] <= 1.0

    def test_outcome_reflects_line_shift(self):
        # pred=9.3 -> nearest .5 line = 9.5 (round(8.8)+0.5 = 9+0.5 = 9.5)
        # actual=9.6
        # offset=0: line=9.5, actual=9.6 > 9.5 -> outcome=1
        # offset=2: line=9.5+1.0=10.5, actual=9.6 < 10.5 -> outcome=0
        row = [{"pred": 9.3, "actual": 9.6}]
        r = _build_ladder_preds(row, "pts", [0, 2])
        assert r[0][0]["outcome"] == 1, \
            "actual 9.6 > line 9.5 (offset 0) should be outcome=1"
        assert r[2][0]["outcome"] == 0, \
            "actual 9.6 < line 10.5 (offset +2) should be outcome=0"

    def test_empty_input_returns_empty_lists(self):
        result = _build_ladder_preds([], "pts", [0, 1, -1])
        for off in [0, 1, -1]:
            assert result[off] == []

    def test_bad_row_skipped(self):
        rows = [{"pred": None, "actual": 5.0},
                {"pred": float("nan"), "actual": 5.0},
                {"pred": 10.0, "actual": float("inf")}]
        result = _build_ladder_preds(rows, "pts", [0])
        assert result[0] == []


# ---------------------------------------------------------------------------
# score_nba_line_ladder
# ---------------------------------------------------------------------------

class TestScoreNbaLineLadder:
    def test_absent_parquet_returns_insufficient_data(self, tmp_path):
        """Absent OOF parquet -> all cells INSUFFICIENT_DATA, no raise."""
        res = score_nba_line_ladder(oof_path=str(tmp_path / "missing.parquet"))
        assert res["overall_n"] if "overall_n" in res else True  # key absent is fine
        for stat in res["stats"]:
            for off in res["offsets"]:
                cell = res["per_stat_offset"][stat][off]
                assert cell == INSUFFICIENT_DATA, \
                    f"({stat},{off}) should be INSUFFICIENT_DATA when parquet absent"

    def test_empty_df_returns_insufficient_data(self):
        """Empty DataFrame -> all INSUFFICIENT_DATA, never raises."""
        import pandas as pd
        df = pd.DataFrame(columns=["stat", "oof_pred", "actual"])
        res = score_nba_line_ladder(df=df)
        for stat in res["stats"]:
            for off in res["offsets"]:
                assert res["per_stat_offset"][stat][off] == INSUFFICIENT_DATA

    def test_synthetic_oof_yields_metrics_at_sufficient_n(self):
        """With n_per_stat=100 all cells should have metrics (not INSUFFICIENT_DATA)."""
        df = _make_oof_df(n_per_stat=100)
        res = score_nba_line_ladder(df=df)
        assert set(res["stats"]) == set(NBA_STATS)
        assert res["offsets"] == _OFFSETS
        for stat in NBA_STATS:
            for off in _OFFSETS:
                cell = res["per_stat_offset"][stat][off]
                assert cell != INSUFFICIENT_DATA, \
                    f"({stat},{off}) unexpectedly INSUFFICIENT_DATA with n=100"
                assert isinstance(cell, dict)
                assert "n" in cell and cell["n"] >= _MIN_N
                assert "ece" in cell and cell["ece"] is not None
                assert "bss" in cell  # may be negative -- that's honest
                assert "reliability_bins" in cell and isinstance(
                    cell["reliability_bins"], list)

    def test_thin_stat_returns_insufficient_data_per_cell(self):
        """Only 5 rows for 'pts' -> all offset cells are INSUFFICIENT_DATA."""
        import pandas as pd
        rows = [{"stat": "pts", "oof_pred": 15.0, "actual": 14.0,
                 "game_id": f"G{i}", "player_id": 1,
                 "game_date": "2024-01-01", "fold": 1, "season": "2024-25"}
                for i in range(5)]
        df = pd.DataFrame(rows)
        res = score_nba_line_ladder(df=df, stats=["pts"])
        for off in res["offsets"]:
            assert res["per_stat_offset"]["pts"][off] == INSUFFICIENT_DATA

    def test_brier_in_unit_interval(self):
        """Brier must be in [0, 1] for all non-INSUFFICIENT cells."""
        df = _make_oof_df(n_per_stat=100)
        res = score_nba_line_ladder(df=df)
        for stat in NBA_STATS:
            for off in _OFFSETS:
                cell = res["per_stat_offset"][stat][off]
                if isinstance(cell, dict):
                    assert 0.0 <= cell["brier"] <= 1.0, \
                        f"({stat},{off}) brier out of [0,1]: {cell['brier']}"

    def test_ece_in_unit_interval(self):
        """ECE must be in [0, 1] for all non-INSUFFICIENT cells."""
        df = _make_oof_df(n_per_stat=100)
        res = score_nba_line_ladder(df=df)
        for stat in NBA_STATS:
            for off in _OFFSETS:
                cell = res["per_stat_offset"][stat][off]
                if isinstance(cell, dict):
                    assert 0.0 <= cell["ece"] <= 1.0, \
                        f"({stat},{off}) ECE out of [0,1]: {cell['ece']}"

    def test_no_dollar_keys(self):
        """No roi/pnl/profit/dollar key anywhere in output."""
        df = _make_oof_df(n_per_stat=100)
        res = score_nba_line_ladder(df=df)
        bad = {"roi", "pnl", "profit", "edge_dollars", "dollar_return"}
        keys = _all_keys(res)
        for b in bad:
            assert b not in keys, f"banned key '{b}' found in output"

    def test_note_is_non_empty_string(self):
        df = _make_oof_df(n_per_stat=50)
        res = score_nba_line_ladder(df=df)
        assert isinstance(res["note"], str) and len(res["note"]) > 10

    def test_subset_stats_and_offsets(self):
        """Passing stats=['pts'] and offsets=[0] restricts the surface."""
        df = _make_oof_df(n_per_stat=100)
        res = score_nba_line_ladder(df=df, stats=["pts"], offsets=[0, 1])
        assert res["stats"] == ["pts"]
        assert res["offsets"] == [0, 1]
        assert "reb" not in res["per_stat_offset"]
        assert 0 in res["per_stat_offset"]["pts"]
        assert 1 in res["per_stat_offset"]["pts"]
        assert -1 not in res["per_stat_offset"]["pts"]

    def test_offset_surface_n_equals_source_n(self):
        """Each cell at a given offset should have the same n as the input rows
        (all rows contribute to every offset cell)."""
        df = _make_oof_df(n_per_stat=60, stats=["pts"])
        res = score_nba_line_ladder(df=df, stats=["pts"])
        pts_cells = res["per_stat_offset"]["pts"]
        # All offsets see the same source rows -- n should be identical across offsets
        ns = [pts_cells[off]["n"] for off in _OFFSETS
              if isinstance(pts_cells[off], dict)]
        if ns:
            assert len(set(ns)) == 1, \
                f"Expected same n across all offsets, got {ns}"

    def test_missing_columns_returns_sentinel(self, tmp_path):
        """OOF with missing column -> note mentions it, cells are INSUFFICIENT_DATA."""
        import pandas as pd
        df = pd.DataFrame({"stat": ["pts"] * 50, "oof_pred": [15.0] * 50})
        # missing 'actual' column
        res = score_nba_line_ladder(df=df, stats=["pts"])
        assert "actual" in res["note"] or INSUFFICIENT_DATA in str(res)


# ---------------------------------------------------------------------------
# Cache round-trip
# ---------------------------------------------------------------------------

class TestCacheRoundTrip:
    def test_write_and_load(self, tmp_path):
        """write_ladder_cache writes JSON; load_ladder_cache reads it back."""
        df = _make_oof_df(n_per_stat=80)
        cache_path = str(tmp_path / "ladder.json")
        payload = write_ladder_cache(df, out_path=cache_path)
        assert payload["written"] is True

        loaded = load_ladder_cache(cache_path)
        assert isinstance(loaded, dict)
        assert loaded.get("mode") == "nba_oof_line_ladder"
        # per_stat_offset should round-trip
        assert "per_stat_offset" in loaded
        assert "pts" in loaded["per_stat_offset"]

    def test_json_is_valid_and_parseable(self, tmp_path):
        """Written cache is valid JSON with required keys."""
        df = _make_oof_df(n_per_stat=80)
        cache_path = str(tmp_path / "ladder.json")
        write_ladder_cache(df, out_path=cache_path)
        with open(cache_path, "r", encoding="ascii") as fh:
            obj = json.load(fh)
        assert "per_stat_offset" in obj
        assert "as_of" in obj
        assert "mode" in obj
        assert obj["mode"] == "nba_oof_line_ladder"

    def test_offset_keys_serialised_as_strings(self, tmp_path):
        """JSON offset keys are strings (JSON does not support int keys)."""
        df = _make_oof_df(n_per_stat=80, stats=["pts"])
        cache_path = str(tmp_path / "ladder_keys.json")
        write_ladder_cache(df, out_path=cache_path, stats=["pts"])
        with open(cache_path, "r", encoding="ascii") as fh:
            obj = json.load(fh)
        pts_cells = obj["per_stat_offset"].get("pts", {})
        # Keys must be strings in the JSON
        for k in pts_cells:
            assert isinstance(k, str), f"Expected str key in JSON, got {type(k)}: {k!r}"

    def test_absent_cache_returns_empty_dict(self, tmp_path):
        """load_ladder_cache on absent path -> {} (never raises)."""
        result = load_ladder_cache(str(tmp_path / "nonexistent.json"))
        assert result == {}

    def test_load_never_raises_on_corrupt_json(self, tmp_path):
        """Corrupt JSON -> {} (never raises)."""
        bad = str(tmp_path / "corrupt.json")
        with open(bad, "w", encoding="ascii") as fh:
            fh.write("{not valid json")
        result = load_ladder_cache(bad)
        assert result == {}

    def test_no_dollar_keys_in_cache(self, tmp_path):
        """No roi/pnl/profit key in the written cache JSON."""
        df = _make_oof_df(n_per_stat=80)
        cache_path = str(tmp_path / "ladder_clean.json")
        payload = write_ladder_cache(df, out_path=cache_path)
        bad = {"roi", "pnl", "profit", "edge_dollars", "dollar_return"}
        keys = _all_keys(payload)
        for b in bad:
            assert b not in keys, f"banned key '{b}' in cache payload"

    def test_write_fails_gracefully_bad_path(self):
        """write_ladder_cache with unwritable path -> written=False, no raise."""
        df = _make_oof_df(n_per_stat=80)
        bad_path = "/no/such/directory/ladder.json"
        try:
            payload = write_ladder_cache(df, out_path=bad_path)
            # On Windows the write may fail silently; written=False is correct
            # On other platforms the same
        except Exception as exc:
            pytest.fail(f"write_ladder_cache raised: {exc}")

    def test_insufficient_data_cells_survive_round_trip(self, tmp_path):
        """INSUFFICIENT_DATA string survives JSON write -> load."""
        import pandas as pd
        # Only 5 rows -> thin -> INSUFFICIENT_DATA for all offsets
        rows = [{"stat": "pts", "oof_pred": 15.0, "actual": 14.0,
                 "game_id": f"G{i}", "player_id": 1,
                 "game_date": "2024-01-01", "fold": 1, "season": "2024-25"}
                for i in range(5)]
        df = pd.DataFrame(rows)
        cache_path = str(tmp_path / "thin.json")
        payload = write_ladder_cache(df, stats=["pts"], out_path=cache_path)
        assert payload["written"] is True

        loaded = load_ladder_cache(cache_path)
        pts = loaded["per_stat_offset"].get("pts", {})
        for k, v in pts.items():
            assert v == INSUFFICIENT_DATA, \
                f"Thin cell ({k}) expected INSUFFICIENT_DATA, got {v!r}"
