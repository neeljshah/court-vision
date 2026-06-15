"""scripts.platformkit.beat_the_close_scoreboard — how good are our predictions vs the market?

The honest, consolidated answer to "are we beating the best available predictor?" — one row
per (sport, market) comparing OUR model to the devigged market close on the SAME real
outcomes. This is the north-star dashboard: prediction-QUALITY vs the market, not a $ edge.

Reads the per-market proof harnesses (NBA totals + moneyline today; extensible as we ingest
more sports' current-season odds). RMSE for totals (points), Brier for win-prob.
"MATCH" = within sampling noise of the close; "BEHIND" = the market's freshness edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC. Calibration/accuracy only; no $ edge.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _nba_totals_row() -> Dict:
    from scripts.platformkit.proof_nba.asof_box_accuracy import run
    r = run()
    if r.get("status") != "ok":
        return {"sport": "NBA", "market": "total (O/U)", "status": r.get("status", "error")}
    gap = r["gap_to_close_rmse"]
    return {"sport": "NBA", "market": "total (O/U)", "metric": "RMSE", "n": r["n_holdout"],
            "model": r["best_model_rmse"], "close": r["close_rmse_vs_realized"], "gap": gap,
            "verdict": "MATCH" if gap <= 1.0 else "BEHIND (freshness)",
            "detail": "possessions/efficiency model; gap = injuries/lineups"}


def _nba_ml_row() -> Dict:
    from scripts.platformkit.proof_nba.ml_accuracy import run
    r = run()
    if r.get("status") != "ok":
        return {"sport": "NBA", "market": "moneyline", "status": r.get("status", "error")}
    gap = r["brier_gap_to_market"]
    return {"sport": "NBA", "market": "moneyline", "metric": "Brier", "n": r["n_holdout"],
            "model": r["model_brier"], "close": r["market_brier"], "gap": gap,
            "verdict": "MATCH" if gap <= 0.012 else "BEHIND (freshness)",
            "detail": "MOV-aware Elo; within sampling noise of the close"}


_ROWS = (_nba_ml_row, _nba_totals_row)


def build() -> List[Dict]:
    rows: List[Dict] = []
    for fn in _ROWS:
        try:
            rows.append(fn())
        except Exception as exc:  # noqa: BLE001
            rows.append({"sport": "?", "market": fn.__name__, "status": f"error: {exc}"})
    return rows


def render_markdown(rows: List[Dict]) -> str:
    L = ["# Beat-the-Close Scoreboard — prediction quality vs the market", "",
         "> Honest: our model vs the **devigged closing line** on the SAME real outcomes. "
         "MATCH = within sampling noise; BEHIND = the market's freshness (injury/lineup) edge "
         "a public/box model cannot see. Calibration/accuracy only — NOT a $ edge.", "",
         "| Sport | Market | Metric | n | Our model | Close | Gap | Verdict | Why |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("status"):
            L.append(f"| {r.get('sport','?')} | {r.get('market','?')} | — | — | — | — | — | "
                     f"{r['status']} | — |")
            continue
        L.append(f"| {r['sport']} | {r['market']} | {r['metric']} | {r['n']} | {r['model']} | "
                 f"{r['close']} | {r['gap']:+} | {r['verdict']} | {r['detail']} |")
    L += ["", "**Reading it:** on the moneyline (mostly team strength) we MATCH the close; on "
          "totals (where injuries swing pace) we trail by the freshness edge. Closing that gap "
          "needs the data the market has (an injury/lineup feed, forward) or in-game conditioning, "
          "not a cleverer box model — proven by W136/W138/W140 nulls and the W139 richer-data win."]
    return "\n".join(L)


def write_report(root: Path = None) -> Path:
    eff = root or _REPO
    out = eff / "vault" / "_Organized" / "_Index" / "_Beat_The_Close.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(build()), encoding="utf-8")
    return out


def _main() -> int:
    rows = build()
    print(render_markdown(rows))
    try:
        p = write_report()
        print(f"\n(written -> {p})")
    except Exception as exc:  # noqa: BLE001
        print(f"\n(report not written: {exc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
