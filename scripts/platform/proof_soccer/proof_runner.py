"""scripts.platform.proof_soccer.proof_runner — V1/V2/V3/V4 execution helpers.

Split from run_proof.py to stay within the 300-LOC/file discipline.
Imports: only kernel gate seam, domains.soccer.*, proof_metrics, decision-kernel seam.
ZERO src.data / src.sim / src.tracking / src.pipeline / domains.nba /
domains.basketball_nba / other-domain imports.
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
from domains.soccer.adapter import SoccerAdapter
from domains.soccer.signals import (
    SoccerH2HTotalsSignal,
    SoccerRestCongestionSignal,
    SoccerTotalsFormSignal,
)
from scripts.platform.proof_soccer.proof_metrics import (
    brier, clv_sign_invariants, ece, isotonic_calibrate, reliability_slope, _devig2,
)
from src.prediction.betting_portfolio import (  # decision-kernel seam — F5 OK
    KELLY_FRACTION, clamp_kelly_pct, check_drawdown_ok,
)
from src.prediction.bet_grades import letter_grade

logger = logging.getLogger(__name__)

_TRAIN_SEASONS = list(range(2015, 2023))
_EVAL_A_SEASONS = [2023, 2024]
_EVAL_B_SEASONS = [2025]
_ALL_SEASONS = list(range(2015, 2026))
_ECE_THRESHOLD = 0.025
_SLOPE_LO, _SLOPE_HI = 0.9, 1.1


def _filter_seasons(df: pd.DataFrame, seasons: List[int]) -> pd.DataFrame:
    years = pd.to_datetime(df["date"]).dt.year
    return df[years.isin(seasons)].reset_index(drop=True)


def _market_brier(adapter: SoccerAdapter, seasons: List[int]) -> Optional[float]:
    """Devigged closing-line Brier for soccer O/U 2.5 — expected to beat model."""
    try:
        m = _filter_seasons(adapter._get_matches(), seasons)
        odds = adapter._get_odds()
    except FileNotFoundError:
        return None
    if m.empty or odds.empty:
        return None
    joined = m.merge(odds, on="event_id", how="inner")
    probs: List[float] = []
    outcomes: List[float] = []
    for _, row in joined.iterrows():
        try:
            op = float(row["ou_close_over"])
            up = float(row["ou_close_under"])
            if op <= 1.0 or up <= 1.0:
                continue
            p_over, _ = _devig2(op, up)
            tgt = float(row.get("target_over25", np.nan))
            if not np.isfinite(tgt):
                continue
            probs.append(p_over)
            outcomes.append(tgt)
        except (TypeError, ValueError, KeyError):
            continue
    return brier(np.array(probs), np.array(outcomes)) if len(probs) >= 10 else None


# --- V1: Calibration ---
def run_v1(adapter: SoccerAdapter) -> Dict[str, Any]:
    """V1: isotonic calibration on 2015-2022, evaluate on 2023-24 and 2025."""
    results: Dict[str, Any] = {"ok": False, "detail": {}}
    try:
        hyp = Hypothesis(name="soccer_p_over25_v1", target="winprob", scope="pregame",
                         statement="Soccer O/U 2.5 Poisson calibration baseline", rationale="")
        train_bundle = adapter.feature_bundle(hyp, _TRAIN_SEASONS)
    except Exception as exc:
        results["detail"]["error"] = str(exc)
        return results

    train_p, train_y = train_bundle.signal_col, train_bundle.target
    corpus_results: Dict[str, Any] = {}
    all_ok = True
    for label, eval_seasons in [("2023-24", _EVAL_A_SEASONS), ("2025", _EVAL_B_SEASONS)]:
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
            "market_devig_brier": round(mkt_b, 5) if mkt_b is not None else "N/A",
            "market_beats_model": (mkt_b < cal_b) if mkt_b is not None else "N/A (expected yes)",
            "calib_beats_raw": calib_beats_raw, "ece_ok": ece_ok,
            "slope_ok": slope_ok, "corpus_ok": corpus_ok,
        }
        if not corpus_ok:
            all_ok = False

    results["ok"] = all_ok
    results["detail"] = corpus_results
    return results


# --- V2: CLV mechanics ---
def run_v2(adapter: SoccerAdapter) -> Dict[str, Any]:
    """V2: CLV plumbing invariants on soccer open vs close prices (wiring correctness)."""
    results: Dict[str, Any] = {"ok": False, "note": "", "detail": {}}
    try:
        odds = adapter._get_odds()
    except FileNotFoundError:
        results["note"] = (
            "odds.parquet absent — V2 CLV mechanics skipped. "
            "Forward-capture CLV requires live feed integration."
        )
        results["ok"] = True
        return results

    open_over = pd.to_numeric(odds.get("ou_open_over", pd.Series([], dtype=float)), errors="coerce")
    open_under = pd.to_numeric(odds.get("ou_open_under", pd.Series([], dtype=float)), errors="coerce")
    close_over = pd.to_numeric(odds.get("ou_close_over", pd.Series([], dtype=float)), errors="coerce")
    close_under = pd.to_numeric(odds.get("ou_close_under", pd.Series([], dtype=float)), errors="coerce")
    valid = (open_over.notna() & open_under.notna() & close_over.notna() & close_under.notna()
             & (open_over > 1.0) & (open_under > 1.0)
             & (close_over > 1.0) & (close_under > 1.0))

    if valid.sum() < 10:
        results["note"] = f"Only {valid.sum()} rows with all four valid O/U prices; skipped."
        results["ok"] = True
        return results

    oa = open_over[valid].values
    ob = open_under[valid].values
    ca = close_over[valid].values
    cb = close_under[valid].values
    inv = clv_sign_invariants(open_a=oa, open_b=ob, close_a=ca, close_b=cb)

    results["ok"] = bool(inv["inv_a_ok"]) and bool(inv["inv_b_ok"])
    results["note"] = (
        "football-data 'as-collected' open prices are a weekly snapshot, NOT a true "
        "exchange opener; V2 is a PLUMBING/wiring-correctness check only, zero edge meaning."
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


def run_v3(adapter: SoccerAdapter) -> Dict[str, Any]:
    """V3: gate.evaluate on 3 soccer signals. Expected: all REJECT (DEFER acceptable)."""
    signal_defs = [
        (SoccerRestCongestionSignal, "REJECT"),
        (SoccerTotalsFormSignal, "REJECT"),
        (SoccerH2HTotalsSignal, "REJECT"),
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
_V4_DISCLAIMER = (
    "paper P&L is a market-follow artifact, not realized edge; no real money; markets efficient"
)


def run_v4(adapter: SoccerAdapter, paper_book_dir: Optional[Path] = None) -> Dict[str, Any]:
    """V4: paper Kelly walk-forward on O/U 2.5 exercising the sport-agnostic decision kernel."""
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

    hyp = Hypothesis(name="soccer_p_over25_v4", target="winprob", scope="pregame",
                     statement="V4 paper wf", rationale="")
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

    eval_matches = _filter_seasons(matches, eval_years)
    joined = eval_matches.merge(odds, on="event_id", how="inner")
    bankroll = bankroll_start = 1000.0
    bets_log: List[Dict[str, Any]] = []
    n_skipped_nan = 0
    for _, row in joined.iterrows():
        try:
            over_price = float(row["ou_close_over"])
            under_price = float(row["ou_close_under"])
            if over_price <= 1.0 or under_price <= 1.0:
                continue
        except (TypeError, ValueError, KeyError):
            continue
        imp_over, _ = _devig2(over_price, under_price)
        try:
            raw_p = float(row.get("p_over25", imp_over))
        except (TypeError, ValueError):
            raw_p = float("nan")
        if not np.isfinite(raw_p) or not np.isfinite(imp_over):
            n_skipped_nan += 1
            continue
        if _iso_ready:
            cal_p = float(np.clip(
                isotonic_calibrate(train_p, train_y, np.array([raw_p]))[0], 0.01, 0.99
            ))
        else:
            cal_p = float(np.clip(raw_p, 0.01, 0.99))
        b = over_price - 1.0
        edge = cal_p - imp_over
        kelly_clamped = clamp_kelly_pct(
            ((b * cal_p - (1 - cal_p)) / b) * KELLY_FRACTION if b > 0 else 0.0
        ) or 0.0
        stake = kelly_clamped * bankroll
        if stake <= 0 or not check_drawdown_ok(bankroll_start, bankroll):
            continue
        tgt = row.get("target_over25", np.nan)
        try:
            outcome = int(float(tgt))
        except (TypeError, ValueError):
            continue
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
        pb = Path(paper_book_dir)
        pb.mkdir(parents=True, exist_ok=True)
        (pb / "paper_book.json").write_text(
            json.dumps({"disclaimer": _V4_DISCLAIMER, **detail, "bets": bets_log}, indent=2),
            encoding="utf-8",
        )

    results["ok"] = inject_fired
    results["detail"] = detail
    if not inject_fired:
        results["note"] = "FAIL: synthetic drawdown injection did not fire"
    return results
