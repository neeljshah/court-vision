"""LANE C5 -- effect graph (nodes/edges) + resolver "what affects" wiring.

Run: python -m pytest scripts/platformkit/answers/test_effect_graph.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.answers import effect_graph as EG
from scripts.platformkit.answers import resolver_registry as R


# ---------------------------------------------------------------------------
# Determinism -- same ledger contents on disk -> identical graph twice.
# ---------------------------------------------------------------------------
def test_build_graph_is_deterministic():
    g1 = EG.build_graph()
    g2 = EG.build_graph()
    assert g1 == g2


def test_build_graph_has_all_four_sports_and_kinds():
    g = EG.build_graph()
    assert set(g["sport_counts"]) == {"nba", "mlb", "soccer", "tennis"}
    for sport, counts in g["sport_counts"].items():
        assert counts.get("mechanism", 0) > 0, f"{sport}: no mechanism nodes"
        assert counts.get("attribute", 0) > 0, f"{sport}: no attribute nodes"


# ---------------------------------------------------------------------------
# Edge-status fidelity vs a small fixture -- verbatim, never re-derived.
# ---------------------------------------------------------------------------
def test_mechanism_edge_status_fidelity_against_fixture(tmp_path):
    fixture = tmp_path / "validation_ledger.jsonl"
    fixture.write_text(
        json.dumps({"hypothesis": "fake_b2b_penalty", "sport": "basketball_nba",
                    "verdict": "CONFIRMED_LOCAL", "effect": -1.73, "n": 4732, "p": 0.005,
                    "corpus": "fixture_corpus", "note": "avg margin dropoff", "edge_claimed": False}) + "\n",
        encoding="utf-8",
    )
    nodes, edges = EG._mechanism_edges("nba", str(fixture))
    assert len(edges) == 1
    e = edges[0]
    assert e["status"] == "CONFIRMED_LOCAL"
    assert e["effect"] == -1.73 and e["n"] == 4732 and e["p"] == 0.005
    assert e["corpus"] == "fixture_corpus"
    assert e["from"] == "nba:mechanism:fake_b2b_penalty"
    assert e["to"] == "nba:outcome:point_margin"  # "margin" in note -> point_margin


def test_factory_edge_status_fidelity_against_fixture(tmp_path):
    fixture = tmp_path / "interaction_factory_ledger.jsonl"
    fixture.write_text(
        json.dumps({"attr_a": "halfcourt_efg", "attr_b": "late_clock_efg", "outcome": "efg",
                    "sport": "basketball_nba", "verdict": "NULL", "effect": 0.0005, "n": 14300,
                    "p": 0.78, "corpus": "fixture_corpus", "candidate_id": "fake_candidate", "note": ""}) + "\n",
        encoding="utf-8",
    )
    nodes, edges = EG._factory_edges(str(fixture))
    assert len(edges) == 1
    e = edges[0]
    assert e["status"] == "NULL" and e["effect"] == 0.0005 and e["n"] == 14300
    assert e["from"] == "nba:interaction:halfcourt_efg_x_late_clock_efg"
    assert e["to"] == "nba:outcome:efg"
    assert e["candidate_id"] == "fake_candidate"


def test_unclassified_outcome_fallback_is_honest_not_fabricated():
    """A note with no recognized keyword must fall back to the labelled
    'unclassified_outcome' bucket, never invent a plausible-sounding target."""
    assert EG._outcome_label("some totally novel phrasing with no keywords", "weird_hypothesis") == "unclassified_outcome"


# ---------------------------------------------------------------------------
# Resolver roundtrip -- "what affects Y" / "what does X affect" against a
# frozen fixture graph (never the live, growing artifact).
# ---------------------------------------------------------------------------
def _fixture_graph() -> dict:
    return {
        "as_of": "2026-01-01T00:00:00+00:00",
        "n_nodes": 2, "n_edges": 1, "sport_counts": {},
        "nodes": [{"id": "nba:mechanism:fake_b2b_penalty", "kind": "mechanism", "sport": "nba",
                   "label": "fake_b2b_penalty"},
                  {"id": "nba:outcome:point_margin", "kind": "outcome", "sport": "nba", "label": "point_margin"}],
        "edges": [{"from": "nba:mechanism:fake_b2b_penalty", "to": "nba:outcome:point_margin", "sport": "nba",
                   "kind": "mechanism", "status": "CONFIRMED_LOCAL", "effect": -1.73, "n": 4732, "p": 0.005,
                   "corpus": "fixture_corpus", "note": "avg margin dropoff",
                   "artifact": "domains/basketball_nba/knowledge/validation_ledger.jsonl"}],
    }


def test_classify_routes_affects_queries_to_mechanism_effect():
    assert R.classify("what affects point margin") == "mechanism_effect"
    assert R.classify("what does fake_b2b_penalty affect") == "mechanism_effect"


def test_resolve_what_affects_y_roundtrip(tmp_path, monkeypatch):
    snap = tmp_path / "effect_graph.json"
    snap.write_text(json.dumps(_fixture_graph()), encoding="utf-8")
    monkeypatch.setattr(EG, "_OUT_PATH", str(snap))
    r = R.resolve("what affects point margin", sport="nba")
    assert r["status"] == "ok" and r["category"] == "mechanism_effect"
    edge = r["edges"][0]
    assert edge["status"] == "CONFIRMED_LOCAL" and edge["effect"] == -1.73 and edge["n"] == 4732
    assert edge["from"] == "nba:mechanism:fake_b2b_penalty"


def test_resolve_what_does_x_affect_roundtrip(tmp_path, monkeypatch):
    snap = tmp_path / "effect_graph.json"
    snap.write_text(json.dumps(_fixture_graph()), encoding="utf-8")
    monkeypatch.setattr(EG, "_OUT_PATH", str(snap))
    r = R.resolve("what does fake_b2b_penalty affect", sport="nba")
    assert r["status"] == "ok"
    assert r["edges"][0]["to"] == "nba:outcome:point_margin"


def test_resolve_affects_no_graph_is_honest_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(EG, "_OUT_PATH", str(tmp_path / "missing.json"))
    r = R.resolve("what affects point margin", sport="nba")
    assert r["status"] == "no_data"


def test_resolve_affects_unknown_target_is_not_supported(tmp_path, monkeypatch):
    snap = tmp_path / "effect_graph.json"
    snap.write_text(json.dumps(_fixture_graph()), encoding="utf-8")
    monkeypatch.setattr(EG, "_OUT_PATH", str(snap))
    r = R.resolve("what affects teleportation field advantage", sport="nba")
    assert r["status"] == "not_supported"
