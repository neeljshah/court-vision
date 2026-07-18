"""Per-file tests for shooter_composite_v2_asof_approx_claims.py (2025-26
atlas-degraded, boxscore-only sibling of shooter_composite_v2_claims.py).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_shooter_composite_v2_asof_approx_claims.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import shooter_composite_v2_asof_approx_claims as approx


_NAN = float("nan")
# player_id, player_name, games, fg3a_per_game, fg3_pct, ft_pct
_FIXTURE_ROWS = [
    (1, "Alice", 70, 8.0, 0.40, 0.85),   # all 3 present
    (2, "Bob", 68, 6.0, 0.35, _NAN),     # ft_pct missing -> mean over 2 present
    (3, "Cara", 60, 4.0, 0.30, 0.75),
    (4, "Dee", 65, 3.9, _NAN, _NAN),     # only 1/3 present -> excluded (<2 floor)
]
_COLS = ["player_id", "player_name", "games", "fg3a_per_game", "fg3_pct", "ft_pct"]


def _raw() -> pd.DataFrame:
    return pd.DataFrame(_FIXTURE_ROWS, columns=_COLS)


@pytest.fixture()
def snap() -> pd.DataFrame:
    return approx.compute_snapshot(_raw())


def test_min_ingredients_floor_excludes_thin_row(snap):
    dee = snap[snap["player_name"] == "Dee"].iloc[0]
    assert dee["n_present"] == 1
    assert pd.isna(dee["shooter_composite_v2_asof_approx"])


def test_missing_one_ingredient_still_scores_on_the_rest(snap):
    bob = snap[snap["player_name"] == "Bob"].iloc[0]
    assert bob["n_present"] == 2
    assert not pd.isna(bob["shooter_composite_v2_asof_approx"])


def test_build_claim_shape_and_floor(snap):
    claim = approx.build_claim(snap, "2025-26")
    assert claim["claim_id"] == "shooter_composite_v2_asof_approx_full_season_2025_26"
    assert claim["criteria"]["window"] == "2025-26"
    assert claim["n_considered"] == 4
    assert claim["n_excluded_below_floor"] == 1  # Dee only
    names_ranked = {r["player_name"] for r in claim["ranking"]}
    assert "Dee" not in names_ranked
    assert {"Alice", "Bob", "Cara"}.issubset(names_ranked)


def test_caveats_name_atlas_gap_and_predictive_receipt(snap):
    claim = approx.build_claim(snap, "2025-26")
    joined = " ".join(claim["caveats"])
    assert "ATLAS-UNAVAILABLE-2025-26" in joined
    assert "PREDICTIVE_VERIFIED" in joined
    # count matches the list that follows (review fix: said 3, lists 4)
    assert "other 4 ingredients" in joined
    assert claim["edge_claimed"] is False


def test_producer_writes_only_its_own_store(tmp_path, monkeypatch):
    """Store-clobber regression (review fix, 8ec45e5c precedent): this
    producer must write ONLY the asof_approx claim to ITS OWN store, never
    the sibling's shooter_composite_v2_claims.jsonl."""
    from scripts.platformkit.intel_validation import shooter_composite_v2_claims as full
    assert approx._CLAIMS_OUT.name == "shooter_composite_v2_asof_approx_claims.jsonl"
    assert approx._CLAIMS_OUT != full._CLAIMS_OUT

    out = tmp_path / approx._CLAIMS_OUT.name
    monkeypatch.setattr(approx, "_CLAIMS_OUT", out)
    stub = {"claim_id": "shooter_composite_v2_asof_approx_full_season_2025_26",
            "ranking": [], "n_considered": 0, "n_excluded_below_floor": 0}
    monkeypatch.setattr(approx, "build_season_claim", lambda season: dict(stub))
    approx.main()
    lines = out.read_text(encoding="ascii").strip().split("\n")
    assert len(lines) == 1  # ONLY the asof claim -- no sibling full-index rebuild
    assert json.loads(lines[0])["claim_id"] == stub["claim_id"]


def test_validator_round_trip_verified(tmp_path, monkeypatch, snap):
    """Same validator the full-index claim uses -- no separate acceptance path."""
    snap_path = tmp_path / "snap.parquet"
    snap.to_parquet(snap_path)
    monkeypatch.setattr(
        "scripts.platformkit.intel_validation.claims_validator.REPO_ROOT", tmp_path,
    )
    monkeypatch.setattr(
        "scripts.platformkit.intel_validation.shooter_composite_v2_claims.REPO_ROOT", tmp_path,
    )
    claim = approx.build_claim(snap, "2025-26", snapshot_path=snap_path)
    claim["source_files"] = ["snap.parquet"]
    verdict = claims_validator.validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason
