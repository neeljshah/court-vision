"""Per-file tests for nba_fit_sweep_claims (PROGRAM v3, lane fit-sweep).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_fit_sweep_claims.py -q

Acceptance criteria:
  1. A team missing a VERIFIED role-vacancy row lands in unanswerable_teams
     and never appears in the ranking; a team with < MIN_ROSTER_N roster
     rows IS written into the snapshot but excluded from the ranking by
     the n_roster floor (n_excluded_below_floor counts it, not
     unanswerable_teams).
  2. The target player's own pid is excluded from his own team's roster
     mean (archetype_complement would differ if he were wrongly folded in).
  3. scheme_fit uses SCHEME_TAG_PERIM_WEIGHT: a DROP COVERAGE team's
     scheme_fit == the player's rim_protect value (w=0.0).
  4. fit_score equals the hand-computed weighted sum (4dp).
  5. Cross-module independence: claims_validator.validate_claim (zero
     import of this producer) independently re-derives the ranking straight
     from criteria.formula + the materialized snapshot parquet -> VERIFIED.
  6. No forbidden predictive words appear in the claim JSON; the gate's
     REJECT citation IS present.
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import nba_fit_sweep_claims as fsc

PLAYER_PID = 2544

_PLAYER_ROW = {
    "rank": 1, "pid": PLAYER_PID, "player_name": "LeBron James", "team": "BOS",
    "value": 0.95, "n": None, "posgroup": "BIG", "archetype": "ROLE_BIG",
    "creation": 0.5, "playmaking": 0.5, "spacing": 0.5, "rim_pressure": 0.5,
    "rebounding": 0.5, "rim_protect": 0.6, "perimeter_d": 0.8, "self_create": 0.5,
    "usage_pct": 0.95, "scorer_pct": 0.9,
}


def _roster_row(rank: int, pid: int, team: str, val: float) -> dict:
    return {
        "rank": rank, "pid": pid, "player_name": f"P{pid}", "team": team,
        "value": 0.5, "n": None, "posgroup": "WING", "archetype": "ROLE_WING",
        "creation": val, "playmaking": val, "spacing": val, "rim_pressure": val,
        "rebounding": val, "rim_protect": val, "perimeter_d": val, "self_create": val,
        "usage_pct": 0.5, "scorer_pct": 0.5,
    }


def _archetype_claim() -> dict:
    ranking = [_PLAYER_ROW]
    ranking += [_roster_row(i, 100 + i, "BOS", 0.4) for i in range(3)]  # 3 mates, excl. player
    ranking += [_roster_row(i, 200 + i, "NYK", 0.5) for i in range(3)]  # 3 mates, full pop
    ranking += [_roster_row(i, 400 + i, "MIA", 0.3) for i in range(2)]  # missing vacancy row
    ranking += [_roster_row(i, 300 + i, "CHI", 0.3) for i in range(2)]  # below floor (n=2)
    return {
        "claim_id": fsc._ARCHETYPE_CLAIM_ID, "kind": "ranking", "question": "q",
        "criteria": {"entity_key": "pid"}, "ranking": ranking, "source_files": ["x.parquet"],
        "computed_at": "t", "n_considered": len(ranking), "n_excluded_below_floor": 0,
        "caveats": [],
    }


def _scheme_claim() -> dict:
    ranking = [
        {"rank": 1, "team": "BOS", "value": 0.1, "n": 20, "dominant_tag": "BALANCED",
         "best_scheme": None, "confidence": "high"},
        {"rank": 2, "team": "NYK", "value": 0.2, "n": 20, "dominant_tag": "DROP COVERAGE",
         "best_scheme": None, "confidence": "high"},
        {"rank": 3, "team": "MIA", "value": 0.3, "n": 20, "dominant_tag": "SWITCH HEAVY",
         "best_scheme": None, "confidence": "high"},
        {"rank": 4, "team": "CHI", "value": 0.4, "n": 20, "dominant_tag": "HELP DEFENSE",
         "best_scheme": None, "confidence": "high"},
    ]
    return {
        "claim_id": fsc._SCHEME_CLAIM_ID, "kind": "ranking", "question": "q",
        "criteria": {"entity_key": "team"}, "ranking": ranking, "source_files": ["y.parquet"],
        "computed_at": "t", "n_considered": len(ranking), "n_excluded_below_floor": 0,
        "caveats": [],
    }


def _vacancy_claim() -> dict:
    # MIA|BIG deliberately absent -> MIA must land in unanswerable_teams.
    ranking = [
        {"rank": 1, "team_posgroup": "BOS|BIG", "value": 0.6, "n": 5, "team": "BOS", "posgroup": "BIG"},
        {"rank": 2, "team_posgroup": "NYK|BIG", "value": 0.3, "n": 4, "team": "NYK", "posgroup": "BIG"},
        {"rank": 3, "team_posgroup": "CHI|BIG", "value": 0.5, "n": 3, "team": "CHI", "posgroup": "BIG"},
    ]
    return {
        "claim_id": fsc._VACANCY_CLAIM_ID, "kind": "ranking", "question": "q",
        "criteria": {"entity_key": "team_posgroup"}, "ranking": ranking, "source_files": ["z.parquet"],
        "computed_at": "t", "n_considered": len(ranking), "n_excluded_below_floor": 0,
        "caveats": [],
    }


def _verified() -> dict:
    return {
        fsc._ARCHETYPE_CLAIM_ID: _archetype_claim(),
        fsc._SCHEME_CLAIM_ID: _scheme_claim(),
        fsc._VACANCY_CLAIM_ID: _vacancy_claim(),
    }


@pytest.fixture()
def built_claim(monkeypatch, tmp_path):
    monkeypatch.setattr(fsc, "load_verified_claims", lambda: _verified())
    monkeypatch.setattr(fsc, "_SNAPSHOT_PATH", tmp_path / "snap.parquet")
    monkeypatch.setattr(fsc, "REPO_ROOT", tmp_path.parent)
    claim, unanswerable = fsc.build_sweep_snapshot(PLAYER_PID)
    return claim, unanswerable, tmp_path


def test_unanswerable_teams_and_floor_exclusion(built_claim):
    claim, unanswerable, _tmp_path = built_claim
    teams_in_ranking = {r["team"] for r in claim["ranking"]}
    unanswerable_teams = {u["team"] for u in unanswerable}

    assert "MIA" in unanswerable_teams  # no VERIFIED vacancy row for MIA|BIG
    assert "MIA" not in teams_in_ranking
    assert "CHI" not in teams_in_ranking  # only 2 roster rows -> below MIN_ROSTER_N
    assert "CHI" not in unanswerable_teams  # still IN the snapshot, excluded by the floor
    assert claim["n_excluded_below_floor"] == 1
    assert claim["n_considered"] == 3  # BOS, NYK, CHI reached the snapshot (MIA did not)
    assert teams_in_ranking == {"BOS", "NYK"}


def test_player_pid_excluded_from_own_team_roster_mean(built_claim):
    claim, _unanswerable, _tmp_path = built_claim
    bos = next(r for r in claim["ranking"] if r["team"] == "BOS")
    # roster mean over BOS's 3 mates (uniform 0.4, player pid EXCLUDED) ->
    # archetype_complement = mean(player[a]*(1-0.4)) = 0.6 * mean(player axes)
    mean_player_axes = sum(_PLAYER_ROW[a] for a in fsc.COMPLEMENT_AXES) / len(fsc.COMPLEMENT_AXES)
    expected = round(0.6 * mean_player_axes, 4)
    assert bos["archetype_complement"] == expected
    # if the player's own row (rim_protect=0.6, perimeter_d=0.8) had been folded
    # into the BOS roster mean, the mean would shift off 0.4 and this would fail


def test_scheme_fit_uses_declared_tag_map(built_claim):
    claim, _unanswerable, _tmp_path = built_claim
    nyk = next(r for r in claim["ranking"] if r["team"] == "NYK")
    # NYK's dominant_tag is DROP COVERAGE -> w=0.0 -> scheme_fit == rim_protect
    assert nyk["scheme_fit"] == round(_PLAYER_ROW["rim_protect"], 4)


def test_fit_score_matches_hand_computed_weighted_sum(built_claim):
    claim, _unanswerable, _tmp_path = built_claim
    bos = next(r for r in claim["ranking"] if r["team"] == "BOS")
    mean_player_axes = sum(_PLAYER_ROW[a] for a in fsc.COMPLEMENT_AXES) / len(fsc.COMPLEMENT_AXES)
    archetype_complement = 0.6 * mean_player_axes
    scheme_fit = 0.5 * _PLAYER_ROW["perimeter_d"] + 0.5 * _PLAYER_ROW["rim_protect"]  # BALANCED, w=0.5
    vacancy_share = 0.6
    expected = round(
        fsc.W_COMPLEMENT * archetype_complement
        + fsc.W_SCHEME * scheme_fit
        + fsc.W_VACANCY * vacancy_share,
        4,
    )
    assert bos["value"] == expected
    assert expected == 0.527


def test_validator_independently_reverifies(built_claim, monkeypatch):
    claim, _unanswerable, tmp_path = built_claim
    monkeypatch.setattr(claims_validator, "REPO_ROOT", tmp_path.parent)
    verdict = claims_validator.validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_no_forbidden_words_and_reject_citation_present(built_claim):
    claim, _unanswerable, _tmp_path = built_claim
    blob = json.dumps(claim).lower()
    for word in ("predict", "will improve", "expected gain", "edge"):
        assert word not in blob
    assert "reject" in blob
