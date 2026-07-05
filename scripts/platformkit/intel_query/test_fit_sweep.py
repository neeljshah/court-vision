"""Per-file tests for intel_query.fit_sweep.compose_fit_sweep.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_query/test_fit_sweep.py -q

Acceptance criteria:
  1. Happy path: a VERIFIED sweep claim with 4 teams -> answerable,
     top_fits truncated to top_n, evidence carries the sweep claim_id,
     scouting_caveat cites the fit-validity gate's REJECT verdict.
  2. Sweep claim present in the producer JSONL but MISMATCH in its
     validation summary -> invisible to load_verified_claims() -> honest
     unanswerable naming missing_ingredient="sweep_claim".
  3. A sweep claim whose caveats contain a forbidden predictive word
     ("edge") -> honest unanswerable naming
     missing_ingredient="forbidden_word_guard".
  4. unanswerable_teams passes through into answer["unanswerable_teams"].
  5. Unicode team/tag strings in the ranking get ASCII-folded in output.
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.intel_query import ask as ask_mod
from scripts.platformkit.intel_query import fit_sweep

_SWEEP_CLAIM_ID = "nba_fit_sweep_lebron_james_current"


def _team_row(
    rank: int,
    team: str,
    value: float = 0.5,
    n: int = 20,
    archetype_complement: str = "COMPLEMENT",
    scheme_fit: str = "HIGH",
    vacancy_share: float = 0.4,
    dominant_tag: str = "SWITCH HEAVY",
    vacancy_n: int = 9,
) -> dict:
    return {
        "rank": rank, "team": team, "value": value, "n": n,
        "archetype_complement": archetype_complement, "scheme_fit": scheme_fit,
        "vacancy_share": vacancy_share, "dominant_tag": dominant_tag, "vacancy_n": vacancy_n,
    }


def _sweep_claim(
    teams: list[dict],
    unanswerable_teams: list[str] | None = None,
    declared_weights: dict | None = None,
    caveats: list[str] | None = None,
) -> dict:
    return {
        "claim_id": _SWEEP_CLAIM_ID,
        "kind": "ranking",
        "question": "Which teams fit LeBron James best?",
        "criteria": {"metric": "fit_score", "entity_key": "team"},
        "ranking": teams,
        "unanswerable_teams": unanswerable_teams if unanswerable_teams is not None else [],
        "declared_weights": declared_weights or {
            "scheme_fit": 0.4, "vacancy_share": 0.3, "archetype_complement": 0.3,
        },
        "source_files": ["data/fake/sweep.parquet"],
        "computed_at": "2026-07-05T00:00:00+00:00",
        "n_considered": 30,
        "n_excluded_below_floor": 0,
        "caveats": caveats if caveats is not None else ["fixture sweep caveat"],
    }


def _write_fixture(tmp_path, monkeypatch, sweep_row: dict, verdict: str = "VERIFIED"):
    claims_path = tmp_path / "sweep_claims.jsonl"
    validation_path = tmp_path / "sweep_claims_validation.json"
    with open(claims_path, "w", encoding="ascii") as f:
        f.write(json.dumps(sweep_row) + "\n")
    validation_summary = {
        "component": "sweep_claims_validation",
        "n_claims": 1,
        "details": [{"claim_id": sweep_row["claim_id"], "verdict": verdict, "reason": "test"}],
    }
    validation_path.write_text(json.dumps(validation_summary), encoding="ascii")
    monkeypatch.setattr(ask_mod, "CLAIM_SOURCE_PAIRS", ((validation_path, claims_path),))


def test_happy_path_answerable_with_evidence_and_caveat(tmp_path, monkeypatch):
    teams = [_team_row(i, f"T{i}") for i in range(1, 5)]
    _write_fixture(tmp_path, monkeypatch, _sweep_claim(teams))

    result = fit_sweep.compose_fit_sweep(top_n=10)
    assert result["answerable"] is True
    assert result["family"] == fit_sweep.FAMILY_FIT_SWEEP
    assert len(result["answer"]["top_fits"]) == min(10, 4)
    assert "REJECT" in result["answer"]["scouting_caveat"]
    claim_ids = {e["claim_id"] for e in result["evidence"]}
    assert _SWEEP_CLAIM_ID in claim_ids


def test_top_n_truncates_ranking(tmp_path, monkeypatch):
    teams = [_team_row(i, f"T{i}") for i in range(1, 5)]
    _write_fixture(tmp_path, monkeypatch, _sweep_claim(teams))

    result = fit_sweep.compose_fit_sweep(top_n=2)
    assert result["answerable"] is True
    assert len(result["answer"]["top_fits"]) == 2


def test_mismatch_verdict_is_honest_unanswerable(tmp_path, monkeypatch):
    teams = [_team_row(1, "T1")]
    _write_fixture(tmp_path, monkeypatch, _sweep_claim(teams), verdict="MISMATCH")

    result = fit_sweep.compose_fit_sweep()
    assert result["answerable"] is False
    assert result["missing_ingredient"] == "sweep_claim"


def test_forbidden_word_in_caveats_refuses(tmp_path, monkeypatch):
    teams = [_team_row(1, "T1")]
    sweep_row = _sweep_claim(teams, caveats=["this mentions edge somewhere"])
    _write_fixture(tmp_path, monkeypatch, sweep_row)

    result = fit_sweep.compose_fit_sweep()
    assert result["answerable"] is False
    assert result["missing_ingredient"] == "forbidden_word_guard"


def test_unanswerable_teams_passthrough(tmp_path, monkeypatch):
    teams = [_team_row(1, "T1")]
    sweep_row = _sweep_claim(teams, unanswerable_teams=["BOS", "MIA"])
    _write_fixture(tmp_path, monkeypatch, sweep_row)

    result = fit_sweep.compose_fit_sweep()
    assert result["answerable"] is True
    assert result["answer"]["unanswerable_teams"] == ["BOS", "MIA"]


def test_unicode_strings_are_ascii_folded(tmp_path, monkeypatch):
    accented_complement = "Complement" + chr(0x00e9)  # "Complemente" with an accented e
    accented_tag = "Sw" + chr(0x00ed) + "tch"  # "Switch" with an accented i
    accented_team = "Bost" + chr(0x00e9) + "on"  # "Bosteon" with an accented e
    teams = [_team_row(1, "ATL", archetype_complement=accented_complement, dominant_tag=accented_tag)]
    sweep_row = _sweep_claim(teams, unanswerable_teams=[accented_team])
    _write_fixture(tmp_path, monkeypatch, sweep_row)

    result = fit_sweep.compose_fit_sweep()
    assert result["answerable"] is True
    top = result["answer"]["top_fits"][0]
    assert top["archetype_complement"] == "Complemente"
    assert top["dominant_tag"] == "Switch"
    assert result["answer"]["unanswerable_teams"][0] == "Bosteon"
