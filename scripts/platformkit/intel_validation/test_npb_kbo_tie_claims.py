"""Per-file tests for npb_kbo_tie_claims (lane seed A6, paired NPB tie-rate /
KBO tie-run-environment claims).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_npb_kbo_tie_claims.py -q

Acceptance criteria:
  1. build_season_tie_table computes n/n_ties/tie_rate correctly per season
     on a small fixture (ties correctly counted, tie_rate = n_ties/n).
  2. build_ranking's min_sample floor excludes a below-floor season; excluded
     count matches n_excluded_below_floor; full population, no top-N cap.
  3. split_half_tie_rate reports the correct first-half/second-half rates
     and their absolute difference on a fixture with a known split.
  4. season_over_season_deltas + regime_boundary_flags: a >=2x swing is
     flagged, a stable series flags nothing (no hardcoded rule-change date).
  5. Both real-corpus claims (NPB tie-rate, KBO tie-run-env) independently
     re-verify via claims_validator.validate_claim -> VERIFIED against the
     real on-disk kbo_results.parquet / npb_results.parquet.
  6. Every emitted claim's caveats disclaim predictor/gate/edge status.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import npb_kbo_tie_claims as tc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_games(tmp_path):
    """3 seasons: 2022 (10 games, 1 tie), 2023 (10 games, 5 ties -- a big
    swing vs 2022), 2024 (5 games, 1 tie -- below a 10-game floor)."""
    rows = []
    for i in range(10):
        rows.append({"date": f"2022-04-{i + 1:02d}", "season": "2022",
                      "home_team": "A", "away_team": "B", "home_score": 3.0, "away_score": 3.0 if i == 0 else 1.0,
                      "home_win": None if i == 0 else 1.0, "tied": i == 0})
    for i in range(10):
        tied = i < 5
        rows.append({"date": f"2023-04-{i + 1:02d}", "season": "2023",
                      "home_team": "A", "away_team": "B", "home_score": 3.0, "away_score": 3.0 if tied else 1.0,
                      "home_win": None if tied else 1.0, "tied": tied})
    for i in range(5):
        rows.append({"date": f"2024-04-{i + 1:02d}", "season": "2024",
                      "home_team": "A", "away_team": "B", "home_score": 3.0, "away_score": 3.0 if i == 0 else 1.0,
                      "home_win": None if i == 0 else 1.0, "tied": i == 0})
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    path = tmp_path / "fixture_results.parquet"
    df.to_parquet(path)
    return path


def test_build_season_tie_table_counts_and_rate(tmp_path):
    path = _fixture_games(tmp_path)
    table = tc.build_season_tie_table(path).set_index("season")
    assert table.loc["2022", "n"] == 10
    assert table.loc["2022", "n_ties"] == 1
    assert table.loc["2022", "tie_rate"] == pytest.approx(0.1)
    assert table.loc["2023", "n_ties"] == 5
    assert table.loc["2023", "tie_rate"] == pytest.approx(0.5)


def test_build_ranking_min_sample_floor_excludes_below_floor_season(tmp_path):
    path = _fixture_games(tmp_path)
    table = tc.build_season_tie_table(path)
    ranking, n_considered, n_excluded = tc.build_ranking(table, "tie_rate", "n", min_n=10)
    ranked_seasons = {r["season"] for r in ranking}
    assert ranked_seasons == {"2022", "2023"}  # 2024 (n=5) excluded
    assert n_excluded == 1
    assert n_considered == 3


def test_build_ranking_full_population_no_top_n_cap(tmp_path):
    path = _fixture_games(tmp_path)
    table = tc.build_season_tie_table(path)
    ranking, n_considered, n_excluded = tc.build_ranking(table, "tie_rate", "n", min_n=0)
    assert n_considered == 3
    assert n_excluded == 0
    assert len(ranking) == 3


def test_split_half_tie_rate_matches_known_split(tmp_path):
    path = _fixture_games(tmp_path)
    # 25 games total ordered by date: 2022's 10 games (1 tie) then 2023's 10
    # (5 ties) then 2024's 5 (1 tie) -> first half (12 games) = all of 2022
    # (1 tie) + first 2 of 2023 (2 ties) = 3/12; second half (13 games) =
    # remaining 8 of 2023 (3 ties) + all of 2024 (1 tie) = 4/13.
    rate_a, rate_b, diff = tc.split_half_tie_rate(path)
    assert rate_a == pytest.approx(3 / 12, abs=1e-4)
    assert rate_b == pytest.approx(4 / 13, abs=1e-4)
    assert diff == pytest.approx(abs(rate_a - rate_b), abs=1e-4)


def test_season_over_season_deltas_and_regime_flag_detects_swing(tmp_path):
    path = _fixture_games(tmp_path)
    table = tc.build_season_tie_table(path)  # 2022 tie_rate=0.1, 2023=0.5 -> 5x swing
    deltas = tc.season_over_season_deltas(table)
    assert len(deltas) == 2  # 2022->2023, 2023->2024
    first = deltas[0]
    assert first["season_from"] == "2022" and first["season_to"] == "2023"
    assert first["ratio"] == pytest.approx(5.0, abs=1e-3)
    flags = tc.regime_boundary_flags(deltas)
    assert any(f["season_from"] == "2022" and f["season_to"] == "2023" for f in flags)


def test_regime_boundary_flags_empty_when_stable():
    stable_deltas = [
        {"season_from": "2022", "season_to": "2023", "tie_rate_from": 0.02, "tie_rate_to": 0.022, "ratio": 1.1},
        {"season_from": "2023", "season_to": "2024", "tie_rate_from": 0.022, "tie_rate_to": 0.019, "ratio": 0.864},
    ]
    assert tc.regime_boundary_flags(stable_deltas) == []


def test_no_predictor_or_edge_language_in_caveats():
    caveats = tc._common_caveats("KBO", "2026-07-04", tc._KBO_RESULTS)
    text = " ".join(caveats).lower()
    assert "descriptive" in text
    assert "not a predictor" in text
    assert "market/$ edge" in text
    assert "separate" in text
    assert "pregame_gate_verdict.json" in text


# --- real on-disk corpus: independent re-verification -----------------------

@pytest.fixture(scope="module")
def real_claims() -> dict[str, dict]:
    npb = tc.build_npb_tie_rate_claim()
    kbo = tc.build_kbo_tie_run_env_claim()
    return {c["claim_id"]: c for c in (npb, kbo)}


def test_real_npb_tie_rate_claim_verifies(real_claims):
    claim = next(c for cid, c in real_claims.items() if cid.startswith("npb_season_tie_rate_full_asof_"))
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_kbo_tie_rate_claim_verifies(real_claims):
    claim = next(c for cid, c in real_claims.items() if cid.startswith("kbo_season_tie_rate_full_asof_"))
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_claims_full_population_every_season_on_disk(real_claims):
    for claim in real_claims.values():
        assert claim["n_excluded_below_floor"] == 0
        raw = pd.read_parquet(tc._NPB_RESULTS if "npb" in claim["claim_id"] else tc._KBO_RESULTS)
        assert len(claim["ranking"]) == raw["season"].nunique()
