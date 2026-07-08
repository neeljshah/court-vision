"""cli -- ASCII checkpoint x rung scoreboard for the in-game compose gate, and
an upsert into the shared weight ledger (method 'ingame_compose_v1_walkforward'
or, with --v2, 'ingame_livestate_v2_walkforward').

    python -m scripts.platformkit.ingame_compose.cli [--season 2025-26] [--no-write] [--v2]

Prints, per checkpoint: base vs conditioned OOS Brier, delta, DM p, truncation-80,
the prior-decay curve (prior beta L2 + delta = how much the PREGAME prior still
matters), the score-info coefficient, and the verdict. Calibration only, no edge/$.

--v2 switches to the live-state ladder (conditional_gate_v2): per checkpoint,
base -> +floor_quality_now -> +star_minutes_load -> +shooting_luck_so_far ->
+bench_depth_used, cumulative.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from scripts.platformkit.ingame_compose.conditional_gate import (
    METHOD,
    IngameGateResult,
    run_all_checkpoints,
)
from scripts.platformkit.ingame_compose.conditional_gate_v2 import (
    METHOD as METHOD_V2,
    RungResult,
    run_all_rungs,
)
from scripts.platformkit.intel_weighting.weight_ledger import LEDGER

_FAMILY = "ingame_compose"
_FAMILY_V2 = "ingame_compose_v2"


def _row(g: IngameGateResult) -> dict:
    return {
        "family": _FAMILY, "metric": g.checkpoint, "sport": "nba",
        "entity_mapping": "team_asof_ingame", "n_games": g.n_games,
        "n_test": g.n_test, "trf": g.trf,
        "brier_base": g.brier_base, "brier_cond": g.brier_cond,
        "delta": g.delta, "delta_trunc80": g.delta_trunc80, "dm_p": g.dm_p,
        "verdict": g.verdict, "score_beta": g.score_beta,
        "prior_beta_l2": g.prior_beta_l2, "prior_betas": g.prior_betas,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "method": METHOD, "edge_claimed": False, "caveats": g.caveats,
    }


def append_results(results: List[IngameGateResult], ledger: Path | None = None) -> Path:
    """Upsert keyed by (family, metric, method) -- rerun REPLACES prior rows."""
    ledger = ledger or LEDGER
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if ledger.exists():
        for line in ledger.read_text(encoding="ascii", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing[(r.get("family"), r.get("metric"), r.get("method"))] = r
    for g in results:
        r = _row(g)
        existing[(r["family"], r["metric"], r["method"])] = r
    tmp = ledger.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="ascii", errors="strict") as f:
        for r in existing.values():
            f.write(json.dumps(r) + "\n")
    tmp.replace(ledger)
    return ledger


def _print_board(results: List[IngameGateResult], cp_skips, glob_skips) -> None:
    print("\ningame_compose scoreboard -- NBA  (method=" + METHOD + ")")
    print("does the composed PREGAME prior improve in-game WP beyond score+time+Elo?")
    print("calibration only (Brier deltas) -- no edge / no $")
    print("-" * 100)
    print(f"{'checkpoint':<10}{'trf':>6}{'n':>6}{'nTest':>7}  {'brier_base':>10} "
          f"{'brier_cond':>10} {'delta':>9} {'d_t80':>9} {'dm_p':>7}  verdict")
    print("-" * 100)
    for g in results:
        print(f"{g.checkpoint:<10}{g.trf:>6.3f}{g.n_games:>6}{g.n_test:>7}  "
              f"{g.brier_base:>10.5f} {g.brier_cond:>10.5f} {g.delta:>+9.5f} "
              f"{g.delta_trunc80:>+9.5f} {g.dm_p:>7.4f}  {g.verdict}")
    print("-" * 100)
    print("PRIOR-DECAY CURVE  (how much the pregame prior still matters at t)")
    print(f"{'checkpoint':<10}{'trf':>6}{'prior_beta_l2':>15}{'delta':>10}{'score_beta':>12}"
          f"   prior_betas(off/conc/net/rest)")
    for g in results:
        pb = g.prior_betas
        b = "/".join(f"{pb.get(c, 0.0):+.3f}" for c in ("off", "conc", "net", "rest"))
        print(f"{g.checkpoint:<10}{g.trf:>6.3f}{g.prior_beta_l2:>15.4f}"
              f"{g.delta:>+10.5f}{g.score_beta:>12.4f}   {b}")
    print("-" * 100)
    print("skipped games per checkpoint (checkpoint absent -- never imputed):")
    for cid, n in cp_skips.items():
        print(f"  {cid:<10} {n}")
    print(f"global skips: {glob_skips}")
    n_m = sum(1 for g in results if g.verdict == "MATTERS_PROVISIONAL")
    n_n = sum(1 for g in results if g.verdict == "NULL")
    n_u = sum(1 for g in results if g.verdict == "UNTESTABLE")
    print(f"MATTERS_PROV={n_m}  NULL={n_n}  UNTESTABLE={n_u}   (honest nulls are wins)")


def _row_v2(r: RungResult) -> dict:
    return {
        "family": _FAMILY_V2, "metric": f"{r.checkpoint}:{r.rung}", "sport": "nba",
        "entity_mapping": "team_asof_ingame", "n_games": r.n_games, "n_test": r.n_test,
        "brier_base": r.brier_base, "brier_cond": r.brier_cond, "delta": r.delta,
        "delta_trunc80": r.delta_trunc80, "dm_p": r.dm_p, "verdict": r.verdict,
        "betas": r.betas, "computed_at": datetime.now(timezone.utc).isoformat(),
        "method": METHOD_V2, "edge_claimed": False, "caveats": r.caveats,
    }


def append_results_v2(results: List[RungResult], ledger: Path | None = None) -> Path:
    """Same upsert-by-(family, metric, method) discipline as append_results,
    keyed on f'{checkpoint}:{rung}' so all 5 ladder rungs coexist."""
    ledger = ledger or LEDGER
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if ledger.exists():
        for line in ledger.read_text(encoding="ascii", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing[(row.get("family"), row.get("metric"), row.get("method"))] = row
    for r in results:
        row = _row_v2(r)
        existing[(row["family"], row["metric"], row["method"])] = row
    tmp = ledger.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="ascii", errors="strict") as f:
        for row in existing.values():
            f.write(json.dumps(row) + "\n")
    tmp.replace(ledger)
    return ledger


def _print_board_v2(results: List[RungResult], cp_skips, glob_skips) -> None:
    print("\ningame_compose v2 scoreboard -- NBA  (method=" + METHOD_V2 + ")")
    print("does LIVE-STATE (floor lineup / foul trouble / in-game luck / bench) beat score+Elo?")
    print("calibration only (Brier deltas) -- no edge / no $")
    print("-" * 100)
    print(f"{'checkpoint':<10}{'rung':<24}{'n':>6}{'nTest':>7}  {'brier_base':>10} "
          f"{'brier_cond':>10} {'delta':>9} {'d_t80':>9} {'dm_p':>7}  verdict")
    print("-" * 100)
    for r in results:
        print(f"{r.checkpoint:<10}{r.rung:<24}{r.n_games:>6}{r.n_test:>7}  "
              f"{r.brier_base:>10.5f} {r.brier_cond:>10.5f} {r.delta:>+9.5f} "
              f"{r.delta_trunc80:>+9.5f} {r.dm_p:>7.4f}  {r.verdict}")
    print("-" * 100)
    print("skipped games per checkpoint (any of the 4 features undefined -- never imputed):")
    for cid, n in cp_skips.items():
        print(f"  {cid:<10} {n}")
    print(f"global skips: {glob_skips}")
    n_m = sum(1 for r in results if r.verdict == "MATTERS_PROVISIONAL")
    n_n = sum(1 for r in results if r.verdict == "NULL")
    n_u = sum(1 for r in results if r.verdict == "UNTESTABLE")
    print(f"MATTERS_PROV={n_m}  NULL={n_n}  UNTESTABLE={n_u}   (honest nulls are wins)")


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="in-game compose checkpoint gate")
    ap.add_argument("--season", default="2025-26")
    ap.add_argument("--no-write", action="store_true", help="scoreboard only")
    ap.add_argument("--v2", action="store_true", help="live-state ladder instead of the v1 composed-prior gate")
    args = ap.parse_args(argv)

    if args.v2:
        results, cp_skips, glob_skips = run_all_rungs(args.season)
        _print_board_v2(results, cp_skips, glob_skips)
        if not args.no_write:
            path = append_results_v2(results)
            print(f"\nledger -> {path}")
        else:
            print(f"\n(--no-write; ledger at {LEDGER} untouched)")
        return 0

    results, cp_skips, glob_skips = run_all_checkpoints(args.season)
    _print_board(results, cp_skips, glob_skips)
    if not args.no_write:
        path = append_results(results)
        print(f"\nledger -> {path}")
    else:
        print(f"\n(--no-write; ledger at {LEDGER} untouched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
