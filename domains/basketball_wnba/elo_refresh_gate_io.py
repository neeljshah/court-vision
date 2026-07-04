"""domains.basketball_wnba.elo_refresh_gate_io -- I/O + reporting companion for
elo_refresh_gate.py: verdict-discrepancy reproduction, JSON/parquet writers, and
the human-readable report + CLI. Split out to keep elo_refresh_gate.py (the gate
math) under the 300 LOC cap; imported lazily by elo_refresh_gate.main() to avoid
a circular import (this module imports FROM elo_refresh_gate).

F5: no src.*/kernel.*/other-domain imports. <=300 LOC. ASCII stdout only.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, Optional

import pandas as pd


def reproduce_fold_discrepancy(feat: pd.DataFrame, train_frac: float,
                                bss_vs_coin: Callable) -> Dict:
    """Reproduce BOTH fold constructions on the frozen baseline (no candidates)
    to explain the wave-30 discrepancy in real numbers, per-season.
      * season-pooled: raw p_home_elo scored over the WHOLE season (matches
        pregame_gate_verdict.json's construction).
      * within-season walk-forward tail: chronological train_frac cut, raw
        p_home_elo scored on the held-out tail only (matches the RAW-ELO part
        of rest_covariate_gate's construction; that gate additionally refits a
        logistic on the train slice, which is noisier still -- noted below).
    """
    out: Dict[str, Dict] = {}
    for s in ("2025", "2026"):
        sdf = feat[feat["season"] == s].copy().sort_values("date", kind="mergesort")
        y_all = sdf["home_win"].to_numpy(dtype=float)
        p_all = sdf["p_home_elo"].to_numpy(dtype=float)
        season_pooled_bss = bss_vs_coin(y_all, p_all)

        n = len(sdf)
        cut = int(n * train_frac)
        test = sdf.iloc[cut:]
        y_te = test["home_win"].to_numpy(dtype=float)
        p_te = test["p_home_elo"].to_numpy(dtype=float)
        wf_tail_bss = bss_vs_coin(y_te, p_te) if len(test) >= 15 else float("nan")

        out[s] = {
            "n_season_pooled": int(n),
            "season_pooled_bss_raw_elo": round(float(season_pooled_bss), 6),
            "n_within_season_test_tail": int(len(test)),
            "within_season_walkforward_tail_bss_raw_elo": round(float(wf_tail_bss), 6),
            "note": "rest_covariate_gate additionally REFITS a logistic on the "
                    "train slice before scoring the tail -- this reproduces only "
                    "the raw-Elo tail BSS; the gate's reported base_degenerate "
                    "used the refit model, which is noisier still on n_test<=51.",
        }
    return out


def write_rows(feat: pd.DataFrame, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cols = [c for c in ("event_id", "date", "season", "home_team", "away_team",
                        "home_score", "away_score", "home_win", "neutral_site",
                        "p_home_elo", "margin_true") if c in feat.columns]
    feat[cols].to_parquet(dest, index=False)
    return str(dest)


def write(payload: Dict, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="ascii") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    return str(dest)


def report(payload: Dict) -> str:
    lines = ["=" * 76, "WNBA FROZEN-ELO-BASE REFRESH GATE", "=" * 76,
             "OVERALL VERDICT: %s  RECOMMENDED: %s" % (
                 payload["verdict"], payload.get("recommended_candidate")), "-" * 76]
    for cname, v in payload.get("candidate_verdicts", {}).items():
        lines.append("%s -> %s" % (cname, v))
        for f in payload["candidate_folds"].get(cname, []):
            lines.append("  %s: bss_base=%.5f bss_cand=%.5f delta=%.6f degen=%s "
                         "improves=%s" % (f["season"], f["bss_base"], f["bss_cand"],
                                          f["bss_delta"], f["base_degenerate"], f["cand_improves"]))
    lines.append("-" * 76 + "\nFOLD DISCREPANCY (season-pooled vs within-season-tail):")
    for s, d in payload.get("fold_discrepancy_explained", {}).items():
        lines.append("  %s: pooled_bss=%.5f (n=%d)  tail_bss=%.5f (n_test=%d)" % (
            s, d["season_pooled_bss_raw_elo"], d["n_season_pooled"],
            d["within_season_walkforward_tail_bss_raw_elo"], d["n_within_season_test_tail"]))
    lines += ["-" * 76, "close_comparison: %s -- calibration only, NO $/edge/ROI."
             % payload.get("close_comparison"), "=" * 76]
    return "\n".join(lines)


__all__ = ["reproduce_fold_discrepancy", "write_rows", "write", "report"]
