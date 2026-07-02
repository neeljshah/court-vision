"""scripts.platformkit.econ.beat_the_line -- the literal "am I beating the
line" scoreboard (6.4).

Per channel (and per channel-per-week, the user's literal weekly ask): n,
realized win rate, close-implied win rate (from each bet's own
fair_close_prob -- the Poisson-binomial normal-approx pattern
clv_result_reconciler.py already uses; REUSED here via its
_close_implied_expectation helper, not reinvented), the EXCESS
(realized - implied) with a binomial-style 95% CI, cumulative units, and
after-cost units (calls into after_cost_scoreboard.py's per-row costing, 6.3).

THE artifact that answers "am I beating lines more often than not" -- not
"do I have positive CLV" (a different, price-based question already answered
by clv_scoreboard.py) but "does my WIN RATE beat what the close itself implied
I should win", in win-rate terms with an honest confidence interval.

Reuses the canonical ledger reader + clv_scoreboard's channel/measurability
filters + clv_result_reconciler's close-implied expectation math + this
package's own after_cost_scoreboard row-costing. New module, does not edit
any near-budget file.

NEVER raises on a single bad row (skips it, keeps going); tiny samples report
INSUFFICIENT_DATA rather than a fake-precise number.

Run:  python -m scripts.platformkit.econ.beat_the_line
"""
from __future__ import annotations

import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.clv_ledger import load_ledger  # canonical reader
from scripts.platformkit.clv.clv_scoreboard import (
    _channel_of, _dedup_settled, _is_measurable, _CHANNEL_LABEL)
from scripts.platformkit.clv.clv_result_reconciler import (
    _close_implied_expectation, _record)
from scripts.platformkit.econ.after_cost_scoreboard import after_cost_units

_OUT_JSON = os.path.join(_REPO, "data", "frontend", "ops", "beat_the_line.json")
_MIN_N = 10  # below this, report INSUFFICIENT_DATA rather than a noisy CI


def _iso_week(row: Dict[str, Any]) -> str:
    """ISO year-week token ('2026-W27') from settled_at, falling back to ts.
    Malformed/missing timestamps bucket under 'unknown' rather than crashing.
    """
    raw = str(row.get("settled_at") or row.get("ts") or "")[:10]
    try:
        import datetime
        d = datetime.date.fromisoformat(raw)
        iso = d.isocalendar()
        return "%04d-W%02d" % (iso[0], iso[1])
    except (ValueError, TypeError):
        return "unknown"


def _win_rate_excess(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """realized win rate vs close-implied win rate, with a binomial-style CI
    on the excess (realized - implied), reusing clv_result_reconciler's
    Poisson-binomial normal-approx expectation for the implied side.
    """
    n = len(rows)
    rec = _record(rows)
    decided = rec["wins"] + rec["losses"]  # pushes excluded from a win-RATE denom
    exp = _close_implied_expectation(rows)
    if n < _MIN_N or decided == 0 or exp["n_used"] == 0:
        return {
            "n": n, "n_decided": decided, "realized_win_rate": None,
            "implied_win_rate": None, "excess": None, "excess_ci95": [None, None],
            "excess_significant": False,
            "verdict": ("INSUFFICIENT_DATA -- only %d settled (%d decided); need "
                        ">= %d to compute a trustworthy excess win rate." % (n, decided, _MIN_N)),
        }
    realized_wr = rec["wins"] / decided
    implied_wr = exp["exp_wins"] / exp["n_used"]
    excess = realized_wr - implied_wr
    # SE of a difference in rates over the same n (paired at the bet level):
    # var(realized) ~= p(1-p)/n_decided (binomial); var(implied) already summed
    # per-bet variance in _close_implied_expectation (se_wins**2 / n_used**2 is
    # the mean-implied-rate variance). Combine conservatively (independent-sum,
    # an over-estimate of the true paired SE, so CIs here are, if anything,
    # WIDER/more conservative than a paired test would give).
    var_realized = (realized_wr * (1.0 - realized_wr) / decided) if decided > 0 else 0.0
    se_wins = exp.get("se_wins")
    var_implied = ((se_wins / exp["n_used"]) ** 2) if se_wins else 0.0
    se_excess = math.sqrt(var_realized + var_implied)
    lo, hi = excess - 1.96 * se_excess, excess + 1.96 * se_excess
    significant = (lo > 0.0) or (hi < 0.0)
    if significant:
        verdict = ("SIGNIFICANT %s -- excess win rate 95%% CI excludes 0 (n=%d)."
                    % ("POSITIVE" if excess > 0 else "NEGATIVE", decided))
    else:
        verdict = ("NOT SIGNIFICANT -- excess win rate CI includes 0 (n=%d); "
                    "not yet distinguishable from close-implied noise." % decided)
    return {
        "n": n, "n_decided": decided,
        "realized_win_rate": round(realized_wr, 4),
        "implied_win_rate": round(implied_wr, 4),
        "excess": round(excess, 4),
        "excess_ci95": [round(lo, 4), round(hi, 4)],
        "excess_significant": significant,
        "verdict": verdict,
    }


def _after_cost_total(rows: Sequence[Dict[str, Any]]) -> Optional[float]:
    total = 0.0
    n_costed = 0
    for r in rows:
        rec = after_cost_units(r)
        if rec is None:
            continue
        n_costed += 1
        total += rec["after_cost_units"]
    return round(total, 3) if n_costed else None


def _channel_report(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    rec = _record(rows)
    wr = _win_rate_excess(rows)
    wr["cumulative_units"] = rec["net_units"]
    wr["after_cost_units"] = _after_cost_total(rows)
    # weekly breakdown -- the user's literal "per week" ask
    by_week: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_week.setdefault(_iso_week(r), []).append(r)
    weekly: Dict[str, Any] = {}
    for wk, wrows in sorted(by_week.items()):
        w_wr = _win_rate_excess(wrows)
        w_rec = _record(wrows)
        w_wr["cumulative_units"] = w_rec["net_units"]
        w_wr["after_cost_units"] = _after_cost_total(wrows)
        weekly[wk] = w_wr
    wr["weekly"] = weekly
    return wr


def beat_the_line(ledger: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Build the per-channel beat-the-line report dict (pure; no printing/I-O)."""
    if ledger is None:
        ledger = load_ledger()
    settled = _dedup_settled(ledger)

    by_ch: Dict[str, List[Dict[str, Any]]] = {}
    for r in settled:
        if not _is_measurable(r):
            continue  # needs a real close to compute an implied win rate
        by_ch.setdefault(_channel_of(r), []).append(r)

    channels: Dict[str, Any] = {}
    for ch, rows in by_ch.items():
        rep = _channel_report(rows)
        rep["label"] = _CHANNEL_LABEL.get(ch, ch)
        channels[ch] = rep

    return {"channels": channels}


def render(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 78)
    lines.append("BEAT THE LINE -- realized vs close-implied win rate (units only)")
    lines.append("=" * 78)
    hdr = ("%-18s %5s %8s %8s %8s %10s %10s"
           % ("channel", "n", "real_wr", "impl_wr", "excess", "cum_u", "net_u"))
    lines.append(hdr)
    lines.append("-" * 78)
    for ch in sorted(report["channels"], key=lambda c: -report["channels"][c]["n"]):
        c = report["channels"][ch]
        rw = ("%.3f" % c["realized_win_rate"]) if c["realized_win_rate"] is not None else "--"
        iw = ("%.3f" % c["implied_win_rate"]) if c["implied_win_rate"] is not None else "--"
        ex = ("%+.3f" % c["excess"]) if c["excess"] is not None else "--"
        if c["excess_significant"]:
            ex += "*"
        ac = ("%+.2f" % c["after_cost_units"]) if c["after_cost_units"] is not None else "--"
        lines.append("%-18s %5d %8s %8s %8s %10.2f %10s"
                     % (c["label"], c["n"], rw, iw, ex, c["cumulative_units"], ac))
        lines.append("    VERDICT: " + c["verdict"])
    lines.append("-" * 78)
    lines.append("* = excess win-rate 95%% CI excludes 0. net_u = after-cost units (6.3).")
    lines.append("=" * 78)
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    report = beat_the_line()
    print(render(report))
    try:
        os.makedirs(os.path.dirname(_OUT_JSON), exist_ok=True)
        with open(_OUT_JSON, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1)
        print("\nwrote %s" % _OUT_JSON)
    except OSError as exc:
        print("(beat_the_line JSON not written: %s)" % type(exc).__name__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
