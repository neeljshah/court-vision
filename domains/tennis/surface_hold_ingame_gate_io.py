"""domains.tennis.surface_hold_ingame_gate_io -- report printer + verdict writer for
surface_hold_ingame_gate.py (sibling-split so the gate module stays <=300 LOC).

NO scoring math here: pure formatting + atomic JSON write, mirroring the
data/frontend/ingame/gate_<sport>.json convention ingame_gate_generic.py uses.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict


def _fold_lines(res: Dict) -> list:
    lines = []
    for f in res["folds"]:
        lines.append(
            f"    fold {f['fold']}: n_test={f['n_test']:6d}  H0 {f['brier_h0']:.5f} -> "
            f"H1 {f['brier_h1']:.5f}  (delta {f['brier_delta_h1_minus_h0']:+.5f})  "
            f"DM p={f['dm_p']:.4f}  h1_beats_h0={f['h1_beats_h0']}  "
            f"degen={f['base_degenerate']}  cells={f['surface_cell_counts']}"
        )
    return lines


def _tour_block(name: str, tour_res: Dict, clears: bool) -> list:
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
    print("TENNIS IN-GAME DETAIL LAYER: surface-specific vs surface-blind hold% prior")
    print("=" * 78)
    print(f"base_model: {res['base_model']}   min_cell={res['min_cell']}"
          f"  n_folds_target={res['n_folds_target']}")
    print("-" * 78)
    for line in _tour_block("atp", res["atp"], res["atp_clears_bar"]):
        print(line)
    print("-" * 78)
    for line in _tour_block("wta", res["wta"], res["wta_clears_bar"]):
        print(line)
    print("-" * 78)
    print(f"planted_null_dies (both tours): {res['planted_null_dies']}")
    print(f"VERDICT: {res['verdict']}")
    print(f"  reason: {res['reason']}")
    print(f"  vs_close: {res['vs_close']}")
    print("(REJECT / NOT_TESTABLE = honest success; calibration only; no edge ever claimed.)")
    print("=" * 78)


def write_verdict(res: Dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(out_path) + ".tmp"
    with open(tmp, "w", encoding="ascii") as f:
        json.dump(res, f, indent=2, default=str)
    os.replace(tmp, str(out_path))
