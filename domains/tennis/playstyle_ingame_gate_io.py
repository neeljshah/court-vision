"""domains.tennis.playstyle_ingame_gate_io -- report printer + verdict writer +
harness-schema row export for playstyle_ingame_gate.py (sibling-split so the gate
module stays <=300 LOC, mirroring surface_hold_ingame_gate_io.py's convention).

NO scoring math here: pure formatting + atomic JSON write + parquet export in the
reprocess_harness.REQUIRED_COLS schema (corpus_id, fold_id, event_id, p_variant,
p_base, outcome) so this gate's rows are re-processable by the standing
scripts.platformkit.reprocess.reprocess_harness machinery without any new code.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict

import pandas as pd


def _fold_lines(res: Dict) -> list:
    lines = []
    for f in res["folds"]:
        lines.append(
            f"    fold {f['fold']}: n_test={f['n_test']:6d}  H0 {f['brier_h0']:.5f} -> "
            f"H1 {f['brier_h1']:.5f}  (delta {f['brier_delta_h1_minus_h0']:+.5f})  "
            f"DM p={f['dm_p']:.4f}  h1_beats_h0={f['h1_beats_h0']}  "
            f"degen={f['base_degenerate']}  tercile=[{f['tercile_lo']},{f['tercile_hi']}]"
        )
    return lines


def _tour_block(name: str, tour_res: Dict, clears: bool) -> list:
    if tour_res.get("not_testable"):
        return [f"[{name.upper()}] NOT_TESTABLE: {tour_res['reason']}"]
    lines = [f"[{name.upper()}] joined_states={tour_res['n_states_joined']}"]
    r = tour_res["real"]
    lines.append(
        f"  REAL   folds_run={r['n_folds_run']}  h1_beats_h0={r['n_folds_h1_beats_h0']}"
        f"  sign_ge_2of3={r['sign_holds_ge_2of3']}  pooled H0 {r['pooled_brier_h0']}"
        f" -> H1 {r['pooled_brier_h1']}  (delta {r['pooled_delta_h1_minus_h0']})"
        f"  clears_bar={clears}"
    )
    lines.extend(_fold_lines(r))
    n = tour_res["planted_null"]
    lines.append(
        f"  NULL   folds_run={n['n_folds_run']}  h1_beats_h0={n['n_folds_h1_beats_h0']}"
        f"  sign_ge_2of3={n['sign_holds_ge_2of3']}  pooled H0 {n['pooled_brier_h0']}"
        f" -> H1 {n['pooled_brier_h1']}  (delta {n['pooled_delta_h1_minus_h0']})"
        f"  (must NOT clear the bar)"
    )
    return lines


def print_report(res: Dict) -> None:
    print("=" * 78)
    print("TENNIS IN-GAME DETAIL LAYER (H3): playstyle-archetype pairing vs hold-diff-blind")
    print("=" * 78)
    print(f"base_model: {res['base_model']}   min_cell={res['min_cell']}"
          f"  n_folds_target={res['n_folds_target']}")
    print(f"AS-OF CAVEAT: {res['as_of_caveat']}")
    print("-" * 78)
    for line in _tour_block("atp", res["atp"], res["atp_clears_bar"]):
        print(line)
    print("-" * 78)
    for line in _tour_block("wta", res["wta"], False):
        print(line)
    print("-" * 78)
    print(f"planted_null_dies (ATP): {res['planted_null_dies']}")
    print(f"wta_testable: {res['wta_testable']}")
    print(f"VERDICT: {res['verdict']}")
    print(f"  reason: {res['reason']}")
    print(f"  vs_close: {res['vs_close']}")
    print("(REJECT / NOT_TESTABLE = honest success; calibration only; no edge ever claimed.)")
    print("=" * 78)


def _strip_export_rows(res: Dict) -> Dict:
    """Drop the bulky per-row export_rows list from the JSON verdict -- those rows
    live in the harness-schema parquet (export_rows_parquet) instead, so the verdict
    JSON stays a small, readable summary (mirrors surface_hold_verdict.json's shape)."""
    out = dict(res)
    for tour_key in ("atp", "wta"):
        tour = out.get(tour_key)
        if not isinstance(tour, dict):
            continue
        tour = dict(tour)
        for block_key in ("real", "planted_null"):
            block = tour.get(block_key)
            if isinstance(block, dict) and "export_rows" in block:
                block = dict(block)
                block.pop("export_rows")
                tour[block_key] = block
        out[tour_key] = tour
    return out


def write_verdict(res: Dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(out_path) + ".tmp"
    with open(tmp, "w", encoding="ascii") as f:
        json.dump(_strip_export_rows(res), f, indent=2, default=str)
    os.replace(tmp, str(out_path))


def export_rows_parquet(res: Dict, out_path: Path) -> int:
    """Write the per-row harness-schema export {corpus_id, fold_id, event_id,
    p_variant, p_base, outcome} for the ATP real-run rows (reprocess_harness.
    REQUIRED_COLS). Returns row count written (0 if ATP produced no folds --
    an empty-but-valid parquet is still written so downstream callers fail
    honestly on a schema check rather than a missing-file error).
    """
    atp = res.get("atp", {})
    real = atp.get("real", {})
    rows = real.get("export_rows", [])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        df = pd.DataFrame(columns=["corpus_id", "fold_id", "event_id", "p_variant",
                                   "p_base", "outcome"])
    else:
        df = pd.DataFrame(rows)
        df.insert(0, "corpus_id", "tennis_atp_h3_playstyle")
        df = df[["corpus_id", "fold_id", "event_id", "p_variant", "p_base", "outcome"]]
    df.to_parquet(out_path, index=False)
    return len(df)
