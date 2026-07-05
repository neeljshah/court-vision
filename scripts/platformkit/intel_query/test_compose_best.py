"""Per-file tests for intel_query.compose_best (the ONE-CONCLUSION composer).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_query/test_compose_best.py -q

Acceptance criteria:
  1. Rule hierarchy: the primary axis is decided by the LIVE gate verdict
     file, not hardcoded -- flipping the verdict on disk flips which
     VERIFIED claim becomes primary/conclusion.
  2. Fail-closed UNANSWERABLE when the primary claim (or verdict file, or
     verdict->claim mapping) is missing/not VERIFIED -- never a guessed name.
  3. Honest disagreement note fires when an attribution axis's own #1
     differs from the primary axis's #1, citing why the primary still wins.
  4. edge_claimed is always False.
  5. provenance lists every claim actually consumed (primary + each
     available attribution axis), each with a VERIFIED evidence entry.
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.intel_query import ask as ask_mod
from scripts.platformkit.intel_query import compose_best as cb_mod


def _ranking_claim(claim_id: str, metric: str, ranking: list[dict], value_field: str = "value") -> dict:
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": f"Top by {metric}?",
        "criteria": {"metric": metric, "formula": f"{metric}_formula", "entity_key": "player_id"},
        "ranking": ranking,
        "source_files": [f"data/fake/{claim_id}.parquet"],
        "computed_at": "2026-07-05T00:00:00+00:00",
        "n_considered": 50,
        "n_excluded_below_floor": 5,
        "caveats": [f"{claim_id} fixture caveat"],
    }


_PRIMARY_A = "fixture_primary_naive"
_PRIMARY_B = "fixture_primary_richer"
_ATTRIB_QUALITY = "fixture_quality_v1"


@pytest.fixture
def fixture_claims(tmp_path, monkeypatch):
    """Two candidate primary claims (A=naive-style top=Alpha, B=richer-style
    top=Beta) plus one attribution axis claim (quality, top=Beta -- disagrees
    with primary A's #1). All three VERIFIED. The verdict file starts
    pointing at A via _ASPECT_CONFIGS' declared mapping."""
    claims_path = tmp_path / "claims.jsonl"
    validation_path = tmp_path / "validation.json"

    primary_a = _ranking_claim(_PRIMARY_A, "naive_comp", [
        {"rank": 1, "player_id": 1, "player_name": "Alpha Player", "value": 0.70, "n": 40},
        {"rank": 2, "player_id": 2, "player_name": "Beta Player", "value": 0.65, "n": 40},
    ])
    primary_b = _ranking_claim(_PRIMARY_B, "richer_comp", [
        {"rank": 1, "player_id": 2, "player_name": "Beta Player", "value": 0.90, "n": 40},
        {"rank": 2, "player_id": 1, "player_name": "Alpha Player", "value": 0.80, "n": 40},
    ])
    attrib_quality = _ranking_claim(_ATTRIB_QUALITY, "quality_v1", [
        {"rank": 1, "player_id": 2, "player_name": "Beta Player", "value": 0.95, "n": 40},
        {"rank": 2, "player_id": 1, "player_name": "Alpha Player", "value": 0.50, "n": 40},
    ])

    with open(claims_path, "w", encoding="ascii") as f:
        for row in (primary_a, primary_b, attrib_quality):
            f.write(json.dumps(row) + "\n")

    validation_summary = {
        "component": "fixture_validation",
        "n_claims": 3,
        "details": [
            {"claim_id": _PRIMARY_A, "verdict": "VERIFIED", "reason": "ok"},
            {"claim_id": _PRIMARY_B, "verdict": "VERIFIED", "reason": "ok"},
            {"claim_id": _ATTRIB_QUALITY, "verdict": "VERIFIED", "reason": "ok"},
        ],
    }
    validation_path.write_text(json.dumps(validation_summary), encoding="ascii")

    monkeypatch.setattr(ask_mod, "CLAIM_SOURCE_PAIRS", ((validation_path, claims_path),))
    return claims_path, validation_path


def _fixture_config(verdict_file, verdict_to_primary=None):
    return cb_mod._AspectConfig(
        verdict_file=verdict_file,
        verdict_to_primary_claim=verdict_to_primary or {
            "REJECT_B": _PRIMARY_A,
            "SHIP_B": _PRIMARY_B,
        },
        attribution_axes=(
            cb_mod._AttributionAxis("quality_rank", _ATTRIB_QUALITY),
        ),
    )


@pytest.fixture
def fixture_aspect(tmp_path, monkeypatch, fixture_claims):
    verdict_file = tmp_path / "verdict.json"
    verdict_file.write_text(json.dumps({"verdict": "REJECT_B"}), encoding="ascii")
    config = _fixture_config(verdict_file)
    monkeypatch.setattr(cb_mod, "_ASPECT_CONFIGS", {"fixture_aspect": config})
    return verdict_file


# --- rule hierarchy: verdict file flip flips the primary ---------------------

def test_verdict_selects_primary_axis_and_conclusion(fixture_aspect):
    result = cb_mod.compose_best("fixture_aspect")
    assert result["conclusion"] == "Alpha Player"
    assert result["primary"]["claim_id"] == _PRIMARY_A
    assert result["primary"]["gate_verdict"] == "REJECT_B"
    assert result["composition_rule"] == cb_mod.COMPOSITION_RULE


def test_flipping_verdict_file_flips_primary_and_conclusion(fixture_aspect):
    # same aspect config, same claims -- ONLY the verdict on disk changes.
    fixture_aspect.write_text(json.dumps({"verdict": "SHIP_B"}), encoding="ascii")
    result = cb_mod.compose_best("fixture_aspect")
    assert result["conclusion"] == "Beta Player"
    assert result["primary"]["claim_id"] == _PRIMARY_B
    assert result["primary"]["gate_verdict"] == "SHIP_B"


# --- fail-closed UNANSWERABLE ------------------------------------------------

def test_unknown_aspect_is_unanswerable(fixture_aspect):
    result = cb_mod.compose_best("no_such_aspect")
    assert result["status"] == "UNANSWERABLE"
    assert result["edge_claimed"] is False
    assert "no_such_aspect" in result["missing"][0] or "no declared composition config" in result["missing"][0]


def test_missing_verdict_file_is_unanswerable(tmp_path, monkeypatch, fixture_claims):
    missing_verdict = tmp_path / "does_not_exist.json"
    config = _fixture_config(missing_verdict)
    monkeypatch.setattr(cb_mod, "_ASPECT_CONFIGS", {"fixture_aspect": config})
    result = cb_mod.compose_best("fixture_aspect")
    assert result["status"] == "UNANSWERABLE"
    assert "verdict file unavailable" in result["missing"][0]


def test_unmapped_verdict_value_is_unanswerable(tmp_path, monkeypatch, fixture_claims):
    verdict_file = tmp_path / "verdict.json"
    verdict_file.write_text(json.dumps({"verdict": "SOME_UNMAPPED_VERDICT"}), encoding="ascii")
    config = _fixture_config(verdict_file)
    monkeypatch.setattr(cb_mod, "_ASPECT_CONFIGS", {"fixture_aspect": config})
    result = cb_mod.compose_best("fixture_aspect")
    assert result["status"] == "UNANSWERABLE"
    assert "no declared primary-claim mapping" in result["missing"][0]


def test_primary_claim_not_verified_is_unanswerable(tmp_path, monkeypatch, fixture_claims):
    verdict_file = tmp_path / "verdict.json"
    verdict_file.write_text(json.dumps({"verdict": "REJECT_NOT_WIRED"}), encoding="ascii")
    config = cb_mod._AspectConfig(
        verdict_file=verdict_file,
        verdict_to_primary_claim={"REJECT_NOT_WIRED": "claim_id_that_does_not_exist"},
        attribution_axes=(),
    )
    monkeypatch.setattr(cb_mod, "_ASPECT_CONFIGS", {"fixture_aspect": config})
    result = cb_mod.compose_best("fixture_aspect")
    assert result["status"] == "UNANSWERABLE"
    assert "claim_id_that_does_not_exist" in result["missing"][0]
    # never a guessed name anywhere in the unanswerable payload
    assert "conclusion" not in result


# --- honest disagreement -----------------------------------------------------

def test_disagreement_fires_when_attribution_axis_disagrees(fixture_aspect):
    # primary A's #1 is Alpha; attribution axis (quality) ranks Beta #1 --
    # a genuine disagreement that must be surfaced, not suppressed.
    result = cb_mod.compose_best("fixture_aspect")
    assert len(result["disagreements"]) == 1
    d = result["disagreements"][0]
    assert d["axis"] == "quality_rank"
    assert d["top_name"] == "Beta Player"
    assert "REJECT_B" in d["why_primary_wins"]


def test_no_disagreement_when_axes_agree(tmp_path, monkeypatch, fixture_claims):
    # richer (B) is primary AND happens to match quality's own #1 (Beta) --
    # no disagreement should be manufactured when there isn't one.
    verdict_file = tmp_path / "verdict.json"
    verdict_file.write_text(json.dumps({"verdict": "SHIP_B"}), encoding="ascii")
    config = _fixture_config(verdict_file)
    monkeypatch.setattr(cb_mod, "_ASPECT_CONFIGS", {"fixture_aspect": config})
    result = cb_mod.compose_best("fixture_aspect")
    assert result["conclusion"] == "Beta Player"
    assert result["disagreements"] == []
    attrib = result["attribution"][0]
    assert attrib["top_name_if_different"] is None


def test_attribution_axis_unavailable_annotates_not_verified(tmp_path, monkeypatch, fixture_claims):
    verdict_file = tmp_path / "verdict.json"
    verdict_file.write_text(json.dumps({"verdict": "REJECT_B"}), encoding="ascii")
    config = cb_mod._AspectConfig(
        verdict_file=verdict_file,
        verdict_to_primary_claim={"REJECT_B": _PRIMARY_A},
        attribution_axes=(cb_mod._AttributionAxis("ghost_axis", "claim_id_never_verified"),),
    )
    monkeypatch.setattr(cb_mod, "_ASPECT_CONFIGS", {"fixture_aspect": config})
    result = cb_mod.compose_best("fixture_aspect")
    # conclusion still resolves -- an unavailable ATTRIBUTION axis never
    # blocks the primary answer, only the primary claim is load-bearing.
    assert result["conclusion"] == "Alpha Player"
    assert result["attribution"] == [
        {"axis": "ghost_axis", "claim_id": "claim_id_never_verified", "status": "not_verified"}
    ]
    assert result["disagreements"] == []


# --- edge_claimed + provenance -----------------------------------------------

def test_edge_claimed_always_false(fixture_aspect):
    result = cb_mod.compose_best("fixture_aspect")
    assert result["edge_claimed"] is False


def test_provenance_lists_primary_and_every_available_attribution_claim(fixture_aspect):
    result = cb_mod.compose_best("fixture_aspect")
    claim_ids = {e["claim_id"] for e in result["provenance"]}
    assert claim_ids == {_PRIMARY_A, _ATTRIB_QUALITY}
    for e in result["provenance"]:
        assert e["validator_verdict"] == "VERIFIED"
        assert e["source_files"]


def test_caveats_propagated_from_primary_and_attribution_claims(fixture_aspect):
    result = cb_mod.compose_best("fixture_aspect")
    assert f"{_PRIMARY_A} fixture caveat" in result["caveats"]
    assert f"{_ATTRIB_QUALITY} fixture caveat" in result["caveats"]


def test_computed_at_present(fixture_aspect):
    result = cb_mod.compose_best("fixture_aspect")
    assert result["computed_at"]


# --- ask.py best-X hook -------------------------------------------------------

def test_ask_routes_singular_best_shooter_to_compose_best(monkeypatch):
    called = {}

    def _fake_compose_best(aspect):
        called["aspect"] = aspect
        return {"aspect": aspect, "conclusion": "Fixture Winner", "edge_claimed": False}

    monkeypatch.setattr(
        "scripts.platformkit.intel_query.compose_best.compose_best", _fake_compose_best
    )
    result = ask_mod.ask("who is the best shooter, all factors weighed?")
    assert result["family"] == ask_mod.FAMILY_BEST
    assert result["conclusion"] == "Fixture Winner"
    assert called["aspect"] == "shooter"


def test_ask_top_n_best_shooters_phrasing_is_not_hijacked_by_best_hook(monkeypatch):
    # "top 5 best shooters" must still fall through to the pre-existing
    # top_n family dispatch -- the best-X hook must not intercept it.
    called = {"hit": False}

    def _fake_compose_best(aspect):
        called["hit"] = True
        return {"aspect": aspect, "conclusion": "should not be reached"}

    monkeypatch.setattr(
        "scripts.platformkit.intel_query.compose_best.compose_best", _fake_compose_best
    )
    result = ask_mod.ask("Who are the top 5 best shooters (composite) in window=last_20?")
    assert called["hit"] is False
    assert result.get("family") != ask_mod.FAMILY_BEST


def test_ask_unrecognized_best_x_falls_through(monkeypatch):
    called = {"hit": False}

    def _fake_compose_best(aspect):
        called["hit"] = True
        return {}

    monkeypatch.setattr(
        "scripts.platformkit.intel_query.compose_best.compose_best", _fake_compose_best
    )
    result = ask_mod.ask("who is the best rebounder in the league?")
    assert called["hit"] is False
    assert result.get("family") != ask_mod.FAMILY_BEST
