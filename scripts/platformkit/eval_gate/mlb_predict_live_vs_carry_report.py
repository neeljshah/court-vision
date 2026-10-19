"""scripts.platformkit.eval_gate.mlb_predict_live_vs_carry_report -- S447 AMENDMENT 5 fix 1f.

Cell/report assembly split out of mlb_predict_live_vs_carry.py to keep every candidate file
under the 300-LOC cap. Takes already-SCORED rows (from process_rows) and turns them into the
historical/forward cell summaries the CLI emits. ASCII; no network; no fit.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from scripts.platformkit.ingame.gate_a0_ingame_vs_market import (
    N_MIN_GAMES, cluster_bootstrap, verdict as _gate_a0_verdict,
)

MIN_CORPORA_EFF = 2  # AMENDMENT 5 item b / Q5; AMENDMENT 6 item a: the current-K REPLICATION
# FLOOR (a constant, never the observed count -- codex round 6 blocker 1) a verdict needs.


def mid_reference(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """DESCRIPTIVE ONLY (case 8): the mid is reported here and NEVER passed to a verdict fn."""
    mids = [float(r["mid"]) for r in rows if r.get("mid") is not None]
    return {"n": len(mids), "mean": (sum(mids) / len(mids)) if mids else None}


def historical_cell(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """mlb_segmented_r3 is SPENT (docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md C2):
    chargeable is always False and there is no `verdict` key at all here (case 9). AMENDMENT 5
    item a / Q9: `rows` carries the per-unit differential series (corpus, game_id, receipt,
    both losses, the paired difference, the carry probability, and the reconstructible as-of
    state) beside the summary, so the paired point/interval can be recomputed from the
    artifact alone, without reopening any source input."""
    if not rows:
        return {"label": "historical_descriptive", "n_ticks": 0, "n_games": 0,
                "brier_live_mean": None, "brier_carry_mean": None,
                "paired_diff": {"point": None, "ci95": [None, None]}, "chargeable": False,
                "rows": []}
    df = pd.DataFrame(rows)
    point, lo, hi = cluster_bootstrap(df, "brier_live", "brier_carry")
    return {
        "label": "historical_descriptive",
        "n_ticks": int(len(df)), "n_games": int(df["game_id"].nunique()),
        "brier_live_mean": float(df["brier_live"].mean()),
        "brier_carry_mean": float(df["brier_carry"].mean()),
        "paired_diff": {"point": point, "ci95": [lo, hi]},
        "chargeable": False,
        "rows": rows,
    }


def forward_cell(rows: List[Dict[str, Any]], n_min: int = N_MIN_GAMES) -> Dict[str, Any]:
    """The chargeable cell (item a): empty -> INSUFFICIENT, n_games 0, every number None,
    field named `chargeable` (true) -- the orchestrator decides whether to spend the one K,
    not this function. n_games < n_min (case 7) -> INSUFFICIENT. AMENDMENT 5 item b / Q5,
    corrected by AMENDMENT 6 item a: AHEAD/BEHIND require `n_corpora_observed` (the count of
    DISTINCT `corpus_unit` values -- the real per-row served-night/window identifier, never the
    constant `corpus` cell label) to be >= `min_corpora_eff` (the current-K replication FLOOR,
    a fixed constant reported alongside it, never the observed count itself); a single window
    alone emits SINGLE-WINDOW instead (the paired sign and interval are still reported as
    numbers) -- never gate_a0's own UNDERPOWERED / BEHIND / AHEAD off a lone window. item a /
    Q9: `rows` carries the per-unit differential series beside the summary (see
    historical_cell)."""
    if not rows:
        return {"label": "forward", "n_ticks": 0, "n_games": 0,
                "brier_live_mean": None, "brier_carry_mean": None,
                "paired_diff": {"point": None, "ci95": [None, None]},
                "verdict": "INSUFFICIENT", "chargeable": True,
                "min_corpora_eff": MIN_CORPORA_EFF, "n_corpora_observed": 0, "rows": []}
    df = pd.DataFrame(rows)
    point, lo, hi = cluster_bootstrap(df, "brier_live", "brier_carry")
    n_games = int(df["game_id"].nunique())
    n_corpora_observed = len({r.get("corpus_unit") for r in rows})
    if n_games < n_min:
        v = "INSUFFICIENT"
    elif n_corpora_observed < MIN_CORPORA_EFF:
        v = "SINGLE-WINDOW"
    else:
        v = _gate_a0_verdict(lo, hi, n_games, n_min=n_min)
    return {
        "label": "forward",
        "n_ticks": int(len(df)), "n_games": n_games,
        "brier_live_mean": float(df["brier_live"].mean()),
        "brier_carry_mean": float(df["brier_carry"].mean()),
        "paired_diff": {"point": point, "ci95": [lo, hi]},
        "verdict": v, "chargeable": True,
        "min_corpora_eff": MIN_CORPORA_EFF, "n_corpora_observed": n_corpora_observed,
        "rows": rows,
    }
