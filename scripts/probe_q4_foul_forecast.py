"""probe_q4_foul_forecast.py -- cycle 96c (loop 5). Validate Q4 PF forecast.

WHY: cycle 95b's decomposition pinpointed `foul_change` (Q4 PF >= 2 picked
up) as the dominant endQ3 residual: PTS MAE 2.95 vs global 2.45 (+0.50
excess) and bias -1.25 (projector under-counts). The cycle-89b
``foul_trouble_factor`` only sees the SNAPSHOT pf, so a player at pf=3
entering Q4 gets factor 1.00 even though they're about to pick up two more
and get benched. We need to apply ``foul_trouble_factor`` at the FORECASTED
end-of-game pf, not the snapshot pf.

This script:
  1. Loads ``data/player_quarter_stats.parquet`` (50 retro games, cycle 91a).
  2. For each (player, game) where the player has pf>=1 by Q3, computes
     the forecasted Q4 PF addition via ``forecast_q4_pf_addition`` and
     compares to actual Q4 PF additions -> forecast MAE.
  3. Reconstructs endQ3 snapshots via cycle-93c infrastructure
     (``retro_inplay_mae.build_snapshot``) and projects finals TWICE:
        - baseline: cycle-88 ``project_snapshot`` (snapshot-pf foul factor).
        - augmented: monkey-patches a forecasted-pf foul factor (replaces
          pf with snap_pf + forecasted Q4 addition before computing factor).
  4. Compares endQ3 MAE on the foul_change stratum (Q4 PF >= 2 actual)
     between baseline and augmented runs.

Ship gate: augmented MAE on PTS in the foul_change stratum improves by
>= 0.10 vs baseline.

Strictly read-only: no parquet write, no model write. Writes
``scripts/_results/q4_foul_forecast_v1.md``.

Run:
    python scripts/probe_q4_foul_forecast.py
    python scripts/probe_q4_foul_forecast.py --max-games 10
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as v1  # noqa: E402
import predict_in_game as pig  # noqa: E402
from src.prediction.q4_foul_forecast import (  # noqa: E402
    forecast_q4_pf_addition, forecasted_endgame_pf,
)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_POSITIONS_PARQUET = os.path.join(PROJECT_DIR, "data", "player_positions.parquet")


def load_positions() -> Dict[int, str]:
    """Return {player_id: position_string}; empty dict on read failure."""
    import pandas as pd
    if not os.path.exists(_POSITIONS_PARQUET):
        return {}
    try:
        df = pd.read_parquet(_POSITIONS_PARQUET)
    except Exception:
        return {}
    out: Dict[int, str] = {}
    for _, r in df.iterrows():
        try:
            pid = int(r["player_id"])
        except (TypeError, ValueError):
            continue
        pos = str(r.get("position") or "")
        if pos:
            out[pid] = pos
    return out


def player_quarter_pf(game_df, pid: int) -> Dict[int, float]:
    """Return {period: pf} for one player in one game."""
    out: Dict[int, float] = {}
    pdf = game_df[game_df["player_id"] == pid]
    for _, r in pdf.iterrows():
        out[int(r["period"])] = float(r["pf"])
    return out


def projected_with_forecast(
    snap: dict,
    positions: Dict[int, str],
) -> Dict[Tuple[int, str], float]:
    """Run project_snapshot, but with each player's pf REPLACED by the
    forecasted endgame pf BEFORE the snapshot enters the projector.

    Cycle 96c hook: only applied at end-of-Q3 (period=4, clock=12:00).
    At earlier snapshots Q4 information is too sparse -- spec excludes
    Q1/Q2 application.
    """
    period = int(snap.get("period") or 1)
    if period != 4:
        return v1.project_snapshot_to_finals(snap)

    # Shallow-clone the snapshot and rewrite each player's pf.
    new_snap = dict(snap)
    new_players: List[dict] = []
    for p in snap.get("players") or []:
        pid = p.get("player_id")
        try:
            pid_i = int(pid)
        except (TypeError, ValueError):
            new_players.append(p)
            continue
        snap_pf = p.get("pf", 0)
        # q3_pf is the per-Q3 PF -- caller supplies min_q3 etc but we only
        # have CUMULATIVE pf in the snapshot. We approximate q3_pf with the
        # delta between snap_pf and the player's min_q1+min_q2 share of pf
        # (no separate per-Q pf in the canonical snapshot schema). Use a
        # conservative proxy: q3_pf >= 2 iff snap_pf - (snap_pf * 2/3) >= 2,
        # which simplifies to snap_pf/3 >= 2 -> snap_pf >= 6. That's too
        # narrow; use the better proxy: assume q3_pf = max(0, snap_pf - 2)
        # i.e. fouls beyond a "baseline 2 from Q1+Q2" are recent.
        try:
            spf = int(round(float(snap_pf)))
        except (TypeError, ValueError):
            spf = 0
        q3pf_proxy = max(0, spf - 2)
        pos_str = positions.get(pid_i)
        new_pf = forecasted_endgame_pf(spf, q3pf_proxy, pos_str)
        new_p = dict(p)
        new_p["pf"] = new_pf
        new_players.append(new_p)
    new_snap["players"] = new_players
    return v1.project_snapshot_to_finals(new_snap)


def run(max_games: Optional[int] = None,
        output: Optional[str] = None) -> int:
    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    positions = load_positions()
    print(f"  probe_q4_foul_forecast: {len(games)} games  "
          f"{len(positions)} player positions loaded")

    # ── Pass 1: forecast MAE vs actual Q4 PF additions ────────────────────
    pf_pred: List[float] = []
    pf_actual: List[float] = []
    for gid in games:
        game_df = qstats_df[qstats_df["game_id"] == gid]
        pids = game_df["player_id"].unique().tolist()
        for pid in pids:
            qpf = player_quarter_pf(game_df, int(pid))
            if 4 not in qpf:
                continue
            pf_through_q3 = sum(qpf.get(q, 0.0) for q in (1, 2, 3))
            q3_pf_only = qpf.get(3, 0.0)
            actual_q4_pf = qpf.get(4, 0.0)
            pos = positions.get(int(pid))
            pred = forecast_q4_pf_addition(
                int(round(pf_through_q3)), int(round(q3_pf_only)), pos)
            pf_pred.append(pred)
            pf_actual.append(actual_q4_pf)

    forecast_mae = (
        sum(abs(p - a) for p, a in zip(pf_pred, pf_actual)) / len(pf_pred)
        if pf_pred else float("nan")
    )
    forecast_n = len(pf_pred)
    forecast_bias = (
        sum(p - a for p, a in zip(pf_pred, pf_actual)) / len(pf_pred)
        if pf_pred else float("nan")
    )
    print(f"  Q4 PF forecast: n={forecast_n}  MAE={forecast_mae:.4f}  "
          f"bias={forecast_bias:+.4f}")

    # ── Pass 2: endQ3 stat-projection MAE, baseline vs augmented ─────────
    base_abs_err: Dict[str, List[float]] = {s: [] for s in STATS}
    aug_abs_err: Dict[str, List[float]] = {s: [] for s in STATS}
    base_strat_abs: Dict[str, List[float]] = {s: [] for s in STATS}
    aug_strat_abs: Dict[str, List[float]] = {s: [] for s in STATS}
    n_strat_pids = 0
    n_total_pids = 0

    for gid in games:
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)
        game_df = qstats_df[qstats_df["game_id"] == gid]

        base_projs = v1.project_snapshot_to_finals(snap)
        aug_projs = projected_with_forecast(snap, positions)

        # Stratum = (player, game) where actual Q4 pf >= 2.
        seen_pids = set(pid for pid, _ in base_projs.keys())
        for pid in seen_pids:
            qpf = player_quarter_pf(game_df, int(pid))
            q4_pf = qpf.get(4, 0.0)
            in_stratum = q4_pf >= 2.0
            n_total_pids += 1
            if in_stratum:
                n_strat_pids += 1
            for stat in STATS:
                actual = actuals.get((int(pid), stat))
                base = base_projs.get((int(pid), stat))
                aug = aug_projs.get((int(pid), stat))
                if actual is None or base is None or aug is None:
                    continue
                be = abs(base - actual)
                ae = abs(aug - actual)
                base_abs_err[stat].append(be)
                aug_abs_err[stat].append(ae)
                if in_stratum:
                    base_strat_abs[stat].append(be)
                    aug_strat_abs[stat].append(ae)

    def _mae(xs: List[float]) -> float:
        return (sum(xs) / len(xs)) if xs else float("nan")

    print(f"\n  endQ3 PTS MAE -- foul_change stratum (n={len(base_strat_abs['pts'])}):")
    print(f"    baseline  : {_mae(base_strat_abs['pts']):.4f}")
    print(f"    augmented : {_mae(aug_strat_abs['pts']):.4f}")
    delta_pts = _mae(aug_strat_abs["pts"]) - _mae(base_strat_abs["pts"])
    print(f"    delta     : {delta_pts:+.4f}  (negative = improvement)")

    ship = delta_pts <= -0.10

    # ── Markdown report ───────────────────────────────────────────────────
    lines: List[str] = []
    lines.append("# Q4 PF forecast head -- cycle 96c (loop 5)")
    lines.append("")
    lines.append(f"**Games analyzed:** {len(games)}")
    lines.append(f"**Player-game rows:** {n_total_pids}  "
                 f"(foul_change stratum: {n_strat_pids})")
    lines.append("")
    lines.append(
        "Tests whether forecasting Q4 PF additions (instead of using the "
        "raw snapshot pf) lets the cycle-89b ``foul_trouble_factor`` fire "
        "EARLIER -- specifically on the cycle-95b ``foul_change`` stratum "
        "(players who actually picked up >=2 PF in Q4)."
    )
    lines.append("")
    lines.append("## Forecast head accuracy")
    lines.append("")
    lines.append(f"- n_player_games: {forecast_n}")
    lines.append(f"- Q4 PF forecast MAE: {forecast_mae:.4f}")
    lines.append(f"- Q4 PF forecast bias (pred - actual): {forecast_bias:+.4f}")
    lines.append("")
    lines.append("## endQ3 projection MAE on foul_change stratum")
    lines.append("")
    lines.append("| stat | n | baseline_mae | augmented_mae | delta |")
    lines.append("|------|---|--------------|---------------|-------|")
    for stat in STATS:
        n = len(base_strat_abs[stat])
        if n == 0:
            continue
        bm = _mae(base_strat_abs[stat])
        am = _mae(aug_strat_abs[stat])
        d = am - bm
        lines.append(f"| {stat} | {n} | {bm:.4f} | {am:.4f} | {d:+.4f} |")
    lines.append("")
    lines.append("## endQ3 projection MAE on full corpus (sanity check)")
    lines.append("")
    lines.append("| stat | n | baseline_mae | augmented_mae | delta |")
    lines.append("|------|---|--------------|---------------|-------|")
    for stat in STATS:
        n = len(base_abs_err[stat])
        if n == 0:
            continue
        bm = _mae(base_abs_err[stat])
        am = _mae(aug_abs_err[stat])
        d = am - bm
        lines.append(f"| {stat} | {n} | {bm:.4f} | {am:.4f} | {d:+.4f} |")
    lines.append("")
    lines.append("## Ship verdict")
    lines.append("")
    lines.append(f"- foul_change PTS delta: {delta_pts:+.4f}")
    lines.append("- Ship gate: foul_change PTS delta <= -0.10")
    if ship:
        lines.append("- **SHIP** -- wire `forecasted_endgame_pf` into "
                     "`predict_in_game.project_snapshot` (replace pf with "
                     "forecasted_pf when projecting remaining time at "
                     "end-of-Q3, period=4 only).")
    else:
        lines.append("- **REJECT** -- forecast-augmented foul factor does not "
                     "clear the 0.10 PTS MAE gate on the foul_change stratum. "
                     "Likely causes: snapshot pf already captures most of the "
                     "signal at endQ3, OR the forecast over-counts Q4 PF for "
                     "the typical foul_change player. The q3_pf proxy "
                     "(snap_pf - 2) may also be too aggressive. Next probe: "
                     "fit forecast coefficients via NNLS on per-position "
                     "buckets, or condition forecast on minutes_per_q3.")
    lines.append("")
    report = "\n".join(lines) + "\n"
    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "q4_foul_forecast_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\n  wrote {out_path}")
    print(f"\n  SHIP={ship}  (delta={delta_pts:+.4f}, gate=-0.10)")
    return 0 if ship else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None,
                    help="Limit to first N games (debug).")
    ap.add_argument("--output", default=None,
                    help="Markdown output path.")
    args = ap.parse_args()
    return run(max_games=args.max_games, output=args.output)


if __name__ == "__main__":
    sys.exit(main())
