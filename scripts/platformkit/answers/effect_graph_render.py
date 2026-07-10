"""LANE C5 -- compact per-sport markdown rendering of the effect graph built
by effect_graph.py. Reads the pinned data/frontend/ops/effect_graph.json
artifact only -- no recompute, no new numbers, verbatim edge rows.

Run: python -m scripts.platformkit.answers.effect_graph_render
  writes docs/research/effect_graph.md
"""
from __future__ import annotations

import os

from scripts.platformkit.answers import effect_graph as _eg

_OUT_MD = os.path.join("docs", "research", "effect_graph.md")
_STATUS_ORDER = ["CONFIRMED_LOCAL", "ARTIFACT_CONFIRMED", "REPLICATED", "SURVIVES_PREREG_PROVISIONAL",
                 "NULL_LOCAL", "NULL", "REJECT", "FAILED_REPLICATION", "FAILED_REPLICATION_POWER_ANNOTATED",
                 "REPLICATION_BLOCKED", "NOT_TESTABLE", "KILLED"]


def _leaf(node_id: str) -> str:
    return node_id.rsplit(":", 1)[-1]


def _edge_row(e: dict) -> str:
    effect = e.get("effect")
    effect_s = f"{effect:.4g}" if isinstance(effect, (int, float)) else "n/a"
    p = e.get("p")
    p_s = f"{p:.3g}" if isinstance(p, (int, float)) else "n/a"
    return (f"| {_leaf(e['from'])} | {_leaf(e['to'])} | {e['status']} | {effect_s} | "
            f"{e.get('n', 'n/a')} | {p_s} | {e.get('corpus', '')} |")


def render_sport(sport: str, graph: dict) -> str:
    edges = [e for e in graph["edges"] if e["sport"] == sport]
    edges.sort(key=lambda e: (_STATUS_ORDER.index(e["status"]) if e["status"] in _STATUS_ORDER else 99, e["from"]))
    counts = graph["sport_counts"].get(sport, {})
    lines = [f"## {sport}", "", f"nodes: {counts} -- {len(edges)} edges", "",
             "| affects (X) | outcome (Y) | status | effect | n | p | corpus |",
             "|---|---|---|---|---|---|---|"]
    lines += [_edge_row(e) for e in edges]
    return "\n".join(lines)


def render(graph: dict) -> str:
    sports = sorted(graph["sport_counts"])
    header = [
        "# Effect graph -- what affects what",
        "",
        f"as_of: {graph['as_of']} -- {graph['n_nodes']} nodes / {graph['n_edges']} edges. "
        "Built entirely from existing ledgers (domains/*/knowledge/validation_ledger.jsonl + "
        "data/cache/intel_claims/interaction_factory_ledger.jsonl); every row here is verbatim, "
        "LOCAL single-corpus, not a market-beating or causal claim.",
        "",
    ]
    return "\n".join(header) + "\n\n".join(render_sport(s, graph) for s in sports)


def main() -> str:
    graph = _eg.load_graph()
    if graph is None:
        graph = _eg.write_graph()
    text = render(graph)
    os.makedirs(os.path.dirname(_OUT_MD), exist_ok=True)
    with open(_OUT_MD, "w", encoding="utf-8") as fh:
        fh.write(text)
    return _OUT_MD


if __name__ == "__main__":
    path = main()
    print(f"wrote {path}")
