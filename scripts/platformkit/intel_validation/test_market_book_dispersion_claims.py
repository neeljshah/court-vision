"""Per-file tests for market_book_dispersion_claims (Depth-wave-2 Lane C).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_market_book_dispersion_claims.py -q

Acceptance:
  1. soccer_dispersion: correct |pinnacle - bet365| dispersion + tightening,
     both schemas exercised (soccer wide-format fixture + mlb single-book fixture).
  2. mlb_dispersion: honest empty-frame exclusion (single-book source), not fabricated.
  3. Aggregate + floor: below-floor (league, market) groups excluded and counted.
  4. Golden asserts: known most-dispersed / most-tightening group ranks first.
  5. Validator VERIFIED end-to-end against the written snapshot parquet.
  6. edge_claimed False + forbidden-edge-token ban (extends
     test_wnba_zone_context_claims.py:82-89 with edge/ROI/beat/profit/bankroll).
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import market_book_dispersion_claims as mbd

FLOOR = mbd.FLOOR_EVENTS


def _soccer_fixture(n_e1: int, n_sp1: int) -> pd.DataFrame:
    """E1: tight books (small, stable dispersion). SP1: wide + widening books
    (large dispersion that GROWS into the close -- positive tightening)."""
    rows = []
    rng = np.random.default_rng(0)
    for _ in range(n_e1):
        p, b = 2.00, 2.02  # dispersion_open = 0.02
        pc, bc = 2.00, 2.01  # dispersion_close = 0.01 -> tightening = -0.01
        rows.append(("E1", p, 3.80 - p, pc, 3.80 - pc, b, 3.80 - b, bc, 3.80 - bc))
    for _ in range(n_sp1):
        p, b = 2.00, 2.50  # dispersion_open = 0.50
        pc, bc = 2.00, 2.70  # dispersion_close = 0.70 -> tightening = +0.20 (widened)
        rows.append(("SP1", p, 3.80 - p, pc, 3.80 - pc, b, 3.80 - b, bc, 3.80 - bc))
    df = pd.DataFrame(rows, columns=["div", "p_over", "p_under", "pc_over", "pc_under",
                                      "b365_over", "b365_under", "b365c_over", "b365c_under"])
    return df


def test_soccer_dispersion_values_correct():
    df = _soccer_fixture(2, 2)
    long_df = mbd.soccer_dispersion(df)
    over = long_df[(long_df["league"] == "E1") & (long_df["market"] == "ou_over")]
    assert pytest.approx(over["dispersion_open"].iloc[0], abs=1e-9) == 0.02
    assert pytest.approx(over["dispersion_close"].iloc[0], abs=1e-9) == 0.01
    assert pytest.approx(over["consensus_tightening"].iloc[0], abs=1e-9) == -0.01
    sp1 = long_df[(long_df["league"] == "SP1") & (long_df["market"] == "ou_over")]
    assert pytest.approx(sp1["consensus_tightening"].iloc[0], abs=1e-9) == 0.20


def test_soccer_dispersion_drops_rows_missing_either_book():
    df = _soccer_fixture(1, 0)
    df.loc[0, "b365_over"] = np.nan
    long_df = mbd.soccer_dispersion(df)
    assert len(long_df[long_df["market"] == "ou_over"]) == 0  # dropped
    assert len(long_df[long_df["market"] == "ou_under"]) == 1  # unaffected


def test_mlb_dispersion_single_book_returns_empty():
    df = pd.DataFrame({"event_id": ["a", "b", "c"], "book": ["sbro_archive"] * 3})
    out = mbd.mlb_dispersion(df)
    assert out.empty
    assert list(out.columns) == ["league", "market", "dispersion_open", "dispersion_close",
                                  "consensus_tightening"]


def test_mlb_dispersion_raises_if_multibook_appears():
    df = pd.DataFrame({"event_id": ["a", "b"], "book": ["sbro_archive", "other_book"]})
    with pytest.raises(NotImplementedError):
        mbd.mlb_dispersion(df)


def test_aggregate_floor_excludes_below_floor_groups():
    df = _soccer_fixture(FLOOR + 5, FLOOR - 5)
    long_df = mbd.soccer_dispersion(df)
    snapshot = mbd._aggregate(long_df)
    claim = mbd._build_ranking_claim(snapshot, "dispersion_close_mean", "desc", "most_dispersed_close")
    ranked_leagues = {r["entity_id"].split("|")[0] for r in claim["ranking"]}
    assert "E1" in ranked_leagues  # n=FLOOR+5, clears
    assert "SP1" not in ranked_leagues  # n=FLOOR-5, excluded
    assert claim["n_excluded_below_floor"] >= 1


def test_golden_most_dispersed_and_most_tightening_rank_first():
    df = _soccer_fixture(FLOOR + 5, FLOOR + 5)
    long_df = mbd.soccer_dispersion(df)
    snapshot = mbd._aggregate(long_df)
    dispersion_claim = mbd._build_ranking_claim(snapshot, "dispersion_close_mean", "desc", "most_dispersed_close")
    assert dispersion_claim["ranking"][0]["entity_id"] == "SP1|ou_over"  # 0.70 close dispersion, widest
    tightening_claim = mbd._build_ranking_claim(snapshot, "consensus_tightening_mean", "asc", "most_tightening")
    assert tightening_claim["ranking"][0]["entity_id"].startswith("E1")  # -0.01, most negative = tightened most


def test_validator_independently_reverifies(tmp_path, monkeypatch):
    df = _soccer_fixture(FLOOR + 5, FLOOR + 5)
    long_df = mbd.soccer_dispersion(df)
    snapshot = mbd._aggregate(long_df)
    snap_path = tmp_path / "market_book_dispersion_snapshot.parquet"
    monkeypatch.setattr(mbd, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mbd, "_SNAPSHOT_PATH", snap_path)
    mbd.write_snapshot(snapshot, snap_path)
    claim = mbd._build_ranking_claim(snapshot, "dispersion_close_mean", "desc", "most_dispersed_close")

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
    df = _soccer_fixture(FLOOR + 5, FLOOR + 5)
    long_df = mbd.soccer_dispersion(df)
    snapshot = mbd._aggregate(long_df)
    for claim in mbd.build_all_claims(snapshot):
        assert claim["edge_claimed"] is False
        blob = json.dumps([claim["caveats"], claim["question"]]).lower()
        # "no market/roi/dollar edge is claimed" / "not an advantage" is an
        # explicit NEGATION of these tokens -- allow them only inside that
        # fixed negation clause, ban them everywhere else in the blob.
        negation_clause = "not an advantage, not a beatable gap, not a predictor -- no market/roi/dollar edge is claimed"
        stripped = blob.replace(negation_clause, "")
        for word in _FORBIDDEN_TOKENS:
            assert word not in stripped, f"forbidden token {word!r} found outside negation context"
        assert "not an advantage" in blob
        assert "not a predictor" in blob
        assert "structure" in blob
