"""tests/test_wnba_pipeline.py - smoke + unit tests for the WNBA pipeline (R17_J6).

These tests cover the deterministic math + plumbing (no live API calls):
    1. predict_player math: q50 == shrinkage-weighted blend, q10/q90 bounds.
    2. L5 lookback truncation: predict only uses the first `lookback` rows.
    3. Quantile-band ordering: q10 <= q50 <= q90, all >= 0.
    4. Ranker output schema: required keys + EV-sorted descending.

We monkeypatch wnba_proxy_predictor._gamelog_cached so no network is hit.
"""
from __future__ import annotations

import os
import sys
import tempfile

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts import wnba_proxy_predictor as wpp  # noqa: E402
from scripts import wnba_bet_ranker as wbr  # noqa: E402


# ---------- fixtures ----------
def _gamelog_fixture(n: int = 8) -> pd.DataFrame:
    """Build a fake PlayerGameLog DataFrame newest-first."""
    rows = []
    for i in range(n):
        rows.append({
            "GAME_DATE": pd.Timestamp(f"2025-08-{20-i:02d}"),
            "PTS":  20 + i,           # 20..27
            "REB":  6 + (i % 3),      # 6,7,8,6,7,8,...
            "AST":  4,                # const
            "FG3M": 2,
            "STL":  1,
            "BLK":  1,
            "TOV":  3,
        })
    return pd.DataFrame(rows)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Block all live API calls in every test in this file."""
    df = _gamelog_fixture(n=8)

    def fake_gamelog(pid: int, season: str):
        return df.copy()

    monkeypatch.setattr(wpp, "_gamelog_cached", fake_gamelog)

    # Also block the roster lookup so resolve_wnba_player works offline.
    def fake_roster(season: str = "2025"):
        return pd.DataFrame([
            {"PERSON_ID": 1001, "DISPLAY_FIRST_LAST": "Test Player",
             "DISPLAY_LAST_COMMA_FIRST": "Player, Test"},
            {"PERSON_ID": 1002, "DISPLAY_FIRST_LAST": "A'ja Wilson",
             "DISPLAY_LAST_COMMA_FIRST": "Wilson, A'ja"},
        ])

    monkeypatch.setattr(wpp, "_wnba_roster", fake_roster)


# ---------- 1. L5 fetch + math ----------
def test_l5_lookback_truncation():
    """predict_player should only consume the first `lookback` rows."""
    pred = wpp.predict_player(1001, season="2025", lookback=5, shrink=0.0)
    assert pred is not None
    # PTS over first 5 rows = mean(20,21,22,23,24) = 22.0
    # With shrink=0 the q50 must equal that raw mean exactly.
    assert pred["pts"]["mu_raw"] == pytest.approx(22.0)
    assert pred["pts"]["q50"] == pytest.approx(22.0)
    assert pred["pts"]["n_games"] == 5


def test_l5_uses_only_top_rows_not_all_history():
    """Lookback=3 should give mean(20,21,22)=21.0 (not 23.5 over all 8)."""
    pred = wpp.predict_player(1001, season="2025", lookback=3, shrink=0.0)
    assert pred["pts"]["mu_raw"] == pytest.approx(21.0)
    assert pred["pts"]["n_games"] == 3


# ---------- 2. q50 math (shrinkage blend) ----------
def test_q50_shrinkage_blend():
    """q50 = (1-w)*mu_raw + w*season_mean where w = K/(n+K).

    Fixture: PTS over all 8 rows = mean(20..27) = 23.5 (season prior),
    PTS over first L5 = 22.0 (recent), K=3, n=5 -> w = 3/8 = 0.375.
    """
    pred = wpp.predict_player(1001, season="2025", lookback=5, shrink=3.0)
    w_expected = 3.0 / (5 + 3.0)
    season_mean = 23.5  # mean(20..27)
    recent_mean = 22.0  # mean(20..24)
    mu_blend = (1 - w_expected) * recent_mean + w_expected * season_mean
    assert pred["pts"]["shrink_weight"] == pytest.approx(w_expected)
    assert pred["pts"]["q50"] == pytest.approx(mu_blend)
    # Blend must lie strictly between recent and season means.
    assert recent_mean <= pred["pts"]["q50"] <= season_mean


def test_q50_no_shrinkage_recovers_raw_mean():
    """shrink=0 -> q50 == mu_raw."""
    pred = wpp.predict_player(1001, season="2025", lookback=5, shrink=0.0)
    for stat in wpp.STATS:
        assert pred[stat]["q50"] == pytest.approx(pred[stat]["mu_raw"])


# ---------- 3. q10/q90 bounds ----------
def test_q10_q90_bounds_ordering():
    """q10 <= q50 <= q90, all >= 0."""
    pred = wpp.predict_player(1001, season="2025", lookback=5, shrink=3.0)
    for stat in wpp.STATS:
        q = pred[stat]
        assert 0 <= q["q10"] <= q["q50"] <= q["q90"], f"stat={stat} ordering broken"
        # Band width should be 2 * 1.2816 * sigma (when not clipped at 0)
        if q["q10"] > 0:
            assert (q["q90"] - q["q10"]) == pytest.approx(2 * 1.2816 * q["sigma"], rel=1e-6)


def test_q10_clipped_at_zero():
    """For low-mean stats, q10 should clip at zero rather than go negative."""
    pred = wpp.predict_player(1001, season="2025", lookback=5, shrink=3.0)
    # BLK in fixture is 1.0 per game, sigma_floor=0.4, mu blended ~0.77.
    # 0.77 - 1.2816*0.4 = ~0.26 -> still positive. STL same story.
    # We just assert clipping invariant: q10 >= 0 always.
    for stat in wpp.STATS:
        assert pred[stat]["q10"] >= 0.0


def test_quantile_band_uses_sigma_floor():
    """When observed sigma < floor, the floor must be used."""
    # AST is constant 4 in fixture -> observed sigma = 0.
    pred = wpp.predict_player(1001, season="2025", lookback=5, shrink=0.0)
    assert pred["ast"]["sigma"] == pytest.approx(wpp._SIGMA_FLOOR["ast"])


# ---------- 4. Bet ranker output schema ----------
def _fake_lines_df() -> pd.DataFrame:
    """Construct a tiny lines DataFrame as if read from Bovada CSV."""
    rows = [
        {"captured_at": pd.Timestamp.utcnow().tz_localize(None) if False else
                         pd.Timestamp("2026-05-26T12:00:00", tz="UTC"),
         "book": "bov", "game_id": "g1", "player_id": "",
         "player_name": "Test Player", "stat": "pts", "line": 17.5,
         "over_price": -110, "under_price": -110, "start_time": ""},
        {"captured_at": pd.Timestamp("2026-05-26T12:00:00", tz="UTC"),
         "book": "bov", "game_id": "g1", "player_id": "",
         "player_name": "Test Player", "stat": "reb", "line": 5.5,
         "over_price": -150, "under_price": +120, "start_time": ""},
        {"captured_at": pd.Timestamp("2026-05-26T12:00:00", tz="UTC"),
         "book": "bov", "game_id": "g1", "player_id": "",
         "player_name": "Unknown NBA Guy", "stat": "pts", "line": 22.5,
         "over_price": -110, "under_price": -110, "start_time": ""},
    ]
    return pd.DataFrame(rows)


def test_ranker_output_schema():
    """rank_bets must return the documented schema and EV-sort descending."""
    df = _fake_lines_df()
    payload = wbr.rank_bets(df, season="2025", lookback=5, shrink=3.0,
                             min_edge_pct=-1e9, bankroll=1000.0)
    # top-level
    assert "meta" in payload and "bets" in payload
    assert "n_evaluated" in payload and "n_bets" in payload
    meta = payload["meta"]
    for k in ("generated_at", "season", "lookback", "shrink",
              "bankroll", "n_lines_input", "n_wnba_resolved", "n_predictions"):
        assert k in meta, f"missing meta key {k}"
    # Test Player resolves, Unknown NBA Guy doesn't -> 1 resolved
    assert meta["n_wnba_resolved"] == 1
    assert meta["n_predictions"] == 1
    # Every bet must carry the required schema keys
    required = {"player", "stat", "side", "line", "odds", "book",
                "model_q50", "model_q10", "model_q90",
                "prob_model", "prob_implied", "edge_pp",
                "ev_per_unit", "kelly_full", "kelly_used", "stake_usd"}
    for b in payload["bets"]:
        missing = required - set(b)
        assert not missing, f"bet missing keys {missing}"
    # Sorted descending by EV
    evs = [b["ev_per_unit"] for b in payload["bets"]]
    assert evs == sorted(evs, reverse=True), "bets not sorted by EV desc"


def test_ranker_filters_min_edge():
    """Bets below min_edge_pct must be filtered out."""
    df = _fake_lines_df()
    huge_edge = wbr.rank_bets(df, season="2025", lookback=5, shrink=3.0,
                                min_edge_pct=-1e9, bankroll=1000.0)
    impossibly_high = wbr.rank_bets(df, season="2025", lookback=5, shrink=3.0,
                                      min_edge_pct=1e9, bankroll=1000.0)
    assert huge_edge["n_bets"] > 0
    assert impossibly_high["n_bets"] == 0
    # n_evaluated should be the same regardless of edge threshold
    assert huge_edge["n_evaluated"] == impossibly_high["n_evaluated"]


def test_model_hit_prob_sanity():
    """Probability monotonicity: higher line -> lower P(OVER)."""
    p_low = wbr.model_hit_prob(15.0, 20.0, 25.0, line=18.0, side="OVER")
    p_high = wbr.model_hit_prob(15.0, 20.0, 25.0, line=22.0, side="OVER")
    assert p_low > p_high
    # OVER + UNDER must sum to 1.0
    p_under = wbr.model_hit_prob(15.0, 20.0, 25.0, line=22.0, side="UNDER")
    assert (p_high + p_under) == pytest.approx(1.0, abs=1e-6)
