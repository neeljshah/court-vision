"""scripts.platformkit.proof_common.runner — sport-blind V1 / V2 / V3 proof harness.

Parameterised entirely by a :class:`~scripts.platformkit.proof_common.spec.ProofSpec`
and a sport-specific adapter; contains ZERO sport tokens and ZERO sport-conditionals.

This is a behaviour-preserving consolidation of the three per-sport proof_runner.py
files (tennis / soccer / mlb).  Every loop order, every expression, and every
rounding call is kept verbatim from the originals so that K-PR-005 can confirm
bitwise-identical outputs on real corpora before the shim swap (K-PR-006).

Thresholds are frozen module constants (NOT ProofSpec fields): freezing them is the
discipline — a spec-level threshold would invite per-sport tuning.

Platform-harness promotion; placement: scripts/ layer.
Placement rationale: this file necessarily imports src.loop.gate / src.loop.signal /
src.prediction.{betting_portfolio,bet_grades}, which are KERNEL_IMPORT_VIOLATIONs if
placed inside kernel/.  It therefore lives here, held to kernel DISCIPLINE
(zero sport tokens, equivalence-gated swap) without violating kernel PURITY.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.gate import FeatureBundle, evaluate
from src.loop.signal import GateResult, Hypothesis, Signal, Verdict
from kernel.validation.proof_metrics import (
    brier,
    clv_sign_invariants,
    devig2,
    ece,
    isotonic_calibrate,
    reliability_slope,
)
from scripts.platformkit.proof_common.spec import EvalWindow, ProofSpec

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Frozen thresholds — identical across all sports; NOT spec fields.
# ---------------------------------------------------------------------------
_ECE_THRESHOLD = 0.025
_SLOPE_LO, _SLOPE_HI = 0.9, 1.1


# ---------------------------------------------------------------------------
# Shared helpers — transplanted verbatim from the originals (all three match).
# ---------------------------------------------------------------------------

def _filter_seasons(df: pd.DataFrame, seasons: List[int]) -> pd.DataFrame:
    """Return rows whose date-year falls in *seasons*.  Verbatim from all three originals."""
    years = pd.to_datetime(df["date"]).dt.year
    return df[years.isin(seasons)].reset_index(drop=True)


def _make_signal_with_bundle(signal_cls: type, bundle: FeatureBundle) -> Signal:
    """Attach a pre-built FeatureBundle to a Signal instance.  Verbatim from all three originals."""
    sig: Signal = signal_cls()
    sig._gate_matrix = bundle  # type: ignore[attr-defined]
    return sig


# ---------------------------------------------------------------------------
# Generic _market_brier
# ---------------------------------------------------------------------------

def _market_brier(
    spec: ProofSpec,
    adapter: Any,
    seasons: List[int],
    ctx: Optional[str] = None,
) -> Optional[float]:
    """Compute devigged market Brier for one eval window.

    Uses ``spec.load_market_frame`` to obtain the joined matches⊕odds frame
    (sport-specific corpus join happens inside the leaf callable).  Returns None
    when data are absent, the frame is empty, or fewer than 10 valid rows remain
    after the per-row > 1.0 guard.

    The devig call uses ``devig2`` from kernel.validation.proof_metrics, which is
    bitwise-identical to tennis's inline ``(1/pp1)/(1/pp1+1/pp2)`` (IEEE division
    is deterministic; §1 verification).  The > 1.0 pre-filter stays in the per-row
    loop, matching all three originals.
    """
    joined = spec.load_market_frame(adapter, seasons, ctx)
    if joined is None or joined.empty:
        return None
    probs: List[float] = []
    outcomes: List[float] = []
    for _, row in joined.iterrows():
        try:
            pa = float(row[spec.close_a_col])
            pb = float(row[spec.close_b_col])
            if pa <= 1.0 or pb <= 1.0:
                continue
            p_a, _ = devig2(pa, pb)
            tgt = spec.outcome_market(row)
            if tgt is None:
                continue
            probs.append(p_a)
            outcomes.append(tgt)
        except (TypeError, ValueError, KeyError):
            continue
    return brier(np.array(probs), np.array(outcomes)) if len(probs) >= 10 else None


# ---------------------------------------------------------------------------
# V1 — Calibration
# ---------------------------------------------------------------------------

def run_v1(spec: ProofSpec, adapter: Any, ctx: Optional[str] = None) -> Dict[str, Any]:
    """V1: isotonic calibration on train seasons; evaluate on each EvalWindow.

    Behaviour-preserving generic: every expression matches the originals verbatim.
    Result-dict key names for the market Brier entry come from the spec so that
    tennis outputs ``pinnacle_devig_brier`` / ``market_beats_elo`` and
    soccer / mlb output ``market_devig_brier`` / ``market_beats_model``.
    ``regime_note`` is emitted only when ``window.regime_note is not None``
    (matches MLB emitting for every window; tennis / soccer emitting for none).
    """
    results: Dict[str, Any] = {"ok": False, "detail": {}}
    try:
        hyp = Hypothesis(
            name=spec.hyp_v1_name,
            target="winprob",
            scope="pregame",
            statement=spec.hyp_v1_statement,
            rationale="",
        )
        train_bundle = adapter.feature_bundle(
            hyp, spec.train_seasons, **spec.bundle_kwargs(ctx)
        )
    except Exception as exc:
        results["detail"]["error"] = str(exc)
        return results

    train_p, train_y = train_bundle.signal_col, train_bundle.target
    corpus_results: Dict[str, Any] = {}
    all_ok = True

    window: EvalWindow
    for window in spec.eval_windows:
        label = window.label
        eval_seasons = window.seasons
        try:
            eval_bundle = adapter.feature_bundle(
                hyp, eval_seasons, **spec.bundle_kwargs(ctx)
            )
        except Exception as exc:
            corpus_results[label] = {"error": str(exc)}
            all_ok = False
            continue

        eval_p_raw, eval_y = eval_bundle.signal_col, eval_bundle.target
        calib_p = isotonic_calibrate(train_p, train_y, eval_p_raw)
        raw_b = brier(eval_p_raw, eval_y)
        cal_b = brier(calib_p, eval_y)
        cal_ece = ece(calib_p, eval_y)
        cal_slope = reliability_slope(calib_p, eval_y)
        mkt_b = _market_brier(spec, adapter, eval_seasons, ctx)

        calib_beats_raw = cal_b <= raw_b + 1e-6
        ece_ok = cal_ece < _ECE_THRESHOLD
        slope_ok = (not np.isnan(cal_slope)) and _SLOPE_LO <= cal_slope <= _SLOPE_HI
        corpus_ok = calib_beats_raw and ece_ok and slope_ok

        row: Dict[str, Any] = {
            "n_eval": int(len(eval_y)),
            "raw_brier": round(raw_b, 5),
            "calibrated_brier": round(cal_b, 5),
            "ece": round(cal_ece, 5),
            "reliability_slope": round(float(cal_slope), 4) if not np.isnan(cal_slope) else "nan",
            spec.market_brier_key: round(mkt_b, 5) if mkt_b is not None else "N/A",
            spec.market_beats_key: (mkt_b < cal_b) if mkt_b is not None else "N/A (expected yes)",
            "calib_beats_raw": calib_beats_raw,
            "ece_ok": ece_ok,
            "slope_ok": slope_ok,
            "corpus_ok": corpus_ok,
        }
        # Emit regime_note only when the spec declares one (None → key absent).
        if window.regime_note is not None:
            row["regime_note"] = window.regime_note

        corpus_results[label] = row
        if not corpus_ok:
            all_ok = False

    results["ok"] = all_ok
    results["detail"] = corpus_results
    return results


# ---------------------------------------------------------------------------
# V2 — CLV mechanics (wiring correctness)
# ---------------------------------------------------------------------------

def run_v2(spec: ProofSpec, adapter: Any, ctx: Optional[str] = None) -> Dict[str, Any]:
    """V2: CLV plumbing invariants.  Wiring correctness only — zero edge meaning.

    When ``spec.open_a_col is None`` (tennis), open prices are set equal to close
    prices, producing a 2-column validity mask (bitwise-identical to tennis's
    ``open==close by construction`` path).  Otherwise a 4-column mask is applied
    (soccer / mlb).

    ``spec.filter_v2_odds`` handles any per-sport pre-filter (e.g. MLB league
    filtering); the identity callable is used for tennis / soccer.
    """
    results: Dict[str, Any] = {"ok": False, "note": "", "detail": {}}
    try:
        odds = adapter._get_odds()
    except FileNotFoundError:
        results["note"] = spec.v2_absent_note
        results["ok"] = True
        return results

    # Apply per-sport pre-filter (identity for tennis/soccer; league-filter for mlb).
    odds = spec.filter_v2_odds(adapter, odds, ctx)

    if spec.open_a_col is None:
        # Tennis: open == close by construction — 2-col validity mask.
        ca = pd.to_numeric(odds.get(spec.close_a_col, pd.Series([], dtype=float)), errors="coerce")
        cb = pd.to_numeric(odds.get(spec.close_b_col, pd.Series([], dtype=float)), errors="coerce")
        valid = ca.notna() & cb.notna() & (ca > 1.0) & (cb > 1.0)
        if valid.sum() < 10:
            results["note"] = spec.v2_skip_note_fmt.format(n=valid.sum())
            results["ok"] = True
            return results
        oa, ob = ca[valid].values, cb[valid].values
        inv = clv_sign_invariants(open_a=oa, open_b=ob, close_a=oa, close_b=ob)
    else:
        # Soccer / mlb: 4-col validity mask.
        oa_s = pd.to_numeric(odds.get(spec.open_a_col, pd.Series([], dtype=float)), errors="coerce")
        ob_s = pd.to_numeric(odds.get(spec.open_b_col, pd.Series([], dtype=float)), errors="coerce")
        ca_s = pd.to_numeric(odds.get(spec.close_a_col, pd.Series([], dtype=float)), errors="coerce")
        cb_s = pd.to_numeric(odds.get(spec.close_b_col, pd.Series([], dtype=float)), errors="coerce")
        valid = (
            oa_s.notna() & ob_s.notna() & ca_s.notna() & cb_s.notna()
            & (oa_s > 1.0) & (ob_s > 1.0) & (ca_s > 1.0) & (cb_s > 1.0)
        )
        if valid.sum() < 10:
            results["note"] = spec.v2_skip_note_fmt.format(n=valid.sum())
            results["ok"] = True
            return results
        oa = oa_s[valid].values
        ob = ob_s[valid].values
        ca = ca_s[valid].values
        cb = cb_s[valid].values
        inv = clv_sign_invariants(open_a=oa, open_b=ob, close_a=ca, close_b=cb)

    results["ok"] = bool(inv["inv_a_ok"]) and bool(inv["inv_b_ok"])
    results["note"] = spec.v2_note
    results["detail"] = {
        "n_rows": int(valid.sum()),
        **{k: (bool(v) if isinstance(v, (bool, np.bool_)) else round(float(v), 8))
           for k, v in inv.items()},
    }
    return results


# ---------------------------------------------------------------------------
# V3 — Honest gate end-to-end
# ---------------------------------------------------------------------------

def run_v3(spec: ProofSpec, adapter: Any, ctx: Optional[str] = None) -> Dict[str, Any]:
    """V3: run gate.evaluate on each signal in spec.signal_defs.

    Expected: all REJECT (DEFER acceptable).  The passed-rule is:
        actual in expected_set  OR  actual in {"REJECT", "DEFER"}
    This is the tennis/soccer form; MLB's simpler ``actual in {"REJECT","DEFER"}``
    is logically identical since every MLB expected_set ⊆ {REJECT, DEFER-variants}
    (§4.2 verification).
    """
    verdict_rows: List[Dict[str, Any]] = []
    for signal_cls, expected in spec.signal_defs:
        name = signal_cls.name
        hyp = Hypothesis(
            name=name,
            target="winprob",
            scope="pregame",
            statement=name,
            rationale="",
        )
        try:
            bundle = adapter.feature_bundle(
                hyp, spec.all_seasons, **spec.bundle_kwargs(ctx)
            )
        except Exception as exc:
            verdict_rows.append({
                "signal": name,
                "expected": expected,
                "actual": "BUNDLE_ERROR",
                "reason": str(exc),
                "passed_expected": False,
            })
            continue

        sig = _make_signal_with_bundle(signal_cls, bundle)
        try:
            result: GateResult = evaluate(sig, device="cpu", n_splits=3)
        except Exception as exc:
            verdict_rows.append({
                "signal": name,
                "expected": expected,
                "actual": "GATE_ERROR",
                "reason": str(exc),
                "passed_expected": False,
            })
            continue

        actual = result.verdict.value
        expected_set = {v.strip() for v in expected.split(" or ")}
        passed = actual in expected_set or actual in {"REJECT", "DEFER"}
        verdict_rows.append({
            "signal": name,
            "expected": expected,
            "actual": actual,
            "reason": result.reason,
            "wf_folds": result.wf_folds,
            "wf_all_improve": result.wf_all_improve,
            "ablation_delta": result.ablation_delta,
            "ablation_pass": result.ablation_pass,
            "null_pass": result.null_pass,
            "calibration_ok": result.calibration_ok,
            "clv": result.clv,
            "p_value": result.p_value,
            "passed_expected": passed,
        })

    return {"ok": all(r["passed_expected"] for r in verdict_rows), "verdicts": verdict_rows}
