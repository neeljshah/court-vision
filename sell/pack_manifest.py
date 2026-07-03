"""sell.pack_manifest -- a stable, reproducible sha256 manifest of the pack.

Hashes every artifact in the evidence pack so any tampering is detectable: change
one byte of any packed file and its digest -- and the manifest's own roll-up
digest -- changes. Hashing is content-only and order-independent (entries are
keyed by the artifact's relative name and sorted), so the manifest is reproducible
across machines and runs.

There are two hash inputs supported, mirroring how the pack is assembled in
memory then written:
  * manifest_for_objects -- hash the CANONICAL JSON bytes of in-memory objects
    (the same canonical_json used for signing: sorted keys, tight separators,
    ASCII). This is what evidence_pack uses so the manifest is computed over the
    exact bytes that will be written.
  * manifest_for_files   -- hash the raw bytes of files already on disk.

INVARIANTS: build only under sell/; <=300 LOC; ASCII only; no secrets; pure (no
network); reproducible digests; no $-edge field.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from sell.signing import canonical_json

MANIFEST_VERSION = "sell.pack_manifest.v1"
HASH_ALGO = "sha256"


def hash_bytes(data: bytes) -> str:
    """Return the hex sha256 of *data* (the one hashing primitive used here)."""
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(obj: Any) -> bytes:
    """Canonical, reproducible byte image of a JSON-like object (signing image)."""
    return canonical_json(obj)


def _entry(name: str, data: bytes) -> Dict[str, Any]:
    return {"name": name, "algo": HASH_ALGO, "size": len(data),
            "sha256": hash_bytes(data)}


def _roll_up(entries: Iterable[Dict[str, Any]]) -> str:
    """A single digest over the per-artifact digests (order-independent).

    Computed over "<name>:<sha256>" lines sorted by name, so the roll-up is stable
    regardless of the order artifacts were added. A change to ANY artifact -- or to
    the set of artifacts -- changes this value.
    """
    lines = sorted("%s:%s" % (e["name"], e["sha256"]) for e in entries)
    blob = "\n".join(lines).encode("ascii")
    return hash_bytes(blob)


def _manifest(entries: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    ordered = [entries[k] for k in sorted(entries)]
    return {
        "version": MANIFEST_VERSION,
        "algo": HASH_ALGO,
        "n_artifacts": len(ordered),
        "artifacts": ordered,                 # sorted by name -> reproducible
        "manifest_sha256": _roll_up(ordered),
    }


def manifest_for_objects(named_objects: Dict[str, Any]) -> Dict[str, Any]:
    """Build a manifest hashing the canonical JSON bytes of each named object.

    *named_objects* maps artifact relative name -> JSON-like object. The manifest
    hashes the exact canonical bytes that the pack writer will emit, so the
    on-disk file and its manifest entry always agree.
    """
    entries: Dict[str, Dict[str, Any]] = {}
    for name in sorted(named_objects):
        entries[name] = _entry(name, canonical_bytes(named_objects[name]))
    return _manifest(entries)


def manifest_for_files(named_paths: Dict[str, Path]) -> Dict[str, Any]:
    """Build a manifest hashing the raw bytes of files already on disk.

    *named_paths* maps artifact relative name -> absolute path. A missing file is
    recorded with sha256=None and size=-1 (an honest "absent", never a fake hash).
    """
    entries: Dict[str, Dict[str, Any]] = {}
    for name in sorted(named_paths):
        p = Path(named_paths[name])
        if not p.exists():
            entries[name] = {"name": name, "algo": HASH_ALGO, "size": -1,
                             "sha256": None, "status": "absent"}
            continue
        entries[name] = _entry(name, p.read_bytes())
    return _manifest(entries)


def verify_manifest(manifest: Dict[str, Any],
                    named_objects: Dict[str, Any]) -> Tuple[bool, Dict[str, str]]:
    """Recompute object digests and compare to *manifest*. Returns (ok, mismatches).

    A mismatch maps artifact name -> reason. Constant-content objects reproduce the
    recorded digests; any drift (or a missing / extra artifact) is reported.
    """
    recomputed = manifest_for_objects(named_objects)
    mismatches: Dict[str, str] = {}
    have = {e["name"]: e["sha256"] for e in manifest.get("artifacts", [])}
    want = {e["name"]: e["sha256"] for e in recomputed["artifacts"]}
    for name in sorted(set(have) | set(want)):
        if name not in have:
            mismatches[name] = "extra artifact not in manifest"
        elif name not in want:
            mismatches[name] = "manifest artifact missing from objects"
        elif have[name] != want[name]:
            mismatches[name] = "sha256 mismatch (tampered)"
    if manifest.get("manifest_sha256") != recomputed["manifest_sha256"]:
        mismatches.setdefault("__roll_up__", "manifest_sha256 mismatch")
    return (len(mismatches) == 0, mismatches)


__all__ = [
    "MANIFEST_VERSION",
    "HASH_ALGO",
    "hash_bytes",
    "canonical_bytes",
    "manifest_for_objects",
    "manifest_for_files",
    "verify_manifest",
]
