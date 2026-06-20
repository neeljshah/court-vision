"""governance.risk_register -- the product's top honesty/correctness risks, each
bound to the gate that ENFORCES its mitigation.

Milestone-10 turns every honesty invariant into an enforced, tested gate. This
register is the human-readable map from RISK -> MITIGATION -> OWNING GATE, so a
reviewer can see, at a glance, that no risk is unowned. It is pure data plus a
``render`` helper; it makes no decision, performs no I/O, and never authorizes a
bet or flips a flag.

The ``status`` of each risk is intentionally NOT "closed": these are standing
risks whose mitigation is an ALWAYS-ON gate. ``gated`` means "an enforced gate
guards this on every governance run"; ``monitored`` means the gate is advisory /
single-process-exact (documented limitation).

INVARIANTS: build only under governance/; <=300 LOC; ASCII; no secrets; no I/O;
never authorizes a bet; never flips a flag.
"""
from __future__ import annotations

from typing import Any, Dict, List, NamedTuple

RISK_REGISTER_VERSION = "governance.risk_register.v1"


class Risk(NamedTuple):
    """One standing product risk and the gate that enforces its mitigation.

    *id*           short stable identifier.
    *description*  what could go wrong (the honesty/correctness failure mode).
    *mitigation*   the control that prevents it.
    *owning_gate*  the governance gate (module) that enforces the mitigation.
    *status*       "gated" (enforced every run) or "monitored" (advisory / a
                   documented single-process-exact guard).
    """
    id: str
    description: str
    mitigation: str
    owning_gate: str
    status: str


#: The standing register. One entry per top risk; each owns exactly one gate.
RISKS: List[Risk] = [
    Risk(
        id="retracted_number_resurfaces",
        description=("A retracted measurement-artifact figure (the pregame ROI, "
                     "endQ3 win-prob, in-play L5-proxy ceiling, etc.) is printed "
                     "as a live result without retraction framing."),
        mitigation=("honesty_linter scans every user-facing string/key for the "
                    "six banned numbers (retraction-context whitelisted) and the "
                    "banned $-edge claim tokens (never whitelisted)."),
        owning_gate="honesty_linter",
        status="gated",
    ),
    Risk(
        id="dollar_edge_claim",
        description=("A $edge / roi_edge / 'guaranteed profit' field or claim "
                     "appears -- the product is a calibrated predictor, not a "
                     "$ROI product; there is no dollar-edge field by design."),
        mitigation=("honesty_linter banned-token + banned-key check (case-"
                    "insensitive, never retraction-whitelisted)."),
        owning_gate="honesty_linter",
        status="gated",
    ),
    Risk(
        id="percentile_fill_defeats_signals",
        description=("A percentile-filled / imputed / proxy number is presented "
                     "as if it were a real model output, silently defeating the "
                     "signal it stands in for."),
        mitigation=("number_provenance + fill_provenance: a FILLED/UNKNOWN cell "
                    "must carry the FILLED enum and be flagged, else it BLOCKS."),
        owning_gate="provenance",
        status="gated",
    ),
    Risk(
        id="proxy_clv_inflates_eligibility",
        description=("Proxy (non-true-close) CLV inflates the real-money "
                     "eligibility bar, authorizing real money on a soft record."),
        mitigation=("realmoney_gate enforces true_close_frac>=0.90 + bootstrap "
                    "LB>0 + pct_beat_close>=0.55 + >=500 settled, default-DENY, "
                    "human flip + signed token required."),
        owning_gate="realmoney_authorized",
        status="gated",
    ),
    Risk(
        id="concurrent_ledger_writes",
        description=("Two writers append the same bet/row to the CLV ledger, "
                     "corrupting CLV accounting via a duplicate or torn line."),
        mitigation=("concurrency_guard routes every append through the lock-"
                    "guarded clv_ledger_io with an advisory duplicate guard "
                    "(single-process-exact; OS lock serialises cross-process)."),
        owning_gate="concurrency",
        status="monitored",
    ),
    Risk(
        id="train_inference_parity_break",
        description=("A feature wired into training reads 0.0 at inference (or a "
                     "key drifts), a silent permanent Brier regression -- the "
                     "most expensive bug class."),
        mitigation=("parity_check wraps improve.parity_check.parity_ok and BLOCKS "
                    "on any value divergence or silent-zero read."),
        owning_gate="parity",
        status="gated",
    ),
    Risk(
        id="pkl_feature_width_mismatch",
        description=("A promoted pkl's n_features_in_ disagrees with the registry "
                     "meta -- features silently misaligned at inference."),
        mitigation=("pkl_integrity registers model width and BLOCKS promotion of "
                    "any artifact whose pkl/meta n disagrees with the registry."),
        owning_gate="pkl_integrity",
        status="gated",
    ),
    Risk(
        id="leak_or_scale_guard_gap",
        description=("A future-dated feature, a schema/coverage gap, a silent-zero "
                     "required feature, or full-history selection leaks the "
                     "future into a backtest / training build."),
        mitigation=("leak_audit reuses eval_gate validate_golden + assert_vintage "
                    "+ walk_forward; any leak / select_inside=False BLOCKS."),
        owning_gate="leak_audit",
        status="gated",
    ),
    Risk(
        id="secret_leakage",
        description=("The real-money signing secret is committed in code, letting "
                     "anyone forge an authorization token."),
        mitigation=("realmoney_gate reads the HMAC secret only from the "
                    "GOVERNANCE_REALMONEY_SECRET env var; with no secret the gate "
                    "can only DENY (safe default). No secret is ever in code."),
        owning_gate="realmoney_authorized",
        status="gated",
    ),
]

#: Quick lookup by id.
RISK_BY_ID: Dict[str, Risk] = {r.id: r for r in RISKS}


def render() -> Dict[str, Any]:
    """Render the register as a scoreboard dict (machine + human readable).

    Returns::

        {
          "version": RISK_REGISTER_VERSION,
          "n_risks": int,
          "n_gated": int,            # risks guarded by an always-on gate
          "n_monitored": int,        # advisory / documented-limitation guards
          "risks": [ {id, description, mitigation, owning_gate, status}, ... ],
          "by_gate": { owning_gate: [risk_id, ...], ... },
          "text": str,              # ASCII scoreboard for logs / preflight
        }

    Pure: no I/O, no decision, never authorizes a bet.
    """
    rows = [r._asdict() for r in RISKS]
    by_gate: Dict[str, List[str]] = {}
    for r in RISKS:
        by_gate.setdefault(r.owning_gate, []).append(r.id)
    n_gated = sum(1 for r in RISKS if r.status == "gated")
    n_monitored = sum(1 for r in RISKS if r.status == "monitored")
    return {
        "version": RISK_REGISTER_VERSION,
        "n_risks": len(RISKS),
        "n_gated": n_gated,
        "n_monitored": n_monitored,
        "risks": rows,
        "by_gate": by_gate,
        "text": render_text(),
    }


def render_text() -> str:
    """ASCII scoreboard of the register (one line per risk)."""
    lines = ["RISK REGISTER (%s)" % RISK_REGISTER_VERSION,
             "  %d risks -- every mitigation owned by a governance gate" % len(RISKS)]
    width = max((len(r.id) for r in RISKS), default=0)
    for r in RISKS:
        lines.append("  [%-9s] %-*s -> %s" % (r.status, width, r.id, r.owning_gate))
    return "\n".join(lines)


__all__ = [
    "RISK_REGISTER_VERSION",
    "Risk",
    "RISKS",
    "RISK_BY_ID",
    "render",
    "render_text",
]
