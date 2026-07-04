"""Independent verdict-claims validator (claim_kind=verdict sibling).

Sibling to claims_validator.py (which recomputes RANKING claims from raw
parquets). This module validates a DIFFERENT claim kind: a verdict-claim
row asserts "gate X produced verdict Y with number Z", citing an on-disk
gate-verdict JSON as the sole evidence. Validation here is PROVENANCE +
CONSISTENCY, not a gate re-run:

    1. verdict_file must exist and parse as JSON.
    2. every field the claim asserts (verdict, primary_number,
       planted_null_passed, ...) must be re-extracted from the cited
       verdict_file at the claim's declared JSON path and match exactly
       (numbers compared with a tight float tolerance).
    3. this module NEVER imports a gate module and NEVER re-runs a gate --
       it only re-reads the artifact the gate already wrote.

Fail-closed: any missing file, missing field, unparsable JSON, or
type/shape surprise is UNVERIFIABLE (never silently treated as VERIFIED).
A value that resolves but disagrees with the claim is MISMATCH.

Claim contract (claim_kind=verdict):
    {
      "claim_id": str,
      "kind": "verdict",
      "question": str,
      "gate_module": str,            # human-readable label, NOT imported
      "verdict_file": str,            # path relative to repo root
      "verdict": str,                 # e.g. "REJECT" / "NOT_TESTABLE" / "SHIP"
      "primary_number": float,        # the one headline number for this verdict
      "corpus_ids": [str, ...],
      "planted_null_passed": bool,    # True == the planted-null check held
                                       #  (i.e. null died / was rejected, per
                                       #  this gate's own convention)
      "edge_claimed": false,          # MUST be false; never a $ claim
      "field_paths": {                # dot-paths into verdict_file JSON for
        "verdict": "verdict",         #  each asserted field above, so this
        "primary_number": "...",      #  validator never guesses field names
        "planted_null_passed": "..."  #  across differently-shaped gates
      },
      "computed_at": str,
      "caveats": [str, ...]
    }

CLI:
    python -m scripts.platformkit.intel_validation.verdict_claims_validator <claims.jsonl>
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = REPO_ROOT / "data" / "frontend" / "ops" / "intel_verdict_claims_validation.json"
NUMBER_TOLERANCE = 1e-6

REQUIRED_FIELDS = (
    "claim_id", "kind", "gate_module", "verdict_file", "verdict",
    "primary_number", "corpus_ids", "planted_null_passed", "edge_claimed",
    "field_paths",
)


@dataclass
class VerdictClaimResult:
    claim_id: str
    verdict: str  # VERIFIED | MISMATCH | UNVERIFIABLE
    reason: str = ""
    first_divergence: dict[str, Any] | None = None


@dataclass
class VerdictValidationSummary:
    component: str = "intel_verdict_claims_validation"
    generated_at: str = ""
    n_claims: int = 0
    n_verified: int = 0
    n_mismatch: int = 0
    n_unverifiable: int = 0
    edge_claimed: bool = False
    details: list[dict[str, Any]] = field(default_factory=list)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with open(path, "r", encoding="ascii", errors="strict") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _resolve_path(payload: Any, dotted: str) -> tuple[bool, Any]:
    """Resolve a dot-path (e.g. 'atp.real.pooled_delta_h1_minus_h0') into a
    loaded JSON structure. Returns (found, value). No wildcards, no eval --
    plain attribute/key/index walk so this stays a pure lookup, never an
    executable expression."""
    node = payload
    for part in dotted.split("."):
        if isinstance(node, dict):
            if part not in node:
                return False, None
            node = node[part]
        elif isinstance(node, list):
            try:
                idx = int(part)
            except ValueError:
                return False, None
            if idx < 0 or idx >= len(node):
                return False, None
            node = node[idx]
        else:
            return False, None
    return True, node


def _values_match(claimed: Any, actual: Any) -> bool:
    if isinstance(claimed, bool) or isinstance(actual, bool):
        return bool(claimed) == bool(actual)
    if isinstance(claimed, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(claimed) - float(actual)) <= NUMBER_TOLERANCE
    if isinstance(claimed, list) and isinstance(actual, list):
        return list(claimed) == list(actual)
    return claimed == actual


def validate_verdict_claim(claim: dict[str, Any]) -> VerdictClaimResult:
    claim_id = claim.get("claim_id", "<missing-id>")

    missing = [f for f in REQUIRED_FIELDS if f not in claim]
    if missing:
        return VerdictClaimResult(
            claim_id, "UNVERIFIABLE", reason=f"claim missing required field(s): {missing}"
        )

    if claim.get("edge_claimed") is not False:
        return VerdictClaimResult(
            claim_id, "UNVERIFIABLE",
            reason="edge_claimed must be exactly false -- no $-edge claims permitted",
        )

    verdict_file_rel = claim["verdict_file"]
    verdict_path = REPO_ROOT / verdict_file_rel
    if not verdict_path.exists():
        return VerdictClaimResult(
            claim_id, "UNVERIFIABLE", reason=f"verdict_file not found: {verdict_file_rel}"
        )

    try:
        with open(verdict_path, "r", encoding="ascii", errors="strict") as f:
            verdict_payload = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return VerdictClaimResult(
            claim_id, "UNVERIFIABLE", reason=f"verdict_file not valid ascii JSON: {e}"
        )

    field_paths = claim.get("field_paths") or {}
    if not isinstance(field_paths, dict) or not field_paths:
        return VerdictClaimResult(
            claim_id, "UNVERIFIABLE", reason="field_paths missing or empty -- cannot re-derive fields"
        )

    checked_fields = ("verdict", "primary_number", "planted_null_passed")
    for check_field in checked_fields:
        if check_field not in field_paths:
            return VerdictClaimResult(
                claim_id, "UNVERIFIABLE",
                reason=f"field_paths does not declare a path for required field {check_field!r}",
            )
        dotted = field_paths[check_field]
        found, actual = _resolve_path(verdict_payload, dotted)
        if not found:
            return VerdictClaimResult(
                claim_id, "UNVERIFIABLE",
                reason=f"field_paths[{check_field!r}]={dotted!r} not resolvable in {verdict_file_rel}",
            )
        claimed_value = claim.get(check_field)
        if not _values_match(claimed_value, actual):
            return VerdictClaimResult(
                claim_id, "MISMATCH",
                reason=(
                    f"{check_field}: claimed={claimed_value!r} "
                    f"recomputed(from {dotted!r})={actual!r}"
                ),
                first_divergence={
                    "field": check_field, "claimed": claimed_value, "recomputed": actual,
                },
            )

    return VerdictClaimResult(
        claim_id, "VERIFIED",
        reason=f"verdict={claim['verdict']} matched {verdict_file_rel} at all declared field_paths",
    )


def validate_verdict_claims_file(path: Path) -> VerdictValidationSummary:
    claims = _load_jsonl(path)
    summary = VerdictValidationSummary(generated_at=datetime.now(timezone.utc).isoformat())
    for claim in claims:
        result = validate_verdict_claim(claim)
        summary.n_claims += 1
        if result.verdict == "VERIFIED":
            summary.n_verified += 1
        elif result.verdict == "MISMATCH":
            summary.n_mismatch += 1
        else:
            summary.n_unverifiable += 1
        summary.details.append({
            "claim_id": result.claim_id,
            "verdict": result.verdict,
            "reason": result.reason,
            "first_divergence": result.first_divergence,
        })
    return summary


def write_summary(summary: VerdictValidationSummary, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "component": summary.component,
        "generated_at": summary.generated_at,
        "n_claims": summary.n_claims,
        "n_verified": summary.n_verified,
        "n_mismatch": summary.n_mismatch,
        "n_unverifiable": summary.n_unverifiable,
        "edge_claimed": summary.edge_claimed,
        "details": summary.details,
    }
    with open(output_path, "w", encoding="ascii", errors="strict") as f:
        json.dump(payload, f, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent verdict-claims validator")
    parser.add_argument("claims_jsonl", type=str, help="path to verdict-claims JSONL file")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    claims_path = Path(args.claims_jsonl)
    if not claims_path.exists():
        print(f"UNVERIFIABLE: claims file not found: {claims_path}")
        return 1

    summary = validate_verdict_claims_file(claims_path)
    write_summary(summary, Path(args.output))

    print(
        f"n_claims={summary.n_claims} verified={summary.n_verified} "
        f"mismatch={summary.n_mismatch} unverifiable={summary.n_unverifiable}"
    )
    for d in summary.details:
        print(f"  {d['claim_id']}: {d['verdict']} -- {d['reason']}")
    return 0 if summary.n_mismatch == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
