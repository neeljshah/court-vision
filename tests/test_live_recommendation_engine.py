"""tests/test_live_recommendation_engine.py — R23_P8.

End-to-end coverage of the live recommendation engine:
  * happy path with synthetic preds + lines → produces valid recs
  * missing predictions cache → empty list + reason (no crash)
  * OUT players are excluded
  * per-bet Kelly cap respected (every stake ≤ PER_BET_CAP * bankroll)
  * slate Kelly cap respected (sum of stakes ≤ SLATE_CAP * bankroll)
  * empty slate (no books) → empty list + reason (no crash)
  * all-OUT day → empty list + reason
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts import live_recommendation_engine as lre  # noqa: E402
from scripts.live_recommendation_engine import (  # noqa: E402
    PER_BET_CAP,
    SLATE_CAP,
    compute_recommendations,
    implied_prob,
    kelly_fraction,
    model_hit_prob_normal,
    run_engine,
)


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
DATE = "2099-01-15"  # synthetic, far-future to avoid clashes with real data


def _write_preds(dir_: str, rows: list[dict]) -> str:
    path = os.path.join(dir_, f"predictions_cache_{DATE}.parquet")
    df = pd.DataFrame(rows)
    df.to_parquet(path)
    return path


def _write_lines_csv(lines_dir: str, book: str, rows: list[dict]) -> str:
    os.makedirs(lines_dir, exist_ok=True)
    path = os.path.join(lines_dir, f"{DATE}_{book}.csv")
    cols = ["captured_at", "book", "game_id", "player_id", "player_name",
            "stat", "line", "over_price", "under_price", "start_time"]
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df[cols].to_csv(path, index=False)
    return path


def _write_injury(dir_: str, out_names: list[str]) -> str:
    path = os.path.join(dir_, f"nba_injuries_{DATE}.parquet")
    rows = [{
        "player_id": 1_000_000 + i,
        "player_name": name,
        "team": "XYZ",
        "status": "OUT",
        "availability_factor": 0.0,
        "reason": "synthetic",
        "source": "test",
        "fetched_at": "2099-01-15T12:00:00",
        "report_date": DATE,
    } for i, name in enumerate(out_names)]
    df = pd.DataFrame(rows)
    df.to_parquet(path)
    return path


def _mk_pred(player: str, stat: str, q50: float, q10: float, q90: float,
             team: str = "AAA") -> dict:
    return {
        "player_id": hash(player) % 10_000_000,
        "player_name": player,
        "team": team,
        "stat": stat,
        "q10": q10, "q50": q50, "q90": q90,
        "sigma": (q90 - q10) / (2 * 1.2816),
        "computed_at": "2099-01-15T12:00:00+00:00",
    }


def _mk_line(player: str, stat: str, line: float,
             over_price: int = -110, under_price: int = -110,
             book: str = "bov") -> dict:
    return {
        "captured_at": "2099-01-15T18:00:00",
        "book": book,
        "game_id": "synthetic",
        "player_id": "",
        "player_name": player,
        "stat": stat,
        "line": line,
        "over_price": over_price,
        "under_price": under_price,
        "start_time": "2099-01-15T20:00:00",
    }


@pytest.fixture
def tmp_dirs(tmp_path):
    """Provide isolated dirs for preds + lines + injury."""
    cache_dir = tmp_path / "cache"
    lines_dir = tmp_path / "lines"
    cache_dir.mkdir()
    lines_dir.mkdir()
    return {
        "cache": str(cache_dir),
        "lines": str(lines_dir),
    }


# --------------------------------------------------------------------------- #
# Test 1: missing predictions → empty list + reason                            #
# --------------------------------------------------------------------------- #
def test_missing_predictions_returns_empty_with_reason(tmp_dirs):
    out = run_engine(
        bankroll=1000.0, top=10, date=DATE,
        predictions_path=os.path.join(tmp_dirs["cache"], "does_not_exist.parquet"),
        lines_dir=tmp_dirs["lines"],
        injury_parquet_path=os.path.join(tmp_dirs["cache"], "no_inj.parquet"),
    )
    assert out["recommendations"] == []
    assert "missing" in out["reason"].lower() or "empty" in out["reason"].lower()
    assert out["n_predictions_available"] == 0


# --------------------------------------------------------------------------- #
# Test 2: empty slate (no books) → empty list + reason                         #
# --------------------------------------------------------------------------- #
def test_empty_slate_returns_empty_with_reason(tmp_dirs):
    _write_preds(tmp_dirs["cache"], [_mk_pred("Player A", "pts", 20.0, 15.0, 26.0)])
    out = run_engine(
        bankroll=1000.0, top=10, date=DATE,
        predictions_path=os.path.join(tmp_dirs["cache"], f"predictions_cache_{DATE}.parquet"),
        lines_dir=tmp_dirs["lines"],  # empty
        injury_parquet_path=os.path.join(tmp_dirs["cache"], "no_inj.parquet"),
    )
    assert out["recommendations"] == []
    assert "no book snapshots" in out["reason"].lower()


# --------------------------------------------------------------------------- #
# Test 3: OUT players excluded                                                 #
# --------------------------------------------------------------------------- #
def test_out_players_excluded(tmp_dirs):
    # Two players, identical predictions + lines (line 18.5 vs q50 22 → OVER edge).
    # OUT player must not appear in recs and must be counted in n_filtered_out.
    _write_preds(tmp_dirs["cache"], [
        _mk_pred("Healthy Hank", "pts", 22.0, 15.0, 29.0),
        _mk_pred("Injured Ian",  "pts", 22.0, 15.0, 29.0),
    ])
    _write_lines_csv(tmp_dirs["lines"], "bov", [
        _mk_line("Healthy Hank", "pts", 18.5, over_price=-110, under_price=-110),
        _mk_line("Injured Ian",  "pts", 18.5, over_price=-110, under_price=-110),
    ])
    _write_injury(tmp_dirs["cache"], ["Injured Ian"])
    out = run_engine(
        bankroll=1000.0, top=10, date=DATE, min_edge=0.01,
        predictions_path=os.path.join(tmp_dirs["cache"], f"predictions_cache_{DATE}.parquet"),
        lines_dir=tmp_dirs["lines"],
        injury_parquet_path=os.path.join(tmp_dirs["cache"], f"nba_injuries_{DATE}.parquet"),
    )
    names = {b["player"] for b in out["recommendations"]}
    assert "Injured Ian" not in names
    assert "Healthy Hank" in names
    # Each OUT row contributes one rejection (one row per player x stat).
    # 'Injured Ian' generates 2 sides * 1 line = should count multiple rejection events
    # at the inner-loop level. We only need >=1 to prove the filter fired.
    assert out["n_filtered_out"] >= 1


# --------------------------------------------------------------------------- #
# Test 4: all-OUT day → empty recommendations + reason                         #
# --------------------------------------------------------------------------- #
def test_all_out_day_produces_empty_list(tmp_dirs):
    _write_preds(tmp_dirs["cache"], [
        _mk_pred("Alice", "pts", 22.0, 15.0, 29.0),
        _mk_pred("Bob",   "reb", 8.0,  4.0,  12.0),
    ])
    _write_lines_csv(tmp_dirs["lines"], "bov", [
        _mk_line("Alice", "pts", 18.5),
        _mk_line("Bob",   "reb", 6.5),
    ])
    _write_injury(tmp_dirs["cache"], ["Alice", "Bob"])
    out = run_engine(
        bankroll=1000.0, top=10, date=DATE, min_edge=0.01,
        predictions_path=os.path.join(tmp_dirs["cache"], f"predictions_cache_{DATE}.parquet"),
        lines_dir=tmp_dirs["lines"],
        injury_parquet_path=os.path.join(tmp_dirs["cache"], f"nba_injuries_{DATE}.parquet"),
    )
    assert out["recommendations"] == []
    assert "no positive-edge" in out["reason"].lower() or out["n_recs"] == 0


# --------------------------------------------------------------------------- #
# Test 5: per-bet Kelly cap respected                                          #
# --------------------------------------------------------------------------- #
def test_per_bet_kelly_cap_respected(tmp_dirs):
    # Build an extreme-edge scenario: q50=30, line=10 → near-certain OVER.
    # Without the per-bet cap, raw Kelly would exceed 5% on a near-100% bet.
    _write_preds(tmp_dirs["cache"], [
        _mk_pred("Star", "pts", 30.0, 25.0, 35.0),
    ])
    _write_lines_csv(tmp_dirs["lines"], "bov", [
        _mk_line("Star", "pts", 10.5, over_price=-110, under_price=+100),
    ])
    out = run_engine(
        bankroll=1000.0, top=10, date=DATE, min_edge=0.01,
        predictions_path=os.path.join(tmp_dirs["cache"], f"predictions_cache_{DATE}.parquet"),
        lines_dir=tmp_dirs["lines"],
        injury_parquet_path=os.path.join(tmp_dirs["cache"], "no_inj.parquet"),
    )
    assert len(out["recommendations"]) >= 1
    for b in out["recommendations"]:
        # Allow the slate-cap multiplier to further shrink stakes; the
        # per-bet cap is the BEFORE-multiplier ceiling. After scaling the
        # post-cap stake must still be ≤ PER_BET_CAP * bankroll.
        assert b["stake_dollars"] <= PER_BET_CAP * 1000.0 + 1e-6, (
            f"per-bet cap violated: {b}"
        )


# --------------------------------------------------------------------------- #
# Test 6: slate Kelly cap respected                                            #
# --------------------------------------------------------------------------- #
def test_slate_kelly_cap_respected(tmp_dirs):
    # Generate many high-edge bets so per-bet sum would blow past 25%.
    pred_rows = [_mk_pred(f"P{i:02d}", "pts", 30.0, 25.0, 35.0) for i in range(30)]
    _write_preds(tmp_dirs["cache"], pred_rows)
    line_rows = [_mk_line(f"P{i:02d}", "pts", 10.5,
                          over_price=-110, under_price=+100)
                 for i in range(30)]
    _write_lines_csv(tmp_dirs["lines"], "bov", line_rows)
    out = run_engine(
        bankroll=1000.0, top=25, date=DATE, min_edge=0.01,
        predictions_path=os.path.join(tmp_dirs["cache"], f"predictions_cache_{DATE}.parquet"),
        lines_dir=tmp_dirs["lines"],
        injury_parquet_path=os.path.join(tmp_dirs["cache"], "no_inj.parquet"),
    )
    total_stake = sum(b["stake_dollars"] for b in out["recommendations"])
    cap = SLATE_CAP * 1000.0
    # Cap is honoured (allow tiny floating-point slack)
    assert total_stake <= cap + 1.0, (
        f"slate cap violated: ${total_stake:.2f} > ${cap:.2f}"
    )
    # When the cap kicks in, we must record at least one cap-scaled bet
    if total_stake >= cap - 1.0:
        assert out["n_filtered_kelly_cap"] >= 1


# --------------------------------------------------------------------------- #
# Test 7: happy path produces ranked recs sorted by edge                       #
# --------------------------------------------------------------------------- #
def test_happy_path_ranked_by_edge(tmp_dirs):
    _write_preds(tmp_dirs["cache"], [
        _mk_pred("Alpha", "pts", 25.0, 20.0, 30.0),  # very strong over
        _mk_pred("Bravo", "pts", 16.0, 11.0, 21.0),  # weaker over
    ])
    _write_lines_csv(tmp_dirs["lines"], "bov", [
        _mk_line("Alpha", "pts", 18.5, over_price=-110, under_price=-110),
        _mk_line("Bravo", "pts", 15.5, over_price=-110, under_price=-110),
    ])
    out = run_engine(
        bankroll=1000.0, top=10, date=DATE, min_edge=0.01,
        predictions_path=os.path.join(tmp_dirs["cache"], f"predictions_cache_{DATE}.parquet"),
        lines_dir=tmp_dirs["lines"],
        injury_parquet_path=os.path.join(tmp_dirs["cache"], "no_inj.parquet"),
    )
    recs = out["recommendations"]
    assert len(recs) >= 1
    # Sorted descending by edge
    edges = [r["edge"] for r in recs]
    assert edges == sorted(edges, reverse=True)
    # Alpha should beat Bravo (larger margin between q50 and line)
    names = [r["player"] for r in recs]
    if "Bravo" in names and "Alpha" in names:
        assert names.index("Alpha") < names.index("Bravo")


# --------------------------------------------------------------------------- #
# Test 8: exclude_books filter                                                 #
# --------------------------------------------------------------------------- #
def test_exclude_books(tmp_dirs):
    _write_preds(tmp_dirs["cache"], [_mk_pred("Alpha", "pts", 25.0, 20.0, 30.0)])
    _write_lines_csv(tmp_dirs["lines"], "bov", [
        _mk_line("Alpha", "pts", 18.5, over_price=-110, under_price=-110, book="bov"),
    ])
    _write_lines_csv(tmp_dirs["lines"], "fd", [
        _mk_line("Alpha", "pts", 18.5, over_price=-110, under_price=-110, book="fd"),
    ])
    out = run_engine(
        bankroll=1000.0, top=10, date=DATE, min_edge=0.01,
        exclude_books=["bov"],
        predictions_path=os.path.join(tmp_dirs["cache"], f"predictions_cache_{DATE}.parquet"),
        lines_dir=tmp_dirs["lines"],
        injury_parquet_path=os.path.join(tmp_dirs["cache"], "no_inj.parquet"),
    )
    assert "bov" not in out["books_loaded"]
    assert "fd" in out["books_loaded"]
    for r in out["recommendations"]:
        assert r["book"] != "bov"


# --------------------------------------------------------------------------- #
# Test 9: odds math sanity                                                     #
# --------------------------------------------------------------------------- #
def test_odds_math_basic():
    assert implied_prob(-110) == pytest.approx(110 / 210)
    assert implied_prob(+100) == pytest.approx(0.5)
    p = model_hit_prob_normal(point=20.0, q10=15.0, q90=25.0,
                               line=15.0, side="OVER")
    assert p is not None and 0.5 < p < 1.0
    # OVER + UNDER probabilities should sum to ~1 (since sigma > 0)
    p_under = model_hit_prob_normal(point=20.0, q10=15.0, q90=25.0,
                                     line=15.0, side="UNDER")
    assert p + p_under == pytest.approx(1.0, abs=1e-9)
    # Kelly is non-negative
    assert kelly_fraction(0.4, -110) == 0.0  # negative-EV → 0
    assert kelly_fraction(0.7, +100) > 0.0


# --------------------------------------------------------------------------- #
# Test 10: bankroll guard                                                      #
# --------------------------------------------------------------------------- #
def test_zero_bankroll_returns_empty():
    out = run_engine(bankroll=0.0, top=10, date=DATE)
    assert out["recommendations"] == []
    assert "bankroll" in out["reason"].lower()


# --------------------------------------------------------------------------- #
# Test 11: dashboard hook renders the new section                              #
# --------------------------------------------------------------------------- #
def test_dashboard_hook_renders_live_recs_section():
    """The R23_P8 operator_dashboard hook adds a 'What to bet right now'
    section when collect_and_render is called with include_live_recs=True.
    The section must render even when the engine returns no recs."""
    from scripts import operator_dashboard as od  # noqa: PLC0415
    # Render with engine but no real data → reason-only block, but the
    # header must be present.
    empty = {"ok": False}
    live_recs = {"ok": True, "recommendations": [], "reason": "test reason",
                 "n_filtered_out": 0, "n_filtered_kelly_cap": 0,
                 "total_stake_post_cap": 0.0, "slate_cap_dollars": 250.0}
    html = od.render_operator_html(
        empty, empty, empty, empty, empty, empty, live_recs,
        auto_refresh_sec=60,
    )
    assert od.LIVE_RECS_SECTION_TITLE in html
    assert "test reason" in html
