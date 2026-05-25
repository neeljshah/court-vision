"""probe_stratified_blend.py -- tier1-2 (loop 5).

Three-way comparison at endQ3 of:

  1. HEURISTIC baseline   (cycle 88b -- pure foul_trouble_factor heuristic)
  2. GLOBAL learned       (cycle 9d3 -- minute_trajectory model only)
  3. STRATIFIED blend     (new -- residual model on foul_change stratum;
                           global model elsewhere)

Computes PTS / REB / AST MAE on three slices:
  * foul_change stratum  (gate fires)
  * non-foul stratum     (gate doesn't fire)
  * full corpus

SHIP GATE (BOTH must hold):
  * foul_change PTS MAE   improves by >= 0.10 vs cycle-88 HEURISTIC baseline
  * non-foul PTS MAE      does NOT regress > 0.05 vs cycle-9d3 GLOBAL model

If single-split passes, run WF 4-fold on foul_change stratum (sequentially-
split games into 4 chronological folds, train residual on fold 0..k, test on
fold k+1; require 4/4 positive deltas vs heuristic).

Strictly read-only: doesn't mutate predict_in_game.py or live_engine.py.
Wire-up happens AFTER ship verdict, in a follow-up edit.

Run:
    python scripts/probe_stratified_blend.py
    python scripts/probe_stratified_blend.py --max-games 50
    python scripts/probe_stratified_blend.py --skip-wf      (single-split only)
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
import train_foul_residual as tfr            # noqa: E402
from src.prediction.minute_trajectory import (  # noqa: E402
    MinuteTrajectoryModel,
    learned_minute_factor,
)
from src.prediction.minute_trajectory_foul_residual import (  # noqa: E402
    FoulChangeResidualModel,
    in_foul_change_stratum,
)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _num(v, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ── projector variants ────────────────────────────────────────────────────────

def project_with_factors(snap: dict,
                          factor_fn,
                          positions: Dict[int, str],
                          l20_lookup: Dict[int, float],
                          l5_lookup: Dict[int, float],
                          q2_pf_lookup: Dict[int, float],
                          ) -> Dict[Tuple[int, str], float]:
    """Generic projection driver that swaps the per-player foul_factor based
    on ``factor_fn(snap_pf, period, clock_rem, **kwargs) -> float``.

    Identical orchestration to ``retro_inplay_mae.project_snapshot_to_finals``
    but parameterized so we can run three variants from the same loop.
    """
    pig._normalize_snapshot(snap)
    period = int(snap.get("period") or 1)
    clock_rem = pig.parse_clock(snap.get("clock"))
    home_team = snap.get("home_team") or ""
    away_team = snap.get("away_team") or ""
    home_score = _num(snap.get("home_score"))
    away_score = _num(snap.get("away_score"))
    margin = home_score - away_score

    out: Dict[Tuple[int, str], float] = {}
    for p in snap.get("players") or []:
        pid = p.get("player_id")
        try:
            pid_i = int(pid)
        except (TypeError, ValueError):
            continue
        team = p.get("team") or ""
        cur_min = _num(p.get("min"))
        snap_pf = _num(p.get("pf"), default=0.0)
        min_q1 = _num(p.get("min_q1", 0.0))
        min_q2 = _num(p.get("min_q2", 0.0))
        min_q3 = _num(p.get("min_q3", 0.0))
        q3_pf_proxy = max(0.0, snap_pf - 2.0)
        team_is_leading = (
            (team == home_team and margin > 0) or
            (team == away_team and margin < 0)
        )
        ff = factor_fn(
            pid_i=pid_i, snap_pf=snap_pf, q3_pf=q3_pf_proxy,
            min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
            period=period, clock_rem=clock_rem,
            margin=margin, team_is_leading=team_is_leading,
            positions=positions, l20=l20_lookup.get(pid_i),
            l5=l5_lookup.get(pid_i),
            q2_pf=q2_pf_lookup.get(pid_i, 0.0),
        )

        share_played_game = pig.clock_played_share(period, clock_rem)
        proj_min = (cur_min / share_played_game) if share_played_game > 0 else cur_min
        is_star = proj_min >= 30.0
        bf = pig.blowout_factor(
            abs(margin), period, is_star=(is_star and team_is_leading))
        period_elapsed_min = max(0.0, pig.PERIOD_MIN - clock_rem)
        bench_now = pig.is_bench_in_current_period(
            p, period, period_elapsed_min=period_elapsed_min)
        player_basis = cur_min if bench_now else None
        for stat in pig.STATS:
            cur = _num(p.get(stat))
            final = pig.project_final(
                cur, period, clock_rem,
                pace_factor=1.0, foul_factor=ff, blow_factor=bf,
                player_clock_played_min=player_basis,
            )
            out[(pid_i, stat)] = float(final)
    return out


def _heuristic_factor_fn(pid_i, snap_pf, q3_pf, min_q1, min_q2, min_q3,
                          period, clock_rem, margin, team_is_leading,
                          positions, l20, l5, q2_pf):
    from src.prediction.live_factors import foul_trouble_factor
    return foul_trouble_factor(snap_pf, period, clock_rem)


def _global_factor_fn(model):
    def fn(pid_i, snap_pf, q3_pf, min_q1, min_q2, min_q3, period, clock_rem,
           margin, team_is_leading, positions, l20, l5, q2_pf):
        if period != 4:
            from src.prediction.live_factors import foul_trouble_factor
            return foul_trouble_factor(snap_pf, period, clock_rem)
        return learned_minute_factor(
            model,
            pf_through_q3=snap_pf, q3_pf=q3_pf,
            min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
            score_margin_abs=abs(margin),
            is_leading_team=1 if team_is_leading else 0,
            position_proxy=positions.get(pid_i),
            l20_min=l20, l5_min=l5,
        )
    return fn


def _blend_factor_fn(global_model, residual_model):
    from src.prediction.minute_trajectory_foul_residual import (
        stratified_minute_factor,
    )

    def fn(pid_i, snap_pf, q3_pf, min_q1, min_q2, min_q3, period, clock_rem,
           margin, team_is_leading, positions, l20, l5, q2_pf):
        if period != 4:
            from src.prediction.live_factors import foul_trouble_factor
            return foul_trouble_factor(snap_pf, period, clock_rem)
        return stratified_minute_factor(
            global_model=global_model,
            residual_model=residual_model,
            pf_through_q3=snap_pf, q3_pf=q3_pf,
            min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
            score_margin_abs=abs(margin),
            is_leading_team=1 if team_is_leading else 0,
            position_proxy=positions.get(pid_i),
            l20_min=l20, l5_min=l5,
            q2_pf=q2_pf,
        )
    return fn


# ── shared per-game lookups ───────────────────────────────────────────────────

def build_per_game_lookups(qstats_df, games, pid_log_index):
    """Return (per_game_l20, per_game_l5, per_game_q2_pf, per_game_q3_pf,
    per_game_pf_through_q3) -- all dict[gid] -> dict[pid] -> value.
    """
    per_l20: Dict[str, Dict[int, float]] = {}
    per_l5: Dict[str, Dict[int, float]] = {}
    per_q2: Dict[str, Dict[int, float]] = {}
    per_q3: Dict[str, Dict[int, float]] = {}
    per_total: Dict[str, Dict[int, float]] = {}
    for gid in games:
        target_date = tmt.find_game_date_for_game(gid, qstats_df, pid_log_index)
        gdf = qstats_df[qstats_df["game_id"] == gid]
        gpids = set(int(pid) for pid in gdf["player_id"].unique())
        l20m: Dict[int, float] = {}
        l5m: Dict[int, float] = {}
        q2m: Dict[int, float] = {}
        q3m: Dict[int, float] = {}
        totalm: Dict[int, float] = {}
        for pid in gpids:
            l20 = tmt.rolling_mean_min(pid, target_date, 20, pid_log_index)
            l5 = tmt.rolling_mean_min(pid, target_date, 5, pid_log_index)
            if l20 is not None:
                l20m[pid] = l20
            if l5 is not None:
                l5m[pid] = l5
            pdf = gdf[gdf["player_id"] == pid]
            q2_pf = 0.0
            q3_pf = 0.0
            total = 0.0
            for _, r in pdf.iterrows():
                per = int(r["period"])
                pf_v = float(r["pf"])
                if per == 2:
                    q2_pf = pf_v
                if per == 3:
                    q3_pf = pf_v
                if per <= 3:
                    total += pf_v
            q2m[pid] = q2_pf
            q3m[pid] = q3_pf
            totalm[pid] = total
        per_l20[gid] = l20m
        per_l5[gid] = l5m
        per_q2[gid] = q2m
        per_q3[gid] = q3m
        per_total[gid] = totalm
    return per_l20, per_l5, per_q2, per_q3, per_total


# ── single-split eval ─────────────────────────────────────────────────────────

def run_single(max_games: Optional[int], output: Optional[str],
                skip_wf: bool) -> int:
    global_model = MinuteTrajectoryModel.load()
    if global_model is None:
        print("  ERROR: global minute_trajectory artifact missing. "
              "Run scripts/train_minute_trajectory.py first.")
        return 2
    residual_model = FoulChangeResidualModel.load()
    if residual_model is None:
        print("  ERROR: residual artifact missing. "
              "Run scripts/train_foul_residual.py first.")
        return 2
    print("  loaded global + residual models.")

    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    positions = tmt.load_positions()
    pid_log_index = tmt.load_player_gamelog_minutes()
    print(f"  {len(games)} games  {len(positions)} positions  "
          f"{len(pid_log_index)} player gamelogs indexed")

    print("  building per-game L20/L5/q2_pf/q3_pf lookups...")
    per_l20, per_l5, per_q2, per_q3, per_total = build_per_game_lookups(
        qstats_df, games, pid_log_index)

    # MAE accumulators per (variant, slice, stat).
    variants = ("heuristic", "global", "blend")
    slices = ("foul_change", "non_foul", "all")
    accum: Dict[Tuple[str, str, str], List[float]] = {
        (v, s, st): [] for v in variants for s in slices for st in STATS
    }
    n_total = 0
    n_strat = 0

    for gid in games:
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)

        heur = project_with_factors(snap, _heuristic_factor_fn, positions,
                                     per_l20.get(gid, {}), per_l5.get(gid, {}),
                                     per_q2.get(gid, {}))
        glob = project_with_factors(snap, _global_factor_fn(global_model),
                                     positions,
                                     per_l20.get(gid, {}), per_l5.get(gid, {}),
                                     per_q2.get(gid, {}))
        blnd = project_with_factors(snap,
                                     _blend_factor_fn(global_model, residual_model),
                                     positions,
                                     per_l20.get(gid, {}), per_l5.get(gid, {}),
                                     per_q2.get(gid, {}))

        seen_pids = set(pid for pid, _ in heur.keys())
        for pid in seen_pids:
            q3_pf = per_q3.get(gid, {}).get(pid, 0.0)
            total_pf = per_total.get(gid, {}).get(pid, 0.0)
            in_strat = in_foul_change_stratum(
                q3_pf=q3_pf, pf_through_q3=total_pf)
            n_total += 1
            if in_strat:
                n_strat += 1
            slice_keys = ["all", "foul_change" if in_strat else "non_foul"]
            for stat in STATS:
                actual = actuals.get((pid, stat))
                if actual is None:
                    continue
                for vname, projs in (("heuristic", heur),
                                     ("global", glob),
                                     ("blend", blnd)):
                    pred = projs.get((pid, stat))
                    if pred is None:
                        continue
                    err = abs(pred - actual)
                    for s in slice_keys:
                        accum[(vname, s, stat)].append(err)

    def _mae(key):
        xs = accum.get(key, [])
        return (sum(xs) / len(xs)) if xs else float("nan")

    # Headline deltas.
    pts_strat_heur = _mae(("heuristic", "foul_change", "pts"))
    pts_strat_glob = _mae(("global", "foul_change", "pts"))
    pts_strat_blnd = _mae(("blend", "foul_change", "pts"))
    pts_non_heur = _mae(("heuristic", "non_foul", "pts"))
    pts_non_glob = _mae(("global", "non_foul", "pts"))
    pts_non_blnd = _mae(("blend", "non_foul", "pts"))

    strat_delta_vs_heur = pts_strat_blnd - pts_strat_heur
    non_delta_vs_glob = pts_non_blnd - pts_non_glob

    ship_single = (strat_delta_vs_heur <= -0.10) and (non_delta_vs_glob <= 0.05)

    print(f"\n  foul_change stratum n={len(accum[('blend','foul_change','pts')])}")
    print(f"    heuristic PTS MAE: {pts_strat_heur:.4f}")
    print(f"    global    PTS MAE: {pts_strat_glob:.4f}")
    print(f"    BLEND     PTS MAE: {pts_strat_blnd:.4f}  "
          f"(delta vs heur: {strat_delta_vs_heur:+.4f})")
    print(f"\n  non_foul stratum n={len(accum[('blend','non_foul','pts')])}")
    print(f"    heuristic PTS MAE: {pts_non_heur:.4f}")
    print(f"    global    PTS MAE: {pts_non_glob:.4f}")
    print(f"    BLEND     PTS MAE: {pts_non_blnd:.4f}  "
          f"(delta vs glob: {non_delta_vs_glob:+.4f})")

    # WF 4-fold if single-split passes.
    wf_results = None
    if ship_single and not skip_wf:
        print("\n  single-split PASSES -- running WF 4-fold on foul_change stratum...")
        wf_results = run_wf_4fold(games, qstats_df, positions, pid_log_index,
                                    per_l20, per_l5, per_q2, per_q3, per_total)

    ship_final = ship_single and (wf_results is None or all(
        d <= -0.0 for d in wf_results["per_fold_delta"]))

    # Markdown report.
    lines: List[str] = []
    lines.append("# stratified_blend probe -- tier1-2 (loop 5)")
    lines.append("")
    lines.append(f"**Games:** {len(games)}  "
                 f"**player-game rows:** {n_total}  "
                 f"**foul_change stratum:** {n_strat}")
    lines.append("")
    lines.append("Three-way comparison at endQ3:")
    lines.append("- **heuristic** -- cycle 88b foul_trouble_factor")
    lines.append("- **global** -- cycle 9d3 minute_trajectory model")
    lines.append("- **blend** -- residual model on foul_change gate; global elsewhere")
    lines.append("")
    for stat in ("pts", "reb", "ast"):
        lines.append(f"## {stat.upper()} MAE")
        lines.append("")
        lines.append("| slice | n | heuristic | global | blend |")
        lines.append("|-------|---|-----------|--------|-------|")
        for sl in slices:
            n = len(accum[("blend", sl, stat)])
            if not n:
                continue
            lines.append(
                f"| {sl} | {n} | "
                f"{_mae(('heuristic', sl, stat)):.4f} | "
                f"{_mae(('global', sl, stat)):.4f} | "
                f"{_mae(('blend', sl, stat)):.4f} |"
            )
        lines.append("")

    lines.append("## Ship gate (single-split)")
    lines.append("")
    lines.append(f"- foul_change PTS delta vs heuristic: {strat_delta_vs_heur:+.4f}  "
                 f"(gate: <= -0.10)")
    lines.append(f"- non_foul PTS delta vs global:      {non_delta_vs_glob:+.4f}  "
                 f"(gate: <= +0.05)")
    if wf_results is not None:
        lines.append("")
        lines.append("## WF 4-fold on foul_change stratum")
        lines.append("")
        lines.append("| fold | n_train | n_test | heur_mae | blend_mae | delta |")
        lines.append("|-----:|--------:|-------:|---------:|----------:|------:|")
        for i, (nt, nv, hm, bm, d) in enumerate(zip(
                wf_results["n_train"], wf_results["n_test"],
                wf_results["heur_mae"], wf_results["blend_mae"],
                wf_results["per_fold_delta"]), 1):
            lines.append(f"| {i} | {nt} | {nv} | {hm:.4f} | {bm:.4f} | {d:+.4f} |")
        wf_pass = sum(1 for d in wf_results["per_fold_delta"] if d <= 0.0)
        lines.append(f"\n**WF:** {wf_pass}/4 folds beat heuristic.")

    if ship_final:
        lines.append("")
        lines.append("- **SHIP** -- wire `_USE_FOUL_RESIDUAL=True` into "
                     "`live_engine.project_from_snapshot` via stratified dispatch.")
    else:
        causes = []
        if strat_delta_vs_heur > -0.10:
            causes.append("foul_change PTS did not improve >= 0.10")
        if non_delta_vs_glob > 0.05:
            causes.append("non_foul PTS regressed > 0.05")
        if wf_results is not None and not all(
                d <= 0.0 for d in wf_results["per_fold_delta"]):
            causes.append("WF 4-fold not 4/4 positive")
        lines.append("")
        lines.append("- **REJECT** -- " + "; ".join(causes))

    report = "\n".join(lines) + "\n"
    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "stratified_blend_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\n  wrote {out_path}")
    print(f"  SHIP={ship_final}")
    return 0 if ship_final else 1


# ── WF 4-fold ──────────────────────────────────────────────────────────────────

def run_wf_4fold(games, qstats_df, positions, pid_log_index,
                 per_l20, per_l5, per_q2, per_q3, per_total):
    """Walk-forward 4-fold on the foul_change stratum.

    Chronologically split games into 5 equal slices. Fold k (1..4):
      * train residual on games[0 : (k+1)/5 * N]
      * test on games[(k+1)/5 * N : (k+2)/5 * N] when k < 4 else remainder.

    For each fold, compute blend vs heuristic PTS MAE on the foul_change
    stratum and report the delta. Gate: 4/4 negative (blend wins).
    """
    games = sorted(games)
    N = len(games)
    # 5 slices: train start always 0; the test slice marches forward.
    fold_bounds: List[Tuple[int, int]] = []
    base = N // 5
    for k in range(4):
        # train ends at (k+1) * base; test runs (k+1)*base : (k+2)*base
        train_end = (k + 1) * base
        test_end = (k + 2) * base if k < 3 else N
        fold_bounds.append((train_end, test_end))

    out = {
        "n_train": [], "n_test": [],
        "heur_mae": [], "blend_mae": [], "per_fold_delta": [],
    }
    for (train_end, test_end) in fold_bounds:
        train_games = set(games[:train_end])
        test_games = set(games[train_end:test_end])
        # Build foul_change corpus restricted to training games.
        X_tr, y_tr = [], []
        for gid in train_games:
            X_g, y_g = _gid_foul_rows(
                gid, qstats_df, positions, pid_log_index)
            X_tr.extend(X_g)
            y_tr.extend(y_g)
        if not X_tr:
            out["n_train"].append(0)
            out["n_test"].append(0)
            out["heur_mae"].append(float("nan"))
            out["blend_mae"].append(float("nan"))
            out["per_fold_delta"].append(float("nan"))
            continue
        residual = FoulChangeResidualModel()
        residual.fit(X_tr, y_tr, num_boost_round=300,
                      learning_rate=0.04, num_leaves=15,
                      min_data_in_leaf=20, seed=42)

        global_model = MinuteTrajectoryModel.load()
        # Evaluate on test games' foul_change rows only.
        heur_errs: List[float] = []
        blnd_errs: List[float] = []
        n_test = 0
        for gid in test_games:
            snap = v1.build_snapshot(gid, "endQ3", qstats_df)
            if snap is None:
                continue
            actuals = v1.actuals_for_game(gid, qstats_df)
            heur = project_with_factors(snap, _heuristic_factor_fn, positions,
                                         per_l20.get(gid, {}), per_l5.get(gid, {}),
                                         per_q2.get(gid, {}))
            blnd = project_with_factors(snap,
                                         _blend_factor_fn(global_model, residual),
                                         positions,
                                         per_l20.get(gid, {}), per_l5.get(gid, {}),
                                         per_q2.get(gid, {}))
            seen = set(pid for pid, _ in heur.keys())
            for pid in seen:
                q3_pf = per_q3.get(gid, {}).get(pid, 0.0)
                total_pf = per_total.get(gid, {}).get(pid, 0.0)
                if not in_foul_change_stratum(
                        q3_pf=q3_pf, pf_through_q3=total_pf):
                    continue
                actual = actuals.get((pid, "pts"))
                if actual is None:
                    continue
                hp = heur.get((pid, "pts"))
                bp = blnd.get((pid, "pts"))
                if hp is None or bp is None:
                    continue
                heur_errs.append(abs(hp - actual))
                blnd_errs.append(abs(bp - actual))
                n_test += 1
        hm = (sum(heur_errs) / len(heur_errs)) if heur_errs else float("nan")
        bm = (sum(blnd_errs) / len(blnd_errs)) if blnd_errs else float("nan")
        out["n_train"].append(len(X_tr))
        out["n_test"].append(n_test)
        out["heur_mae"].append(hm)
        out["blend_mae"].append(bm)
        out["per_fold_delta"].append(bm - hm)
    return out


def _gid_foul_rows(gid, qstats_df, positions, pid_log_index):
    """Return (X, y) rows for the foul_change stratum from this game."""
    from src.prediction.minute_trajectory_foul_residual import (
        build_feature_row, in_foul_change_stratum,
    )
    gdf = qstats_df[qstats_df["game_id"] == gid]
    target_date = tmt.find_game_date_for_game(gid, qstats_df, pid_log_index)
    X, y = [], []
    for pid in gdf["player_id"].unique():
        pdf = gdf[gdf["player_id"] == pid]
        min_by_q, pf_by_q = {}, {}
        for _, r in pdf.iterrows():
            p = int(r["period"])
            min_by_q[p] = float(r["min"])
            pf_by_q[p] = float(r["pf"])
        min_q1 = min_by_q.get(1, 0.0)
        min_q2 = min_by_q.get(2, 0.0)
        min_q3 = min_by_q.get(3, 0.0)
        if min_q1 + min_q2 + min_q3 <= 0.5:
            continue
        q2_pf = pf_by_q.get(2, 0.0)
        q3_pf = pf_by_q.get(3, 0.0)
        pf_through = pf_by_q.get(1, 0.0) + pf_by_q.get(2, 0.0) + pf_by_q.get(3, 0.0)
        if not in_foul_change_stratum(q3_pf=q3_pf, pf_through_q3=pf_through):
            continue
        rem = 0.0
        for _, r in pdf.iterrows():
            if int(r["period"]) >= 4:
                rem += float(r["min"])
        pos_str = positions.get(int(pid))
        l20 = tmt.rolling_mean_min(int(pid), target_date, 20, pid_log_index)
        l5 = tmt.rolling_mean_min(int(pid), target_date, 5, pid_log_index)
        X.append(build_feature_row(
            pf_through_q3=pf_through, q3_pf=q3_pf,
            min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
            position_proxy=pos_str, l20_min=l20, l5_min=l5, q2_pf=q2_pf,
        ))
        y.append(float(rem))
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
