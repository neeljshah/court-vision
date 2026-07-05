"""Per-file tests for nba_fit_ingredient_claims (PROGRAM v3 item 2, lane
fit-ingredients).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_fit_ingredient_claims.py -q

Acceptance criteria:
  1. build_archetype_claim excludes below-MIN_MPG players into
     n_excluded_below_floor, never silently drops them.
  2. build_scheme_identity_claim covers all 30 team_scheme rows (full
     population, no floor).
  3. build_role_vacancy_snapshot's is_below_median split is LEAGUE-WIDE per
     posgroup (not per-team), and MIN_TEAM_POSGROUP_N excludes thin pairs.
  4. Each of the 3 REAL on-disk claims independently re-verifies via
     claims_validator.validate_claim -> VERIFIED (cross-module check,
     proves independence from this producer, not just self-consistency).
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import nba_fit_ingredient_claims as fic
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def test_archetype_claim_excludes_below_floor_players(monkeypatch, tmp_path):
    fixture = pd.DataFrame({
        "pid": [1, 2, 3],
        "player": ["Alpha", "Beta", "Gamma"],
        "team": ["ATL", "BOS", "CHI"],
        "mpg": [25.0, 5.0, 12.0],  # Beta below a 10.0 floor
        "posgroup": ["GUARD", "WING", "BIG"],
        "archetype": ["LEAD_GUARD", "ROLE_WING", "ROLE_BIG"],
        "creation": [0.9, 0.2, 0.5], "playmaking": [0.8, 0.2, 0.4],
        "spacing": [0.5, 0.3, 0.2], "rim_pressure": [0.3, 0.2, 0.7],
        "rebounding": [0.3, 0.4, 0.8], "rim_protect": [0.2, 0.1, 0.6],
        "perimeter_d": [0.4, 0.5, 0.3], "self_create": [0.7, 0.2, 0.3],
        "usage_pct": [0.95, 0.40, 0.60], "scorer_pct": [0.9, 0.3, 0.5],
    })
    path = tmp_path / "player_roles.parquet"
    fixture.to_parquet(path)
    monkeypatch.setattr(fic, "_PLAYER_ROLES", path)
    monkeypatch.setattr(fic, "REPO_ROOT", tmp_path.parent)

    claim = fic.build_archetype_claim()
    ranked_pids = {r["pid"] for r in claim["ranking"]}
    assert 2 not in ranked_pids  # Beta excluded: mpg=5.0 < floor 10.0
    assert claim["n_considered"] == 3
    assert claim["n_excluded_below_floor"] == 1
    # Alpha (usage_pct=0.95) ranks above Gamma (0.60) -- desc by usage_pct
    assert claim["ranking"][0]["pid"] == 1


def test_scheme_identity_claim_covers_full_population_no_floor(monkeypatch, tmp_path):
    fixture = pd.DataFrame({
        "row_type": ["team_scheme", "team_scheme", "player_vs_coverage"],
        "team": ["ATL", "BOS", "ATL"],
        "wf_ppp_allowed_z": [0.5, -0.3, 9.9],
        "dominant_tag": ["SWITCH HEAVY", "DROP COVERAGE", "IGNORED"],
        "best_scheme": [None, None, None],
        "confidence": ["high", "high", "high"],
        "n_obs": [23, 30, 5],
    })
    path = tmp_path / "scheme_coverage.parquet"
    fixture.to_parquet(path)
    monkeypatch.setattr(fic, "_SCHEME_COVERAGE", path)
    monkeypatch.setattr(fic, "REPO_ROOT", tmp_path.parent)

    claim = fic.build_scheme_identity_claim()
    # the player_vs_coverage row must never leak into the team_scheme ranking
    assert claim["n_considered"] == 2
    assert claim["n_excluded_below_floor"] == 0
    teams = {r["team"] for r in claim["ranking"]}
    assert teams == {"ATL", "BOS"}
    assert claim["ranking"][0]["team"] == "ATL"  # 0.5 > -0.3, desc


def _fixture_boxscores() -> pd.DataFrame:
    # ATL|BIG: 3 players (clears MIN_TEAM_POSGROUP_N=3), BOS|BIG: 1 player
    # (feeds the league-wide BIG median pool but is itself below floor),
    # CHI|GUARD: 1 player (also below floor). League-wide BIG pts_per_min
    # pool = [1.0, 1.0, 0.1, 1.0] -> median=1.0; ATL's player 12 (0.1) is
    # the only ATL|BIG player below that median -> ATL|BIG vacancy=1/3.
    return pd.DataFrame({
        "player_id": [10, 11, 12, 13, 20],
        "team": ["ATL", "ATL", "ATL", "BOS", "CHI"],
        "min": [10.0, 10.0, 10.0, 10.0, 10.0],
        "pts": [10.0, 10.0, 1.0, 10.0, 5.0],
    })


def test_role_vacancy_uses_league_wide_posgroup_median_and_floor(monkeypatch, tmp_path):
    box_path = tmp_path / "player_boxscores.parquet"
    roles_path = tmp_path / "player_roles.parquet"
    _fixture_boxscores().to_parquet(box_path)
    pd.DataFrame({
        "pid": [10, 11, 12, 13, 20],
        "posgroup": ["BIG", "BIG", "BIG", "BIG", "GUARD"],
    }).to_parquet(roles_path)

    monkeypatch.setattr(fic, "_PLAYER_BOXSCORES", box_path)
    monkeypatch.setattr(fic, "_PLAYER_ROLES", roles_path)
    monkeypatch.setattr(fic, "_VACANCY_SNAPSHOT", tmp_path / "snap.parquet")
    monkeypatch.setattr(fic, "MIN_TEAM_POSGROUP_N", 3)
    monkeypatch.setattr(fic, "REPO_ROOT", tmp_path.parent)

    claim = fic.build_role_vacancy_claim()
    keys = {r["team_posgroup"] for r in claim["ranking"]}
    # BOS|BIG (1 player) and CHI|GUARD (1 player) are below floor 3 -> excluded
    assert "BOS|BIG" not in keys
    assert "CHI|GUARD" not in keys
    assert claim["n_excluded_below_floor"] == 2
    atl_big = next(r for r in claim["ranking"] if r["team_posgroup"] == "ATL|BIG")
    assert atl_big["value"] == round(1 / 3, 4)
    assert atl_big["n"] == 3


def test_real_archetype_claim_independently_verifies():
    """Cross-module check against the REAL on-disk parquet -- proves the
    emitted ranking is independently reproducible by claims_validator."""
    claim = fic.build_archetype_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_scheme_identity_claim_independently_verifies():
    claim = fic.build_scheme_identity_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_role_vacancy_claim_independently_verifies():
    claim = fic.build_role_vacancy_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason
