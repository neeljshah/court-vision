"""clv_gate.py -- R9 C8 CLV-positive ship gate.

Composed with the existing MAE gate (never replaces it). A probe declares
its `change_type` as one of three buckets and supplies `clv_metrics` from
a backtest replay; this module returns (passed, reason) which the scaffold
ANDs with the MAE verdict.

Change buckets
--------------
- ``model`` / ``feature`` : MAE gate REQUIRED. CLV gate also REQUIRED:
  ``beat_rate >= 0.52`` AND ``mean_clv_percent >= 0.0`` AND ``n_bets >= 200``.
  (Justification: 52% is the lower 95% CI bound for a true 53% strategy at
  n=200; +0% / non-negative mean CLV ensures we don't ship a feature that
  worsens line capture even when raw MAE wins.)

- ``sizing_timing`` : Kelly fraction / edge-threshold / placement-timing
  tweaks where treatment MAE === baseline. MAE gate BYPASSED. CLV gate
  REQUIRED at the stricter bar: ``mean_clv_percent >= 0.01`` (+1%/bet)
  AND 4/4 WF CLV folds positive AND ``n_bets >= 200``.

Backward compat
---------------
If ``probe_results.get("clv_metrics")`` is None or empty AND `change_type`
defaults to ``model``, the gate returns ``(True, "CLV unavailable -- legacy probe")``
so R0-R8 historical replays still pass through untouched. New probes that
explicitly declare a change_type but ship empty metrics fail closed with an
explicit reason -- preventing silent ship-gate skips on R9+ work.
"""
from __future__ import annotations

from typing import List, Tuple

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Gate thresholds (justified in module docstring).
MIN_BETS = 200
BEAT_RATE_FLOOR = 0.52
SIZING_CLV_FLOOR = 0.01  # +1% mean CLV per bet for sizing/timing changes

_KNOWN_CHANGE_TYPES = ("model", "feature", "sizing_timing")


def _wf_folds_positive(folds) -> bool:
    """Return True iff every WF fold has mean_clv_percent > 0.

    Accepts either a list of floats or a list of dicts with a
    ``mean_clv_percent`` (or ``mean_pct``) key. Empty list returns False.
    """
    if not folds:
        return False
    n_pos = 0
    n_total = 0
    for f in folds:
        if isinstance(f, dict):
            v = f.get("mean_clv_percent", f.get("mean_pct"))
        else:
            v = f
        try:
            fv = float(v)
        except (TypeError, ValueError):
            return False
        n_total += 1
        if fv > 0:
            n_pos += 1
    return n_total >= 1 and n_pos == n_total


def _is_legacy(probe_results: dict) -> bool:
    """A probe is 'legacy' (pre-R9 / no CLV instrumentation) if it lacks the
    `clv_metrics` block entirely or its block is None / empty dict."""
    if not isinstance(probe_results, dict):
        return True
    cm = probe_results.get("clv_metrics")
    if cm is None:
        return True
    if isinstance(cm, dict) and len(cm) == 0:
        return True
    return False


def _metric(cm: dict, *names, default=None):
    """Read first present key from cm matching one of names."""
    for k in names:
        if k in cm and cm[k] is not None:
            return cm[k]
    return default


def check_clv_gate(probe_results: dict, change_type: str = "model") -> Tuple[bool, str]:
    """Adjudicate the CLV gate for a probe.

    Args
    ----
    probe_results : dict
        The probe's result dict. Expected to optionally carry a
        ``clv_metrics`` sub-dict with keys ``beat_rate``, ``mean_pct``
        (or ``mean_clv_percent``), ``n`` (or ``n_bets``), ``wf``
        (or ``wf_folds``).
    change_type : str
        One of ``"model"``, ``"feature"``, ``"sizing_timing"``. Defaults to
        ``"model"`` for backward compatibility with R0-R8 callers.

    Returns
    -------
    (passed, reason) : tuple[bool, str]
    """
    if change_type not in _KNOWN_CHANGE_TYPES:
        return False, f"unknown change_type {change_type!r}"

    # Legacy / pre-R9 passthrough: only when caller didn't provide CLV data
    # AND didn't explicitly tag a non-model change_type that REQUIRES CLV.
    if _is_legacy(probe_results):
        if change_type == "sizing_timing":
            # sizing/timing probes have no MAE signal -- empty CLV is fatal.
            return False, "CLV unavailable for sizing_timing change (no MAE fallback)"
        # model/feature legacy probes (R0-R8) fall through to MAE adjudication.
        return True, "CLV unavailable -- legacy probe"

    cm = probe_results.get("clv_metrics") or {}
    beat_rate = _metric(cm, "beat_rate", "beat_close_rate")
    mean_pct = _metric(cm, "mean_pct", "mean_clv_percent")
    n_bets = _metric(cm, "n_bets", "n")
    wf_folds = _metric(cm, "wf_folds", "wf", default=[])

    # Coerce.
    try:
        n_bets = int(n_bets) if n_bets is not None else 0
    except (TypeError, ValueError):
        n_bets = 0
    try:
        beat_rate = float(beat_rate) if beat_rate is not None else None
    except (TypeError, ValueError):
        beat_rate = None
    try:
        mean_pct = float(mean_pct) if mean_pct is not None else None
    except (TypeError, ValueError):
        mean_pct = None

    if n_bets < MIN_BETS:
        return False, f"n={n_bets} < {MIN_BETS} bets (insufficient sample)"

    if change_type in ("model", "feature"):
        if beat_rate is None:
            return False, "CLV beat_rate missing"
        if mean_pct is None:
            return False, "CLV mean_clv_percent missing"
        if beat_rate < BEAT_RATE_FLOOR:
            return False, f"beat_rate {beat_rate:.4f} < {BEAT_RATE_FLOOR}"
        if mean_pct < 0.0:
            return False, f"mean_clv_percent {mean_pct:+.4f} < 0.0"
        return True, (f"CLV ok: beat_rate={beat_rate:.4f} "
                       f"mean_pct={mean_pct:+.4f} n={n_bets}")

    # sizing_timing: stricter mean_pct + 4/4 WF requirement.
    if mean_pct is None:
        return False, "CLV mean_clv_percent missing for sizing_timing"
    if mean_pct < SIZING_CLV_FLOOR:
        return False, (f"mean_clv_percent {mean_pct:+.4f} < "
                       f"{SIZING_CLV_FLOOR:+.4f} (sizing/timing bar)")
    if not _wf_folds_positive(wf_folds):
        n_pos = sum(1 for f in wf_folds if (
            float(f.get("mean_clv_percent", f.get("mean_pct", 0)))
            if isinstance(f, dict) else float(f)) > 0)
        return False, f"WF {n_pos}/{len(wf_folds)} folds positive (need 4/4)"
    return True, (f"sizing/timing CLV ok: mean_pct={mean_pct:+.4f} "
                   f"WF 4/4 n={n_bets}")


def compose_with_mae(
    mae_passed: bool,
    mae_reason: str,
    clv_passed: bool,
    clv_reason: str,
    change_type: str = "model",
) -> Tuple[bool, str]:
    """Compose MAE + CLV verdicts per change_type.

    - model / feature : ship iff (mae_passed AND clv_passed)
    - sizing_timing  : ship iff clv_passed (MAE bypassed -- treatment is MAE-equal)

    Returns (ship, composed_reason).
    """
    if change_type == "sizing_timing":
        if clv_passed:
            return True, f"sizing_timing SHIP: {clv_reason}"
        return False, f"sizing_timing REJECT: {clv_reason}"

    # model / feature: AND-composition.
    if mae_passed and clv_passed:
        return True, f"MAE+CLV SHIP: MAE={mae_reason}; CLV={clv_reason}"

    causes: List[str] = []
    if not mae_passed:
        causes.append(f"MAE fail: {mae_reason}")
    if not clv_passed:
        causes.append(f"CLV fail: {clv_reason}")
    return False, "; ".join(causes)
