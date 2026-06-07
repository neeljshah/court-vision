"""test_w040_matchup_tilt.py — CV_INGAME_MATCHUP_TILT enricher unit tests.

Asserted here:
  1. Flag semantics: _flag_on() is False by default; True for truthy values.
  2. Byte-identical guarantee: apply_matchup_tilt returns rows UNCHANGED
     when flag is OFF.
  3. load_scheme_map: correct normalisation of dominant_tag; empty dict when
     file is missing.
  4. load_vs_scheme_atlas: n_games < MIN_N entries are excluded; valid entries
     produce correct {scheme: {stat: float}} structure.
  5. compute_tilt: returns capped float; 0.0 when player/scheme absent.
  6. apply_matchup_tilt (flag ON): projected_final is mutated toward scheme
     tilt direction for covered players; current stat is a floor.
  7. apply_matchup_tilt: uncovered players (not in atlas) are untouched.
  8. apply_matchup_tilt: tilt is applied to REMAINING delta only (not current).
  9. apply_matchup_tilt: abs tilt never exceeds MAX_TILT.
 10. apply_matchup_tilt: non-TILT_STATS rows (stl, blk, tov) are untouched.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import patch

import pytest

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("NBA_OFFLINE", "1")

from src.ingame.snapshot_matchup_tilt_enricher import (  # noqa: E402
    _FLAG_ENV,
    _MAX_TILT,
    _MIN_N,
    _flag_on,
    apply_matchup_tilt,
    compute_tilt,
    load_scheme_map,
    load_vs_scheme_atlas,
    TILT_STATS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rows(stats=None, current=5.0, projected=15.0, pid=1001, team="BOS"):
    """Build synthetic projection rows for a player."""
    if stats is None:
        stats = list(TILT_STATS) + ["stl", "blk", "tov"]
    return [
        {
            "player_id": pid,
            "name": f"pid_{pid}",
            "team": team,
            "stat": s,
            "current": current,
            "projected_final": projected,
        }
        for s in stats
    ]


def _snap(home="BOS", away="OKC"):
    return {
        "game_id": "0022400001",
        "home_team": home,
        "away_team": away,
        "home_score": 50,
        "away_score": 45,
        "period": 3,
        "clock": "12:00",
        "players": [
            {"player_id": 1001, "name": "Player A", "team": home},
            {"player_id": 1002, "name": "Player B", "team": away},
        ],
    }


def _scheme_map(home="BOS", away="OKC"):
    return {
        home: "drop_coverage",
        away: "switch_heavy",
    }


def _atlas_with_bias():
    """Player 1001 scores better vs drop_coverage (+20%) vs baseline."""
    return {
        1001: {
            "drop_coverage": {"pts": 24.0, "reb": 6.0, "ast": 5.0, "fg3m": 3.0},
            "switch_heavy": {"pts": 20.0, "reb": 5.0, "ast": 5.0, "fg3m": 2.5},
            "help_defense": {"pts": 20.0, "reb": 5.0, "ast": 5.0, "fg3m": 2.5},
        },
        # avg = (24+20+20)/3 = 21.33; drop_coverage tilt = 24/21.33 - 1 = +0.125
    }


def _atlas_negative():
    """Player 1001 scores worse vs switch_heavy (negative tilt)."""
    return {
        1001: {
            "drop_coverage": {"pts": 24.0, "reb": 6.0, "ast": 5.0, "fg3m": 3.0},
            "switch_heavy": {"pts": 17.0, "reb": 4.0, "ast": 4.0, "fg3m": 2.0},
            "help_defense": {"pts": 22.0, "reb": 5.5, "ast": 5.0, "fg3m": 2.5},
        },
    }


# ---------------------------------------------------------------------------
# Fixture: reset caches and env flag around each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_state():
    """Clear module-level caches and flag env between tests."""
    import src.ingame.snapshot_matchup_tilt_enricher as m
    saved_flag = os.environ.get(_FLAG_ENV)
    saved_scheme = m._scheme_map_cache
    saved_atlas = m._atlas_cache

    m._scheme_map_cache = None
    m._atlas_cache = None
    os.environ.pop(_FLAG_ENV, None)

    yield

    m._scheme_map_cache = None
    m._atlas_cache = None
    if saved_flag is None:
        os.environ.pop(_FLAG_ENV, None)
    else:
        os.environ[_FLAG_ENV] = saved_flag


# ---------------------------------------------------------------------------
# 1. Flag semantics
# ---------------------------------------------------------------------------

class TestFlagSemantics:
    def test_default_off(self):
        assert _flag_on() is False

    def test_falsy_values_off(self):
        for v in ("0", "", "false", "no", "off"):
            os.environ[_FLAG_ENV] = v
            assert _flag_on() is False, f"expected OFF for {v!r}"

    def test_truthy_values_on(self):
        for v in ("1", "true", "yes", "on", "TRUE"):
            os.environ[_FLAG_ENV] = v
            assert _flag_on() is True, f"expected ON for {v!r}"

    def test_flag_name(self):
        assert _FLAG_ENV == "CV_INGAME_MATCHUP_TILT"


# ---------------------------------------------------------------------------
# 2. Byte-identical when flag OFF
# ---------------------------------------------------------------------------

class TestByteIdentical:
    def test_flag_off_no_mutation(self):
        rows = _rows()
        original = [dict(r) for r in rows]
        snap = _snap()
        result = apply_matchup_tilt(snap, rows,
                                    scheme_map=_scheme_map(),
                                    atlas=_atlas_with_bias())
        assert result is rows  # same object
        for orig, res in zip(original, result):
            assert orig["projected_final"] == res["projected_final"], (
                f"stat {orig['stat']}: projected_final changed with flag OFF"
            )

    def test_flag_off_no_extra_keys(self):
        rows = _rows()
        original_keys = [set(r.keys()) for r in rows]
        snap = _snap()
        apply_matchup_tilt(snap, rows,
                           scheme_map=_scheme_map(),
                           atlas=_atlas_with_bias())
        for orig_keys, row in zip(original_keys, rows):
            assert set(row.keys()) == orig_keys


# ---------------------------------------------------------------------------
# 3. load_scheme_map
# ---------------------------------------------------------------------------

class TestLoadSchemeMap:
    def test_missing_file_returns_empty(self, tmp_path):
        from src.ingame.snapshot_matchup_tilt_enricher import load_scheme_map as lsm
        result = lsm(path=tmp_path / "nonexistent.parquet")
        assert result == {}

    def test_correct_normalisation(self):
        from src.ingame.snapshot_matchup_tilt_enricher import _norm_tag
        assert _norm_tag("DROP COVERAGE") == "drop_coverage"
        assert _norm_tag("PAINT-FIRST DEFENSE") == "paint_first_defense"
        assert _norm_tag("SWITCH HEAVY") == "switch_heavy"
        assert _norm_tag("HELP DEFENSE") == "help_defense"
        assert _norm_tag("PACE CONTROL") == "pace_control"
        assert _norm_tag("BALANCED") == "balanced"


# ---------------------------------------------------------------------------
# 4. load_vs_scheme_atlas
# ---------------------------------------------------------------------------

class TestLoadVsSchemeAtlas:
    def test_missing_file_returns_empty(self, tmp_path):
        from src.ingame.snapshot_matchup_tilt_enricher import load_vs_scheme_atlas as lva
        result = lva(path=tmp_path / "nonexistent.parquet")
        assert result == {}

    def test_min_n_gate_excludes_small_samples(self):
        """Directly test that entries with n_games < _MIN_N are excluded."""
        import json
        import pandas as pd
        import tempfile
        from src.ingame.snapshot_matchup_tilt_enricher import load_vs_scheme_atlas as lva

        # Build a minimal parquet with one low-n and one high-n scheme
        by_scheme = {
            "drop_coverage": {
                "tag": "DROP COVERAGE", "n_games": _MIN_N + 5,
                "pts_pg": 20.0, "reb_pg": 5.0, "ast_pg": 4.0, "fg3m_pg": 2.0,
            },
            "switch_heavy": {
                "tag": "SWITCH HEAVY", "n_games": _MIN_N - 1,  # below threshold
                "pts_pg": 18.0, "reb_pg": 4.0, "ast_pg": 3.5, "fg3m_pg": 1.5,
            },
        }
        df = pd.DataFrame([{"player_id": 42, "by_scheme": json.dumps(by_scheme)}])
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            tmp_p = f.name
        try:
            df.to_parquet(tmp_p)
            result = lva(path=Path(tmp_p))
            assert 42 in result
            assert "drop_coverage" in result[42]
            assert "switch_heavy" not in result[42], (
                "switch_heavy has n_games < _MIN_N and must be excluded"
            )
        finally:
            os.unlink(tmp_p)


# ---------------------------------------------------------------------------
# 5. compute_tilt
# ---------------------------------------------------------------------------

class TestComputeTilt:
    def test_returns_zero_for_missing_player(self):
        atlas = _atlas_with_bias()
        t = compute_tilt(9999, "drop_coverage", "pts", atlas)
        assert t == 0.0

    def test_returns_zero_for_missing_scheme(self):
        atlas = _atlas_with_bias()
        t = compute_tilt(1001, "zone_press", "pts", atlas)
        assert t == 0.0

    def test_positive_tilt_for_favourable_scheme(self):
        atlas = _atlas_with_bias()
        # drop_coverage = 24.0; avg = (24+20+20)/3 = 21.33 → tilt ≈ +0.125
        t = compute_tilt(1001, "drop_coverage", "pts", atlas)
        assert t > 0.0, f"Expected positive tilt, got {t}"

    def test_negative_tilt_for_unfavourable_scheme(self):
        atlas = _atlas_negative()
        # switch_heavy = 17.0; avg = (24+17+22)/3 = 21.0 → tilt ≈ -0.190
        t = compute_tilt(1001, "switch_heavy", "pts", atlas)
        assert t < 0.0, f"Expected negative tilt, got {t}"

    def test_tilt_capped_at_max(self):
        """Extreme values in atlas must be capped at ±_MAX_TILT."""
        atlas = {
            1001: {
                "drop_coverage": {"pts": 100.0, "reb": 5.0, "ast": 4.0, "fg3m": 2.0},
                "switch_heavy": {"pts": 1.0, "reb": 5.0, "ast": 4.0, "fg3m": 2.0},
            }
        }
        t_pos = compute_tilt(1001, "drop_coverage", "pts", atlas)
        t_neg = compute_tilt(1001, "switch_heavy", "pts", atlas)
        assert abs(t_pos) <= _MAX_TILT, f"Expected |tilt| <= {_MAX_TILT}, got {t_pos}"
        assert abs(t_neg) <= _MAX_TILT, f"Expected |tilt| <= {_MAX_TILT}, got {t_neg}"

    def test_tilt_zero_when_avg_zero(self):
        atlas = {1001: {"drop_coverage": {"pts": 0.0}}}
        t = compute_tilt(1001, "drop_coverage", "pts", atlas)
        assert t == 0.0


# ---------------------------------------------------------------------------
# 6. apply_matchup_tilt (flag ON): mutations
# ---------------------------------------------------------------------------

class TestApplyMatchupTiltEnabled:
    def _enable(self):
        os.environ[_FLAG_ENV] = "1"

    def test_positive_tilt_increases_projected_final(self):
        self._enable()
        snap = _snap(home="BOS", away="OKC")
        # BOS player (pid=1001) faces OKC (switch_heavy scheme)
        # Make pid=1001 score better vs switch_heavy → positive tilt
        atlas = {
            1001: {
                "switch_heavy": {"pts": 28.0, "reb": 7.0, "ast": 6.0, "fg3m": 3.5},
                "drop_coverage": {"pts": 20.0, "reb": 5.0, "ast": 5.0, "fg3m": 2.5},
                "balanced": {"pts": 20.0, "reb": 5.0, "ast": 5.0, "fg3m": 2.5},
            }
        }
        scheme_map = {"BOS": "drop_coverage", "OKC": "switch_heavy"}
        rows = _rows(stats=["pts"], current=8.0, projected=20.0, pid=1001, team="BOS")
        result = apply_matchup_tilt(snap, rows,
                                    scheme_map=scheme_map, atlas=atlas)
        pts_row = next(r for r in result if r["stat"] == "pts")
        assert pts_row["projected_final"] > 20.0, (
            f"Positive tilt should increase projected_final, got {pts_row['projected_final']}"
        )

    def test_negative_tilt_decreases_projected_final(self):
        self._enable()
        snap = _snap(home="BOS", away="OKC")
        atlas = {
            1001: {
                "switch_heavy": {"pts": 14.0, "reb": 3.0, "ast": 3.0, "fg3m": 1.0},
                "drop_coverage": {"pts": 24.0, "reb": 6.0, "ast": 6.0, "fg3m": 3.0},
                "balanced": {"pts": 22.0, "reb": 6.0, "ast": 6.0, "fg3m": 3.0},
            }
        }
        scheme_map = {"BOS": "drop_coverage", "OKC": "switch_heavy"}
        rows = _rows(stats=["pts"], current=8.0, projected=20.0, pid=1001, team="BOS")
        result = apply_matchup_tilt(snap, rows,
                                    scheme_map=scheme_map, atlas=atlas)
        pts_row = next(r for r in result if r["stat"] == "pts")
        assert pts_row["projected_final"] < 20.0, (
            f"Negative tilt should decrease projected_final, got {pts_row['projected_final']}"
        )

    def test_current_stat_is_floor(self):
        """Even with extreme negative tilt, projected_final >= current."""
        self._enable()
        snap = _snap(home="BOS", away="OKC")
        atlas = {
            1001: {
                "switch_heavy": {"pts": 0.5, "reb": 0.5, "ast": 0.5, "fg3m": 0.5},
                "drop_coverage": {"pts": 100.0, "reb": 100.0, "ast": 100.0, "fg3m": 100.0},
            }
        }
        scheme_map = {"BOS": "drop_coverage", "OKC": "switch_heavy"}
        rows = _rows(stats=["pts"], current=12.0, projected=14.0, pid=1001, team="BOS")
        result = apply_matchup_tilt(snap, rows,
                                    scheme_map=scheme_map, atlas=atlas)
        pts_row = next(r for r in result if r["stat"] == "pts")
        assert pts_row["projected_final"] >= 12.0, (
            f"projected_final must be >= current ({12.0}), got {pts_row['projected_final']}"
        )

    def test_uncovered_player_untouched(self):
        """Player not in atlas must have projected_final unchanged."""
        self._enable()
        snap = _snap(home="BOS", away="OKC")
        atlas = {}  # no player data
        scheme_map = {"BOS": "drop_coverage", "OKC": "switch_heavy"}
        rows = _rows(stats=["pts"], current=8.0, projected=20.0, pid=1001, team="BOS")
        result = apply_matchup_tilt(snap, rows,
                                    scheme_map=scheme_map, atlas=atlas)
        pts_row = next(r for r in result if r["stat"] == "pts")
        assert pts_row["projected_final"] == 20.0, (
            "Uncovered player must be untouched"
        )

    def test_tilt_applied_to_remaining_only(self):
        """Verify formula: new_proj = current + remaining * (1 + tilt)."""
        self._enable()
        snap = _snap(home="BOS", away="OKC")
        # Controlled atlas: switch_heavy=28, others=20 → tilt ≈ (28/22.67)-1 ≈ +0.235, capped at 0.15
        atlas = {
            1001: {
                "switch_heavy": {"pts": 28.0, "reb": 6.0, "ast": 5.0, "fg3m": 3.0},
                "drop_coverage": {"pts": 20.0, "reb": 5.0, "ast": 4.5, "fg3m": 2.5},
                "balanced": {"pts": 20.0, "reb": 5.0, "ast": 4.5, "fg3m": 2.5},
            }
        }
        scheme_map = {"BOS": "drop_coverage", "OKC": "switch_heavy"}
        current, projected = 8.0, 20.0
        rows = _rows(stats=["pts"], current=current, projected=projected,
                     pid=1001, team="BOS")
        result = apply_matchup_tilt(snap, rows,
                                    scheme_map=scheme_map, atlas=atlas)
        pts_row = next(r for r in result if r["stat"] == "pts")
        # compute expected
        tilt = compute_tilt(1001, "switch_heavy", "pts", atlas)
        remaining = max(0.0, projected - current)
        expected = current + remaining * (1.0 + tilt)
        assert abs(pts_row["projected_final"] - expected) < 1e-9, (
            f"projected_final={pts_row['projected_final']} != expected={expected}"
        )

    def test_abs_tilt_never_exceeds_max(self):
        """All tilt-applied rows must have |delta|/remaining <= _MAX_TILT."""
        self._enable()
        snap = _snap(home="BOS", away="OKC")
        atlas = {
            1001: {
                "switch_heavy": {"pts": 100.0, "reb": 100.0, "ast": 100.0, "fg3m": 100.0},
                "drop_coverage": {"pts": 1.0, "reb": 1.0, "ast": 1.0, "fg3m": 1.0},
            }
        }
        scheme_map = {"BOS": "drop_coverage", "OKC": "switch_heavy"}
        rows = _rows(stats=list(TILT_STATS), current=5.0, projected=15.0,
                     pid=1001, team="BOS")
        result = apply_matchup_tilt(snap, rows,
                                    scheme_map=scheme_map, atlas=atlas)
        for row in result:
            if row["stat"] not in TILT_STATS:
                continue
            remaining_before = max(0.0, 15.0 - 5.0)
            if remaining_before <= 0:
                continue
            delta = abs(row["projected_final"] - 15.0)
            rel = delta / remaining_before
            assert rel <= _MAX_TILT + 1e-9, (
                f"stat {row['stat']}: relative tilt {rel:.4f} > _MAX_TILT {_MAX_TILT}"
            )

    def test_non_tilt_stats_untouched(self):
        """STL, BLK, TOV rows must not be mutated."""
        self._enable()
        snap = _snap(home="BOS", away="OKC")
        atlas = {
            1001: {
                "switch_heavy": {"pts": 28.0, "reb": 6.0, "ast": 5.0, "fg3m": 3.0},
                "drop_coverage": {"pts": 20.0, "reb": 5.0, "ast": 4.0, "fg3m": 2.5},
            }
        }
        scheme_map = {"BOS": "drop_coverage", "OKC": "switch_heavy"}
        rows = _rows(stats=["stl", "blk", "tov"], current=1.0, projected=3.0,
                     pid=1001, team="BOS")
        result = apply_matchup_tilt(snap, rows,
                                    scheme_map=scheme_map, atlas=atlas)
        for row in result:
            assert row["projected_final"] == 3.0, (
                f"stat {row['stat']} should be untouched, got {row['projected_final']}"
            )

    def test_no_remaining_delta_untouched(self):
        """When projected_final == current (player done), no change."""
        self._enable()
        snap = _snap(home="BOS", away="OKC")
        atlas = _atlas_with_bias()
        scheme_map = {"BOS": "drop_coverage", "OKC": "switch_heavy"}
        # current == projected_final (player has finished)
        rows = _rows(stats=["pts"], current=10.0, projected=10.0,
                     pid=1001, team="BOS")
        result = apply_matchup_tilt(snap, rows,
                                    scheme_map=scheme_map, atlas=atlas)
        pts_row = next(r for r in result if r["stat"] == "pts")
        assert pts_row["projected_final"] == 10.0
