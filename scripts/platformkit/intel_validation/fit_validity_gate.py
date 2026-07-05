"""fit_validity_gate -- SKELETON ONLY, guarded, for PROGRAM v3 item 3.

This module is the pre-registered gate that will one day test whether a
composed fit score (player archetype x team scheme x role vacancy, built
from claims already VERIFIED by scripts.platformkit.intel_validation
.claims_validator) predicts realized post-move performance change on the
STRICT historical-moves corpus (n=96, on-disk only) defined in
docs/research/intel-layer/fit_validity_gate_prereg.json.

NO FIT RUNS IN THIS MODULE THIS WAVE. The guard IS the deliverable: calling
run_gate() unconditionally raises FitGateNotAuthorized unless BOTH:
    1. the pre-registration spec's `pre_registered` flag is exactly True, and
    2. the caller passes explicit_run_requested=True.

This mirrors the project's binding invariant that a predictive framing may
never be attempted before its validity gate is pre-registered (see
docs/research/intel-layer/FIT_VALIDITY_GATE_PREREG_2026-07-05.md section 1).
The spec's own `run_permitted` field is a SEPARATE, stronger guard: even with
explicit_run_requested=True, run_gate() also refuses unless run_permitted is
True in the spec file -- so re-authorizing a real run requires editing the
pre-registration itself (a deliberate, reviewable act), not just a call-site
flag flip.

Planted-null scaffolding (shuffle_move_team_assignment, pure_noise_control)
are exposed as documented, spec-describing STUBS -- they raise NotImplementedError
when actually invoked with data, because no gate math ships this wave. Their
docstrings describe the exact design in fit_validity_gate_prereg.json so a
future implementation wave has an unambiguous contract to fill in.

CLI:
    python -m scripts.platformkit.intel_validation.fit_validity_gate --status
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
PREREG_SPEC_PATH = REPO_ROOT / "docs" / "research" / "intel-layer" / "fit_validity_gate_prereg.json"


class FitGateNotAuthorized(RuntimeError):
    """Raised by run_gate() whenever the pre-registration or call-site does
    not explicitly authorize a real run. This exception IS the guard -- it
    is expected to fire on every call this wave, since no fit executes yet."""


@dataclass
class PreRegSpec:
    """Thin, read-only view over fit_validity_gate_prereg.json. Deliberately
    does not parse every nested field -- callers that need the full spec
    should read raw_payload directly. This dataclass only surfaces the
    fields the guard itself needs to decide."""

    pre_registered: bool
    run_permitted: bool
    status: str
    hypothesis_h1: str
    n_moves: int
    decision_current_wave: str
    raw_payload: dict[str, Any]


def load_prereg_spec(path: Path = PREREG_SPEC_PATH) -> PreRegSpec:
    """Load and lightly validate the pre-registration JSON. Fail-closed: any
    missing required field raises KeyError/ValueError rather than defaulting
    to a permissive guess (a missing `pre_registered` key must NEVER be
    silently treated as True)."""
    if not path.exists():
        raise FileNotFoundError(f"pre-registration spec not found: {path}")
    with open(path, "r", encoding="ascii", errors="strict") as f:
        payload = json.load(f)

    for required in ("pre_registered", "run_permitted", "status", "hypothesis", "corpus", "decision_rule"):
        if required not in payload:
            raise ValueError(f"pre-registration spec missing required field: {required!r}")

    pre_registered = payload["pre_registered"]
    run_permitted = payload["run_permitted"]
    if not isinstance(pre_registered, bool) or not isinstance(run_permitted, bool):
        raise ValueError(
            "pre_registered and run_permitted must be JSON booleans, "
            f"got {type(pre_registered)} / {type(run_permitted)}"
        )

    return PreRegSpec(
        pre_registered=pre_registered,
        run_permitted=run_permitted,
        status=str(payload["status"]),
        hypothesis_h1=str(payload["hypothesis"]["H1_candidate"]),
        n_moves=int(payload["corpus"]["verified_counts"]["n_strict_moves_team_changed"]),
        decision_current_wave=str(payload["decision_rule"]["current_wave_verdict"]),
        raw_payload=payload,
    )


def run_gate(explicit_run_requested: bool = False, spec_path: Path = PREREG_SPEC_PATH) -> None:
    """The guard. ALWAYS raises this wave.

    Refuses unless ALL of:
        - the spec's pre_registered flag is True,
        - the spec's run_permitted flag is True (a second, independent gate
          the spec itself controls -- see module docstring), and
        - the caller passes explicit_run_requested=True.

    Even if every condition were met, this skeleton has no fit implementation
    to execute -- a future wave must add the actual H0/H1 fit, the shuffle
    null, and the pure-noise control before this function could do anything
    beyond raise. That is intentional: this wave ships the guard, not the gate.
    """
    spec = load_prereg_spec(spec_path)

    if not explicit_run_requested:
        raise FitGateNotAuthorized(
            "fit_validity_gate.run_gate() refused: explicit_run_requested=False. "
            "Pass explicit_run_requested=True to even attempt authorization."
        )
    if not spec.pre_registered:
        raise FitGateNotAuthorized(
            "fit_validity_gate.run_gate() refused: pre_registered is False in "
            f"{spec_path}. A fit may never run before pre-registration."
        )
    if not spec.run_permitted:
        raise FitGateNotAuthorized(
            "fit_validity_gate.run_gate() refused: run_permitted is False in "
            f"{spec_path}. Per the pre-registration, this stays False until an "
            "accrual-threshold event (second move-cohort, or corpus growth past "
            "the stated floor) is named and the spec is explicitly edited to "
            "authorize a real run -- see decision_rule.not_testable_if and "
            "power_audit.accrual_threshold_that_would_reopen_it in the spec."
        )

    # Unreachable this wave: both guards above fire first (run_permitted is
    # hard-coded False in the committed spec). Left in place so a future
    # wave's authorization edit has an obvious next step to implement.
    raise FitGateNotAuthorized(
        "fit_validity_gate.run_gate() reached the post-guard stage, but no "
        "H0/H1 fit implementation exists yet in this skeleton. Implement the "
        "actual gate (H0 base model, H1 candidate model, planted-null shuffle, "
        "pure-noise control) before removing this final raise."
    )


def shuffle_move_team_assignment(moves: Any, seed: int) -> Any:
    """STUB -- planted-null scaffolding, described but not implemented.

    Per fit_validity_gate_prereg.json's planted_null_design: randomly permute
    which OTHER post-move team (drawn from the same move-cohort's destination
    pool) is assigned to each player when computing the fit score, while
    keeping each player's TRUE realized outcome (bpm_delta) fixed. This
    preserves every marginal distribution (same players, same stat spread,
    same n) while breaking the causal fit-to-outcome link, so any H1-vs-H0
    gain measured under the shuffle is definitionally spurious.

    Raises NotImplementedError -- no gate math ships this wave.
    """
    raise NotImplementedError(
        "shuffle_move_team_assignment is a pre-registration stub. See "
        "fit_validity_gate_prereg.json:planted_null_design for the exact "
        "design this must implement before it is called for real."
    )


def pure_noise_control(fit_scores: Any, seed: int) -> Any:
    """STUB -- synthesis-rail scaffolding, described but not implemented.

    Per fit_validity_gate_prereg.json's synthesis_rail: if any part of the
    fit-score composition requires a constructed/synthetic intermediate,
    this control replaces the fit score with iid random draws matched in
    distribution to the real fit-score, and that control must ALSO fail to
    clear the H1-vs-H0 bar. Catches a degenerate/near-constant fit-score
    family that a shuffle alone would not expose.

    Raises NotImplementedError -- no gate math ships this wave.
    """
    raise NotImplementedError(
        "pure_noise_control is a pre-registration stub. See "
        "fit_validity_gate_prereg.json:synthesis_rail for the exact design "
        "this must implement before it is called for real."
    )


def print_status(spec_path: Path = PREREG_SPEC_PATH) -> None:
    spec = load_prereg_spec(spec_path)
    print("=" * 78)
    print("FIT-VALIDITY GATE -- PRE-REGISTRATION STATUS (PROGRAM v3 item 3)")
    print("=" * 78)
    print(f"spec: {spec_path}")
    print(f"status: {spec.status}")
    print(f"pre_registered: {spec.pre_registered}   run_permitted: {spec.run_permitted}")
    print(f"corpus n_strict_moves: {spec.n_moves}")
    print(f"H1: {spec.hypothesis_h1}")
    print(f"this wave's pre-registered decision: {spec.decision_current_wave}")
    print("-" * 78)
    print("NO FIT RUNS THIS WAVE. run_gate() raises FitGateNotAuthorized unconditionally.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fit-validity gate -- pre-registration guard (no fit runs)")
    parser.add_argument("--status", action="store_true", help="print pre-registration status and exit")
    parser.add_argument(
        "--attempt-run", action="store_true",
        help="attempt to authorize a real run (expected to raise FitGateNotAuthorized this wave)",
    )
    args = parser.parse_args(argv)

    if args.attempt_run:
        try:
            run_gate(explicit_run_requested=True)
        except FitGateNotAuthorized as e:
            print(f"REFUSED (expected): {e}")
            return 0
        print("UNEXPECTED: run_gate() did not raise -- this should never happen this wave.")
        return 1

    print_status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
