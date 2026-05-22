"""weekly_review.py — Weekly model health, calibration, and paper-trade review.

Run every Sunday morning or after sufficient residuals accumulate.  The
paper-trade review (task 19-02) evaluates the six go/no-go acceptance
criteria and prints an overall GO/NO-GO verdict, removing subjective
judgement from the decision to enable LIVE_BETTING=1.

Usage:
    python scripts/weekly_review.py [--min-samples N]
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_RESIDUALS_PATH = os.path.join(PROJECT_DIR, "data", "models", "prop_residuals.json")
_BET_LOG_PATH   = os.path.join(PROJECT_DIR, "data", "models", "bet_log.json")
_BACKTEST_PATH  = os.path.join(PROJECT_DIR, "data", "output", "backtest_results.json")
_CIRCUIT_PATH   = os.path.join(PROJECT_DIR, "data", "output", "circuit_state.json")
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

# ── go/no-go thresholds ──────────────────────────────────────────────────────
MIN_PAPER_BETS_SETTLED   = 20      # enough settled sample to judge
MIN_CLV_BEAT_RATE        = 0.50    # beat the closing line more than half the time
MIN_PAPER_ROI            = 0.0     # paper book must not be losing money
MAX_DRIFTED_STATS        = 0       # no stat may show calibration drift
MIN_BACKTEST_PAPER_RATIO = 0.70    # paper ROI >= 70% of backtested ROI
MAX_BREAKER_EVENTS_7D    = 2       # at most 2 circuit-breaker trips in 7 days
_DRIFT_REL_BIAS          = 0.15    # per-stat relative bias that counts as drift


def review_calibration(min_samples: int = 30) -> dict:
    """Run A/B calibration test. Returns results dict."""
    if not os.path.exists(_RESIDUALS_PATH):
        print("[weekly_review] No residuals found — run predictions first.")
        return {}

    with open(_RESIDUALS_PATH, encoding="utf-8") as f:
        residuals = json.load(f)

    # Import ab_test_calibration from fit_prop_calibration
    sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))
    from fit_prop_calibration import ab_test_calibration

    results = ab_test_calibration(residuals)
    return results


# ── paper-trade go/no-go review (task 19-02) ─────────────────────────────────

def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _clv_beat(bet: dict):
    """Whether a bet beat its closing line, or None when CLV is unknown."""
    if bet.get("clv") is not None:
        return float(bet["clv"]) > 0
    closing = bet.get("closing_line")
    opening = bet.get("book_line", bet.get("line"))
    if closing is None or opening is None:
        return None
    move = float(closing) - float(opening)
    return move > 0 if str(bet.get("direction", "over")).lower() == "over" else move < 0


def _settled_paper_bets(bets: list) -> list:
    """Paper bets that have been graded win/loss."""
    return [b for b in bets
            if (b.get("status") in ("won", "lost") or b.get("won") is not None)
            and b.get("status") != "pending"]


def _criterion(name: str, value, threshold, passed: bool, detail: str = "") -> dict:
    return {"name": name, "value": value, "threshold": threshold,
            "pass": bool(passed), "detail": detail}


def _calibration_drift(residuals: list, min_samples: int = 20) -> dict:
    """Per-stat relative bias; a stat is 'drifted' when |rel bias| > threshold."""
    drift = {}
    for stat in STATS:
        rows = [r for r in residuals if r.get("stat") == stat
                and r.get("predicted") is not None and r.get("actual") is not None]
        if len(rows) < min_samples:
            continue
        preds   = [float(r["predicted"]) for r in rows]
        actuals = [float(r["actual"]) for r in rows]
        mean_a  = sum(actuals) / len(actuals)
        bias    = sum(p - a for p, a in zip(preds, actuals)) / len(rows)
        rel     = abs(bias) / max(mean_a, 1.0)
        drift[stat] = {"rel_bias": round(rel, 4), "n": len(rows),
                       "drifted": rel > _DRIFT_REL_BIAS}
    return drift


def _breaker_events_within(circuit_state: dict, days: int = 7) -> int:
    """Count circuit-breaker trips whose timestamp falls within `days`."""
    if not circuit_state:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    count = 0
    for key, val in circuit_state.items():
        if not key.endswith("tripped_at") or not val:
            continue
        try:
            ts = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                count += 1
        except Exception:
            continue
    return count


def run_paper_trade_review(
    bet_log_path: str = None,
    backtest_path: str = None,
    circuit_state_path: str = None,
    residuals_path: str = None,
    *,
    days: int = 7,
) -> dict:
    """Evaluate the six paper-trade go/no-go criteria.

    Returns ``{"criteria": [...], "verdict": "GO"|"NO-GO", "passed": int,
    "total": int}``.  The verdict is GO only when every criterion passes.
    """
    bets       = _load_json(bet_log_path or _BET_LOG_PATH, [])
    backtest   = _load_json(backtest_path or _BACKTEST_PATH, {})
    circuit    = _load_json(circuit_state_path or _CIRCUIT_PATH, {})
    residuals  = _load_json(residuals_path or _RESIDUALS_PATH, [])

    settled = _settled_paper_bets(bets)
    criteria = []

    # 1. Paper bets settled
    n_settled = len(settled)
    criteria.append(_criterion(
        "paper_bets_settled", n_settled, MIN_PAPER_BETS_SETTLED,
        n_settled >= MIN_PAPER_BETS_SETTLED,
        f"{n_settled} settled (need >= {MIN_PAPER_BETS_SETTLED})"))

    # 2. CLV beat rate
    beats = [_clv_beat(b) for b in settled]
    beats = [b for b in beats if b is not None]
    clv_rate = (sum(beats) / len(beats)) if beats else None
    criteria.append(_criterion(
        "clv_beat_rate", round(clv_rate, 4) if clv_rate is not None else None,
        MIN_CLV_BEAT_RATE, clv_rate is not None and clv_rate >= MIN_CLV_BEAT_RATE,
        f"beat closing line on {len(beats)} bets" if beats else "no CLV data"))

    # 3. Paper ROI
    staked = sum(float(b.get("stake", 0.0) or 0.0) for b in settled)
    pnl    = sum(float(b.get("pnl", 0.0) or 0.0) for b in settled)
    paper_roi = (pnl / staked) if staked > 0 else None
    criteria.append(_criterion(
        "paper_roi", round(paper_roi, 4) if paper_roi is not None else None,
        MIN_PAPER_ROI, paper_roi is not None and paper_roi >= MIN_PAPER_ROI,
        f"pnl={pnl:.2f} on staked={staked:.2f}"))

    # 4. Calibration drift per stat
    drift = _calibration_drift(residuals)
    drifted = [s for s, d in drift.items() if d["drifted"]]
    criteria.append(_criterion(
        "calibration_drift", len(drifted), MAX_DRIFTED_STATS,
        len(drifted) <= MAX_DRIFTED_STATS,
        f"drifted stats: {drifted}" if drifted else "all stats within tolerance"))

    # 5. Backtest vs paper ROI ratio
    bt_roi = backtest.get("total_roi")
    if paper_roi is not None and bt_roi not in (None, 0):
        ratio = paper_roi / bt_roi
        ratio_pass = ratio >= MIN_BACKTEST_PAPER_RATIO
    else:
        ratio, ratio_pass = None, False
    criteria.append(_criterion(
        "backtest_paper_ratio", round(ratio, 4) if ratio is not None else None,
        MIN_BACKTEST_PAPER_RATIO, ratio_pass,
        f"paper_roi/backtest_roi (backtest_roi={bt_roi})"))

    # 6. Circuit breaker events last 7 days
    breaker_events = _breaker_events_within(circuit, days)
    criteria.append(_criterion(
        "circuit_breaker_events", breaker_events, MAX_BREAKER_EVENTS_7D,
        breaker_events <= MAX_BREAKER_EVENTS_7D,
        f"{breaker_events} trip(s) in last {days} days"))

    passed = sum(1 for c in criteria if c["pass"])
    verdict = "GO" if passed == len(criteria) else "NO-GO"
    return {"criteria": criteria, "verdict": verdict,
            "passed": passed, "total": len(criteria)}


def print_paper_trade_review(review: dict) -> None:
    """Print the paper-trade review as a PASS/FAIL table + GO/NO-GO verdict."""
    print("\n" + "=" * 60)
    print("Paper-Trade Review — Go/No-Go Criteria (19-02)")
    print("=" * 60)
    for c in review["criteria"]:
        flag = "PASS" if c["pass"] else "FAIL"
        print(f"  [{flag}] {c['name']:24s} value={c['value']}  "
              f"threshold={c['threshold']}")
        if c["detail"]:
            print(f"         {c['detail']}")
    print("-" * 60)
    print(f"  {review['passed']}/{review['total']} criteria passed  "
          f"-->  VERDICT: {review['verdict']}")
    print("=" * 60)


def main(min_samples: int = 30) -> None:
    print("=" * 60)
    print("Weekly Review — Calibration A/B Test")
    print("=" * 60)

    results = review_calibration(min_samples)
    if not results:
        print("[weekly_review] Calibration skipped — no residuals.")
        print_paper_trade_review(run_paper_trade_review())
        return

    promoted_count = sum(1 for r in results.values() if r.get("promoted"))
    print(f"\nCalibration results ({promoted_count}/{len(results)} models promoted):")
    for stat, r in results.items():
        if "reason" in r:
            print(f"  {stat}: skipped ({r['reason']})")
            continue
        status = "PROMOTED" if r.get("promoted") else "kept"
        old = f"{r.get('old_brier', 'n/a'):.4f}" if isinstance(r.get("old_brier"), float) else "n/a"
        new = f"{r.get('new_brier', 0):.4f}"
        print(f"  {stat}: old_brier={old}  new_brier={new}  [{status}]")

    print_paper_trade_review(run_paper_trade_review())
    print("\nDone.")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Weekly model health review")
    p.add_argument("--min-samples", type=int, default=30)
    args = p.parse_args()
    main(min_samples=args.min_samples)
