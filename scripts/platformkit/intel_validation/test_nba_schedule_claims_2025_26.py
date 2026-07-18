"""Per-file tests for nba_schedule_claims_2025_26.py (additive 2025-26
sibling of nba_schedule_claims.py). Synthetic fixture only -- this worktree
has no data/ on disk.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_schedule_claims_2025_26.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import nba_schedule_claims_2025_26 as sc2
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_games(season: str) -> pd.DataFrame:
    # ATL: home,home,away,away,away,home -- a 3-game road trip, one b2b, and
    # DET as a single-game (thin) team for the min-games-floor test.
    return pd.DataFrame({
        "game_id": [f"{season}_g1", f"{season}_g2", f"{season}_g3",
                    f"{season}_g4", f"{season}_g5", f"{season}_g6"],
        "date": pd.to_datetime([
            "2026-01-01", "2026-01-03", "2026-01-04",
            "2026-01-05", "2026-01-08", "2026-01-09",
        ]),
        "season": [season] * 6,
        "home_team": ["ATL", "ATL", "BOS", "MIA", "CHI", "ATL"],
        "away_team": ["NYK", "PHI", "ATL", "ATL", "ATL", "DET"],
    })


def _fixture_games_every_team_has_two_games(season: str) -> pd.DataFrame:
    # Same ATL road trip + a 2nd game for every other team (g7-g11) so each
    # team has >=2 games -- a real rest_days observation, not just an
    # unfillable first-game NaN. A single-game team gets wiped out entirely
    # by the module's own dropna step before the floor check runs, which is
    # an artifact of too-thin a fixture (the real 82-game season only ever
    # drops ONE row/team this way) -- irrelevant to the min-games-floor test
    # above, which uses the thin fixture on purpose.
    base = _fixture_games(season)
    extra = pd.DataFrame({
        "game_id": [f"{season}_g{i}" for i in range(7, 12)],
        "date": pd.to_datetime(["2026-01-11", "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15"]),
        "season": [season] * 5,
        "home_team": ["BOS", "MIA", "CHI", "NYK", "PHI"],
        "away_team": ["DET", "NYK", "PHI", "DET", "DET"],
    })
    return pd.concat([base, extra], ignore_index=True)


def test_season_is_2025_26_and_ids_match():
    assert sc2.SEASON == "2025-26"
    assert sc2._SEASON_ID == "2025_26"


def test_build_season_claims_ids_and_shape(monkeypatch, tmp_path):
    path = tmp_path / "games.parquet"
    _fixture_games("2025-26").to_parquet(path)
    monkeypatch.setattr(sc2, "_GAMES", path)
    monkeypatch.setattr(sc2, "_GAME_SNAPSHOT", tmp_path / "game_snap.parquet")
    monkeypatch.setattr(sc2, "_STREAK_SNAPSHOT", tmp_path / "streak_snap.parquet")
    monkeypatch.setattr(sc2, "_LONGEST_TRIP_SNAPSHOT", tmp_path / "longest_snap.parquet")
    monkeypatch.setattr("scripts.platformkit.intel_validation.nba_schedule_claims.REPO_ROOT", tmp_path.parent)

    claims = sc2.build_season_claims()
    ids = [c["claim_id"] for c in claims]
    assert ids == [
        "nba_schedule_back_to_back_rate_2025_26",
        "nba_schedule_avg_rest_days_2025_26",
        "nba_schedule_three_in_four_rate_2025_26",
        "nba_schedule_longest_road_trip_2025_26",
        "nba_schedule_road_trip_avg_len_2025_26",
    ]
    for c in claims:
        assert c["criteria"]["window"] == "2025-26"
        for verdict_field in ("kind", "ranking", "n_considered", "n_excluded_below_floor", "caveats"):
            assert verdict_field in c


def test_build_season_claims_min_games_floor_excludes_thin_team(monkeypatch, tmp_path):
    path = tmp_path / "games.parquet"
    _fixture_games("2025-26").to_parquet(path)
    monkeypatch.setattr(sc2, "_GAMES", path)
    monkeypatch.setattr(sc2, "_GAME_SNAPSHOT", tmp_path / "game_snap.parquet")
    monkeypatch.setattr(sc2, "_STREAK_SNAPSHOT", tmp_path / "streak_snap.parquet")
    monkeypatch.setattr("scripts.platformkit.intel_validation.nba_schedule_claims.REPO_ROOT", tmp_path.parent)
    monkeypatch.setattr("scripts.platformkit.intel_validation.nba_schedule_claims.MIN_GAMES_FLOOR", 6)

    game_path, snap = sc2.build_game_dims_snapshot()
    claim = sc2.build_back_to_back_claim(game_path, snap)
    teams_ranked = {r["team"] for r in claim["ranking"]}
    assert "ATL" in teams_ranked
    assert "DET" not in teams_ranked  # DET has 1 game < floor 6 -- excluded, not silently dropped
    assert claim["n_excluded_below_floor"] >= 1


def test_build_season_claims_recomputable_via_validator(monkeypatch, tmp_path):
    """Each 2025-26 claim independently re-verifies through the SAME
    validator the 2024-25 claims use -- no separate acceptance path."""
    path = tmp_path / "games.parquet"
    _fixture_games_every_team_has_two_games("2025-26").to_parquet(path)
    monkeypatch.setattr(sc2, "_GAMES", path)
    monkeypatch.setattr(sc2, "_GAME_SNAPSHOT", tmp_path / "game_snap.parquet")
    monkeypatch.setattr(sc2, "_STREAK_SNAPSHOT", tmp_path / "streak_snap.parquet")
    monkeypatch.setattr(sc2, "_LONGEST_TRIP_SNAPSHOT", tmp_path / "longest_snap.parquet")
    monkeypatch.setattr("scripts.platformkit.intel_validation.nba_schedule_claims.REPO_ROOT", tmp_path.parent)
    monkeypatch.setattr("scripts.platformkit.intel_validation.claims_validator.REPO_ROOT", tmp_path.parent)
    monkeypatch.setattr("scripts.platformkit.intel_validation.nba_schedule_claims.MIN_GAMES_FLOOR", 1)
    # sc2 imported MIN_GAMES_FLOOR as its own binding (used directly by
    # build_longest_road_trip_claim, which bypasses _build_mean_claim) --
    # patching the origin module above does not follow through to it.
    monkeypatch.setattr(sc2, "MIN_GAMES_FLOOR", 1)

    for claim in sc2.build_season_claims():
        verdict = validate_claim(claim)
        assert verdict.verdict == "VERIFIED", (claim["claim_id"], verdict.reason)
