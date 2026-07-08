"""cli -- ASCII checkpoint x rung scoreboard for the in-game compose gate, and
an upsert into the shared weight ledger (method 'ingame_compose_v1_walkforward').

    python -m scripts.platformkit.ingame_compose.cli [--season 2025-26] [--no-write]

Prints, per checkpoint: base vs conditioned OOS Brier, delta, DM p, truncation-80,
the prior-decay curve (prior beta L2 + delta = how much the PREGAME prior still
matters), the score-info coefficient, and the verdict. Calibration only, no edge/$.
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
from scripts.platformkit.intel_weighting.weight_ledger import LEDGER

_FAMILY = "ingame_compose"


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


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="in-game compose checkpoint gate")
    ap.add_argument("--season", default="2025-26")
    ap.add_argument("--no-write", action="store_true", help="scoreboard only")
    args = ap.parse_args(argv)

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
