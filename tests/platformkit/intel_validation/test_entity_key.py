"""Tests for criteria.entity_key -- the cross-sport ranking-entity generalization
(intelligence_program.json build_queue rank 2).

Proves the contract works for a NON-player entity (e.g. team_id / pitcher_id)
via a synthetic ranking claim, while an existing basketball claim with NO
entity_key field still validates via the 'player_id' default (back-compat),
and a claim whose entity_key does not match its source data is caught, not
silently passed.

Run ONLY this file:
    python -m pytest tests/platformkit/intel_validation/test_entity_key.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.intel_validation.claims_validator import validate_claim  # noqa: E402


def _make_parquet(tmp_path: Path, name: str, rows: list[dict]) -> str:
    df = pd.DataFrame(rows)
    p = tmp_path / name
    df.to_parquet(p)
    return str(p)


def _team_rows() -> list[dict]:
    """Synthetic MLB-shaped rows keyed on team_id, not player_id -- proves the
    contract generalizes to a non-basketball entity."""
    return [
        {"team_id": "NYY", "team_name": "Yankees", "runs": 5.2, "games": 40},
        {"team_id": "BOS", "team_name": "Red Sox", "runs": 4.8, "games": 38},
        {"team_id": "TBR", "team_name": "Rays", "runs": 4.1, "games": 41},
        {"team_id": "BAL", "team_name": "Orioles", "runs": 6.0, "games": 5},  # below floor
    ]


def _team_ranking_claim(source_path: str) -> dict:
    return {
        "claim_id": "mlb_runs_per_game_team",
        "kind": "ranking",
        "question": "Which team scores the most runs per game?",
        "criteria": {
            "metric": "runs_per_game",
            "formula": "runs",
            "window": "season",
            "min_sample": {"games": 10},
            "direction": "desc",
            "entity_key": "team_id",
        },
        "ranking": [
            {"rank": 1, "team_id": "NYY", "team_name": "Yankees", "value": 5.2, "n": 40},
            {"rank": 2, "team_id": "BOS", "team_name": "Red Sox", "value": 4.8, "n": 38},
            {"rank": 3, "team_id": "TBR", "team_name": "Rays", "value": 4.1, "n": 41},
        ],
        "source_files": [source_path],
        "computed_at": "2026-07-04T00:00:00+00:00",
        "n_considered": 3,
        "n_excluded_below_floor": 1,
        "caveats": [],
    }


def test_non_player_entity_key_ranking_verifies(tmp_path):
    """A ranking claim keyed on team_id (not player_id) recomputes correctly
    end-to-end -- proves generalization beyond basketball's player_id."""
    src = _make_parquet(tmp_path, "team_runs.parquet", _team_rows())
    verdict = validate_claim(_team_ranking_claim(src))
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_wrong_entity_planted_is_mismatch(tmp_path):
    """PLANT: smuggle the below-floor Orioles row in as team_id claimed at
    rank 1 with a value that matches its true data -- only the min_sample
    floor recompute (keyed on the declared entity_key) excludes it, so rank 1
    must recompute as a different team."""
    src = _make_parquet(tmp_path, "team_runs.parquet", _team_rows())
    claim = _team_ranking_claim(src)
    claim["ranking"] = [
        {"rank": 1, "team_id": "BAL", "team_name": "Orioles", "value": 6.0, "n": 5},
        {"rank": 2, "team_id": "NYY", "team_name": "Yankees", "value": 5.2, "n": 40},
        {"rank": 3, "team_id": "BOS", "team_name": "Red Sox", "value": 4.8, "n": 38},
    ]
    claim["n_excluded_below_floor"] = 0
    verdict = validate_claim(claim)
    assert verdict.verdict == "MISMATCH"
    assert verdict.first_divergence["rank"] == 1


def test_entity_key_mismatch_with_group_by_is_unverifiable(tmp_path):
    """A claim whose criteria.entity_key disagrees with its own
    aggregate.group_by is a malformed/inconsistent contract row -- fail
    closed as UNVERIFIABLE, never silently pass on the wrong column."""
    src = _make_parquet(tmp_path, "team_runs.parquet", _team_rows())
    claim = _team_ranking_claim(src)
    claim["criteria"]["formula"] = "mean(runs)"
    claim["criteria"]["aggregate"] = {
        "group_by": "team_id",
        "derived": {"games": "count(games)"},
    }
    claim["criteria"]["entity_key"] = "player_id"  # deliberately wrong vs group_by
    verdict = validate_claim(claim)
    assert verdict.verdict == "UNVERIFIABLE"
    assert "entity_key" in verdict.reason


def test_no_entity_key_field_defaults_to_player_id_backcompat(tmp_path):
    """A claim with NO entity_key field at all (every claim published before
    this feature existed) must still validate via the 'player_id' default --
    zero behavior change for existing basketball claims."""
    rows = [
        {"player_id": "201", "player_name": "Zed", "fg3_pct": 0.42, "fg3a": 150},
        {"player_id": "202", "player_name": "Yara", "fg3_pct": 0.39, "fg3a": 140},
    ]
    src = _make_parquet(tmp_path, "shooting.parquet", rows)
    claim = {
        "claim_id": "top_fg3pct_no_entity_key_field",
        "kind": "ranking",
        "question": "Who leads in 3pt%?",
        "criteria": {
            "metric": "fg3_pct",
            "formula": "fg3_pct",
            "window": "season",
            "min_sample": {"fg3a": 100},
            "direction": "desc",
            # deliberately NO "entity_key" key present
        },
        "ranking": [
            {"rank": 1, "player_id": "201", "player_name": "Zed", "value": 0.42, "n": 150},
            {"rank": 2, "player_id": "202", "player_name": "Yara", "value": 0.39, "n": 140},
        ],
        "source_files": [src],
        "computed_at": "2026-07-04T00:00:00+00:00",
        "n_considered": 2,
        "n_excluded_below_floor": 0,
        "caveats": [],
    }
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_existing_basketball_claim_shape_still_verifies_with_entity_key_field(tmp_path):
    """An explicit entity_key='player_id' (what the NBA producer now emits)
    behaves identically to the omitted-field default -- additive only."""
    rows = [
        {"player_id": "301", "player_name": "Kip", "fg3_pct": 0.44, "fg3a": 200},
        {"player_id": "302", "player_name": "Mo", "fg3_pct": 0.41, "fg3a": 180},
    ]
    src = _make_parquet(tmp_path, "shooting2.parquet", rows)
    claim = {
        "claim_id": "top_fg3pct_explicit_entity_key",
        "kind": "ranking",
        "question": "Who leads in 3pt%?",
        "criteria": {
            "metric": "fg3_pct",
            "formula": "fg3_pct",
            "window": "season",
            "min_sample": {"fg3a": 100},
            "direction": "desc",
            "entity_key": "player_id",
        },
        "ranking": [
            {"rank": 1, "player_id": "301", "player_name": "Kip", "value": 0.44, "n": 200},
            {"rank": 2, "player_id": "302", "player_name": "Mo", "value": 0.41, "n": 180},
        ],
        "source_files": [src],
        "computed_at": "2026-07-04T00:00:00+00:00",
        "n_considered": 2,
        "n_excluded_below_floor": 0,
        "caveats": [],
    }
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason
