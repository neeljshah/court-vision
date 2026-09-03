"""Additive historical frozen-family views for the S174 construct.

The current FWER file remains the default reader input.  These constants expose the
sealed S14 blob only when a caller explicitly requests its version.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from typing import Any, Iterable


S14_V1 = "s14-families-v1"
S14_V2 = "s14-families-v2"
S14_V1_PIN = "62702554f6e57ec9f3182e8edc1e4d6a109a3b41"
S14_V1_SHA256 = "906501a6be7373a5223205ebc7252d2c48a8ed126f20b1f7e65b018789c5ee40"
DROP_REASON = "no period market in any local store (S171 2026-09-04)"
DROPPED_FAMILIES = {
    "mlb_inning": DROP_REASON,
    "nba_quarter_shape": DROP_REASON,
}


@dataclass(frozen=True)
class DroppedFamily:
    """Historical family record plus the additive v2 drop annotation."""

    base: Any
    status: str
    reason: str

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base, name)


def mark_dropped(family: Any) -> Any:
    """Return the v2 annotation only for records deliberately dropped in S174."""
    reason = DROPPED_FAMILIES.get(family.name)
    return DroppedFamily(family, "DROPPED", reason) if reason is not None else family


def s14_v1_text() -> str:
    """Return the immutable historical S14 blob after checking its byte hash."""
    result = subprocess.run(["git", "cat-file", "blob", S14_V1_PIN],
                            capture_output=True, check=True)
    raw = result.stdout
    if hashlib.sha256(raw).hexdigest() != S14_V1_SHA256:
        raise ValueError("historical S14 blob SHA-256 does not match its sealed value")
    return raw.decode("ascii")


def canonical_v2_payload(families: Iterable[Any]) -> bytes:
    """Canonical full-history v2 record, including only the two new drop fields."""
    rows = []
    for family in families:
        row = {
            "features": family.features,
            "horizon": family.horizon,
            "hypotheses": family.hypotheses,
            "kind": family.kind,
            "market": family.market,
            "members": list(family.members),
            "name": family.name,
            "q_rule": family.q_rule,
            "sources": list(family.sources),
            "sport": family.sport,
        }
        if family.name in DROPPED_FAMILIES:
            row["reason"] = DROPPED_FAMILIES[family.name]
            row["status"] = "DROPPED"
        rows.append(row)
    payload = {"families": rows, "spec_version": S14_V2, "v1_pin": S14_V1_PIN}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")


def s14_v2_pin(families: Iterable[Any]) -> str:
    """SHA-256 of the reproducible v2 full-history payload."""
    return hashlib.sha256(canonical_v2_payload(families)).hexdigest()
