"""Additive G389 reference-census helpers; no judgment or scoring occurs here."""
from __future__ import annotations

from typing import Iterable


REFERENCE_FIELDS = ("frame_key", "split", "source", "label", "box_x", "box_y", "box_w",
                    "box_h", "cx", "cy", "diameter", "decided_by", "n_raters", "review_state")


def full_schema_merge(manifest: Iterable[dict[str, str]], reference: Iterable[dict[str, str]],
                      adjudications: Iterable[dict[str, str]], reviewed_unknown: set[str] | None = None) -> list[dict[str, str]]:
    """Retain every manifest identity and distinguish unvisited from reviewed UNKNOWN."""
    reviewed_unknown = reviewed_unknown or set()
    ref = {row["frame_key"]: row for row in reference}
    adj = {row["frame_key"]: row for row in adjudications}
    if len(ref) + len(adj) != len(set(ref) | set(adj)):
        raise ValueError("overlapping-settled-keys")
    rows: list[dict[str, str]] = []
    for item in manifest:
        key = item["frame_key"]
        chosen = adj.get(key) or ref.get(key)
        if chosen is None:
            state, label = "UNVISITED", ""
        else:
            state, label = "REVIEWED", chosen.get("label", "")
        if key in reviewed_unknown:
            if state != "REVIEWED" or label != "UNKNOWN":
                raise ValueError("unknown-requires-reviewed-decision")
        row = {field: "" for field in REFERENCE_FIELDS}
        row.update({field: chosen.get(field, "") for field in REFERENCE_FIELDS} if chosen else {})
        row.update(frame_key=key, split=item.get("split", ""), source=item.get("source", ""),
                   label=label, review_state=state)
        rows.append(row)
    if len({row["frame_key"] for row in rows}) != len(rows):
        raise ValueError("duplicate-frame-key merged")
    return rows
