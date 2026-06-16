"""sport-blind V4 paper Kelly walk-forward, parameterised by ProofSpec.

Numeric loop order (§4.2 pinned):
  price-parse → ≤1.0-filter → implied → model-prob → finite-skip →
  calibrate → b=price_a-1 → edge → kelly-clamp → stake →
  (stake≤0|drawdown)continue → outcome-leaf(None→continue) →
  pnl → letter_grade seam(discarded) → bankroll → log-append
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.signal import Hypothesis
from src.prediction.betting_portfolio import KELLY_FRACTION, check_drawdown_ok, clamp_kelly_pct
from src.prediction.bet_grades import letter_grade
from kernel.validation.proof_metrics import isotonic_calibrate, devig2

from scripts.platformkit.proof_common.spec import ProofSpec

# _filter_seasons: verbatim from originals; defined locally because runner.py
# (K-PR-002) is a parallel-group-2 task that may not exist at import time.
def _filter_seasons(df: pd.DataFrame, seasons: List[int]) -> pd.DataFrame:
    """Return rows whose date-year is in *seasons*, resetting the index."""
    years = pd.to_datetime(df["date"]).dt.year
    return df[years.isin(seasons)].reset_index(drop=True)


_V4_DISCLAIMER = (
    "paper/simulated, market-follow-artifact risk, NOT realized edge; "
    "no real money; markets efficient"
)

# EXPLICIT opt-in env var. The V4 paper-Kelly path emits a $ bankroll P&L whose SHAPE is
# exactly the retracted +ROI artifact. It is OFF by default and must never run inside the
# scoreboards. Enable it only deliberately: env PROOF_ALLOW_PAPER_KELLY=1 or allow=True.
_PAPER_KELLY_ENV = "PROOF_ALLOW_PAPER_KELLY"


def _paper_kelly_allowed(allow: Optional[bool]) -> bool:
    """True only on explicit opt-in: allow=True kwarg OR env PROOF_ALLOW_PAPER_KELLY=1."""
    if allow is True:
        return True
    if allow is False:
        return False
    return os.environ.get(_PAPER_KELLY_ENV, "").strip() in ("1", "true", "True", "TRUE")


def _gated_noop(reason: str) -> Dict[str, Any]:
    """No-op return when the paper-Kelly $ path is not explicitly enabled."""
    return {
        "ok": True,
        "gated": True,
        "note": reason,
        "detail": {
            "gated": True,
            "paper_kelly_allowed": False,
            "n_bets": 0,
            "paper_pnl_units": 0.0,
            "paper_return_pct": 0.0,
            "disclaimer": _V4_DISCLAIMER,
        },
    }


def run_v4(
    spec: ProofSpec,
    adapter: Any,
    paper_book_dir: Optional[Path] = None,
    ctx: Optional[str] = None,
    allow: Optional[bool] = None,
) -> Dict[str, Any]:
    """V4: paper Kelly walk-forward exercising the sport-agnostic decision kernel.

    GATED: this path emits a $ bankroll P&L (the SHAPE of the retracted +ROI artifact). It
    NO-OPS unless explicitly opted-in via allow=True or env PROOF_ALLOW_PAPER_KELLY=1. Every
    printed/returned $ number carries _V4_DISCLAIMER. No scoreboard imports or runs this.
    """
    if not _paper_kelly_allowed(allow):
        return _gated_noop(
            "V4 paper-Kelly $ P&L is gated OFF (paper/simulated, market-follow-artifact "
            "risk, NOT realized edge). Set allow=True or env "
            f"{_PAPER_KELLY_ENV}=1 to run it deliberately."
        )
    inject_fired = not check_drawdown_ok(1000.0, 800.0)
    results: Dict[str, Any] = {"ok": False, "note": "", "detail": {}}

    try:
        matches, odds = spec.get_frames_v4(adapter)
    except FileNotFoundError:
        results.update({"ok": inject_fired, "note": "odds.parquet absent — bets skipped.",
                        "detail": {"drawdown_inject_fired": inject_fired,
                                   "disclaimer": _V4_DISCLAIMER}})
        return results

    hyp = Hypothesis(name=spec.hyp_v4_name, target="winprob", scope="pregame",
                     statement="V4 paper wf", rationale="")
    all_years = sorted(pd.to_datetime(matches["date"]).dt.year.unique().tolist())
    split_idx = max(1, len(all_years) * 2 // 5)
    train_years, eval_years = all_years[:split_idx], all_years[split_idx:]

    try:
        train_bundle = adapter.feature_bundle(hyp, train_years, **spec.bundle_kwargs(ctx))
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

    eval_frame = spec.filter_v4_eval(_filter_seasons(matches, eval_years), ctx)
    joined = eval_frame.merge(odds, on="event_id", how="inner")

    bankroll = bankroll_start = 1000.0
    bets_log: List[Dict[str, Any]] = []
    n_skipped_nan = 0

    for _, row in joined.iterrows():
        try:
            price_a = float(row[spec.close_a_col])
            price_b = float(row[spec.close_b_col])
            if price_a <= 1.0 or price_b <= 1.0:
                continue
        except (TypeError, ValueError, KeyError):
            continue

        imp_p, _ = devig2(price_a, price_b)

        try:
            raw_p = float(row.get(spec.model_prob_col, imp_p))
        except (TypeError, ValueError):
            raw_p = float("nan")

        if not np.isfinite(raw_p) or not np.isfinite(imp_p):
            n_skipped_nan += 1
            continue

        if _iso_ready:
            cal_p = float(np.clip(
                isotonic_calibrate(train_p, train_y, np.array([raw_p]))[0], 0.01, 0.99
            ))
        else:
            cal_p = float(np.clip(raw_p, 0.01, 0.99))

        b = price_a - 1.0
        edge = cal_p - imp_p
        kelly_clamped = clamp_kelly_pct(
            ((b * cal_p - (1 - cal_p)) / b) * KELLY_FRACTION if b > 0 else 0.0
        ) or 0.0
        stake = kelly_clamped * bankroll
        if stake <= 0 or not check_drawdown_ok(bankroll_start, bankroll):
            continue

        outcome = spec.outcome_v4(row)
        if outcome is None:
            continue

        pnl = stake * b if outcome == 1 else -stake
        _ = letter_grade("winprob", cal_p, edge, playoff_window=False)
        bankroll += pnl
        bets_log.append({"event_id": str(row.get("event_id", "")),
                         "cal_p": round(cal_p, 4), "kelly_clamped": round(kelly_clamped, 4),
                         "stake": round(stake, 4), "pnl": round(pnl, 4),
                         "disclaimer": _V4_DISCLAIMER})

    n_bets = len(bets_log)
    paper_pnl = round(sum(b["pnl"] for b in bets_log), 4)
    paper_roi = round(paper_pnl / bankroll_start * 100, 2) if n_bets > 0 else 0.0
    detail: Dict[str, Any] = {
        "n_bets": n_bets, "kelly_fraction_used": KELLY_FRACTION,
        "risk_gate_fired": False, "drawdown_inject_fired": inject_fired,
        "n_skipped_nan": n_skipped_nan, "n_finite_train": _n_finite_train,
        "paper_pnl_units": paper_pnl, "paper_return_pct": paper_roi,
        "disclaimer": _V4_DISCLAIMER,
    }

    if paper_book_dir is not None:
        pb = Path(paper_book_dir)
        pb.mkdir(parents=True, exist_ok=True)
        (pb / spec.book_filename(ctx)).write_text(
            json.dumps({"disclaimer": _V4_DISCLAIMER, **detail, "bets": bets_log}, indent=2),
            encoding="utf-8",
        )

    results["ok"] = inject_fired
    results["detail"] = detail
    if not inject_fired:
        results["note"] = "FAIL: synthetic drawdown injection did not fire"
    return results
