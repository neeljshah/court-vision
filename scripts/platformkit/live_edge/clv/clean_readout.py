"""scripts.platformkit.live_edge.clv.clean_readout -- the FIRST honest same-book
CLV verdict on the real accumulated paper ledger (data/frontend/clv_ledger.jsonl).

Answers the only real "am-I-better" question: do our paper bets beat the close,
same book, out of sample? Headline = clv_status=='true_close' rows ONLY (a real
closing line captured on the SAME book the bet was taken at -- see
grade_paper_one.py:132 and clv_ledger.is_clv_suspect for what filters that status).
proxy (kx last-tick) and no_close rows are EXCLUDED from the headline and reported
only as counts -- cross-venue/proxy CLV is basis, not edge (reference_crossvenue_
clv_basis_2026_07_06).

REUSES, never re-derives:
  * scripts.platformkit.clv_ledger.load_ledger / is_clv_suspect -- the canonical
    reader + the off-market-price guard, and the clv_pct field itself (already
    computed there as (fair_close - taken_p) / taken_p * 100, i.e. CLV in
    percent-of-price UNITS -- never a $/ROI/bankroll figure).
  * scripts.platformkit.clv.clv_scoreboard._dedup_settled -- collapse re-grade /
    archive twins to one row per bet_id (the same dedup the live scoreboard uses).
  * scripts.platformkit.live_edge.clv.clv_trial.clv_distribution / verdict_label --
    the median/IQR/bootstrap-CI math and the AHEAD/PAR/BEHIND labelling, so this
    module only wires real rows into machinery that already exists.

edge_claimed is always False. This is a CLV READOUT, not an edge claim -- it is
PROVISIONAL until an explicit edge_greenlight elsewhere in the repo says otherwise.
An honest PAR / no-clean-edge verdict is a SUCCESS, reported plainly.

ASCII only; stdlib only; <=300 LOC; read-only against clv_ledger.jsonl; never
writes the claims journal.

Run:  python -m scripts.platformkit.live_edge.clv.clean_readout
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.clv_ledger import is_clv_suspect, load_ledger
from scripts.platformkit.clv.clv_scoreboard import _dedup_settled
from scripts.platformkit.live_edge.clv.clv_trial import (clv_distribution,
                                                          verdict_label)

Row = Dict[str, Any]

_OUT_MD = os.path.join(_REPO, "data", "omni", "live_edge", "clv",
                        "CLEAN_CLV_READOUT.md")


def _breakdown(settled: Sequence[Row]) -> Dict[str, Any]:
    """Same-book vs proxy vs no_close, with suspect rows split out of true_close
    so the honesty of the headline is visible at a glance."""
    true_close = [r for r in settled if r.get("clv_status") == "true_close"]
    proxy = [r for r in settled if r.get("clv_status") == "proxy"]
    no_close = [r for r in settled if r.get("clv_status") == "no_close"]
    other = [r for r in settled
             if r.get("clv_status") not in ("true_close", "proxy", "no_close")]
    suspect = [r for r in true_close if is_clv_suspect(r)]
    clean = [r for r in true_close if not is_clv_suspect(r)]
    return {
        "n_settled": len(settled),
        "n_true_close": len(true_close),
        "n_suspect_excluded": len(suspect),
        "n_clean_same_book": len(clean),
        "n_proxy_excluded": len(proxy),
        "n_no_close_excluded": len(no_close),
        "n_other_status": len(other),
        "clean_rows": clean,
    }


def clean_readout(ledger: Sequence[Row] = None) -> Dict[str, Any]:
    """Build the clean same-book CLV readout dict (pure; no printing/I-O)."""
    if ledger is None:
        ledger = load_ledger()
    settled = _dedup_settled(ledger)
    bd = _breakdown(settled)
    clean = bd.pop("clean_rows")

    by_sport: Dict[str, List[Row]] = {}
    for r in clean:
        by_sport.setdefault(str(r.get("sport") or "unknown"), []).append(r)

    per_sport: Dict[str, Any] = {}
    for sport, rows in sorted(by_sport.items()):
        clvs = [float(r["clv_pct"]) for r in rows if r.get("clv_pct") is not None]
        dist = clv_distribution(clvs)
        per_sport[sport] = {
            "n": dist["n"],
            "median_clv_pct": dist["median"],
            "iqr_clv_pct": dist["iqr"],
            "mean_clv_pct": dist["mean"],
            "ci95_clv_pct": dist["ci95"],
            "verdict": verdict_label(tuple(dist["ci95"]), dist["n"]),
        }

    overall_clvs = [float(r["clv_pct"]) for r in clean if r.get("clv_pct") is not None]
    overall = clv_distribution(overall_clvs)
    return {
        "edge_claimed": False,
        "provisional": True,
        "breakdown": bd,
        "per_sport": per_sport,
        "overall": {
            "n": overall["n"],
            "median_clv_pct": overall["median"],
            "iqr_clv_pct": overall["iqr"],
            "mean_clv_pct": overall["mean"],
            "ci95_clv_pct": overall["ci95"],
            "verdict": verdict_label(tuple(overall["ci95"]), overall["n"]),
        },
        "note": ("Headline = clv_status=='true_close' AND NOT is_clv_suspect "
                 "(same-book close only). proxy + no_close rows are EXCLUDED "
                 "from every headline number and reported only as counts. "
                 "CLV is in clv_pct units (percent-of-price), never $/ROI/"
                 "bankroll. PROVISIONAL: not an edge claim until edge_greenlight."),
    }


def render(board: Dict[str, Any]) -> str:
    bd = board["breakdown"]
    lines: List[str] = []
    lines.append("# Clean Same-Book CLV Readout (PROVISIONAL, edge_claimed=False)")
    lines.append("")
    lines.append("Same-book CLV = the only real am-I-better measure on the paper "
                  "ledger. Headline is clv_status=='true_close' and NOT "
                  "is_clv_suspect ONLY; proxy/no_close are basis, not edge, and "
                  "are excluded here (counted below).")
    lines.append("")
    lines.append("## Honesty breakdown (settled bets, dedup by bet_id)")
    lines.append("")
    lines.append("| bucket | n |")
    lines.append("|---|---|")
    lines.append("| settled (deduped) | %d |" % bd["n_settled"])
    lines.append("| clv_status=true_close | %d |" % bd["n_true_close"])
    lines.append("| -- suspect (off-market price, excluded) | %d |"
                  % bd["n_suspect_excluded"])
    lines.append("| -- **clean same-book (headline)** | **%d** |"
                  % bd["n_clean_same_book"])
    lines.append("| clv_status=proxy (excluded, basis not edge) | %d |"
                  % bd["n_proxy_excluded"])
    lines.append("| clv_status=no_close (excluded, unmeasurable) | %d |"
                  % bd["n_no_close_excluded"])
    if bd["n_other_status"]:
        lines.append("| other/unlabeled status (excluded) | %d |"
                      % bd["n_other_status"])
    lines.append("")
    lines.append("## Per-sport clean same-book CLV (units = clv_pct, "
                  "percent-of-price; never $/ROI)")
    lines.append("")
    lines.append("| sport | n | median | IQR | mean | 95%% CI | verdict |")
    lines.append("|---|---|---|---|---|---|---|")
    for sport, s in board["per_sport"].items():
        lines.append("| %s | %d | %s | %s | %s | %s | %s |" % (
            sport, s["n"], s["median_clv_pct"], s["iqr_clv_pct"],
            s["mean_clv_pct"], s["ci95_clv_pct"], s["verdict"]))
    ov = board["overall"]
    lines.append("")
    lines.append("## Overall (all sports pooled, clean same-book)")
    lines.append("")
    lines.append("n=%d  median=%s  IQR=%s  mean=%s  95%% CI=%s  **verdict: %s**"
                  % (ov["n"], ov["median_clv_pct"], ov["iqr_clv_pct"],
                     ov["mean_clv_pct"], ov["ci95_clv_pct"], ov["verdict"]))
    lines.append("")
    lines.append("## What is NOT verified")
    lines.append("")
    lines.append("- Selection bias: these are the bets our own model chose to "
                  "flag/take, not a random sample of the market -- no external "
                  "control group.")
    lines.append("- proxy (%d) and no_close (%d) rows are real settled bets "
                  "excluded from CLV because we cannot prove same-book close -- "
                  "they are NOT folded into the headline in either direction."
                  % (bd["n_proxy_excluded"], bd["n_no_close_excluded"]))
    lines.append("- Sample size: per-sport n may be small (see table); "
                  "INSUFFICIENT_DATA verdicts mean literally that, not BEHIND.")
    lines.append("- PROVISIONAL: edge_claimed=False. A CLV readout is a "
                  "measurement, not an edge claim, until edge_greenlight.")
    for sport, s in board["per_sport"].items():
        if (s["median_clv_pct"] is not None and s["mean_clv_pct"] is not None
                and (s["median_clv_pct"] < 0) != (s["mean_clv_pct"] < 0)):
            lines.append("- %s: median and mean disagree in sign (median=%s, "
                          "mean=%s) -- the verdict is CI-on-mean per the shared "
                          "verdict_label gate, but a right-skewed distribution "
                          "(many small losses, occasional large wins) is driving "
                          "the positive mean; read the IQR, not just the verdict."
                          % (sport, s["median_clv_pct"], s["mean_clv_pct"]))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    board = clean_readout()
    md = render(board)
    os.makedirs(os.path.dirname(_OUT_MD), exist_ok=True)
    with open(_OUT_MD, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(md)
    print("\nwrote %s" % _OUT_MD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
