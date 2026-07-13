"""clv_scoreboard -- the per-channel CLV truth table (the only honest edge yardstick).

Accuracy is not edge. The single question that decides whether a betting channel
has edge is: do we beat the price we can actually transact at, out-of-sample? In
betting that is CLOSING LINE VALUE (CLV). Positive CLV => +EV by construction;
non-positive CLV => no edge, no matter the win rate.

This module reads the paper CLV ledger and prints a PER-CHANNEL scoreboard that
honestly separates:

  * MEASURABLE bets  -- clv_status == 'true_close' with a real closing line. For
    these we report mean CLV %, % that beat the close, and a 95% CI so you can see
    whether mean CLV is statistically distinguishable from zero (small n => "not
    yet provable", which is the honest verdict, not a failure).
  * UN-MEASURABLE bets -- props / markets with NO closing line captured
    (clv_status == 'no_close'). We can only report win/loss + units, which is
    high-variance bookkeeping, NOT an edge measurement. The COVERAGE column shows
    what fraction of a channel is even measurable -- the headline gap to close.

Rows are deduped by bet_id (re-grades / archive twins collapse). Reuses the
canonical clv_ledger reader + math; never claims a dollar edge; ASCII only.

Run:  python -m scripts.platformkit.clv.clv_scoreboard
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

from scripts.platformkit.clv_ledger import (  # canonical reader + suspect guard
    is_clv_suspect, load_ledger)
# W1 fix: read-time historical recovery + the SEPARATE kx-proxy measurable tier
# for paper_ingame rows (never merged into the true_close 'measurable' bucket).
from scripts.platformkit.clv.kx_close_math import (
    enrich_paper_ingame_no_close, is_measurable_proxy)
from scripts.platformkit.clv.clv_quarantine import (
    quarantined_bet_ids, split_quarantined)

# Friendly channel labels; an absent channel that still carries a closing line is
# the legacy game-moneyline book (the '?' rows).
_CHANNEL_LABEL = {
    "paper": "pregame props",
    "paper_pm": "Kalshi/PM game",
    "paper_ingame_prop": "in-game props",
    "paper_ingame": "in-game ML",
    "moneyline": "game moneyline",
}

_OUT_JSON = os.path.join(
    _REPO, "data", "frontend", "ops", "clv_scoreboard.json")


def _channel_of(row: Dict[str, Any]) -> str:
    ch = row.get("channel")
    if ch:
        return str(ch)
    # No channel tag but a real closing line => legacy game-moneyline.
    if row.get("closing_decimal_home") is not None:
        return "moneyline"
    return "unknown"


def _is_measurable(row: Dict[str, Any]) -> bool:
    # An off-market / misparsed taken price fabricates a fake CLV -> it is NOT a
    # measurable edge row (it would dishonestly inflate the channel mean, e.g. a
    # "taken" 12.0 on a pick'em close -> +497%). Excluded here so the scoreboard
    # mirrors clv_ledger.clv_summary's suspect filter.
    return (row.get("clv_status") == "true_close"
            and row.get("clv_pct") is not None
            and not is_clv_suspect(row))


def _dedup_settled(ledger: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the latest settled row per bet_id (collapses re-grades / archive twins)."""
    best: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for r in ledger:
        if r.get("status") != "settled":
            continue
        key = str(r.get("bet_id") or r.get("settle_key") or id(r))
        if key not in best:
            order.append(key)
        # latest settled_at wins
        cur = best.get(key)
        if cur is None or str(r.get("settled_at") or "") >= str(cur.get("settled_at") or ""):
            best[key] = r
    return [best[k] for k in order]


def _mean_ci(values: Sequence[float]) -> Dict[str, Optional[float]]:
    """Mean + 95% CI (normal approx) + a 'significant' flag (CI excludes 0)."""
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": None, "se": None, "lo95": None, "hi95": None,
                "significant": False}
    mean = sum(values) / n
    if n == 1:
        return {"n": 1, "mean": round(mean, 4), "se": None, "lo95": None,
                "hi95": None, "significant": False}
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    se = math.sqrt(var / n)
    lo, hi = mean - 1.96 * se, mean + 1.96 * se
    return {"n": n, "mean": round(mean, 4), "se": round(se, 4),
            "lo95": round(lo, 4), "hi95": round(hi, 4),
            "significant": (lo > 0.0 or hi < 0.0)}


def _wlp_units(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    w = l = p = 0
    units = 0.0
    for r in rows:
        ur = r.get("unit_result")
        try:
            ur = float(ur)
        except (TypeError, ValueError):
            continue
        units += ur
        if ur > 0:
            w += 1
        elif ur < 0:
            l += 1
        else:
            p += 1
    return {"wins": w, "losses": l, "pushes": p, "net_units": round(units, 2)}


def scoreboard(ledger: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Build the per-channel CLV scoreboard dict (pure; no printing/I-O)."""
    if ledger is None:
        ledger = load_ledger()
    settled = _dedup_settled(ledger)
    # Quarantine adjudication (EXCLUDE-FROM-AGGREGATES rows only, fail-open
    # otherwise) -- dropped here, counted, never silently vanished.
    settled, n_excluded_quarantined = split_quarantined(settled, quarantined_bet_ids())
    # W1 fix: read-time recovery ONLY for paper_ingame rows still labelled
    # no_close -- every other row (wrong channel/status, or a genuine miss)
    # passes through byte-identical. Never mutates the ledger on disk.
    settled = [enrich_paper_ingame_no_close(r) for r in settled]

    by_ch: Dict[str, Dict[str, Any]] = {}
    for r in settled:
        ch = _channel_of(r)
        b = by_ch.setdefault(
            ch, {"rows": [], "measurable": [], "measurable_proxy": [], "n_suspect": 0})
        b["rows"].append(r)
        if is_clv_suspect(r):
            b["n_suspect"] += 1          # off-market line: counted, never measured
        if _is_measurable(r):
            b["measurable"].append(r)
        elif is_measurable_proxy(r):     # SEPARATE tier -- never both (statuses differ)
            b["measurable_proxy"].append(r)

    channels: Dict[str, Any] = {}
    tot_settled = tot_measurable = tot_suspect = tot_measurable_proxy = 0
    for ch, b in by_ch.items():
        rows, meas, proxy = b["rows"], b["measurable"], b["measurable_proxy"]
        tot_settled += len(rows)
        tot_measurable += len(meas)
        tot_measurable_proxy += len(proxy)
        tot_suspect += b["n_suspect"]
        clvs = [float(m["clv_pct"]) for m in meas]
        ci = _mean_ci(clvs)
        beats = sum(1 for c in clvs if c > 0.0)
        clvs_proxy = [float(m["clv_pct"]) for m in proxy]
        ci_proxy = _mean_ci(clvs_proxy)
        beats_proxy = sum(1 for c in clvs_proxy if c > 0.0)
        channels[ch] = {
            "label": _CHANNEL_LABEL.get(ch, ch),
            "n_settled": len(rows),
            "n_measurable": len(meas),
            "n_suspect_excluded": b["n_suspect"],
            "coverage_pct": round(100.0 * len(meas) / len(rows), 1) if rows else 0.0,
            "mean_clv_pct": ci["mean"],
            "clv_ci95": [ci["lo95"], ci["hi95"]],
            "clv_significant": ci["significant"],
            "beat_close_pct": round(100.0 * beats / len(meas), 1) if meas else None,
            "record": _wlp_units(rows),
            # PROXY tier (kx-ticker last-tick close, W1 fix) -- honest-labels
            # discipline: NEVER merged into the true_close fields above.
            "n_measurable_proxy": len(proxy),
            "clv_proxy_pct": ci_proxy["mean"],
            "clv_proxy_ci95": [ci_proxy["lo95"], ci_proxy["hi95"]],
            "clv_proxy_significant": ci_proxy["significant"],
            "beat_close_proxy_pct": (round(100.0 * beats_proxy / len(proxy), 1)
                                     if proxy else None),
        }

    return {
        "total_settled": tot_settled,
        "total_measurable": tot_measurable,
        "total_measurable_proxy": tot_measurable_proxy,
        "total_suspect_excluded": tot_suspect,
        "n_excluded_quarantined": n_excluded_quarantined,
        "coverage_pct": (round(100.0 * tot_measurable / tot_settled, 1)
                         if tot_settled else 0.0),
        "channels": channels,
        "verdict": _overall_verdict(channels, tot_measurable, tot_settled),
    }


def _overall_verdict(channels: Dict[str, Any], n_meas: int, n_set: int) -> str:
    if n_set == 0:
        return "No settled bets yet -- nothing to measure."
    if n_meas == 0:
        return ("0 of %d settled bets are CLV-measurable: NO closing lines "
                "captured. Edge is unprovable until closing prices are recorded "
                "(props + PM have none)." % n_set)
    sig = [c for c in channels.values() if c["clv_significant"]]
    if not sig:
        return ("%d/%d bets measurable; no channel has a statistically "
                "significant CLV yet (need more closing-line data). Honest "
                "verdict: not yet provable." % (n_meas, n_set))
    pos = [c for c in sig if (c["mean_clv_pct"] or 0) > 0]
    if pos:
        return ("SIGNAL: %s show significant POSITIVE CLV -- candidate edge, keep "
                "measuring." % ", ".join(c["label"] for c in pos))
    return ("%d/%d measurable; significant channels are NEGATIVE CLV (taking worse "
            "than the close) -- anti-edge, fix price capture / timing."
            % (n_meas, n_set))


def render(board: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 78)
    lines.append("CLV SCOREBOARD -- the honest edge yardstick (units only, no $ claim)")
    lines.append("=" * 78)
    lines.append("settled=%d  measurable(true close)=%d  coverage=%.1f%%"
                 % (board["total_settled"], board["total_measurable"],
                    board["coverage_pct"]))
    if board.get("total_suspect_excluded"):
        lines.append("excluded %d off-market/misparsed row(s) from CLV (fabricated "
                     "edge guard)" % board["total_suspect_excluded"])
    if board.get("n_excluded_quarantined"):
        lines.append("excluded %d row(s) flagged EXCLUDE-FROM-AGGREGATES by "
                     "quarantine adjudication" % board["n_excluded_quarantined"])
    lines.append("")
    hdr = ("%-18s %5s %6s %8s %9s %7s  %s"
           % ("channel", "n", "meas", "covg%", "meanCLV%", "beat%", "W-L-P / units"))
    lines.append(hdr)
    lines.append("-" * 78)
    for ch in sorted(board["channels"], key=lambda c: -board["channels"][c]["n_settled"]):
        c = board["channels"][ch]
        rec = c["record"]
        clv = ("%+.2f" % c["mean_clv_pct"]) if c["mean_clv_pct"] is not None else "  --"
        if c["clv_significant"]:
            clv += "*"  # CI excludes 0
        beat = ("%.0f" % c["beat_close_pct"]) if c["beat_close_pct"] is not None else "--"
        lines.append("%-18s %5d %6d %7.0f %9s %7s  %d-%d-%d / %+.1fu"
                     % (c["label"], c["n_settled"], c["n_measurable"],
                        c["coverage_pct"], clv, beat,
                        rec["wins"], rec["losses"], rec["pushes"], rec["net_units"]))
        if c.get("n_measurable_proxy"):
            pclv = ("%+.2f" % c["clv_proxy_pct"]) if c["clv_proxy_pct"] is not None else "  --"
            if c["clv_proxy_significant"]:
                pclv += "*"
            lines.append("  |- proxy (kx last-tick, NOT true close): n=%d meanCLV%%=%s"
                         % (c["n_measurable_proxy"], pclv))
    lines.append("-" * 78)
    lines.append("* = mean CLV 95%% CI excludes 0 (statistically distinguishable).")
    lines.append("meanCLV/beat%% shown ONLY for measurable bets; '--' = no closing "
                 "line (win/loss only, NOT an edge signal).")
    lines.append("")
    lines.append("VERDICT: " + board["verdict"])
    lines.append("=" * 78)
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    board = scoreboard()
    print(render(board))
    try:
        os.makedirs(os.path.dirname(_OUT_JSON), exist_ok=True)
        with open(_OUT_JSON, "w", encoding="utf-8") as fh:
            json.dump(board, fh, indent=1)
        print("\nwrote %s" % _OUT_JSON)
    except OSError as exc:
        print("(scoreboard JSON not written: %s)" % type(exc).__name__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
