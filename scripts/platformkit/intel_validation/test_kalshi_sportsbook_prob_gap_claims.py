"""Per-file tests for kalshi_sportsbook_prob_gap_claims.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_kalshi_sportsbook_prob_gap_claims.py -q

Acceptance:
  1. stream_groups: last capture per book wins (shared helper w/ line_value_dispersion).
  2. aggregate_sport: groups without both a kalshi + non-kalshi quote are excluded.
  3. _discover_sports: dynamic, never hardcoded -- picks up whatever dirs exist.
  4. Golden asserts: widest abs-gap market ranks first.
  5. Validator VERIFIED end-to-end against the written snapshot parquet.
  6. edge_claimed False + forbidden-edge-token ban + "not a tradable signal".
  7. Empty-ranking honest skip: zero kalshi data -> build_all_claims returns [].

All fixtures are tiny synthetic tmp_path jsonl files (<100 rows) -- no real
data/ is read or written by this test.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import kalshi_sportsbook_prob_gap_claims as ksg

FLOOR = ksg.FLOOR_EVENTS


def _write_day_file(tmp_path, sport: str, date: str, rows: list[dict]):
    d = tmp_path / sport
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{date}.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def _row(game_id, market_type, side, line, book, prob):
    return {"sport": "mlb", "game_id": game_id, "home": "A", "away": "B",
            "market_type": market_type, "side": side, "line": line, "odds": None,
            "book": book, "devigged_prob": prob, "captured_at": "2026-07-16T00:00:00+00:00",
            "commence_time": "2026-07-16T12:00:00Z"}


def test_discover_sports_is_dynamic(tmp_path):
    (tmp_path / "mlb").mkdir()
    (tmp_path / "wnba").mkdir()
    (tmp_path / "not_a_dir.txt").write_text("x")
    assert ksg._discover_sports(tmp_path) == ["mlb", "wnba"]
    assert ksg._discover_sports(tmp_path / "missing") == []


def test_stream_groups_last_capture_per_book_wins(tmp_path):
    rows = [
        _row("g1", "moneyline", "home", None, "kalshi", 0.50),
        _row("g1", "moneyline", "home", None, "kalshi", 0.55),  # 2nd capture, same book
        _row("g1", "moneyline", "home", None, "pinnacle", 0.60),
    ]
    _write_day_file(tmp_path, "mlb", "2026-07-16", rows)
    groups = ksg.stream_groups("mlb", window_days=14, base_dir=tmp_path)
    g1 = groups[("g1", "moneyline", "home", None)]
    assert g1 == {"kalshi": 0.55, "pinnacle": 0.60}  # last kalshi capture wins


def test_aggregate_sport_excludes_groups_without_both_sides():
    groups = {
        ("g1", "moneyline", "home", None): {"kalshi": 0.60, "pinnacle": 0.50},  # comparable
        ("g2", "moneyline", "home", None): {"kalshi": 0.40},  # kalshi-only, excluded
        ("g3", "moneyline", "home", None): {"pinnacle": 0.40, "fanduel": 0.42},  # no kalshi, excluded
    }
    rows = ksg.aggregate_sport("mlb", groups)
    assert len(rows) == 1
    r = rows[0]
    assert r["n_events"] == 1  # only g1 counts
    assert pytest.approx(r["mean_gap"], abs=1e-9) == 0.10  # 0.60 - 0.50
    assert pytest.approx(r["mean_abs_gap"], abs=1e-9) == 0.10


def test_aggregate_sport_gap_is_kalshi_minus_book_mean():
    groups = {
        ("g1", "total", "over", 8.5): {"kalshi": 0.30, "pinnacle": 0.50, "fanduel": 0.46},
    }
    rows = ksg.aggregate_sport("mlb", groups)
    r = rows[0]
    # mean(non-kalshi) = 0.48, gap = 0.30 - 0.48 = -0.18
    assert pytest.approx(r["mean_gap"], abs=1e-9) == -0.18
    assert pytest.approx(r["mean_abs_gap"], abs=1e-9) == 0.18


def _build_snapshot_fixture(n_narrow: int, n_wide: int) -> pd.DataFrame:
    """narrow market: gap 0.02 every group. wide market: gap 0.30 every group
    (kalshi runs high). Both cleared of the n_events floor by caller args."""
    groups = {}
    for i in range(n_narrow):
        groups[(f"n{i}", "moneyline", "home", None)] = {"kalshi": 0.52, "pinnacle": 0.50}
    for i in range(n_wide):
        groups[(f"w{i}", "total", "over", 8.5)] = {"kalshi": 0.70, "pinnacle": 0.40}
    rows = ksg.aggregate_sport("mlb", groups)
    df = pd.DataFrame(rows, columns=["sport", "market_type", "n_events", "mean_gap", "mean_abs_gap"])
    df["entity_id"] = df["sport"] + "|" + df["market_type"]
    return df


def test_floor_excludes_below_floor_groups():
    snapshot = _build_snapshot_fixture(FLOOR + 5, FLOOR - 5)
    claim = ksg._build_ranking_claim(snapshot, "mean_abs_gap", "widest_abs_gap")
    ranked_markets = {r["entity_id"].split("|")[1] for r in claim["ranking"]}
    assert "moneyline" in ranked_markets  # n=FLOOR+5, clears
    assert "total" not in ranked_markets  # n=FLOOR-5, excluded
    assert claim["n_excluded_below_floor"] >= 1


def test_golden_widest_gap_ranks_first():
    snapshot = _build_snapshot_fixture(FLOOR + 5, FLOOR + 5)
    claim = ksg._build_ranking_claim(snapshot, "mean_abs_gap", "widest_abs_gap")
    assert claim["ranking"][0]["entity_id"] == "mlb|total"  # 0.30 >> 0.02


def test_empty_ranking_is_skipped_honestly():
    empty = pd.DataFrame(columns=["sport", "market_type", "n_events", "mean_gap",
                                   "mean_abs_gap", "entity_id"])
    assert ksg.build_all_claims(empty) == []


def test_validator_independently_reverifies(tmp_path, monkeypatch):
    snapshot = _build_snapshot_fixture(FLOOR + 5, FLOOR + 5)
    snap_path = tmp_path / "kalshi_sportsbook_prob_gap_snapshot.parquet"
    monkeypatch.setattr(ksg, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(ksg, "_SNAPSHOT_PATH", snap_path)
    ksg.write_snapshot(snapshot, snap_path)
    claim = ksg._build_ranking_claim(snapshot, "mean_abs_gap", "widest_abs_gap")

    import scripts.platformkit.intel_validation.claims_validator as cv_mod
    orig_root = cv_mod.REPO_ROOT
    cv_mod.REPO_ROOT = tmp_path
    try:
        verdict = claims_validator.validate_claim(claim)
    finally:
        cv_mod.REPO_ROOT = orig_root
    assert verdict.verdict == "VERIFIED", verdict.reason


_FORBIDDEN_TOKENS = ("edge", "roi", "$", "bankroll", "beat", "profit")


def test_honest_caveats_and_edge_claimed_false():
    snapshot = _build_snapshot_fixture(FLOOR + 5, FLOOR + 5)
    for claim in ksg.build_all_claims(snapshot):
        assert claim["edge_claimed"] is False
        blob = json.dumps([claim["caveats"], claim["question"]]).lower()
        negation_clause = "not an advantage, not a beatable gap, not a predictor -- no market/roi/dollar edge is claimed"
        stripped = blob.replace(negation_clause, "")
        for word in _FORBIDDEN_TOKENS:
            assert word not in stripped, f"forbidden token {word!r} found outside negation context"
        assert "not a tradable signal" in blob
        assert "not an advantage" in blob
        assert "not a predictor" in blob
