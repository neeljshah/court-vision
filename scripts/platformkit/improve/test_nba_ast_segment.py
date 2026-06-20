"""Per-file test for scripts.platformkit.improve.nba_ast_segment.

Acceptance criteria (from BACKLOG.md P1-4-nba-ast-segment):
  - strong segment KEPT on synthetic OOF (p10_r >= STRONG_R_FLOOR)
  - null segment DROPPED on synthetic OOF (p10_r < STRONG_R_FLOOR)
  - playoff-flagged rows (0042xxxx game_id) EXCLUDED
  - full-surface validation runs across all stat pairs without error
  - thin segment (<MIN_BOOTSTRAP_N rows) -> INSUFFICIENT_DATA
  - no $ / roi / pnl / profit key in any output dict
  - flag = 'OFF' always
  - note = 'calibration, not edge'

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/improve/test_nba_ast_segment.py -q
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any, List

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.improve.nba_ast_segment import (
    MIN_BOOTSTRAP_N,
    _PLAYOFF_PREFIXES,
    _STRONG_R_FLOOR,
    load_oof_rows,
    run_ast_segment_filter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)


def _all_keys(obj: Any) -> List[str]:
    """Recursively collect all dict keys from a nested structure."""
    keys: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(str(k))
            keys.extend(_all_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_all_keys(item))
    return keys


def _assert_no_banned_keys(obj: Any, context: str = "") -> None:
    for k in _all_keys(obj):
        assert not _BANNED_KEY_RE.search(k), (
            "Banned key '%s' found in output%s" % (k, (" (%s)" % context) if context else "")
        )


def _make_oof_parquet(tmp_path: Path,
                      n_strong: int = 200,
                      n_null: int = 100,
                      n_playoff: int = 0,
                      stats: tuple = ("ast", "pts"),
                      seed: int = 0) -> Path:
    """Build a synthetic pregame_oof.parquet with known strong/null structure.

    Strong rows: oof_pred is a reliable predictor of actual (high or low range,
    strong linear correlation).
    Null rows: oof_pred in the middle range, near-zero correlation with actual.
    Playoff rows: game_id starting with '0042'.
    """
    rng = np.random.default_rng(seed)
    rows = []

    for stat in stats:
        # Strong segment: low range (oof_pred 0-1) with tight correlation
        for i in range(n_strong // 2):
            pred = float(rng.uniform(0.0, 1.0))
            actual = pred + float(rng.normal(0, 0.05))  # tight noise
            rows.append({
                "game_id": "002230%04d" % i,
                "player_id": i + 1000,
                "stat": stat,
                "oof_pred": round(pred, 4),
                "actual": round(max(0.0, actual), 4),
                "game_date": "2024-01-01",
                "fold": 1,
                "season": "2023-24",
            })
        # Strong segment: high range (oof_pred 5-9) with tight correlation
        for i in range(n_strong // 2):
            pred = float(rng.uniform(5.0, 9.0))
            actual = pred + float(rng.normal(0, 0.15))
            rows.append({
                "game_id": "002240%04d" % i,
                "player_id": i + 2000,
                "stat": stat,
                "oof_pred": round(pred, 4),
                "actual": round(max(0.0, actual), 4),
                "game_date": "2024-02-01",
                "fold": 2,
                "season": "2023-24",
            })
        # Null segment: middle range (oof_pred 2-4) with no correlation
        for i in range(n_null):
            pred = float(rng.uniform(2.0, 4.0))
            actual = float(rng.uniform(0.0, 8.0))  # random, no correlation
            rows.append({
                "game_id": "002250%04d" % i,
                "player_id": i + 3000,
                "stat": stat,
                "oof_pred": round(pred, 4),
                "actual": round(max(0.0, actual), 4),
                "game_date": "2024-03-01",
                "fold": 3,
                "season": "2023-24",
            })
        # Playoff rows (should be excluded)
        for i in range(n_playoff):
            rows.append({
                "game_id": "00421%05d" % i,  # playoff prefix
                "player_id": i + 9000,
                "stat": stat,
                "oof_pred": round(float(rng.uniform(1.0, 5.0)), 4),
                "actual": round(float(rng.uniform(0.0, 9.0)), 4),
                "game_date": "2024-05-01",
                "fold": 4,
                "season": "2023-24 Playoffs",
            })

    df = pd.DataFrame(rows)
    parquet_path = tmp_path / "pregame_oof.parquet"
    df.to_parquet(parquet_path, index=False)
    return parquet_path


# ---------------------------------------------------------------------------
# Tests: playoff exclusion
# ---------------------------------------------------------------------------

class TestPlayoffExclusion:
    """Playoff-flagged game_id rows must be excluded from analysis."""

    def test_playoff_rows_excluded_from_load(self, tmp_path: Path) -> None:
        parquet_path = _make_oof_parquet(
            tmp_path, n_strong=60, n_null=40, n_playoff=20, stats=("ast",)
        )
        df = load_oof_rows(oof_path=parquet_path)
        # No playoff prefixes in returned df
        for pfx in _PLAYOFF_PREFIXES:
            n_pf = (df["game_id"].astype(str).str.startswith(pfx)).sum()
            assert n_pf == 0, "Playoff prefix %s leaked into OOF rows: %d rows" % (pfx, n_pf)

    def test_playoff_rows_do_not_inflate_n(self, tmp_path: Path) -> None:
        n_strong, n_null, n_playoff = 60, 40, 20
        parquet_path = _make_oof_parquet(
            tmp_path, n_strong=n_strong, n_null=n_null, n_playoff=n_playoff, stats=("ast",)
        )
        df = load_oof_rows(oof_path=parquet_path)
        # Each stat produces n_strong + n_null non-playoff rows
        expected = n_strong + n_null
        assert len(df) == expected, (
            "Expected %d non-playoff rows, got %d" % (expected, len(df))
        )

    def test_no_playoff_data_is_ok(self, tmp_path: Path) -> None:
        parquet_path = _make_oof_parquet(
            tmp_path, n_strong=60, n_null=40, n_playoff=0, stats=("ast",)
        )
        df = load_oof_rows(oof_path=parquet_path)
        assert not df.empty


# ---------------------------------------------------------------------------
# Tests: strong segment kept, null segment dropped
# ---------------------------------------------------------------------------

class TestSegmentFilterDecision:
    """Strong segment is KEPT; null segment is DROPPED on synthetic OOF."""

    def test_strong_segment_kept(self, tmp_path: Path) -> None:
        parquet_path = _make_oof_parquet(
            tmp_path, n_strong=300, n_null=150, stats=("ast",), seed=99
        )
        result = run_ast_segment_filter(oof_path=parquet_path, stats=["ast"], n_boot=200)
        assert result["status"] == "ok", "Expected ok, got: %s" % result
        ast_v = result["ast_verdict"]
        assert ast_v["status"] == "ok"
        strong = ast_v["strong_segment"]
        assert strong["kept"] is True, (
            "Strong segment not kept: p10_r=%s, threshold=%s" % (
                strong["p10_r"], _STRONG_R_FLOOR)
        )

    def test_null_segment_dropped(self, tmp_path: Path) -> None:
        parquet_path = _make_oof_parquet(
            tmp_path, n_strong=300, n_null=150, stats=("ast",), seed=99
        )
        result = run_ast_segment_filter(oof_path=parquet_path, stats=["ast"], n_boot=200)
        assert result["status"] == "ok"
        ast_v = result["ast_verdict"]
        assert ast_v["status"] == "ok"
        null_seg = ast_v["null_segment"]
        assert null_seg["dropped"] is True, (
            "Null segment not dropped: p10_r=%s, threshold=%s" % (
                null_seg["p10_r"], _STRONG_R_FLOOR)
        )

    def test_verdict_strong_kept_null_dropped(self, tmp_path: Path) -> None:
        parquet_path = _make_oof_parquet(
            tmp_path, n_strong=300, n_null=150, stats=("ast",), seed=99
        )
        result = run_ast_segment_filter(oof_path=parquet_path, stats=["ast"], n_boot=200)
        ast_v = result["ast_verdict"]
        assert ast_v.get("verdict") == "strong_kept_null_dropped"


# ---------------------------------------------------------------------------
# Tests: thin segment -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

class TestInsufficientData:
    """Thin segment (<MIN_BOOTSTRAP_N rows) produces INSUFFICIENT_DATA verdict."""

    def test_too_few_rows_is_insufficient(self, tmp_path: Path) -> None:
        parquet_path = _make_oof_parquet(
            tmp_path, n_strong=MIN_BOOTSTRAP_N - 2, n_null=MIN_BOOTSTRAP_N - 2,
            stats=("ast",), seed=7
        )
        result = run_ast_segment_filter(oof_path=parquet_path, stats=["ast"], n_boot=50)
        ast_v = result["ast_verdict"]
        assert ast_v["status"] == "INSUFFICIENT_DATA", (
            "Expected INSUFFICIENT_DATA for thin segment, got: %s" % ast_v
        )

    def test_missing_parquet_is_insufficient(self, tmp_path: Path) -> None:
        absent = tmp_path / "missing.parquet"
        result = run_ast_segment_filter(oof_path=absent)
        assert result["status"] == "INSUFFICIENT_DATA"

    def test_insufficient_always_flag_off(self, tmp_path: Path) -> None:
        absent = tmp_path / "missing.parquet"
        result = run_ast_segment_filter(oof_path=absent)
        assert result.get("flag") == "OFF"


# ---------------------------------------------------------------------------
# Tests: full-surface validation
# ---------------------------------------------------------------------------

class TestFullSurface:
    """Full stat-surface validation runs across multiple stat pairs."""

    def test_full_surface_runs_all_stats(self, tmp_path: Path) -> None:
        all_stats = ("ast", "pts", "reb", "blk", "fg3m", "stl", "tov")
        parquet_path = _make_oof_parquet(
            tmp_path, n_strong=200, n_null=100, stats=all_stats, seed=3
        )
        result = run_ast_segment_filter(oof_path=parquet_path, n_boot=100)
        assert result["status"] == "ok"
        per_stat = result["per_stat"]
        for s in all_stats:
            assert s in per_stat, "Missing stat %s in per_stat" % s
            assert "status" in per_stat[s]
        # ast_verdict mirrors per_stat["ast"]
        assert result["ast_verdict"] == per_stat["ast"]


# ---------------------------------------------------------------------------
# Tests: no banned keys, flag OFF, honest note
# ---------------------------------------------------------------------------

class TestHonestGuards:
    """No $ / roi / pnl / profit key; flag OFF; note = calibration not edge."""

    def test_no_banned_keys_and_honest_fields(self, tmp_path: Path) -> None:
        parquet_path = _make_oof_parquet(
            tmp_path, n_strong=200, n_null=100, stats=("ast", "pts"), seed=0
        )
        result = run_ast_segment_filter(oof_path=parquet_path, n_boot=100)
        _assert_no_banned_keys(result, "ok result")
        assert result.get("flag") == "OFF"
        assert result.get("note") == "calibration, not edge"
        assert result.get("vs_close") == "UNPROVEN"

    def test_no_banned_keys_insufficient(self, tmp_path: Path) -> None:
        absent = tmp_path / "missing.parquet"
        result = run_ast_segment_filter(oof_path=absent)
        _assert_no_banned_keys(result, "insufficient result")
        assert result.get("flag") == "OFF"
