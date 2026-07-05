"""Per-file tests for nba_schedule_claims (PROGRAM v3 direction, lane
nba-travel-descriptive).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_schedule_claims.py -q

Acceptance criteria:
  1. build_game_dims_snapshot derives is_b2b/rest_days/is_three_in_four
     correctly from a small fixture schedule (a hand-checkable sequence),
     and the first game of the season is honestly NaN/0, never fabricated.
  2. build_road_trip_streak_snapshot's streak_id correctly segments a
     mixed home/away sequence into maximal away-only runs.
  3. MIN_GAMES_FLOOR excludes a below-floor team into n_excluded_below_floor
     without silently dropping it.
  4. Each of the 5 REAL on-disk claims independently re-verifies via
     claims_validator.validate_claim -> VERIFIED (cross-module check).
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import nba_schedule_claims as sc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_games() -> pd.DataFrame:
    # ATL: home,home,away,away,away,home (a 3-game road trip, one b2b at
    # g2->g3 since 2026-01-02 -> 2026-01-03 is a 1-day gap... use exact
    # dates below so the diffs are hand-checkable.
    return pd.DataFrame({
        "game_id": ["g1", "g2", "g3", "g4", "g5", "g6"],
        "date": pd.to_datetime([
            "2026-01-01", "2026-01-03", "2026-01-04",
            "2026-01-05", "2026-01-08", "2026-01-09",
        ]),
        "season": ["FX"] * 6,
        "home_team": ["ATL", "ATL", "BOS", "MIA", "CHI", "ATL"],
        "away_team": ["NYK", "PHI", "ATL", "ATL", "ATL", "DET"],
    })


def test_game_dims_snapshot_derives_b2b_rest_and_three_in_four(monkeypatch, tmp_path):
    path = tmp_path / "games.parquet"
    _fixture_games().to_parquet(path)
    monkeypatch.setattr(sc, "_GAMES", path)
    monkeypatch.setattr(sc, "_SEASON", "FX")
    monkeypatch.setattr(sc, "_GAME_SNAPSHOT", tmp_path / "game_snap.parquet")

    _, snap = sc.build_game_dims_snapshot()
    atl = snap[snap["team"] == "ATL"].sort_values("date").reset_index(drop=True)
    assert len(atl) == 6
    # g1 (01-01): first game -> no prior -> rest_days NaN, is_b2b=0 (never fabricated)
    assert pd.isna(atl.loc[0, "rest_days"])
    assert atl.loc[0, "is_b2b"] == 0
    # g2 (01-03): 2 days after g1 -> rest_days=2, not b2b
    assert atl.loc[1, "rest_days"] == 2.0
    assert atl.loc[1, "is_b2b"] == 0
    # g3 (01-04): 1 day after g2 -> rest_days=1 -> IS a back-to-back
    assert atl.loc[2, "rest_days"] == 1.0
    assert atl.loc[2, "is_b2b"] == 1
    # g3 (01-04): within [01-01, 01-04] trailing window, ATL played g1,g2,g3 -> 3-in-4
    assert atl.loc[2, "is_three_in_four"] == 1
    # g5 (01-08): only g4(01-05, 3 days back) and g5 in trailing window -> NOT 3-in-4
    assert atl.loc[4, "is_three_in_four"] == 0
    assert (atl["n_games"] == 6).all()


def test_road_trip_streak_snapshot_segments_away_only_runs(monkeypatch, tmp_path):
    path = tmp_path / "games.parquet"
    _fixture_games().to_parquet(path)
    monkeypatch.setattr(sc, "_GAMES", path)
    monkeypatch.setattr(sc, "_SEASON", "FX")
    monkeypatch.setattr(sc, "_GAME_SNAPSHOT", tmp_path / "game_snap.parquet")
    monkeypatch.setattr(sc, "_STREAK_SNAPSHOT", tmp_path / "streak_snap.parquet")

    _, game_snap = sc.build_game_dims_snapshot()
    _, streaks = sc.build_road_trip_streak_snapshot(game_snap)
    atl_streaks = streaks[streaks["team"] == "ATL"]["streak_len"].tolist()
    # ATL's sequence is home,home,away,away,away,home -> ONE 3-game road trip
    assert atl_streaks == [3]


def test_min_games_floor_excludes_thin_team_honestly(monkeypatch, tmp_path):
    fixture = _fixture_games()
    # add a second, thin team (DET) with only 1 game -- below any realistic floor
    path = tmp_path / "games.parquet"
    fixture.to_parquet(path)
    monkeypatch.setattr(sc, "_GAMES", path)
    monkeypatch.setattr(sc, "_SEASON", "FX")
    monkeypatch.setattr(sc, "_GAME_SNAPSHOT", tmp_path / "game_snap.parquet")
    monkeypatch.setattr(sc, "REPO_ROOT", tmp_path.parent)
    monkeypatch.setattr(sc, "MIN_GAMES_FLOOR", 6)  # ATL clears (6), DET (1 game) does not

    _, snap = sc.build_game_dims_snapshot()
    claim = sc.build_back_to_back_claim(sc._GAME_SNAPSHOT, snap)
    teams_ranked = {r["team"] for r in claim["ranking"]}
    assert "ATL" in teams_ranked
    assert "DET" not in teams_ranked  # DET has 1 game < floor 6, excluded not dropped silently
    assert claim["n_excluded_below_floor"] >= 1


def test_real_back_to_back_claim_independently_verifies():
    claim = sc.build_all_claims()[0]
    assert claim["claim_id"] == "nba_schedule_back_to_back_rate_2024_25"
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_avg_rest_days_claim_independently_verifies():
    claim = sc.build_all_claims()[1]
    assert claim["claim_id"] == "nba_schedule_avg_rest_days_2024_25"
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_three_in_four_claim_independently_verifies():
    claim = sc.build_all_claims()[2]
    assert claim["claim_id"] == "nba_schedule_three_in_four_rate_2024_25"
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_longest_road_trip_claim_independently_verifies():
    claim = sc.build_all_claims()[3]
    assert claim["claim_id"] == "nba_schedule_longest_road_trip_2024_25"
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_road_trip_avg_len_claim_independently_verifies():
    claim = sc.build_all_claims()[4]
    assert claim["claim_id"] == "nba_schedule_road_trip_avg_len_2024_25"
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_repo_full_population_all_30_teams_every_claim():
    """FULL POPULATION acceptance: all 5 dims cover 30/30 NBA teams for the
    2024-25 season with n_excluded_below_floor honestly reported (0 this
    season since every team played all 82 games)."""
    for claim in sc.build_all_claims():
        assert claim["n_considered"] == 30
        assert len(claim["ranking"]) == 30
        assert claim["n_excluded_below_floor"] == 0


def test_real_repo_discovered_by_ask_auto_discovery():
    """The new store is AUTO-DISCOVERED by intel_query.ask's glob (zero
    per-store registration needed), matching every sibling claims store."""
    from scripts.platformkit.intel_query.ask import discover_claim_source_pairs

    pairs = discover_claim_source_pairs()
    names = {c.name for _v, c in pairs}
    assert "nba_schedule_claims.jsonl" in names
