"""Per-file tests for line_history_consensus_claims (Depth-wave-3 final lane).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_line_history_consensus_claims.py -q

Acceptance:
  1. stream_groups: streams day-files line-by-line, groups by
     (game_id, market_type, side, line), accumulates n_books + odds spread.
  2. aggregate_sport: coverage_breadth over ALL groups, consensus_tightness
     over multi-book groups only (single-book groups excluded from tightness).
  3. Aggregate + floor: below-floor (sport, market_type) groups excluded.
  4. Golden asserts: known widest-coverage / tightest-consensus group ranks first.
  5. Validator VERIFIED end-to-end against the written snapshot parquet.
  6. edge_claimed False + forbidden-edge-token ban.
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import line_history_consensus_claims as lhc

FLOOR = lhc.FLOOR_EVENTS


def _write_day_file(tmp_path, sport: str, date: str, rows: list[dict]):
    d = tmp_path / sport
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{date}.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def _row(game_id, market_type, side, line, book, odds):
    return {"sport": "soccer", "game_id": game_id, "home": "A", "away": "B",
            "market_type": market_type, "side": side, "line": line, "odds": odds,
            "book": book, "devigged_prob": None, "captured_at": "2026-07-16T00:00:00+00:00",
            "commence_time": "2026-07-16T12:00:00Z"}


def test_stream_groups_accumulates_books_and_odds_range(tmp_path):
    rows = [
        _row("g1", "moneyline", "home", None, "pinnacle", 2.00),
        _row("g1", "moneyline", "home", None, "espn:DraftKings", 2.10),
        _row("g2", "moneyline", "home", None, "pinnacle", 1.50),  # single-book group
    ]
    _write_day_file(tmp_path, "soccer", "2026-07-16", rows)
    groups = lhc.stream_groups("soccer", window_days=14, base_dir=tmp_path)
    g1 = groups[("g1", "moneyline", "home", None)]
    assert g1["books"] == {"pinnacle", "espn:DraftKings"}
    assert g1["min_odds"] == 2.00 and g1["max_odds"] == 2.10
    g2 = groups[("g2", "moneyline", "home", None)]
    assert len(g2["books"]) == 1


def test_aggregate_sport_tightness_excludes_single_book_groups():
    groups = {
        ("g1", "moneyline", "home", None): {"books": {"pinnacle", "espn:DraftKings"}, "min_odds": 2.00, "max_odds": 2.10},
        ("g2", "moneyline", "home", None): {"books": {"pinnacle"}, "min_odds": 1.50, "max_odds": 1.50},
    }
    rows = lhc.aggregate_sport("soccer", groups)
    assert len(rows) == 1
    r = rows[0]
    assert r["n_events"] == 2
    assert r["n_multibook_events"] == 1
    assert pytest.approx(r["coverage_breadth_mean"], abs=1e-9) == 1.5  # (2+1)/2
    assert pytest.approx(r["consensus_tightness_mean"], abs=1e-9) == 0.10  # only g1 counts


def test_window_days_caps_files_read(tmp_path):
    for i in range(1, 21):
        date = f"2026-07-{i:02d}"
        _write_day_file(tmp_path, "soccer", date, [_row(f"g{i}", "moneyline", "home", None, "pinnacle", 2.0)])
    files = lhc._recent_day_files("soccer", window_days=5, base_dir=tmp_path)
    assert len(files) == 5
    assert [p.stem for p in files] == ["2026-07-16", "2026-07-17", "2026-07-18", "2026-07-19", "2026-07-20"]


def _build_snapshot_fixture(n_wide_multibook: int, n_tight_multibook: int, extra_single: int = 0) -> "pd.DataFrame":  # noqa: F821
    groups = {}
    for i in range(n_wide_multibook):
        groups[(f"wide{i}", "moneyline", "home", None)] = {
            "books": {"pinnacle", "espn:DraftKings"}, "min_odds": 2.00, "max_odds": 2.50}  # spread 0.50
    for i in range(n_tight_multibook):
        groups[(f"tight{i}", "totals", "over", 2.5)] = {
            "books": {"pinnacle", "espn:DraftKings"}, "min_odds": 2.00, "max_odds": 2.02}  # spread 0.02
    for i in range(extra_single):
        groups[(f"single{i}", "spread", "home", -1.5)] = {"books": {"pinnacle"}, "min_odds": 1.9, "max_odds": 1.9}
    rows = lhc.aggregate_sport("soccer", groups)
    import pandas as pd
    df = pd.DataFrame(rows, columns=["sport", "market_type", "n_events", "n_multibook_events",
                                      "coverage_breadth_mean", "consensus_tightness_mean"])
    df["entity_id"] = df["sport"] + "|" + df["market_type"]
    return df


def test_aggregate_floor_excludes_below_floor_groups():
    snapshot = _build_snapshot_fixture(FLOOR + 5, FLOOR - 5)
    claim = lhc._build_ranking_claim(snapshot, "consensus_tightness_mean", "n_multibook_events", "asc", "tightest_consensus")
    ranked_markets = {r["entity_id"].split("|")[1] for r in claim["ranking"]}
    assert "moneyline" in ranked_markets  # n=FLOOR+5, clears
    assert "totals" not in ranked_markets  # n=FLOOR-5, excluded
    assert claim["n_excluded_below_floor"] >= 1


def test_golden_widest_coverage_and_tightest_consensus_rank_first():
    snapshot = _build_snapshot_fixture(FLOOR + 5, FLOOR + 5)
    breadth_claim = lhc._build_ranking_claim(snapshot, "coverage_breadth_mean", "n_events", "desc", "coverage_breadth")
    assert breadth_claim["ranking"][0]["value"] == 2.0  # both groups are all-multibook here
    tightness_claim = lhc._build_ranking_claim(snapshot, "consensus_tightness_mean", "n_multibook_events", "asc", "tightest_consensus")
    assert tightness_claim["ranking"][0]["entity_id"] == "soccer|totals"  # spread 0.02, tightest


def test_validator_independently_reverifies(tmp_path, monkeypatch):
    snapshot = _build_snapshot_fixture(FLOOR + 5, FLOOR + 5)
    snap_path = tmp_path / "line_history_consensus_snapshot.parquet"
    monkeypatch.setattr(lhc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(lhc, "_SNAPSHOT_PATH", snap_path)
    lhc.write_snapshot(snapshot, snap_path)
    claim = lhc._build_ranking_claim(snapshot, "coverage_breadth_mean", "n_events", "desc", "coverage_breadth")

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
    for claim in lhc.build_all_claims(snapshot):
        assert claim["edge_claimed"] is False
        blob = json.dumps([claim["caveats"], claim["question"]]).lower()
        negation_clause = "not an advantage, not a beatable gap, not a predictor -- no market/roi/dollar edge is claimed"
        stripped = blob.replace(negation_clause, "")
        for word in _FORBIDDEN_TOKENS:
            assert word not in stripped, f"forbidden token {word!r} found outside negation context"
        assert "not an advantage" in blob
        assert "not a predictor" in blob
        assert "tennis excluded" in blob
