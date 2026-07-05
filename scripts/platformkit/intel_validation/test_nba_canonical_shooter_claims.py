"""Per-file tests for nba_canonical_shooter_claims (one-conclusion-composer wave).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_canonical_shooter_claims.py -q

Acceptance criteria:
  1. Contract shape: kind="ranking", entity_key="player_id", full ordered
     ranking (rank 1..n, contiguous), top_name matches ranking[0].
  2. Floors: min_sample/floors reuse QUALIFY_MIN_GAMES/QUALIFY_MIN_FGA
     imported from domains.basketball_nba.quality_indices, never fresh
     literals; a row below either floor never appears in the pool at all
     (it was excluded by load_qualifying_factor_table upstream).
  3. Formula string: criteria.formula is built from the imported
     NAIVE_WEIGHTS dict (0.55/0.30/0.15), not re-typed literals -- changing
     NAIVE_WEIGHTS changes the emitted formula string.
  4. Validator VERIFIED end-to-end on a small synthetic fixture (zero
     dependence on real parquet data): claims_validator.validate_claim
     independently recomputes naive_comp straight from criteria.formula +
     the snapshot parquet and matches the claimed ranking exactly.
  5. Honest caveats: the gate-verdict citation, the naive-metrics-blind-to-
     difficulty/gravity limitation (with real Curry/Ellis ranks), and
     edge_claimed=False are all present; no forbidden predictive/edge words.
  6. fg3m/fg3a fields: every ranking row carries fg3m/fg3a (additive, sourced
     via _attach_fg3m from the same season boxscore aggregate) -- ranking
     order/values/floors are untouched by their presence.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import nba_canonical_shooter_claims as csc
from domains.basketball_nba.quality_indices import NAIVE_WEIGHTS, QUALIFY_MIN_FGA, QUALIFY_MIN_GAMES

# Synthetic qualifying pool: 5 players, columns matching
# load_qualifying_factor_table()'s real output shape. naive_comp deliberately
# NOT precomputed here -- the module recomputes ranking from ts_pct/efg_pct/
# ft_pct via the SAME formula it emits, so a fixture with hand-picked values
# lets every rank be predicted by hand.
_FIXTURE_ROWS = [
    # player_id, name, games, fga, ts_pct, efg_pct, ft_pct
    (1, "Alice", 40, 300, 0.60, 0.55, 0.80),   # naive = .55*.60+.30*.55+.15*.80 = .615
    (2, "Bob", 40, 300, 0.70, 0.65, 0.90),      # naive = .55*.70+.30*.65+.15*.90 = .715  <- top
    (3, "Cara", 40, 300, 0.50, 0.45, 0.70),     # naive = .55*.50+.30*.45+.15*.70 = .515
    (4, "Dee", 40, 300, 0.65, 0.60, 0.85),      # naive = .55*.65+.30*.60+.15*.85 = .655
    (5, "Stephen Curry", 40, 300, 0.55, 0.50, 0.75),  # naive = .55*.55+.30*.50+.15*.75 = .565
]

# fg3m per fixture player_id -- deliberately distinct values so a test can
# assert the field is read from THIS table, not zeroed/hardcoded.
_FIXTURE_FG3M = {1: 50, 2: 90, 3: 10, 4: 120, 5: 200}


def _fixture_table() -> pd.DataFrame:
    df = pd.DataFrame(
        _FIXTURE_ROWS,
        columns=["player_id", "player_name", "games", "fga", "ts_pct", "efg_pct", "ft_pct"],
    )
    df["naive_comp"] = (
        NAIVE_WEIGHTS["ts_pct"] * df["ts_pct"]
        + NAIVE_WEIGHTS["efg_pct"] * df["efg_pct"]
        + NAIVE_WEIGHTS["ft_pct"] * df["ft_pct"]
    )
    df["fg3a"] = 100
    return df


def _fixture_attach_fg3m(t: pd.DataFrame, season: str) -> pd.DataFrame:
    """Stand-in for csc._attach_fg3m in tests: same additive-join contract
    (keyed on player_id) without touching real boxscore parquet data."""
    out = t.copy()
    out["fg3m"] = out["player_id"].map(_FIXTURE_FG3M)
    return out


@pytest.fixture()
def built_claim(monkeypatch, tmp_path):
    monkeypatch.setattr(csc, "load_qualifying_factor_table", lambda season=None: _fixture_table())
    monkeypatch.setattr(csc, "_attach_fg3m", _fixture_attach_fg3m)
    monkeypatch.setattr(csc, "_SNAPSHOT_PATH", tmp_path / "snap.parquet")
    monkeypatch.setattr(csc, "REPO_ROOT", tmp_path.parent)
    # rank_of is a plain pandas helper imported from quality_claim_builders;
    # it operates on whatever DataFrame is passed in, so it works unmodified
    # against the fixture table -- no monkeypatch needed for it.
    claim = csc.build_canonical_shooter_claim(season="fixture")
    return claim, tmp_path


def test_contract_shape_and_top_name(built_claim):
    claim, _tmp_path = built_claim
    assert claim["kind"] == "ranking"
    assert claim["criteria"]["entity_key"] == "player_id"
    ranks = [r["rank"] for r in claim["ranking"]]
    assert ranks == list(range(1, len(ranks) + 1))  # contiguous, full ordering
    assert len(claim["ranking"]) == 5  # every fixture row qualifies (no floor exclusion)
    assert claim["top_name"] == "Bob"  # highest naive_comp by hand-computation
    assert claim["ranking"][0]["player_name"] == "Bob"
    assert claim["n_considered"] == 5
    assert claim["n_excluded_below_floor"] == 0


def test_floors_reused_not_reinvented(built_claim):
    claim, _tmp_path = built_claim
    assert claim["criteria"]["floors"] == {"min_games": QUALIFY_MIN_GAMES, "min_fga": QUALIFY_MIN_FGA}
    assert claim["criteria"]["min_sample"] == {"games": QUALIFY_MIN_GAMES, "fga": QUALIFY_MIN_FGA}
    # floors identical to the imported constants, not fresh literals
    assert QUALIFY_MIN_GAMES == 20
    assert QUALIFY_MIN_FGA == 200


def test_formula_string_matches_imported_weights(built_claim):
    claim, _tmp_path = built_claim
    formula = claim["criteria"]["formula"]
    assert f"{NAIVE_WEIGHTS['ts_pct']}*ts_pct" in formula
    assert f"{NAIVE_WEIGHTS['efg_pct']}*efg_pct" in formula
    assert f"{NAIVE_WEIGHTS['ft_pct']}*ft_pct" in formula
    assert claim["criteria"]["weights"] == NAIVE_WEIGHTS


def test_ranking_values_match_hand_computed_naive_comp(built_claim):
    claim, _tmp_path = built_claim
    by_name = {r["player_name"]: r["value"] for r in claim["ranking"]}
    assert by_name["Bob"] == round(0.55 * 0.70 + 0.30 * 0.65 + 0.15 * 0.90, 4)
    assert by_name["Alice"] == round(0.55 * 0.60 + 0.30 * 0.55 + 0.15 * 0.80, 4)
    assert by_name["Cara"] == round(0.55 * 0.50 + 0.30 * 0.45 + 0.15 * 0.70, 4)


def test_face_validity_diagnostic_present_and_reported(built_claim):
    claim, _tmp_path = built_claim
    fv = claim["face_validity_diagnostic"]
    assert fv["type"] == "reported_never_a_fitting_target"
    # Stephen Curry is rank 4/5 by hand-computation in this fixture (naive
    # .565 beats only Cara's .515) -- confirms the diagnostic looks up the
    # ACTUAL rank, not a hardcoded value.
    assert fv["stephen_curry_rank"] == 4
    assert fv["n_qualifying"] == 5


def test_validator_independently_reverifies(built_claim, monkeypatch):
    claim, tmp_path = built_claim
    monkeypatch.setattr(claims_validator, "REPO_ROOT", tmp_path.parent)
    verdict = claims_validator.validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_fg3m_fg3a_present_on_every_ranking_row(built_claim):
    claim, _tmp_path = built_claim
    by_name = {r["player_name"]: (r["fg3m"], r["fg3a"]) for r in claim["ranking"]}
    # sourced from _FIXTURE_FG3M (per player_id) + fixture's flat fg3a=100 --
    # confirms the values are READ from the attached table, not hardcoded.
    assert by_name["Alice"] == (50, 100)
    assert by_name["Bob"] == (90, 100)
    assert by_name["Stephen Curry"] == (200, 100)
    for r in claim["ranking"]:
        assert isinstance(r["fg3m"], int)
        assert isinstance(r["fg3a"], int)


def test_no_forbidden_words_and_required_caveats_present(built_claim):
    claim, _tmp_path = built_claim
    # Ban roi/pnl/$/bankroll everywhere, and ban "edge" EXCEPT inside the
    # mandated edge_claimed:false field itself (every sibling claim under
    # this contract carries that exact field name; the ban targets edge
    # LANGUAGE in prose, not the required boolean field name).
    caveats_blob = json.dumps(claim["caveats"]).lower()
    question_blob = claim["question"].lower()
    for word in ("roi", "pnl", "$", "bankroll", "edge"):
        assert word not in caveats_blob
        assert word not in question_blob
    assert claim["edge_claimed"] is False
    blob = json.dumps(claim).lower()
    assert "reject" in blob
    assert "reject_naive_stays_canonical" in blob
    assert "quality_validity_gate_verdict.json" in blob
    assert "difficulty" in blob and "gravity" in blob
    assert "face-validity" in blob or "face_validity" in blob
