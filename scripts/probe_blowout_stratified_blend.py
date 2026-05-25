"""probe_blowout_stratified_blend.py -- cycle 102a (loop 5).

Three-way comparison at endQ3 of blowout-aware projections:

  1. HEURISTIC    -- cycle 88f blowout_factor only (no residual)
  2. BLEND        -- residual replaces heuristic when blowout_flip gate fires
                     (live-proxy gate at inference; ground-truth gate for
                     stratum membership in the eval slice)

Computes PTS / REB / AST MAE on three slices:
  * blowout_flip stratum (gate fires on the GROUND-TRUTH final-margin classifier
    so we measure improvement on the actual blowout subset)
  * non-blowout stratum (everything else)
  * full corpus

SHIP GATE (BOTH must hold):
  * blowout_flip PTS MAE improves by >= 0.10 vs HEURISTIC baseline
  * non_blowout PTS MAE does NOT regress > 0.05 vs HEURISTIC baseline
  * WF 4/4 negative on blowout_flip stratum

Strictly read-only: doesn't mutate predict_in_game.py or live_engine.py.

Run:
    python scripts/probe_blowout_stratified_blend.py
    python scripts/probe_blowout_stratified_blend.py --max-games 100
    python scripts/probe_blowout_stratified_blend.py --skip-wf
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
import train_blowout_residual as tbr         # noqa: E402
from src.prediction.blowout_residual import (  # noqa: E402
    BlowoutResidualModel,
    build_feature_row as blowout_build_feature_row,
    in_blowout_flip_stratum,
    in_blowout_flip_live_proxy,
    stratified_blowout_factor,
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

def project_with_blow_fn(snap: dict,
                          blow_fn,
                          positions: Dict[int, str],
                          l20_lookup: Dict[int, float],
                          l5_lookup: Dict[int, float],
                          per_team_q_margins: Dict[str, Dict[int, float]],
                          ) -> Dict[Tuple[int, str], float]:
    """Generic projection driver that swaps the per-player blow_factor based
    on ``blow_fn(...) -> float``. Same orchestration as retro_inplay_mae but
    parameterized so we can run heuristic vs blend from one loop.
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

        # Compute per-team signed Q3 margin + velocity from per_team_q_margins.
        team_q = per_team_q_margins.get(team, {})
        opp_candidates = [t for t in per_team_q_margins if t != team]
        opp = opp_candidates[0] if opp_candidates else ""
        opp_q = per_team_q_margins.get(opp, {}) if opp else {}
        q3_signed = sum(team_q.get(q, 0.0) - opp_q.get(q, 0.0) for q in (1, 2, 3))
        q2_signed = sum(team_q.get(q, 0.0) - opp_q.get(q, 0.0) for q in (1, 2))
        velocity = q3_signed - q2_signed

        share_played_game = pig.clock_played_share(period, clock_rem)
        proj_min = (cur_min / share_played_game) if share_played_game > 0 else cur_min
        is_star = proj_min >= 30.0

        # Default heuristic blow factor (cycle-88f).
        heuristic_bf = pig.blowout_factor(
            abs(margin), period, is_star=(is_star and team_is_leading))

        bf = blow_fn(
            pid_i=pid_i,
            heuristic_factor=heuristic_bf,
            snap_pf=snap_pf, q3_pf=q3_pf_proxy,
            min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
            period=period, clock_rem=clock_rem,
            margin=margin, team_is_leading=team_is_leading,
            q3_signed=q3_signed, velocity=velocity,
            positions=positions,
            l20=l20_lookup.get(pid_i), l5=l5_lookup.get(pid_i),
        )

        period_elapsed_min = max(0.0, pig.PERIOD_MIN - clock_rem)
        bench_now = pig.is_bench_in_current_period(
            p, period, period_elapsed_min=period_elapsed_min)
        player_basis = cur_min if bench_now else None
        for stat in pig.STATS:
            cur = _num(p.get(stat))
            final = pig.project_final(
                cur, period, clock_rem,
                pace_factor=1.0, foul_factor=1.0, blow_factor=bf,
                player_clock_played_min=player_basis,
            )
            out[(pid_i, stat)] = float(final)
    return out


def _heuristic_blow_fn(*, pid_i, heuristic_factor, snap_pf, q3_pf, min_q1,
                        min_q2, min_q3, period, clock_rem, margin,
                        team_is_leading, q3_signed, velocity, positions,
                        l20, l5):
    return heuristic_factor


def _blend_blow_fn(residual_model):
    def fn(*, pid_i, heuristic_factor, snap_pf, q3_pf, min_q1, min_q2, min_q3,
           period, clock_rem, margin, team_is_leading, q3_signed, velocity,
           positions, l20, l5):
        if period != 4:
            return heuristic_factor
        return stratified_blowout_factor(
            heuristic_factor=heuristic_factor,
            residual_model=residual_model,
            pf_through_q3=snap_pf, q3_pf=q3_pf,
            min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
            score_margin_abs=abs(q3_signed),
            score_margin_signed_q3=q3_signed,
            score_velocity_q3=velocity,
            is_leading_team=1 if team_is_leading else 0,
            position_proxy=positions.get(pid_i),
            l20_min=l20, l5_min=l5,
        )
    return fn


# ── per-game lookups ──────────────────────────────────────────────────────────

def build_per_game_lookups(qstats_df, games, pid_log_index):
    """Return per-game (L20, L5, team_q_margins, pid_to_team, final_margins_by_team).

    final_margins_by_team[gid][team] -> absolute final margin (signed-from-team-POV).
    q3_margins_by_team[gid][team] -> absolute Q3 margin.
    """
    per_l20: Dict[str, Dict[int, float]] = {}
    per_l5: Dict[str, Dict[int, float]] = {}
    per_team_q: Dict[str, Dict[str, Dict[int, float]]] = {}
    per_pid_team: Dict[str, Dict[int, str]] = {}
    per_q3_margins: Dict[str, Dict[str, float]] = {}
    per_final_margins: Dict[str, Dict[str, float]] = {}

    for gid in games:
        target_date = tmt.find_game_date_for_game(gid, qstats_df, pid_log_index)
        gdf = qstats_df[qstats_df["game_id"] == gid]
        gpids = set(int(pid) for pid in gdf["player_id"].unique())

        l20m: Dict[int, float] = {}
        l5m: Dict[int, float] = {}
        for pid in gpids:
            l20 = tmt.rolling_mean_min(pid, target_date, 20, pid_log_index)
            l5 = tmt.rolling_mean_min(pid, target_date, 5, pid_log_index)
            if l20 is not None:
                l20m[pid] = l20
            if l5 is not None:
                l5m[pid] = l5
        per_l20[gid] = l20m
        per_l5[gid] = l5m

        pid_to_team, _home, _away = v1.load_team_map(gid)
        per_pid_team[gid] = pid_to_team

        teams_q: Dict[str, Dict[int, float]] = {}
        for _, r in gdf.iterrows():
            try:
                pid_i = int(r["player_id"])
            except (TypeError, ValueError):
                continue
            t = pid_to_team.get(pid_i, "")
            if not t:
                continue
            per = int(r["period"])
            teams_q.setdefault(t, {}).setdefault(per, 0.0)
            teams_q[t][per] += float(r["pts"])
        per_team_q[gid] = teams_q

        teams = list(teams_q.keys())
        q3_marg: Dict[str, float] = {}
        final_marg: Dict[str, float] = {}
        if len(teams) >= 2:
            for t in teams:
                opp_candidates = [o for o in teams if o != t]
                if not opp_candidates:
                    continue
                opp = opp_candidates[0]
                my_q = teams_q.get(t, {})
                op_q = teams_q.get(opp, {})
                q3_s = sum(my_q.get(q, 0.0) - op_q.get(q, 0.0) for q in (1, 2, 3))
                all_q = set(my_q.keys()) | set(op_q.keys())
                final_s = sum(my_q.get(q, 0.0) - op_q.get(q, 0.0) for q in all_q)
                q3_marg[t] = abs(q3_s)
                final_marg[t] = abs(final_s)
        per_q3_margins[gid] = q3_marg
        per_final_margins[gid] = final_marg

    return per_l20, per_l5, per_team_q, per_pid_team, per_q3_margins, per_final_margins


# ── single-split eval ─────────────────────────────────────────────────────────

def run_single(max_games: Optional[int], output: Optional[str],
                skip_wf: bool) -> int:
    residual_model = BlowoutResidualModel.load()
    if residual_model is None:
        print("  ERROR: blowout_residual artifact missing. "
              "Run scripts/train_blowout_residual.py first.")
        return 2
    print("  loaded blowout_residual model.")

    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    positions = tmt.load_positions()
    pid_log_index = tmt.load_player_gamelog_minutes()
    print(f"  {len(games)} games  {len(positions)} positions  "
          f"{len(pid_log_index)} player gamelogs indexed")

    print("  building per-game lookups...")
    (per_l20, per_l5, per_team_q, per_pid_team,
     per_q3_margins, per_final_margins) = build_per_game_lookups(
        qstats_df, games, pid_log_index)

    variants = ("heuristic", "blend")
    slices = ("blowout_flip", "non_blowout", "all")
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
        team_q = per_team_q.get(gid, {})
        pid_to_team = per_pid_team.get(gid, {})

        heur = project_with_blow_fn(snap, _heuristic_blow_fn, positions,
                                     per_l20.get(gid, {}), per_l5.get(gid, {}),
                                     team_q)
        blnd = project_with_blow_fn(snap, _blend_blow_fn(residual_model),
                                     positions,
                                     per_l20.get(gid, {}), per_l5.get(gid, {}),
                                     team_q)

        seen_pids = set(pid for pid, _ in heur.keys())
        q3_m = per_q3_margins.get(gid, {})
        final_m = per_final_margins.get(gid, {})

        for pid in seen_pids:
            team = pid_to_team.get(pid, "")
            q3_abs = q3_m.get(team, 0.0) if team else 0.0
            final_abs = final_m.get(team, 0.0) if team else 0.0
            in_strat = in_blowout_flip_stratum(
                q3_margin_abs=q3_abs, final_margin_abs=final_abs)
            n_total += 1
            if in_strat:
                n_strat += 1
            slice_keys = ["all", "blowout_flip" if in_strat else "non_blowout"]
            for stat in STATS:
                actual = actuals.get((pid, stat))
                if actual is None:
                    continue
                for vname, projs in (("heuristic", heur), ("blend", blnd)):
                    pred = projs.get((pid, stat))
                    if pred is None:
                        continue
                    err = abs(pred - actual)
                    for s in slice_keys:
                        accum[(vname, s, stat)].append(err)

    def _mae(key):
        xs = accum.get(key, [])
        return (sum(xs) / len(xs)) if xs else float("nan")

    pts_strat_heur = _mae(("heuristic", "blowout_flip", "pts"))
    pts_strat_blnd = _mae(("blend", "blowout_flip", "pts"))
    pts_non_heur = _mae(("heuristic", "non_blowout", "pts"))
    pts_non_blnd = _mae(("blend", "non_blowout", "pts"))

    strat_delta_vs_heur = pts_strat_blnd - pts_strat_heur
    non_delta_vs_heur = pts_non_blnd - pts_non_heur

    ship_single = (strat_delta_vs_heur <= -0.10) and (non_delta_vs_heur <= 0.05)

    print(f"\n  blowout_flip stratum n={len(accum[('blend','blowout_flip','pts')])}")
    print(f"    heuristic PTS MAE: {pts_strat_heur:.4f}")
    print(f"    BLEND     PTS MAE: {pts_strat_blnd:.4f}  "
          f"(delta vs heur: {strat_delta_vs_heur:+.4f})")
    print(f"\n  non_blowout stratum n={len(accum[('blend','non_blowout','pts')])}")
    print(f"    heuristic PTS MAE: {pts_non_heur:.4f}")
    print(f"    BLEND     PTS MAE: {pts_non_blnd:.4f}  "
          f"(delta vs heur: {non_delta_vs_heur:+.4f})")

    wf_results = None
    if ship_single and not skip_wf:
        print("\n  single-split PASSES -- running WF 4-fold on blowout_flip stratum...")
        wf_results = run_wf_4fold(games, qstats_df, positions, pid_log_index,
                                    per_l20, per_l5, per_team_q, per_pid_team,
                                    per_q3_margins, per_final_margins)

    ship_final = ship_single and (wf_results is None or all(
        d <= 0.0 for d in wf_results["per_fold_delta"]
        if d == d  # filter NaN
    ) and len([d for d in wf_results["per_fold_delta"] if d == d]) >= 4)

    lines: List[str] = []
    lines.append("# blowout_stratified_blend probe -- cycle 102a (loop 5)")
    lines.append("")
    lines.append(f"**Games:** {len(games)}  "
                 f"**player-game rows:** {n_total}  "
                 f"**blowout_flip stratum:** {n_strat}")
    lines.append("")
    lines.append("Two-way comparison at endQ3:")
    lines.append("- **heuristic** -- cycle 88f blowout_factor")
    lines.append("- **blend** -- residual on blowout_flip live proxy; heuristic elsewhere")
    lines.append("")
    for stat in ("pts", "reb", "ast"):
        lines.append(f"## {stat.upper()} MAE")
        lines.append("")
        lines.append("| slice | n | heuristic | blend |")
        lines.append("|-------|---|-----------|-------|")
        for sl in slices:
            n = len(accum[("blend", sl, stat)])
            if not n:
                continue
            lines.append(
                f"| {sl} | {n} | "
                f"{_mae(('heuristic', sl, stat)):.4f} | "
                f"{_mae(('blend', sl, stat)):.4f} |"
            )
        lines.append("")

    lines.append("## Ship gate (single-split)")
    lines.append("")
    lines.append(f"- blowout_flip PTS delta vs heuristic: {strat_delta_vs_heur:+.4f}  "
                 f"(gate: <= -0.10)")
    lines.append(f"- non_blowout PTS delta vs heuristic: {non_delta_vs_heur:+.4f}  "
                 f"(gate: <= +0.05)")
    if wf_results is not None:
        lines.append("")
        lines.append("## WF 4-fold on blowout_flip stratum")
        lines.append("")
        lines.append("| fold | n_train | n_test | heur_mae | blend_mae | delta |")
        lines.append("|-----:|--------:|-------:|---------:|----------:|------:|")
        for i, (nt, nv, hm, bm, d) in enumerate(zip(
                wf_results["n_train"], wf_results["n_test"],
                wf_results["heur_mae"], wf_results["blend_mae"],
                wf_results["per_fold_delta"]), 1):
            lines.append(f"| {i} | {nt} | {nv} | {hm:.4f} | {bm:.4f} | {d:+.4f} |")
        wf_pass = sum(1 for d in wf_results["per_fold_delta"] if d == d and d <= 0.0)
        lines.append(f"\n**WF:** {wf_pass}/4 folds beat heuristic.")

    if ship_final:
        lines.append("")
        lines.append("- **SHIP** -- wire `_USE_BLOWOUT_RESIDUAL=True` into "
                     "`live_engine.project_from_snapshot` via stratified dispatch.")
    else:
        causes = []
        if strat_delta_vs_heur > -0.10:
            causes.append("blowout_flip PTS did not improve >= 0.10")
        if non_delta_vs_heur > 0.05:
            causes.append("non_blowout PTS regressed > 0.05")
        if wf_results is not None:
            valid = [d for d in wf_results["per_fold_delta"] if d == d]
            wf_pass = sum(1 for d in valid if d <= 0.0)
            if wf_pass < 4:
                causes.append(f"WF {wf_pass}/4 folds negative")
        lines.append("")
        lines.append("- **REJECT** -- " + "; ".join(causes))

    report = "\n".join(lines) + "\n"
    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "blowout_stratified_blend_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\n  wrote {out_path}")
    print(f"  SHIP={ship_final}")
    return 0 if ship_final else 1


# ── WF 4-fold ──────────────────────────────────────────────────────────────────

def run_wf_4fold(games, qstats_df, positions, pid_log_index,
                  per_l20, per_l5, per_team_q, per_pid_team,
                  per_q3_margins, per_final_margins):
    games = sorted(games)
    N = len(games)
    fold_bounds: List[Tuple[int, int]] = []
    base = N // 5
    for k in range(4):
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
        X_tr, y_tr = [], []
        for gid in train_games:
            X_g, y_g = _gid_blowout_rows(
                gid, qstats_df, positions, pid_log_index,
                per_pid_team, per_team_q)
            X_tr.extend(X_g)
            y_tr.extend(y_g)
        if not X_tr:
            out["n_train"].append(0)
            out["n_test"].append(0)
            out["heur_mae"].append(float("nan"))
            out["blend_mae"].append(float("nan"))
            out["per_fold_delta"].append(float("nan"))
            continue
        residual = BlowoutResidualModel()
        residual.fit(X_tr, y_tr, num_boost_round=300,
                      learning_rate=0.04, num_leaves=15,
                      min_data_in_leaf=20, seed=42)

        heur_errs: List[float] = []
        blnd_errs: List[float] = []
        n_test = 0
        for gid in test_games:
            snap = v1.build_snapshot(gid, "endQ3", qstats_df)
            if snap is None:
                continue
            actuals = v1.actuals_for_game(gid, qstats_df)
            team_q = per_team_q.get(gid, {})
            pid_to_team = per_pid_team.get(gid, {})
            heur = project_with_blow_fn(snap, _heuristic_blow_fn, positions,
                                         per_l20.get(gid, {}), per_l5.get(gid, {}),
                                         team_q)
            blnd = project_with_blow_fn(snap, _blend_blow_fn(residual),
                                         positions,
                                         per_l20.get(gid, {}), per_l5.get(gid, {}),
                                         team_q)
            seen = set(pid for pid, _ in heur.keys())
            q3_m = per_q3_margins.get(gid, {})
            final_m = per_final_margins.get(gid, {})
            for pid in seen:
                team = pid_to_team.get(pid, "")
                q3_abs = q3_m.get(team, 0.0) if team else 0.0
                final_abs = final_m.get(team, 0.0) if team else 0.0
                if not in_blowout_flip_stratum(
                        q3_margin_abs=q3_abs, final_margin_abs=final_abs):
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
        if hm == hm and bm == bm:
            out["per_fold_delta"].append(bm - hm)
        else:
            out["per_fold_delta"].append(float("nan"))
    return out


def _gid_blowout_rows(gid, qstats_df, positions, pid_log_index,
                       per_pid_team, per_team_q):
    """Return (X, y) rows for the blowout_flip stratum from this game."""
    gdf = qstats_df[qstats_df["game_id"] == gid]
    pid_to_team = per_pid_team.get(gid, {})
    team_q = per_team_q.get(gid, {})
    if not pid_to_team or not team_q:
        return [], []
    teams = list(team_q.keys())
    if len(teams) < 2:
        return [], []
    target_date = tmt.find_game_date_for_game(gid, qstats_df, pid_log_index)

    def margins_for_team(team: str) -> Tuple[float, float, float]:
        opp_candidates = [t for t in teams if t != team]
        if not opp_candidates:
            return 0.0, 0.0, 0.0
        opp = opp_candidates[0]
        my_q = team_q.get(team, {})
        op_q = team_q.get(opp, {})
        q3_s = sum(my_q.get(q, 0.0) - op_q.get(q, 0.0) for q in (1, 2, 3))
        q2_s = sum(my_q.get(q, 0.0) - op_q.get(q, 0.0) for q in (1, 2))
        all_q = set(my_q.keys()) | set(op_q.keys())
        final_s = sum(my_q.get(q, 0.0) - op_q.get(q, 0.0) for q in all_q)
        return q3_s, q2_s, final_s

    X, y = [], []
    for pid in gdf["player_id"].unique():
        try:
            pid_i = int(pid)
        except (TypeError, ValueError):
            continue
        team = pid_to_team.get(pid_i, "")
        if not team:
            continue
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
        q3_pf = pf_by_q.get(3, 0.0)
        pf_through = pf_by_q.get(1, 0.0) + pf_by_q.get(2, 0.0) + pf_by_q.get(3, 0.0)
        q3_s, q2_s, final_s = margins_for_team(team)
        if not in_blowout_flip_stratum(
                q3_margin_abs=abs(q3_s), final_margin_abs=abs(final_s)):
            continue
        velocity = q3_s - q2_s
        team_is_leading = 1 if q3_s > 0 else 0
        rem = 0.0
        for _, r in pdf.iterrows():
            if int(r["period"]) >= 4:
                rem += float(r["min"])
        pos_str = positions.get(pid_i)
        l20 = tmt.rolling_mean_min(pid_i, target_date, 20, pid_log_index)
        l5 = tmt.rolling_mean_min(pid_i, target_date, 5, pid_log_index)
        X.append(blowout_build_feature_row(
            pf_through_q3=pf_through, q3_pf=q3_pf,
            min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
            period=3,
            score_margin_abs=abs(q3_s),
            score_margin_signed_q3=q3_s,
            score_velocity_q3=velocity,
            is_leading_team=team_is_leading,
            position_proxy=pos_str, l20_min=l20, l5_min=l5,
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
