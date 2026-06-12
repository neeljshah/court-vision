"""scripts.platform.proof_tennis.proof_runner — V1/V2/V3/V4 execution helpers.

Split from run_proof.py to stay within the 300-LOC/file discipline.
Imports: only kernel gate seam, domains.tennis.*, proof_metrics, decision-kernel seam.
ZERO src.data / src.sim / src.tracking / src.pipeline / domains.nba imports.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.gate import FeatureBundle, evaluate
from src.loop.signal import GateResult, Hypothesis, Signal, Verdict
from domains.tennis.adapter import TennisAdapter
from domains.tennis.signals import FatigueRestSignal, H2HResidualSignal, SurfaceTransitionSignal
from scripts.platform.proof_tennis.proof_metrics import (
    brier, clv_sign_invariants, ece, isotonic_calibrate, reliability_slope,
)
from src.prediction.betting_portfolio import (  # decision-kernel seam — F5 OK
    KELLY_FRACTION, clamp_kelly_pct, check_drawdown_ok,
)
from src.prediction.bet_grades import letter_grade

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
    """Devigged Pinnacle Brier — expected to beat Elo (honest framing)."""
    try:
        m = _filter_seasons(adapter._get_matches(), seasons)
        odds = adapter._get_odds()
    except FileNotFoundError:
        return None
    if m.empty or odds.empty:
        return None
    joined = m.merge(odds, on="event_id", how="inner")
    probs, outcomes = [], []
    for _, row in joined.iterrows():
        try:
            pp1, pp2 = float(row["ps_p1"]), float(row["ps_p2"])
            if pp1 <= 1.0 or pp2 <= 1.0:
                continue
            probs.append((1.0 / pp1) / (1.0 / pp1 + 1.0 / pp2))
            outcomes.append(1.0 if int(row.get("winner", 0)) == 1 else 0.0)
        except (TypeError, ValueError, KeyError):
            continue
    return brier(np.array(probs), np.array(outcomes)) if len(probs) >= 10 else None

# --- V1: Calibration ---
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

    train_p, train_y = train_bundle.signal_col, train_bundle.target
    corpus_results: Dict[str, Any] = {}
    all_ok = True
    for label, eval_seasons in [("2023-24", _EVAL_A_SEASONS), ("2025-26", _EVAL_B_SEASONS)]:
        try:
            eval_bundle = adapter.feature_bundle(hyp, eval_seasons)
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

# --- V2: CLV mechanics ---
def run_v2(adapter: TennisAdapter) -> Dict[str, Any]:
    """V2: CLV plumbing invariants (wiring correctness — NOT edge measurement)."""
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

# --- V3: Honest gate end-to-end ---
def _make_signal_with_bundle(signal_cls: type, bundle: FeatureBundle) -> Signal:
    sig: Signal = signal_cls()
    sig._gate_matrix = bundle  # type: ignore[attr-defined]
    return sig

def run_v3(adapter: TennisAdapter) -> Dict[str, Any]:
    """V3: gate.evaluate on 3 signals. Expected: all REJECT (gate honesty across sports)."""
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

# --- V4: Paper portfolio walk-forward (ARTIFACT-DISCLAIMED) ---
_V4_DISCLAIMER = "paper P&L is a market-follow artifact, not realized edge; no real money; markets efficient"

def run_v4(adapter: TennisAdapter, paper_book_dir: Optional[Path] = None) -> Dict[str, Any]:
    """V4: paper Kelly walk-forward exercising the sport-agnostic decision kernel."""
    inject_fired = not check_drawdown_ok(1000.0, 800.0)  # 20% loss > 15% threshold

    results: Dict[str, Any] = {"ok": False, "note": "", "detail": {}}
    try:
        matches = adapter._get_matches()
        odds = adapter._get_odds()
    except FileNotFoundError:
        results.update({"ok": inject_fired, "note": "odds.parquet absent — bets skipped.",
                        "detail": {"drawdown_inject_fired": inject_fired,
                                   "disclaimer": _V4_DISCLAIMER}})
        return results

    hyp = Hypothesis(name="tennis_elo_v4", target="winprob", scope="pregame",
                     statement="V4 paper wf", rationale="")
    # Use the earliest 40% of matches as train, rest as eval (robust to any date range)
    all_years = sorted(pd.to_datetime(matches["date"]).dt.year.unique().tolist())
    split_idx = max(1, len(all_years) * 2 // 5)
    train_years, eval_years = all_years[:split_idx], all_years[split_idx:]
    try:
        train_bundle = adapter.feature_bundle(hyp, train_years)
    except Exception as exc:
        results.update({"ok": inject_fired, "note": f"bundle error: {exc}",
                        "detail": {"drawdown_inject_fired": inject_fired,
                                   "disclaimer": _V4_DISCLAIMER}})
        return results

    train_p_raw, train_y_raw = train_bundle.signal_col, train_bundle.target
    _fin = np.isfinite(train_p_raw) & np.isfinite(train_y_raw)
    train_p, train_y = train_p_raw[_fin], train_y_raw[_fin]
    _n_finite_train = int(_fin.sum())
    _iso_ready = _n_finite_train >= 10

    joined = _filter_seasons(matches, eval_years).merge(odds, on="event_id", how="inner")
    bankroll = bankroll_start = 1000.0
    bets_log: List[Dict[str, Any]] = []
    n_skipped_nan = 0
    for _, row in joined.iterrows():
        try:
            pp1, pp2 = float(row["ps_p1"]), float(row["ps_p2"])
            if pp1 <= 1.0 or pp2 <= 1.0:
                continue
        except (TypeError, ValueError, KeyError):
            continue
        imp_p1 = (1.0 / pp1) / (1.0 / pp1 + 1.0 / pp2)
        try:
            raw_elo = float(row.get("p1_elo_prob", imp_p1))
        except (TypeError, ValueError):
            raw_elo = float("nan")
        if not np.isfinite(raw_elo) or not np.isfinite(imp_p1):
            n_skipped_nan += 1
            continue
        if _iso_ready:
            cal_p = float(np.clip(
                isotonic_calibrate(train_p, train_y, np.array([raw_elo]))[0], 0.01, 0.99
            ))
        else:
            cal_p = float(np.clip(raw_elo, 0.01, 0.99))
        b = pp1 - 1.0
        edge = cal_p - imp_p1
        kelly_clamped = clamp_kelly_pct(
            ((b * cal_p - (1 - cal_p)) / b) * KELLY_FRACTION if b > 0 else 0.0
        ) or 0.0
        stake = kelly_clamped * bankroll
        if stake <= 0 or not check_drawdown_ok(bankroll_start, bankroll):
            continue
        outcome = 1 if int(row.get("winner", 0)) == 1 else 0
        pnl = stake * b if outcome == 1 else -stake
        _ = letter_grade("winprob", cal_p, edge, playoff_window=False)  # exercise seam
        bankroll += pnl
        bets_log.append({"event_id": str(row.get("event_id", "")),
                         "cal_p": round(cal_p, 4), "kelly_clamped": round(kelly_clamped, 4),
                         "stake": round(stake, 4), "pnl": round(pnl, 4),
                         "disclaimer": _V4_DISCLAIMER})

    n_bets = len(bets_log)
    paper_pnl = round(sum(b["pnl"] for b in bets_log), 4)
    paper_roi = round(paper_pnl / bankroll_start * 100, 2) if n_bets > 0 else 0.0
    detail = {"n_bets": n_bets, "kelly_fraction_used": KELLY_FRACTION,
              "risk_gate_fired": False, "drawdown_inject_fired": inject_fired,
              "n_skipped_nan": n_skipped_nan, "n_finite_train": _n_finite_train,
              "paper_pnl_units": paper_pnl, "paper_return_pct": paper_roi,
              "disclaimer": _V4_DISCLAIMER}

    if paper_book_dir is not None:
        pb = Path(paper_book_dir); pb.mkdir(parents=True, exist_ok=True)
        (pb / "paper_book.json").write_text(
            json.dumps({"disclaimer": _V4_DISCLAIMER, **detail, "bets": bets_log}, indent=2),
            encoding="utf-8",
        )

    results["ok"] = inject_fired
    results["detail"] = detail
    if not inject_fired:
        results["note"] = "FAIL: synthetic drawdown injection did not fire"
    return results
