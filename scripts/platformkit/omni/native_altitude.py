"""scripts.platformkit.omni.native_altitude -- P3 native-altitude scoring contract.

Every signal is scored at the FINEST observable it claims to move
(distributionally, vs the best existing model of that observable), and
verdicts are PER MARKET FAMILY -- a game-endpoint REJECT is not a rejection
at props/mainlines altitude. See .planning/omni/handoff/
P3_native_altitude_contract_draft.md for the design.

This module does NOT compute CRPS/logloss/reliability itself -- that stays in
the existing signal-audit / eval-gate flows (src.loop.gate, proof_common
run_v3, scripts/platformkit/eval_gate/). This is only the CONTRACT + LEDGERING
seam: a manifest those flows can adopt, and a thin wrapper that turns their
per-family verdict dict into claims in scripts.platformkit.omni.claims_ledger.

INVARIANTS: pandas + stdlib only. <=300 LOC. ASCII stdout. Never writes
data/registry/. No $/edge claims.
"""
from __future__ import annotations

import json
from typing import Any

from scripts.platformkit.omni import claims_ledger as cl

NATIVE_OBSERVABLES = {
    "minutes_dist", "usage_share", "shot_quality", "possession_outcome",
    "pace", "to_rate", "game_total", "game_winprob",
}
METRICS = {"crps", "logloss", "reliability"}
VERDICTS = {"ACCEPT", "REJECT", "NOT_TESTABLE"}

_LIFECYCLE_BY_VERDICT = {"ACCEPT": "accepted", "REJECT": "rejected", "NOT_TESTABLE": "screened"}
_TYPE_BY_VERDICT = {"ACCEPT": "effect", "REJECT": "negative", "NOT_TESTABLE": "meta"}

_REQUIRED_FIELDS = (
    "signal_name", "sport", "native_observable", "metric", "baseline_model",
    "market_families", "regime_scope", "corpus",
)


def validate_contract(c: dict) -> None:
    """Raise ValueError loudly if *c* is missing a required field or uses an
    unknown enum value. No return value -- call before build_contract's
    caller trusts *c*."""
    if not isinstance(c, dict):
        raise ValueError(f"contract must be a dict, got {type(c)!r}")
    missing = [f for f in _REQUIRED_FIELDS if not c.get(f)]
    if missing:
        raise ValueError(f"native-altitude contract missing required field(s): {missing}")
    if c["native_observable"] not in NATIVE_OBSERVABLES:
        raise ValueError(
            f"unknown native_observable {c['native_observable']!r}; "
            f"expected one of {sorted(NATIVE_OBSERVABLES)}"
        )
    if c["metric"] not in METRICS:
        raise ValueError(f"unknown metric {c['metric']!r}; expected one of {sorted(METRICS)}")
    if not isinstance(c["market_families"], list) or not c["market_families"]:
        raise ValueError("contract.market_families must be a non-empty list")


def build_contract(
    signal_name: str, sport: str, native_observable: str, metric: str,
    baseline_model: str, market_families: list[str], regime_scope: str,
    corpus: str,
) -> dict:
    """Assemble + validate a contract dict. Convenience only -- callers may
    also build the dict by hand and call validate_contract() directly."""
    c = {
        "signal_name": signal_name, "sport": sport,
        "native_observable": native_observable, "metric": metric,
        "baseline_model": baseline_model, "market_families": list(market_families),
        "regime_scope": regime_scope, "corpus": corpus,
    }
    validate_contract(c)
    return c


def record_verdicts(contract: dict, verdicts: dict[str, dict[str, Any]], base_dir=None) -> list[str]:
    """Write ONE claim per (signal, family) in *verdicts* into the claims
    ledger. *verdicts* maps market_family -> {verdict, delta, ci_low,
    ci_high, n}. verdict must be one of VERDICTS.

    Content-hashed claim_id (scripts.platformkit.omni.claims_ledger.
    make_claim_id) means a second identical run journals the same claim_id
    again (add_claim is idempotent-by-id on replay: rebuild_parquet collapses
    to the latest state per id, so re-running does not duplicate rows).
    Returns the list of claim_ids written, in *verdicts* iteration order.
    """
    validate_contract(contract)
    claim_ids: list[str] = []
    for family, v in verdicts.items():
        verdict = v.get("verdict")
        if verdict not in VERDICTS:
            raise ValueError(f"unknown verdict {verdict!r} for family {family!r}; expected one of {VERDICTS}")
        statement = (
            f"{contract['signal_name']} native-altitude {contract['metric']} "
            f"vs {contract['baseline_model']} on {family}: {verdict}"
        )
        scope = {
            "sport": contract["sport"],
            "regime": contract["regime_scope"],
            "market_families": [family],
        }
        claim = {
            "statement": statement,
            "type": _TYPE_BY_VERDICT[verdict],
            "scope": scope,
            "topic": contract["native_observable"],
            "lifecycle": _LIFECYCLE_BY_VERDICT[verdict],
            "effect": {
                "metric": contract["metric"],
                "size": v.get("delta"),
                "ci_low": v.get("ci_low"),
                "ci_high": v.get("ci_high"),
                "n": v.get("n"),
            },
            "provenance": {"created_by_lane": "P3_native_altitude", "contract": contract},
            "links": {"market_families": [family]},
        }
        claim_ids.append(cl.add_claim(claim, base_dir=base_dir))
    return claim_ids


def per_family_summary(signal_name: str, sport: str | None = None, base_dir=None) -> dict[str, dict]:
    """Query the ledger back for *signal_name* and return {family: {verdict,
    lifecycle, claim_id}} -- one entry per market family the signal has been
    scored on. Proves the dual index (ledger query by topic/sport) is enough
    to drive a re-audit lane without re-parsing statements."""
    df = cl.query(sport=sport, base_dir=base_dir)
    out: dict[str, dict] = {}
    lifecycle_to_verdict = {v: k for k, v in _LIFECYCLE_BY_VERDICT.items()}
    for _, row in df.iterrows():
        if not row["statement"].startswith(f"{signal_name} native-altitude"):
            continue
        scope = json.loads(row["scope_json"])
        for fam in scope.get("market_families") or []:
            out[fam] = {
                "verdict": lifecycle_to_verdict.get(row["lifecycle"], row["lifecycle"]),
                "lifecycle": row["lifecycle"],
                "claim_id": row["claim_id"],
            }
    return out


__all__ = [
    "NATIVE_OBSERVABLES", "METRICS", "VERDICTS",
    "validate_contract", "build_contract", "record_verdicts", "per_family_summary",
]
