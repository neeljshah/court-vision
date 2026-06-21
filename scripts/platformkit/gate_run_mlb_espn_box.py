"""scripts.platformkit.gate_run_mlb_espn_box -- GATE-RUN for the MLB ESPN box-score
defensive/efficiency AS-OF layer (errors / strikeouts / LOB-proxy / earned-runs ...) as
PREGAME win-prob candidates.

THE QUESTION: does adding a strictly-prior trailing as-of box-stat diff (from
domains.mlb.asof_espn_box) to a leak-free run-margin BASE lower held-out P(home win)
Brier, REPLICATED across >=2 INDEPENDENT corpora, DM clustered by game, degenerate-base
guarded, with a PLANTED-NULL noise column that MUST reject -- through the IDENTICAL proven
gate core reused VERBATIM from gate_run_soccer_espn28 (gate_one / _gate_corpus)?

HONEST STATE ON CURRENT DISK: INSUFFICIENT_DATA. data/domains/mlb/espn_boxscores.parquet
holds only ~3 weeks of current-season box rows -- far too few to form two independent
leak-free cross-corpus walk-forwards (each needs ~100 warmup + >=200 test). To gate FOR
REAL, materialize >=2 seasons via domains.mlb.ingest_espn_box, then re-run this unchanged.
HONEST EXPECTATION once gateable: REJECT-scouting (box defensive efficiency is well-priced
by team strength + run-margin, and noisy) -- kept as SCOUTING, NEVER force-fed as a feature.

PROPOSAL / MEASUREMENT-ONLY: writes ONLY the verdict JSON under data/frontend/funnel/;
NO data/registry write, NO flag flip, NO sentinel, NO $/ROI/edge field. CALIBRATION only
(held-out home-win Brier); vs-close is a yardstick, never a feature. ASCII; <=300 LOC.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from domains.mlb.asof_espn_box import ASOF_FEATURES, build_asof_espn_box
# Reuse the PROVEN gate core verbatim (leak-free split, DM-by-game, degenerate guard).
from scripts.platformkit.gate_run_soccer_espn28 import gate_one, _NULL_COL

_REPO = Path(__file__).resolve().parents[2]
_BOX = _REPO / "data" / "domains" / "mlb" / "espn_boxscores.parquet"
_VERDICT_OUT = _REPO / "data" / "frontend" / "funnel" / "mlb_espn_box_gate.json"

_WARMUP = 100        # mirrors the proven gate core's leak-free warmup
_MIN_TEST = 200      # _gate_corpus needs >=200 covered rows after warmup
# Rows needed to even attempt 2 corpora x (warmup + test). Below this -> INSUFFICIENT_DATA.
_MIN_GATEABLE = 2 * (_WARMUP + _MIN_TEST)   # 600
# Defensive/efficiency subset to test as pregame diffs (the backlog's box layer).
_TEST_FEATS = ("fld_errors", "pit_strikeouts", "pit_earnedRuns", "bat_strikeouts",
               "bat_walks", "bat_hits")


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


def _leakfree_base(df: pd.DataFrame) -> np.ndarray:
    """Strictly-prior run-margin base p_home: each team's expanding mean (runs_for -
    runs_against) over PRIOR games (shift 1), home minus away, squashed. Leak-free."""
    rows = []
    for _, r in df.iterrows():
        rows.append({"event_id": r["event_id"], "team": r["home_abbr"],
                     "net": float(r["home_score"]) - float(r["away_score"]), "side": "h"})
        rows.append({"event_id": r["event_id"], "team": r["away_abbr"],
                     "net": float(r["away_score"]) - float(r["home_score"]), "side": "a"})
    lng = pd.DataFrame(rows)
    lng["prior"] = (lng.groupby("team")["net"]
                    .transform(lambda s: s.shift(1).expanding().mean()))
    piv = lng.pivot_table(index="event_id", columns="side", values="prior", aggfunc="first")
    base_diff = (piv.get("h", pd.Series(dtype=float)).fillna(0.0)
                 - piv.get("a", pd.Series(dtype=float)).fillna(0.0))
    base_diff = base_diff.reindex(df["event_id"].values).fillna(0.0).to_numpy(float)
    return _sigmoid(0.18 * base_diff)


def build_corpus(box: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Leak-free per-game frame: base p_home + as-of box diffs + planted null + label."""
    box = box.copy()
    box["event_id"] = box["event_id"].astype(str)
    box = box.sort_values("date", kind="mergesort").reset_index(drop=True)
    # build_asof_espn_box returns (df, out_path) and writes a parquet; redirect the write
    # to a throwaway temp so a gate run NEVER clobbers real data or writes on a synthetic box.
    with tempfile.TemporaryDirectory() as _td:
        asof, _ = build_asof_espn_box(box, out_path=Path(_td) / "asof.parquet")
    asof["event_id"] = asof["event_id"].astype(str)
    diff_cols = [f"diff_{f}_asof" for f in ASOF_FEATURES if f"diff_{f}_asof" in asof.columns]
    merged = box[["event_id", "date", "home_abbr", "away_abbr",
                  "home_score", "away_score"]].merge(
        asof[["event_id", *diff_cols]], on="event_id", how="left")
    merged["y_home"] = (merged["home_score"].astype(float)
                        > merged["away_score"].astype(float)).astype(float)
    merged["p_poisson"] = _leakfree_base(merged)   # gate core reads this base column name
    rng = np.random.default_rng(seed)
    merged[_NULL_COL] = rng.standard_normal(len(merged))
    return merged.sort_values("date", kind="mergesort").reset_index(drop=True)


def _sufficiency(corp_a: pd.DataFrame, corp_b: pd.DataFrame) -> Dict[str, object]:
    na, nb = len(corp_a), len(corp_b)
    ok = na >= (_WARMUP + _MIN_TEST) and nb >= (_WARMUP + _MIN_TEST)
    return {"gateable": bool(ok), "n_corpus_a": int(na), "n_corpus_b": int(nb),
            "min_per_corpus": _WARMUP + _MIN_TEST}


def run(eps: float = 0.05, seed: int = 0,
        box: Optional[pd.DataFrame] = None,
        out_path: Optional[Path] = None) -> Dict[str, object]:
    """Build 2 chronological corpora, check sufficiency, gate every diff + the null.

    out_path defaults to the real verdict JSON; tests pass a tmp path so a SYNTHETIC
    corpus NEVER overwrites the real on-disk verdict (which would fabricate a result).
    """
    dest = out_path if out_path is not None else _VERDICT_OUT
    if box is None:
        box = pd.read_parquet(_BOX) if _BOX.exists() else pd.DataFrame()
    feats = [f"diff_{f}_asof" for f in _TEST_FEATS]
    if len(box) < _MIN_GATEABLE:
        out: Dict[str, object] = {
            "layer": "mlb_espn_box_defensive_efficiency_asof",
            "verdict": "INSUFFICIENT_DATA", "n_rows_on_disk": int(len(box)),
            "min_gateable": _MIN_GATEABLE,
            "reason": (f"only {len(box)} ESPN box rows on disk (~3 weeks current season); "
                       "a leak-free cross-corpus walk-forward needs >=2 seasons. Materialize "
                       "via domains.mlb.ingest_espn_box then re-run -- the proven gate core "
                       "(gate_one/_gate_corpus) runs unchanged."),
            "machinery_ready": True, "tested_feats": feats,
            "proposal_only": True, "force_fed": False, "scouting_only": True,
            "vs_close": "UNPROVEN -- CALIBRATION only; not gateable yet (data)",
            "honest_expectation": "REJECT-scouting once materialized (defensive efficiency "
                                  "subsumed by team strength + run-margin; noisy)",
        }
        _write(out, dest)
        return out
    # --- gateable path (runs once >=2 seasons are materialized) ---
    box = box.sort_values("date", kind="mergesort").reset_index(drop=True)
    mid = len(box) // 2
    corp_a = build_corpus(box.iloc[:mid], seed)
    corp_b = build_corpus(box.iloc[mid:], seed + 1)
    results = [gate_one(corp_a, corp_b, c, eps) for c in feats if c in corp_a.columns]
    null = gate_one(corp_a, corp_b, _NULL_COL, eps)
    null_rejects = null["verdict"] in ("REJECT", "INVALID_BASE", "PARTIAL")
    base_ok = not any(r["base_degenerate"] for r in results)
    any_ship = any(r["verdict"] == "SHIP" for r in results)
    verdict = ("NOT_TESTABLE" if not null_rejects else
               "INVALID_BASE" if not base_ok else
               "SHIP" if any_ship else "REJECT")
    out = {"layer": "mlb_espn_box_defensive_efficiency_asof", "verdict": verdict,
           "n_corpora": 2, "eps": eps, "base": "leak-free expanding run-margin p_home",
           "results": results, "null": null, "null_rejects": null_rejects,
           "sufficiency": _sufficiency(corp_a, corp_b), "base_skillful": base_ok,
           "proposal_only": True, "force_fed": False, "scouting_only": verdict != "SHIP",
           "vs_close": "UNPROVEN -- CALIBRATION only (held-out home-win Brier), not edge"}
    _write(out, dest)
    return out


def _write(out: Dict[str, object], dest: Path = _VERDICT_OUT) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="ascii") as f:
        json.dump(out, f, indent=2, sort_keys=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Gate the MLB ESPN box-score as-of layer.")
    ap.add_argument("--eps", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    res = run(eps=a.eps, seed=a.seed)
    print(f"MLB ESPN-BOX GATE -> {res['verdict']}")
    for k in ("n_rows_on_disk", "reason", "n_corpora"):
        if k in res:
            print(f"  {k}: {res[k]}")
    print(f"wrote {_VERDICT_OUT}")
    return 0


__all__ = ["run", "build_corpus", "_leakfree_base", "_sufficiency", "main", "_TEST_FEATS"]

if __name__ == "__main__":
    raise SystemExit(main())
