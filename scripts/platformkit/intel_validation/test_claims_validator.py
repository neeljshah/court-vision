"""Per-file tests for claims_validator's write_summary() numpy-safety, PLUS
the batch-validation parity + anti-fake tamper tests (spec sec 3 / sec 6).

Regression coverage for the honest catch: a MISMATCH first_divergence block
can carry a raw numpy scalar (e.g. recomputed_id straight off an int64
entity_key column) and write_summary()'s json.dump used to crash TypeError
persisting it. Fixed via a numpy-safe default= encoder at the json.dump site
only -- no verdict-logic change.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/intel_validation/test_claims_validator.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.platformkit.intel_validation.claims_validator import (
    ValidationSummary,
    validate_claim,
    validate_claims_file,
    validate_claims_file_batched,
    write_summary,
)


def _make_parquet(tmp_path: Path, name: str, rows: list[dict]) -> str:
    p = tmp_path / name
    pd.DataFrame(rows).to_parquet(p)
    return str(p)


def test_write_summary_persists_mismatch_with_numpy_int64_id(tmp_path):
    """int64 player_id source column -> recomputed_id in first_divergence is
    a raw np.int64. Before the fix, json.dump(payload) here raised
    TypeError: Object of type int64 is not JSON serializable."""
    rows = [
        {"player_id": 101, "player_name": "Alpha", "fg3_pct": 0.45, "fg3a": 300},
        {"player_id": 102, "player_name": "Bravo", "fg3_pct": 0.40, "fg3a": 250},
    ]
    src = _make_parquet(tmp_path, "shooting.parquet", rows)
    claim = {
        "claim_id": "top_fg3pct",
        "kind": "ranking",
        "question": "Who leads in 3pt%?",
        "criteria": {
            "metric": "fg3_pct", "formula": "fg3_pct", "window": "season",
            "min_sample": {"fg3a": 100}, "direction": "desc",
        },
        # PLANT: rank 1 claimed as player 102 despite 101 actually leading --
        # forces a MISMATCH first_divergence carrying recomputed_id=101 (np.int64).
        "ranking": [{"rank": 1, "player_id": 102, "player_name": "Bravo", "value": 0.40, "n": 250}],
        "source_files": [src],
        "computed_at": "2026-07-05T00:00:00+00:00",
        "n_considered": 2,
        "n_excluded_below_floor": 0,
        "caveats": [],
    }
    verdict = validate_claim(claim)
    assert verdict.verdict == "MISMATCH"
    recomputed_id = verdict.first_divergence["recomputed"]["player_id"]
    assert isinstance(recomputed_id, (np.integer,))  # confirms this test exercises the real numpy path

    summary = ValidationSummary(generated_at="2026-07-05T00:00:00+00:00")
    summary.n_claims = 1
    summary.n_mismatch = 1
    summary.details.append({
        "claim_id": verdict.claim_id,
        "verdict": verdict.verdict,
        "reason": verdict.reason,
        "first_divergence": verdict.first_divergence,
    })

    out_path = tmp_path / "out.json"
    write_summary(summary, out_path)  # must not raise

    payload = json.loads(out_path.read_text(encoding="ascii"))
    detail = payload["details"][0]
    assert detail["verdict"] == "MISMATCH"
    # numpy int64 round-tripped to a plain JSON int, value preserved exactly
    assert detail["first_divergence"]["recomputed"]["player_id"] == 101
    assert isinstance(detail["first_divergence"]["recomputed"]["player_id"], int)


def test_write_summary_persists_mismatch_with_numpy_float64_value(tmp_path):
    """A MISMATCH on a plain-value miscompare (not an id miscompare) also
    carries a numpy float64 for the recomputed value in some column dtypes;
    confirms the same default= hook round-trips floats too."""
    rows = [
        {"player_id": "1", "player_name": "A", "pts": np.float64(30.0), "reb": np.float64(10.0), "gp": 60},
        {"player_id": "2", "player_name": "B", "pts": np.float64(20.0), "reb": np.float64(5.0), "gp": 55},
    ]
    src = _make_parquet(tmp_path, "combo.parquet", rows)
    claim = {
        "claim_id": "pts_plus_reb",
        "kind": "ranking",
        "question": "Who has the highest pts+reb?",
        "criteria": {
            "metric": "pts_plus_reb", "formula": "pts + reb", "window": "season",
            "min_sample": {"gp": 10}, "direction": "desc",
        },
        # PLANT: claimed value inflated beyond tolerance -> MISMATCH on value, not id.
        "ranking": [{"rank": 1, "player_id": "1", "player_name": "A", "value": 999.0, "n": 60}],
        "source_files": [src],
        "computed_at": "2026-07-05T00:00:00+00:00",
        "n_considered": 2,
        "n_excluded_below_floor": 0,
        "caveats": [],
    }
    verdict = validate_claim(claim)
    assert verdict.verdict == "MISMATCH"

    summary = ValidationSummary(generated_at="2026-07-05T00:00:00+00:00")
    summary.n_claims = 1
    summary.n_mismatch = 1
    summary.details.append({
        "claim_id": verdict.claim_id, "verdict": verdict.verdict,
        "reason": verdict.reason, "first_divergence": verdict.first_divergence,
    })

    out_path = tmp_path / "out.json"
    write_summary(summary, out_path)  # must not raise

    payload = json.loads(out_path.read_text(encoding="ascii"))
    assert payload["details"][0]["first_divergence"]["recomputed"]["value"] == 40.0


# ---------------------------------------------------------------------------
# Batch validation parity + anti-fake tamper test (spec sec 3 / sec 6).
# This IS the hill: validate_claims_file_batched must produce the SAME
# per-claim verdict as looping validate_claim, and revalidation after a
# tampered source value must flip EXACTLY the affected claims to MISMATCH.
# ---------------------------------------------------------------------------

def _fixture_family(tmp_path):
    """Two source parquets (two recompute groups) covering: multiple
    entities per group, a VERIFIED claim, a deliberately planted MISMATCH
    claim, and a claim that sits below its own min_sample floor. Returns
    (claims_list, jsonl_path, season_src_path, career_src_path)."""
    season_rows = [
        {"player_id": 201, "player_name": "Alpha", "fg3_pct": 0.42, "fg3a": 320, "gp": 60},
        {"player_id": 202, "player_name": "Bravo", "fg3_pct": 0.38, "fg3a": 280, "gp": 58},
        {"player_id": 203, "player_name": "Charlie", "fg3_pct": 0.35, "fg3a": 50, "gp": 20},  # below fg3a floor
    ]
    career_rows = [
        {"player_id": 201, "player_name": "Alpha", "ast_to_tov": 2.5, "gp": 400},
        {"player_id": 202, "player_name": "Bravo", "ast_to_tov": 3.1, "gp": 380},
    ]
    season_src = _make_parquet(tmp_path, "season_shooting.parquet", season_rows)
    career_src = _make_parquet(tmp_path, "career_playmaking.parquet", career_rows)

    def _season_claim(claim_id, ranking):
        return {
            "claim_id": claim_id,
            "kind": "ranking",
            "question": "Who leads in 3pt%% this season?",
            "criteria": {
                "metric": "fg3_pct", "formula": "fg3_pct", "window": "season_2024_25",
                "min_sample": {"fg3a": 100}, "direction": "desc",
                "value_precision": 4, "entity_key": "player_id",
            },
            "ranking": ranking,
            "source_files": [season_src],
            "computed_at": "2026-07-06T00:00:00+00:00",
            "n_considered": 3,
            "n_excluded_below_floor": 1,
            "caveats": [],
        }

    def _career_claim(claim_id, ranking):
        return {
            "claim_id": claim_id,
            "kind": "ranking",
            "question": "Who leads in career AST/TOV?",
            "criteria": {
                "metric": "ast_to_tov", "formula": "ast_to_tov", "window": "career_to_date",
                "min_sample": {"gp": 40}, "direction": "desc",
                "value_precision": 4, "entity_key": "player_id",
            },
            "ranking": ranking,
            "source_files": [career_src],
            "computed_at": "2026-07-06T00:00:00+00:00",
            "n_considered": 2,
            "n_excluded_below_floor": 0,
            "caveats": [],
        }

    # Group A (season window): 2 claims sharing ONE recompute -- one VERIFIED
    # (correct top-2 ranking) and one MISMATCH (rank 1 claimed as the WRONG
    # entity -- Bravo instead of the actually-leading Alpha).
    claim_a_verified = _season_claim(
        "season_fg3pct_verified",
        [
            {"rank": 1, "player_id": 201, "player_name": "Alpha", "value": 0.42, "n": 320},
            {"rank": 2, "player_id": 202, "player_name": "Bravo", "value": 0.38, "n": 280},
        ],
    )
    claim_a_mismatch = _season_claim(
        "season_fg3pct_mismatch",
        [{"rank": 1, "player_id": 202, "player_name": "Bravo", "value": 0.38, "n": 280}],
    )
    # Group B (career window): shares NO recompute key with group A (different
    # formula/window/source) -- proves groups stay independent.
    claim_b_verified = _career_claim(
        "career_asttotov_verified",
        [{"rank": 1, "player_id": 202, "player_name": "Bravo", "value": 3.1, "n": 380}],
    )
    # Claim whose OWN min_sample floor (fg3a>=100) is never met by ANY row in
    # its group's below-floor entity, exercised via n_excluded_below_floor
    # cross-check (Charlie's 50 fg3a is correctly excluded upstream).
    claim_a_floor_check = _season_claim(
        "season_fg3pct_floor_check",
        [{"rank": 1, "player_id": 201, "player_name": "Alpha", "value": 0.42, "n": 320}],
    )

    claims = [claim_a_verified, claim_a_mismatch, claim_b_verified, claim_a_floor_check]
    jsonl_path = tmp_path / "family.jsonl"
    with open(jsonl_path, "w", encoding="ascii") as f:
        for c in claims:
            f.write(json.dumps(c) + "\n")
    return claims, jsonl_path, season_src, career_src


def test_batched_validation_matches_looping_validate_claim(tmp_path):
    """THE parity test: validate_claims_file_batched's per-claim verdicts
    must equal looping validate_claim, claim-by-claim, including the planted
    MISMATCH row. Compared by claim_id (not file-order position) since
    batching groups claims by recompute key and does not promise to
    preserve original emission order."""
    claims, jsonl_path, _, _ = _fixture_family(tmp_path)

    looped = {c["claim_id"]: validate_claim(c).verdict for c in claims}
    batched_summary = validate_claims_file_batched(jsonl_path)
    batched = {d["claim_id"]: d["verdict"] for d in batched_summary.details}

    assert batched.keys() == looped.keys()
    for claim_id, expected_verdict in looped.items():
        assert batched[claim_id] == expected_verdict, f"{claim_id}: batched={batched[claim_id]} looped={expected_verdict}"

    # Sanity: the fixture actually exercises both a MISMATCH and a VERIFIED,
    # not a vacuously-all-one-verdict fixture.
    assert looped["season_fg3pct_verified"] == "VERIFIED"
    assert looped["season_fg3pct_mismatch"] == "MISMATCH"
    assert looped["career_asttotov_verified"] == "VERIFIED"
    assert looped["season_fg3pct_floor_check"] == "VERIFIED"

    # Also cross-check against the existing whole-file looping entry point
    # (validate_claims_file) for the same claim_id -> verdict equality.
    file_summary = validate_claims_file(jsonl_path)
    file_verdicts = {d["claim_id"]: d["verdict"] for d in file_summary.details}
    assert file_verdicts == looped
    assert batched_summary.n_claims == len(claims)
    assert batched_summary.n_verified == 3
    assert batched_summary.n_mismatch == 1


def test_batched_validation_anti_fake_tamper_flips_only_affected_claims(tmp_path):
    """ANTI-FAKE test (spec sec 6): tamper ONE value in a fixture source
    parquet, then revalidate. EXACTLY the claims whose recompute depends on
    the tampered row must flip to MISMATCH -- proving the batched path
    genuinely re-reads live data instead of rubber-stamping declared values.
    Claims from the UNTOUCHED source (career window) must stay unaffected."""
    claims, jsonl_path, season_src, career_src = _fixture_family(tmp_path)

    before = validate_claims_file_batched(jsonl_path)
    before_verdicts = {d["claim_id"]: d["verdict"] for d in before.details}
    assert before_verdicts["season_fg3pct_verified"] == "VERIFIED"
    assert before_verdicts["season_fg3pct_floor_check"] == "VERIFIED"
    assert before_verdicts["career_asttotov_verified"] == "VERIFIED"

    # TAMPER: overwrite Alpha's fg3_pct in the season source so the claimed
    # rank-1 value (0.42) no longer matches a fresh recompute.
    season_df = pd.read_parquet(season_src)
    season_df.loc[season_df["player_id"] == 201, "fg3_pct"] = 0.05
    season_df.to_parquet(season_src)

    after = validate_claims_file_batched(jsonl_path)
    after_verdicts = {d["claim_id"]: d["verdict"] for d in after.details}

    # Claims whose ranking cites Alpha's now-wrong value MUST flip -- Alpha
    # (tampered to 0.05, now the WORST of the two qualifiers) no longer
    # matches its claimed rank-1 value/entity in either claim that names her.
    assert after_verdicts["season_fg3pct_verified"] == "MISMATCH"
    assert after_verdicts["season_fg3pct_floor_check"] == "MISMATCH"
    # The claim that named ONLY Bravo at rank 1 flips the OTHER direction:
    # with Alpha nerfed below Bravo, Bravo is now genuinely the top qualifier
    # (Charlie stays excluded, below the fg3a floor) -- this claim's rank-1
    # assertion becomes TRUE post-tamper, proving the recompute is directional
    # and live (not a rubber stamp that always says MISMATCH after any edit).
    assert after_verdicts["season_fg3pct_mismatch"] == "VERIFIED"
    # The career-window claim reads a COMPLETELY DIFFERENT source file and
    # must be completely unaffected by the season-file tamper.
    assert after_verdicts["career_asttotov_verified"] == "VERIFIED"


def test_write_summary_preserves_predictive_validity(tmp_path):
    """The pod validation loop rewrites every *_validation.json each cycle --
    the predictive_validity stamp (a different, slower pipeline) must survive."""
    import json
    from scripts.platformkit.intel_validation.claims_validator import (
        ValidationSummary, write_summary,
    )
    out = tmp_path / "fam_validation.json"
    out.write_text(json.dumps({"n_claims": 1, "predictive_validity": {
        "m1": {"verdict": "PREDICTIVE_VERIFIED"}}}), encoding="ascii")
    write_summary(ValidationSummary(generated_at="t"), out)
    doc = json.loads(out.read_text(encoding="ascii"))
    assert doc["predictive_validity"]["m1"]["verdict"] == "PREDICTIVE_VERIFIED"
    assert doc["component"] == "intel_claims_validation"
