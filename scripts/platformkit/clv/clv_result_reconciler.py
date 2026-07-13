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
# W1 fix: SEPARATE kx-proxy measurable tier, never merged into true_close.
from scripts.platformkit.clv.kx_close_math import (
    enrich_paper_ingame_no_close, is_measurable_proxy)
from scripts.platformkit.clv.clv_quarantine import (
    quarantined_bet_ids, split_quarantined)

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


def _measurable_proxy_rows(channel: str, ledger: Optional[Sequence[Dict[str, Any]]] = None
                           ) -> List[Dict[str, Any]]:
    """W1 fix: the SEPARATE kx-proxy measurable tier for one channel (never
    merged into _measurable_rows' true_close set). Applies the same read-
    time historical recovery clv_scoreboard.scoreboard() does for paper_ingame
    rows still labelled no_close."""
    if ledger is None:
        ledger = load_ledger()
    settled = [enrich_paper_ingame_no_close(r) for r in _dedup_settled(ledger)]
    return [r for r in settled
            if _channel_of(r) == channel and is_measurable_proxy(r)]


def _label_proxy(verdict: str) -> str:
    """Stamp a verdict string's leading token with _PROXY (e.g. 'DIVERGENT'
    -> 'DIVERGENT_PROXY') -- honest-labels discipline for the kx-proxy tier."""
    head, sep, rest = verdict.partition(" -- ")
    return (head + "_PROXY" + sep + rest) if sep else (verdict + "_PROXY")


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


def _single_side(rows: Sequence[Dict[str, Any]]
                 ) -> "tuple[List[Dict[str, Any]], int]":
    """Collapse to one row/event_id (keep first-taken side, input order) +
    count events with >=2 rows (both sides taken -- anti-correlated, not
    independent). No-event_id rows are each their own singleton.
    """
    counts: Dict[Any, int] = {}
    for r in rows:
        eid = r.get("event_id")
        if eid is not None:
            counts[eid] = counts.get(eid, 0) + 1
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for r in rows:
        eid = r.get("event_id")
        if eid is not None and eid in seen:
            continue
        if eid is not None:
            seen.add(eid)
        out.append(r)
    both_pairs = sum(1 for c in counts.values() if c > 1)
    return out, both_pairs


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


# A prediction-market venue (Kalshi/Polymarket). A row taken here whose close was
# NOT resolved from the SAME venue is a cross-venue BASIS row: clv_pct then measures
# the price gap between where you bet (Kalshi/PM) and a different-venue devigged close
# (e.g. a sportsbook line via line_store), which is basis, not a beaten line. Same-
# venue closes carry close_source/close_venue tagged kalshi/poly (pm_close_capture).
# See reference memory 'cross-venue CLV = basis not edge' + the PROPOSED same-venue
# close restriction. Additive/read-only: does NOT touch the verdict or z-scores.
_PM_VENUE_TOKENS = ("kalshi", "polymarket", "poly", "pm")


def _is_pm_taken(row: Dict[str, Any]) -> bool:
    if row.get("is_pm"):
        return True
    for k in ("venue", "taken_book", "book"):
        v = str(row.get(k) or "").lower()
        if any(tok in v for tok in _PM_VENUE_TOKENS):
            return True
    return False


def _is_same_venue_close(row: Dict[str, Any]) -> bool:
    for k in ("close_source", "close_venue"):
        v = str(row.get(k) or "").lower()
        if "kalshi" in v or "poly" in v:
            return True
    return False


def _cross_venue_basis(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Count measurable rows taken on a PM venue but priced against a DIFFERENT-
    venue close -- for those, clv_pct is basis, not a beaten line. Transparency
    only; never alters the verdict/z. books = the different-venue close origin.
    """
    cross = [r for r in rows if _is_pm_taken(r) and not _is_same_venue_close(r)]
    n = len(cross)
    books: Dict[str, int] = {}
    for r in cross:
        b = str(r.get("close_book_home") or r.get("close_source") or "unknown")
        books[b] = books.get(b, 0) + 1
    clvs = [float(r["clv_pct"]) for r in cross if r.get("clv_pct") is not None]
    note = None
    if n:
        note = ("%d of %d measurable rows were taken on a prediction-market venue "
                "but priced against a DIFFERENT-venue close (%s) -- for these, "
                "clv_pct is cross-venue BASIS, not a beaten line. Read the channel "
                "CLV as basis, not edge." % (
                    n, len(rows),
                    ", ".join("%s:%d" % kv for kv in sorted(books.items()))))
    return {
        "n": n,
        "n_measurable": len(rows),
        "mean_clv_pct": (round(sum(clvs) / len(clvs), 4) if clvs else None),
        "books": books,
        "note": note,
    }


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


def _proxy_block(proxy_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Same reconciliation math as the true_close tier, applied to the
    SEPARATE kx-proxy measurable rows -- every output key/verdict PROXY-
    labelled (honest-labels discipline, W1 fix)."""
    n = len(proxy_rows)
    rec = _record(proxy_rows)
    clv_ci = _mean_ci([float(r["clv_pct"]) for r in proxy_rows if r.get("clv_pct") is not None])
    exp = _close_implied_expectation(proxy_rows)
    z_wins = _zscore(rec["wins"], exp["exp_wins"], exp["se_wins"])
    z_units = _zscore(rec["net_units"], exp["exp_units"], exp["se_units"])
    return {
        "n_measurable_proxy": n,
        "record": rec,
        "clv_proxy_pct": clv_ci["mean"],
        "clv_proxy_ci95": [clv_ci["lo95"], clv_ci["hi95"]],
        "clv_proxy_significant": clv_ci["significant"],
        "close_implied": exp,
        "z_wins": z_wins,
        "z_units": z_units,
        "verdict": _label_proxy(_verdict(n, z_wins, z_units)),
    }


def reconcile_channel(channel: str,
                       ledger: Optional[Sequence[Dict[str, Any]]] = None
                      ) -> Dict[str, Any]:
    """Pure (no I/O beyond the ledger read). Returns the full reconciliation report."""
    rows = _measurable_rows(channel, ledger)
    quarantined = quarantined_bet_ids()
    rows, n_excl_true = split_quarantined(rows, quarantined)
    n = len(rows)
    rec = _record(rows)
    clv_ci = _mean_ci([float(r["clv_pct"]) for r in rows if r.get("clv_pct") is not None])
    exp = _close_implied_expectation(rows)
    z_wins = _zscore(rec["wins"], exp["exp_wins"], exp["se_wins"])
    z_units = _zscore(rec["net_units"], exp["exp_units"], exp["se_units"])
    dup_pairs = _duplicate_close_pairs(rows)

    ss_rows, both_pairs = _single_side(rows)  # additive; never alters verdict above
    ss_n = len(ss_rows)
    ss_rec = _record(ss_rows)
    ss_exp = _close_implied_expectation(ss_rows)
    single_side = {
        "n": ss_n,
        "z_wins": _zscore(ss_rec["wins"], ss_exp["exp_wins"], ss_exp["se_wins"]),
        "z_units": _zscore(ss_rec["net_units"], ss_exp["exp_units"], ss_exp["se_units"]),
        "both_sides_pairs": both_pairs,
        "note": ("%d event(s) had both sides taken as the line moved -- those "
                 "rows are anti-correlated, not independent; single_side "
                 "collapses each to its first-taken side before z-scoring."
                 % both_pairs) if both_pairs > 0 else None,
    }

    # W1 fix: SEPARATE kx-proxy tier, computed for every channel (cheap; most
    # channels have zero proxy rows). paper_ingame's TOP-LEVEL verdict may
    # fall back to it (PROXY-labelled) only when the true_close tier has too
    # few rows to say anything -- every other channel's verdict stays exactly
    # as before.
    proxy_rows = _measurable_proxy_rows(channel, ledger)
    proxy_rows, n_excl_proxy = split_quarantined(proxy_rows, quarantined)
    clv_proxy = _proxy_block(proxy_rows)
    verdict = _verdict(n, z_wins, z_units)
    if (channel == "paper_ingame" and n < _MIN_N
            and clv_proxy["n_measurable_proxy"] >= _MIN_N):
        verdict = clv_proxy["verdict"]

    return {
        "channel": channel,
        "label": _CHANNEL_LABEL.get(channel, channel),
        "n_measurable": n,
        "n_excluded_quarantined": n_excl_true + n_excl_proxy,
        "record": rec,
        "mean_clv_pct": clv_ci["mean"],
        "clv_ci95": [clv_ci["lo95"], clv_ci["hi95"]],
        "clv_significant": clv_ci["significant"],
        "close_implied": exp,
        "z_wins": z_wins,
        "z_units": z_units,
        "duplicate_close_pairs_diff_event": dup_pairs,
        "verdict": verdict,
        "single_side": single_side,
        "cross_venue_basis": _cross_venue_basis(rows),
        "clv_proxy": clv_proxy,
    }


def render(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 78)
    lines.append("CLV RESULT RECONCILER -- %s (n=%d measurable)"
                 % (report["label"], report["n_measurable"]))
    lines.append("=" * 78)
    if report.get("n_excluded_quarantined"):
        lines.append("excluded %d row(s) flagged EXCLUDE-FROM-AGGREGATES by "
                     "quarantine adjudication" % report["n_excluded_quarantined"])
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
    ss = report["single_side"]
    if ss.get("note"):
        lines.append("note: %s (single_side: n=%s z_wins=%s z_units=%s)"
                     % (ss["note"], ss["n"], ss["z_wins"], ss["z_units"]))
    cvb = report.get("cross_venue_basis") or {}
    if cvb.get("note"):
        lines.append("BASIS: %s (cross-venue mean CLV %s%%)"
                     % (cvb["note"],
                        ("%+.2f" % cvb["mean_clv_pct"]) if cvb.get("mean_clv_pct") is not None else "--"))
    cp = report.get("clv_proxy") or {}
    if cp.get("n_measurable_proxy"):
        pclv = ("%+.2f%%" % cp["clv_proxy_pct"]) if cp["clv_proxy_pct"] is not None else "--"
        lines.append("PROXY (kx last-tick, NOT true close): n=%d meanCLV=%s  verdict=%s"
                     % (cp["n_measurable_proxy"], pclv, cp["verdict"]))
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
