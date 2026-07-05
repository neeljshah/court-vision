"""clv_result_reconciler -- resolves an apparent CLV-vs-record contradiction.

The scoreboard (clv_scoreboard.py) can show a channel with significant POSITIVE
mean CLV alongside a LOSING realized record (e.g. paper_pm: +CLV%* but net
negative units). That looks contradictory but usually is not: CLV measures
whether you got a BETTER PRICE than the close, not whether that price wins.
Beating the close is +EV in expectation vs the market's own probability
estimate; a losing streak on top of that is ordinary variance unless the
record diverges from what the close-implied probabilities themselves predict
by more than noise.

This module tells the two apart for one channel's MEASURABLE (true_close, not
suspect) settled rows:

  1. CLOSE-IMPLIED EXPECTATION: using each bet's own fair_close_prob (the
     devigged probability of the side taken, at the close), compute the
     expected win count (Poisson-binomial normal approx) and expected units
     (EV under the close-implied probability) and their standard errors.
  2. Z-SCORE the realized record against that expectation. |z| < 1.96 (95%)
     means the realized record is NOT distinguishable from what an efficient
     close would produce -- GENUINE_VARIANCE, not a data problem.
  3. MECHANISM SMELL CHECK (transparency only, never auto-flags SUSPECT by
     itself): counts rows whose closing (home,away) decimal pair is IDENTICAL
     across two DIFFERENT event_ids -- worth a human glance (a real stale/
     cached-quote bug looks like this), but round American odds (e.g. -139)
     legitimately repeat across unrelated games, so this is reported as a
     count, not a verdict.

Honest rails: units only, no $ field, no edge claim, read-only (never mutates
the ledger), reuses the canonical ledger reader + scoreboard filters.

Run:  python -m scripts.platformkit.clv.clv_result_reconciler [channel ...]
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
    _channel_of, _dedup_settled, _is_measurable, _mean_ci, _CHANNEL_LABEL)

_OUT_DIR = os.path.join(_REPO, "data", "frontend", "ops")
_Z_SIG = 1.96
_MIN_N = 10

# Full known-channel set (greenlight E-check-3): the reconciler must emit a
# file for every one of these EACH run, even when a channel currently has
# zero/too-few measurable rows -- an absent file reads as "reconciler broken",
# not "not yet". reconcile_channel() already returns an honest
# INSUFFICIENT_DATA verdict + real n_measurable + un-fabricated (None) z's for
# a zero-row channel, so no change to the math below; this is enumeration only.
KNOWN_CHANNELS = ("moneyline", "paper_pm", "paper_ingame", "paper_ingame_prop")


def _measurable_rows(channel: str, ledger: Optional[Sequence[Dict[str, Any]]] = None
                     ) -> List[Dict[str, Any]]:
    if ledger is None:
        ledger = load_ledger()
    settled = _dedup_settled(ledger)
    return [r for r in settled
            if _channel_of(r) == channel and _is_measurable(r)]


def _unit_result(row: Dict[str, Any]) -> Optional[float]:
    try:
        return float(row["unit_result"])
    except (KeyError, TypeError, ValueError):
        return None


def _record(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    w = l = p = 0
    units = 0.0
    for r in rows:
        ur = _unit_result(r)
        if ur is None:
            continue
        units += ur
        if ur > 0:
            w += 1
        elif ur < 0:
            l += 1
        else:
            p += 1
    return {"wins": w, "losses": l, "pushes": p, "net_units": round(units, 3)}


def _close_implied_expectation(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Poisson-binomial normal-approx expected wins + close-implied expected
    units, both driven by each row's own fair_close_prob (the devigged
    probability, AT THE CLOSE, of the side actually taken). Never raises;
    rows missing fair_close_prob/taken_decimal/stake_units are skipped.
    """
    exp_wins = var_wins = 0.0
    exp_units = var_units = 0.0
    n_used = 0
    for r in rows:
        try:
            p = float(r["fair_close_prob"])
            dec = float(r["taken_decimal"])
            stake = float(r.get("stake_units", 1.0))
        except (KeyError, TypeError, ValueError):
            continue
        if not (0.0 < p < 1.0) or dec <= 1.0:
            continue
        n_used += 1
        exp_wins += p
        var_wins += p * (1.0 - p)
        payoff_win = stake * (dec - 1.0)
        ev = p * payoff_win - (1.0 - p) * stake
        var = p * (1.0 - p) * (payoff_win + stake) ** 2
        exp_units += ev
        var_units += var
    return {
        "n_used": n_used,
        "exp_wins": round(exp_wins, 3),
        "se_wins": round(math.sqrt(var_wins), 3) if var_wins > 0 else None,
        "exp_units": round(exp_units, 3),
        "se_units": round(math.sqrt(var_units), 3) if var_units > 0 else None,
    }


def _zscore(realized: float, expected: float, se: Optional[float]) -> Optional[float]:
    if se is None or se <= 0.0:
        return None
    return round((realized - expected) / se, 3)


def _duplicate_close_pairs(rows: Sequence[Dict[str, Any]]) -> int:
    """Count of (home,away) closing-decimal pairs shared by >=2 DIFFERENT
    event_ids -- a transparency signal only (see module docstring); round
    American odds legitimately repeat across unrelated games.
    """
    by_pair: Dict[Any, set] = {}
    for r in rows:
        pair = (r.get("closing_decimal_home"), r.get("closing_decimal_away"))
        if pair[0] is None or pair[1] is None:
            continue
        by_pair.setdefault(pair, set()).add(str(r.get("event_id") or ""))
    return sum(1 for eids in by_pair.values() if len(eids) > 1)


def _verdict(n: int, z_wins: Optional[float], z_units: Optional[float]) -> str:
    if n < _MIN_N:
        return ("INSUFFICIENT_DATA -- only %d measurable bets; too few to "
                "distinguish variance from a real close-capture problem "
                "(need >= %d)." % (n, _MIN_N))
    zs = [z for z in (z_wins, z_units) if z is not None]
    if not zs:
        return "INSUFFICIENT_DATA -- close-implied expectation not computable."
    worst = max(zs, key=abs)
    if abs(worst) < _Z_SIG:
        return ("GENUINE_VARIANCE -- realized record is within the 95%% band of "
                "what the close-implied probabilities themselves predict "
                "(max |z|=%.2f). The CLV-vs-record gap is ordinary sampling "
                "noise at this n, not evidence the close is stale/fabricated."
                % abs(worst))
    direction = "WORSE" if worst < 0 else "BETTER"
    return ("DIVERGENT -- realized record is %s than close-implied at 95%% "
            "confidence (max |z|=%.2f). Not proof of a bad close (could still "
            "be variance at small n, or a genuine calibration issue), but "
            "worth a closer audit of the close-capture mechanism before "
            "trusting the CLV number." % (direction, abs(worst)))


def reconcile_channel(channel: str,
                       ledger: Optional[Sequence[Dict[str, Any]]] = None
                      ) -> Dict[str, Any]:
    """Pure (no I/O beyond the ledger read). Returns the full reconciliation report."""
    rows = _measurable_rows(channel, ledger)
    n = len(rows)
    rec = _record(rows)
    clv_ci = _mean_ci([float(r["clv_pct"]) for r in rows if r.get("clv_pct") is not None])
    exp = _close_implied_expectation(rows)
    z_wins = _zscore(rec["wins"], exp["exp_wins"], exp["se_wins"])
    z_units = _zscore(rec["net_units"], exp["exp_units"], exp["se_units"])
    dup_pairs = _duplicate_close_pairs(rows)
    return {
        "channel": channel,
        "label": _CHANNEL_LABEL.get(channel, channel),
        "n_measurable": n,
        "record": rec,
        "mean_clv_pct": clv_ci["mean"],
        "clv_ci95": [clv_ci["lo95"], clv_ci["hi95"]],
        "clv_significant": clv_ci["significant"],
        "close_implied": exp,
        "z_wins": z_wins,
        "z_units": z_units,
        "duplicate_close_pairs_diff_event": dup_pairs,
        "verdict": _verdict(n, z_wins, z_units),
    }


def render(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 78)
    lines.append("CLV RESULT RECONCILER -- %s (n=%d measurable)"
                 % (report["label"], report["n_measurable"]))
    lines.append("=" * 78)
    rec = report["record"]
    lines.append("realized: %d-%d-%d, net %+.2fu   mean CLV %s%s"
                 % (rec["wins"], rec["losses"], rec["pushes"], rec["net_units"],
                    ("%+.2f%%" % report["mean_clv_pct"]) if report["mean_clv_pct"] is not None else "--",
                    "*" if report["clv_significant"] else ""))
    exp = report["close_implied"]
    lines.append("close-implied expectation (from each bet's own fair_close_prob):")
    lines.append("  wins  exp=%s  se=%s  z=%s"
                 % (exp["exp_wins"], exp["se_wins"], report["z_wins"]))
    lines.append("  units exp=%s  se=%s  z=%s"
                 % (exp["exp_units"], exp["se_units"], report["z_units"]))
    if report["duplicate_close_pairs_diff_event"]:
        lines.append("note: %d closing-price pair(s) shared across different events "
                     "(commonly just round American odds repeating -- glance, don't "
                     "assume a bug)." % report["duplicate_close_pairs_diff_event"])
    lines.append("")
    lines.append("VERDICT: " + report["verdict"])
    lines.append("=" * 78)
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None, out_dir: Optional[str] = None) -> int:
    """Default (no argv): ALWAYS reconciles + writes every KNOWN_CHANNELS entry
    (E-check-3 build-wave extension) so a downstream trust check never sees a
    missing file for a known channel. Passing explicit channel args on argv
    still reconciles exactly those (manual/ad-hoc CLI use unchanged).
    """
    argv = list(argv if argv is not None else sys.argv[1:])
    channels = argv or list(KNOWN_CHANNELS)
    out_dir = out_dir or _OUT_DIR
    ledger = load_ledger()
    os.makedirs(out_dir, exist_ok=True)
    for ch in channels:
        report = reconcile_channel(ch, ledger)
        print(render(report))
        out_path = os.path.join(out_dir, "clv_reconcile_%s.json" % ch)
        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=1)
            print("wrote %s\n" % out_path)
        except OSError as exc:
            print("(reconcile JSON not written: %s)\n" % type(exc).__name__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
