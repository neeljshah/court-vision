"""LANE F -- system intelligence map: a DECLARED (curated, hand-reviewed, not
introspected) dataflow graph of nodes (writer/daemon/producer/store/resolver/
webapp/consumer) and edges (writes/reads/serves/registers), verified against
disk at build time. The graph data lives in system_map_data.py (spec-exempt,
data-only); this module only verifies + writes the artifact.

Verification: every node's `path` is checked to exist on disk (module file or
data artifact). A node gets `verified: true` if its path exists, `false` if
the path resolves but is absent (e.g. a gitignored data/ artifact not yet
built in this clone), never silently assumed present.

Run: python -m scripts.platformkit.analytics_verify.system_map
  writes data/cache/analytics_verify/system_map.json
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.platformkit.analytics_verify.system_map_data import EDGES, NODES

ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = ROOT / "data" / "cache" / "analytics_verify" / "system_map.json"

HONEST_NOTE = (
    "This is a curated, hand-reviewed dataflow graph, not code introspection -- "
    "a human/agent declared these edges by reading the source, and each node's "
    "path is verified to exist on disk at build time. A node existing does not "
    "mean the edge relation is currently true (e.g. a daemon not running); it "
    "means the declared file/artifact is real, not invented. edge_claimed=false: "
    "this graph describes data plumbing, not a dollar edge."
)


def _verify_node(node: dict) -> dict:
    path = ROOT / node["path"]
    exists = path.exists()
    out = dict(node)
    out["verified"] = exists
    if exists:
        out["mtime"] = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    else:
        out["mtime"] = None
    return out


def build() -> dict:
    node_ids = {n["id"] for n in NODES}
    verified_nodes = [_verify_node(n) for n in NODES]
    n_verified = sum(1 for n in verified_nodes if n["verified"])
    n_unverified = len(verified_nodes) - n_verified
    # honest cross-check: every edge endpoint must reference a declared node --
    # a dangling edge is a bug in the curated data, not something to hide.
    dangling = [e for e in EDGES if e["src"] not in node_ids or e["dst"] not in node_ids]
    if dangling:
        raise ValueError(f"system_map_data.py has {len(dangling)} dangling edge(s): {dangling}")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "edge_claimed": False,
        "honest_note": HONEST_NOTE,
        "n_nodes": len(verified_nodes),
        "n_edges": len(EDGES),
        "n_verified": n_verified,
        "n_unverified": n_unverified,
        "nodes": verified_nodes,
        "edges": EDGES,
    }


def write(out_path: Path = OUT_PATH) -> dict:
    data = build()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(out_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="ascii", errors="backslashreplace") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp_path, out_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return data


def main(argv=None) -> None:
    data = write()
    print(f"system_map.json: n_nodes={data['n_nodes']} n_edges={data['n_edges']} "
          f"n_verified={data['n_verified']} n_unverified={data['n_unverified']}")


if __name__ == "__main__":
    main()
