"""scripts.platformkit.ingame.ingame_gumbo_mlb_patch -- RFC6902 patch-apply sidecar for
ingame_gumbo_mlb.py (split out to keep the main extractor file under the LOC budget).

Applies a minimal subset of RFC6902 JSON-Patch ops (add/replace/remove) to a deep-copied
GUMBO snapshot dict, and turns a diffPatch HTTP response (full-snapshot dict OR patch-batch
list -- see ingame_gumbo_mlb.py header for the observed-live shape notes) into a full GUMBO
doc ready for ingame_gumbo_mlb.extract_state(). Never raises out of apply_diffpatch_response
-- any failure returns None so the caller falls back to a full bootstrap re-fetch (honest,
no fabricated state).

Per-file test: this module is exercised via
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/ingame/test_ingame_gumbo_mlb.py -q
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Union

GumboDoc = Dict[str, Any]


def is_full_update(doc: GumboDoc) -> bool:
    """True when doc is a full-snapshot GUMBO payload (has liveData/gameData), OR a
    patch-batch doc whose metaData.logicalEvents contains 'fullUpdate' -- trap (a)."""
    if not isinstance(doc, dict):
        return False
    if "liveData" in doc and "gameData" in doc:
        return True
    meta = doc.get("metaData")
    logical = meta.get("logicalEvents", []) if isinstance(meta, dict) else []
    return "fullUpdate" in (logical or [])


def apply_patch(base_state: GumboDoc, patch_ops: List[Dict[str, Any]]) -> GumboDoc:
    """Apply RFC6902 add/replace/remove ops to a deep copy of base_state, walking
    '/'-separated JSON-Pointer paths. Raises ValueError on any op it cannot apply
    (caller must catch and fall back to a full re-fetch)."""
    doc = copy.deepcopy(base_state)
    for op in patch_ops:
        action = op.get("op")
        path = op.get("path", "")
        parts = [p.replace("~1", "/").replace("~0", "~") for p in path.split("/") if p != ""]
        if not parts:
            raise ValueError("empty patch path")
        node = doc
        for key in parts[:-1]:
            if isinstance(node, list):
                node = node[int(key)]
            elif isinstance(node, dict):
                node = node.setdefault(key, {})
            else:
                raise ValueError("cannot traverse into scalar at %r" % key)
        last = parts[-1]
        if action in ("add", "replace"):
            if isinstance(node, list):
                idx = len(node) if last == "-" else int(last)
                node.insert(idx, op.get("value")) if action == "add" else node.__setitem__(idx, op.get("value"))
            elif isinstance(node, dict):
                node[last] = op.get("value")
            else:
                raise ValueError("cannot set on scalar")
        elif action == "remove":
            if isinstance(node, list):
                del node[int(last)]
            elif isinstance(node, dict):
                node.pop(last, None)
            else:
                raise ValueError("cannot remove from scalar")
        else:
            raise ValueError("unsupported op %r" % action)
    return doc


def apply_diffpatch_response(last_full: Optional[GumboDoc],
                              response: Union[GumboDoc, List[GumboDoc]]) -> Optional[GumboDoc]:
    """Turn a diffPatch HTTP response into a full GUMBO doc.

    response may be (observed live, 2026-07-04): a full-snapshot dict (treat as-is), OR
    (per the documented RFC6902 spec) a list of patch-batch docs each with a 'diff' array
    to apply against last_full in order. On a fullUpdate doc with no embedded snapshot, or
    if any patch application fails, or if last_full is None and only patches are given,
    returns None (caller must do a full bootstrap re-fetch)."""
    if isinstance(response, dict):
        return response if is_full_update(response) or "liveData" in response else None
    if isinstance(response, list):
        if not response:
            return last_full
        state = last_full
        for doc in response:
            if is_full_update(doc):
                if "liveData" in doc:
                    state = doc
                    continue
                return None   # fullUpdate logical event but no embedded snapshot -> re-fetch
            if state is None:
                return None
            try:
                state = apply_patch(state, doc.get("diff", []))
            except (ValueError, IndexError, KeyError, TypeError):
                return None
        return state
    return None


__all__ = ["apply_patch", "apply_diffpatch_response", "is_full_update"]
