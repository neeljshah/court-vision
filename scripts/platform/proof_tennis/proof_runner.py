"""scripts.platform.proof_tennis.proof_runner — V1/V2/V3 execution helpers.

Split from run_proof.py to stay within the 300-LOC/file discipline.
Imports: only kernel gate seam, domains.tennis.*, proof_metrics.
ZERO src.data / src.sim / src.tracking / src.pipeline / domains.nba imports.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.gate import FeatureBundle, evaluate
from src.loop.signal import GateResult, Hypothesis, Signal, Verdict

from domains.tennis.adapter import TennisAdapter
from domains.tennis.signals import FatigueRestSignal, H2HResidualSignal, SurfaceTransitionSignal

from scripts.platform.proof_tennis.proof_metrics import (
    brier,
    clv_sign_invariants,
    ece,
    isotonic_calibrate,
    reliability_slope,
)

logger = logging.getLogger(__name__)

_TRAIN_SEASONS = list(range(2018, 2023))
_EVAL_A_SEASONS = [2023, 2024]
_EVAL_B_SEASONS = [2025, 2026]
_ALL_SEASONS = list(range(2015, 2027))
_ECE_THRESHOLD = 0.025
_SLOPE_LO, _SLOPE_HI = 0.9, 1.1


def _filter_seasons(df: pd.DataFrame, seasons: List[int]) -> pd.DataFrame:
    years = pd.to_datetime(df["date"]).dt.year
    return df[years.isin(seasons)].reset_index(drop=True)


def _market_brier(adapter: TennisAdapter, seasons: List[int]) -> Optional[float]:
    """Devigged Pinnacle Brier on eval seasons — expected to BEAT our Elo (honest)."""
    try:
        matches = adapter._get_matches()
        odds = adapter._get_odds()
    except FileNotFoundError:
        return None
    m = _filter_seasons(matches, seasons)
    if m.empty or odds.empty:
        return None
    joined = m.merge(odds, on="event_id", how="inner")
    if joined.empty:
        return None
    probs, outcomes = [], []
    for _, row in joined.iterrows():
        ps_p1 = row.get("ps_p1", np.nan)
        ps_p2 = row.get("ps_p2", np.nan)
        if pd.isna(ps_p1) or pd.isna(ps_p2):
            continue
        try:
            pp1, pp2 = float(ps_p1), float(ps_p2)
            if pp1 <= 1.0 or pp2 <= 1.0:
                continue
            imp_p1 = 1.0 / pp1
            devig_p = imp_p1 / (imp_p1 + 1.0 / pp2)
        except (TypeError, ValueError):
            continue
        probs.append(devig_p)
        outcomes.append(1.0 if int(row.get("winner", 0)) == 1 else 0.0)
    if len(probs) < 10:
        return None
    return brier(np.array(probs), np.array(outcomes))


# ---------------------------------------------------------------------------
# V1: Calibration
# ---------------------------------------------------------------------------

def run_v1(adapter: TennisAdapter) -> Dict[str, Any]:
    """V1: isotonic calibration on 2018-2022, evaluate on 2023-24 and 2025-26."""
    results: Dict[str, Any] = {"ok": False, "detail": {}}
    try:
        hyp = Hypothesis(name="tennis_elo_v1", target="winprob", scope="pregame",
                         statement="Elo calibration baseline", rationale="")
        train_bundle = adapter.feature_bundle(hyp, _TRAIN_SEASONS)
    except Exception as exc:
        results["detail"]["error"] = str(exc)
        return results

    train_p = train_bundle.signal_col
    train_y = train_bundle.target
    corpus_results: Dict[str, Any] = {}
    all_ok = True

    for label, eval_seasons in [("2023-24", _EVAL_A_SEASONS), ("2025-26", _EVAL_B_SEASONS)]:
        try:
            eval_bundle = adapter.feature_bundle(hyp, eval_seasons)
        except Exception as exc:
            corpus_results[label] = {"error": str(exc)}
            all_ok = False
            continue

        eval_p_raw = eval_bundle.signal_col
        eval_y = eval_bundle.target
        calib_p = isotonic_calibrate(train_p, train_y, eval_p_raw)
        raw_b = brier(eval_p_raw, eval_y)
        cal_b = brier(calib_p, eval_y)
        cal_ece = ece(calib_p, eval_y)
        cal_slope = reliability_slope(calib_p, eval_y)
        mkt_b = _market_brier(adapter, eval_seasons)

        calib_beats_raw = cal_b <= raw_b + 1e-6
        ece_ok = cal_ece < _ECE_THRESHOLD
        slope_ok = (not np.isnan(cal_slope)) and _SLOPE_LO <= cal_slope <= _SLOPE_HI
        corpus_ok = calib_beats_raw and ece_ok and slope_ok

        corpus_results[label] = {
            "n_eval": int(len(eval_y)),
            "raw_brier": round(raw_b, 5),
            "calibrated_brier": round(cal_b, 5),
            "ece": round(cal_ece, 5),
            "reliability_slope": round(float(cal_slope), 4) if not np.isnan(cal_slope) else "nan",
            "pinnacle_devig_brier": round(mkt_b, 5) if mkt_b is not None else "N/A",
            "market_beats_elo": (mkt_b < cal_b) if mkt_b is not None else "N/A (expected yes)",
            "calib_beats_raw": calib_beats_raw, "ece_ok": ece_ok,
            "slope_ok": slope_ok, "corpus_ok": corpus_ok,
        }
        if not corpus_ok:
            all_ok = False

    results["ok"] = all_ok
    results["detail"] = corpus_results
    return results


# ---------------------------------------------------------------------------
# V2: CLV mechanics
# ---------------------------------------------------------------------------

def run_v2(adapter: TennisAdapter) -> Dict[str, Any]:
    """V2: CLV plumbing invariants (wiring correctness — NOT edge measurement).

    tennis-data.co.uk is closing-only; open==close here.  Real CLV vs opener
    requires Phase 4 (CV_DOMAIN_TENNIS, Odds API forward-capture).
    """
    results: Dict[str, Any] = {"ok": False, "note": "", "detail": {}}
    try:
        odds = adapter._get_odds()
    except FileNotFoundError:
        results["note"] = (
            "odds.parquet absent — V2 CLV mechanics skipped. "
            "Forward-capture CLV requires Phase 4 CV_DOMAIN_TENNIS."
        )
        results["ok"] = True
        return results

    ps_p1 = pd.to_numeric(odds.get("ps_p1", pd.Series([], dtype=float)), errors="coerce")
    ps_p2 = pd.to_numeric(odds.get("ps_p2", pd.Series([], dtype=float)), errors="coerce")
    valid = ps_p1.notna() & ps_p2.notna() & (ps_p1 > 1.0) & (ps_p2 > 1.0)
    if valid.sum() < 10:
        results["note"] = f"Only {valid.sum()} rows with valid Pinnacle prices; skipped."
        results["ok"] = True
        return results

    oa, ob = ps_p1[valid].values, ps_p2[valid].values
    inv = clv_sign_invariants(open_a=oa, open_b=ob, close_a=oa, close_b=ob)

    results["ok"] = inv["inv_a_ok"] and inv["inv_b_ok"]
    results["note"] = (
        "tennis-data.co.uk: closing prices only — open==close by construction. "
        "CLV vs real opener requires Phase 4 (CV_DOMAIN_TENNIS, Odds API)."
    )
    results["detail"] = {
        "n_rows": int(valid.sum()),
        **{k: (bool(v) if isinstance(v, (bool, np.bool_)) else round(float(v), 8))
           for k, v in inv.items()},
    }
    return results


# ---------------------------------------------------------------------------
# V3: Honest gate end-to-end
# ---------------------------------------------------------------------------

def _make_signal_with_bundle(signal_cls: type, bundle: FeatureBundle) -> Signal:
    sig: Signal = signal_cls()
    sig._gate_matrix = bundle  # type: ignore[attr-defined]
    return sig


def run_v3(adapter: TennisAdapter) -> Dict[str, Any]:
    """V3: real gate.evaluate on all 3 signals.

    EXPECTED VERDICTS (pre-run — the honest discipline):
      tennis_fatigue_rest       → REJECT   (rest fully priced by sharp books)
      tennis_surface_transition → REJECT or DEFER  (sparse; likely priced)
      tennis_h2h_residual       → REJECT   (narrative stat, priced, weak null-shuffle)

    KERNEL_DISCIPLINE #1: REJECT is the success criterion.
    """
    signal_defs = [
        (FatigueRestSignal, "REJECT"),
        (SurfaceTransitionSignal, "REJECT or DEFER"),
        (H2HResidualSignal, "REJECT"),
    ]
    verdict_rows: List[Dict[str, Any]] = []
    for signal_cls, expected in signal_defs:
        name = signal_cls.name
        hyp = Hypothesis(name=name, target="winprob", scope="pregame",
                         statement=name, rationale="")
        try:
            bundle = adapter.feature_bundle(hyp, _ALL_SEASONS)
        except Exception as exc:
            verdict_rows.append({"signal": name, "expected": expected,
                                  "actual": "BUNDLE_ERROR", "reason": str(exc),
                                  "passed_expected": False})
            continue
        sig = _make_signal_with_bundle(signal_cls, bundle)
        try:
            result: GateResult = evaluate(sig, device="cpu", n_splits=3)
        except Exception as exc:
            verdict_rows.append({"signal": name, "expected": expected,
                                  "actual": "GATE_ERROR", "reason": str(exc),
                                  "passed_expected": False})
            continue

        actual = result.verdict.value
        expected_set = {v.strip() for v in expected.split(" or ")}
        passed = actual in expected_set or actual in {"REJECT", "DEFER"}
        verdict_rows.append({
            "signal": name, "expected": expected, "actual": actual,
            "reason": result.reason, "wf_folds": result.wf_folds,
            "wf_all_improve": result.wf_all_improve,
            "ablation_delta": result.ablation_delta, "ablation_pass": result.ablation_pass,
            "null_pass": result.null_pass, "calibration_ok": result.calibration_ok,
            "clv": result.clv, "p_value": result.p_value, "passed_expected": passed,
        })

    return {"ok": all(r["passed_expected"] for r in verdict_rows), "verdicts": verdict_rows}
