"""probe_heat_check_blend.py -- cycle 102b (loop 5).

Three-way comparison at endQ3 for PTS only (heat_check is PTS-specific):

  1. HEURISTIC baseline   (cycle 88b -- pure linear extrapolation, no override)
  2. CYCLE-96D shrinkage  (heuristic Bayesian shrinkage that rejected at -0.082)
  3. RESIDUAL blend       (learned Q4 PPM specialist on heat_check stratum)

Computes PTS MAE on:
  * heat_check stratum  (gate fires)
  * non-heat stratum    (gate doesn't fire)
  * full corpus

SHIP GATE (BOTH must hold):
  * heat_check PTS MAE   improves by >= 0.10 vs cycle-88 HEURISTIC baseline
  * non_heat PTS MAE     does NOT regress > 0.05 vs cycle-88 HEURISTIC baseline

If single-split passes, run WF 4-fold on heat_check stratum (chronological
splits; train on first k of 4 slices, test on slice k+1). Require 4/4
positive deltas vs heuristic.

Strictly read-only: doesn't mutate predict_in_game.py or live_engine.py.

Run:
    python scripts/probe_heat_check_blend.py
    python scripts/probe_heat_check_blend.py --max-games 100
    python scripts/probe_heat_check_blend.py --skip-wf      (single-split only)
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import predict_in_game as pig                # noqa: E402
import retro_inplay_mae as v1                # noqa: E402
import train_minute_trajectory as tmt        # noqa: E402
import train_heat_check_residual as thr      # noqa: E402
from src.prediction.heat_check_residual import (  # noqa: E402
    HeatCheckResidualModel,
    build_feature_row,
    in_heat_check_stratum,
    stratified_heat_check_projection,
)
from src.prediction.heat_check_shrinkage import heat_check_factor  # noqa: E402


def _num(v, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _heuristic_pts(snap_p: dict, period: int, clock_rem: float) -> float:
    """Plain cycle-88 PTS projection (no shrinkage, no override)."""
    cur = _num(snap_p.get("pts"))
    cur_min = _num(snap_p.get("min"))
    period_elapsed_min = max(0.0, pig.PERIOD_MIN - clock_rem)
    bench_now = pig.is_bench_in_current_period(
        snap_p, period, period_elapsed_min=period_elapsed_min)
    player_basis = cur_min if bench_now else None
    return pig.project_final(
        cur, period, clock_rem,
        pace_factor=1.0, foul_factor=1.0, blow_factor=1.0,
        player_clock_played_min=player_basis,
    )


def _shrinkage_pts(snap_p: dict, period: int, clock_rem: float,
                    q3_ppm: float, q12_ppm: float) -> float:
    """Cycle-96d shrinkage: multiply REMAINING projection by heat_check_factor."""
    cur = _num(snap_p.get("pts"))
    cur_min = _num(snap_p.get("min"))
    period_elapsed_min = max(0.0, pig.PERIOD_MIN - clock_rem)
    bench_now = pig.is_bench_in_current_period(
        snap_p, period, period_elapsed_min=period_elapsed_min)
    player_basis = cur_min if bench_now else None
    rem = pig.project_remaining(
        cur, period, clock_rem,
        pace_factor=1.0, foul_factor=1.0, blow_factor=1.0,
        player_clock_played_min=player_basis,
    )
    factor = heat_check_factor(q3_ppm, q12_ppm, season_ppm=0.0)
    return cur + rem * factor


def _residual_pts(snap_p: dict, period: int, clock_rem: float,
                   residual: Optional[HeatCheckResidualModel],
                   q1_pts: float, q2_pts: float, q3_pts: float,
                   min_q1: float, min_q2: float, min_q3: float,
                   season_ppm: Optional[float], l5_ppm: Optional[float],
                   position_proxy: Optional[str],
                   heuristic_fallback: float) -> float:
    """Override PTS via stratified_heat_check_projection when gate fires.
    Falls back to heuristic when gate doesn't fire (returns the heuristic
    we already computed). The fallback when residual is None defaults to
    the heuristic projection.
    """
    cur = _num(snap_p.get("pts"))
    # Remaining minutes estimate: use cycle-88 remaining-time anchor.
    # Q3-end snapshot ~ 12 min remaining; mid-quarter would scale.
    share_rem = max(0.0, 1.0 - pig.clock_played_share(period, clock_rem))
    rem_min_est = share_rem * pig.GAME_MIN

    override = stratified_heat_check_projection(
        residual_model=residual,
        current_pts=cur,
        q1_pts=q1_pts, q2_pts=q2_pts, q3_pts=q3_pts,
        min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
        remaining_min=rem_min_est,
        season_pts_per_min=season_ppm,
        l5_pts_per_min=l5_ppm,
        position_proxy=position_proxy,
        fallback_projection=heuristic_fallback,
    )
    return heuristic_fallback if override is None else float(override)


def _build_per_game_prior_ppm(qstats_df, games):
    """Same logic as train_heat_check_residual._build_prior_ppm_index but
    bounded to the requested game subset for speed.
    """
    return thr._build_prior_ppm_index(qstats_df)


def run_single(max_games: Optional[int], output: Optional[str],
                skip_wf: bool) -> int:
    residual = HeatCheckResidualModel.load()
    if residual is None:
        print("  ERROR: heat_check residual artifact missing. "
              "Run scripts/train_heat_check_residual.py first.")
        return 2
    print("  loaded heat_check residual.")

    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    positions = tmt.load_positions()
    print(f"  {len(games)} games  {len(positions)} positions")

    print("  building per-game prior season + L5 PPM lookup...")
    prior_ppm = _build_per_game_prior_ppm(qstats_df, games)

    variants = ("heuristic", "shrinkage", "residual")
    slices = ("heat_check", "non_heat", "all")
    accum: Dict[Tuple[str, str], List[float]] = {
        (v, s): [] for v in variants for s in slices
    }
    n_total = 0
    n_strat = 0

    for gid in games:
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)
        gdf = qstats_df[qstats_df["game_id"] == gid]

        # Build per-player Q1/Q2/Q3 pts + min lookup for the heat_check gate.
        per_player_q: Dict[int, Dict[str, float]] = {}
        for pid in gdf["player_id"].unique():
            pdf = gdf[gdf["player_id"] == pid]
            pq: Dict[str, float] = {
                "q1_pts": 0.0, "q2_pts": 0.0, "q3_pts": 0.0,
                "min_q1": 0.0, "min_q2": 0.0, "min_q3": 0.0,
            }
            for _, r in pdf.iterrows():
                p = int(r["period"])
                if p == 1:
                    pq["q1_pts"] = float(r["pts"])
                    pq["min_q1"] = float(r["min"])
                elif p == 2:
                    pq["q2_pts"] = float(r["pts"])
                    pq["min_q2"] = float(r["min"])
                elif p == 3:
                    pq["q3_pts"] = float(r["pts"])
                    pq["min_q3"] = float(r["min"])
            per_player_q[int(pid)] = pq

        pig._normalize_snapshot(snap)
        period = int(snap.get("period") or 4)
        clock_rem = pig.parse_clock(snap.get("clock"))

        for p in snap.get("players") or []:
            try:
                pid_i = int(p.get("player_id"))
            except (TypeError, ValueError):
                continue
            pq = per_player_q.get(pid_i)
            if not pq:
                continue

            min_q3 = pq["min_q3"]
            q12_min = pq["min_q1"] + pq["min_q2"]
            if min_q3 <= 0.0 or q12_min <= 0.0:
                continue
            q3_ppm = pq["q3_pts"] / min_q3
            q12_ppm = (pq["q1_pts"] + pq["q2_pts"]) / q12_min
            in_strat = in_heat_check_stratum(q3_ppm, q12_ppm)

            n_total += 1
            if in_strat:
                n_strat += 1
            slice_keys = ["all", "heat_check" if in_strat else "non_heat"]

            actual = actuals.get((pid_i, "pts"))
            if actual is None:
                continue

            # Variants.
            heur_v = _heuristic_pts(p, period, clock_rem)
            shrink_v = _shrinkage_pts(p, period, clock_rem, q3_ppm, q12_ppm)
            spm, lpm = prior_ppm.get((pid_i, gid), (float("nan"), float("nan")))
            pos_str = positions.get(pid_i)
            res_v = _residual_pts(
                p, period, clock_rem, residual,
                q1_pts=pq["q1_pts"], q2_pts=pq["q2_pts"], q3_pts=pq["q3_pts"],
                min_q1=pq["min_q1"], min_q2=pq["min_q2"], min_q3=pq["min_q3"],
                season_ppm=(None if spm != spm else spm),
                l5_ppm=(None if lpm != lpm else lpm),
                position_proxy=pos_str,
                heuristic_fallback=heur_v,
            )
            for sl in slice_keys:
                accum[("heuristic", sl)].append(abs(heur_v - actual))
                accum[("shrinkage", sl)].append(abs(shrink_v - actual))
                accum[("residual", sl)].append(abs(res_v - actual))

    def _mae(key):
        xs = accum.get(key, [])
        return (sum(xs) / len(xs)) if xs else float("nan")

    pts_strat_heur = _mae(("heuristic", "heat_check"))
    pts_strat_shrink = _mae(("shrinkage", "heat_check"))
    pts_strat_res = _mae(("residual", "heat_check"))
    pts_non_heur = _mae(("heuristic", "non_heat"))
    pts_non_res = _mae(("residual", "non_heat"))

    strat_delta_vs_heur = pts_strat_res - pts_strat_heur
    non_delta_vs_heur = pts_non_res - pts_non_heur

    ship_single = (strat_delta_vs_heur <= -0.10) and (non_delta_vs_heur <= 0.05)

    print(f"\n  heat_check stratum n={len(accum[('residual','heat_check')])}")
    print(f"    heuristic PTS MAE: {pts_strat_heur:.4f}")
    print(f"    shrinkage PTS MAE: {pts_strat_shrink:.4f}")
    print(f"    RESIDUAL  PTS MAE: {pts_strat_res:.4f}  "
          f"(delta vs heur: {strat_delta_vs_heur:+.4f})")
    print(f"\n  non_heat stratum n={len(accum[('residual','non_heat')])}")
    print(f"    heuristic PTS MAE: {pts_non_heur:.4f}")
    print(f"    RESIDUAL  PTS MAE: {pts_non_res:.4f}  "
          f"(delta vs heur: {non_delta_vs_heur:+.4f})")

    wf_results = None
    if ship_single and not skip_wf:
        print("\n  single-split PASSES -- running WF 4-fold on heat_check stratum...")
        wf_results = run_wf_4fold(games, qstats_df, positions, prior_ppm)

    ship_final = ship_single and (wf_results is None or all(
        d < 0.0 for d in wf_results["per_fold_delta"]))

    # Markdown report.
    lines: List[str] = []
    lines.append("# heat_check residual blend probe -- cycle 102b (loop 5)")
    lines.append("")
    lines.append(f"**Games:** {len(games)}  "
                 f"**player-game rows:** {n_total}  "
                 f"**heat_check stratum:** {n_strat}")
    lines.append("")
    lines.append("## PTS MAE")
    lines.append("")
    lines.append("| slice | n | heuristic | shrinkage(96d) | residual |")
    lines.append("|-------|---|-----------|----------------|----------|")
    for sl in slices:
        n = len(accum[("residual", sl)])
        if not n:
            continue
        lines.append(
            f"| {sl} | {n} | "
            f"{_mae(('heuristic', sl)):.4f} | "
            f"{_mae(('shrinkage', sl)):.4f} | "
            f"{_mae(('residual', sl)):.4f} |"
        )
    lines.append("")
    lines.append("## Ship gate (single-split)")
    lines.append("")
    lines.append(f"- heat_check PTS delta vs heuristic: {strat_delta_vs_heur:+.4f}  "
                 f"(gate: <= -0.10)")
    lines.append(f"- non_heat PTS delta vs heuristic:   {non_delta_vs_heur:+.4f}  "
                 f"(gate: <= +0.05)")
    if wf_results is not None:
        lines.append("")
        lines.append("## WF 4-fold on heat_check stratum")
        lines.append("")
        lines.append("| fold | n_train | n_test | heur_mae | residual_mae | delta |")
        lines.append("|-----:|--------:|-------:|---------:|-------------:|------:|")
        for i, (nt, nv, hm, bm, d) in enumerate(zip(
                wf_results["n_train"], wf_results["n_test"],
                wf_results["heur_mae"], wf_results["residual_mae"],
                wf_results["per_fold_delta"]), 1):
            lines.append(f"| {i} | {nt} | {nv} | {hm:.4f} | {bm:.4f} | {d:+.4f} |")
        wf_pass = sum(1 for d in wf_results["per_fold_delta"] if d < 0.0)
        lines.append(f"\n**WF:** {wf_pass}/4 folds beat heuristic.")

    if ship_final:
        lines.append("")
        lines.append("- **SHIP** -- wire heat_check residual as third stratified "
                     "override in `live_engine.project_from_snapshot`.")
    else:
        causes = []
        if strat_delta_vs_heur > -0.10:
            causes.append(f"heat_check PTS delta {strat_delta_vs_heur:+.4f} > -0.10")
        if non_delta_vs_heur > 0.05:
            causes.append(f"non_heat PTS regressed {non_delta_vs_heur:+.4f} > +0.05")
        if wf_results is not None and not all(
                d < 0.0 for d in wf_results["per_fold_delta"]):
            causes.append("WF 4-fold not 4/4 negative")
        lines.append("")
        lines.append("- **REJECT** -- " + "; ".join(causes))

    report = "\n".join(lines) + "\n"
    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "heat_check_blend_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\n  wrote {out_path}")
    print(f"  SHIP={ship_final}")
    return 0 if ship_final else 1


# ── WF 4-fold ──────────────────────────────────────────────────────────────────

def run_wf_4fold(games, qstats_df, positions, prior_ppm):
    """Walk-forward 4-fold on heat_check stratum.

    Chronologically split games into 5 equal slices. Fold k (0..3):
      * train residual on games[0 : (k+1) * N // 5]
      * test on games[(k+1) * N // 5 : (k+2) * N // 5]   (last fold runs to end)

    For each fold, compute residual vs heuristic PTS MAE on heat_check rows
    only and report the delta. Gate: 4/4 negative (residual wins).
    """
    games = sorted(games)
    N = len(games)
    base = N // 5
    fold_bounds: List[Tuple[int, int]] = []
    for k in range(4):
        train_end = (k + 1) * base
        test_end = (k + 2) * base if k < 3 else N
        fold_bounds.append((train_end, test_end))

    out = {
        "n_train": [], "n_test": [],
        "heur_mae": [], "residual_mae": [], "per_fold_delta": [],
    }
    for (train_end, test_end) in fold_bounds:
        train_games = set(games[:train_end])
        test_games = set(games[train_end:test_end])

        # Build training corpus from train_games only.
        X_tr, y_tr = [], []
        for gid in train_games:
            X_g, y_g = _gid_heat_rows(gid, qstats_df, positions, prior_ppm)
            X_tr.extend(X_g)
            y_tr.extend(y_g)
        if not X_tr:
            out["n_train"].append(0)
            out["n_test"].append(0)
            out["heur_mae"].append(float("nan"))
            out["residual_mae"].append(float("nan"))
            out["per_fold_delta"].append(float("nan"))
            continue
        residual = HeatCheckResidualModel()
        residual.fit(X_tr, y_tr, num_boost_round=200,
                      learning_rate=0.04, num_leaves=15,
                      min_data_in_leaf=15, seed=42)

        heur_errs: List[float] = []
        res_errs: List[float] = []
        n_test = 0
        for gid in test_games:
            snap = v1.build_snapshot(gid, "endQ3", qstats_df)
            if snap is None:
                continue
            actuals = v1.actuals_for_game(gid, qstats_df)
            gdf = qstats_df[qstats_df["game_id"] == gid]
            per_player_q: Dict[int, Dict[str, float]] = {}
            for pid in gdf["player_id"].unique():
                pdf = gdf[gdf["player_id"] == pid]
                pq = {"q1_pts": 0.0, "q2_pts": 0.0, "q3_pts": 0.0,
                      "min_q1": 0.0, "min_q2": 0.0, "min_q3": 0.0}
                for _, r in pdf.iterrows():
                    p = int(r["period"])
                    if p == 1:
                        pq["q1_pts"] = float(r["pts"]); pq["min_q1"] = float(r["min"])
                    elif p == 2:
                        pq["q2_pts"] = float(r["pts"]); pq["min_q2"] = float(r["min"])
                    elif p == 3:
                        pq["q3_pts"] = float(r["pts"]); pq["min_q3"] = float(r["min"])
                per_player_q[int(pid)] = pq
            pig._normalize_snapshot(snap)
            period = int(snap.get("period") or 4)
            clock_rem = pig.parse_clock(snap.get("clock"))
            for p in snap.get("players") or []:
                try:
                    pid_i = int(p.get("player_id"))
                except (TypeError, ValueError):
                    continue
                pq = per_player_q.get(pid_i)
                if not pq:
                    continue
                min_q3 = pq["min_q3"]
                q12_min = pq["min_q1"] + pq["min_q2"]
                if min_q3 <= 0.0 or q12_min <= 0.0:
                    continue
                q3_ppm = pq["q3_pts"] / min_q3
                q12_ppm = (pq["q1_pts"] + pq["q2_pts"]) / q12_min
                if not in_heat_check_stratum(q3_ppm, q12_ppm):
                    continue
                actual = actuals.get((pid_i, "pts"))
                if actual is None:
                    continue
                heur_v = _heuristic_pts(p, period, clock_rem)
                spm, lpm = prior_ppm.get((pid_i, gid), (float("nan"), float("nan")))
                res_v = _residual_pts(
                    p, period, clock_rem, residual,
                    q1_pts=pq["q1_pts"], q2_pts=pq["q2_pts"], q3_pts=pq["q3_pts"],
                    min_q1=pq["min_q1"], min_q2=pq["min_q2"], min_q3=pq["min_q3"],
                    season_ppm=(None if spm != spm else spm),
                    l5_ppm=(None if lpm != lpm else lpm),
                    position_proxy=positions.get(pid_i),
                    heuristic_fallback=heur_v,
                )
                heur_errs.append(abs(heur_v - actual))
                res_errs.append(abs(res_v - actual))
                n_test += 1
        hm = (sum(heur_errs) / len(heur_errs)) if heur_errs else float("nan")
        rm = (sum(res_errs) / len(res_errs)) if res_errs else float("nan")
        out["n_train"].append(len(X_tr))
        out["n_test"].append(n_test)
        out["heur_mae"].append(hm)
        out["residual_mae"].append(rm)
        out["per_fold_delta"].append(rm - hm)
    return out


def _gid_heat_rows(gid, qstats_df, positions, prior_ppm):
    """Return (X, y) rows for the heat_check stratum from this game."""
    gdf = qstats_df[qstats_df["game_id"] == gid]
    X, y = [], []
    for pid in gdf["player_id"].unique():
        pdf = gdf[gdf["player_id"] == pid]
        min_by_q, pts_by_q = {}, {}
        for _, r in pdf.iterrows():
            p = int(r["period"])
            min_by_q[p] = float(r["min"])
            pts_by_q[p] = float(r["pts"])
        min_q1 = min_by_q.get(1, 0.0)
        min_q2 = min_by_q.get(2, 0.0)
        min_q3 = min_by_q.get(3, 0.0)
        q1_pts = pts_by_q.get(1, 0.0)
        q2_pts = pts_by_q.get(2, 0.0)
        q3_pts = pts_by_q.get(3, 0.0)
        if min_q3 <= 0.0 or (min_q1 + min_q2) <= 0.0:
            continue
        q3_ppm = q3_pts / min_q3
        q12_ppm = (q1_pts + q2_pts) / (min_q1 + min_q2)
        if not in_heat_check_stratum(q3_ppm, q12_ppm):
            continue
        q4_min = min_by_q.get(4, 0.0)
        q4_pts = pts_by_q.get(4, 0.0)
        if q4_min < 0.5:
            continue
        target_ppm = q4_pts / q4_min
        spm, lpm = prior_ppm.get((int(pid), gid), (float("nan"), float("nan")))
        X.append(build_feature_row(
            q1_pts=q1_pts, q2_pts=q2_pts, q3_pts=q3_pts,
            min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
            season_pts_per_min=spm, l5_pts_per_min=lpm,
            position_proxy=positions.get(int(pid)),
        ))
        y.append(float(target_ppm))
    return X, y


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--output", default=None)
    ap.add_argument("--skip-wf", action="store_true",
                    help="Skip 4-fold WF even if single-split passes.")
    args = ap.parse_args()
    return run_single(args.max_games, args.output, args.skip_wf)


if __name__ == "__main__":
    sys.exit(main())
