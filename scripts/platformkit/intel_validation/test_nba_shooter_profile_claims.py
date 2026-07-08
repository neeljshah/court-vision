"""Per-file tests for nba_shooter_profile_claims (shooter trait-profile family).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_shooter_profile_claims.py -q

Acceptance:
  1. Contract shape: kind="ranking", entity_key="player_id", contiguous full
     ordering, sorted desc by fg3m/fg3a.
  2. Floor: fg3m < FG3M_QUALIFY_MIN rows are excluded from the ranking and
     counted honestly in n_excluded_below_floor.
  3. External-standard pin: FG3M_QUALIFY_MIN == compose_best's shooter
     domain_filter minimum (same NBA official standard, cannot drift).
  4. Validator VERIFIED end-to-end on a synthetic snapshot fixture.
  5. Honest caveats + edge_claimed False, no forbidden edge words.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_query.compose_best import _ASPECT_CONFIGS
from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import nba_shooter_profile_claims as spc

# player_id, name, games, fg3m, fg3a -- hand-computable fg3_pct
_FIXTURE_ROWS = [
    (1, "Alice", 40, 100, 250),   # .400  qualified, rank 2
    (2, "Bob", 40, 120, 280),      # .4286 qualified, rank 1
    (3, "Cara", 40, 81, 200),      # below the 82 floor -> excluded
    (4, "Dee", 40, 90, 300),       # .300  qualified, rank 3
    (5, "Eve", 40, 10, 40),        # below floor -> excluded
]


def _fixture_pool() -> pd.DataFrame:
    return pd.DataFrame(
        _FIXTURE_ROWS, columns=["player_id", "player_name", "games", "fg3m", "fg3a"]
    )


@pytest.fixture()
def built_claim(monkeypatch, tmp_path):
    monkeypatch.setattr(spc, "_pool_table", lambda season: _fixture_pool())
    monkeypatch.setattr(spc, "_SNAPSHOT_PATH", tmp_path / "snap.parquet")
    monkeypatch.setattr(spc, "REPO_ROOT", tmp_path.parent)
    claim = spc.build_fg3_pct_qualified_claim(season="fixture")
    return claim, tmp_path


def test_contract_shape_and_ordering(built_claim):
    claim, _ = built_claim
    assert claim["kind"] == "ranking"
    assert claim["criteria"]["entity_key"] == "player_id"
    assert claim["criteria"]["formula"] == "fg3m / fg3a"
    ranks = [r["rank"] for r in claim["ranking"]]
    assert ranks == list(range(1, len(ranks) + 1))
    names = [r["player_name"] for r in claim["ranking"]]
    assert names == ["Bob", "Alice", "Dee"]  # hand-computed fg3_pct order
    assert claim["ranking"][0]["value"] == round(120 / 280, 4)
    assert claim["ranking"][1]["value"] == round(100 / 250, 4)


def test_floor_excludes_and_counts_honestly(built_claim):
    claim, _ = built_claim
    assert claim["n_considered"] == 5
    assert claim["n_excluded_below_floor"] == 2  # Cara (81) + Eve (10)
    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    assert 3 not in ranked_ids and 5 not in ranked_ids
    assert claim["criteria"]["min_sample"] == {"fg3m": spc.FG3M_QUALIFY_MIN}


def test_floor_is_the_external_nba_standard_pinned_to_compose_best(built_claim):
    shooter_filter = _ASPECT_CONFIGS["shooter"].domain_filter
    assert shooter_filter is not None
    assert spc.FG3M_QUALIFY_MIN == shooter_filter.min == 82


def test_ranking_rows_carry_sample_fields(built_claim):
    claim, _ = built_claim
    for r in claim["ranking"]:
        assert isinstance(r["fg3m"], int)
        assert isinstance(r["fg3a"], int)
        assert isinstance(r["n"], int)  # games


def test_validator_independently_reverifies(built_claim, monkeypatch):
    claim, tmp_path = built_claim
    monkeypatch.setattr(claims_validator, "REPO_ROOT", tmp_path.parent)
    verdict = claims_validator.validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_no_forbidden_words_and_honest_caveats(built_claim):
    claim, _ = built_claim
    blob = json.dumps([claim["caveats"], claim["question"]]).lower()
    for word in ("roi", "pnl", "$", "bankroll", "edge claim", "predict"):
        assert word not in blob
    assert claim["edge_claimed"] is False
    assert "official" in blob            # external-standard citation
    assert "one axis" in blob            # never-the-whole-shooter caveat
    assert "descriptive" in blob
