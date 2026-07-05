"""fit_validity_gate -- V1 guard (DEFAULT, still refuses) + V2 pass-through
for PROGRAM v3 item 3.

This module's DEFAULT behavior is UNCHANGED from the original skeleton: with
no --spec argument (or an explicit V1 spec_path), run_gate() refuses via the
V1 guard below -- V1's run_permitted stays False forever (frozen,
sha256[:16]=23c53baf5a658f2c), so the DEFAULT path must ALWAYS still refuse.
This is a deliberate regression test, not an oversight: a caller must
EXPLICITLY pass --spec pointing at the V2 amendment to get a real run.

A composed fit score (player archetype x team scheme x role vacancy, built
from claims already VERIFIED by scripts.platformkit.intel_validation
.claims_validator) predicts realized post-move performance change on the
STRICT historical-moves corpus defined in
docs/research/intel-layer/fit_validity_gate_prereg.json (V1, n=96) or its
V2 amendment (docs/research/intel-layer/fit_validity_gate_prereg_v2.json,
n=417 across 5 walk-forward folds, run_permitted=true, authorized under the
recorded Fable decision in that file).

run_gate() unconditionally raises FitGateNotAuthorized for V1 (or any spec
where pre_registered/run_permitted are not both True) unless BOTH:
    1. the pre-registration spec's `pre_registered` flag is exactly True, and
    2. the caller passes explicit_run_requested=True.
AND (a third, separate gate the spec itself controls) the spec's own
`run_permitted` field must also be True -- V1's stays False forever; V2's is
True, so a caller must pass spec_path=V2_SPEC_PATH to get past this guard.
Even when all three conditions are met, THIS module still does not execute
any fit math -- it hands off to
scripts.platformkit.intel_validation.fit_validity_gate_impl.run_gate(), the
real implementation, kept in a separate file so this guard stays the tiny,
trivially auditable surface it always was.

Planted-null STUBS (shuffle_move_team_assignment, pure_noise_control) remain
in THIS file as documented, spec-describing placeholders that raise
NotImplementedError -- the REAL, working null implementations
(shuffle_move_team_assignment, shuffle_outcome_deltas) live in
fit_validity_gate_nulls.py and are used only by fit_validity_gate_impl.py's
V2 run path, never by this guard module directly.

CLI:
    python -m scripts.platformkit.intel_validation.fit_validity_gate --status
    python -m scripts.platformkit.intel_validation.fit_validity_gate --status --spec <path>
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


def _load_guard_fields(path: Path) -> tuple[bool, bool]:
    """Schema-agnostic guard-field read: every spec (V1, V2, or any future
    amendment) MUST carry top-level `pre_registered` / `run_permitted`
    booleans -- this is the ONE contract every spec variant is held to,
    independent of how the rest of that spec's schema is shaped. Used only
    by run_gate()'s authorization check; load_prereg_spec (above) remains
    the STRICT, V1-shaped parser used by print_status/the regression tests
    and is never relaxed."""
    if not path.exists():
        raise FileNotFoundError(f"pre-registration spec not found: {path}")
    with open(path, "r", encoding="ascii", errors="strict") as f:
        payload = json.load(f)
    for required in ("pre_registered", "run_permitted"):
        if required not in payload:
            raise ValueError(f"pre-registration spec missing required field: {required!r}")
    pre_registered, run_permitted = payload["pre_registered"], payload["run_permitted"]
    if not isinstance(pre_registered, bool) or not isinstance(run_permitted, bool):
        raise ValueError(
            "pre_registered and run_permitted must be JSON booleans, "
            f"got {type(pre_registered)} / {type(run_permitted)}"
        )
    return pre_registered, run_permitted


def run_gate(explicit_run_requested: bool = False, spec_path: Path = PREREG_SPEC_PATH) -> None:
    """The guard. Refuses for V1 (or any spec with run_permitted=False)
    unconditionally.

    Refuses unless ALL of:
        - the spec's pre_registered flag is True,
        - the spec's run_permitted flag is True (a second, independent gate
          the spec itself controls -- see module docstring), and
        - the caller passes explicit_run_requested=True.

    THIS module never executes fit math regardless of spec_path -- clearing
    this guard only means the CALLER may now invoke
    fit_validity_gate_impl.run_gate() (the real implementation) directly;
    this function itself has no fit logic to fall through to.
    """
    pre_registered, run_permitted = _load_guard_fields(spec_path)

    if not explicit_run_requested:
        raise FitGateNotAuthorized(
            "fit_validity_gate.run_gate() refused: explicit_run_requested=False. "
            "Pass explicit_run_requested=True to even attempt authorization."
        )
    if not pre_registered:
        raise FitGateNotAuthorized(
            "fit_validity_gate.run_gate() refused: pre_registered is False in "
            f"{spec_path}. A fit may never run before pre-registration."
        )
    if not run_permitted:
        raise FitGateNotAuthorized(
            "fit_validity_gate.run_gate() refused: run_permitted is False in "
            f"{spec_path}. Per the pre-registration, this stays False until an "
            "accrual-threshold event (second move-cohort, or corpus growth past "
            "the stated floor) is named and the spec is explicitly edited to "
            "authorize a real run -- see decision_rule.not_testable_if and "
            "power_audit.accrual_threshold_that_would_reopen_it in the spec."
        )

    # Reached whenever pre_registered/run_permitted/explicit_run_requested
    # are ALL True (e.g. the V2 spec) -- but THIS module (the guard) never
    # executes fit math itself by design, even when authorized. The real
    # implementation is scripts.platformkit.intel_validation
    # .fit_validity_gate_impl.run_gate(), which the caller must invoke
    # separately once this guard clears. For V1 this line is unreachable
    # (run_permitted is hard-coded False there, forever).
    raise FitGateNotAuthorized(
        "fit_validity_gate.run_gate() (the guard module) cleared authorization "
        f"for {spec_path}, but this module never executes fit math itself. "
        "Call scripts.platformkit.intel_validation.fit_validity_gate_impl"
        ".run_gate() directly to run the real V2 implementation."
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
    """V1-shaped status printer (unchanged). load_prereg_spec's PreRegSpec
    dataclass is contracted to V1's exact corpus.verified_counts schema --
    calling this against a differently-shaped spec (e.g. V2, which records
    accrual/power info differently) would raise KeyError, which is the
    correct fail-closed behavior for a schema this function does not know
    how to summarize; use print_generic_spec_summary for any other spec."""
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


def print_generic_spec_summary(spec_path: Path) -> None:
    """Schema-agnostic status printer for any spec (V1 or V2 or future
    amendments) -- reads only the two guard fields every spec must have
    (pre_registered, run_permitted) plus status/doc, without assuming V1's
    exact nested corpus shape."""
    with open(spec_path, "r", encoding="ascii", errors="strict") as f:
        payload = json.load(f)
    print("=" * 78)
    print(f"FIT-VALIDITY GATE -- SPEC STATUS: {payload.get('doc', spec_path.name)}")
    print("=" * 78)
    print(f"spec: {spec_path}")
    print(f"status: {payload.get('status')}")
    print(f"pre_registered: {payload.get('pre_registered')}   run_permitted: {payload.get('run_permitted')}")
    print("-" * 78)
    if payload.get("run_permitted"):
        print("run_permitted=true -- see fit_validity_gate_impl.run_gate() for the real implementation path.")
    else:
        print("run_permitted=false -- run_gate() (this module) refuses unconditionally for this spec.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fit-validity gate -- V1 guard (default) + V2 spec pass-through")
    parser.add_argument("--status", action="store_true", help="print spec status and exit")
    parser.add_argument(
        "--attempt-run", action="store_true",
        help="attempt to authorize a real run against the selected spec (V1 default: expected to raise)",
    )
    parser.add_argument(
        "--spec", type=str, default=None,
        help="path to an alternate spec (e.g. the V2 amendment); DEFAULT stays the frozen V1 spec, which must still refuse",
    )
    args = parser.parse_args(argv)
    spec_path = Path(args.spec) if args.spec else PREREG_SPEC_PATH

    if args.attempt_run:
        try:
            run_gate(explicit_run_requested=True, spec_path=spec_path)
        except FitGateNotAuthorized as e:
            print(f"REFUSED: {e}")
            return 0
        print(f"AUTHORIZED against {spec_path} -- guard cleared (real math lives in fit_validity_gate_impl.py).")
        return 0

    if spec_path == PREREG_SPEC_PATH:
        print_status(spec_path)
    else:
        print_generic_spec_summary(spec_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
