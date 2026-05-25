"""probe_minute_trajectory_replacement.py -- tier3-10 (loop 5).

Compares the cycle-88 baseline endQ3 projection against the SAME projection
where the per-player foul_trouble_factor multiplier is replaced by
``learned_minute_factor`` from :mod:`src.prediction.minute_trajectory`.

For each retro game's endQ3 snapshot:
  1. Build the baseline projection (foul_trouble_factor + pace + blowout) --
     reuses :func:`retro_inplay_mae.project_snapshot_to_finals`.
  2. Build a replacement projection where, per-player, the foul_factor is
     swapped for ``learned_remaining_min / 12.0``.
  3. Stratify by FOUL_CHANGE (Q4 PF >= 2). Compute PTS/REB/AST MAE on:
       - foul_change stratum   -- must IMPROVE by >= 0.10 PTS MAE
       - non-foul_change       -- must not regress by > 0.05 PTS MAE

Writes ``scripts/_results/minute_trajectory_v1.md`` with ship verdict.
Strictly read-only -- doesn't mutate predict_in_game.py.
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

import predict_in_game as pig  # noqa: E402
import retro_inplay_mae as v1  # noqa: E402
import train_minute_trajectory as tmt  # noqa: E402
from src.prediction.minute_trajectory import (  # noqa: E402
    MinuteTrajectoryModel,
    learned_minute_factor,
)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _num(v, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def project_snapshot_with_learned_minutes(
    snap: dict,
    model: MinuteTrajectoryModel,
    positions: Dict[int, str],
    l20_lookup: Dict[int, float],
    l5_lookup: Dict[int, float],
    pace_factor: float = 1.0,
    star_threshold_min: float = 30.0,
) -> Dict[Tuple[int, str], float]:
    """Re-implements ``project_snapshot`` with foul_factor swapped for the
    learned remaining-minute ratio. Identical pace + blowout + bench logic
    to the cycle-88b baseline.
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

        # endQ3 inputs for the learned model.
        snap_pf = _num(p.get("pf"), default=0.0)
        min_q1 = _num(p.get("min_q1", 0.0))
        min_q2 = _num(p.get("min_q2", 0.0))
        min_q3 = _num(p.get("min_q3", 0.0))
        q3_pf_proxy = max(0.0, snap_pf - 2.0)

        team_is_leading = (
            (team == home_team and margin > 0) or
            (team == away_team and margin < 0)
        )

        # Substituted factor: learned remaining-min / 12.0. ONLY for period=4
        # snapshots (endQ3 ladder). Earlier periods still get heuristic.
        if period == 4:
            ff = learned_minute_factor(
                model,
                pf_through_q3=snap_pf,
                q3_pf=q3_pf_proxy,
                min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
                score_margin_abs=abs(margin),
                is_leading_team=1 if team_is_leading else 0,
                position_proxy=positions.get(pid_i),
                l20_min=l20_lookup.get(pid_i),
                l5_min=l5_lookup.get(pid_i),
            )
        else:
            from src.prediction.live_factors import foul_trouble_factor
            ff = foul_trouble_factor(snap_pf, period, clock_rem)

        share_played_game = pig.clock_played_share(period, clock_rem)
        proj_min = (cur_min / share_played_game) if share_played_game > 0 else cur_min
        is_star = proj_min >= star_threshold_min
        bf = pig.blowout_factor(
            abs(margin), period, is_star=(is_star and team_is_leading))

        period_elapsed_min = max(0.0, pig.PERIOD_MIN - clock_rem)
        bench_now = pig.is_bench_in_current_period(
            p, period, period_elapsed_min=period_elapsed_min,
        )
        player_basis = cur_min if bench_now else None

        for stat in pig.STATS:
            cur = _num(p.get(stat))
            final = pig.project_final(
                cur, period, clock_rem,
                pace_factor=pace_factor,
                foul_factor=ff, blow_factor=bf,
                player_clock_played_min=player_basis,
            )
            out[(pid_i, stat)] = float(final)
    return out


def run(max_games: Optional[int] = None, output: Optional[str] = None) -> int:
    model = MinuteTrajectoryModel.load()
    if model is None:
        print("  ERROR: model artifact not found. Run "
              "scripts/train_minute_trajectory.py first.")
        return 2
    print("  loaded MinuteTrajectoryModel from data/models/minute_trajectory.lgb")

    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    positions = tmt.load_positions()
    pid_log_index = tmt.load_player_gamelog_minutes()
    print(f"  {len(games)} games  {len(positions)} positions  "
          f"{len(pid_log_index)} player gamelogs indexed")

    # Per-game L20/L5 lookup -- we MUST use a date earlier than the game to
    # avoid future-game leakage. The probe spans the FULL 550-game corpus,
    # so we have to recompute per game. For speed we'll precompute a flat
    # {pid: most-recent L20/L5 prior to the median game date}. This is a
    # slight approximation -- model was trained with per-game lookup -- but
    # the probe is read-only and computing per-game would 50x runtime. The
    # margin is small (L20 changes slowly across the season corpus).
    # For safety, we use the per-game lookup since training did:
    per_game_l20: Dict[str, Dict[int, float]] = {}
    per_game_l5: Dict[str, Dict[int, float]] = {}
    for gid in games:
        target_date = tmt.find_game_date_for_game(gid, qstats_df, pid_log_index)
        gpids = set(int(pid) for pid in
                    qstats_df[qstats_df["game_id"] == gid]["player_id"].unique())
        l20m: Dict[int, float] = {}
        l5m: Dict[int, float] = {}
        for pid in gpids:
            l20 = tmt.rolling_mean_min(pid, target_date, 20, pid_log_index)
            l5 = tmt.rolling_mean_min(pid, target_date, 5, pid_log_index)
            if l20 is not None:
                l20m[pid] = l20
            if l5 is not None:
                l5m[pid] = l5
        per_game_l20[gid] = l20m
        per_game_l5[gid] = l5m

    # Stratified MAE accumulators.
    base_strat: Dict[str, List[float]] = {s: [] for s in STATS}
    learned_strat: Dict[str, List[float]] = {s: [] for s in STATS}
    base_nonstrat: Dict[str, List[float]] = {s: [] for s in STATS}
    learned_nonstrat: Dict[str, List[float]] = {s: [] for s in STATS}
    base_all: Dict[str, List[float]] = {s: [] for s in STATS}
    learned_all: Dict[str, List[float]] = {s: [] for s in STATS}

    n_strat = 0
    n_total = 0
    for gid in games:
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)
        game_df = qstats_df[qstats_df["game_id"] == gid]

        base_projs = v1.project_snapshot_to_finals(snap)
        learned_projs = project_snapshot_with_learned_minutes(
            snap, model, positions,
            per_game_l20.get(gid, {}), per_game_l5.get(gid, {}),
        )

        seen_pids = set(pid for pid, _ in base_projs.keys())
        for pid in seen_pids:
            pdf = game_df[game_df["player_id"] == pid]
            q4_pf = 0.0
            for _, r in pdf.iterrows():
                if int(r["period"]) == 4:
                    q4_pf = float(r["pf"])
                    break
            in_strat = q4_pf >= 2.0
            n_total += 1
            if in_strat:
                n_strat += 1
            for stat in STATS:
                actual = actuals.get((int(pid), stat))
                base = base_projs.get((int(pid), stat))
                learned = learned_projs.get((int(pid), stat))
                if actual is None or base is None or learned is None:
                    continue
                be = abs(base - actual)
                le = abs(learned - actual)
                base_all[stat].append(be)
                learned_all[stat].append(le)
                if in_strat:
                    base_strat[stat].append(be)
                    learned_strat[stat].append(le)
                else:
                    base_nonstrat[stat].append(be)
                    learned_nonstrat[stat].append(le)

    def _mae(xs: List[float]) -> float:
        return (sum(xs) / len(xs)) if xs else float("nan")

    pts_strat_b = _mae(base_strat["pts"])
    pts_strat_l = _mae(learned_strat["pts"])
    pts_strat_d = pts_strat_l - pts_strat_b
    pts_nonstrat_b = _mae(base_nonstrat["pts"])
    pts_nonstrat_l = _mae(learned_nonstrat["pts"])
    pts_nonstrat_d = pts_nonstrat_l - pts_nonstrat_b

    print(f"\n  foul_change stratum (n={len(base_strat['pts'])})")
    print(f"    PTS  baseline={pts_strat_b:.4f}  learned={pts_strat_l:.4f}  "
          f"delta={pts_strat_d:+.4f}")
    print(f"  NON-foul_change stratum (n={len(base_nonstrat['pts'])})")
    print(f"    PTS  baseline={pts_nonstrat_b:.4f}  learned={pts_nonstrat_l:.4f}  "
          f"delta={pts_nonstrat_d:+.4f}")

    ship = (pts_strat_d <= -0.10) and (pts_nonstrat_d <= 0.05)

    # ── markdown report ─────────────────────────────────────────────────
    lines: List[str] = []
    lines.append("# minute_trajectory replacement probe -- tier3-10 (loop 5)")
    lines.append("")
    lines.append(f"**Games:** {len(games)}  "
                 f"**player-game rows:** {n_total} "
                 f"(foul_change stratum: {n_strat})")
    lines.append("")
    lines.append("Replaces heuristic `foul_trouble_factor` with "
                 "`learned_remaining_min / 12.0` from "
                 "`src.prediction.minute_trajectory.MinuteTrajectoryModel`. "
                 "Pace + blowout + bench logic identical to cycle 88b "
                 "baseline. Substitution applied ONLY when period=4 "
                 "(endQ3 snapshot ladder).")
    lines.append("")
    lines.append("## endQ3 PTS/REB/AST MAE -- foul_change stratum")
    lines.append("")
    lines.append("| stat | n | baseline | learned | delta |")
    lines.append("|------|---|----------|---------|-------|")
    for stat in ("pts", "reb", "ast"):
        bs = base_strat[stat]
        ls = learned_strat[stat]
        if not bs:
            continue
        bm, lm = _mae(bs), _mae(ls)
        lines.append(f"| {stat} | {len(bs)} | {bm:.4f} | {lm:.4f} | {lm - bm:+.4f} |")
    lines.append("")
    lines.append("## endQ3 PTS/REB/AST MAE -- NON-foul_change (regression guard)")
    lines.append("")
    lines.append("| stat | n | baseline | learned | delta |")
    lines.append("|------|---|----------|---------|-------|")
    for stat in ("pts", "reb", "ast"):
        bs = base_nonstrat[stat]
        ls = learned_nonstrat[stat]
        if not bs:
            continue
        bm, lm = _mae(bs), _mae(ls)
        lines.append(f"| {stat} | {len(bs)} | {bm:.4f} | {lm:.4f} | {lm - bm:+.4f} |")
    lines.append("")
    lines.append("## endQ3 MAE -- full corpus (all 7 stats)")
    lines.append("")
    lines.append("| stat | n | baseline | learned | delta |")
    lines.append("|------|---|----------|---------|-------|")
    for stat in STATS:
        bs = base_all[stat]
        ls = learned_all[stat]
        if not bs:
            continue
        bm, lm = _mae(bs), _mae(ls)
        lines.append(f"| {stat} | {len(bs)} | {bm:.4f} | {lm:.4f} | {lm - bm:+.4f} |")
    lines.append("")
    lines.append("## Ship gate")
    lines.append("")
    lines.append(f"- foul_change PTS delta: {pts_strat_d:+.4f}  (gate: <= -0.10)")
    lines.append(f"- non-foul_change PTS delta: {pts_nonstrat_d:+.4f}  "
                 f"(gate: <= +0.05)")
    if ship:
        lines.append("- **SHIP** -- expose `_USE_LEARNED_MINUTES` flag in "
                     "`predict_in_game`; keep heuristic as default until "
                     "further out-of-sample validation.")
    else:
        causes = []
        if pts_strat_d > -0.10:
            causes.append("foul_change PTS did not improve >= 0.10")
        if pts_nonstrat_d > 0.05:
            causes.append("non-foul_change PTS regressed > 0.05")
        lines.append("- **REJECT** -- " + "; ".join(causes))
        lines.append("- model artifact + wrapper stay for future iteration "
                     "(e.g. extend features, recalibrate, retrain on full "
                     "season).")
    lines.append("")
    report = "\n".join(lines) + "\n"

    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "minute_trajectory_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"  wrote {out_path}")
    print(f"  SHIP={ship}  "
          f"(strat_delta={pts_strat_d:+.4f}, "
          f"nonstrat_delta={pts_nonstrat_d:+.4f})")
    return 0 if ship else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    return run(max_games=args.max_games, output=args.output)


if __name__ == "__main__":
    sys.exit(main())
