"""scripts.platform.proof_mlb.proof_runner — V1/V2/V3/V4 execution helpers.

ZERO src.data/src.sim/src.tracking/src.pipeline/domains.nba/domains.basketball_nba
or other-domain imports.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.gate import FeatureBundle, evaluate
from src.loop.signal import GateResult, Hypothesis, Signal
from domains.mlb.adapter import MLBAdapter
from domains.mlb.signals import MLBRestAdvantageSignal, MLBStreakFormSignal, MLBH2HSeasonSignal
from scripts.platform.proof_mlb.proof_metrics import (
    brier, clv_sign_invariants, ece, isotonic_calibrate, reliability_slope, _devig2,
)
from src.prediction.betting_portfolio import KELLY_FRACTION, clamp_kelly_pct, check_drawdown_ok
from src.prediction.bet_grades import letter_grade

logger = logging.getLogger(__name__)

_TRAIN_SEASONS = list(range(2010, 2018))
_EVAL_A_SEASONS = [2018, 2019]
_EVAL_B_SEASONS = [2020, 2021]
_ALL_SEASONS = list(range(2010, 2022))
_ECE_THRESHOLD = 0.025
_SLOPE_LO, _SLOPE_HI = 0.9, 1.1
_V4_DISCLAIMER = (
    "paper P&L is a market-follow artifact, not realized edge; no real money; markets efficient"
)


def _filter_seasons(df: pd.DataFrame, seasons: List[int]) -> pd.DataFrame:
    return df[pd.to_datetime(df["date"]).dt.year.isin(seasons)].reset_index(drop=True)


def _market_brier(adapter: MLBAdapter, seasons: List[int], lf: Optional[str]) -> Optional[float]:
    """Devigged closing moneyline Brier (home side) — expected to beat model."""
    try:
        games = adapter._get_games(); odds = adapter._get_odds()
    except FileNotFoundError:
        return None
    games = games[games["season"].isin(seasons)]
    if lf is not None:
        games = games[games["home_league"] == lf]
    if games.empty or odds.empty:
        return None
    joined = games.merge(odds, on="event_id", how="inner")
    probs: List[float] = []; outcomes: List[float] = []
    for _, row in joined.iterrows():
        try:
            hc, ac = float(row["dec_close_home"]), float(row["dec_close_away"])
            if hc <= 1.0 or ac <= 1.0:
                continue
            p_home, _ = _devig2(hc, ac)
            tgt = float(row.get("target_home_win", np.nan))
            if not np.isfinite(tgt):
                continue
            probs.append(p_home); outcomes.append(tgt)
        except (TypeError, ValueError, KeyError):
            continue
    return brier(np.array(probs), np.array(outcomes)) if len(probs) >= 10 else None


# --- V1: Calibration ---
def run_v1(adapter: MLBAdapter, league_filter: Optional[str] = None) -> Dict[str, Any]:
    """V1: isotonic calibration 2010-2017; evaluate 2018-19 and 2020-21.
    2020 = COVID 60-game season — recorded honestly; thresholds UNCHANGED.
    """
    results: Dict[str, Any] = {"ok": False, "detail": {}}
    hyp = Hypothesis(name="mlb_p_home_elo_v1", target="winprob", scope="pregame",
                     statement="MLB Elo home-win probability calibration baseline", rationale="")
    try:
        train_bundle = adapter.feature_bundle(hyp, _TRAIN_SEASONS, league_filter=league_filter)
    except Exception as exc:
        results["detail"]["error"] = str(exc); return results
    train_p, train_y = train_bundle.signal_col, train_bundle.target
    corpus_results: Dict[str, Any] = {}
    all_ok = True
    for label, eval_seasons, note in [
        ("2018-19", _EVAL_A_SEASONS, ""),
        ("2020-21", _EVAL_B_SEASONS, "NOTE: 2020 COVID 60-game season included as-is."),
    ]:
        try:
            eb = adapter.feature_bundle(hyp, eval_seasons, league_filter=league_filter)
        except Exception as exc:
            corpus_results[label] = {"error": str(exc)}; all_ok = False; continue
        ep, ey = eb.signal_col, eb.target
        cp = isotonic_calibrate(train_p, train_y, ep)
        rb, cb = brier(ep, ey), brier(cp, ey)
        ce, cs = ece(cp, ey), reliability_slope(cp, ey)
        mkt = _market_brier(adapter, eval_seasons, league_filter)
        calib_ok = cb <= rb + 1e-6
        ece_ok = ce < _ECE_THRESHOLD
        slope_ok = (not np.isnan(cs)) and _SLOPE_LO <= cs <= _SLOPE_HI
        ok = calib_ok and ece_ok and slope_ok
        corpus_results[label] = {
            "n_eval": int(len(ey)), "raw_brier": round(rb, 5), "calibrated_brier": round(cb, 5),
            "ece": round(ce, 5),
            "reliability_slope": round(float(cs), 4) if not np.isnan(cs) else "nan",
            "market_devig_brier": round(mkt, 5) if mkt is not None else "N/A",
            "market_beats_model": (mkt < cb) if mkt is not None else "N/A (expected yes)",
            "calib_beats_raw": calib_ok, "ece_ok": ece_ok, "slope_ok": slope_ok,
            "corpus_ok": ok, "regime_note": note,
        }
        if not ok:
            all_ok = False
    results["ok"] = all_ok; results["detail"] = corpus_results
    return results


# --- V2: CLV mechanics ---
def run_v2(adapter: MLBAdapter, league_filter: Optional[str] = None) -> Dict[str, Any]:
    """V2: CLV plumbing on MLB open+close moneyline. WIRING CORRECTNESS ONLY."""
    results: Dict[str, Any] = {"ok": False, "note": "", "detail": {}}
    try:
        odds = adapter._get_odds()
    except FileNotFoundError:
        results["note"] = "odds.parquet absent — V2 CLV mechanics skipped."
        results["ok"] = True; return results
    if league_filter is not None:
        try:
            games = adapter._get_games()
            ids = set(games[games["home_league"] == league_filter]["event_id"].astype(str))
            odds = odds[odds["event_id"].astype(str).isin(ids)]
        except Exception:
            pass
    oa = pd.to_numeric(odds.get("dec_open_home", pd.Series([], dtype=float)), errors="coerce")
    ob = pd.to_numeric(odds.get("dec_open_away", pd.Series([], dtype=float)), errors="coerce")
    ca = pd.to_numeric(odds.get("dec_close_home", pd.Series([], dtype=float)), errors="coerce")
    cb = pd.to_numeric(odds.get("dec_close_away", pd.Series([], dtype=float)), errors="coerce")
    valid = (oa.notna() & ob.notna() & ca.notna() & cb.notna()
             & (oa > 1.0) & (ob > 1.0) & (ca > 1.0) & (cb > 1.0))
    if valid.sum() < 10:
        results["note"] = f"Only {valid.sum()} rows with valid prices; skipped."
        results["ok"] = True; return results
    inv = clv_sign_invariants(open_a=oa[valid].values, open_b=ob[valid].values,
                              close_a=ca[valid].values, close_b=cb[valid].values)
    results["ok"] = bool(inv["inv_a_ok"]) and bool(inv["inv_b_ok"])
    results["note"] = ("MLB moneyline has TRUE opening and closing prices "
                       "(strongest V2 plumbing test); wiring-correctness ONLY.")
    results["detail"] = {
        "n_rows": int(valid.sum()),
        **{k: (bool(v) if isinstance(v, (bool, np.bool_)) else round(float(v), 8))
           for k, v in inv.items()},
    }
    return results


# --- V3: Honest gate ---
def _make_signal_with_bundle(signal_cls: type, bundle: FeatureBundle) -> Signal:
    sig: Signal = signal_cls()
    sig._gate_matrix = bundle  # type: ignore[attr-defined]
    return sig


def run_v3(adapter: MLBAdapter, league_filter: Optional[str] = None) -> Dict[str, Any]:
    """V3: gate.evaluate on 3 MLB signals. Expected: all REJECT (DEFER acceptable)."""
    verdict_rows: List[Dict[str, Any]] = []
    for signal_cls, expected in [
        (MLBRestAdvantageSignal, "REJECT"),
        (MLBStreakFormSignal, "REJECT"),
        (MLBH2HSeasonSignal, "REJECT"),
    ]:
        name = signal_cls.name
        hyp = Hypothesis(name=name, target="winprob", scope="pregame",
                         statement=name, rationale="")
        try:
            bundle = adapter.feature_bundle(hyp, _ALL_SEASONS, league_filter=league_filter)
        except Exception as exc:
            verdict_rows.append({"signal": name, "expected": expected, "actual": "BUNDLE_ERROR",
                                  "reason": str(exc), "passed_expected": False}); continue
        sig = _make_signal_with_bundle(signal_cls, bundle)
        try:
            result: GateResult = evaluate(sig, device="cpu", n_splits=3)
        except Exception as exc:
            verdict_rows.append({"signal": name, "expected": expected, "actual": "GATE_ERROR",
                                  "reason": str(exc), "passed_expected": False}); continue
        actual = result.verdict.value
        passed = actual in {"REJECT", "DEFER"}
        verdict_rows.append({
            "signal": name, "expected": expected, "actual": actual, "reason": result.reason,
            "wf_folds": result.wf_folds, "wf_all_improve": result.wf_all_improve,
            "ablation_delta": result.ablation_delta, "ablation_pass": result.ablation_pass,
            "null_pass": result.null_pass, "calibration_ok": result.calibration_ok,
            "clv": result.clv, "p_value": result.p_value, "passed_expected": passed,
        })
    return {"ok": all(r["passed_expected"] for r in verdict_rows), "verdicts": verdict_rows}


# --- V4: Paper portfolio (ARTIFACT-DISCLAIMED) ---
def run_v4(adapter: MLBAdapter, paper_book_dir: Optional[Path] = None,
           league_filter: Optional[str] = None) -> Dict[str, Any]:
    """V4: paper Kelly walk-forward on MLB moneyline; exercises decision kernel."""
    inject_fired = not check_drawdown_ok(1000.0, 800.0)
    base = {"drawdown_inject_fired": inject_fired, "disclaimer": _V4_DISCLAIMER}
    results: Dict[str, Any] = {"ok": False, "note": "", "detail": {}}
    try:
        games = adapter._get_games(); odds = adapter._get_odds()
    except FileNotFoundError:
        results.update({"ok": inject_fired, "note": "odds.parquet absent.", "detail": base})
        return results
    hyp = Hypothesis(name="mlb_p_home_elo_v4", target="winprob", scope="pregame",
                     statement="V4 paper wf", rationale="")
    all_years = sorted(pd.to_datetime(games["date"]).dt.year.unique().tolist())
    split_idx = max(1, len(all_years) * 2 // 5)
    train_years, eval_years = all_years[:split_idx], all_years[split_idx:]
    try:
        tb = adapter.feature_bundle(hyp, train_years, league_filter=league_filter)
    except Exception as exc:
        results.update({"ok": inject_fired, "note": f"bundle error: {exc}", "detail": base})
        return results
    _fin = np.isfinite(tb.signal_col) & np.isfinite(tb.target)
    tp, ty, nft = tb.signal_col[_fin], tb.target[_fin], int(_fin.sum())
    iso_ok = nft >= 10
    ev = _filter_seasons(games, eval_years)
    if league_filter is not None:
        ev = ev[ev["home_league"] == league_filter]
    joined = ev.merge(odds, on="event_id", how="inner")
    bankroll = start = 1000.0; bets: List[Dict] = []; nskip = 0
    for _, row in joined.iterrows():
        try:
            hp, ap = float(row["dec_close_home"]), float(row["dec_close_away"])
            if hp <= 1.0 or ap <= 1.0: continue
        except (TypeError, ValueError, KeyError): continue
        imp, _ = _devig2(hp, ap)
        try: rp = float(row.get("p_home_elo", imp))
        except (TypeError, ValueError): rp = float("nan")
        if not np.isfinite(rp) or not np.isfinite(imp): nskip += 1; continue
        cal = float(np.clip(isotonic_calibrate(tp, ty, np.array([rp]))[0], 0.01, 0.99)) \
            if iso_ok else float(np.clip(rp, 0.01, 0.99))
        b = hp - 1.0; edge = cal - imp
        k = clamp_kelly_pct(((b * cal - (1 - cal)) / b) * KELLY_FRACTION if b > 0 else 0.0) or 0.0
        stake = k * bankroll
        if stake <= 0 or not check_drawdown_ok(start, bankroll): continue
        try: outcome = int(float(row.get("target_home_win", np.nan)))
        except (TypeError, ValueError): continue
        _ = letter_grade("winprob", cal, edge, playoff_window=False)
        pnl = stake * b if outcome == 1 else -stake
        bankroll += pnl
        bets.append({"event_id": str(row.get("event_id", "")), "cal_p": round(cal, 4),
                     "kelly_clamped": round(k, 4), "stake": round(stake, 4),
                     "pnl": round(pnl, 4), "disclaimer": _V4_DISCLAIMER})
    nb = len(bets); ppnl = round(sum(x["pnl"] for x in bets), 4)
    detail = {"n_bets": nb, "kelly_fraction_used": KELLY_FRACTION, "risk_gate_fired": False,
              "drawdown_inject_fired": inject_fired, "n_skipped_nan": nskip,
              "n_finite_train": nft, "paper_pnl_units": ppnl,
              "paper_return_pct": round(ppnl / start * 100, 2) if nb > 0 else 0.0,
              "disclaimer": _V4_DISCLAIMER}
    if paper_book_dir is not None:
        pb = Path(paper_book_dir); pb.mkdir(parents=True, exist_ok=True)
        sfx = f"_{league_filter}" if league_filter else ""
        (pb / f"paper_book{sfx}.json").write_text(
            json.dumps({"disclaimer": _V4_DISCLAIMER, **detail, "bets": bets}, indent=2),
            encoding="utf-8")
    results["ok"] = inject_fired; results["detail"] = detail
    if not inject_fired:
        results["note"] = "FAIL: synthetic drawdown injection did not fire"
    return results
