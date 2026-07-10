"""LANE C5 -- what-affects-what effect graph: composes everything the system
has PROVEN (or disproven) about causes and effects into one queryable
artifact. Zero new claims -- every edge is a verbatim row lifted from an
existing ledger; this module only labels and links, never recomputes a
verdict/effect/n/p.

Nodes:
    mechanism   -- one per (sport, hypothesis) in
                   domains/<sport>/knowledge/validation_ledger.jsonl
    interaction -- one per candidate row (survivor or reject) in
                   data/cache/intel_claims/interaction_factory_ledger.jsonl
    attribute   -- one per entry in domains/<sport>/profiles/attribute_registry.py
                   (ATTRIBUTES or REGISTRY dict, sport-dependent name) -- pure
                   descriptive vocabulary, no edges required to originate here
    outcome     -- the measured target a mechanism/interaction edge lands on

Edges ("X affects Y"): {from, to, sport, kind, status, effect, n, p, corpus,
artifact, note}. `status`/`effect`/`n`/`p`/`corpus`/`note` are the ledger
row's own columns, copied verbatim.

# ponytail: mechanism-ledger rows have no explicit target column (only a free
# -text `note`), so the outcome node label is extracted MECHANICALLY via a
# fixed keyword vocabulary matched against that same note/hypothesis text --
# this labels what the row's own note already says, it asserts nothing new.
# Unmatched rows fall back to "unclassified_outcome" (honest, not silently
# dropped). Factory-ledger rows need no such guess: attr_a/attr_b/outcome are
# already structured columns.

Run: python -m scripts.platformkit.answers.effect_graph
  writes data/frontend/ops/effect_graph.json (as-of stamped from the newest
  source ledger's mtime -- a pinned artifact, not a live recompute per call).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from importlib import import_module

_LEDGER_PATHS = {
    "nba": "domains/basketball_nba/knowledge/validation_ledger.jsonl",
    "mlb": "domains/mlb/knowledge/validation_ledger.jsonl",
    "soccer": "domains/soccer/knowledge/validation_ledger.jsonl",
    "tennis": "domains/tennis/knowledge/validation_ledger.jsonl",
}
_ATTR_MODULES = {
    "nba": "domains.basketball_nba.profiles.attribute_registry",
    "mlb": "domains.mlb.profiles.attribute_registry",
    "soccer": "domains.soccer.profiles.attribute_registry",
    "tennis": "domains.tennis.profiles.attribute_registry",
}
_FACTORY_LEDGER = "data/cache/intel_claims/interaction_factory_ledger.jsonl"
_SPORT_FULL_TO_SHORT = {"basketball_nba": "nba", "mlb": "mlb", "soccer": "soccer", "tennis": "tennis"}
_OUT_PATH = os.path.join("data", "frontend", "ops", "effect_graph.json")

# Ordered (regex, canonical label) pairs -- first match against the ledger
# row's own note (fallback hypothesis) text wins. See ponytail note above.
_OUTCOME_VOCAB = [
    (r"win[-_ ]?rate|win%|win probability|match-win rate", "win_rate"),
    (r"\bmargin\b", "point_margin"),
    (r"\bgoal", "goals"),
    (r"efg|true.?shooting|ts-proxy", "shooting_efficiency"),
    (r"dreb|oreb|rebound", "rebound_rate"),
    (r"\bminutes\b|\bmin\b", "minutes"),
    (r"\bshare\b", "usage_share"),
    (r"xwoba|babip|\biso\b|chase rate|\bbb rate\b|k-rate|strand.rate", "batting_rate"),
    (r"shots?/min|shot.rate", "shot_rate"),
    (r"serve|hold rate|break.point|\bdf rate\b|double fault", "serve_outcome"),
    (r"retirement", "retirement_rate"),
    (r"upset", "upset_rate"),
    (r"conversion", "conversion_rate"),
    (r"\bvariance\b|\bstd\b", "variance"),
]


def _outcome_label(note: str, hypothesis: str) -> str:
    text = f"{note or ''} {hypothesis or ''}".lower()
    for pat, label in _OUTCOME_VOCAB:
        if re.search(pat, text):
            return label
    return "unclassified_outcome"


def _node_id(kind: str, sport: str, name: str) -> str:
    return f"{sport}:{kind}:{name}"


def _load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _mechanism_edges(sport: str, path: str) -> tuple[list[dict], list[dict]]:
    """One edge per validation_ledger row: hypothesis -> derived outcome."""
    nodes, edges = [], []
    for r in _load_jsonl(path):
        outcome = _outcome_label(r.get("note", ""), r["hypothesis"])
        frm, to = _node_id("mechanism", sport, r["hypothesis"]), _node_id("outcome", sport, outcome)
        nodes.append({"id": frm, "kind": "mechanism", "sport": sport, "label": r["hypothesis"]})
        nodes.append({"id": to, "kind": "outcome", "sport": sport, "label": outcome})
        edges.append({
            "from": frm, "to": to, "sport": sport, "kind": "mechanism",
            "status": r["verdict"], "effect": r.get("effect"), "n": r.get("n"), "p": r.get("p"),
            "corpus": r.get("corpus"), "note": r.get("note", ""), "artifact": path,
        })
    return nodes, edges


def _factory_edges(path: str) -> tuple[list[dict], list[dict]]:
    """One edge per factory-ledger row: attr_a x attr_b -> outcome (already
    structured columns -- no text inference needed)."""
    nodes, edges = [], []
    for r in _load_jsonl(path):
        sport = _SPORT_FULL_TO_SHORT.get(r.get("sport"), r.get("sport"))
        interaction_name = f"{r['attr_a']}_x_{r['attr_b']}"
        frm, to = _node_id("interaction", sport, interaction_name), _node_id("outcome", sport, r["outcome"])
        nodes.append({"id": frm, "kind": "interaction", "sport": sport, "label": interaction_name,
                      "attr_a": r["attr_a"], "attr_b": r["attr_b"], "template_id": r.get("template_id")})
        nodes.append({"id": to, "kind": "outcome", "sport": sport, "label": r["outcome"]})
        edges.append({
            "from": frm, "to": to, "sport": sport, "kind": "interaction",
            "status": r["verdict"], "effect": r.get("effect"), "n": r.get("n"), "p": r.get("p"),
            "corpus": r.get("corpus"), "note": r.get("note", ""), "artifact": path,
            "candidate_id": r.get("candidate_id"),
        })
    return nodes, edges


def _attribute_nodes(sport: str, module_path: str) -> list[dict]:
    """Descriptive vocabulary nodes -- no edges required to originate here."""
    mod = import_module(module_path)
    attrs = getattr(mod, "ATTRIBUTES", None)
    if attrs is None:
        attrs = getattr(mod, "REGISTRY", {})
    return [{
        "id": _node_id("attribute", sport, name), "kind": "attribute", "sport": sport, "label": name,
        "entity": spec.get("entity"), "status": spec.get("status"), "description": spec.get("description"),
    } for name, spec in attrs.items()]


def _dedup_nodes(nodes: list[dict]) -> list[dict]:
    seen, out = set(), []
    for n in nodes:
        if n["id"] in seen:
            continue
        seen.add(n["id"])
        out.append(n)
    return out


def _as_of_stamp() -> str:
    """Newest mtime across the source ledgers -- deterministic given fixed
    inputs (unlike datetime.now()), matching the pinned-artifact convention
    resolver_registry.py already uses for calibration_number/mechanism_effect."""
    paths = list(_LEDGER_PATHS.values()) + [_FACTORY_LEDGER]
    mtimes = [os.path.getmtime(p) for p in paths if os.path.exists(p)]
    ts = max(mtimes) if mtimes else 0.0
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def build_graph() -> dict:
    """Deterministic: identical ledger contents -> identical graph (nodes and
    edges are sorted, never insertion-order-dependent)."""
    all_nodes, all_edges = [], []
    for sport, path in _LEDGER_PATHS.items():
        nodes, edges = _mechanism_edges(sport, path)
        all_nodes += nodes
        all_edges += edges
    fnodes, fedges = _factory_edges(_FACTORY_LEDGER)
    all_nodes += fnodes
    all_edges += fedges
    for sport, mod_path in _ATTR_MODULES.items():
        all_nodes += _attribute_nodes(sport, mod_path)
    all_nodes = sorted(_dedup_nodes(all_nodes), key=lambda n: n["id"])
    all_edges = sorted(all_edges, key=lambda e: (e["sport"], e["kind"], e["from"], e["to"]))
    counts: dict = {}
    for n in all_nodes:
        counts.setdefault(n["sport"], {}).setdefault(n["kind"], 0)
        counts[n["sport"]][n["kind"]] += 1
    return {"as_of": _as_of_stamp(), "n_nodes": len(all_nodes), "n_edges": len(all_edges),
            "sport_counts": counts, "nodes": all_nodes, "edges": all_edges}


def load_graph(path: str | None = None) -> dict | None:
    """Reads the pinned artifact -- never recomputes. None if not built yet
    in this clone (data/ is gitignored)."""
    path = path or _OUT_PATH
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def query_edges(sport: str, target_tokens: set[str], direction: str = "to", graph: dict | None = None) -> list[dict]:
    """Edges where `direction` node's leaf label (the part after the last
    ':') is a token-superset of `target_tokens` -- same subset-match shape
    resolver_registry.mechanism_effect already uses for hypothesis names."""
    graph = graph if graph is not None else load_graph()
    if not graph or not target_tokens:
        return []
    hits = []
    for e in graph.get("edges", []):
        if e["sport"] != sport:
            continue
        leaf = e[direction].rsplit(":", 1)[-1]
        leaf_tokens = set(re.findall(r"[a-z0-9]+", leaf.lower()))
        if target_tokens <= leaf_tokens:
            hits.append(e)
    return hits


def write_graph(out_path: str = _OUT_PATH) -> dict:
    graph = build_graph()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(graph, fh, indent=2)
    return graph


if __name__ == "__main__":
    g = write_graph()
    print(f"wrote {_OUT_PATH}: {g['n_nodes']} nodes, {g['n_edges']} edges, sport_counts={g['sport_counts']}")
