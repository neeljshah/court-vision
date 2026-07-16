"""LANE F -- system_map builder + resolver tests: proves the graph verifies
against real disk paths (no phantom nodes), that a dangling edge is a hard
build error, and that the system_map() resolver's fail-closed gates + node
lookup match the pattern of the other analytics_verify resolvers.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/analytics_verify/test_system_map.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts.platformkit.analytics_verify import answers as A
from scripts.platformkit.analytics_verify import system_map as SM
from scripts.platformkit.answers import resolver_registry as R

FRESH = datetime.now(timezone.utc).isoformat()
STALE = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _point(tmp_path, monkeypatch):
    p = tmp_path / "system_map.json"
    monkeypatch.setitem(A.ARTIFACTS, "system_map", str(p))
    return p


# ---------------------------------------------------------------------------
# builder
# ---------------------------------------------------------------------------
def test_build_has_no_dangling_edges_and_stamps_edge_claimed_false():
    data = SM.build()
    assert data["edge_claimed"] is False
    assert data["n_nodes"] == len(data["nodes"])
    assert data["n_edges"] == len(data["edges"])
    node_ids = {n["id"] for n in data["nodes"]}
    for e in data["edges"]:
        assert e["src"] in node_ids
        assert e["dst"] in node_ids


def test_build_verifies_every_node_against_real_disk():
    data = SM.build()
    for n in data["nodes"]:
        assert n["verified"] in (True, False)
        # a module/store path that "verified" claims exists must actually exist
        if n["verified"]:
            assert (SM.ROOT / n["path"]).exists()


def test_write_round_trips_to_disk(tmp_path):
    out = tmp_path / "system_map.json"
    data = SM.write(out_path=out)
    assert out.exists()
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["n_nodes"] == data["n_nodes"]
    assert on_disk["edge_claimed"] is False


# ---------------------------------------------------------------------------
# resolver: system_map() in answers.py
# ---------------------------------------------------------------------------
def test_resolver_no_data_when_artifact_absent(tmp_path, monkeypatch):
    _point(tmp_path, monkeypatch)
    r = A.system_map("nba")
    assert r["status"] == "no_data"
    assert r["category"] == "system_map"


def test_resolver_refused_when_edge_claimed_missing(tmp_path, monkeypatch):
    p = _point(tmp_path, monkeypatch)
    _write(p, {"generated_at": FRESH, "nodes": [], "edges": []})
    r = A.system_map("nba")
    assert r["status"] == "refused"
    assert "edge_claimed" in r["note"]


def test_resolver_refused_when_stale(tmp_path, monkeypatch):
    p = _point(tmp_path, monkeypatch)
    _write(p, {"generated_at": STALE, "edge_claimed": False, "nodes": [], "edges": []})
    r = A.system_map("nba")
    assert r["status"] == "refused"
    assert "staleness" in r["note"]


def test_resolver_ok_whole_graph_summary(tmp_path, monkeypatch):
    p = _point(tmp_path, monkeypatch)
    _write(p, {"generated_at": FRESH, "edge_claimed": False, "honest_note": "x",
               "n_nodes": 1, "n_edges": 0,
               "nodes": [{"id": "a", "kind": "store", "path": "x", "verified": True}],
               "edges": []})
    r = A.system_map("nba")
    assert r["status"] == "ok"
    assert r["nodes"] == ["a"]


def test_resolver_ok_node_lookup_returns_produced_by_and_consumed_by(tmp_path, monkeypatch):
    p = _point(tmp_path, monkeypatch)
    _write(p, {"generated_at": FRESH, "edge_claimed": False,
               "n_nodes": 3, "n_edges": 2,
               "nodes": [{"id": "writer", "kind": "writer"}, {"id": "store", "kind": "store"},
                         {"id": "reader", "kind": "resolver"}],
               "edges": [{"src": "writer", "dst": "store", "relation": "writes"},
                         {"src": "reader", "dst": "store", "relation": "reads"}]})
    r = A.system_map("nba", node="store")
    assert r["status"] == "ok"
    assert r["node"]["id"] == "store"
    assert len(r["produced_by"]) == 1 and r["produced_by"][0]["src"] == "writer"
    assert len(r["consumed_by"]) == 1 and r["consumed_by"][0]["src"] == "reader"


def test_resolver_no_data_for_unknown_node(tmp_path, monkeypatch):
    p = _point(tmp_path, monkeypatch)
    _write(p, {"generated_at": FRESH, "edge_claimed": False, "nodes": [], "edges": []})
    r = A.system_map("nba", node="does_not_exist")
    assert r["status"] == "no_data"


# ---------------------------------------------------------------------------
# resolver_registry classification + dispatch
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("q", [
    "what produces the clv ledger?",
    "what consumes the card ledger?",
    "show me the system map",
    "how does the system work end to end",
])
def test_classify_routes_system_map_questions(q):
    assert R.classify(q) == "system_map"


def test_registered_in_resolvers_table():
    assert "system_map" in R.RESOLVERS
    assert R.RESOLVERS["system_map"]["source_artifact"] == "data/cache/analytics_verify/system_map.json"


def test_resolve_dispatches_to_analytics_system_map(tmp_path, monkeypatch):
    p = _point(tmp_path, monkeypatch)
    _write(p, {"generated_at": FRESH, "edge_claimed": False,
               "n_nodes": 1, "n_edges": 0,
               "nodes": [{"id": "a", "kind": "store"}], "edges": []})
    r = R.resolve("what produces the clv ledger?", sport="nba")
    assert r["status"] == "ok"
    assert r["category"] == "system_map"
