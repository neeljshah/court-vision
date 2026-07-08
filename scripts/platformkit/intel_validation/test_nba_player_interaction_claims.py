"""Per-file tests for nba_player_interaction_claims (lane
player-interactions): n-floor exclusion (incl. the negative-placeholder-id
floor), TOP-N capping, ranking-row schema (rank/entity/value/n/text), and
that a real produced claim independently re-verifies via claims_validator.

Run: python -m pytest scripts/platformkit/intel_validation/test_nba_player_interaction_claims.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import nba_player_interaction_claims as m
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_pairwise() -> pd.DataFrame:
    return pd.DataFrame([
        # qualifies, strong effect
        {"team_id": 1, "player_x": 10, "player_y": 20, "player_x_name": "A", "player_y_name": "B",
         "min_together": 250.0, "min_x_without_y": 150.0, "lineup_ppm_with_y_on": 1.1,
         "lineup_ppm_without_y": 1.0, "x_efg_with_y_on": 0.60, "x_efg_without_y": 0.40,
         "ppm_delta": 0.1, "efg_delta": 0.20},
        # qualifies, weaker effect
        {"team_id": 1, "player_x": 11, "player_y": 21, "player_x_name": "C", "player_y_name": "D",
         "min_together": 300.0, "min_x_without_y": 200.0, "lineup_ppm_with_y_on": 1.0,
         "lineup_ppm_without_y": 1.0, "x_efg_with_y_on": 0.50, "x_efg_without_y": 0.45,
         "ppm_delta": 0.0, "efg_delta": 0.05},
        # below floor on min_together -- must be counted, never ranked
        {"team_id": 1, "player_x": 12, "player_y": 22, "player_x_name": "E", "player_y_name": "F",
         "min_together": 50.0, "min_x_without_y": 150.0, "lineup_ppm_with_y_on": 1.0,
         "lineup_ppm_without_y": 1.0, "x_efg_with_y_on": 0.60, "x_efg_without_y": 0.40,
         "ppm_delta": 0.0, "efg_delta": 0.20},
        # negative-placeholder id -- must be counted via the id>=0 floor, never ranked
        {"team_id": 1, "player_x": -1, "player_y": 23, "player_x_name": "PLACEHOLDER", "player_y_name": "G",
         "min_together": 300.0, "min_x_without_y": 200.0, "lineup_ppm_with_y_on": 1.0,
         "lineup_ppm_without_y": 1.0, "x_efg_with_y_on": 0.70, "x_efg_without_y": 0.30,
         "ppm_delta": 0.0, "efg_delta": 0.40},
    ])


def test_pairwise_claim_applies_floor_and_negative_id_exclusion_honestly(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "TOP_N", 10)
    monkeypatch.setattr(m, "REPO_ROOT", tmp_path)
    src = tmp_path / "pairwise_onoff_FX.parquet"
    _fixture_pairwise().to_parquet(src)

    claim = m._build_ranking_claim(
        claim_id="test_pairwise", question="q ({season})", metric_col="efg_delta",
        entity_key=["team_id", "player_x", "player_y"],
        min_sample={"min_together": 200.0, "min_x_without_y": 100.0, "player_x": 0, "player_y": 0},
        src=src, season="FX", row_fmt=m._pairwise_row, caveats=["c"],
    )
    assert claim["n_considered"] == 4
    # excluded: the 50-min row (fails min_together) AND the negative-id row (fails player_x>=0)
    assert claim["n_excluded_below_floor"] == 2
    assert len(claim["ranking"]) == 2  # only the two qualifying rows
    ranked_pairs = {(r["player_x"], r["player_y"]) for r in claim["ranking"]}
    assert (12, 22) not in ranked_pairs  # below floor
    assert (-1, 23) not in ranked_pairs  # negative placeholder id
    # strongest effect (0.20) ranked above the weaker one (0.05)
    assert claim["ranking"][0]["player_x"] == 10 and claim["ranking"][0]["value"] == 0.20
    assert claim["ranking"][1]["value"] == 0.05


def test_ranking_row_schema_has_rank_entity_value_n_text(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "TOP_N", 10)
    monkeypatch.setattr(m, "REPO_ROOT", tmp_path)
    src = tmp_path / "pairwise_onoff_FX.parquet"
    _fixture_pairwise().to_parquet(src)
    claim = m._build_ranking_claim(
        claim_id="test_pairwise", question="q ({season})", metric_col="efg_delta",
        entity_key=["team_id", "player_x", "player_y"],
        min_sample={"min_together": 200.0, "min_x_without_y": 100.0, "player_x": 0, "player_y": 0},
        src=src, season="FX", row_fmt=m._pairwise_row, caveats=["c"],
    )
    row = claim["ranking"][0]
    for key in ("rank", "team_id", "player_x", "player_y", "value", "n", "text"):
        assert key in row
    assert isinstance(row["text"], str) and "eFG" in row["text"] and "FX" in row["text"]
    assert claim["criteria"]["entity_key"] == ["team_id", "player_x", "player_y"]
    assert claim["kind"] == "ranking"
    assert claim["edge_claimed"] is False


def test_top_n_cap_applied(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "TOP_N", 1)
    monkeypatch.setattr(m, "REPO_ROOT", tmp_path)
    src = tmp_path / "pairwise_onoff_FX.parquet"
    _fixture_pairwise().to_parquet(src)
    claim = m._build_ranking_claim(
        claim_id="test_pairwise", question="q ({season})", metric_col="efg_delta",
        entity_key=["team_id", "player_x", "player_y"],
        min_sample={"min_together": 200.0, "min_x_without_y": 100.0, "player_x": 0, "player_y": 0},
        src=src, season="FX", row_fmt=m._pairwise_row, caveats=["c"],
    )
    assert len(claim["ranking"]) == 1
    assert claim["ranking"][0]["value"] == 0.20  # the strongest of the qualifiers, not just first-seen


@pytest.mark.skipif(
    not (m._INTERACTIONS_DIR / "pairwise_onoff_2025_26.parquet").exists(),
    reason="local-only data not present",
)
def test_real_pairwise_gravity_claim_independently_verifies():
    claim = m.build_claims_for_season("2025_26")[0]
    assert claim["claim_id"] == "nba_pairwise_gravity_top50_2025_26"
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason
