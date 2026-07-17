"""Per-file tests for line_value_dispersion_claims.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_line_value_dispersion_claims.py -q

Acceptance:
  1. stream_groups: last capture per book wins; single-book groups carry 1 key.
  2. aggregate_sport: single-book groups excluded from dispersion entirely.
  3. window_days caps files read (never a full-directory load).
  4. Golden asserts: widely-dispersed market ranks first for both metrics.
  5. Validator VERIFIED end-to-end against the written snapshot parquet.
  6. edge_claimed False + forbidden-edge-token ban + "not a tradable signal".

All fixtures are tiny synthetic tmp_path jsonl files (<100 rows) -- no real
data/ is read or written by this test.
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import line_value_dispersion_claims as lvd

FLOOR = lvd.FLOOR_EVENTS


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


def test_stream_groups_last_capture_per_book_wins(tmp_path):
    rows = [
        _row("g1", "moneyline", "home", None, "pinnacle", 0.50),
        _row("g1", "moneyline", "home", None, "pinnacle", 0.55),  # 2nd capture, same book
        _row("g1", "moneyline", "home", None, "kalshi", 0.60),
        _row("g2", "moneyline", "home", None, "pinnacle", 0.40),  # single-book group
    ]
    _write_day_file(tmp_path, "mlb", "2026-07-16", rows)
    groups = lvd.stream_groups("mlb", window_days=14, base_dir=tmp_path)
    g1 = groups[("g1", "moneyline", "home", None)]
    assert g1 == {"pinnacle": 0.55, "kalshi": 0.60}  # last pinnacle capture wins
    g2 = groups[("g2", "moneyline", "home", None)]
    assert len(g2) == 1


def test_aggregate_sport_excludes_single_book_groups():
    groups = {
        ("g1", "moneyline", "home", None): {"pinnacle": 0.50, "kalshi": 0.60},
        ("g2", "moneyline", "home", None): {"pinnacle": 0.40},  # single-book, excluded
    }
    rows = lvd.aggregate_sport("mlb", groups)
    assert len(rows) == 1
    r = rows[0]
    assert r["n_events"] == 1  # only g1 counts
    assert r["n_books_mean"] == 2.0
    assert pytest.approx(r["median_prob_dispersion"], abs=1e-9) == 0.10
    assert pytest.approx(r["p90_prob_dispersion"], abs=1e-9) == 0.10


def test_window_days_caps_files_read(tmp_path):
    for i in range(1, 21):
        date = f"2026-07-{i:02d}"
        _write_day_file(tmp_path, "mlb", date, [_row(f"g{i}", "moneyline", "home", None, "pinnacle", 0.5)])
    files = lvd._recent_day_files("mlb", window_days=5, base_dir=tmp_path)
    assert len(files) == 5
    assert [p.stem for p in files] == ["2026-07-16", "2026-07-17", "2026-07-18", "2026-07-19", "2026-07-20"]


def _build_snapshot_fixture(n_narrow: int, n_wide: int) -> "pd.DataFrame":  # noqa: F821
    """narrow market: dispersion 0.02 every group. wide market: dispersion
    0.30 every group. Both cleared of the n_events floor by caller args."""
    groups = {}
    for i in range(n_narrow):
        groups[(f"n{i}", "moneyline", "home", None)] = {"pinnacle": 0.50, "kalshi": 0.52}
    for i in range(n_wide):
        groups[(f"w{i}", "total", "over", 8.5)] = {"pinnacle": 0.40, "kalshi": 0.70}
    rows = lvd.aggregate_sport("mlb", groups)
    import pandas as pd
    df = pd.DataFrame(rows, columns=["sport", "market_type", "n_events", "n_books_mean",
                                      "median_prob_dispersion", "p90_prob_dispersion"])
    df["entity_id"] = df["sport"] + "|" + df["market_type"]
    return df


def test_aggregate_floor_excludes_below_floor_groups():
    snapshot = _build_snapshot_fixture(FLOOR + 5, FLOOR - 5)
    claim = lvd._build_ranking_claim(snapshot, "median_prob_dispersion", "median_dispersion")
    ranked_markets = {r["entity_id"].split("|")[1] for r in claim["ranking"]}
    assert "moneyline" in ranked_markets  # n=FLOOR+5, clears
    assert "total" not in ranked_markets  # n=FLOOR-5, excluded
    assert claim["n_excluded_below_floor"] >= 1


def test_golden_widest_dispersion_ranks_first():
    snapshot = _build_snapshot_fixture(FLOOR + 5, FLOOR + 5)
    median_claim = lvd._build_ranking_claim(snapshot, "median_prob_dispersion", "median_dispersion")
    assert median_claim["ranking"][0]["entity_id"] == "mlb|total"  # 0.30 >> 0.02
    p90_claim = lvd._build_ranking_claim(snapshot, "p90_prob_dispersion", "p90_dispersion")
    assert p90_claim["ranking"][0]["entity_id"] == "mlb|total"


def test_validator_independently_reverifies(tmp_path, monkeypatch):
    snapshot = _build_snapshot_fixture(FLOOR + 5, FLOOR + 5)
    snap_path = tmp_path / "line_value_dispersion_snapshot.parquet"
    monkeypatch.setattr(lvd, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(lvd, "_SNAPSHOT_PATH", snap_path)
    lvd.write_snapshot(snapshot, snap_path)
    claim = lvd._build_ranking_claim(snapshot, "median_prob_dispersion", "median_dispersion")

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
    for claim in lvd.build_all_claims(snapshot):
        assert claim["edge_claimed"] is False
        blob = json.dumps([claim["caveats"], claim["question"]]).lower()
        negation_clause = "not an advantage, not a beatable gap, not a predictor -- no market/roi/dollar edge is claimed"
        stripped = blob.replace(negation_clause, "")
        for word in _FORBIDDEN_TOKENS:
            assert word not in stripped, f"forbidden token {word!r} found outside negation context"
        assert "not a tradable signal" in blob
        assert "not an advantage" in blob
        assert "not a predictor" in blob
        assert "tennis excluded" in blob
