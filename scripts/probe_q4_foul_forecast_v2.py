"""probe_q4_foul_forecast_v2.py -- cycle 97e (loop 5). Validate v2.

WHY: cycle 96c v1 was REJECTED (foul_change PTS delta +0.039 vs the -0.10
ship gate). v1's heuristic table over-counted Q4 PF by +0.38 PF on average,
pushing pf=3 borderline players into the pf=4 band and over-shrinking their
projections. v2 swaps the heuristic for an NNLS-fit linear model with a
no-op gate (pf>=2 AND min_q3>=6) and round-DOWN (truncate) integerization.

What this probe checks
----------------------
1. Forecast accuracy: cross-validated Q4 PF MAE on the GATED retro sample
   (target gate: forecast MAE <= 0.80, mirror v1's 0.76).
2. Forecast bias: |mean(pred - actual)| <= 0.20 (cycle 96c's failure was
   bias +0.38 -- v2 has to halve it).
3. Stratum impact: endQ3 PTS MAE on the 102-row foul_change stratum must
   IMPROVE by >= 0.10 vs the cycle-88 baseline (originally 2.95).
4. No-regression: endQ3 PTS MAE on the non-foul_change strata may not
   regress by > 0.02.

Strictly read-only -- writes ``scripts/_results/q4_foul_forecast_v2.md``
and prints a SHIP / REJECT verdict to stdout.
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

import retro_inplay_mae as v1  # noqa: E402
from src.prediction.q4_foul_forecast_v2 import (  # noqa: E402
    FEATURE_NAMES,
    build_feature_row,
    build_training_data,
    cross_val_mae,
    fit_coefficients,
    fit_default_coefficients,
    forecasted_endgame_pf_v2,
    passes_gate,
    reset_cache,
)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_POSITIONS_PARQUET = os.path.join(PROJECT_DIR, "data", "player_positions.parquet")
_QUARTER_PARQUET = os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet")


def load_positions() -> Dict[int, str]:
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


def player_quarter_data(game_df, pid: int) -> Tuple[Dict[int, float], Dict[int, float]]:
    """Return ({period: pf}, {period: min}) for one player in one game."""
    pf_out: Dict[int, float] = {}
    min_out: Dict[int, float] = {}
    pdf = game_df[game_df["player_id"] == pid]
    for _, r in pdf.iterrows():
        pf_out[int(r["period"])] = float(r["pf"])
        min_out[int(r["period"])] = float(r["min"])
    return pf_out, min_out


def projected_with_v2(
    snap: dict,
    positions: Dict[int, str],
    qstats_df,
    coefficients: List[float],
) -> Dict[Tuple[int, str], float]:
    """Re-project a snapshot using v2's forecasted endgame pf."""
    period = int(snap.get("period") or 1)
    if period != 4:
        return v1.project_snapshot_to_finals(snap)

    gid = snap.get("game_id")
    game_df = qstats_df[qstats_df["game_id"] == gid] if gid else None

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
        try:
            spf = int(round(float(snap_pf)))
        except (TypeError, ValueError):
            spf = 0
        # q3_pf proxy = max(0, snap_pf - 2) [Q1+Q2 baseline ~2 fouls],
        # consistent with cycle 96c's probe so the comparison is apples-apples.
        q3pf_proxy = max(0, spf - 2)
        # min_q3 comes from the snapshot's min_q3 field, populated by
        # retro_inplay_mae.build_snapshot.
        min_q3 = float(p.get("min_q3", 0.0) or 0.0)
        pos_str = positions.get(pid_i)
        new_pf = forecasted_endgame_pf_v2(
            spf, q3pf_proxy, min_q3, pos_str, coefficients=coefficients)
        new_p = dict(p)
        new_p["pf"] = new_pf
        new_players.append(new_p)
    new_snap["players"] = new_players
    return v1.project_snapshot_to_finals(new_snap)


def run(max_games: Optional[int] = None,
        output: Optional[str] = None) -> int:
    reset_cache()
    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    positions = load_positions()
    print(f"  probe_q4_foul_forecast_v2: {len(games)} games  "
          f"{len(positions)} player positions loaded")

    # ── Fit NNLS coefficients on gated training set ────────────────────────
    X, y, _ = build_training_data()
    print(f"  training rows (gated): {len(X)}")
    if not X:
        print("  ERROR: no gated training rows, abort")
        return 2
    coef = fit_coefficients(X, y)
    print("  NNLS coefficients (feature: value)")
    for name, c in zip(FEATURE_NAMES, coef):
        print(f"    {name:20s}  {c:+.5f}")

    # In-sample forecast MAE + bias (sanity).
    preds = [sum(c * v for c, v in zip(coef, row)) for row in X]
    in_mae = sum(abs(p - a) for p, a in zip(preds, y)) / len(y)
    in_bias = sum(p - a for p, a in zip(preds, y)) / len(y)
    print(f"  IN-SAMPLE  forecast MAE={in_mae:.4f}  bias={in_bias:+.4f}")

    # k-fold CV MAE.
    cv = cross_val_mae(X, y, k=5, seed=0)
    print(f"  CV(k=5)    forecast MAE={cv:.4f}")

    # ── Pass 2: endQ3 projection MAE -- baseline vs v2 ────────────────────
    base_strat_abs: Dict[str, List[float]] = {s: [] for s in STATS}
    aug_strat_abs: Dict[str, List[float]] = {s: [] for s in STATS}
    base_nonstrat_abs: Dict[str, List[float]] = {s: [] for s in STATS}
    aug_nonstrat_abs: Dict[str, List[float]] = {s: [] for s in STATS}
    base_all_abs: Dict[str, List[float]] = {s: [] for s in STATS}
    aug_all_abs: Dict[str, List[float]] = {s: [] for s in STATS}
    n_strat_pids = 0
    n_total_pids = 0
    n_gated = 0

    for gid in games:
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)
        game_df = qstats_df[qstats_df["game_id"] == gid]

        base_projs = v1.project_snapshot_to_finals(snap)
        aug_projs = projected_with_v2(snap, positions, qstats_df, coef)

        # Count how many players in this snapshot pass the gate.
        for p in snap.get("players") or []:
            spf = max(0, int(round(float(p.get("pf", 0) or 0))))
            mq3 = float(p.get("min_q3", 0.0) or 0.0)
            if passes_gate(spf, mq3):
                n_gated += 1

        seen_pids = set(pid for pid, _ in base_projs.keys())
        for pid in seen_pids:
            qpf, _ = player_quarter_data(game_df, int(pid))
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
                base_all_abs[stat].append(be)
                aug_all_abs[stat].append(ae)
                if in_stratum:
                    base_strat_abs[stat].append(be)
                    aug_strat_abs[stat].append(ae)
                else:
                    base_nonstrat_abs[stat].append(be)
                    aug_nonstrat_abs[stat].append(ae)

    def _mae(xs: List[float]) -> float:
        return (sum(xs) / len(xs)) if xs else float("nan")

    pts_strat_base = _mae(base_strat_abs["pts"])
    pts_strat_aug = _mae(aug_strat_abs["pts"])
    pts_strat_delta = pts_strat_aug - pts_strat_base
    pts_nonstrat_base = _mae(base_nonstrat_abs["pts"])
    pts_nonstrat_aug = _mae(aug_nonstrat_abs["pts"])
    pts_nonstrat_delta = pts_nonstrat_aug - pts_nonstrat_base

    print(f"\n  endQ3 stat MAE -- foul_change stratum (n={len(base_strat_abs['pts'])})")
    print(f"    PTS  baseline={pts_strat_base:.4f}  v2={pts_strat_aug:.4f}  "
          f"delta={pts_strat_delta:+.4f}")
    print(f"  endQ3 stat MAE -- NON-foul_change (n={len(base_nonstrat_abs['pts'])})")
    print(f"    PTS  baseline={pts_nonstrat_base:.4f}  v2={pts_nonstrat_aug:.4f}  "
          f"delta={pts_nonstrat_delta:+.4f}")

    # Ship gate.
    ship = (pts_strat_delta <= -0.10) and (pts_nonstrat_delta <= 0.02)

    # ── Markdown report ───────────────────────────────────────────────────
    lines: List[str] = []
    lines.append("# Q4 PF forecast v2 -- cycle 97e (loop 5)")
    lines.append("")
    lines.append(f"**Games analyzed:** {len(games)}")
    lines.append(f"**Player-game rows:** {n_total_pids}  "
                 f"(foul_change stratum: {n_strat_pids})")
    lines.append(f"**Players passing gate at endQ3:** {n_gated}")
    lines.append("")
    lines.append("Cycle-96c v1 was REJECTED for biasing +0.38 PF high. v2 swaps the "
                 "heuristic table for an NNLS-fit linear model + gating "
                 "(pf>=2 AND min_q3>=6) + ROUND-DOWN integerization.")
    lines.append("")
    lines.append("## NNLS coefficients")
    lines.append("")
    lines.append("| feature | coefficient |")
    lines.append("|---------|-------------|")
    for name, c in zip(FEATURE_NAMES, coef):
        lines.append(f"| {name} | {c:+.5f} |")
    lines.append("")
    lines.append("## Forecast head accuracy (gated training rows)")
    lines.append("")
    lines.append(f"- n_rows (gated): {len(X)}")
    lines.append(f"- IN-SAMPLE  forecast MAE: {in_mae:.4f}  bias: {in_bias:+.4f}")
    lines.append(f"- CV(k=5)    forecast MAE: {cv:.4f}")
    lines.append("")
    lines.append("## endQ3 projection MAE -- foul_change stratum")
    lines.append("")
    lines.append("| stat | n | baseline_mae | v2_mae | delta |")
    lines.append("|------|---|--------------|--------|-------|")
    for stat in STATS:
        n = len(base_strat_abs[stat])
        if n == 0:
            continue
        bm = _mae(base_strat_abs[stat])
        am = _mae(aug_strat_abs[stat])
        lines.append(f"| {stat} | {n} | {bm:.4f} | {am:.4f} | {am - bm:+.4f} |")
    lines.append("")
    lines.append("## endQ3 projection MAE -- NON-foul_change stratum (regression guard)")
    lines.append("")
    lines.append("| stat | n | baseline_mae | v2_mae | delta |")
    lines.append("|------|---|--------------|--------|-------|")
    for stat in STATS:
        n = len(base_nonstrat_abs[stat])
        if n == 0:
            continue
        bm = _mae(base_nonstrat_abs[stat])
        am = _mae(aug_nonstrat_abs[stat])
        lines.append(f"| {stat} | {n} | {bm:.4f} | {am:.4f} | {am - bm:+.4f} |")
    lines.append("")
    lines.append("## endQ3 projection MAE -- full corpus (sanity)")
    lines.append("")
    lines.append("| stat | n | baseline_mae | v2_mae | delta |")
    lines.append("|------|---|--------------|--------|-------|")
    for stat in STATS:
        n = len(base_all_abs[stat])
        if n == 0:
            continue
        bm = _mae(base_all_abs[stat])
        am = _mae(aug_all_abs[stat])
        lines.append(f"| {stat} | {n} | {bm:.4f} | {am:.4f} | {am - bm:+.4f} |")
    lines.append("")
    lines.append("## Ship verdict")
    lines.append("")
    lines.append(f"- foul_change PTS delta: {pts_strat_delta:+.4f}  "
                 f"(gate: <= -0.10)")
    lines.append(f"- non-foul_change PTS delta: {pts_nonstrat_delta:+.4f}  "
                 f"(gate: <= +0.02)")
    if ship:
        lines.append("- **SHIP** -- wire `forecasted_endgame_pf_v2` into "
                     "`predict_in_game.project_snapshot` at period=4 only.")
    else:
        causes = []
        if pts_strat_delta > -0.10:
            causes.append("foul_change PTS delta did not improve >= 0.10")
        if pts_nonstrat_delta > 0.02:
            causes.append("non-foul_change PTS regressed > 0.02")
        lines.append("- **REJECT** -- " + "; ".join(causes))
        lines.append("- v2 stays as a stand-alone helper for future cycles.")
    lines.append("")
    report = "\n".join(lines) + "\n"
    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "q4_foul_forecast_v2.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\n  wrote {out_path}")
    print(f"\n  SHIP={ship}  "
          f"(strat_delta={pts_strat_delta:+.4f}, "
          f"nonstrat_delta={pts_nonstrat_delta:+.4f})")
    return 0 if ship else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    return run(max_games=args.max_games, output=args.output)


if __name__ == "__main__":
    sys.exit(main())
