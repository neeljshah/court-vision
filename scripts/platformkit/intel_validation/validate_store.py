"""validate_store -- streaming-validate claim stores + write the paired summary.

Runs claims_validator_batch.validate_claims_file_batched (memory-bounded) on
each named store and writes `<stem>_validation.json` next to it -- the exact
pairing rule discover_families / ask.py require. Producers that skip this step
leave their store verified-but-invisible to the ask layer and the
intel_weighting CLI; this closes that gap with one command.

    python -m scripts.platformkit.intel_validation.validate_store <stem-or-path> [...]

Stores are processed SEQUENTIALLY (never parallelize validator runs).

RIGOR-SWEEP FIX (2026-07-17): claims_validator_batch only knows how to
recompute `kind=ranking` claims (criteria.formula + a leaderboard). Six
stores in data/cache/intel_claims/ are NOT ranking claims -- they are
audit/verdict LEDGERS (no criteria.formula by design, most have no `kind`
field at all): claim_weights (per-family Brier weighting ledger),
false_discovery_ledger (FDR accounting), gate_verdict_claims (kind=verdict --
already has its OWN dedicated validator, verdict_claims_validator.py, whose
output ask.py already reads via _LEGACY_VALIDATION_OVERRIDES in ask.py),
ingame_distributional_crps_ledger (CRPS benchmark ledger),
interaction_factory_ledger (interaction-mining survivor ledger),
prereg_hypothesis_ledger (preregistered-hypothesis ledger). Running any of
these through the ranking recompute used to write a `<stem>_validation.json`
reporting every single row "UNVERIFIABLE -- criteria.formula missing" --
a validator/store CATEGORY MISMATCH (wrong tool), not a real gap; for
gate_verdict_claims it was actively misleading since a correct sidecar
already exists elsewhere (data/frontend/ops/intel_verdict_claims_validation.json,
14/17 VERIFIED) and ask.py never reads the in-directory one anyway. Skipping
these here (root-caused once, in the one function every caller routes
through) means discover_families()/ask.py's glob no longer pairs a
`<stem>_validation.json` for them, so they correctly drop out of the ask()
claims surface instead of falsely reporting 100% UNVERIFIABLE.
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

# Known non-ranking-claim stems (see module docstring). Not a general kind-
# sniffer on purpose: this set is small, stable, and enumerable -- adding a
# per-row "peek at kind" heuristic would risk silently swallowing a genuine
# future formula-missing regression in a real ranking producer.
_NOT_RANKING_CLAIM_STORES = frozenset({
    "claim_weights",
    "false_discovery_ledger",
    "gate_verdict_claims",
    "ingame_distributional_crps_ledger",
    "interaction_factory_ledger",
    "prereg_hypothesis_ledger",
})


def validate_and_write(stem_or_path: str) -> dict:
    p = Path(stem_or_path)
    if not p.suffix:
        p = CLAIMS_DIR / f"{stem_or_path}.jsonl"
    if p.stem in _NOT_RANKING_CLAIM_STORES:
        return {"store": p.name, "skipped": True,
                "reason": "not a ranking-claims store (verdict/ledger kind) -- "
                          "see validate_store.py docstring"}
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
        if r.get("skipped"):
            print(f"{r['store']}: SKIPPED -- {r['reason']}")
            continue
        ok = r["n_mismatch"] == 0 and r["n_unverifiable"] == 0
        print(f"{r['store']}: {r['n_verified']}/{r['n_claims']} verified, "
              f"{r['n_mismatch']} mismatch, {r['n_unverifiable']} unverifiable "
              f"-> {'OK' if ok else 'FAIL'}")
        rc = rc if ok else 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
