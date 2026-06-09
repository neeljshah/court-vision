"""src/sim/agent/provenance.py — Blake2b provenance stamper for SimAgent / TeamAgent.

ROADMAP PHASE: Domain 1 — Entity-Agent Layer (D01_entity_agent.md §9 Step 1).
Implements the four public functions called by build.py at agent-construction time:
  content_hash   — deterministic Blake2b hex over sorted (field, value) pairs
  built_from_mtimes — maps parquet paths to ISO-8601 mtime strings
  stamp          — returns an AgentProvenance with content_hash="" placeholder
  stamp_agent    — returns an AgentProvenance with content_hash filled from the agent

stdlib hashlib only; no heavy deps at module load.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sim.agent.schema import SCHEMA_VERSION, AgentProvenance


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sorted_field_pairs(obj: Any) -> List[tuple[str, str]]:
    """Return sorted (field_name, repr(value)) pairs for all dataclass fields.

    Fields whose value is an unhashable mapping (dict) are handled by sorting
    their items() before repr — guarantees determinism regardless of dict
    insertion order (Python 3.7+ dicts are ordered, but this is explicit).

    Only dataclass fields are included (assist_feeders is a dataclass field but
    has hash=False, compare=False — we still include it for provenance purposes,
    with sorted items for determinism).
    """
    pairs: List[tuple[str, str]] = []
    for f in dataclasses.fields(obj):
        val = getattr(obj, f.name)
        if isinstance(val, dict):
            # Sort items so that insertion-order differences don't change the hash.
            val_repr = repr(sorted(val.items()))
        else:
            val_repr = repr(val)
        pairs.append((f.name, val_repr))
    # Sort by field name so field definition order doesn't affect the hash.
    pairs.sort(key=lambda t: t[0])
    return pairs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def content_hash(obj: Any) -> str:
    """Return a Blake2b-256 hex digest over the sorted (field_name, repr(value))
    pairs of *obj* (must be a dataclass instance).

    Properties:
    - Deterministic: same field values -> same hash regardless of call order.
    - Sensitive: changing any single field -> different hash.
    - Order-independent: dict-valued fields (e.g. assist_feeders) are sorted
      before hashing, so insertion order does not matter.

    Uses hashlib.blake2b with digest_size=32 (256 bits = 64 hex chars).
    """
    h = hashlib.blake2b(digest_size=32)
    for field_name, value_repr in _sorted_field_pairs(obj):
        # Encode each pair as "name\x00value\x00" so that a value that starts
        # with the next field's name cannot cause a collision.
        h.update(field_name.encode("utf-8"))
        h.update(b"\x00")
        h.update(value_repr.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def built_from_mtimes(paths: List[str]) -> Dict[str, str]:
    """Return a mapping of existing parquet path -> ISO-8601 mtime string.

    Paths that do not exist on disk are silently skipped (missing parquets are
    a normal condition for VAULT_PROXY agents built without a full local cache).

    The mtime is expressed in UTC with timezone info so the string is unambiguous.
    """
    result: Dict[str, str] = {}
    for p in paths:
        try:
            stat = os.stat(p)
        except (OSError, FileNotFoundError):
            continue
        mtime_utc = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        result[p] = mtime_utc.isoformat()
    return result


def stamp(
    tier: str,
    built_from: Dict[str, str],
    missing_fields: Optional[List[str]] = None,
    recency_asof: Optional[str] = None,
) -> AgentProvenance:
    """Build an AgentProvenance with content_hash="" (placeholder).

    Use stamp_agent() when the SimAgent is available to fill content_hash.

    Args:
        tier:           "FULL_PBP" or "VAULT_PROXY".
        built_from:     dict mapping parquet path/name -> ISO-8601 mtime.
                        Typically produced by built_from_mtimes().
        missing_fields: list of required column names that fell back to league
                        prior (empty list means all columns were present).
        recency_asof:   ISO date string of the last game in the recency window,
                        or None if no recency data was used.

    Returns:
        AgentProvenance with schema_version=SCHEMA_VERSION and content_hash="".
    """
    return AgentProvenance(
        schema_version=SCHEMA_VERSION,
        tier=tier,
        built_from=dict(built_from),
        content_hash="",
        missing_fields=list(missing_fields) if missing_fields is not None else [],
        recency_asof=recency_asof,
    )


def stamp_agent(
    sim_agent: Any,
    tier: str,
    built_from: Dict[str, str],
    missing_fields: Optional[List[str]] = None,
    recency_asof: Optional[str] = None,
) -> AgentProvenance:
    """Build an AgentProvenance with content_hash filled from sim_agent.

    Calls content_hash(sim_agent) to compute the Blake2b hex, then returns a
    fully-populated AgentProvenance.  The hash is computed ONCE at build time
    (per D01 §6 "Provenance hash is computed once at build, ~µs").

    Args:
        sim_agent:      A SimAgent (or any frozen dataclass).
        tier:           "FULL_PBP" or "VAULT_PROXY".
        built_from:     dict mapping parquet path/name -> ISO-8601 mtime.
        missing_fields: required cols that fell back to league prior.
        recency_asof:   last game date in recency window; None = no recency.

    Returns:
        AgentProvenance with schema_version=SCHEMA_VERSION and a 64-char hex
        content_hash.
    """
    ch = content_hash(sim_agent)
    return AgentProvenance(
        schema_version=SCHEMA_VERSION,
        tier=tier,
        built_from=dict(built_from),
        content_hash=ch,
        missing_fields=list(missing_fields) if missing_fields is not None else [],
        recency_asof=recency_asof,
    )
