"""Per-file tests for nba_context_scheme_claims (axis 2) and
nba_context_margin_claims (axis 3) -- SYNTHETIC atlas parquet fixtures only.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_context_atlas_claims.py -q

Acceptance:
  1. Atlas-caveat presence: both modules' claims carry the mandatory
     2024-25-era/not-refreshable/decay-caution caveat verbatim.
  2. Missing-atlas-file honest skip (no crash, empty ranking never survives
     build_all_claims' filter).
  3. Floor + descriptive-only labeling.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import nba_context_margin_claims as margin
from scripts.platformkit.intel_validation import nba_context_scheme_claims as scheme


def test_scheme_missing_atlas_file_skips_honestly(tmp_path):
    result = scheme.build_claims(box=None, atlas_path=tmp_path / "nope.parquet")
    assert result[0]["ranking"] == []


def test_scheme_claim_carries_atlas_caveat_and_floor(tmp_path, monkeypatch):
    atlas = pd.DataFrame({
        "player_id": [1, 2, 3],
        "n_games_total": [25, 5, 30],  # player 2 below MIN_GAMES_TOTAL=20
        "scheme_ts_pct_best_minus_worst": [0.08, 0.20, 0.03],
        "best_scheme": ["drop", "drop", "switch"],
        "worst_scheme": ["switch", "switch", "drop"],
    })
    atlas_path = tmp_path / "atlas_player_vs_scheme_splits.parquet"
    atlas.to_parquet(atlas_path, index=False)
    out_dir = tmp_path / "intel_claims"
    monkeypatch.setattr(scheme, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(scheme, "_OUT_DIR", out_dir)
    monkeypatch.setattr(scheme, "_SNAPSHOT", out_dir / "nba_context_scheme_snapshot.parquet")

    claims = scheme.build_claims(box=None, atlas_path=atlas_path)
    claim = claims[0]
    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    assert 2 not in ranked_ids  # n_games_total=5 < floor 20
    assert 1 in ranked_ids and 3 in ranked_ids
    assert claim["edge_claimed"] is False
    blob = json.dumps(claim["caveats"]).lower()
    assert "2024-25-era snapshot" in blob
    assert "not refreshable" in blob
    assert "decay caution" in blob


def test_margin_missing_atlas_file_skips_honestly(tmp_path):
    result = margin.build_claims(box=None, atlas_path=tmp_path / "nope.parquet")
    assert result[0]["ranking"] == []


def test_margin_claim_carries_atlas_caveat_and_floor(tmp_path, monkeypatch):
    atlas = pd.DataFrame({
        "player_id": [1, 2, 3],
        "leading": [json.dumps({"fga_pg": 10.0}), json.dumps({"fga_pg": 8.0}), json.dumps({"fga_pg": 12.0})],
        "trailing": [json.dumps({"fga_pg": 14.0}), json.dumps({"fga_pg": 8.5}), json.dumps({"fga_pg": 12.5})],
        "n": [25, 5, 30],  # player 2 below MIN_N=20
    })
    atlas_path = tmp_path / "atlas_player_score_margin_splits.parquet"
    atlas.to_parquet(atlas_path, index=False)
    out_dir = tmp_path / "intel_claims"
    monkeypatch.setattr(margin, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(margin, "_OUT_DIR", out_dir)
    monkeypatch.setattr(margin, "_SNAPSHOT", out_dir / "nba_context_margin_snapshot.parquet")

    claims = margin.build_claims(box=None, atlas_path=atlas_path)
    claim = claims[0]
    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    assert 2 not in ranked_ids  # n=5 < floor 20
    assert 1 in ranked_ids and 3 in ranked_ids
    top = claim["ranking"][0]
    assert top["player_id"] == 1  # 14.0 - 10.0 = 4.0 usage collapse, largest gap
    assert claim["edge_claimed"] is False
    blob = json.dumps(claim["caveats"]).lower()
    assert "2024-25-era snapshot" in blob
    assert "not refreshable" in blob
    assert "decay caution" in blob
    assert "descriptive_only" in blob
