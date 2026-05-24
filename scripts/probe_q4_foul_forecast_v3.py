"""probe_q4_foul_forecast_v3.py -- cycle 98a (loop 5). Validate v3.

WHY: cycle 97e v2 was REJECTED as a no-op (0/254 gated rows crossed an
integer foul band under round-down truncation, mean forecast 0.66 PF).
v2's report explicitly suggested fractional-weighted band blending as
the next probe. v3 implements that:

    factor = (1 - frac) * band(spf + whole) + frac * band(spf + whole + 1)

with ``whole = int(forecast_add)`` and ``frac = forecast_add - whole``.

This probe re-uses v2's coefficients (no re-fit), recomputes the
foul_trouble_factor at endQ3 with the fractional blend, and re-runs the
``project_snapshot`` projection logic against the cycle-91a 50-game retro
corpus. Compares endQ3 PTS MAE on:

    - foul_change stratum (Q4 PF >= 2)  -- must IMPROVE by >= 0.10
    - non-foul_change stratum            -- must not regress by > 0.02
    - full corpus (sanity)

The probe re-implements ``project_snapshot``'s inner loop so it can swap
in the v3 fractional factor at the per-player level (the unified
``foul_trouble_factor`` only sees integer pf). Pace and blowout logic
mirror cycle 88b/88f exactly.

Strictly read-only -- writes ``scripts/_results/q4_foul_forecast_v3.md``
and prints SHIP / REJECT to stdout.
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
from src.prediction.live_factors import foul_trouble_factor  # noqa: E402
from src.prediction.q4_foul_forecast_v2 import (  # noqa: E402
    FEATURE_NAMES,
    build_training_data,
    fit_coefficients,
    forecast_q4_pf_addition_v2,
    passes_gate,
    reset_cache,
)
from src.prediction.q4_foul_forecast_v3 import (  # noqa: E402
    fractional_band_factor,
)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_POSITIONS_PARQUET = os.path.join(PROJECT_DIR, "data", "player_positions.parquet")


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


def _num(v, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def project_snapshot_with_v3(
    snap: dict,
    positions: Dict[int, str],
    coefficients: List[float],
    pace_factor: float = 1.0,
    star_threshold_min: float = 30.0,
) -> Dict[Tuple[int, str], float]:
    """Re-implements ``predict_in_game.project_snapshot`` with v3 factor.

    Identical to pig.project_snapshot except the foul_factor for each
    player is computed via ``fractional_band_factor`` when the gate clears.
    Otherwise it falls back to the canonical integer band lookup -- the
    same behavior as the cycle-88b baseline. Result: byte-for-byte match
    with baseline when the gate doesn't clear (true no-op for low-foul
    players).

    Returns dict keyed (player_id, stat) -> projected_final, matching
    ``retro_inplay_mae.project_snapshot_to_finals``.
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
        snap_pf = p.get("pf", 0)
        try:
            spf = max(0, int(round(float(snap_pf))))
        except (TypeError, ValueError):
            spf = 0
        min_q3 = _num(p.get("min_q3", 0.0))
        pos_str = positions.get(pid_i)
        q3pf_proxy = max(0, spf - 2)

        # v3 factor: gated NNLS forecast + fractional blend; otherwise
        # canonical integer band lookup (exact baseline behavior).
        if period == 4 and passes_gate(spf, min_q3):
            add = forecast_q4_pf_addition_v2(
                pf_through_q3=spf,
                q3_pf=q3pf_proxy,
                min_q3=min_q3,
                position_proxy=pos_str,
                coefficients=coefficients,
            )
            ff = fractional_band_factor(spf, add, period, clock_rem)
        else:
            ff = foul_trouble_factor(spf, period, clock_rem)

        share_played_game = pig.clock_played_share(period, clock_rem)
        proj_min = (cur_min / share_played_game) if share_played_game > 0 else cur_min
        is_star = proj_min >= star_threshold_min
        team_is_leading = (
            (team == home_team and margin > 0) or
            (team == away_team and margin < 0)
        )
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


def _factor_distribution_on_gated(
    games: List[str],
    qstats_df,
    positions: Dict[int, str],
    coef: List[float],
) -> Tuple[int, float, float, int]:
    """Compute factor distribution on gated rows at endQ3 (period=4 logic).

    Returns (n_gated, mean_factor, pct_below_085, n_total_snapshot_players).
    Note: gate is checked at the SNAPSHOT (endQ3 snapshot has period=4 in
    the snapshot ladder), matching the in-game projector wiring.
    """
    factors: List[float] = []
    n_total = 0
    for gid in games:
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        snap_period = int(snap.get("period") or 1)
        snap_clock = pig.parse_clock(snap.get("clock"))
        for p in snap.get("players") or []:
            n_total += 1
            try:
                spf = max(0, int(round(float(p.get("pf", 0) or 0))))
            except (TypeError, ValueError):
                spf = 0
            min_q3 = _num(p.get("min_q3", 0.0))
            if not passes_gate(spf, min_q3):
                continue
            pid = p.get("player_id")
            try:
                pid_i = int(pid)
            except (TypeError, ValueError):
                pid_i = -1
            pos_str = positions.get(pid_i)
            q3pf_proxy = max(0, spf - 2)
            add = forecast_q4_pf_addition_v2(
                pf_through_q3=spf,
                q3_pf=q3pf_proxy,
                min_q3=min_q3,
                position_proxy=pos_str,
                coefficients=coef,
            )
            f = fractional_band_factor(spf, add, snap_period, snap_clock)
            factors.append(f)
    if not factors:
        return 0, float("nan"), float("nan"), n_total
    mean_f = sum(factors) / len(factors)
    pct_below_085 = 100.0 * sum(1 for x in factors if x < 0.85) / len(factors)
    return len(factors), mean_f, pct_below_085, n_total


def run(max_games: Optional[int] = None,
        output: Optional[str] = None) -> int:
    reset_cache()
    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    positions = load_positions()
    print(f"  probe_q4_foul_forecast_v3: {len(games)} games  "
          f"{len(positions)} player positions loaded")

    X, y, _ = build_training_data()
    print(f"  training rows (gated): {len(X)}")
    if not X:
        print("  ERROR: no gated training rows, abort")
        return 2
    coef = fit_coefficients(X, y)
    print("  NNLS coefficients (feature: value) -- INHERITED from v2")
    for name, c in zip(FEATURE_NAMES, coef):
        print(f"    {name:20s}  {c:+.5f}")

    # ── factor distribution on gated rows ────────────────────────────────
    n_gated, mean_f, pct_lo, n_total = _factor_distribution_on_gated(
        games, qstats_df, positions, coef)
    print(f"\n  Gated rows: {n_gated} / {n_total}  "
          f"({100.0 * n_gated / max(1, n_total):.1f}%)")
    print(f"  Mean v3 factor on gated: {mean_f:.4f}  "
          f"(% below 0.85: {pct_lo:.1f}%)")

    # ── Pass 2: endQ3 projection MAE -- baseline vs v3 ───────────────────
    base_strat: Dict[str, List[float]] = {s: [] for s in STATS}
    aug_strat: Dict[str, List[float]] = {s: [] for s in STATS}
    base_nonstrat: Dict[str, List[float]] = {s: [] for s in STATS}
    aug_nonstrat: Dict[str, List[float]] = {s: [] for s in STATS}
    base_all: Dict[str, List[float]] = {s: [] for s in STATS}
    aug_all: Dict[str, List[float]] = {s: [] for s in STATS}
    n_strat = 0
    n_total_rows = 0

    for gid in games:
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)
        game_df = qstats_df[qstats_df["game_id"] == gid]

        base_projs = v1.project_snapshot_to_finals(snap)
        v3_projs = project_snapshot_with_v3(snap, positions, coef)

        seen_pids = set(pid for pid, _ in base_projs.keys())
        for pid in seen_pids:
            pdf = game_df[game_df["player_id"] == pid]
            q4_pf = 0.0
            for _, r in pdf.iterrows():
                if int(r["period"]) == 4:
                    q4_pf = float(r["pf"])
                    break
            in_stratum = q4_pf >= 2.0
            n_total_rows += 1
            if in_stratum:
                n_strat += 1
            for stat in STATS:
                actual = actuals.get((int(pid), stat))
                base = base_projs.get((int(pid), stat))
                aug = v3_projs.get((int(pid), stat))
                if actual is None or base is None or aug is None:
                    continue
                be = abs(base - actual)
                ae = abs(aug - actual)
                base_all[stat].append(be)
                aug_all[stat].append(ae)
                if in_stratum:
                    base_strat[stat].append(be)
                    aug_strat[stat].append(ae)
                else:
                    base_nonstrat[stat].append(be)
                    aug_nonstrat[stat].append(ae)

    def _mae(xs: List[float]) -> float:
        return (sum(xs) / len(xs)) if xs else float("nan")

    pts_strat_b = _mae(base_strat["pts"])
    pts_strat_a = _mae(aug_strat["pts"])
    pts_strat_d = pts_strat_a - pts_strat_b
    pts_nonstrat_b = _mae(base_nonstrat["pts"])
    pts_nonstrat_a = _mae(aug_nonstrat["pts"])
    pts_nonstrat_d = pts_nonstrat_a - pts_nonstrat_b

    print(f"\n  endQ3 PTS MAE -- foul_change (n={len(base_strat['pts'])})")
    print(f"    baseline={pts_strat_b:.4f}  v3={pts_strat_a:.4f}  "
          f"delta={pts_strat_d:+.4f}")
    print(f"  endQ3 PTS MAE -- NON-foul_change (n={len(base_nonstrat['pts'])})")
    print(f"    baseline={pts_nonstrat_b:.4f}  v3={pts_nonstrat_a:.4f}  "
          f"delta={pts_nonstrat_d:+.4f}")

    ship = (pts_strat_d <= -0.10) and (pts_nonstrat_d <= 0.02)

    # ── Markdown report ───────────────────────────────────────────────
    lines: List[str] = []
    lines.append("# Q4 PF forecast v3 (fractional band blend) -- cycle 98a (loop 5)")
    lines.append("")
    lines.append(f"**Games analyzed:** {len(games)}")
    lines.append(f"**Player-game rows:** {n_total_rows}  "
                 f"(foul_change stratum: {n_strat})")
    lines.append(f"**Players passing gate at endQ3:** {n_gated} / {n_total} "
                 f"({100.0 * n_gated / max(1, n_total):.1f}%)")
    lines.append("")
    lines.append("Cycle 97e v2 was REJECTED as no-op (0/254 gated rows crossed "
                 "an integer band under round-down truncation). v3 keeps v2's "
                 "NNLS coefficients + gate, but replaces the integerization "
                 "step with a fractional weighted blend between adjacent "
                 "foul_trouble_factor bands.")
    lines.append("")
    lines.append("## NNLS coefficients (inherited from v2)")
    lines.append("")
    lines.append("| feature | coefficient |")
    lines.append("|---------|-------------|")
    for name, c in zip(FEATURE_NAMES, coef):
        lines.append(f"| {name} | {c:+.5f} |")
    lines.append("")
    lines.append("## v3 factor distribution on gated rows")
    lines.append("")
    lines.append(f"- mean v3 factor: **{mean_f:.4f}** "
                 f"(baseline integer band lookup would yield 1.0 for most rows "
                 f"since 254/254 gated rows had spf < 4)")
    lines.append(f"- % of gated factors below 0.85: **{pct_lo:.1f}%** "
                 f"(v2 was 0.0%, by construction)")
    lines.append("")
    lines.append("## endQ3 projection MAE -- foul_change stratum")
    lines.append("")
    lines.append("| stat | n | baseline_mae | v3_mae | delta |")
    lines.append("|------|---|--------------|--------|-------|")
    for stat in STATS:
        n = len(base_strat[stat])
        if n == 0:
            continue
        bm = _mae(base_strat[stat])
        am = _mae(aug_strat[stat])
        lines.append(f"| {stat} | {n} | {bm:.4f} | {am:.4f} | {am - bm:+.4f} |")
    lines.append("")
    lines.append("## endQ3 projection MAE -- NON-foul_change (regression guard)")
    lines.append("")
    lines.append("| stat | n | baseline_mae | v3_mae | delta |")
    lines.append("|------|---|--------------|--------|-------|")
    for stat in STATS:
        n = len(base_nonstrat[stat])
        if n == 0:
            continue
        bm = _mae(base_nonstrat[stat])
        am = _mae(aug_nonstrat[stat])
        lines.append(f"| {stat} | {n} | {bm:.4f} | {am:.4f} | {am - bm:+.4f} |")
    lines.append("")
    lines.append("## endQ3 projection MAE -- full corpus")
    lines.append("")
    lines.append("| stat | n | baseline_mae | v3_mae | delta |")
    lines.append("|------|---|--------------|--------|-------|")
    for stat in STATS:
        n = len(base_all[stat])
        if n == 0:
            continue
        bm = _mae(base_all[stat])
        am = _mae(aug_all[stat])
        lines.append(f"| {stat} | {n} | {bm:.4f} | {am:.4f} | {am - bm:+.4f} |")
    lines.append("")
    lines.append("## Ship verdict")
    lines.append("")
    lines.append(f"- foul_change PTS delta: {pts_strat_d:+.4f}  (gate: <= -0.10)")
    lines.append(f"- non-foul_change PTS delta: {pts_nonstrat_d:+.4f}  "
                 f"(gate: <= +0.02)")
    if ship:
        lines.append("- **SHIP** -- wire `fractional_factor_for_snapshot` into "
                     "`predict_in_game.project_snapshot` (period=4 only) and "
                     "`live_engine.project_from_snapshot`. Deprecate v1 + v2 "
                     "docstrings.")
    else:
        causes = []
        if pts_strat_d > -0.10:
            causes.append("foul_change PTS delta did not improve >= 0.10")
        if pts_nonstrat_d > 0.02:
            causes.append("non-foul_change PTS regressed > 0.02")
        lines.append("- **REJECT** -- " + "; ".join(causes))
        lines.append("- v3 stays as a stand-alone helper; v1 + v2 unchanged.")
    lines.append("")
    report = "\n".join(lines) + "\n"
    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "q4_foul_forecast_v3.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\n  wrote {out_path}")
    print(f"\n  SHIP={ship}  "
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
