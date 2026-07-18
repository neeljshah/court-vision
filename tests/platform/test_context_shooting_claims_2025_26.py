"""Per-file tests for context_shooting_claims_2025_26.py (additive 2025-26
sibling of context_shooting_claims.py). Synthetic frame only.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platform/test_context_shooting_claims_2025_26.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_nba import context_shooting_claims as csc
from domains.basketball_nba import context_shooting_claims_2025_26 as csc26
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _synthetic_rows_2025_26() -> pd.DataFrame:
    """Same shape as context_shooting_claims's own fixture, season stamped
    2025-26, with every TeamA player getting a 3rd (B2B) game so all 3 dims
    have data."""
    return pd.DataFrame([
        {"game_id": "g1", "date": pd.Timestamp("2025-11-01"), "season": "2025-26",
         "team": "A", "player_id": 1, "player_name": "P1", "fg3m": 20, "fg3a": 50},
        {"game_id": "g2", "date": pd.Timestamp("2025-11-03"), "season": "2025-26",
         "team": "A", "player_id": 1, "player_name": "P1", "fg3m": 20, "fg3a": 50},
        {"game_id": "g3", "date": pd.Timestamp("2025-11-04"), "season": "2025-26",
         "team": "A", "player_id": 1, "player_name": "P1", "fg3m": 5, "fg3a": 50},
        {"game_id": "g1", "date": pd.Timestamp("2025-11-01"), "season": "2025-26",
         "team": "A", "player_id": 2, "player_name": "P2", "fg3m": 10, "fg3a": 50},
        {"game_id": "g2", "date": pd.Timestamp("2025-11-03"), "season": "2025-26",
         "team": "A", "player_id": 2, "player_name": "P2", "fg3m": 10, "fg3a": 50},
        {"game_id": "g3", "date": pd.Timestamp("2025-11-04"), "season": "2025-26",
         "team": "A", "player_id": 2, "player_name": "P2", "fg3m": 5, "fg3a": 50},
        {"game_id": "g1", "date": pd.Timestamp("2025-11-01"), "season": "2025-26",
         "team": "A", "player_id": 3, "player_name": "P3", "fg3m": 20, "fg3a": 200},
        {"game_id": "g2", "date": pd.Timestamp("2025-11-03"), "season": "2025-26",
         "team": "A", "player_id": 3, "player_name": "P3", "fg3m": 20, "fg3a": 200},
        {"game_id": "g3", "date": pd.Timestamp("2025-11-04"), "season": "2025-26",
         "team": "A", "player_id": 3, "player_name": "P3", "fg3m": 20, "fg3a": 200},
        {"game_id": "g1", "date": pd.Timestamp("2025-11-01"), "season": "2025-26",
         "team": "B", "player_id": 4, "player_name": "P4", "fg3m": 5, "fg3a": 10},
    ])


def test_season_constant():
    assert csc26.SEASON == "2025-26"


def test_build_season_claims_ids_and_window(monkeypatch, tmp_path):
    box_path = tmp_path / "player_boxscores.parquet"
    _synthetic_rows_2025_26().to_parquet(box_path)
    monkeypatch.setattr(csc, "_BOXSCORES", box_path)
    monkeypatch.setattr(csc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(csc, "_rel", lambda p: str(p))
    monkeypatch.setattr(csc, "MIN_PLAYER_FG3A", 50)  # small synthetic pop
    monkeypatch.setattr(csc, "MIN_TEAM_OTHER_FG3A", 50)
    monkeypatch.setattr(csc, "MIN_REST_SIDE_FG3A", 1)

    claims = csc26.build_season_claims()
    assert len(claims) == 3
    ids = sorted(c["claim_id"] for c in claims)
    assert ids == sorted([
        "nba_fg3_pct_vs_team_context_2025-26",
        "nba_fg3a_share_of_team_2025-26",
        "nba_fg3_pct_rest_split_2025-26",
    ])
    for c in claims:
        assert c["criteria"]["window"] == "season_2025-26_nba"


def test_build_season_claims_verify_against_validator(monkeypatch, tmp_path):
    box_path = tmp_path / "player_boxscores.parquet"
    _synthetic_rows_2025_26().to_parquet(box_path)
    monkeypatch.setattr(csc, "_BOXSCORES", box_path)
    monkeypatch.setattr(csc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(csc, "_rel", lambda p: str(p))
    monkeypatch.setattr(csc, "MIN_PLAYER_FG3A", 50)
    monkeypatch.setattr(csc, "MIN_TEAM_OTHER_FG3A", 50)
    monkeypatch.setattr(csc, "MIN_REST_SIDE_FG3A", 1)

    for claim in csc26.build_season_claims():
        verdict = validate_claim(claim)
        assert verdict.verdict == "VERIFIED", (claim["claim_id"], verdict.reason)
