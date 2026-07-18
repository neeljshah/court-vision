"""Per-file test for scripts.platformkit.answers.claims_resolver -- the
RESOLVER BRIDGE that makes auto-discovered VERIFIED claim families reachable
through resolver_registry.resolve().

Fixture-first (a fake ask() so PASS/no_data/excerpt shape is proven without a
real claim load), plus a couple of real capped calls against the actual repo
(status-agnostic: an ok OR a fail-closed status is a pass, both fields present).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/answers/test_claims_resolver.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.answers import claims_resolver as C
from scripts.platformkit.answers import resolver_registry as R
from scripts.platformkit.intel_query import ask as ask_mod


# --- pure excerpt / normalization logic (the load-bearing adapter piece) -----
def test_excerpt_accepts_both_name_keys():
    # WNBA families key ranking rows entity_name; ask entity_lookup keys player_name
    wnba = {"ranking": [{"rank": 1, "entity_name": "Julie Allemand", "value": 0.84, "n": 19}]}
    ask = {"ranking": [{"rank": 1, "player_name": "Stephen Curry", "value": 0.7, "n": 50}]}
    assert C._excerpt(wnba, "x")[0]["name"] == "Julie Allemand"
    assert C._excerpt(ask, "x")[0]["name"] == "Stephen Curry"


def test_excerpt_top5_plus_named_entity_below_floor():
    rows = [{"rank": i, "entity_name": f"P{i}", "value": 1.0 / i, "n": 10} for i in range(1, 9)]
    ex = C._excerpt({"ranking": rows}, "evidence for P7 please", top=5)
    names = [r["name"] for r in ex]
    assert names[:5] == ["P1", "P2", "P3", "P4", "P5"]
    assert "P7" in names and len(ex) == 6  # asked entity appended past top-5


def test_excerpt_empty_when_no_ranking():
    assert C._excerpt({"caveats": ["c"]}, "x") == []


# --- ask() wrap: ok envelope with receipts, and fail-closed no_data ----------
def test_wrap_ask_ok_envelope_has_receipts(monkeypatch):
    fake = {
        "answerable": True, "family": "provenance",
        "answer": {"claim_id": "cid_x_y", "caveats": ["descriptive only"],
                   "ranking": [{"rank": 1, "player_name": "A B", "value": 0.5, "n": 12}]},
        "evidence": [{"claim_id": "cid_x_y", "as_of": "2026-07-17T00:00:00+00:00",
                      "validator_verdict": "VERIFIED",
                      "validator_source": "v.json", "producer_source": "p.jsonl"}],
    }
    monkeypatch.setattr("scripts.platformkit.intel_query.ask.ask", lambda q: fake)
    env = C._wrap_ask("show the evidence for cid_x_y", "nba")
    assert env["status"] == "ok" and env["category"] == "verified_claims"
    assert env["claim_id"] == "cid_x_y"
    assert env["validator_verdict"] == "VERIFIED"
    assert env["source_artifact"] == "p.jsonl" and env["as_of"] == "2026-07-17T00:00:00+00:00"
    assert env["caveats"] == ["descriptive only"]
    assert env["ranking_excerpt"][0]["name"] == "A B"


def test_wrap_ask_unanswerable_is_no_data(monkeypatch):
    monkeypatch.setattr("scripts.platformkit.intel_query.ask.ask",
                        lambda q: {"answerable": False, "reason": "no VERIFIED claim covers this",
                                   "nearest_supported_families": []})
    env = C._wrap_ask("show the evidence for made_up_zzz", "nba")
    assert env["status"] == "no_data" and env["category"] == "verified_claims"
    assert "no VERIFIED claim" in env["note"]
    assert env["source_artifact"] == "data/cache/intel_claims/"


# --- family-level fallback for NAME-KEYED stores (referee crews) -----------
# Documented gap (qa_bank id nba_referee_crew_ft_routing): family-level
# referee phrasings used to return no_data because ask()'s NL matcher
# resolves neither a specific metric nor a family listing. resolve() now
# falls back to listing the ONE named family's VERIFIED claims directly.
def _write_referee_fixture(tmp_path, monkeypatch):
    claims_path = tmp_path / "nba_referee_crew_ft_claims.jsonl"
    validation_path = tmp_path / "nba_referee_crew_ft_claims_validation.json"
    row = {
        "claim_id": "fixture_referee_mean_fta_alltime",
        "kind": "ranking",
        "question": "NBA official mean fta environment, alltime?",
        "criteria": {"metric": "mean_fta", "window": "alltime", "entity_key": "entity_id"},
        "ranking": [{"rank": 1, "entity_id": "Leon Wood", "value": 46.2, "n_games": 120}],
        "source_files": ["data/fake/referee_source.parquet"],
        "computed_at": "2026-07-18T00:00:00+00:00",
    }
    claims_path.write_text(json.dumps(row) + "\n", encoding="ascii")
    validation_path.write_text(json.dumps({
        "component": "intel_claims_validation", "n_claims": 1,
        "details": [{"claim_id": "fixture_referee_mean_fta_alltime", "verdict": "VERIFIED", "reason": "ok"}],
    }), encoding="ascii")
    monkeypatch.setattr(ask_mod, "INTEL_CLAIMS_DIR", tmp_path)
    monkeypatch.setattr(ask_mod, "CLAIM_SOURCE_PAIRS", ((validation_path, claims_path),))


def test_family_level_referee_question_lists_family_claims(tmp_path, monkeypatch):
    _write_referee_fixture(tmp_path, monkeypatch)
    env = C.resolve("which referee crews inflate free throws")
    assert env["status"] == "ok" and env["category"] == "verified_claims"
    assert env["family"] == "nba_referee_crew_ft_claims"
    assert env["claims"][0]["claim_id"] == "fixture_referee_mean_fta_alltime"
    assert env["claims"][0]["top"][0]["name"] == "Leon Wood"


def test_qa_bank_referee_routing_phrasing_now_ok(tmp_path, monkeypatch):
    # the exact qa_bank id=nba_referee_crew_ft_routing phrasing
    _write_referee_fixture(tmp_path, monkeypatch)
    env = C.resolve("top officials by fta per game officiated")
    assert env["status"] == "ok"
    assert env["claims"][0]["top"][0]["name"] == "Leon Wood"


def test_named_referee_beats_family_fallback(tmp_path, monkeypatch):
    """PROBE 2 (2026-07-19): a SPECIFIC referee name must return that
    official's own entity_lookup answer -- the family-level listing is the
    LAST resort, only for questions that name no resolvable entity."""
    _write_referee_fixture(tmp_path, monkeypatch)
    env = C.resolve("where does Leon Wood rank on mean fta among nba officials")
    assert env["status"] == "ok"
    assert "claims" not in env  # not the family-level listing
    assert env["family"] == "entity_lookup"
    assert env["ranking_excerpt"] == [] or env.get("claim_id")  # entity answer envelope


def test_non_referee_question_unaffected_by_family_fallback(monkeypatch):
    # a no_data answer for a query that names NO known family route must
    # stay no_data -- the fallback only fires on a recognized family regex.
    monkeypatch.setattr("scripts.platformkit.intel_query.ask.ask",
                        lambda q: {"answerable": False, "reason": "no VERIFIED claim covers this",
                                   "nearest_supported_families": []})
    env = C.resolve("what is the capital of nowhere")
    assert env["status"] == "no_data"


# --- family discovery --------------------------------------------------------
def test_list_claim_families_real_repo_ok():
    d = C.list_claim_families()
    assert d["status"] == "ok" and d["n_families"] >= 10
    assert all("family" in f and "n_verified" in f for f in d["families"])


def test_list_claim_families_sport_filter():
    d = C.list_claim_families("tennis")
    assert d["status"] == "ok" and d["sport"] == "tennis"
    assert all("tennis" in f["family"] for f in d["families"])


def test_resolve_routes_list_vs_wrap():
    # a family-discovery question lists; sport parsed from the query, not the param
    d = C.resolve("what claim families exist for tennis?")
    assert d["status"] == "ok" and d["sport"] == "tennis" and "families" in d


# --- real resolve() bridge, provenance by a real claim_id --------------------
def test_real_provenance_bridge_through_registry():
    cid = "wnba_zone_context_zone_rim_efg_full_2026"
    d = R.resolve(f"show the evidence for {cid}", sport="wnba")
    assert d["category"] == "verified_claims"
    if d["status"] == "ok":  # claim store present on this box
        assert d["claim_id"] == cid and d["validator_verdict"] == "VERIFIED"
        assert "intel_claims" in d["source_artifact"]
    else:
        assert d["status"] in ("no_data",)  # fresh clone: fail-closed, never a guess
