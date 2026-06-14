"""brain_vault — make vault/_Organized openable as its OWN clean Obsidian vault.

The user keeps their FULL vault at vault/ (untouched). vault/_Organized/ holds the
dense person-free intelligence brain. Opening _Organized as a SEPARATE Obsidian vault
("Open another vault" -> vault/_Organized) gives a graph that shows ONLY the brain
(drivers/mechanisms/archetypes/schemes/identity/MOC hubs) — clean BY CONSTRUCTION,
because that folder contains no matchups/players at all. No graph.json filter needed
and no clobber problem (everything there IS brain).

The one-command rebuild wipes _Organized each run, so this re-seeds its .obsidian
config every rebuild (deterministic; the _Organized vault is a generated view).
HONEST: an intelligence map; markets efficient; calibration is not edge; no edge.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

_CORE_PLUGINS = ["graph", "backlink", "outline", "page-preview", "tag-pane", "search"]

# Graph view for the brain-only vault: colour by sport + causal-spine + hubs.
# No "search" scope filter is needed — every node in this vault is brain.
_GRAPH: Dict = {
    "collapse-filter": False, "search": "", "showTags": False,
    "showAttachments": False, "hideUnresolved": True, "showOrphans": True,
    "collapse-color-groups": False,
    "colorGroups": [
        {"query": "path:NBA", "color": {"a": 1, "rgb": 16753920}},
        {"query": "path:MLB", "color": {"a": 1, "rgb": 5025616}},
        {"query": "path:Soccer", "color": {"a": 1, "rgb": 52479}},
        {"query": "path:Tennis", "color": {"a": 1, "rgb": 12597497}},
        {"query": "path:Drivers", "color": {"a": 1, "rgb": 16007990}},
        {"query": "path:Mechanisms", "color": {"a": 1, "rgb": 16738740}},
        {"query": "path:Archetypes OR path:Playstyles", "color": {"a": 1, "rgb": 5028096}},
        {"query": "path:Schemes OR path:Tactics", "color": {"a": 1, "rgb": 16770304}},
        {"query": "file:_Identity", "color": {"a": 1, "rgb": 8421504}},
        {"query": "path:_Index OR file:_Brain OR file:_WhatWins OR file:_Digest",
         "color": {"a": 1, "rgb": 16777215}},
    ],
    "collapse-display": False, "showArrow": False, "textFadeMultiplier": -0.5,
    "nodeSizeMultiplier": 1.15, "lineSizeMultiplier": 0.6, "collapse-forces": False,
    "centerStrength": 0.5, "repelStrength": 9.5, "linkStrength": 0.6,
    "linkDistance": 200, "scale": 0.18, "close": True,
}


def _w(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def ensure_brain_graph_config(organized_root: Path) -> Dict:
    """Seed/refresh organized_root/.obsidian so _Organized opens as a clean vault.

    Idempotent + deterministic. Returns {"obsidian_dir","files"}.
    """
    organized_root = Path(organized_root)
    obs = organized_root / ".obsidian"
    obs.mkdir(parents=True, exist_ok=True)
    files = {
        "app.json": json.dumps({"alwaysUpdateLinks": True}, indent=2),
        "appearance.json": json.dumps({"accentColor": "", "theme": "obsidian"}, indent=2),
        "core-plugins.json": json.dumps(_CORE_PLUGINS, indent=2),
        "graph.json": json.dumps(_GRAPH, indent=2),
    }
    for name, text in files.items():
        _w(obs / name, text)
    return {"obsidian_dir": str(obs), "files": sorted(files)}


def _main(argv=None) -> int:
    import sys
    root = Path(argv[0]) if (argv := list(sys.argv[1:] if argv is None else argv)) \
        else Path(__file__).resolve().parents[2] / "vault" / "_Organized"
    rep = ensure_brain_graph_config(root)
    print(json.dumps(rep, indent=2))
    print(f"\nOpen this folder as an Obsidian vault for a clean brain-only graph:\n  {root}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["ensure_brain_graph_config"]
