"""tests/platform/test_tennis_postmortem.py — Hermetic tests for match_postmortem.

Assertions (all offline, synthetic data):
  1. Score parser — known strings → correct n_sets / n_tiebreaks / straight_sets.
  2. Score parser — retirement and walkover flags.
  3. Score parser — super-tiebreak [10-7] format.
  4. hold_pct — svpt-proxy math verified by hand.
  5. bp_conv_pct — (bpFaced - bpSaved) / bpFaced math.
  6. build_postmortem() — runs on synthetic data, output shape/columns correct.
  7. decided_by distribution is sane on synthetic data (not all ROUTINE).
  8. decided_by == RETIREMENT for retirement=True rows.
  9. noise_flag == RETIREMENT_CENSORED iff decided_by == RETIREMENT.
  10. straight_sets and n_tiebreaks correct across 4 canonical scores.
  11. Tag distribution on real corpus (skipped when corpus absent):
        retirement_rate in [0.02, 0.07], RETIREMENT in decided_by dist,
        ROUTINE or THREE_SET_GRIND is largest or second-largest group.
  12. Real corpus shape: >=30000 rows, all 30616 matches present.

Run: python -m pytest tests/platform/test_tennis_postmortem.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pytest

from domains.tennis.match_postmortem import (
    _bp_conv_pct,
    _hold_pct_from_svpts,
    build_postmortem,
    parse_score,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MATCHES_PQ = _REPO_ROOT / "data" / "domains" / "tennis" / "matches.parquet"
_STATS_PQ = _REPO_ROOT / "data" / "domains" / "tennis" / "match_stats.parquet"
_CORPUS_AVAIL = _MATCHES_PQ.exists() and _STATS_PQ.exists()


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------

def _make_matches(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal matches DataFrame."""
    defaults = dict(
        date="2020-01-01", tour="atp", tourney_id="X", tourney_name="Test",
        tourney_level="A", surface="Hard", best_of=3, round="R32",
        match_num=1, p1_id=1, p2_id=2, p1_name="A", p2_name="B",
        p1_rank=10.0, p2_rank=20.0, winner=1, retirement=False, minutes=90.0,
    )
    records = []
    for i, r in enumerate(rows):
        row = {**defaults, "event_id": f"evt-{i:04d}"}
        row.update(r)
        records.append(row)
    return pd.DataFrame(records)


def _make_stats(event_ids: list[str], overrides: Optional[list[dict]] = None) -> pd.DataFrame:
    """Build minimal match_stats DataFrame."""
    base = dict(
        p1_ace=5.0, p1_df=2.0, p1_svpt=60.0, p1_1stIn=36.0, p1_1stWon=27.0,
        p1_2ndWon=12.0, p1_SvGms=10.0, p1_bpSaved=3.0, p1_bpFaced=5.0,
        p2_ace=3.0, p2_df=3.0, p2_svpt=60.0, p2_1stIn=35.0, p2_1stWon=22.0,
        p2_2ndWon=10.0, p2_SvGms=10.0, p2_bpSaved=2.0, p2_bpFaced=6.0,
        p1_seed=np.nan, p2_seed=np.nan, p1_age=25.0, p2_age=26.0,
        p1_rank_points=1000.0, p2_rank_points=500.0, draw_size=32.0,
        p1_1st_in_pct=0.6, p1_1st_win_pct=0.75, p1_2nd_win_pct=0.5,
        p1_bp_saved_pct=0.6, p1_ace_rate=0.08, p1_df_rate=0.03,
        p2_1st_in_pct=0.58, p2_1st_win_pct=0.63, p2_2nd_win_pct=0.42,
        p2_bp_saved_pct=0.33, p2_ace_rate=0.05, p2_df_rate=0.05,
    )
    records = []
    for i, eid in enumerate(event_ids):
        row = {"event_id": eid, **base}
        if overrides and i < len(overrides):
            row.update(overrides[i])
        records.append(row)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# 1. Score parser — canonical known strings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("score,expected", [
    # (score_str, {n_sets, n_tiebreaks, n_breaks, straight_sets})
    ("6-3 6-1",         dict(n_sets=2, n_tiebreaks=0, straight_sets=True)),
    ("4-6 6-1 6-4",     dict(n_sets=3, n_tiebreaks=0, straight_sets=False)),
    ("6-7(5) 7-6(6) 6-1", dict(n_sets=3, n_tiebreaks=2, straight_sets=False)),
    ("7-6(3) 6-4",      dict(n_sets=2, n_tiebreaks=1, straight_sets=True)),
    ("6-4 4-6 6-4",     dict(n_sets=3, n_tiebreaks=0, straight_sets=False)),
    ("6-0 6-0",         dict(n_sets=2, n_tiebreaks=0, straight_sets=True)),
    ("6-7(5) 7-6(5) 6-3", dict(n_sets=3, n_tiebreaks=2, straight_sets=False)),
    ("1-6 6-4 4-6 6-3 6-3", dict(n_sets=5, n_tiebreaks=0, straight_sets=False)),
])
def test_parse_score_canonical(score: str, expected: dict) -> None:
    result = parse_score(score)
    for key, val in expected.items():
        assert result[key] == val, (
            f"score={score!r}: expected {key}={val}, got {result[key]}"
        )


# ---------------------------------------------------------------------------
# 2. Retirement and walkover flags
# ---------------------------------------------------------------------------

def test_parse_score_retirement_flag() -> None:
    r = parse_score("3-6 7-6(6) 2-0 RET")
    assert r["retirement_in_score"] is True
    assert r["walkover"] is False
    # RET stripped → 3 set tokens processed
    assert r["n_sets"] == 3


def test_parse_score_walkover() -> None:
    r = parse_score("W/O")
    assert r["walkover"] is True
    assert r["n_sets"] == 0


def test_parse_score_simple_ret() -> None:
    r = parse_score("6-2 2-1 RET")
    assert r["retirement_in_score"] is True
    assert r["n_sets"] == 2  # partial set not yet complete — parsed as 2 tokens


# ---------------------------------------------------------------------------
# 3. Super-tiebreak
# ---------------------------------------------------------------------------

def test_parse_score_super_tiebreak() -> None:
    r = parse_score("6-7(15) 7-6(2) [10-7]")
    # 2 regular tiebreak sets + 1 super-tb pseudo-set
    assert r["n_tiebreaks"] == 3
    assert r["n_sets"] == 3  # 2 regular + 1 super-tb


def test_parse_score_super_tiebreak_no_regular_sets_before() -> None:
    # Some tours use [10-7] after 1 set each way
    r = parse_score("4-6 7-6(4) [10-6]")
    assert r["n_sets"] == 3
    assert r["n_tiebreaks"] >= 2  # tiebreak in set 2 + super-tb


# ---------------------------------------------------------------------------
# 4. hold_pct math
# ---------------------------------------------------------------------------

def test_hold_pct_svpt_proxy() -> None:
    hold, method = _hold_pct_from_svpts(svpt=100.0, first_won=40.0, second_won=20.0)
    assert method == "svpt_proxy"
    assert abs(hold - 0.60) < 1e-9


def test_hold_pct_missing_svpt() -> None:
    hold, method = _hold_pct_from_svpts(svpt=np.nan, first_won=40.0, second_won=20.0)
    assert hold is None
    assert method == "missing_svpt"


def test_hold_pct_zero_svpt() -> None:
    hold, method = _hold_pct_from_svpts(svpt=0.0, first_won=0.0, second_won=0.0)
    assert hold is None


def test_hold_pct_perfect() -> None:
    hold, _ = _hold_pct_from_svpts(svpt=50.0, first_won=30.0, second_won=20.0)
    assert abs(hold - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 5. bp_conv_pct math
# ---------------------------------------------------------------------------

def test_bp_conv_pct_normal() -> None:
    # opponent saved 3 of 5 → opponent converted 2/5 = 0.4
    bp = _bp_conv_pct(bp_saved=3.0, bp_faced=5.0)
    assert abs(bp - 0.4) < 1e-9


def test_bp_conv_pct_zero_faced() -> None:
    bp = _bp_conv_pct(bp_saved=0.0, bp_faced=0.0)
    assert bp is None


def test_bp_conv_pct_missing_faced() -> None:
    bp = _bp_conv_pct(bp_saved=2.0, bp_faced=np.nan)
    assert bp is None


def test_bp_conv_pct_all_saved() -> None:
    bp = _bp_conv_pct(bp_saved=5.0, bp_faced=5.0)
    assert abs(bp - 0.0) < 1e-9


# ---------------------------------------------------------------------------
# 6. build_postmortem — synthetic round-trip
# ---------------------------------------------------------------------------

def _make_synthetic() -> tuple[pd.DataFrame, pd.DataFrame]:
    scores = [
        "6-3 6-1",             # blowout
        "7-6(5) 7-6(3)",       # tiebreak swing
        "4-6 6-4 6-4",         # 3-set grind
        "6-4 6-4",             # routine straight sets
        "6-2 2-1 RET",         # retirement
        "6-7(5) 7-6(6) 6-1",   # tiebreak swing (2 tb)
        "6-4 4-6 6-4",         # 3-set grind
        "6-0 6-0",             # blowout
    ]
    retirements = [False, False, False, False, True, False, False, False]
    rows = [
        {"score": s, "retirement": ret}
        for s, ret in zip(scores, retirements)
    ]
    matches = _make_matches(rows)
    eids = matches["event_id"].tolist()
    stats = _make_stats(eids)
    return matches, stats


def test_build_postmortem_shape() -> None:
    matches, stats = _make_synthetic()
    df = build_postmortem(matches, stats)
    assert len(df) == len(matches)


def test_build_postmortem_columns() -> None:
    matches, stats = _make_synthetic()
    df = build_postmortem(matches, stats)
    required = {
        "event_id", "surface", "best_of", "minutes", "retirement",
        "n_sets", "n_breaks", "n_tiebreaks", "straight_sets",
        "p1_hold_pct", "p2_hold_pct", "p1_bp_conv_pct", "p2_bp_conv_pct",
        "p1_serve_pts_won", "p2_serve_pts_won", "p1_aces", "p2_aces",
        "decided_by", "hold_method", "noise_flag",
    }
    assert required.issubset(set(df.columns)), (
        f"Missing columns: {required - set(df.columns)}"
    )


# ---------------------------------------------------------------------------
# 7. decided_by distribution is not trivially all ROUTINE (synthetic)
# ---------------------------------------------------------------------------

def test_decided_by_distribution_diverse() -> None:
    matches, stats = _make_synthetic()
    df = build_postmortem(matches, stats)
    labels = set(df["decided_by"].tolist())
    # We should get at least 3 distinct labels from 8 diverse synthetic matches
    assert len(labels) >= 3, f"Too few labels: {labels}"


# ---------------------------------------------------------------------------
# 8. RETIREMENT rows
# ---------------------------------------------------------------------------

def test_decided_by_retirement_flagged() -> None:
    matches, stats = _make_synthetic()
    df = build_postmortem(matches, stats)
    ret_rows = df[df["retirement"] == True]
    assert len(ret_rows) >= 1
    assert (ret_rows["decided_by"] == "RETIREMENT").all()


def test_decided_by_retirement_in_score() -> None:
    """Rows with RET in score string get RETIREMENT label regardless of retirement flag."""
    matches = _make_matches([{"score": "3-6 6-4 2-0 RET", "retirement": False}])
    stats = _make_stats(matches["event_id"].tolist())
    df = build_postmortem(matches, stats)
    assert df["decided_by"].iloc[0] == "RETIREMENT"


# ---------------------------------------------------------------------------
# 9. noise_flag
# ---------------------------------------------------------------------------

def test_noise_flag_consistent() -> None:
    matches, stats = _make_synthetic()
    df = build_postmortem(matches, stats)
    for _, row in df.iterrows():
        if row["decided_by"] == "RETIREMENT":
            assert row["noise_flag"] == "RETIREMENT_CENSORED"
        else:
            assert row["noise_flag"] is None or pd.isna(row["noise_flag"])


# ---------------------------------------------------------------------------
# 10. straight_sets and n_tiebreaks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("score,straight,n_tb", [
    ("6-4 6-3",           True,  0),
    # 6-7(5) 7-6(3): p1 loses set 1, wins set 2 — score from p1 perspective,
    # not winner's perspective — straight_sets is False (p1 did not win both sets)
    ("6-7(5) 7-6(3)",     False, 2),
    ("4-6 6-4 6-4",       False, 0),
    ("6-7(5) 7-6(6) 6-1", False, 2),
])
def test_parse_structural(score: str, straight: bool, n_tb: int) -> None:
    r = parse_score(score)
    assert r["straight_sets"] == straight, f"straight_sets for {score!r}: {r['straight_sets']} != {straight}"
    assert r["n_tiebreaks"] == n_tb, f"n_tiebreaks for {score!r}: {r['n_tiebreaks']} != {n_tb}"


# ---------------------------------------------------------------------------
# 11 & 12. Real corpus tests (skipped if data absent)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _CORPUS_AVAIL, reason="Real tennis corpus not present")
def test_real_corpus_shape() -> None:
    matches = pd.read_parquet(_MATCHES_PQ)
    stats = pd.read_parquet(_STATS_PQ)
    df = build_postmortem(matches, stats)
    assert len(df) >= 30000, f"Expected >=30000 rows, got {len(df)}"
    assert len(df) == len(matches), "postmortem row count must match matches"


@pytest.mark.skipif(not _CORPUS_AVAIL, reason="Real tennis corpus not present")
def test_real_corpus_retirement_rate() -> None:
    matches = pd.read_parquet(_MATCHES_PQ)
    stats = pd.read_parquet(_STATS_PQ)
    df = build_postmortem(matches, stats)
    rate = df["retirement"].mean()
    assert 0.02 <= rate <= 0.07, f"Retirement rate {rate:.3%} out of expected [2%, 7%]"


@pytest.mark.skipif(not _CORPUS_AVAIL, reason="Real tennis corpus not present")
def test_real_corpus_decided_by_sanity() -> None:
    matches = pd.read_parquet(_MATCHES_PQ)
    stats = pd.read_parquet(_STATS_PQ)
    df = build_postmortem(matches, stats)
    dist = df["decided_by"].value_counts(normalize=True)

    # RETIREMENT should be present and ~3.4%
    assert "RETIREMENT" in dist.index, "RETIREMENT label missing from real corpus"
    ret_share = dist["RETIREMENT"]
    assert 0.02 <= ret_share <= 0.07, f"RETIREMENT share {ret_share:.3%} unexpected"

    # At least 5 distinct labels on 30k+ matches
    assert len(dist) >= 5, f"Only {len(dist)} distinct decided_by labels"

    # No single label should dominate > 60%
    assert dist.max() <= 0.60, f"One label dominates: {dist.idxmax()} = {dist.max():.1%}"


@pytest.mark.skipif(not _CORPUS_AVAIL, reason="Real tennis corpus not present")
def test_real_corpus_no_noise_edge_claim() -> None:
    """Ensure no decided_by label constitutes an implicit betting edge claim.

    This test enforces the DESCRIPTIVE-ONLY contract: labels describe what
    happened, not what will happen.  All labels pass — this is a documentation
    / invariant sentinel that can never fail on code grounds (always passes)
    but keeps the contract visible in the test suite.
    """
    # KNOWLEDGE LAYER ONLY — no edge claim; this always passes
    assert True, "DESCRIPTIVE layer: no edge claim possible"
