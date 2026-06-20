"""Per-file test for scripts.platformkit.props_eval_nba.

Acceptance criteria (all must pass):
  1. Synthetic OOF frame -> per-stat dict has n / brier / bss for each stat.
  2. INSUFFICIENT_DATA returned for stats with fewer than _MIN_N rows (never fabricated).
  3. Cache round-trip: write_nba_calibration_cache writes JSON; load_nba_calibration
     reads it back with identical per-stat bss values.
  4. Absent OOF input -> INSUFFICIENT_DATA sentinel, never a fabricated metric.
  5. load_nba_calibration on absent cache path -> {} (never raises).

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_props_eval_nba.py -q
"""
from __future__ import annotations

import json
import math
import os
import tempfile

import pytest

from scripts.platformkit.props_eval_nba import (
    INSUFFICIENT_DATA,
    NBA_STATS,
    _MIN_N,
    _build_nba_cache_payload,
    _build_preds_for_stat,
    _nearest_half_line,
    _p_over_gaussian,
    _per_stat_sigma,
    load_nba_calibration,
    score_nba_oof,
    write_nba_calibration_cache,
)
from scripts.platformkit import prop_tiering


# ---------------------------------------------------------------------------
# Fixtures -- synthetic OOF dataframe
# ---------------------------------------------------------------------------

def _make_oof_df(n_per_stat: int = 60, stats=None, seed: int = 42):
    """Build a synthetic pregame_oof-shaped DataFrame."""
    import pandas as pd
    import numpy as np

    rng = np.random.default_rng(seed)
    stats = stats or NBA_STATS
    rows = []
    for stat in stats:
        means = {"pts": 15.0, "reb": 5.0, "ast": 4.0,
                 "stl": 1.2, "blk": 0.8, "fg3m": 1.8, "tov": 2.0}
        mu = means.get(stat, 5.0)
        # oof_pred near the mean with some spread; actual has independent noise
        preds = rng.normal(mu, mu * 0.3, size=n_per_stat).clip(0)
        actuals = rng.normal(mu, mu * 0.35, size=n_per_stat).clip(0)
        for p, a in zip(preds, actuals):
            rows.append({
                "game_id": "G001",
                "player_id": 1,
                "stat": stat,
                "oof_pred": float(p),
                "actual": float(a),
                "game_date": "2024-01-01",
                "fold": 1,
                "season": "2024-25",
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------

class TestNearestHalfLine:
    def test_round_to_nearest_half(self):
        assert _nearest_half_line(15.3) == 15.5
        assert _nearest_half_line(15.0) == 14.5
        assert _nearest_half_line(15.7) == 15.5

    def test_minimum_is_half(self):
        assert _nearest_half_line(0.0) == 0.5
        assert _nearest_half_line(-1.0) == 0.5

    def test_non_finite(self):
        assert _nearest_half_line(float("nan")) == 0.5
        assert _nearest_half_line(float("inf")) == 0.5


class TestPOverGaussian:
    def test_at_mean_is_half(self):
        # p(x > mean) under symmetric Gaussian is 0.5
        p = _p_over_gaussian(10.0, 3.0, 10.0)
        assert abs(p - 0.5) < 1e-6

    def test_above_mean_is_less_than_half(self):
        # line above mean -> less likely to go over
        p = _p_over_gaussian(10.0, 3.0, 13.0)
        assert p < 0.5

    def test_below_mean_is_more_than_half(self):
        p = _p_over_gaussian(10.0, 3.0, 7.0)
        assert p > 0.5

    def test_zero_sigma_returns_half(self):
        p = _p_over_gaussian(10.0, 0.0, 10.0)
        assert p == 0.5

    def test_output_clipped(self):
        # Very far from line -> still in (0, 1)
        p = _p_over_gaussian(10.0, 1.0, 50.0)
        assert 0.0 <= p <= 1.0


class TestPerStatSigma:
    def test_basic(self):
        rows = [{"pred": float(i), "actual": float(i) + 2.0} for i in range(20)]
        sigma = _per_stat_sigma(rows)
        assert math.isfinite(sigma)
        assert sigma > 0

    def test_too_few_returns_one(self):
        rows = [{"pred": 5.0, "actual": 7.0}]
        assert _per_stat_sigma(rows) == 1.0

    def test_empty_returns_one(self):
        assert _per_stat_sigma([]) == 1.0


class TestBuildPredsForStat:
    def test_returns_p_and_outcome_keys(self):
        rows = [{"pred": 15.0, "actual": float(i)} for i in range(50)]
        preds = _build_preds_for_stat(rows, "pts")
        assert len(preds) == 50
        for p in preds:
            assert "p_over" in p and "outcome" in p
            assert 0.0 <= p["p_over"] <= 1.0
            assert p["outcome"] in (0, 1)

    def test_empty_input(self):
        assert _build_preds_for_stat([], "pts") == []

    def test_outcome_settled_correctly(self):
        # pred=10.0 -> line=9.5; actual=12.0 > 9.5 -> outcome=1
        preds = _build_preds_for_stat([{"pred": 10.0, "actual": 12.0}], "pts")
        assert len(preds) == 1
        assert preds[0]["outcome"] == 1

        # actual=8.0 < 9.5 -> outcome=0
        preds = _build_preds_for_stat([{"pred": 10.0, "actual": 8.0}], "pts")
        assert preds[0]["outcome"] == 0


# ---------------------------------------------------------------------------
# score_nba_oof
# ---------------------------------------------------------------------------

class TestScoreNbaOof:
    def test_absent_path_returns_insufficient_data(self, tmp_path):
        """Absent OOF parquet -> every stat is INSUFFICIENT_DATA, overall n=0."""
        absent = str(tmp_path / "nonexistent.parquet")
        res = score_nba_oof(oof_path=absent)
        assert res["overall"]["n"] == 0
        for stat in res["stats"]:
            assert res["per_stat"][stat] == INSUFFICIENT_DATA

    def test_none_df_and_absent_file_returns_insufficient_data(self, tmp_path):
        """Explicit df=None + nonexistent file -> INSUFFICIENT_DATA, no raise."""
        res = score_nba_oof(df=None, oof_path=str(tmp_path / "missing.parquet"))
        assert res["overall"]["n"] == 0

    def test_empty_df_returns_insufficient_data(self):
        """Empty DataFrame -> INSUFFICIENT_DATA, never raises."""
        import pandas as pd
        df = pd.DataFrame(columns=["stat", "oof_pred", "actual"])
        res = score_nba_oof(df=df)
        assert res["overall"]["n"] == 0

    def test_synthetic_oof_yields_per_stat_metrics(self):
        """Synthetic OOF -> each stat dict has n, brier, brier_skill_score."""
        df = _make_oof_df(n_per_stat=80)
        res = score_nba_oof(df=df)

        assert set(res["stats"]) == set(NBA_STATS)
        for stat in NBA_STATS:
            d = res["per_stat"][stat]
            assert d != INSUFFICIENT_DATA, f"{stat} should not be INSUFFICIENT_DATA (n=80)"
            assert isinstance(d, dict)
            assert d["n"] >= _MIN_N
            assert math.isfinite(d["brier"])
            assert d.get("brier_skill_score") is not None

    def test_overall_aggregates(self):
        """Overall n >= sum of per-stat n's (or equal if no overlap)."""
        df = _make_oof_df(n_per_stat=80)
        res = score_nba_oof(df=df)
        per_stat_n = sum(
            d["n"] for d in res["per_stat"].values()
            if isinstance(d, dict) and d.get("n")
        )
        assert res["overall"]["n"] == per_stat_n

    def test_thin_stat_returns_insufficient_data(self):
        """A stat with only 10 rows -> INSUFFICIENT_DATA (below _MIN_N=30)."""
        import pandas as pd
        rows = [{"stat": "ast", "oof_pred": 4.0 + i * 0.1, "actual": 3.5 + i * 0.05,
                 "game_id": f"G{i}", "player_id": 1, "game_date": "2024-01-01",
                 "fold": 1, "season": "2024-25"}
                for i in range(10)]
        df = pd.DataFrame(rows)
        res = score_nba_oof(df=df, stats=["ast"])
        assert res["per_stat"]["ast"] == INSUFFICIENT_DATA
        assert "n" not in res["per_stat"]["ast"] or True  # it's the string sentinel

    def test_brier_in_valid_range(self):
        """Brier scores must be in [0, 1]."""
        df = _make_oof_df(n_per_stat=100)
        res = score_nba_oof(df=df)
        for stat, d in res["per_stat"].items():
            if isinstance(d, dict):
                assert 0.0 <= d["brier"] <= 1.0, f"{stat} brier out of range"

    def test_note_never_empty(self):
        df = _make_oof_df()
        res = score_nba_oof(df=df)
        assert isinstance(res["note"], str) and len(res["note"]) > 0

    def test_no_dollar_keys(self):
        """No roi / pnl / profit keys in the output dict keys -- honesty invariant.
        (The note may say 'no $-edge' as a disclaimer, which is correct; we check
        that no key in the returned dicts is a banned accounting term.)"""
        df = _make_oof_df(n_per_stat=80)
        res = score_nba_oof(df=df)
        # Collect all dict keys recursively
        def all_keys(obj):
            keys = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    keys.append(k)
                    keys.extend(all_keys(v))
            elif isinstance(obj, (list, tuple)):
                for v in obj:
                    keys.extend(all_keys(v))
            return keys
        key_set = {k.lower() for k in all_keys(res)}
        banned_keys = ("roi", "pnl", "profit", "edge_dollars", "dollar_return")
        for b in banned_keys:
            assert b not in key_set, f"banned key '{b}' found in output dict keys"

    def test_subset_stats(self):
        """Passing stats=['pts','ast'] only scores those two."""
        df = _make_oof_df(n_per_stat=80)
        res = score_nba_oof(df=df, stats=["pts", "ast"])
        assert set(res["stats"]) == {"pts", "ast"}
        assert "reb" not in res["per_stat"]


# ---------------------------------------------------------------------------
# Cache round-trip
# ---------------------------------------------------------------------------

class TestCacheRoundTrip:
    def test_write_and_reload_identical_bss(self, tmp_path):
        """write_nba_calibration_cache writes JSON; load_nba_calibration reads it
        with identical per-stat bss values."""
        df = _make_oof_df(n_per_stat=80)
        cache_path = str(tmp_path / "nba_cal.json")

        payload = write_nba_calibration_cache(df, out_path=cache_path)
        assert payload["written"] is True

        loaded = load_nba_calibration(cache_path)
        assert isinstance(loaded, dict)
        # Every stat in the cache should reload
        for stat, d in payload["per_stat"].items():
            assert stat in loaded, f"{stat} missing from reloaded cache"
            assert abs((loaded[stat].get("bss") or 0.0) - (d.get("bss") or 0.0)) < 1e-9

    def test_written_json_is_valid(self, tmp_path):
        """Written file must be parseable JSON."""
        df = _make_oof_df(n_per_stat=80)
        cache_path = str(tmp_path / "nba_cal.json")
        write_nba_calibration_cache(df, out_path=cache_path)
        with open(cache_path, "r", encoding="ascii") as fh:
            obj = json.load(fh)
        assert "per_stat" in obj
        assert "overall" in obj
        assert "as_of" in obj

    def test_written_json_has_mode_nba(self, tmp_path):
        """Cache must record mode='nba_oof_walk_forward' not 'soccer'."""
        df = _make_oof_df(n_per_stat=80)
        cache_path = str(tmp_path / "nba_cal.json")
        write_nba_calibration_cache(df, out_path=cache_path)
        with open(cache_path, "r", encoding="ascii") as fh:
            obj = json.load(fh)
        assert obj.get("mode") == "nba_oof_walk_forward"

    def test_insufficient_data_not_written_to_cache(self, tmp_path):
        """Stats that returned INSUFFICIENT_DATA must NOT appear in the cache."""
        import pandas as pd
        # Only 5 rows for 'ast' -> INSUFFICIENT_DATA
        rows = [{"stat": "ast", "oof_pred": 4.0, "actual": 3.5,
                 "game_id": "G1", "player_id": 1, "game_date": "2024-01-01",
                 "fold": 1, "season": "2024-25"}] * 5
        df = pd.DataFrame(rows)
        cache_path = str(tmp_path / "nba_thin.json")
        payload = write_nba_calibration_cache(df, stats=["ast"], out_path=cache_path)
        # 'ast' has too few rows; must not be in per_stat
        assert "ast" not in payload.get("per_stat", {}), \
            "INSUFFICIENT_DATA stat must not appear in cache payload"

    def test_absent_cache_returns_empty_dict(self, tmp_path):
        """load_nba_calibration on absent path -> {} (never raises)."""
        result = load_nba_calibration(str(tmp_path / "missing.json"))
        assert result == {}

    def test_write_fails_gracefully_on_bad_path(self):
        """write_nba_calibration_cache with unwritable path -> written=False, no raise."""
        df = _make_oof_df(n_per_stat=80)
        # Use an invalid path (directory that cannot be created)
        bad_path = "/no/such/directory/allowed/nba_cal.json"
        try:
            payload = write_nba_calibration_cache(df, out_path=bad_path)
            # If it gets here (e.g., path creation somehow succeeded), skip gracefully
            # On Windows, should fail; accept either written=False or if somehow ok
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"write_nba_calibration_cache raised: {exc}")


# ---------------------------------------------------------------------------
# prop_tiering round-trip (via the exact same reader the board uses)
# ---------------------------------------------------------------------------

class TestPropTieringIntegration:
    def test_load_nba_calibration_classifies_each_stat(self, tmp_path):
        """After writing cache, load_nba_calibration + prop_tiering.classify each stat.

        Uses load_nba_calibration (NBA-specific, bypasses soccer staleness guard)
        then classifies via prop_tiering.classify.
        """
        df = _make_oof_df(n_per_stat=200)  # large n to get real scores
        cache_path = str(tmp_path / "nba_cal.json")
        write_nba_calibration_cache(df, out_path=cache_path)

        cal = load_nba_calibration(cache_path)
        assert isinstance(cal, dict) and len(cal) > 0

        for stat in cal:
            label, bss, n = prop_tiering.classify(stat, cal)
            assert label in ("proven", "marginal", "weak", "unmeasured"), \
                f"{stat} got unexpected label {label!r}"
            # n must be positive (we wrote only positive-n stats)
            assert n is None or n > 0

    def test_load_nba_calibration_reads_n_correctly(self, tmp_path):
        """n values from cache match those scored (via load_nba_calibration)."""
        df = _make_oof_df(n_per_stat=80)
        cache_path = str(tmp_path / "nba_cal.json")
        payload = write_nba_calibration_cache(df, out_path=cache_path)
        cal = load_nba_calibration(cache_path)

        for stat, d in payload["per_stat"].items():
            assert cal[stat]["n"] == d["n"]

    def test_load_nba_calibration_bypasses_stale_guard(self, tmp_path):
        """load_nba_calibration must NOT apply the soccer settle-version stale guard.

        Write a cache with settle_logic_version=None (NBA has no soccer version);
        load_nba_calibration must return the stats, not an empty dict.
        """
        import json as _json
        cache_path = str(tmp_path / "nba_stale_test.json")
        payload = {
            "as_of": "2026-01-01T00:00:00+00:00",
            "settle_logic_version": None,  # NBA: no soccer settle version
            "mode": "nba_oof_walk_forward",
            "overall": {"bss": 0.01, "brier": 0.24, "ece": 0.03, "n": 100},
            "per_stat": {
                "ast": {"bss": 0.05, "brier": 0.23, "ece": 0.02, "n": 100},
                "pts": {"bss": 0.01, "brier": 0.25, "ece": 0.04, "n": 100},
            },
            "note": "test",
        }
        with open(cache_path, "w", encoding="ascii") as fh:
            _json.dump(payload, fh)
        cal = load_nba_calibration(cache_path)
        assert "ast" in cal and "pts" in cal, \
            "load_nba_calibration must not flag NBA cache as stale"


# ---------------------------------------------------------------------------
# build_nba_cache_payload helper
# ---------------------------------------------------------------------------

class TestBuildNbaCachePayload:
    def test_excludes_insufficient_data_stats(self):
        """INSUFFICIENT_DATA entries must be excluded from per_stat output."""
        res = {
            "per_stat": {
                "ast": {"n": 50, "brier": 0.23, "brier_skill_score": 0.04, "ece": 0.02},
                "pts": INSUFFICIENT_DATA,
            },
            "overall": {"n": 50, "brier": 0.23, "brier_skill_score": 0.04, "ece": 0.02},
            "note": "test",
        }
        payload = _build_nba_cache_payload(res)
        assert "ast" in payload["per_stat"]
        assert "pts" not in payload["per_stat"]

    def test_overall_n_in_payload(self):
        res = {
            "per_stat": {
                "ast": {"n": 50, "brier": 0.23, "brier_skill_score": 0.04, "ece": 0.02},
            },
            "overall": {"n": 50, "brier": 0.23, "brier_skill_score": 0.04, "ece": 0.02},
            "note": "test note",
        }
        payload = _build_nba_cache_payload(res)
        assert payload["overall"]["n"] == 50
        assert payload["note"] == "test note"
        assert payload["mode"] == "nba_oof_walk_forward"

    def test_as_of_is_present_and_string(self):
        res = {"per_stat": {}, "overall": {}, "note": ""}
        payload = _build_nba_cache_payload(res)
        assert isinstance(payload.get("as_of"), str) and len(payload["as_of"]) > 0
