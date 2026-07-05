"""scripts.platformkit.l4.prereg_sha_stamp -- additive sha256 stamp for prereg artifacts.

F-check-5(ii) (GREENLIGHT_UNCAP_SPEC_2026-07-05.md, R-c) needs a `sha256` field on
pre-registration artifacts (e.g. l4_gate_prereg.json) so a later refresh can detect a
post-hoc goalpost move. This module is the ONLY producer: it computes sha256 over the
canonical JSON (sorted keys, minus any existing `sha256` field) and writes that field
back ADDITIVELY. It refuses to change anything else -- parsed-content-minus-sha is
asserted byte-identical before and after; any difference aborts without writing.

Idempotent: re-stamping an already-stamped file with unchanged content recomputes the
same sha and skips the write (`rewrote: False`).

Also creates a first-seen snapshot copy under `snapshot_dir` on the FIRST stamp of a
given path (by basename) -- the immutable copy F-check-5(i) compares future refreshes
against. Never overwrites an existing snapshot.

NOT run against real data/frontend/ops/l4_gate_prereg.json in this build lane (tests
use tmp_path only) -- the orchestrator runs it once later, ledgered separately.

INVARIANTS: no $ field; no flag flip; no data/registry write; ASCII only; <=120 LOC;
never raises (returns a result dict with ok=False + reason instead).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/l4/test_prereg_sha_stamp.py -q
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Dict


def _canonical_bytes(obj: Dict[str, Any]) -> bytes:
    """Canonical JSON (sorted keys, minus sha256) as ASCII bytes for hashing."""
    minus_sha = {k: v for k, v in obj.items() if k != "sha256"}
    return json.dumps(minus_sha, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":")).encode("ascii")


def compute_sha(obj: Dict[str, Any]) -> str:
    """sha256 hex digest over the canonical JSON (sorted keys, minus sha256 field)."""
    return hashlib.sha256(_canonical_bytes(obj)).hexdigest()


def stamp(path: Path, snapshot_dir: Path) -> Dict[str, Any]:
    """Additively write/refresh the sha256 field on the JSON object at *path*.

    Returns {ok, rewrote, sha256, path, snapshot_path, reason}. Never raises --
    any exception is caught and reported as ok=False with a reason string.
    """
    path = Path(path)
    snapshot_dir = Path(snapshot_dir)
    result: Dict[str, Any] = {
        "ok": False, "rewrote": False, "sha256": None,
        "path": str(path), "snapshot_path": None, "reason": None,
    }
    try:
        raw = path.read_text(encoding="utf-8")
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            result["reason"] = "not_a_json_object"
            return result

        before_minus_sha = _canonical_bytes(obj)
        new_sha = compute_sha(obj)
        old_sha = obj.get("sha256")

        if old_sha == new_sha:
            result.update(ok=True, rewrote=False, sha256=new_sha)
        else:
            stamped = dict(obj)
            stamped["sha256"] = new_sha
            # Refuse-to-touch-anything-else guard: content minus sha must be
            # byte-identical before vs after the field write.
            after_minus_sha = _canonical_bytes(stamped)
            if after_minus_sha != before_minus_sha:
                result["reason"] = "refused_nonadditive_change"
                return result
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(stamped, sort_keys=True, ensure_ascii=True,
                                       indent=1), encoding="ascii")
            tmp.replace(path)
            result.update(ok=True, rewrote=True, sha256=new_sha)

        snap_path = snapshot_dir / path.name
        if not snap_path.exists():
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(path), str(snap_path))
        result["snapshot_path"] = str(snap_path)
        return result
    except Exception as exc:  # noqa: BLE001 -- fail-closed, never raise on the caller
        result["reason"] = "error:%s" % str(exc)[:80]
        return result


def main() -> None:
    print("prereg_sha_stamp: import stamp(path, snapshot_dir) -- not run against real "
          "artifacts from this CLI; the orchestrator invokes it once, ledgered.")


if __name__ == "__main__":
    main()


__all__ = ["compute_sha", "stamp"]
