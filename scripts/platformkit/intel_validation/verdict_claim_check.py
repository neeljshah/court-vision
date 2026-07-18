"""Kind-dispatch bridge: verdict-kind claims inside RANKING stores.

claims_validator.validate_claim routes kind="verdict"/"gate_verdict" rows
here instead of the formula-recompute path (which can only say "criteria.
formula missing"). Two shapes:

  - kind="verdict": the strict field_paths contract -- DELEGATED verbatim to
    the existing verdict_claims_validator.validate_verdict_claim (provenance
    + declared-path consistency, required-fields rail, edge_claimed rail).
  - kind="gate_verdict" (e.g. nba_quality gate-3a): no field_paths by
    design; the claim shares top-level key names with its cited
    *_verdict.json. Verified generically: every shared scalar field (one
    dict level deep) must match the artifact.

Float tolerance on the generic path is 5e-4: gate claims embed
DISPLAY-ROUNDED quotes (3-4 decimals) of full-precision artifact values; a
real divergence is orders larger. "X/Y" ratio strings (the sign_holds
convention) compare X against the artifact value and Y against its n_folds.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FLOAT_TOL = 5e-4
_SKIP_KEYS = frozenset({
    "claim_id", "kind", "question", "criteria", "verdict_file", "field_paths",
    "computed_at", "caveats", "edge_claimed", "source_files", "gate_module",
    "corpus_ids", "per_cutoff",
})
_RATIO_RE = re.compile(r"^(\d+)\s*/\s*(\d+)$")

VERDICT_KINDS = ("gate_verdict", "verdict")


def _scalar_matches(claimed: Any, actual: Any) -> bool:
    if isinstance(claimed, bool) or isinstance(actual, bool):
        return bool(claimed) == bool(actual)
    if isinstance(claimed, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(claimed) - float(actual)) <= _FLOAT_TOL
    return str(claimed) == str(actual)


def _compare_pairs(claim: dict[str, Any], doc: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    """Shared-top-level-key comparison list [(key, claimed, actual)]. Dicts
    recurse one level over shared scalar sub-keys; 'X/Y' ratio strings expand
    to (X, artifact value) + (Y, artifact n_folds); type-incompatible quote
    formatting is skipped (not a factual divergence)."""
    pairs: list[tuple[str, Any, Any]] = []
    for key, claimed in claim.items():
        if key in _SKIP_KEYS or key not in doc:
            continue
        actual = doc[key]
        if isinstance(claimed, dict) and isinstance(actual, dict):
            for sub, sub_claimed in claimed.items():
                if sub in actual and isinstance(sub_claimed, (str, int, float, bool)):
                    pairs.append((f"{key}.{sub}", sub_claimed, actual[sub]))
            continue
        if isinstance(claimed, str) and isinstance(actual, (int, float)) \
                and not isinstance(actual, bool):
            m = _RATIO_RE.match(claimed)
            if m:
                pairs.append((key, int(m.group(1)), actual))
                if "n_folds" in doc:
                    pairs.append((f"{key}(denominator)", int(m.group(2)), doc["n_folds"]))
            continue
        if isinstance(claimed, (str, int, float, bool)):
            pairs.append((key, claimed, actual))
    return pairs


def validate_verdict_claim(claim: dict[str, Any]) -> "ClaimVerdict":
    from scripts.platformkit.intel_validation.claims_validator import ClaimVerdict

    claim_id = claim.get("claim_id", "<missing-id>")

    if claim.get("kind") == "verdict":
        # Strict field_paths contract -- reuse the existing validator verbatim.
        from scripts.platformkit.intel_validation.verdict_claims_validator import (
            validate_verdict_claim as _strict,
        )
        r = _strict(claim)
        return ClaimVerdict(r.claim_id, r.verdict, reason=r.reason,
                            first_divergence=r.first_divergence)

    verdict_file = claim.get("verdict_file")
    if not verdict_file:
        return ClaimVerdict(claim_id, "UNVERIFIABLE",
                            reason="verdict_file missing on gate_verdict claim")
    path = _REPO_ROOT / verdict_file
    if not path.exists():
        return ClaimVerdict(claim_id, "UNVERIFIABLE",
                            reason=f"verdict_file not found: {verdict_file}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 -- fail closed
        return ClaimVerdict(claim_id, "UNVERIFIABLE", reason=f"verdict_file unreadable: {e}")

    pairs = _compare_pairs(claim, doc)
    if not pairs:
        return ClaimVerdict(claim_id, "UNVERIFIABLE",
                            reason="no comparable fields between claim and verdict_file")
    for key, claimed, actual in pairs:
        if actual is None or not _scalar_matches(claimed, actual):
            return ClaimVerdict(
                claim_id, "MISMATCH",
                reason=f"claim quotes {key}={claimed!r} but verdict_file has {actual!r}",
                first_divergence={"field": key, "claimed": claimed, "recomputed": actual},
            )
    return ClaimVerdict(claim_id, "VERIFIED",
                        reason=f"verdict_file cross-check: {len(pairs)} fields match")
