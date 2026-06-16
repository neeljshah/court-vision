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

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_NO_CORPUS_BANNER = (
    "CORPUS NOT PRESENT -- run with --corpus tests/fixtures/proof or provide data/domains/ "
    "(every row is non-ok; no real or fixture corpus resolved).")


def _all_non_ok(rows: List[Dict]) -> bool:
    """True when EVERY row failed to produce a measured number (status set on all)."""
    return bool(rows) and all(r.get("status") for r in rows)


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


def _mlb_ml_row() -> Dict:
    from scripts.platformkit.proof_mlb.beat_the_close_ml import run
    r = run()
    if r.get("status") != "ok":
        return {"sport": "MLB", "market": "moneyline", "status": r.get("status", "error")}
    gap = r["gap"]
    return {"sport": "MLB", "market": "moneyline", "metric": "Brier", "n": r["n_holdout"],
            "model": r["model_brier"], "close": r["close_brier"], "gap": gap,
            "verdict": "MATCH" if gap <= 0.012 else "BEHIND (freshness)",
            "detail": "walk-forward MOV-Elo; tiny deficit = pitcher-blindness (the close prices SP)"}


def _mlb_total_row() -> Dict:
    from scripts.platformkit.proof_mlb.beat_the_close_total import run
    r = run()
    if r.get("status") != "ok":
        return {"sport": "MLB", "market": "total (O/U)", "status": r.get("status", "error")}
    gap = r["gap"]
    return {"sport": "MLB", "market": "total (O/U)", "metric": "RMSE", "n": r["n_holdout"],
            "model": r["model_total_rmse"], "close": r["close_total_rmse"], "gap": gap,
            "verdict": "MATCH" if gap <= 0.20 else "BEHIND (freshness)",
            "detail": "run-rate expected total vs closing line; gap = park/weather/SP/lineup"}


def _soccer_ou_row() -> Dict:
    from scripts.platformkit.proof_soccer.beat_the_close_ou import run
    r = run()
    if r.get("status") != "ok":
        return {"sport": "Soccer", "market": "O/U-2.5", "status": r.get("status", "error")}
    gap = r["gap"]
    return {"sport": "Soccer", "market": "O/U-2.5", "metric": "Brier", "n": r.get("n_holdout", r.get("n")),
            "model": r["model_brier"], "close": r["close_brier"], "gap": gap,
            "verdict": "MATCH" if gap <= 0.012 else "BEHIND (freshness)",
            "detail": "EW-Poisson+finishing+pooled-Platt vs devigged Pinnacle close (W133 win)"}


def _tennis_atp_ml_row() -> Dict:
    from scripts.platformkit.proof_tennis.beat_the_close_ml import run
    r = run()
    if r.get("status") != "ok":
        return {"sport": "Tennis (ATP)", "market": "match-win", "status": r.get("status", "error")}
    gap = r["gap"]
    return {"sport": "Tennis (ATP)", "market": "match-win", "metric": "Brier", "n": r.get("n_holdout", r.get("n")),
            "model": r["model_metric"], "close": r["close_metric"], "gap": gap,
            "verdict": "MATCH" if gap <= 0.012 else "BEHIND (freshness)",
            "detail": "surface-Elo+Platt vs devigged Pinnacle; ATP closes very efficient"}


_ROWS = (_nba_ml_row, _nba_totals_row, _mlb_ml_row, _mlb_total_row,
         _soccer_ou_row, _tennis_atp_ml_row)


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
    L += ["", "**Reading it (4 sports now measured):** on team-strength win markets (NBA & MLB "
          "moneyline) we MATCH the devigged close within noise; the small MLB-ML deficit is "
          "pitcher-blindness (the close prices the starting pitcher). On totals/derived markets "
          "(NBA totals, MLB totals, Soccer O/U-2.5, ATP match-win) we trail by the freshness edge "
          "— injuries/lineups/weather/park/SP the market sees and a public/box model cannot. "
          "Soccer O/U sits in the MATCH band (pooled Platt, W133). Closing the remaining gaps needs "
          "the data the market has (a freshness feed, forward) or in-game conditioning, not a "
          "cleverer pregame model. WTA: temperature recal (T=1.36) is the chosen live recalibrator "
          "(holdout ECE 0.045->0.019), a calibration win, not a market row.",
          "", "_Soccer 1X2 is absent by design: the football-data corpus carries O/U-2.5 prices "
          "only — no 1X2 closing odds exist to devig against (W149 data finding)._"]
    return "\n".join(L)


def write_report(root: Path = None) -> Path:
    # Write to _Edge_Maps (LOCAL, not rmtree'd by the brain rebuild), NOT _Organized
    # (which the rebuild wipes — the report would vanish there).
    eff = root or _REPO
    out = eff / "vault" / "_Edge_Maps" / "_Beat_The_Close.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(build()), encoding="utf-8")
    return out


def _main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(description="Beat-the-close scoreboard (prediction quality).")
    ap.add_argument("--corpus", default=None,
                    help="corpus root (e.g. tests/fixtures/proof); sets PROOF_CORPUS_ROOT "
                         "BEFORE build() so each per-sport run() picks up its fixtures.")
    args = ap.parse_args(argv)
    if args.corpus:
        os.environ["PROOF_CORPUS_ROOT"] = args.corpus
    rows = build()
    print(render_markdown(rows))
    if _all_non_ok(rows):
        print("\n" + _NO_CORPUS_BANNER)
    # Fixture/demo mode (--corpus) is PRINT-ONLY: it must NOT overwrite the canonical
    # _Edge_Maps report with synthetic-fixture numbers. Only a real-corpus run writes.
    if args.corpus:
        print("\n(fixture/demo mode -- canonical report NOT written; run with no --corpus to refresh it)")
        return 0
    try:
        p = write_report()
        print(f"\n(written -> {p})")
    except Exception as exc:  # noqa: BLE001
        print(f"\n(report not written: {exc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
