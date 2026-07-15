import json
from pathlib import Path

from scripts.platformkit.showcase.lint_bundle import lint_bundle
from scripts.platformkit.showcase.rooms import claims, graveyard

BANNED_NUMBERS = ("18.38", "0.119", "78.11", "8.94", "54.57")


def test_claims_build_has_both_corpora():
    result = claims.build()
    assert "preregistered" in result and "verified_facts" in result

    pre = result["preregistered"]
    if pre.get("status") != "unavailable":
        assert pre["total"] > 0
        assert len(pre["sample"]) <= claims.SAMPLE_CAP
        for row in pre["sample"]:
            assert set(row) >= {"card_id", "claim", "sport", "verdict", "asof"}

    vf = result["verified_facts"]
    if vf.get("status") != "unavailable":
        assert vf["total"] > 0
        assert len(vf["sample"]) <= claims.SAMPLE_CAP
        for row in vf["sample"]:
            assert set(row) >= {"claim_id", "statement", "family", "verdict", "asof"}


def test_graveyard_rejects_mapped_and_gates_present():
    result = graveyard.build()
    assert "rejects" in result and "retractions" in result and "gate_verdicts" in result

    rejects = result["rejects"]
    if isinstance(rejects, list):
        assert len(rejects) <= graveyard.REJECT_CAP
        for r in rejects:
            assert set(r) >= {"hypothesis", "sport", "why_killed", "gate", "asof", "receipt"}
    else:
        assert rejects.get("status") == "unavailable"

    for gv in result["gate_verdicts"]:
        assert set(gv) >= {"name", "verdict", "why", "brier_base", "brier_layer",
                            "brier_delta", "n_games", "receipt"}


def test_retractions_have_no_banned_numeric_literals():
    result = graveyard.build()
    dumped = json.dumps(result["retractions"])
    for num in BANNED_NUMBERS:
        assert num not in dumped
    assert "+54%" not in dumped


def test_lint_passes_on_dumped_room_output(tmp_path: Path):
    claims_result = claims.build()
    graveyard_result = graveyard.build()

    (tmp_path / "claims_index.json").write_text(
        json.dumps(claims_result, default=str), encoding="utf-8")
    (tmp_path / "graveyard.json").write_text(
        json.dumps(graveyard_result, default=str), encoding="utf-8")

    violations = lint_bundle(tmp_path)
    assert violations == [], violations
