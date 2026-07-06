"""Sidecar `.index.jsonl` builder (spec sec 4 SERVING AT SCALE, LANE L-D).

Reads a producer `<family>.jsonl` + its `<family>_validation.json` (the
naming convention every store in data/cache/intel_claims/ already follows --
`ask.py:discover_claim_source_pairs`) and writes `<family>.index.jsonl`: one
line per claim `{claim_id, metric, window, entity_key, computed_at,
byte_offset, verdict, source_mtime}`. `verdict` is copied from the
validation summary AT INDEX-BUILD TIME (R5/self-critique C: the index is
always built LAST, after batch validation, in the same regen sequence).

STALENESS GUARD (self-critique C): the index stores `source_mtime`, the
max mtime across the claims jsonl + validation json at build time (not the
underlying data parquet -- those two files are regenerated together by the
factory, so their mtimes ARE the staleness signal a caller can check without
re-parsing either file). A caller (ask.py) compares this to the LIVE files'
current mtime; any drift (validation re-run without a new index, or vice
versa) means "treat as stale," never "trust silently."

ATOMIC: same tmp-then-os.replace pattern as claims_factory.py / precedent at
basketball_claims_io.atomic_write_parquet -- a crashed build never leaves a
half-written index for ask.py to partially read.

CLI: python -m scripts.platformkit.intel_query.claims_index --family <name>
     (defaults to data/cache/intel_claims/; --claims-dir to override, tests only)
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CLAIMS_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"


class IndexError_(ValueError):
    """Fail-closed: claims file missing/malformed -- no index written."""


def _validation_verdicts(validation_path: Path) -> dict[str, str]:
    with open(validation_path, "r", encoding="ascii", errors="strict") as f:
        summary = json.load(f)
    return {d["claim_id"]: d.get("verdict") for d in summary.get("details", [])}


def build_index(family: str, claims_dir: Path | None = None) -> dict[str, Any]:
    """Build `<family>.index.jsonl` from `<family>.jsonl` + its validation
    JSON. Raises IndexError_ (no artifact written) if either file is
    missing or the claims jsonl has malformed lines -- fail-closed, matching
    the factory's own FactoryError convention."""
    claims_dir = claims_dir or _DEFAULT_CLAIMS_DIR
    claims_path = claims_dir / f"{family}.jsonl"
    validation_path = claims_dir / f"{family}_validation.json"
    if not claims_path.exists():
        raise IndexError_(f"claims file not found: {claims_path}")
    if not validation_path.exists():
        raise IndexError_(f"validation summary not found: {validation_path}")

    verdicts = _validation_verdicts(validation_path)
    source_mtime = max(claims_path.stat().st_mtime, validation_path.stat().st_mtime)

    index_rows: list[dict[str, Any]] = []
    with open(claims_path, "rb") as f:
        offset = 0
        for line in f:
            stripped = line.strip()
            if not stripped:
                offset += len(line)
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise IndexError_(f"{claims_path}: malformed line at byte_offset={offset}: {e}") from e
            criteria = row.get("criteria", {})
            index_rows.append({
                "claim_id": row.get("claim_id"),
                "metric": criteria.get("metric"),
                "window": criteria.get("window"),
                "entity_key": criteria.get("entity_key"),
                "computed_at": row.get("computed_at"),
                "byte_offset": offset,
                "verdict": verdicts.get(row.get("claim_id")),
                "source_mtime": source_mtime,
            })
            offset += len(line)

    index_path = claims_dir / f"{family}.index.jsonl"
    tmp_path = index_path.with_name(f"{index_path.stem}.{uuid.uuid4().hex}.tmp{index_path.suffix}")
    with open(tmp_path, "w", encoding="ascii", errors="strict") as f:
        for row in index_rows:
            f.write(json.dumps(row) + "\n")
    os.replace(tmp_path, index_path)

    return {
        "family": family,
        "n_indexed": len(index_rows),
        "n_verified": sum(1 for r in index_rows if r["verdict"] == "VERIFIED"),
        "index_path": str(index_path),
        "source_mtime": source_mtime,
    }


def is_index_fresh(family: str, claims_dir: Path | None = None) -> bool:
    """True iff `<family>.index.jsonl` exists AND its stored `source_mtime`
    matches (>=) the LIVE max-mtime of claims jsonl + validation json right
    now. False on any missing/malformed piece -- callers (ask.py) must
    treat False as "fall back to full load," never guess VERIFIED."""
    claims_dir = claims_dir or _DEFAULT_CLAIMS_DIR
    claims_path = claims_dir / f"{family}.jsonl"
    validation_path = claims_dir / f"{family}_validation.json"
    index_path = claims_dir / f"{family}.index.jsonl"
    if not (claims_path.exists() and validation_path.exists() and index_path.exists()):
        return False
    try:
        with open(index_path, "r", encoding="ascii", errors="strict") as f:
            first_line = f.readline().strip()
        if not first_line:
            return True  # empty family (0 claims) -- vacuously fresh, nothing to be stale
        stored_mtime = json.loads(first_line).get("source_mtime")
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False
    if stored_mtime is None:
        return False
    live_mtime = max(claims_path.stat().st_mtime, validation_path.stat().st_mtime)
    return stored_mtime >= live_mtime


def discover_families(claims_dir: Path | None = None) -> list[str]:
    """Family stems that have BOTH a claims jsonl and a validation json --
    the same pairing rule as ask.py's discover_claim_source_pairs, restated
    here (not imported) to avoid an intel_query -> intel_query circular
    concern between siblings; both read the identical on-disk convention."""
    claims_dir = claims_dir or _DEFAULT_CLAIMS_DIR
    if not claims_dir.exists():
        return []
    families = []
    for p in sorted(claims_dir.glob("*.jsonl")):
        if p.name.endswith(".index.jsonl"):
            continue
        if (claims_dir / f"{p.stem}_validation.json").exists():
            families.append(p.stem)
    return families


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the sidecar .index.jsonl for a claims family")
    parser.add_argument("--family", default=None, help="single family; default = every discoverable family")
    parser.add_argument("--claims-dir", default=None)
    args = parser.parse_args(argv)

    claims_dir = Path(args.claims_dir) if args.claims_dir else None
    families = [args.family] if args.family else discover_families(claims_dir)
    if not families:
        print("no families with a paired (claims.jsonl, validation.json) found")
        return 1

    for fam in families:
        result = build_index(fam, claims_dir)
        print(f"{result['family']}: n_indexed={result['n_indexed']} n_verified={result['n_verified']} -> {result['index_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
