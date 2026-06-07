"""tests/test_courtvision_data.py — EX-1 CV_ROW_SIGMA flag tests.

Three required tests:
  (a) CV_ROW_SIGMA unset → grade_bet output byte-identical to flat-sigma path
      for a REB row.
  (b) CV_ROW_SIGMA=1 + REB row with monotone q10/q90 → sigma and p_over differ
      from the flat-sigma result (per-row sigma is wired in).
  (c) AST and PTS rows are unaffected even with CV_ROW_SIGMA=1.
"""
from __future__ import annotations

import math
import os
import sys
from typing import Any

import pytest

# Ensure project root is on sys.path when run directly.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from api._courtvision_data import grade_bet, normal_cdf


# ── Minimal stubs so tests never touch the filesystem / network ────────────────

class _FakeBettingEdge:
    """Minimal stand-in for BettingEdge used inside grade_bet."""
    def evaluate(self, model_prob: float, odds: int, bankroll: float = 5000.0) -> dict:
        if odds >= 100:
            b = odds / 100.0
        else:
            b = 100.0 / abs(odds)
        q = 1.0 - model_prob
        f = max(0.0, (b * model_prob - q) / b)
        return {
            "implied_prob": 100.0 / (abs(odds) + 100.0) if odds < 0
                            else odds / (odds + 100.0),
            "kelly_size": f * bankroll,
        }


def _patch_betting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the module-level _BETTING singleton with the stub."""
    import api._courtvision_data as _mod
    monkeypatch.setattr(_mod, "_BETTING", _FakeBettingEdge(), raising=True)


def _patch_team_color(monkeypatch: pytest.MonkeyPatch) -> None:
    import api._courtvision_data as _mod
    monkeypatch.setattr(_mod, "_team_primary_color", lambda abbr: "#000000", raising=True)


# ── Shared fixtures ────────────────────────────────────────────────────────────

_STAT_SIGMA: dict[str, float] = {
    "pts": 5.0, "reb": 2.5, "ast": 2.0, "fg3m": 1.5,
    "stl": 0.8, "blk": 0.7, "tov": 1.2,
}
_BANKROLL = 5000.0
_BOOKS = [{"book": "DraftKings", "over_odds": -110, "under_odds": -110}]


def _reb_slate_row(with_quantiles: bool = False) -> dict[str, Any]:
    row: dict[str, Any] = {
        "player_id": "1234", "player_name": "Test Player",
        "team": "OKC", "opp": "SAS", "venue": "home",
        "game_id": "0042500317", "date": "2026-06-01",
        "injury_status": "", "stat": "reb", "q50": 8.5,
    }
    if with_quantiles:
        # q10=5.2, q90=12.0 gives a band sigma = (12.0-5.2)/2.5631 ≈ 2.653
        # which differs from the flat sigma of 2.5.
        row["q10"] = 5.2
        row["q90"] = 12.0
    return row


def _line_row(line: float = 9.5) -> dict[str, Any]:
    return {"line": line, "books": _BOOKS}


# ── Test (a): CV_ROW_SIGMA unset → byte-identical to flat-sigma ────────────────

def test_reb_flag_off_is_byte_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    """grade_bet output must be IDENTICAL when CV_ROW_SIGMA is unset,
    regardless of whether the slate row carries q10/q90."""
    _patch_betting(monkeypatch)
    _patch_team_color(monkeypatch)
    # Guarantee the env var is absent.
    monkeypatch.delenv("CV_ROW_SIGMA", raising=False)

    row_without = _reb_slate_row(with_quantiles=False)
    row_with = _reb_slate_row(with_quantiles=True)

    ln = _line_row()
    result_without = grade_bet(row_without, ln, _STAT_SIGMA, _BANKROLL)
    result_with = grade_bet(row_with, ln, _STAT_SIGMA, _BANKROLL)

    # Both must produce the same model_prob and sigma-derived values.
    assert result_without["model_prob"] == result_with["model_prob"], (
        "model_prob changed when CV_ROW_SIGMA is unset — flat path violated"
    )
    assert result_without["ev_pct"] == result_with["ev_pct"], (
        "ev_pct changed when CV_ROW_SIGMA is unset"
    )
    assert result_without["kelly_pct"] == result_with["kelly_pct"], (
        "kelly_pct changed when CV_ROW_SIGMA is unset"
    )
    # Verify the flat sigma is actually being used.
    # grade_bet: p_over = 1 - normal_cdf((line - q50) / sigma)
    #            side = "OVER" if q50 >= line else "UNDER"
    #            model_prob = p_over if side == "OVER" else 1 - p_over
    q50 = float(row_without["q50"])
    line = float(ln["line"])
    flat_sigma = _STAT_SIGMA["reb"]
    p_over = 1.0 - normal_cdf((line - q50) / flat_sigma)
    expected_model_prob = p_over if q50 >= line else 1.0 - p_over
    assert abs(result_without["model_prob"] - round(expected_model_prob, 4)) < 1e-9, (
        "model_prob does not match flat-sigma calculation"
    )


# ── Test (b): CV_ROW_SIGMA=1 + REB + monotone quantiles → sigma differs ───────

def test_reb_flag_on_uses_per_row_sigma(monkeypatch: pytest.MonkeyPatch) -> None:
    """With CV_ROW_SIGMA=1 and a REB row carrying monotone q10/q90 whose
    band-sigma differs from the flat sigma, model_prob MUST differ."""
    _patch_betting(monkeypatch)
    _patch_team_color(monkeypatch)
    monkeypatch.setenv("CV_ROW_SIGMA", "1")

    row_with = _reb_slate_row(with_quantiles=True)
    row_without = _reb_slate_row(with_quantiles=False)
    ln = _line_row()

    result_per_row = grade_bet(row_with, ln, _STAT_SIGMA, _BANKROLL)
    result_flat = grade_bet(row_without, ln, _STAT_SIGMA, _BANKROLL)

    # The band-sigma from q10=5.2/q90=12.0: after apply_qcal (reb is symmetric,
    # scale ~1.0), (cq90-cq10)/2.5631 ≈ 2.65, vs flat=2.5.  They must differ.
    assert result_per_row["model_prob"] != result_flat["model_prob"], (
        "model_prob did not change with CV_ROW_SIGMA=1 and per-row q10/q90 — "
        "per-row sigma is not being applied"
    )

    # Sanity: the per-row path should yield a valid probability in (0, 1).
    assert 0.0 < result_per_row["model_prob"] < 1.0, (
        f"model_prob out of (0,1): {result_per_row['model_prob']}"
    )


def test_reb_flag_on_no_quantiles_falls_back_to_flat(monkeypatch: pytest.MonkeyPatch) -> None:
    """With CV_ROW_SIGMA=1 but q10/q90 absent, grade_bet must fall back to
    the flat sigma (graceful degradation)."""
    _patch_betting(monkeypatch)
    _patch_team_color(monkeypatch)
    monkeypatch.setenv("CV_ROW_SIGMA", "1")

    row_no_q = _reb_slate_row(with_quantiles=False)
    ln = _line_row()

    result = grade_bet(row_no_q, ln, _STAT_SIGMA, _BANKROLL)

    q50 = float(row_no_q["q50"])
    line = float(ln["line"])
    flat_sigma = _STAT_SIGMA["reb"]
    p_over = 1.0 - normal_cdf((line - q50) / flat_sigma)
    expected_model_prob = p_over if q50 >= line else 1.0 - p_over
    assert abs(result["model_prob"] - round(expected_model_prob, 4)) < 1e-9, (
        "grade_bet did not fall back to flat sigma when q10/q90 missing"
    )


def test_reb_flag_on_non_monotone_quantiles_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """With CV_ROW_SIGMA=1 but q10 > q50 (non-monotone), grade_bet must use
    the flat sigma (monotonicity guard)."""
    _patch_betting(monkeypatch)
    _patch_team_color(monkeypatch)
    monkeypatch.setenv("CV_ROW_SIGMA", "1")

    row_bad = _reb_slate_row(with_quantiles=False)
    row_bad["q10"] = 10.0   # q10 > q50 = 8.5 → non-monotone
    row_bad["q90"] = 12.0
    ln = _line_row()

    result = grade_bet(row_bad, ln, _STAT_SIGMA, _BANKROLL)

    q50 = float(row_bad["q50"])
    line = float(ln["line"])
    flat_sigma = _STAT_SIGMA["reb"]
    p_over = 1.0 - normal_cdf((line - q50) / flat_sigma)
    expected_model_prob = p_over if q50 >= line else 1.0 - p_over
    assert abs(result["model_prob"] - round(expected_model_prob, 4)) < 1e-9, (
        "grade_bet did not fall back to flat sigma for non-monotone q10/q90"
    )


# ── Test (c): AST and PTS rows are unaffected even with CV_ROW_SIGMA=1 ────────

@pytest.mark.parametrize("stat", ["ast", "pts", "fg3m"])
def test_excluded_stats_unaffected_by_flag(
        stat: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """AST, PTS, and FG3M grade_bet output must be identical with/without
    CV_ROW_SIGMA=1, even when q10/q90 are present in the slate row."""
    _patch_betting(monkeypatch)
    _patch_team_color(monkeypatch)

    row = {
        "player_id": "9999", "player_name": "Other Player",
        "team": "SAS", "opp": "OKC", "venue": "away",
        "game_id": "0042500317", "date": "2026-06-01",
        "injury_status": "", "stat": stat, "q50": 20.0,
        "q10": 14.0, "q90": 26.0,
    }
    # Use a line that differs from q50 so sigma differences would show up.
    ln = {"line": 21.5, "books": _BOOKS}

    monkeypatch.delenv("CV_ROW_SIGMA", raising=False)
    result_flag_off = grade_bet(row, ln, _STAT_SIGMA, _BANKROLL)

    monkeypatch.setenv("CV_ROW_SIGMA", "1")
    result_flag_on = grade_bet(row, ln, _STAT_SIGMA, _BANKROLL)

    assert result_flag_off["model_prob"] == result_flag_on["model_prob"], (
        f"model_prob changed for stat={stat} with CV_ROW_SIGMA=1 — "
        f"stat should be excluded from per-row sigma"
    )
    assert result_flag_off["ev_pct"] == result_flag_on["ev_pct"], (
        f"ev_pct changed for stat={stat} with CV_ROW_SIGMA=1"
    )
