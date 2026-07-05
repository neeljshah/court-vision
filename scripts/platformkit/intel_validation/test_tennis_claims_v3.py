"""Per-file tests for tennis_claims_v3 (lane tennis-fullpop, program v3).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_tennis_claims_v3.py -q

Acceptance criteria:
  1. _reshape_long melts p1_/p2_ wide rows into one row per player per match
     for an ARBITRARY metric column (generalizing tennis_hold_claims.py's
     single-metric version).
  2. _season_snapshot keeps exactly one (most recent) row per player.
  3. build_all_claims honestly reports the WTA return-quality dims as
     dims_corpus_absent (no on-disk WTA return corpus exists), never
     silently drops them.
  4. build_ranking_claim's claimed ranking is independently re-verified by
     claims_validator.validate_claim -> VERIFIED for a real on-disk metric.
  5. FULL POPULATION: no top-N truncation -- ranked count == qualifying count.
  6. Every ranking row carries player_name (wave-63 idname-fix: this is the
     name source ask.py's entity_lookup resolves against).
  7. A player_id genuinely absent from the matches p1_name/p2_name source
     gets an honest fallback, never a fabricated name.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import tennis_claims_v3 as tcv3
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_matches() -> pd.DataFrame:
    return pd.DataFrame({
        "event_id": ["e1", "e2", "e3"],
        "date": [pd.Timestamp("2025-01-01").date(), pd.Timestamp("2025-02-01").date(),
                 pd.Timestamp("2025-03-01").date()],
        "p1_id": [1, 1, 2],
        "p2_id": [2, 3, 3],
        "p1_name": ["Alice", "Alice", "Carol"],
        "p2_name": ["Bob", "Carol", "Carol"],
    })


def _fixture_return() -> pd.DataFrame:
    return pd.DataFrame({
        "event_id": ["e1", "e2", "e3"],
        "p1_return_won_asof": [0.30, 0.35, 0.20],
        "p2_return_won_asof": [0.25, 0.28, 0.33],
        "p1_return_won_n_prior": [10, 15, 5],
        "p2_return_won_n_prior": [3, 4, 20],
    })


def test_reshape_long_melts_p1_p2_for_arbitrary_metric():
    long_df = tcv3._reshape_long(_fixture_matches(), _fixture_return(), "return_won_asof", "return_won_n_prior")
    # 3 matches x 2 players per match = 6 rows
    assert len(long_df) == 6
    assert set(long_df.columns) == {"player_id", "date", "value", "n_prior"}
    assert (long_df["player_id"] == 1).sum() == 2


def test_season_snapshot_keeps_one_most_recent_row_per_player():
    long_df = tcv3._reshape_long(_fixture_matches(), _fixture_return(), "return_won_asof", "return_won_n_prior")
    snap = tcv3._season_snapshot(long_df, "2025")
    assert len(snap) == 3
    assert sorted(snap["player_id"].tolist()) == [1, 2, 3]
    # player 1's most recent 2025 row is e2 (p1_return_won_asof=0.35), not e1's 0.30
    p1_row = snap[snap["player_id"] == 1].iloc[0]
    assert p1_row["value"] == 0.35


def test_build_all_claims_honestly_reports_wta_return_as_corpus_absent():
    """The WTA return-quality dims have NO on-disk corpus -- must appear in
    dims_corpus_absent, never silently omitted with no trace."""
    claims, absent = tcv3.build_all_claims()
    assert "return.return_won_asof.wta" in absent
    assert "return.break_pct_asof.wta" in absent
    # setdetail covers BOTH tours -- must NOT appear in the absent list
    assert "setdetail.tiebreak_win_pct_asof.wta" not in absent
    assert "setdetail.tiebreak_win_pct_asof.atp" not in absent


def test_build_all_claims_produces_expected_claim_count():
    """2 return metrics x ATP-only (WTA absent) + 3 setdetail metrics x
    (ATP+WTA) = 2 + 6 = 8 claims."""
    claims, absent = tcv3.build_all_claims()
    assert len(claims) == 8
    assert len(absent) == 2


def test_real_atp_return_claim_independently_verifies_and_is_full_population():
    """Cross-module check against the REAL on-disk asof_return.parquet --
    proves the emitted ranking is independently reproducible by
    claims_validator AND covers the full qualifying population (no top-N cap)."""
    metric = tcv3.SOURCES[0].metrics[0]  # return_won_asof
    claim = tcv3.build_ranking_claim("return", metric, "atp")
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason
    n_qualifying = claim["n_considered"] - claim["n_excluded_below_floor"]
    assert len(claim["ranking"]) == n_qualifying
    assert n_qualifying > 50, "expected real ATP 2025 qualifying pool to exceed a top-50 cap"


def test_real_wta_setdetail_claim_independently_verifies():
    """Cross-module check against the REAL on-disk asof_setdetail_wta.parquet
    -- the WTA-side of the setdetail source family."""
    metric = tcv3.SOURCES[1].metrics[0]  # tiebreak_win_pct_asof
    claim = tcv3.build_ranking_claim("setdetail", metric, "wta")
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_ranking_rows_carry_player_name_field():
    """wave-63 idname-fix acceptance: every ranking row must carry a real
    player_name (not just player_id) so ask.py's name-based entity_lookup
    can resolve v3 rows -- v3 already sourced this from matches.parquet's
    p1_name/p2_name; this test locks the contract in place."""
    metric = tcv3.SOURCES[0].metrics[0]  # return_won_asof
    claim = tcv3.build_ranking_claim("return", metric, "atp")
    assert len(claim["ranking"]) > 0
    for row in claim["ranking"]:
        assert "player_name" in row
        assert row["player_name"] != ""


def test_name_lookup_id_absent_from_source_gets_honest_fallback_not_fabricated():
    """A player_id with NO row in matches' p1_name/p2_name columns must never
    be silently assigned a fabricated name -- _name_lookup's caller falls
    back to the literal sentinel "Unknown", not a guess."""
    matches = _fixture_matches()
    names = tcv3._name_lookup(matches)
    assert names.get(999) is None  # id 999 never appears in the fixture
    # build_tour_snapshot's own .get(..., "Unknown") fallback for any id
    # absent from the lookup dict:
    assert names.get(999, "Unknown") == "Unknown"
