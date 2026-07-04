"""Per-file tests for mlb_pitcher_claims (mission spine 5, lane claims-breadth-2).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_mlb_pitcher_claims.py -q

Acceptance criteria:
  1. build_pitcher_season_rows filters to is_pitcher rows only, stamps season.
  2. min_sample floor (battersFaced) actually excludes below-floor pitchers.
  3. build_ranking_claim's claimed ranking is independently re-verified by
     claims_validator.validate_claim -> VERIFIED (the real cross-module check,
     against the REAL on-disk parquet -- proves reproducibility, not just
     self-consistency).
  4. ASCII-folding strips diacritics from mojibake player names.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import mlb_pitcher_claims as mpc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_gamelogs() -> pd.DataFrame:
    return pd.DataFrame({
        "game_pk": [1, 2, 3, 4, 5],
        "date": pd.to_datetime(["2025-04-01", "2025-04-08", "2025-05-01", "2025-04-01", "2024-04-01"]),
        "player_id": [101, 101, 102, 999, 101],
        "player": ["Ace Pitcher", "Ace Pitcher", "Rook Reliever", "Bench Batter", "Ace Pitcher"],
        "is_pitcher": [True, True, True, False, True],
        "battersFaced": [120.0, 110.0, 15.0, None, 100.0],
        "pitch_strikeOuts": [40.0, 35.0, 2.0, None, 30.0],
    })


def test_build_pitcher_season_rows_filters_pitchers_and_season(tmp_path, monkeypatch):
    monkeypatch.setattr(mpc, "_GAMELOGS", tmp_path / "unused.parquet")
    monkeypatch.setattr(mpc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(mpc, "_SNAPSHOT_OUT", tmp_path / "mlb_pitcher_season_rows.parquet")
    df = _fixture_gamelogs()
    df.to_parquet(mpc._GAMELOGS)

    out_path, name_df = mpc.build_pitcher_season_rows("2025")
    raw = pd.read_parquet(out_path)
    # batter row (999) and 2024 row dropped; only 2025 pitcher rows remain (3 rows)
    assert len(raw) == 3
    assert set(raw["player_id"]) == {101, 102}
    assert (raw["season"] == 2025).all()
    assert dict(zip(name_df["player_id"], name_df["player_name"]))[101] == "Ace Pitcher"


def test_min_sample_floor_excludes_low_batters_faced(tmp_path, monkeypatch):
    monkeypatch.setattr(mpc, "_GAMELOGS", tmp_path / "unused.parquet")
    monkeypatch.setattr(mpc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(mpc, "_SNAPSHOT_OUT", tmp_path / "mlb_pitcher_season_rows.parquet")
    monkeypatch.setattr(mpc, "_CLAIMS_OUT", tmp_path / "mlb_pitcher_claims.jsonl")
    monkeypatch.setattr(mpc, "REPO_ROOT", tmp_path.parent)
    monkeypatch.setattr(mpc, "MIN_BATTERS_FACED", 200)
    _fixture_gamelogs().to_parquet(mpc._GAMELOGS)

    claim = mpc.build_ranking_claim()
    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    # 101: 120+110=230 bf >= 200 floor -> qualifies; 102: 15 bf < 200 -> excluded
    assert 101 in ranked_ids
    assert 102 not in ranked_ids
    assert claim["n_excluded_below_floor"] == 1


def test_ascii_fold_strips_diacritics():
    assert mpc._ascii_fold("Cristopher Sánchez") == "Cristopher Sanchez"
    assert mpc._ascii_fold("Aníbal Sánchez") == "Anibal Sanchez"


def test_real_mlb_pitcher_claim_independently_verifies():
    """Cross-module check against the REAL on-disk parquet (matches the
    production claim this module ships) -- proves the emitted ranking is
    independently reproducible by claims_validator, not just self-consistent."""
    claim = mpc.build_ranking_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason
