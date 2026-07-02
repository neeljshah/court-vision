"""scripts.platformkit.paper.pnl_progress -- "is paper EXECUTION making money and
getting BETTER at winning?" (realized units P&L + win-rate + CLV TREND).

The realized-money companion to clv.model_progress (which tracks calibration). It
reuses pnl_series.collect_settled (time-ordered, flat-1-unit, ONE position per market
= the model's best/+EV side) and grade_paper_summary.grade_bucket (win/units/CLV, with
the off-market suspect guard), then splits the settled timeline into an EARLIER half and
a RECENT half and asks two honest questions separately:

  1. ARE WE MAKING MONEY?  -> net units over the whole paper sample (descriptive, units,
     paper -- executed=False, never $). Positive net units is a paper track record, NOT a
     proven edge; it is high-variance until CLV confirms it.
  2. ARE WE GETTING BETTER AT WINNING?  -> the TREND verdict, ANCHORED ON CLV. CLV
     (better-number-than-close) is the only durable predictor of long-run profit, so a
     genuine "getting better" call REQUIRES recent CLV to be positive AND higher than
     earlier CLV. A rising win-rate / units curve WITHOUT a CLV rise is labelled
     "variance, not yet signal" -- the CLV-over-ROI discipline, enforced in code.

HONESTY (binding): UNITS ONLY -- no $ / pnl / roi field. edge_claimed=False; real money
stays default-DENY. Small windows -> INSUFFICIENT_DATA, never a fabricated verdict. CLV
excludes off-market/misparsed rows (clv_ledger.is_clv_suspect) so a corrupt taken price
cannot manufacture a fake +CLV trend.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets; no
$-edge claim; no flag flip; no real-money path.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/paper/test_pnl_progress.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit.grade_paper_summary import grade_bucket
from scripts.platformkit.paper import pnl_series as _series

# A window needs at least this many DECIDED (win/loss) bets before its win-rate/units
# mean is reported, and this many TRUE-CLOSE CLV rows before a CLV trend is trusted.
# Below these, the window is INSUFFICIENT_DATA (honest, not a failure).
MIN_DECIDED_PER_WINDOW = 8
MIN_CLV_PER_WINDOW = 5
# CLV must move by more than this (percentage points) to count as a real change rather
# than noise -- a deliberately conservative dead-band so tiny wiggles read as FLAT.
_CLV_TREND_TOL = 0.5


def _units_per_bet(bucket: Dict[str, Any]) -> Optional[float]:
    """Net units divided by priced bets -- the realized money RATE for a window."""
    n = bucket.get("n_priced_units") or 0
    nu = bucket.get("net_units")
    if not n or nu is None:
        return None
    return round(float(nu) / n, 6)


def _window_view(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-window realized view: win-rate, net units, units/bet, CLV (suspect-guarded)."""
    b = grade_bucket(list(rows))
    enough = (b["n_decided"] or 0) >= MIN_DECIDED_PER_WINDOW
    enough_clv = (b["n_with_clv"] or 0) >= MIN_CLV_PER_WINDOW
    return {
        "n_total": b["n_total"],
        "n_decided": b["n_decided"],
        "win_rate_pct": b["hit_rate"] if enough else None,
        "net_units": b["net_units"],
        "units_per_bet": _units_per_bet(b) if enough else None,
        "n_with_clv": b["n_with_clv"],
        "mean_clv_pct": b["mean_clv_pct"] if enough_clv else None,
        "pct_beat_close": b["pct_beat_close"] if enough_clv else None,
        "clv_trustworthy": enough_clv,
    }


def _trend_verdict(earlier: Dict[str, Any], recent: Dict[str, Any]) -> str:
    """The getting-better-at-winning verdict, ANCHORED ON CLV (durable), not units."""
    ec, rc = earlier.get("mean_clv_pct"), recent.get("mean_clv_pct")
    if not (earlier.get("clv_trustworthy") and recent.get("clv_trustworthy")):
        # No trustworthy CLV in both halves -> the only honest read is the units curve,
        # which is variance, not a getting-better signal.
        nu_e, nu_r = earlier.get("units_per_bet"), recent.get("units_per_bet")
        if nu_e is None or nu_r is None:
            return ("INSUFFICIENT_DATA -- not enough settled bets (or no captured closes) "
                    "to say whether execution is getting better. Keep settling.")
        direction = "up" if nu_r > nu_e else "down" if nu_r < nu_e else "flat"
        return ("units/bet is %s recent-vs-earlier, but with too few captured closing "
                "lines this is VARIANCE, not a getting-better signal. CLV (the durable "
                "yardstick) is not yet measurable -- capture more closes." % direction)
    d = round(rc - ec, 6)
    if rc > 0.0 and d > _CLV_TREND_TOL:
        return ("GETTING BETTER -- recent CLV %.2f%% is POSITIVE and higher than earlier "
                "%.2f%% (+%.2fpp). This is the real signal: beating the close more, which "
                "is what makes paper units durable. Keep ratcheting." % (rc, ec, d))
    if d < -_CLV_TREND_TOL and rc < ec:
        return ("DECLINING -- recent CLV %.2f%% is below earlier %.2f%% (%.2fpp). Taking "
                "worse numbers than before; tighten the gate / fix price-capture timing."
                % (rc, ec, d))
    return ("FLAT -- CLV %.2f%% recent vs %.2f%% earlier is within noise (+/-%.1fpp). Not "
            "yet distinguishable from holding steady at the close." % (rc, ec, _CLV_TREND_TOL))


def progress(settled: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Build the realized money + getting-better-at-winning report. Pure given *settled*.

    *settled* defaults to pnl_series.collect_settled() (the canonical time-ordered,
    flat-unit, one-position-per-market paper set). UNITS ONLY; never raises on an empty
    ledger (returns an honest INSUFFICIENT_DATA shape).
    """
    rows = list(settled) if settled is not None else _series.collect_settled()
    overall = grade_bucket(rows)
    half = len(rows) // 2
    earlier = _window_view(rows[:half])
    recent = _window_view(rows[half:])
    net = overall.get("net_units")
    making_money = (
        "INSUFFICIENT_DATA -- no priced settled bets yet." if net is None else
        ("YES (paper, units): net %+.2f u over %d bets -- a paper track record, NOT a "
         "proven edge (high-variance until CLV confirms)." % (net, overall["n_priced_units"]))
        if net > 0 else
        ("NOT YET (paper, units): net %+.2f u over %d bets. Markets are efficient; profit "
         "comes only from positive CLV, which is the lever to push." % (net, overall["n_priced_units"]))
    )
    return {
        "n_settled": overall["n_total"],
        "net_units": net,
        "win_rate_pct": overall["hit_rate"],
        "mean_clv_pct": overall["mean_clv_pct"],
        "n_with_clv": overall["n_with_clv"],
        "n_clv_suspect_excluded": overall.get("n_clv_suspect_excluded", 0),
        "earlier": earlier,
        "recent": recent,
        "making_money": making_money,
        "getting_better": _trend_verdict(earlier, recent),
        "edge_claimed": False,
        "executed": False,
        "honest_note": (
            "Paper UNITS only (executed=False, no $). 'Making money' is descriptive over a "
            "small-N paper sample; 'getting better' is anchored on CLV (the durable "
            "predictor) -- a rising units curve without rising CLV is variance, not edge."),
    }


def render(p: Dict[str, Any]) -> str:
    """ASCII render of the realized money + getting-better report."""
    L: List[str] = []
    L.append("=" * 78)
    L.append("IS PAPER EXECUTION MAKING MONEY + GETTING BETTER AT WINNING? (units, no $)")
    L.append("=" * 78)
    L.append("settled=%d  net=%s u  win_rate=%s%%  mean_clv=%s%%  (clv n=%s, suspect_excl=%s)"
             % (p["n_settled"],
                ("%+.2f" % p["net_units"]) if p["net_units"] is not None else "--",
                p["win_rate_pct"] if p["win_rate_pct"] is not None else "--",
                p["mean_clv_pct"] if p["mean_clv_pct"] is not None else "--",
                p["n_with_clv"], p["n_clv_suspect_excluded"]))
    L.append("")
    hdr = "%-9s %6s %8s %10s %9s %8s" % ("window", "dec", "win%", "units/bet",
                                         "meanCLV%", "beat%")
    L.append(hdr)
    L.append("-" * 78)
    for name, w in (("earlier", p["earlier"]), ("recent", p["recent"])):
        L.append("%-9s %6s %8s %10s %9s %8s" % (
            name, w["n_decided"],
            w["win_rate_pct"] if w["win_rate_pct"] is not None else "--",
            w["units_per_bet"] if w["units_per_bet"] is not None else "--",
            w["mean_clv_pct"] if w["mean_clv_pct"] is not None else "--",
            w["pct_beat_close"] if w["pct_beat_close"] is not None else "--"))
    L.append("-" * 78)
    L.append("MAKING MONEY?   " + p["making_money"])
    L.append("GETTING BETTER? " + p["getting_better"])
    L.append("=" * 78)
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:  # pragma: no cover -- thin CLI
    print(render(progress()))
    return 0


__all__ = ["progress", "render", "main", "MIN_DECIDED_PER_WINDOW", "MIN_CLV_PER_WINDOW"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
