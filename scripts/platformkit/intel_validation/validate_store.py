"""validate_store -- streaming-validate claim stores + write the paired summary.

Runs claims_validator_batch.validate_claims_file_batched (memory-bounded) on
each named store and writes `<stem>_validation.json` next to it -- the exact
pairing rule discover_families / ask.py require. Producers that skip this step
leave their store verified-but-invisible to the ask layer and the
intel_weighting CLI; this closes that gap with one command.

    python -m scripts.platformkit.intel_validation.validate_store <stem-or-path> [...]

Stores are processed SEQUENTIALLY (never parallelize validator runs).
"""
from __future__ import annotations

import sys
from pathlib import Path

from scripts.platformkit.intel_validation.claims_validator import write_summary
from scripts.platformkit.intel_validation.claims_validator_batch import (
    validate_claims_file_batched,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CLAIMS_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"


def validate_and_write(stem_or_path: str) -> dict:
    p = Path(stem_or_path)
    if not p.suffix:
        p = CLAIMS_DIR / f"{stem_or_path}.jsonl"
    summary = validate_claims_file_batched(p)
    out = p.with_name(f"{p.stem}_validation.json")
    # ponytail: reuse write_summary's numpy-safe json.dump (_json_numpy_default)
    # instead of a second hand-rolled json.dumps -- this path used to crash
    # TypeError: Object of type int64 is not JSON serializable on any store
    # whose MISMATCH first_divergence carries a raw numpy scalar id/value.
    write_summary(summary, out)
    return {"store": p.name, "n_claims": summary.n_claims,
            "n_verified": summary.n_verified, "n_mismatch": summary.n_mismatch,
            "n_unverifiable": summary.n_unverifiable, "out": str(out)}


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: validate_store <stem-or-path> [...]")
        return 2
    rc = 0
    for arg in argv:
        r = validate_and_write(arg)
        ok = r["n_mismatch"] == 0 and r["n_unverifiable"] == 0
        print(f"{r['store']}: {r['n_verified']}/{r['n_claims']} verified, "
              f"{r['n_mismatch']} mismatch, {r['n_unverifiable']} unverifiable "
              f"-> {'OK' if ok else 'FAIL'}")
        rc = rc if ok else 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
