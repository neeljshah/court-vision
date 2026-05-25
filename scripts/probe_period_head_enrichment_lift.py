"""probe_period_head_enrichment_lift.py -- Cycle 108a (loop 5).

Quantifies the MAE lift from cycle 107b pregame enrichment on the period-specific
heads (endQ1 / endQ2). Compares two modes:

  - BASELINE: live_engine with period heads but NO pregame enrichment
    (simulates cycle 106a state: l5/l20/position are NaN for all heads)
  - ENRICHED: live_engine as-is (107b: pregame_enrichment injects real values)

Both share the same retro snapshot reconstruction (player_quarter_stats.parquet)
and the same actuals. The only difference is whether `pregame_enrichment` runs.

Ship gate: enriched MAE strictly < baseline MAE for >=4/7 stats at endQ2.

Run:
    python scripts/probe_period_head_enrichment_lift.py
    python scripts/probe_period_head_enrichment_lift.py --max-games 100
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as rim  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SNAPSHOT_POINTS = ("endQ1", "endQ2")

# Keys injected by pregame_enrichment that the period heads use.
_ENRICHMENT_KEYS = [
    "l5_pts", "l5_reb", "l5_ast", "l5_fg3m", "l5_stl", "l5_blk", "l5_tov",
    "l20_pts", "l20_reb", "l20_ast", "l20_fg3m", "l20_stl", "l20_blk", "l20_tov",
    "l20_min", "position",
]


def _snap_deep(snap: dict) -> dict:
    """Deep-copy of snap (players list + player dicts only)."""
    import copy
    return {**snap, "players": [dict(p) for p in (snap.get("players") or [])]}


def _collect_pairs(
    max_games: int = 0,
) -> Dict[str, Dict[str, Dict[str, List[Tuple[float, float]]]]]:
    """
    Returns {point: {mode: {stat: [(proj, actual), ...]}}}
    mode in ("baseline", "enriched")

    BASELINE: player dicts pre-populated with None for enrichment keys.
    enrich_snapshot_with_pregame_features checks `if k not in p` before
    injecting — so pre-set None causes it to skip those keys, leaving
    the period heads with None → NaN (pre-107b behavior).

    ENRICHED: standard project_from_snapshot (107b enrichment active).
    """
    from src.prediction.live_engine import project_from_snapshot

    qstats = rim.load_quarter_stats()
    game_ids = list(qstats["game_id"].unique())
    if max_games:
        game_ids = game_ids[:max_games]

    out: Dict = {
        p: {"baseline": defaultdict(list), "enriched": defaultdict(list)}
        for p in SNAPSHOT_POINTS
    }

    n_processed = 0
    for gid in game_ids:
        actuals = rim.actuals_for_game(gid, qstats)
        if not actuals:
            continue
        for point in SNAPSHOT_POINTS:
            snap = rim.build_snapshot(gid, point, qstats)
            if snap is None:
                continue
            # ENRICHED: current live_engine (pregame enrichment active)
            try:
                rows_enr = project_from_snapshot(_snap_deep(snap))
            except Exception:
                continue

            # BASELINE: pre-populate enrichment keys with None so the
            # enrich call inside _apply_period_heads skips them (it checks
            # `if k not in p`).  This replicates cycle 106a NaN behavior.
            snap_base = _snap_deep(snap)
            for p in snap_base.get("players") or []:
                for k in _ENRICHMENT_KEYS:
                    p.setdefault(k, None)  # only sets if truly absent
                    p[k] = None  # force None regardless
            try:
                rows_base = project_from_snapshot(snap_base)
            except Exception:
                continue

            def _collect(rows, mode_dict):
                for r in rows:
                    pid = r.get("player_id")
                    stat = r.get("stat")
                    if pid is None or stat not in STATS:
                        continue
                    try:
                        proj = float(r.get("projected_final", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        continue
                    actual = actuals.get((int(pid), stat))
                    if actual is None:
                        continue
                    mode_dict[stat].append((proj, float(actual)))

            _collect(rows_enr, out[point]["enriched"])
            _collect(rows_base, out[point]["baseline"])
            n_processed += 1
            if n_processed % 100 == 0:
                print(f"  [{n_processed}] snapshots done", flush=True)

    return out


def probe(max_games: int = 0) -> dict:
    from src.prediction.pregame_enrichment import clear_cache
    clear_cache()

    print(f"[probe-108a] collecting pairs (max_games={max_games or 'ALL'})...",
          flush=True)
    pairs = _collect_pairs(max_games=max_games)

    results: dict = {}
    for point in SNAPSHOT_POINTS:
        results[point] = {}
        n_wins = 0
        print(f"\n── {point} ──────────────────────────────────────────", flush=True)
        print(f"  {'stat':4s}  {'n':>5s}  {'baseline':>9s}  "
              f"{'enriched':>9s}  {'delta':>8s}  verdict", flush=True)
        for stat in STATS:
            base_pts = pairs[point]["baseline"].get(stat) or []
            enr_pts = pairs[point]["enriched"].get(stat) or []
            if len(base_pts) < 20 or len(enr_pts) < 20:
                print(f"  {stat:4s}  n<20 — skip", flush=True)
                continue
            base_arr = np.asarray(base_pts, dtype=float)
            enr_arr = np.asarray(enr_pts, dtype=float)
            base_mae = float(np.mean(np.abs(base_arr[:, 0] - base_arr[:, 1])))
            enr_mae = float(np.mean(np.abs(enr_arr[:, 0] - enr_arr[:, 1])))
            delta = enr_mae - base_mae
            win = delta < 0
            if win:
                n_wins += 1
            verdict = "WIN" if win else "LOSS"
            results[point][stat] = {
                "n": len(enr_pts),
                "baseline_mae": round(base_mae, 4),
                "enriched_mae": round(enr_mae, 4),
                "delta": round(delta, 4),
                "win": win,
            }
            print(f"  {stat:4s}  {len(enr_pts):5d}  {base_mae:9.4f}  "
                  f"{enr_mae:9.4f}  {delta:+8.4f}  {verdict}", flush=True)

        ship = n_wins >= 4
        results[point]["_n_wins"] = n_wins
        results[point]["_ship"] = ship
        verdict = "SHIP" if ship else "REJECT"
        print(f"  {point}: {n_wins}/7 enriched wins -- {verdict}", flush=True)

    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=0)
    args = ap.parse_args()
    import warnings
    warnings.filterwarnings("ignore")
    probe(max_games=args.max_games)
    return 0


if __name__ == "__main__":
    sys.exit(main())
