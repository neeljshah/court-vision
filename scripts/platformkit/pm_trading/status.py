"""status.py -- read-only "where do we stand" dashboard (no keys, no trades).

Summarizes the accumulating FORWARD record so you can see progress toward the
go-live gate at a glance:
  - prediction ledger (read_ledger reuse): how many real-game predictions are
    logged, across which sports/days, how many have settled (graded), and on
    the graded ones the honest accuracy + Brier (calibration, NOT $),
  - paper blotter: net paper P&L, fills, fees (0 until a price source is wired),
  - an honest standing line.

Nothing here is a claim of edge or ROI; it just reports what the system has
actually recorded. Run: python -m scripts.platformkit.pm_trading.status
"""
from __future__ import annotations

import pathlib
import sys
from typing import Optional

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def status_report(ledger_dir: Optional[str] = None,
                  blotter_dir: Optional[str] = None) -> dict:
    rep: dict = {"n_predictions": 0, "n_graded": 0}

    try:
        from scripts.platformkit.ledger.ledger import read_ledger
        df = read_ledger(base_dir=ledger_dir)
    except Exception:
        df = None

    if df is not None and len(df):
        rep["n_predictions"] = int(len(df))
        if "sport" in df:
            rep["by_sport"] = {str(k): int(v)
                               for k, v in df["sport"].value_counts().items()}
        if "game_date" in df:
            days = {d for d in df["game_date"].tolist() if d}
            rep["forward_days"] = len(days)
        graded = df[df["outcome"].notna()] if "outcome" in df else df.iloc[0:0]
        rep["n_graded"] = int(len(graded))
        if len(graded):
            y = graded["outcome"].astype(float)
            p = graded["calibrated_prob"].astype(float)
            rep["accuracy"] = round(float((((p > 0.5).astype(float)) == y).mean()), 4)
            rep["brier"] = round(float(((p - y) ** 2).mean()), 4)
            if "devig_close_prob" in graded and graded["devig_close_prob"].notna().any():
                gg = graded[graded["devig_close_prob"].notna()]
                gap = (gg["calibrated_prob"].astype(float)
                       - gg["devig_close_prob"].astype(float)).mean()
                # model prob vs devigged close -- a gap, NOT realized CLV
                rep["model_vs_devigclose_gap"] = round(float(gap), 4)

    try:
        from pnl import PnLBlotter
        rep["paper"] = (PnLBlotter(base_dir=blotter_dir) if blotter_dir
                        else PnLBlotter()).summary()
    except Exception:
        rep["paper"] = {}

    rep["standing"] = _standing(rep)
    rep["note"] = ("Forward predictions = the track-record/CLV clock. Paper "
                   "trades stay 0 until a market-price source is wired (odds "
                   "API key, human-provided). No real money, no edge claimed.")
    return rep


def _standing(rep: dict) -> str:
    if rep["n_predictions"] == 0:
        return "EMPTY -- no forward predictions logged yet."
    if rep["n_graded"] == 0:
        return ("ACCUMULATING -- %d predictions logged, none settled yet; "
                "calibration/CLV grade once outcomes land." % rep["n_predictions"])
    return ("GRADING -- %d/%d settled; acc=%s brier=%s (calibration, not $)."
            % (rep["n_graded"], rep["n_predictions"],
               rep.get("accuracy"), rep.get("brier")))


def format_report(rep: dict) -> str:
    lines = ["=" * 60, "PM-TRADING STATUS (read-only; paper; no edge claimed)",
             "=" * 60,
             "predictions logged : %d" % rep["n_predictions"]]
    if rep.get("by_sport"):
        lines.append("  by sport         : %s" % rep["by_sport"])
    if "forward_days" in rep:
        lines.append("  forward days     : %d" % rep["forward_days"])
    lines.append("settled (graded)   : %d" % rep["n_graded"])
    if "accuracy" in rep:
        lines.append("  accuracy / brier : %s / %s (calibration, not $)"
                     % (rep.get("accuracy"), rep.get("brier")))
    if "model_vs_devigclose_gap" in rep:
        lines.append("  model vs devig-close gap : %s (a gap, not realized CLV)"
                     % rep["model_vs_devigclose_gap"])
    paper = rep.get("paper") or {}
    lines.append("paper net P&L      : %s (fills=%s fees=%s)"
                 % (paper.get("net_paper_pnl", 0), paper.get("n_fills", 0),
                    paper.get("fees_paid", 0)))
    lines.append("-" * 60)
    lines.append("standing: %s" % rep["standing"])
    lines.append(rep["note"])
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_report(status_report()))
