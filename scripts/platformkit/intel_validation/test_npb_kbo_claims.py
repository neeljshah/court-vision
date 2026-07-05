"""Per-file tests for npb_kbo_claims (+ its io/home_away siblings), lane
npb-kbo-strength-claims.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_npb_kbo_claims.py -q

Acceptance criteria:
  1. build_team_strength_table computes wins/decided_games/run_diff/home-away
     splits correctly on a small fixture, with ties correctly excluded from
     decided_games (neither a win nor a loss).
  2. min_sample floor (n_games>=30) excludes a below-floor team; excluded
     count matches n_excluded_below_floor.
  3. FULL POPULATION: no top-N cap.
  4. npb_rowcount_check: True on a 3964-row fixture, False on a mismatched
     count (proves the wave-42 rebuild guard actually gates, not decorative).
  5. All 8 real-corpus claims (KBO x4, NPB x4) independently re-verify via
     claims_validator.validate_claim -> VERIFIED against the REAL on-disk
     kbo_results.parquet / npb_results.parquet snapshots -- proves
     reproducibility, not just self-consistency.
  6. every emitted claim's caveats disclaim predictor/edge/calibration
     status and cite the separate, unchanged pregame/ingame gate verdicts.
  7. home_win_pct vs away_win_pct are the SAME team's split (not two
     independent populations) -- both present for every qualifying team.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import npb_kbo_claims as nk
from scripts.platformkit.intel_validation import npb_kbo_claims_home_away as home_away
from scripts.platformkit.intel_validation.claims_validator import validate_claim
from scripts.platformkit.intel_validation.npb_kbo_claims_io import build_team_strength_table


def _fixture_games() -> pd.DataFrame:
    """4 teams, small game set: A dominates home, B dominates away, C is a
    .500 team, D has exactly one tie (excluded from decided_games)."""
    rows = [
        # A (home) beats B (away) twice, loses once
        {"date": "2026-01-01", "season": "2026", "home_team": "A", "away_team": "B",
         "home_score": 5.0, "away_score": 2.0, "home_win": 1.0, "tied": False},
        {"date": "2026-01-02", "season": "2026", "home_team": "A", "away_team": "B",
         "home_score": 4.0, "away_score": 1.0, "home_win": 1.0, "tied": False},
        {"date": "2026-01-03", "season": "2026", "home_team": "A", "away_team": "B",
         "home_score": 1.0, "away_score": 3.0, "home_win": 0.0, "tied": False},
        # B (home) beats A (away) twice
        {"date": "2026-01-04", "season": "2026", "home_team": "B", "away_team": "A",
         "home_score": 6.0, "away_score": 2.0, "home_win": 1.0, "tied": False},
        {"date": "2026-01-05", "season": "2026", "home_team": "B", "away_team": "A",
         "home_score": 3.0, "away_score": 1.0, "home_win": 1.0, "tied": False},
        # C (home) vs D (away): a tie -- excluded from decided_games/wins
        {"date": "2026-01-06", "season": "2026", "home_team": "C", "away_team": "D",
         "home_score": 3.0, "away_score": 3.0, "home_win": None, "tied": True},
        # C (home) beats D (away)
        {"date": "2026-01-07", "season": "2026", "home_team": "C", "away_team": "D",
         "home_score": 4.0, "away_score": 2.0, "home_win": 1.0, "tied": False},
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["home_win"] = df["home_win"].astype("float64")
    return df


def test_build_team_strength_table_wins_and_run_diff():
    table = build_team_strength_table(_fixture_games()).set_index("team")
    # A: 3 games as home (2W1L) + 2 games as away (0W2L) = 5 games, 2 wins overall
    assert table.loc["A", "games"] == 5
    assert table.loc["A", "wins"] == 2
    assert table.loc["A", "decided_games"] == 5
    assert table.loc["A", "runs_for"] == 5 + 4 + 1 + 2 + 1  # home_score rows + away_score rows
    assert table.loc["A", "runs_against"] == 2 + 1 + 3 + 6 + 3


def test_build_team_strength_table_tie_excluded_from_decided_games():
    table = build_team_strength_table(_fixture_games()).set_index("team")
    # C played 2 games as home (1 tie + 1 win): games=2, but decided_games=1 (tie excluded)
    assert table.loc["C", "home_games"] == 2
    assert table.loc["C", "home_decided_games"] == 1
    assert table.loc["C", "home_wins"] == 1
    # D played 2 games as away (1 tie + 1 loss): decided_games=1, wins=0
    assert table.loc["D", "away_games"] == 2
    assert table.loc["D", "away_decided_games"] == 1
    assert table.loc["D", "away_wins"] == 0


def test_build_team_strength_table_home_away_split_independent_of_overall():
    table = build_team_strength_table(_fixture_games()).set_index("team")
    # A: home_wins=2/3, away_wins=0/2 -- home and away splits differ from each other
    assert table.loc["A", "home_wins"] == 2
    assert table.loc["A", "home_decided_games"] == 3
    assert table.loc["A", "away_wins"] == 0
    assert table.loc["A", "away_decided_games"] == 2


def test_min_sample_floor_excludes_below_floor_team():
    """Teams with < min_n games must be excluded from the ranking and
    counted in n_excluded_below_floor. C and D each have games=2 (their only
    meeting is a 2-game set) -- both below a floor of 3; A and B (5 games
    each) both clear it."""
    table = build_team_strength_table(_fixture_games())
    table["win_pct"] = table["wins"] / table["decided_games"]
    ranking, n_considered, n_excluded = nk.rank_desc(
        table, value_col="win_pct", n_col="games", min_n=3,
    )
    ranked_teams = {r["team"] for r in ranking}
    assert ranked_teams == {"A", "B"}
    assert n_excluded == 2
    assert n_considered == 4  # A, B, C, D all considered; C and D excluded


def test_full_population_no_top_n_cap(monkeypatch, tmp_path):
    """A fixture with 60 qualifying teams (well past any historical top-N
    cap) must all appear ranked, proving there is no cap."""
    rows = []
    for i in range(60):
        rows.append({
            "date": "2026-01-01", "season": "2026",
            "home_team": f"T{i}", "away_team": f"T{(i + 1) % 60}",
            "home_score": float(i + 1), "away_score": float(i),
            "home_win": 1.0, "tied": False,
        })
    games = pd.DataFrame(rows)
    games["date"] = pd.to_datetime(games["date"])
    table = build_team_strength_table(games)
    ranking, n_considered, n_excluded = nk.rank_desc(
        table.assign(win_pct=table["wins"] / table["decided_games"].replace(0, 1)),
        value_col="win_pct", n_col="games", min_n=0,
    )
    assert n_considered == 60
    assert n_excluded == 0
    assert len(ranking) == 60


def test_npb_rowcount_check_true_on_matching_fixture(tmp_path):
    df = pd.DataFrame({"x": range(nk.NPB_EXPECTED_ROWCOUNT)})
    path = tmp_path / "npb_fixture.parquet"
    df.to_parquet(path)
    matches, n = nk.npb_rowcount_check(path)
    assert matches is True
    assert n == nk.NPB_EXPECTED_ROWCOUNT


def test_npb_rowcount_check_false_on_mismatched_fixture(tmp_path):
    df = pd.DataFrame({"x": range(100)})
    path = tmp_path / "npb_fixture_bad.parquet"
    df.to_parquet(path)
    matches, n = nk.npb_rowcount_check(path)
    assert matches is False
    assert n == 100


def test_no_predictor_or_edge_language_in_caveats():
    """HARD RAIL: every emitted claim must disclaim predictor/gate/edge
    status and cite the separate, unchanged pregame/ingame gate verdicts."""
    caveats = nk.base_caveats("KBO", "2026-07-04", "win_pct")
    caveats_text = " ".join(caveats).lower()
    assert "descriptive" in caveats_text
    assert "not a predictor" in caveats_text
    assert "market/$ edge" in caveats_text
    assert "separate" in caveats_text
    assert "pregame_gate_verdict.json" in caveats_text


def test_ascii_safe_never_raises_on_non_ascii_team_code():
    japanese_team = "ソフトバンク"
    safe = nk._ascii_safe(japanese_team)
    assert safe.isascii()
    safe.encode("ascii")  # never raises


# --- real on-disk corpus: independent re-verification ------------------------

@pytest.fixture(scope="module")
def real_league_claims() -> dict[str, dict]:
    matches, n = nk.npb_rowcount_check()
    assert matches, f"NPB corpus row count {n} != expected {nk.NPB_EXPECTED_ROWCOUNT}"
    kbo_claims = nk.build_league_claims("KBO", nk._KBO_RESULTS, nk._KBO_SNAPSHOT_OUT)
    npb_claims = nk.build_league_claims("NPB", nk._NPB_RESULTS, nk._NPB_SNAPSHOT_OUT)
    return {c["claim_id"]: c for c in (*kbo_claims, *npb_claims)}


def test_real_npb_corpus_matches_wave42_rowcount():
    matches, n = nk.npb_rowcount_check()
    assert matches is True
    assert n == 3964


@pytest.mark.parametrize("league", ["kbo", "npb"])
@pytest.mark.parametrize("dim", ["win_pct", "run_diff_per_game", "home_win_pct", "away_win_pct"])
def test_real_claim_independently_verifies(real_league_claims, league, dim):
    claim = next(
        c for cid, c in real_league_claims.items()
        if cid.startswith(f"{league}_team_{dim}_full_asof_")
    )
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_kbo_all_10_teams_clear_floor(real_league_claims):
    win_pct_claim = next(
        c for cid, c in real_league_claims.items() if cid.startswith("kbo_team_win_pct_full_asof_")
    )
    assert win_pct_claim["n_considered"] == 10
    assert win_pct_claim["n_excluded_below_floor"] == 0
    assert len(win_pct_claim["ranking"]) == 10


def test_real_npb_two_teams_excluded_below_floor(real_league_claims):
    win_pct_claim = next(
        c for cid, c in real_league_claims.items() if cid.startswith("npb_team_win_pct_full_asof_")
    )
    assert win_pct_claim["n_considered"] == 14
    assert win_pct_claim["n_excluded_below_floor"] == 2
    assert len(win_pct_claim["ranking"]) == 12


def test_real_home_away_split_present_for_every_qualifying_team(real_league_claims):
    home_claim = next(
        c for cid, c in real_league_claims.items() if cid.startswith("kbo_team_home_win_pct_full_asof_")
    )
    away_claim = next(
        c for cid, c in real_league_claims.items() if cid.startswith("kbo_team_away_win_pct_full_asof_")
    )
    home_teams = {r["team"] for r in home_claim["ranking"]}
    away_teams = {r["team"] for r in away_claim["ranking"]}
    assert home_teams == away_teams  # same team population, both venue roles


def test_home_away_split_builder_produces_two_related_claims():
    snapshot_path = nk._KBO_SNAPSHOT_OUT
    if not snapshot_path.exists():
        nk.build_league_snapshot("KBO", nk._KBO_RESULTS, snapshot_path, nk._OUT_DIR)
    home_claim, away_claim = home_away.build_home_away_split_claims("KBO", snapshot_path, "2026-07-04", 10)
    assert home_claim["criteria"]["metric"] == "home_win_pct"
    assert away_claim["criteria"]["metric"] == "away_win_pct"
    assert home_claim["criteria"]["entity_key"] == away_claim["criteria"]["entity_key"] == "team"
