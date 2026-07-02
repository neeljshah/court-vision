"""scripts.platformkit.econ.greenlight_criteria -- the seven 8.1 criterion
evaluators + date-parity halving, factored out of edge_greenlight.py to keep
both files under the 300 LOC cap. Pure functions; no I/O beyond one read of
the segment-trust JSON artifact and one in-process offline eval-gate run
(cached). Never raises -- a criterion that cannot be computed reports its own
honest failure detail rather than crashing the nightly report.

See edge_greenlight.py's module docstring for the full criteria (a)-(g) text
and the two documented NOT_BUILT gaps (channel-trust 4.1, cv-honesty-gate).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit.clv.clv_scoreboard import _is_measurable, _mean_ci, _wlp_units
from scripts.platformkit.econ.cost_model import breakeven_edge_prob
from scripts.platformkit.econ.after_cost_scoreboard import after_cost_units
from scripts.platformkit.econ.beat_the_line import _win_rate_excess

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
_TRUST_JSON = os.path.join(_REPO, "data", "frontend", "ops", "ingame_segment_trust.json")

_N_TOTAL_MIN = 300
_N_HALF_MIN = 150

# Observed-evidence-only venue fallback (every paper_pm row seen to date is
# venue=kalshi) -- never guessed for a channel with no venue evidence.
_CHANNEL_DEFAULT_VENUE = {"paper_pm": "kalshi"}


def _row_date(row: Dict[str, Any]) -> str:
    gd = str(row.get("game_date") or "").strip()
    if gd:
        return gd[:10]
    return str(row.get("ts") or row.get("settled_at") or "")[:10]


def halves(rows: Sequence[Dict[str, Any]]) -> Sequence[Sequence[Dict[str, Any]]]:
    """Two INDEPENDENT date-parity halves (even/odd day-of-month) -- a cheap,
    deterministic, leak-free split with no hand-chosen fold boundary.
    """
    half_a: List[Dict[str, Any]] = []
    half_b: List[Dict[str, Any]] = []
    for r in rows:
        d = _row_date(r)
        day_num = int(d[8:10]) if len(d) >= 10 and d[8:10].isdigit() else None
        (half_a if (day_num is not None and day_num % 2 == 0) else half_b).append(r)
    return half_a, half_b


def criterion_a(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    a, b = halves(rows)
    na, nb = len(a), len(b)
    passed = (n >= _N_TOTAL_MIN) and (na >= _N_HALF_MIN) and (nb >= _N_HALF_MIN)
    shortfall = []
    if n < _N_TOTAL_MIN:
        shortfall.append("need %d more total (have %d, need %d)"
                          % (_N_TOTAL_MIN - n, n, _N_TOTAL_MIN))
    if na < _N_HALF_MIN:
        shortfall.append("need %d more in half A (have %d, need %d)"
                          % (_N_HALF_MIN - na, na, _N_HALF_MIN))
    if nb < _N_HALF_MIN:
        shortfall.append("need %d more in half B (have %d, need %d)"
                          % (_N_HALF_MIN - nb, nb, _N_HALF_MIN))
    return {"id": "a", "passed": passed, "n_total": n, "n_half_a": na, "n_half_b": nb,
            "detail": "n>=300 (>=150/half)" if passed else "; ".join(shortfall)}


def criterion_b(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    a, b = halves(rows)
    ua = _wlp_units(a)["net_units"]
    ub = _wlp_units(b)["net_units"]
    passed = (ua > 0.0) and (ub > 0.0)
    return {"id": "b", "passed": passed, "units_half_a": ua, "units_half_b": ub,
            "detail": ("net units > 0 both halves" if passed else
                       "half A units=%.2f, half B units=%.2f (need both > 0)" % (ua, ub))}


def _cost_hurdle_pct(rows: Sequence[Dict[str, Any]]) -> Optional[float]:
    """Mean breakeven_edge_prob (as a %-of-price hurdle, comparable to clv_pct)
    across a row set. None if no row is costable -- never fabricates a hurdle.
    """
    from scripts.platformkit.clv.clv_scoreboard import _channel_of
    hurdles = []
    for r in rows:
        venue = str(r.get("venue") or _CHANNEL_DEFAULT_VENUE.get(_channel_of(r)) or "").lower()
        if not venue:
            continue
        try:
            dec = float(r.get("taken_decimal"))
        except (TypeError, ValueError):
            continue
        if dec <= 1.0:
            continue
        price = 1.0 / dec
        be = breakeven_edge_prob(venue, price, side="taker")
        if be is None:
            continue
        hurdles.append(be / price * 100.0)
    return (sum(hurdles) / len(hurdles)) if hurdles else None


def criterion_c(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    meas = [r for r in rows if _is_measurable(r)]
    a, b = halves(meas)
    results: Dict[str, Any] = {}
    ok = True
    for label, half in (("half_a", a), ("half_b", b)):
        clvs = [float(r["clv_pct"]) for r in half if r.get("clv_pct") is not None]
        ci = _mean_ci(clvs)
        hurdle = _cost_hurdle_pct(half)
        half_pass = (ci["significant"] and hurdle is not None
                     and ci["mean"] is not None and ci["mean"] > hurdle)
        ok = ok and half_pass
        results[label] = {"n": ci["n"], "mean_clv_pct": ci["mean"],
                           "ci95": [ci["lo95"], ci["hi95"]],
                           "cost_hurdle_pct": (round(hurdle, 4) if hurdle is not None else None),
                           "passed": half_pass}
    detail = ("mean CLV > cost hurdle, CI excl 0, both halves" if ok else
              "one or both halves fail: CLV must exceed the fee hurdle with CI "
              "excluding 0 (see half_a/half_b)")
    return {"id": "c", "passed": ok, **results, "detail": detail}


def criterion_d(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    meas = [r for r in rows if _is_measurable(r)]
    a, b = halves(meas)
    vals: Dict[str, Any] = {}
    ok = True
    for label, half in (("half_a", a), ("half_b", b)):
        total = 0.0
        n_costed = 0
        for r in half:
            rec = after_cost_units(r)
            if rec is None:
                continue
            n_costed += 1
            total += rec["after_cost_units"]
        half_pass = (n_costed > 0) and (total > 0.0)
        ok = ok and half_pass
        vals[label] = {"n_costed": n_costed, "after_cost_units": round(total, 3),
                        "passed": half_pass}
    detail = ("after-cost units > 0 both halves" if ok else
              "one or both halves not after-cost positive (see half_a/half_b)")
    return {"id": "d", "passed": ok, **vals, "detail": detail}


def criterion_e(channel: str) -> Dict[str, Any]:
    segment_status = "NOT_BUILT"
    trusted_segments: List[str] = []
    try:
        if os.path.exists(_TRUST_JSON):
            with open(_TRUST_JSON, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            trusted_segments = list(doc.get("trusted") or [])
            segment_status = "TRUSTED" if trusted_segments else "NO_TRUSTED_SEGMENTS"
    except (OSError, json.JSONDecodeError):
        segment_status = "READ_ERROR"
    # Channel-level trust (4.1) -- NOT BUILT anywhere in this repo as of this
    # pass. Reported honestly rather than defaulted to pass.
    channel_trust_status = "NOT_BUILT"
    passed = (segment_status == "TRUSTED") and (channel_trust_status == "TRUSTED")
    return {
        "id": "e", "passed": passed,
        "segment_trust_status": segment_status,
        "trusted_segments": trusted_segments,
        "channel_trust_status": channel_trust_status,
        "detail": ("segments TRUSTED (m26) AND channel TRUSTED (4.1) both required; "
                   "channel-trust gate (4.1) is NOT_BUILT in this repo -- criterion "
                   "cannot pass until it exists. segment status=%s" % segment_status),
    }


_EVAL_GATE_CACHE: Dict[str, Any] = {}


def criterion_f() -> Dict[str, Any]:
    if "result" not in _EVAL_GATE_CACHE:
        try:
            from scripts.platformkit.eval_gate.run_gate import (
                run_gate_in_process, gate_exit_code, offline_predict_fn)
            rows = run_gate_in_process(offline_predict_fn, golden_path=None, corpus_dir=None)
            code = gate_exit_code(rows)
            _EVAL_GATE_CACHE["result"] = {"status": "GREEN" if code == 0 else "RED",
                                           "exit_code": code}
        except Exception as exc:  # noqa: BLE001
            _EVAL_GATE_CACHE["result"] = {"status": "UNKNOWN",
                                           "error": "%s: %s" % (type(exc).__name__, exc)}
    eval_gate_result = _EVAL_GATE_CACHE["result"]
    eval_gate_green = eval_gate_result.get("status") == "GREEN"
    # cv-honesty-gate: NOT BUILT anywhere in this repo. governance/honesty_linter.py
    # is a DIFFERENT thing (scans output strings for banned $-edge claims/numbers,
    # never adjudicates whether a proof-of-edge claim is refuted).
    cv_honesty_status = "NOT_BUILT"
    passed = eval_gate_green and (cv_honesty_status == "NOT_REFUTED")
    return {
        "id": "f", "passed": passed,
        "eval_gate_offline_golden": eval_gate_result,
        "cv_honesty_gate_status": cv_honesty_status,
        "detail": ("eval-gate green AND cv-honesty-gate NOT-REFUTED both required; "
                   "cv-honesty-gate is NOT_BUILT in this repo (governance/"
                   "honesty_linter.py is a banned-claim STRING scanner, not a claim "
                   "adjudicator) -- criterion cannot pass until it exists. "
                   "eval_gate(offline golden)=%s" % eval_gate_result.get("status")),
    }


def criterion_g(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    meas = [r for r in rows if _is_measurable(r)]
    wr = _win_rate_excess(meas)
    passed = bool(wr.get("excess_significant"))
    return {"id": "g", "passed": passed, "n": wr["n"],
            "excess": wr.get("excess"), "excess_ci95": wr.get("excess_ci95"),
            "detail": wr.get("verdict")}


__all__ = ["halves", "criterion_a", "criterion_b", "criterion_c", "criterion_d",
           "criterion_e", "criterion_f", "criterion_g"]
