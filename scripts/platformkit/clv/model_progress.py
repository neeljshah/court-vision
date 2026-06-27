"""model_progress -- "are the models getting better?", measured honestly.

"Getting better" has a precise, two-axis meaning -- and BOTH must move:

  1. PREDICTION quality (calibration): is the model's probability sharpening?
     Tracked by the self-improve loop in improve_ledger.jsonl as Brier / ECE per
     sport over time, plus bss_vs_close (Brier Skill Score vs the market close --
     does the model PREDICT better than the closing line?).
  2. REALIZED edge (CLV): is the prediction turning into a better PRICE than the
     close? Tracked by clv_scoreboard. A model can predict well yet still lose to
     the close on PRICE (timing / not best-book) -- that is an execution problem,
     not a model one, and only the two axes together reveal it.

This reads the real improve ledger + the CLV scoreboard and prints one honest
per-sport readout: the calibration trend (first vs latest), the data gate (the
loop refuses to recalibrate on < ~60 settled games -- INSUFFICIENT_DATA is honest,
not failure), and the edge. No fabricated improvement; no dollar-edge claim.

Run:  python -m scripts.platformkit.clv.model_progress
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.clv.clv_scoreboard import scoreboard as clv_scoreboard

_IMPROVE_LEDGER = os.path.join(_REPO, "data", "frontend", "improve_ledger.jsonl")
_OUT_JSON = os.path.join(_REPO, "data", "frontend", "ops", "model_progress.json")

# The self-improve loop needs this many real settled games to recalibrate leak-free.
_MIN_SETTLED = 60


def _load_improve(path: str = _IMPROVE_LEDGER) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _real_metric_series(rows: Sequence[Dict[str, Any]], sport: str) -> List[Dict[str, Any]]:
    """Time-ordered improve entries for *sport* that carry a real Brier readout."""
    series = []
    for r in rows:
        if r.get("sport") != sport:
            continue
        rd = r.get("readout") or {}
        if rd.get("raw_brier") is None:
            continue
        series.append({"ts": r.get("ts", ""), **rd, "verdict": r.get("verdict")})
    series.sort(key=lambda x: x["ts"])
    return series


def _trend(first: Optional[float], last: Optional[float]) -> str:
    if first is None or last is None:
        return "n/a"
    d = last - first
    if abs(d) < 1e-4:
        return "flat"
    return "improving" if d < 0 else "worse"  # lower Brier/ECE is better


def _sport_progress(rows: Sequence[Dict[str, Any]], sport: str) -> Dict[str, Any]:
    series = _real_metric_series(rows, sport)
    if not series:
        return {"sport": sport, "datapoints": 0, "n_settled": 0,
                "verdict": "NO DATA -- loop has no settled games yet"}
    first, last = series[0], series[-1]
    n = int(last.get("n") or 0)
    brier_first, brier_last = first.get("raw_brier"), last.get("raw_brier")
    ece_first, ece_last = first.get("raw_ece"), last.get("raw_ece")
    info = {
        "sport": sport,
        "datapoints": len(series),
        "n_settled": n,
        "n_with_close": int(last.get("n_with_close") or 0),
        "brier_first": brier_first,
        "brier_latest": brier_last,
        "brier_trend": _trend(brier_first, brier_last),
        "ece_latest": ece_last,
        "ece_trend": _trend(ece_first, ece_last),
        "bss_vs_close": last.get("bss_vs_close"),
        "pct_beat_close_pred": last.get("pct_beat_close"),
    }
    info["verdict"] = _sport_verdict(info)
    return info


def _sport_verdict(i: Dict[str, Any]) -> str:
    n = i["n_settled"]
    if n < _MIN_SETTLED:
        return ("DATA-GATED: %d/%d settled -- loop holds recalibration until ~%d "
                "(honest, not a failure)" % (n, _MIN_SETTLED, _MIN_SETTLED))
    bt = i["brier_trend"]
    if bt == "improving":
        return "CALIBRATION IMPROVING (Brier trending down on >=%d games)" % _MIN_SETTLED
    if bt == "flat":
        return "STABLE (no new settled games moving the metric)"
    return "REGRESSING (Brier up) -- investigate"


def progress(improve_rows: Optional[Sequence[Dict[str, Any]]] = None,
             clv: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rows = list(improve_rows) if improve_rows is not None else _load_improve()
    sports = []
    seen = []
    for r in rows:
        s = r.get("sport")
        if s and s not in seen:
            seen.append(s)
    for s in seen:
        sports.append(_sport_progress(rows, s))
    board = clv if clv is not None else clv_scoreboard()
    return {
        "sports": sports,
        "edge": {
            "coverage_pct": board.get("coverage_pct"),
            "total_settled": board.get("total_settled"),
            "total_measurable": board.get("total_measurable"),
            "verdict": board.get("verdict"),
        },
        "ship_count": sum(1 for r in rows if r.get("verdict") == "SHIP"),
        "insufficient_count": sum(1 for r in rows
                                  if r.get("verdict") == "INSUFFICIENT_DATA"),
    }


def render(p: Dict[str, Any]) -> str:
    L: List[str] = []
    L.append("=" * 80)
    L.append("ARE THE MODELS GETTING BETTER? -- two axes, measured (no $ claim)")
    L.append("=" * 80)
    L.append("self-improve loop: %d real recalibrations SHIPPED, %d held as "
             "INSUFFICIENT_DATA (honest)" % (p["ship_count"], p["insufficient_count"]))
    L.append("")
    L.append("AXIS 1 -- PREDICTION (calibration, per sport):")
    L.append("%-8s %5s %8s %10s %8s %10s  %s"
             % ("sport", "n", "Brier", "trend", "ECE", "bss>close", "verdict"))
    L.append("-" * 80)
    for s in p["sports"]:
        if s["datapoints"] == 0:
            L.append("%-8s %5d %8s %10s %8s %10s  %s"
                     % (s["sport"], 0, "--", "--", "--", "--", s["verdict"]))
            continue
        bss = s.get("bss_vs_close")
        bss_s = ("%+.3f" % bss) if isinstance(bss, (int, float)) else "--"
        L.append("%-8s %5d %8.4f %10s %8.4f %10s  %s"
                 % (s["sport"], s["n_settled"], s["brier_latest"] or 0,
                    s["brier_trend"], s["ece_latest"] or 0, bss_s, s["verdict"]))
    L.append("-" * 80)
    L.append("bss>close = Brier Skill Score vs the market close (model PREDICTS "
             "better than the line when > 0; small n => not yet provable).")
    L.append("")
    e = p["edge"]
    L.append("AXIS 2 -- REALIZED EDGE (CLV): coverage %.1f%% (%d/%d bets measurable)"
             % (e["coverage_pct"] or 0, e["total_measurable"] or 0,
                e["total_settled"] or 0))
    L.append("  " + (e["verdict"] or ""))
    L.append("")
    L.append("BOTTOM LINE: 'better' requires BOTH Brier/ECE trending DOWN *and* CLV "
             "going POSITIVE. A good prediction at a bad price is still no edge.")
    L.append("=" * 80)
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = progress()
    print(render(p))
    try:
        os.makedirs(os.path.dirname(_OUT_JSON), exist_ok=True)
        with open(_OUT_JSON, "w", encoding="utf-8") as fh:
            json.dump(p, fh, indent=1)
        print("\nwrote %s" % _OUT_JSON)
    except OSError as exc:
        print("(progress JSON not written: %s)" % type(exc).__name__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
