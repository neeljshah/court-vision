"""Per-file tests for the nba_lineup_context claim family
(nba_lineup_context_claims.py + nba_lineup_context_spacing.py).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_lineup_context_claims.py -q

Acceptance: floor-skip (no empty ranking ever emitted), delta math, roster-
confound caveat on every claim, both-season emission, validator VERIFIED
round-trip for all 5 claim shapes.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import nba_lineup_context_claims as lc
from scripts.platformkit.intel_validation import nba_lineup_context_spacing as sp

_ON_OFF_COLS = [
    "player_id", "team_id", "n_games", "min_on", "min_off",
    "net_rating_on_per48", "net_rating_off_per48",
    "teammate_efg_on", "teammate_efg_off", "teammate_fga_on", "teammate_fga_off", "player_name",
]
_ON_OFF_ROWS = [
    (1, 100, 35, 600.0, 400.0, 5.0, -2.0, 0.55, 0.50, 250, 250, "Alice"),   # delta=7.0, lift=.05
    (2, 100, 32, 550.0, 310.0, 1.0, 1.0, 0.52, 0.52, 250, 250, "Bob"),      # delta=0, lift=0
    (3, 100, 10, 700.0, 500.0, 9.0, -9.0, 0.60, 0.20, 250, 250, "Cara"),    # n_games<30 -> excluded
]

_GRAVITY_COLS = ["player_id", "team_id", "player_name", "n_games", "min_on", "teammate_efg_on", "teammate_efg_off", "gravity_proxy"]
_GRAVITY_ROWS = [
    (1, 100, "Alice", 25, 350.0, 0.56, 0.50, 0.06),
    (2, 100, "Bob", 15, 400.0, 0.60, 0.50, 0.10),   # n_games<20 -> excluded
    (4, 100, "Dee", 22, 310.0, 0.52, 0.50, 0.02),
]

_ZONE_COLS = [
    "player_id", "team_id", "player_name", "n_games", "min_on", "min_off",
    "rim_fga_on", "rim_fga_off", "rim_efg_allowed_on", "rim_efg_allowed_off",
]
_ZONE_ROWS = [
    (1, 100, "Alice", 35, 600.0, 400.0, 40, 25, 0.55, 0.65),   # delta=.10
    (2, 100, "Bob", 32, 550.0, 310.0, 20, 25, 0.50, 0.50),      # rim_fga_on<30 -> excluded
]

_SPACING_COLS = ["team_id", "lineup_key", "n_shots", "spacing_mean_dist"]
_SPACING_ROWS = [
    (100, "1,2,3,4,5", 150, 12.0),
    (100, "1,2,3,4,6", 120, 8.0),
    (100, "1,2,3,4,7", 50, 20.0),   # n_shots<100 -> excluded from ranking
    (200, "8,9,10,11,12", 110, 5.0),  # only 1 qualifier for team 200 -> whole claim skipped
]


@pytest.fixture()
def wired(monkeypatch, tmp_path):
    lineups_dir = tmp_path / "lineups"
    out_dir = tmp_path / "out"
    lineups_dir.mkdir()
    out_dir.mkdir()

    for season in lc.SEASONS:
        pd.DataFrame(_ON_OFF_ROWS, columns=_ON_OFF_COLS).to_parquet(lineups_dir / f"on_off_{season}.parquet")
        pd.DataFrame(_GRAVITY_ROWS, columns=_GRAVITY_COLS).to_parquet(lineups_dir / f"gravity_proxy_{season}.parquet")
        pd.DataFrame(_ZONE_ROWS, columns=_ZONE_COLS).to_parquet(lineups_dir / f"zone_onoff_{season}.parquet")
        pd.DataFrame(_SPACING_ROWS, columns=_SPACING_COLS).to_parquet(lineups_dir / f"lineup_spacing_{season}.parquet")

    monkeypatch.setattr(lc, "_LINEUPS_DIR", lineups_dir)
    monkeypatch.setattr(lc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sp, "_LINEUPS_DIR", lineups_dir)
    monkeypatch.setattr(sp, "_OUT_DIR", out_dir)
    monkeypatch.setattr(sp, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(claims_validator, "REPO_ROOT", tmp_path)
    return tmp_path


def test_net_rating_delta_math_and_floor(wired):
    claim = lc.build_net_rating_delta_claim(season="2025_26")
    assert claim["n_considered"] == 3
    assert claim["n_excluded_below_floor"] == 1  # Cara (n_games=10)
    ranked = {r["player_id"]: r["value"] for r in claim["ranking"]}
    assert ranked == {1: 7.0, 2: 0.0}


def test_teammate_efg_lift_math(wired):
    claim = lc.build_teammate_efg_lift_claim(season="2025_26")
    top = claim["ranking"][0]
    assert top["player_id"] == 1
    assert top["value"] == round(0.55 - 0.50, 4)


def test_gravity_proxy_floor_excludes_bob(wired):
    claim = lc.build_gravity_proxy_claim(season="2025_26")
    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    assert 2 not in ranked_ids  # n_games=15 < 20
    assert ranked_ids == {1, 4}


def test_rim_protection_delta_math_and_floor(wired):
    claim = lc.build_rim_protection_claim(season="2025_26")
    assert claim["n_excluded_below_floor"] == 1  # Bob rim_fga_on=20 < 30
    top = claim["ranking"][0]
    assert top["player_id"] == 1
    assert top["value"] == round(0.65 - 0.55, 4)


def test_spacing_skips_team_with_lt2_qualifiers_never_empty_ranking(wired):
    claims = sp.build_spacing_claims(season="2025_26")
    team_ids = {c["claim_id"].rsplit("_", 1)[-1] for c in claims}
    assert "200" not in team_ids  # only 1 qualifying lineup -> skipped entirely
    assert all(c["ranking"] for c in claims)  # never an empty ranking
    team100 = next(c for c in claims if c["claim_id"].endswith("_100"))
    assert team100["ranking"][0]["lineup_key"] == "1,2,3,4,5"  # best (most spread)
    assert team100["ranking"][-1]["lineup_key"] == "1,2,3,4,6"  # worst
    assert team100["n_excluded_below_floor"] == 1  # the 50-shot lineup


def test_both_seasons_emitted(wired):
    claims = lc.build_all_claims(seasons=list(lc.SEASONS))
    claim_ids = {c["claim_id"] for c in claims}
    for season in lc.SEASONS:
        assert f"nba_lineup_context_net_rating_delta_{season}" in claim_ids
        assert f"nba_lineup_context_gravity_proxy_{season}" in claim_ids


def test_roster_confound_caveat_on_every_claim(wired):
    claims = lc.build_all_claims(seasons=["2025_26"])
    for claim in claims:
        blob = " ".join(claim["caveats"]).lower()
        assert "roster confound" in blob
        assert claim["label"] == "DESCRIPTIVE_ONLY"
        assert claim["edge_claimed"] is False


def test_no_forbidden_words(wired):
    claims = lc.build_all_claims(seasons=["2025_26"])
    blob = json.dumps([c["caveats"] for c in claims]).lower()
    for word in ("roi", "pnl", "bankroll"):
        assert word not in blob


def test_validator_verified_for_all_five_claim_shapes(wired):
    claims = lc.build_all_claims(seasons=["2025_26"])
    assert len(claims) == 5  # 4 delta claims + 1 spacing claim (team 200 skipped)
    for claim in claims:
        verdict = claims_validator.validate_claim(claim)
        assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"
