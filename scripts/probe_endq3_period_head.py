"""probe_endq3_period_head.py -- Cycle 109a (loop 5).

Measures whether wiring the endQ3 period-specific LGB head into live_engine
improves MAE vs the current cycle-88 linear + stratified-residual baseline.

WHY: Cycle 105b trained 21 LGB artifacts (7 stats × 3 points). The endQ3
head was intentionally excluded from live_engine in cycle 106a ("already
near-optimal"). Cycles 107b validated pregame enrichment (which also benefits
endQ3 heads). This probe re-evaluates whether the endQ3 head + enrichment
now beats the current baseline (linear + foul/blowout/heat_check residuals).

BASELINE: current live_engine project_from_snapshot() — uses cycle-88 linear
extrapolation + three stratified residual overrides at endQ3.

HEAD: same, but with endQ3 added to _apply_period_heads() allowed points.

Note: the endQ3 head fires BEFORE stratified residuals in the current pipeline.
That means if the head fires, the residual overrides still apply on top of it.
This probe tests the marginal value of the head BEFORE the residuals.

Ship gate: HEAD MAE < BASELINE for >=4/7 stats at endQ3 over 300+ games.

Run:
    python scripts/probe_endq3_period_head.py
    python scripts/probe_endq3_period_head.py --max-games 100
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as rim  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _project_with_endq3_head(snap: dict) -> list:
    """Run live_engine with endQ3 head enabled (monkey-patch _apply_period_heads)."""
    import src.prediction.live_engine as le
    import src.prediction.period_specific_heads as psh

    original_fn = le._apply_period_heads

    def _patched_apply_period_heads(snap_inner: dict, rows: list) -> list:
        try:
            snap_period = snap_inner.get("period")
            snap_clock = snap_inner.get("clock")
            point = psh.snapshot_point_for(snap_period, snap_clock)
            if point not in ("endQ1", "endQ2", "endQ3"):
                return rows
            # Temporarily redirect to allow endQ3 by removing the guard and
            # calling the rest of the original function logic.
            # We do this by setting point inclusion to ALL three then calling.
        except Exception:
            return rows

        # Manually call the head dispatch logic (replicated from original).
        try:
            from src.prediction.pregame_enrichment import (
                enrich_snapshot_with_pregame_features,
            )
            snap_inner = enrich_snapshot_with_pregame_features(snap_inner)
        except Exception:
            pass

        src_tag = f"{point}_head"
        observed_qs = psh.SNAPSHOT_QUARTERS[point]
        by_pid: dict = {}
        for p in snap_inner.get("players") or []:
            try:
                by_pid[int(p.get("player_id"))] = p
            except (TypeError, ValueError):
                continue
        try:
            home_score = float(snap_inner.get("home_score") or 0)
        except (TypeError, ValueError):
            home_score = 0.0
        try:
            away_score = float(snap_inner.get("away_score") or 0)
        except (TypeError, ValueError):
            away_score = 0.0
        margin_signed = home_score - away_score
        margin_abs = abs(margin_signed)
        home_team = snap_inner.get("home_team") or ""
        away_team = snap_inner.get("away_team") or ""

        for r in rows:
            pid = r.get("player_id")
            stat = r.get("stat")
            if pid is None or stat not in psh.STATS:
                continue
            try:
                pid_i = int(pid)
            except (TypeError, ValueError):
                continue
            p = by_pid.get(pid_i)
            if p is None:
                continue
            try:
                current_stat = float(p.get(stat) or 0)
            except (TypeError, ValueError):
                current_stat = 0.0
            min_through = 0.0
            any_q = False
            for q in observed_qs:
                v = p.get(f"min_q{q}")
                if v is not None:
                    any_q = True
                    try:
                        min_through += float(v or 0)
                    except (TypeError, ValueError):
                        pass
            if not any_q:
                try:
                    min_through = float(p.get("min") or 0)
                except (TypeError, ValueError):
                    min_through = 0.0
            try:
                pf_through = float(p.get("pf") or 0)
            except (TypeError, ValueError):
                pf_through = 0.0
            team = p.get("team") or ""
            team_is_leading = (
                (team == home_team and margin_signed > 0)
                or (team == away_team and margin_signed < 0)
            )
            try:
                remaining = psh.predict_remaining(
                    stat, point,
                    current_stat=current_stat,
                    min_through=min_through,
                    pf_through=pf_through,
                    score_margin_abs=margin_abs,
                    is_leading_team=1 if team_is_leading else 0,
                    l5_stat=p.get(f"l5_{stat}"),
                    l20_stat=p.get(f"l20_{stat}"),
                    l20_min=p.get("l20_min"),
                    position_proxy=p.get("position"),
                )
            except Exception:
                remaining = None
            if remaining is None:
                continue
            r["projected_final"] = float(current_stat + max(0.0, float(remaining)))
            r["projection_source"] = src_tag
        return rows

    # Temporarily replace _apply_period_heads
    le._apply_period_heads = _patched_apply_period_heads
    try:
        rows = le.project_from_snapshot(snap)
    finally:
        le._apply_period_heads = original_fn
    return rows


def _snap_deep(snap: dict) -> dict:
    return {**snap, "players": [dict(p) for p in (snap.get("players") or [])]}


def _collect_pairs(max_games: int = 0) -> Dict[str, Dict[str, List[Tuple[float, float]]]]:
    from src.prediction.live_engine import project_from_snapshot

    qstats = rim.load_quarter_stats()
    game_ids = list(qstats["game_id"].unique())
    if max_games:
        game_ids = game_ids[:max_games]

    out: Dict = {"baseline": defaultdict(list), "head": defaultdict(list)}

    n_snaps = 0
    for gid in game_ids:
        actuals = rim.actuals_for_game(gid, qstats)
        if not actuals:
            continue
        snap = rim.build_snapshot(gid, "endQ3", qstats)
        if snap is None:
            continue

        try:
            rows_base = project_from_snapshot(_snap_deep(snap))
        except Exception:
            continue
        try:
            rows_head = _project_with_endq3_head(_snap_deep(snap))
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

        _collect(rows_base, out["baseline"])
        _collect(rows_head, out["head"])
        n_snaps += 1
        if n_snaps % 100 == 0:
            print(f"  [{n_snaps}] games done", flush=True)

    return out


def probe(max_games: int = 0) -> dict:
    from src.prediction.pregame_enrichment import clear_cache
    clear_cache()

    print(f"[probe-109a] collecting endQ3 pairs (max_games={max_games or 'ALL'})...",
          flush=True)
    pairs = _collect_pairs(max_games=max_games)

    print(f"\n── endQ3 period head vs baseline ────────────────────────", flush=True)
    print(f"  {'stat':4s}  {'n':>5s}  {'baseline':>9s}  {'head':>9s}  {'delta':>8s}  verdict",
          flush=True)

    results: dict = {}
    n_wins = 0
    for stat in STATS:
        base_pts = pairs["baseline"].get(stat) or []
        head_pts = pairs["head"].get(stat) or []
        if len(base_pts) < 20 or len(head_pts) < 20:
            print(f"  {stat:4s}  n<20 — skip", flush=True)
            continue
        base_arr = np.asarray(base_pts, dtype=float)
        head_arr = np.asarray(head_pts, dtype=float)
        base_mae = float(np.mean(np.abs(base_arr[:, 0] - base_arr[:, 1])))
        head_mae = float(np.mean(np.abs(head_arr[:, 0] - head_arr[:, 1])))
        delta = head_mae - base_mae
        win = delta < 0
        if win:
            n_wins += 1
        verdict = "WIN" if win else "LOSS"
        results[stat] = {
            "n": len(head_pts),
            "baseline_mae": round(base_mae, 4),
            "head_mae": round(head_mae, 4),
            "delta": round(delta, 4),
            "win": win,
        }
        print(f"  {stat:4s}  {len(head_pts):5d}  {base_mae:9.4f}  "
              f"{head_mae:9.4f}  {delta:+8.4f}  {verdict}", flush=True)

    ship = n_wins >= 4
    results["_n_wins"] = n_wins
    results["_ship"] = ship
    verdict = "SHIP" if ship else "REJECT"
    print(f"\n  endQ3 head: {n_wins}/7 wins vs baseline -- {verdict}", flush=True)
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
