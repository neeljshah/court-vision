"""governance.leak_audit -- enforced leak guard over a feature/prediction build.

Milestone-10 turns the leak-free invariant into a TESTED governance gate. It does
not re-implement leak detection; it REUSES the vetted eval-gate machinery:

  * ``scripts.platformkit.eval_gate.schema.validate_golden``  -- the golden-set
    leak + coverage guard (asserts every feature_avail is strictly before the
    prediction-time boundary, plus regime coverage).
  * ``scripts.platformkit.eval_gate.walkforward.assert_vintage`` -- the per-state
    vintage guard (defense in depth: future-dated feature_avail BLOCKS).
  * ``scripts.platformkit.eval_gate.walkforward.walk_forward`` -- the expanding
    window with purge + embargo; its ``select_inside`` flag is surfaced so a
    build that selects on the full history (select_inside=False) is BLOCKED.

A 0.0-read (a feature present in feature_avail / declared as a real feature but
whose value is exactly 0.0 at every state where it should carry signal) is also
a finding: it is the inference-time silent-zero wiring bug seen as DATA, and it
BLOCKS just like a future-dated feature.

DECISION-ONLY: this never authorizes a bet, never moves money, never writes any
artifact, never flips a flag. It returns a verdict dict; the caller (run_governance)
decides. No edge / $ field anywhere.

INVARIANTS: build only under governance/; <=300 LOC; ASCII; no I/O of its own
beyond reading what the caller hands it; stdlib + the eval-gate reuse.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.eval_gate.schema import validate_golden
from scripts.platformkit.eval_gate.walkforward import (
    assert_vintage,
    walk_forward,
)

AUDIT_VERSION = "governance.leak_audit.v1"


def _finding(kind: str, detail: str, game_id: Optional[str] = None) -> Dict[str, Any]:
    """One leak/parity finding. Plain dict so callers need no imports."""
    f: Dict[str, Any] = {"kind": kind, "detail": detail}
    if game_id is not None:
        f["game_id"] = game_id
    return f


def _states_of(build: Any) -> List[dict]:
    """Extract the per-state list from a build object or a plain list.

    Accepts either a list of state dicts, or an object/dict exposing ``states``.
    """
    if isinstance(build, dict) and "states" in build:
        return list(build["states"])
    if hasattr(build, "states"):
        return list(getattr(build, "states"))
    if isinstance(build, (list, tuple)):
        return list(build)
    raise TypeError("leak_audit: build must be a list of states or expose .states")


def _check_vintage(states: Sequence[dict]) -> List[Dict[str, Any]]:
    """Future-dated feature -> finding (per-state vintage guard). BLOCKS."""
    findings: List[Dict[str, Any]] = []
    for s in states:
        try:
            assert_vintage(s)
        except AssertionError as exc:
            findings.append(_finding("future_dated_feature", str(exc),
                                     s.get("game_id")))
        except Exception as exc:  # malformed state still BLOCKS, never false-green
            findings.append(_finding("malformed_state", str(exc)[:200],
                                     s.get("game_id") if isinstance(s, dict) else None))
    return findings


def _check_zero_reads(states: Sequence[dict],
                      required_features: Sequence[str]) -> List[Dict[str, Any]]:
    """A declared real feature that reads exactly 0.0 at EVERY state BLOCKS.

    Mirrors the inference-time silent-zero wiring bug at the DATA level: a feature
    that is supposed to carry signal but is 0.0 everywhere never reached the build.
    A feature that is 0.0 at some states but non-zero at others is fine (real data).
    """
    findings: List[Dict[str, Any]] = []
    for feat in required_features:
        seen_any = False
        nonzero_any = False
        for s in states:
            feats = s.get("features", {}) if isinstance(s, dict) else {}
            if feat in feats:
                seen_any = True
                try:
                    if abs(float(feats[feat])) > 0.0:
                        nonzero_any = True
                        break
                except (TypeError, ValueError):
                    nonzero_any = True  # non-numeric -> not a silent zero
                    break
        if not seen_any:
            findings.append(_finding(
                "missing_required_feature",
                f"required feature {feat!r} absent from every state"))
        elif not nonzero_any:
            findings.append(_finding(
                "zero_read",
                f"required feature {feat!r} reads 0.0 at every state "
                f"(silent-zero wiring bug)"))
    return findings


def _check_select_inside(states: List[dict],
                         predict_fn: Optional[Callable[..., float]],
                         select_inside: bool) -> List[Dict[str, Any]]:
    """Run the leak-free walk_forward; surface select_inside / lookahead leaks.

    The walk_forward harness re-asserts vintage on every test state (defense in
    depth) and records ``select_inside``. A build that tunes / selects features on
    the FULL history (select_inside=False) is a leak and BLOCKS.
    """
    findings: List[Dict[str, Any]] = []
    if select_inside is False:
        findings.append(_finding(
            "select_outside_window",
            "feature selection / tuning ran on the FULL history "
            "(select_inside=False) -- this leaks the future"))
    if predict_fn is None:
        return findings
    try:
        result = walk_forward(states, predict_fn, select_inside=select_inside)
    except AssertionError as exc:
        findings.append(_finding("walkforward_leak", str(exc)[:200]))
        return findings
    except Exception as exc:
        findings.append(_finding("walkforward_error", str(exc)[:200]))
        return findings
    # The harness's own record of select_inside must agree (no silent override).
    if result.select_inside is False and select_inside is not False:
        findings.append(_finding(
            "select_inside_mismatch",
            "walk_forward recorded select_inside=False unexpectedly"))
    return findings


def audit(
    build: Any,
    *,
    required_features: Optional[Sequence[str]] = None,
    predict_fn: Optional[Callable[..., float]] = None,
    select_inside: bool = True,
    validate_schema: bool = True,
) -> Dict[str, Any]:
    """Audit a feature/prediction *build* for leakage. Returns a verdict dict.

    Parameters
    ----------
    build:
        A list of golden-style state dicts, or an object/dict exposing ``states``.
        Each state must carry ``feature_avail`` (feature -> ISO availability date),
        ``state_ts`` (the prediction-time boundary), and (for walk-forward)
        ``home`` / ``away`` / ``outcome`` / ``game_id``.
    required_features:
        Features that MUST carry real signal. Any that read 0.0 at every state, or
        are absent from every state, are reported (zero-read / missing). Optional.
    predict_fn:
        Optional ``predict_fn(train, test, select_inside) -> p in [0,1]`` to drive
        the leak-free walk_forward (vintage re-asserted on every test state).
    select_inside:
        Whether feature selection / tuning happened strictly inside the window.
        ``False`` is itself a leak finding and BLOCKS.
    validate_schema:
        Run the golden-set schema leak + coverage guard first (default True).

    Returns
    -------
    dict with keys:
        ``leak_free`` -- True only if there are zero findings.
        ``findings``  -- list of finding dicts (kind, detail, [game_id]).
        ``n_states``  -- number of states audited.
        ``select_inside`` -- echoed.
        ``version``   -- AUDIT_VERSION.

    Never raises on a leak; a malformed build is itself a (blocking) finding so the
    gate can never go falsely green.
    """
    findings: List[Dict[str, Any]] = []
    try:
        states = _states_of(build)
    except Exception as exc:
        return {
            "leak_free": False,
            "findings": [_finding("bad_build", str(exc)[:200])],
            "n_states": 0,
            "select_inside": select_inside,
            "version": AUDIT_VERSION,
        }

    if validate_schema:
        try:
            validate_golden(states)
        except AssertionError as exc:
            findings.append(_finding("schema_leak_or_coverage", str(exc)[:200]))
        except Exception as exc:
            findings.append(_finding("schema_error", str(exc)[:200]))

    findings.extend(_check_vintage(states))
    if required_features:
        findings.extend(_check_zero_reads(states, required_features))
    findings.extend(_check_select_inside(states, predict_fn, select_inside))

    return {
        "leak_free": len(findings) == 0,
        "findings": findings,
        "n_states": len(states),
        "select_inside": bool(select_inside),
        "version": AUDIT_VERSION,
    }


__all__ = ["audit", "AUDIT_VERSION"]
