"""tests/platformkit/improve/test_prop_line_distance_calib.py

Acceptance tests for prop_line_distance_calib.run_line_distance_calib.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest
      tests/platformkit/improve/test_prop_line_distance_calib.py -q

Tests:
  (1) synthetic OOF: pickem band UNRELIABLE, far band CALIBRATION_PROVEN
  (2) leak-free: z uses sigma from rows with date < game_i_date ONLY
  (3) thin band (n < MIN_N) -> verdict==INSUFFICIENT_DATA, brier/ece/bss absent
  (4) absent/empty OOF -> all INSUFFICIENT_DATA, never raises
  (5) stat with all three bands thin -> all INSUFFICIENT_DATA
  (6) no $/roi/pnl/edge/profit key in any returned dict
  (7) table is list of dicts with keys {stat, band, n, brier, ece, bss, verdict}
  never raises on malformed input
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_oof_row(
    stat: str,
    pred: float,
    actual: float,
    date: str = "2024-01-01",
) -> Dict[str, Any]:
    return {"stat": stat, "oof_pred": pred, "actual": actual, "game_date": date}


# ---------------------------------------------------------------------------
# (1) Synthetic OOF: pickem UNRELIABLE, far CALIBRATION_PROVEN
# ---------------------------------------------------------------------------
# Design rationale:
#   We monkeypatch _compute_rolling_sigma to return a fixed sigma=0.1
#   so band assignment is deterministic and independent of residual dynamics.
#
#   With sigma=0.1, _nearest_half_line(pred), and line=5.5:
#     far    : pred in {5.2, 5.8} -> |z|=3.0 -> far
#     pickem : pred=5.499         -> |z|=0.01 -> pickem
#
#   Far rows (far band):
#     pred alternates 5.2/5.8, actual matches pred -> perfect predictions:
#       p_over(5.2,0.1,5.5) ~ 0.0013, outcome=0 (5.2<5.5) -> near-zero Brier
#       p_over(5.8,0.1,5.5) ~ 0.9987, outcome=1 (5.8>5.5) -> near-zero Brier
#     => high BSS, low ECE -> CALIBRATION_PROVEN
#
#   Pickem rows (pickem band):
#     pred=5.499 (p_over~0.496), actual ALWAYS 8.0 (outcome=1 always):
#       model says ~50% over, reality is 100% over -> miscalibrated, ECE high
#     => bss<0 or high ECE -> UNRELIABLE
# ---------------------------------------------------------------------------

def _constant_sigma_factory(sigma: float):
    """Returns a _compute_rolling_sigma replacement that always returns sigma."""
    def _fixed(dates, preds, actuals, floor):
        return [sigma] * len(dates)
    return _fixed


class TestSyntheticBands:
    """(1) Pickem band UNRELIABLE, far band CALIBRATION_PROVEN."""

    def test_pickem_unreliable_far_proven(self, monkeypatch):
        import pandas as pd
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        # Inject fixed sigma=0.1 for deterministic band assignment
        monkeypatch.setattr(mod, "_compute_rolling_sigma", _constant_sigma_factory(0.1))
        # Also patch sigma floor (used to look up stat's floor before passing to _compute_rolling_sigma)
        monkeypatch.setattr(
            "scripts.platformkit.props_eval_nba._SIGMA_FLOOR",
            {"pts": 0.1},
        )

        n = 200
        rows: List[Dict[str, Any]] = []

        # Far rows: pred alternates 5.2/5.8, actual matches pred
        # pred=5.2 -> line=5.5, z=3.0 (far), p_over~0.0013, actual<5.5 -> outcome=0
        # pred=5.8 -> line=5.5, z=3.0 (far), p_over~0.9987, actual>5.5 -> outcome=1
        # Both: model is nearly always right -> very low Brier, high BSS
        for i in range(n):
            date = f"2024-01-{(i % 28) + 1:02d}"
            pred = 5.2 if i % 2 == 0 else 5.8
            actual = pred  # actual matches prediction (stays on same side of line)
            rows.append(_make_oof_row("pts", pred, actual, date))

        # Pickem rows: pred=5.499 (z=0.01, pickem), actual ALWAYS 8.0 -> outcome=1
        # p_over~0.496, but actual is always over -> ECE high, BSS negative
        for i in range(n):
            date = f"2024-02-{(i % 28) + 1:02d}"
            rows.append(_make_oof_row("pts", 5.499, 8.0, date))

        df = pd.DataFrame(rows)
        table = mod.run_line_distance_calib(df, stats=["pts"])

        assert isinstance(table, list), "table must be list"
        by_band = {row["band"]: row for row in table if row["stat"] == "pts"}

        far_row = by_band.get("far")
        pickem_row = by_band.get("pickem")

        assert far_row is not None, "far band row must be present"
        assert pickem_row is not None, "pickem band row must be present"
        assert far_row["n"] >= 30, f"far band must have n>=30, got {far_row['n']}"
        assert pickem_row["n"] >= 30, f"pickem band must have n>=30, got {pickem_row['n']}"

        assert far_row["verdict"] == mod.CALIBRATION_PROVEN, (
            f"far expected CALIBRATION_PROVEN, got {far_row['verdict']}, "
            f"brier={far_row['brier']}, ece={far_row['ece']}, bss={far_row['bss']}"
        )
        assert pickem_row["verdict"] == mod.UNRELIABLE, (
            f"pickem expected UNRELIABLE, got {pickem_row['verdict']}, "
            f"brier={pickem_row['brier']}, ece={pickem_row['ece']}, "
            f"bss={pickem_row['bss']}"
        )

        # Both present in per-(stat, band) table
        assert any(r["stat"] == "pts" and r["band"] == "far" for r in table)
        assert any(r["stat"] == "pts" and r["band"] == "pickem" for r in table)


# ---------------------------------------------------------------------------
# (2) Leak-free: sigma computed from rows with date < game_i_date only
# ---------------------------------------------------------------------------

class TestLeakFree:
    """z uses sigma from rows with date < game_i_date ONLY."""

    def test_sigma_uses_only_past_dates(self):
        """Manually verify _compute_rolling_sigma against hand-computed values."""
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        # 5 rows with distinct dates and known residuals
        preds_v = [5.0, 5.0, 5.0, 5.0, 5.0]
        actuals_v = [6.0, 7.0, 4.0, 3.0, 8.0]  # residuals: 1, 2, -1, -2, 3
        dates_v = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        sigma_floor = 0.5

        sigmas = mod._compute_rolling_sigma(dates_v, preds_v, actuals_v, sigma_floor)

        # Row 0: no past data -> floor
        assert abs(sigmas[0] - sigma_floor) < 1e-9, "row 0 must use floor"

        # Row 1: past = [residual of row 0] = [1.0], n=1 < 2 -> floor
        assert abs(sigmas[1] - sigma_floor) < 1e-9, "row 1: only 1 past point -> floor"

        # Row 2: past = [1.0, 2.0], mean=1.5, var=(0.25+0.25)/1=0.5, sigma=0.707
        # max(0.707, 0.5) = 0.707
        past = [1.0, 2.0]
        mean_r = sum(past) / len(past)
        var = sum((r - mean_r) ** 2 for r in past) / (len(past) - 1)
        exp_sigma = max(math.sqrt(max(var, 1e-9)), sigma_floor)
        assert abs(sigmas[2] - exp_sigma) < 1e-9, (
            f"row 2: expected {exp_sigma:.6f}, got {sigmas[2]:.6f}"
        )

        # Row 3: past = [1.0, 2.0, -1.0], mean=2/3, var=sum(...)/(2)
        past3 = [1.0, 2.0, -1.0]
        mean3 = sum(past3) / 3
        var3 = sum((r - mean3) ** 2 for r in past3) / 2
        exp3 = max(math.sqrt(max(var3, 1e-9)), sigma_floor)
        assert abs(sigmas[3] - exp3) < 1e-9, (
            f"row 3: expected {exp3:.6f}, got {sigmas[3]:.6f}"
        )

        # Confirm future rows (4 and 5) do NOT affect sigma of row 0 or 1
        # (already verified since sigmas[0] and sigmas[1] == floor)

    def test_same_date_not_leaked(self):
        """Rows with the same date as game_i do NOT contribute to sigma[i]."""
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        # Two rows on same date, one row on a later date
        rows = [
            {"pred": 5.0, "actual": 10.0, "game_date": "2024-01-01"},  # residual=5
            {"pred": 5.0, "actual": 0.0, "game_date": "2024-01-01"},   # residual=-5
            {"pred": 5.0, "actual": 5.0, "game_date": "2024-01-02"},   # later
        ]
        dates = [r["game_date"] for r in rows]
        preds_v = [r["pred"] for r in rows]
        actuals_v = [r["actual"] for r in rows]

        sigmas = mod._compute_rolling_sigma(dates, preds_v, actuals_v, 1.0)

        # Rows 0 and 1 (2024-01-01): no prior dates -> sigma = floor
        assert abs(sigmas[0] - 1.0) < 1e-9, "row 0 sigma must be floor (no past)"
        assert abs(sigmas[1] - 1.0) < 1e-9, "row 1 sigma must be floor (same date, no past)"

        # Row 2 (2024-01-02): past = rows from 2024-01-01 -> residuals [5, -5]
        # sample std: mean=0, var=50/1=50, sigma=sqrt(50)~7.07
        past = [5.0, -5.0]
        mean_p = sum(past) / 2
        var = sum((r - mean_p) ** 2 for r in past) / (2 - 1)  # sample std, n-1=1
        exp_sigma = max(math.sqrt(max(var, 1e-9)), 1.0)
        assert abs(sigmas[2] - exp_sigma) < 1e-6, (
            f"row 2 sigma should use past date residuals (exp={exp_sigma:.4f}, got={sigmas[2]:.4f})"
        )


# ---------------------------------------------------------------------------
# (3) Thin band -> INSUFFICIENT_DATA, brier/ece/bss None
# ---------------------------------------------------------------------------

class TestThinBand:
    """n < MIN_N -> verdict==INSUFFICIENT_DATA, metrics absent."""

    def test_thin_band_insufficient(self, monkeypatch):
        """Only a few rows -> all bands are thin."""
        import pandas as pd
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        monkeypatch.setattr(mod, "_compute_rolling_sigma", _constant_sigma_factory(0.1))
        monkeypatch.setattr(
            "scripts.platformkit.props_eval_nba._SIGMA_FLOOR", {"pts": 0.1}
        )
        # 5 rows total -- less than MIN_N for any band
        rows = [_make_oof_row("pts", 5.499, 3.0, f"2024-01-{i+1:02d}") for i in range(5)]
        df = pd.DataFrame(rows)

        table = mod.run_line_distance_calib(df, stats=["pts"], min_n=30)

        for row in table:
            if row["stat"] == "pts":
                assert row["verdict"] == mod.INSUFFICIENT_DATA, (
                    f"band {row['band']} n={row['n']} expected INSUFFICIENT_DATA"
                )
                assert row["brier"] is None, "brier must be None for thin band"
                assert row["ece"] is None, "ece must be None for thin band"
                assert row["bss"] is None, "bss must be None for thin band"

    def test_thin_band_n_recorded(self, monkeypatch):
        """Even thin bands should record their actual n."""
        import pandas as pd
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        monkeypatch.setattr(mod, "_compute_rolling_sigma", _constant_sigma_factory(0.1))
        monkeypatch.setattr(
            "scripts.platformkit.props_eval_nba._SIGMA_FLOOR", {"pts": 0.1}
        )
        rows = [_make_oof_row("pts", 5.499, 3.0, f"2024-01-{i+1:02d}") for i in range(5)]
        df = pd.DataFrame(rows)
        table = mod.run_line_distance_calib(df, stats=["pts"], min_n=30)

        pickem_rows = [r for r in table if r["stat"] == "pts" and r["band"] == "pickem"]
        assert len(pickem_rows) == 1
        assert pickem_rows[0]["n"] == 5


# ---------------------------------------------------------------------------
# (4) Absent/empty OOF -> all INSUFFICIENT_DATA, never raises
# ---------------------------------------------------------------------------

class TestAbsentOOF:
    """Absent or empty OOF -> all bands INSUFFICIENT_DATA, no exception."""

    def test_absent_parquet_returns_empty(self, tmp_path):
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        nonexistent = str(tmp_path / "does_not_exist.parquet")
        table = mod.run_line_distance_calib(oof_path=nonexistent)

        assert isinstance(table, list), "must return list"
        for row in table:
            assert row["verdict"] == mod.INSUFFICIENT_DATA
            assert row["brier"] is None
            assert row["ece"] is None

    def test_empty_dataframe_returns_insufficient(self):
        import pandas as pd
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        df = pd.DataFrame(
            columns=["stat", "oof_pred", "actual", "game_date"]
        )
        table = mod.run_line_distance_calib(df)
        assert isinstance(table, list)
        for row in table:
            assert row["verdict"] == mod.INSUFFICIENT_DATA

    def test_none_df_absent_path_no_raise(self, monkeypatch):
        """df=None and path absent -> all INSUFFICIENT_DATA, no raises."""
        import os
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        # Patch exists to False so parquet loading is skipped
        monkeypatch.setattr(os.path, "exists", lambda p: False)
        table = mod.run_line_distance_calib()
        assert isinstance(table, list)
        for row in table:
            assert row["verdict"] == mod.INSUFFICIENT_DATA


# ---------------------------------------------------------------------------
# (5) All three bands thin -> all INSUFFICIENT_DATA per stat
# ---------------------------------------------------------------------------

class TestAllBandsThin:
    """Stat with all three bands having n<MIN_N -> all INSUFFICIENT_DATA."""

    def test_all_bands_thin_for_stat(self, monkeypatch):
        import pandas as pd
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        monkeypatch.setattr(mod, "_compute_rolling_sigma", _constant_sigma_factory(0.1))
        monkeypatch.setattr(
            "scripts.platformkit.props_eval_nba._SIGMA_FLOOR", {"ast": 0.1}
        )
        # 3 rows: one per band (too few for any MIN_N)
        rows = [
            _make_oof_row("ast", 5.499, 1.0, "2024-01-01"),   # pickem
            _make_oof_row("ast", 5.4, 3.0, "2024-01-02"),     # near
            _make_oof_row("ast", 5.2, 12.0, "2024-01-03"),    # far
        ]
        df = pd.DataFrame(rows)
        table = mod.run_line_distance_calib(df, stats=["ast"], min_n=30)

        ast_rows = [r for r in table if r["stat"] == "ast"]
        assert len(ast_rows) == 3, f"expect 3 bands for ast, got {len(ast_rows)}"
        for row in ast_rows:
            assert row["verdict"] == mod.INSUFFICIENT_DATA, (
                f"expected INSUFFICIENT_DATA, got {row['verdict']} for band {row['band']}"
            )


# ---------------------------------------------------------------------------
# (6) No $/roi/pnl/edge/profit key
# ---------------------------------------------------------------------------

class TestHonestyKeys:
    """No forbidden key in any returned dict."""

    FORBIDDEN = frozenset({"$", "roi", "pnl", "edge", "profit", "dollar"})

    def test_no_forbidden_keys(self, monkeypatch):
        import pandas as pd
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        monkeypatch.setattr(mod, "_compute_rolling_sigma", _constant_sigma_factory(0.1))
        monkeypatch.setattr(
            "scripts.platformkit.props_eval_nba._SIGMA_FLOOR", {"pts": 0.1}
        )
        rows = [_make_oof_row("pts", 5.499, float(v % 10), f"2024-01-{(v % 28) + 1:02d}")
                for v in range(60)]
        df = pd.DataFrame(rows)
        table = mod.run_line_distance_calib(df, stats=["pts"])

        for row in table:
            for key in row:
                assert key.lower() not in self.FORBIDDEN, (
                    f"forbidden key '{key}' in output row"
                )

    def test_no_forbidden_keys_absent_oof(self, tmp_path):
        """Also check absent-OOF path."""
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        table = mod.run_line_distance_calib(
            oof_path=str(tmp_path / "absent.parquet"), stats=["pts"]
        )
        for row in table:
            for key in row:
                assert key.lower() not in self.FORBIDDEN


# ---------------------------------------------------------------------------
# (7) Table schema: list of dicts with required keys
# ---------------------------------------------------------------------------

class TestTableSchema:
    """Table is list of dicts with exactly {stat, band, n, brier, ece, bss, verdict}."""

    REQUIRED_KEYS = {"stat", "band", "n", "brier", "ece", "bss", "verdict"}

    def test_table_schema_with_data(self, monkeypatch):
        import pandas as pd
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        monkeypatch.setattr(mod, "_compute_rolling_sigma", _constant_sigma_factory(0.1))
        monkeypatch.setattr(
            "scripts.platformkit.props_eval_nba._SIGMA_FLOOR", {"pts": 0.1}
        )
        rows = [_make_oof_row("pts", 5.499, float(v % 10), f"2024-01-{(v % 28) + 1:02d}")
                for v in range(100)]
        df = pd.DataFrame(rows)
        table = mod.run_line_distance_calib(df, stats=["pts"])

        assert isinstance(table, list)
        for row in table:
            assert isinstance(row, dict), f"each row must be dict, got {type(row)}"
            assert self.REQUIRED_KEYS.issubset(set(row.keys())), (
                f"row missing required keys: {self.REQUIRED_KEYS - set(row.keys())}"
            )

    def test_table_schema_absent_parquet(self, tmp_path):
        """Schema holds even on absent OOF."""
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        table = mod.run_line_distance_calib(
            oof_path=str(tmp_path / "absent.parquet"),
            stats=["pts", "reb"],
        )
        assert isinstance(table, list)
        for row in table:
            assert self.REQUIRED_KEYS.issubset(set(row.keys())), (
                f"absent-OOF row missing keys: {self.REQUIRED_KEYS - set(row.keys())}"
            )

    def test_band_values_in_allowed_set(self, monkeypatch):
        """band values must be one of pickem/near/far."""
        import pandas as pd
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        monkeypatch.setattr(mod, "_compute_rolling_sigma", _constant_sigma_factory(0.1))
        monkeypatch.setattr(
            "scripts.platformkit.props_eval_nba._SIGMA_FLOOR", {"pts": 0.1}
        )
        rows = [_make_oof_row("pts", 5.499, 3.0, f"2024-01-{i+1:02d}") for i in range(3)]
        df = pd.DataFrame(rows)
        table = mod.run_line_distance_calib(df, stats=["pts"])
        valid_bands = {"pickem", "near", "far"}
        for row in table:
            assert row["band"] in valid_bands, f"unexpected band: {row['band']}"

    def test_verdict_values_allowed(self, monkeypatch):
        """verdict is always one of the four sentinel strings."""
        import pandas as pd
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        monkeypatch.setattr(mod, "_compute_rolling_sigma", _constant_sigma_factory(0.1))
        monkeypatch.setattr(
            "scripts.platformkit.props_eval_nba._SIGMA_FLOOR", {"pts": 0.1}
        )
        rows = [_make_oof_row("pts", 5.499, 3.0, f"2024-01-{i+1:02d}") for i in range(3)]
        df = pd.DataFrame(rows)
        table = mod.run_line_distance_calib(df, stats=["pts"])
        valid = {
            mod.CALIBRATION_PROVEN, mod.UNRELIABLE,
            mod.MARGINAL, mod.INSUFFICIENT_DATA,
        }
        for row in table:
            assert row["verdict"] in valid, f"unexpected verdict: {row['verdict']}"

    def test_covers_all_three_bands(self, monkeypatch):
        """Table always contains exactly 3 rows per stat (one per band)."""
        import pandas as pd
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        monkeypatch.setattr(mod, "_compute_rolling_sigma", _constant_sigma_factory(0.1))
        monkeypatch.setattr(
            "scripts.platformkit.props_eval_nba._SIGMA_FLOOR", {"pts": 0.1}
        )
        rows = [_make_oof_row("pts", 5.499, 3.0, f"2024-01-{i+1:02d}") for i in range(3)]
        df = pd.DataFrame(rows)
        table = mod.run_line_distance_calib(df, stats=["pts"])

        pts_rows = [r for r in table if r["stat"] == "pts"]
        assert len(pts_rows) == 3, f"expect 3 bands, got {len(pts_rows)}"
        bands_seen = {r["band"] for r in pts_rows}
        assert bands_seen == {"pickem", "near", "far"}


# ---------------------------------------------------------------------------
# (bonus) Never raises on malformed input
# ---------------------------------------------------------------------------

class TestNeverRaises:
    """run_line_distance_calib never raises regardless of input."""

    def test_none_input(self):
        import scripts.platformkit.improve.prop_line_distance_calib as mod
        result = mod.run_line_distance_calib(None)
        assert isinstance(result, list)

    def test_garbage_dataframe(self):
        import pandas as pd
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        df = pd.DataFrame({"junk": [1, 2, 3], "other": ["a", "b", "c"]})
        result = mod.run_line_distance_calib(df)
        assert isinstance(result, list)

    def test_nan_values(self, monkeypatch):
        import pandas as pd
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        monkeypatch.setattr(mod, "_compute_rolling_sigma", _constant_sigma_factory(0.1))
        monkeypatch.setattr(
            "scripts.platformkit.props_eval_nba._SIGMA_FLOOR", {"pts": 0.1}
        )
        df = pd.DataFrame([
            {"stat": "pts", "oof_pred": float("nan"), "actual": 5.0,
             "game_date": "2024-01-01"},
            {"stat": "pts", "oof_pred": 5.0, "actual": float("nan"),
             "game_date": "2024-01-02"},
            {"stat": "pts", "oof_pred": float("inf"), "actual": 5.0,
             "game_date": "2024-01-03"},
        ])
        result = mod.run_line_distance_calib(df)
        assert isinstance(result, list)

    def test_empty_stats_list(self):
        import pandas as pd
        import scripts.platformkit.improve.prop_line_distance_calib as mod

        df = pd.DataFrame(columns=["stat", "oof_pred", "actual", "game_date"])
        result = mod.run_line_distance_calib(df, stats=[])
        assert isinstance(result, list)
        assert len(result) == 0
