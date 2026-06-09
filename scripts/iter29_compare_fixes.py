"""iter29_compare_fixes.py — iter-29 (loop 5). Measure iter-28 fix impact on iter-26 backtest.

WHY: iter-26 ran backtest_inplay_edge_v2 and got +80% endQ3 ROI / 93.4% hit on
3,427 bets at threshold=1.0. iter-28 then shipped 4 risk-reducing pretip-ranker
fixes (sanity guard, sigma floor for BLK/STL/FG3M, 25pp edge cap, heuristic
fallback). Those fixes live in live_bet_ranker.py + inplay_bet_ranker.py, NOT
in backtest_inplay_edge.py — so iter-26's headline was measured WITHOUT the
fixes applied.

This script mirrors the iter-28 sigma-floor + edge-cap logic into the EXACT
same simulate_bets pipeline and produces a side-by-side comparison.

Why ONLY 2 of the 4 iter-28 fixes apply here:
  * Sanity guard (widen inverted q90)  → backtest has no q10/q50/q90, only
    a point estimate + _CAL_SPREAD sigma. Inversion cannot occur.
  * Heuristic fallback                  → backtest already has a point + sigma.
  * Sigma floor for BLK/STL/FG3M       → ✓ applies (point estimate IS the
    de-facto q50, so floor_sigma = max(0.4 * q50, 0.5) is well-defined)
  * Edge cap @ 25pp                    → ✓ applies (skip bet if |edge_pct| > 25)

Read-only — no model writes. Does not modify backtest_inplay_edge.py /
backtest_inplay_edge_v2.py.

Run:
    python scripts/iter29_compare_fixes.py
    python scripts/iter29_compare_fixes.py --max-games 10
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from math import erf, sqrt
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as v1            # noqa: E402
import backtest_inplay_edge as bie       # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SNAPSHOT_POINTS = ("endQ1", "endQ2", "endQ3")
THRESHOLDS = (0.5, 1.0, 1.5, 2.0, 3.0)
DEFAULT_ODDS = -110

# iter-28 risk-reducing fix constants (mirrored from inplay_bet_ranker.py).
_COUNTING_STAT_SIGMA_FLOOR = {"blk", "stl", "fg3m"}
EDGE_CAP_PP = 25.0
# -110 implied prob = 100 / 210 = 0.523809...
_IMPLIED_PROB_AT_M110 = 100.0 / 210.0


def _patched_model_hit_prob(point_pred: float, line: float,
                             stat: str, side: str,
                             counters: Optional[Dict[str, int]] = None
                             ) -> Tuple[float, float]:
    """Mirror iter-28's sigma-floor for BLK/STL/FG3M.

    Returns (prob, sigma_used). The backtest has only a point estimate + a
    canonical _CAL_SPREAD sigma. The point IS the de-facto q50 for floor
    derivation.
    """
    cal_sigma = bie._CAL_SPREAD.get(stat, 1.0) / (2.0 * 1.2816)
    sigma = cal_sigma
    if stat in _COUNTING_STAT_SIGMA_FLOOR:
        floor_sigma = max(0.4 * float(point_pred or 0), 0.5)
        if floor_sigma > cal_sigma:
            sigma = floor_sigma
            if counters is not None:
                counters["sigma_floor_activated"] += 1
                counters[f"sigma_floor_{stat}"] += 1
    if sigma <= 0:
        prob = 1.0 if (
            (side == "OVER" and point_pred > line)
            or (side == "UNDER" and point_pred < line)
        ) else 0.0
        return prob, sigma
    z = (line - point_pred) / sigma
    cdf_at_line = 0.5 * (1.0 + erf(z / sqrt(2.0)))
    p_over = 1.0 - cdf_at_line
    return (p_over if side == "OVER" else 1.0 - p_over), sigma


def simulate_bets_patched(
    triples: Dict[Tuple[str, int, str], float],
    lines: Dict[Tuple[str, int, str], float],
    actuals: Dict[Tuple[str, int, str], float],
    threshold: float,
    odds: int = DEFAULT_ODDS,
    counters: Optional[Dict[str, int]] = None,
) -> Dict[str, dict]:
    """Mirror of bie.simulate_bets WITH iter-28 sigma-floor + edge-cap."""
    out: Dict[str, dict] = {s: {
        "n_bets": 0, "wins": 0,
        "stake_flat": 0.0, "pnl_flat": 0.0,
        "stake_kelly": 0.0, "pnl_kelly": 0.0,
        "n_edge_capped": 0,
    } for s in STATS}

    for key, pred in triples.items():
        gid, pid, stat = key
        line = lines.get(key)
        actual = actuals.get(key)
        if line is None or actual is None:
            continue
        edge = pred - line
        if abs(edge) < threshold:
            continue
        side = "OVER" if edge > 0 else "UNDER"

        prob, sigma_used = _patched_model_hit_prob(pred, line, stat, side,
                                                   counters=counters)
        kf = bie.kelly_fraction(prob, odds)
        if kf <= 0:
            continue

        # iter-28 risk-reducing fix: edge cap @ 25pp.
        edge_pct = (prob - _IMPLIED_PROB_AT_M110) * 100.0
        if abs(edge_pct) > EDGE_CAP_PP:
            out[stat]["n_edge_capped"] += 1
            if counters is not None:
                counters["edge_cap_triggered"] += 1
                counters[f"edge_cap_{stat}"] += 1
            continue

        pnl_flat = bie.settle_bet(1.0, side, line, actual, odds)
        pnl_kelly = bie.settle_bet(kf, side, line, actual, odds)
        b = out[stat]
        b["n_bets"] += 1
        if pnl_flat > 0:
            b["wins"] += 1
        b["stake_flat"] += 1.0
        b["pnl_flat"] += pnl_flat
        b["stake_kelly"] += kf
        b["pnl_kelly"] += pnl_kelly

    for s, b in out.items():
        b["roi_flat"] = (b["pnl_flat"] / b["stake_flat"]) if b["stake_flat"] > 0 else None
        b["roi_kelly"] = (b["pnl_kelly"] / b["stake_kelly"]) if b["stake_kelly"] > 0 else None
        b["win_rate"] = (b["wins"] / b["n_bets"]) if b["n_bets"] > 0 else None
    return out


def _pool_across_stats(per_stat_results: Dict[str, dict]) -> dict:
    """Aggregate per-stat cells into one pooled cell (n_bets-weighted)."""
    n_bets = sum(c.get("n_bets", 0) for c in per_stat_results.values())
    wins = sum(c.get("wins", 0) for c in per_stat_results.values())
    stake_flat = sum(c.get("stake_flat", 0.0) for c in per_stat_results.values())
    pnl_flat = sum(c.get("pnl_flat", 0.0) for c in per_stat_results.values())
    n_capped = sum(c.get("n_edge_capped", 0) for c in per_stat_results.values())
    return {
        "n_bets": n_bets,
        "wins": wins,
        "n_edge_capped": n_capped,
        "win_rate": (wins / n_bets) if n_bets > 0 else None,
        "roi_flat": (pnl_flat / stake_flat) if stake_flat > 0 else None,
    }


def run(max_games: Optional[int] = None,
        output: Optional[str] = None) -> int:
    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    print(f"  iter29_compare_fixes: {len(games)} games")

    game_dates: Dict[str, str] = {}
    for gid in games:
        d = v1.find_game_date(gid, qstats_df)
        if d:
            game_dates[gid] = d
    print(f"  dated games: {len(game_dates)} / {len(games)}")

    # Snapshot reconstruction + projection at all 3 points.
    inplay_by_point: Dict[str, Dict[Tuple[str, int, str], float]] = {
        p: {} for p in SNAPSHOT_POINTS
    }
    actuals_t: Dict[Tuple[str, int, str], float] = {}
    for gid in games:
        for point in SNAPSHOT_POINTS:
            snap = v1.build_snapshot(gid, point, qstats_df)
            if snap is None:
                continue
            for (pid, stat), proj in v1.project_snapshot_to_finals(snap).items():
                inplay_by_point[point][(gid, pid, stat)] = float(proj)
        for (pid, stat), act in v1.actuals_for_game(gid, qstats_df).items():
            actuals_t[(gid, pid, stat)] = float(act)
    for point in SNAPSHOT_POINTS:
        print(f"  {point} projections: {len(inplay_by_point[point])}")

    lines = v1.pregame_predictions_via_gamelog(game_dates, qstats_df)
    print(f"  L5 line proxies: {len(lines)}")

    # Side-by-side comparison.
    results_iter26: Dict[str, Dict[float, Dict[str, dict]]] = {
        p: {} for p in SNAPSHOT_POINTS
    }
    results_iter29: Dict[str, Dict[float, Dict[str, dict]]] = {
        p: {} for p in SNAPSHOT_POINTS
    }
    counters: Dict[str, int] = defaultdict(int)

    for point in SNAPSHOT_POINTS:
        for thr in THRESHOLDS:
            results_iter26[point][thr] = bie.simulate_bets(
                inplay_by_point[point], lines, actuals_t, thr)
            results_iter29[point][thr] = simulate_bets_patched(
                inplay_by_point[point], lines, actuals_t, thr,
                counters=counters,
            )

    # ── Build report ────────────────────────────────────────────────────────
    out_lines: List[str] = []
    out_lines.append("# iter-29: iter-28 fix impact on iter-26 in-play backtest")
    out_lines.append("")
    out_lines.append(f"**Games analyzed:** {len(games)}")
    out_lines.append("")
    out_lines.append(
        "Side-by-side comparison of the iter-26 in-play edge backtest (no "
        "iter-28 fixes applied) vs the iter-29 patched version (sigma-floor "
        "for BLK/STL/FG3M + edge-cap @ 25pp applied at the same point in the "
        "simulate_bets pipeline)."
    )
    out_lines.append("")
    out_lines.append(
        "**Note:** the iter-28 quantile-sanity-guard + heuristic-fallback "
        "fixes are NO-OPS here because the backtest uses a single point "
        "estimate + the canonical _CAL_SPREAD sigma rather than q10/q50/q90 "
        "from the quantile heads. Only the sigma-floor + edge-cap fixes can "
        "fire in this pipeline."
    )
    out_lines.append("")

    # ── Pooled headline at endQ3 / threshold=1.0 ───────────────────────────
    out_lines.append("## Headline: endQ3 / threshold=1.0 pooled across stats")
    out_lines.append("")
    pooled_26 = _pool_across_stats(results_iter26["endQ3"][1.0])
    pooled_29 = _pool_across_stats(results_iter29["endQ3"][1.0])
    out_lines.append("| metric | iter-26 | iter-29 | delta |")
    out_lines.append("|--------|--------:|--------:|------:|")

    def _fmt_int(a, b):
        return f"{a - b:+d}"

    def _fmt_pct(a, b):
        if a is None or b is None:
            return "—"
        return f"{(a - b) * 100:+.2f}pp"

    def _fmt_or_dash(x, fmt):
        return format(x, fmt) if x is not None else "—"

    out_lines.append(
        f"| n_bets | {pooled_26['n_bets']} | {pooled_29['n_bets']} | "
        f"{_fmt_int(pooled_29['n_bets'], pooled_26['n_bets'])} |"
    )
    out_lines.append(
        f"| hit_rate | "
        f"{_fmt_or_dash(pooled_26['win_rate'], '.4f')} | "
        f"{_fmt_or_dash(pooled_29['win_rate'], '.4f')} | "
        f"{_fmt_pct(pooled_29['win_rate'], pooled_26['win_rate'])} |"
    )
    out_lines.append(
        f"| ROI_flat | "
        f"{_fmt_or_dash(pooled_26['roi_flat'], '+.4f')} | "
        f"{_fmt_or_dash(pooled_29['roi_flat'], '+.4f')} | "
        f"{_fmt_pct(pooled_29['roi_flat'], pooled_26['roi_flat'])} |"
    )
    out_lines.append(
        f"| n_edge_capped | 0 | {pooled_29['n_edge_capped']} | "
        f"+{pooled_29['n_edge_capped']} |"
    )
    out_lines.append("")

    # ── Counters ────────────────────────────────────────────────────────────
    out_lines.append("## Counter activations (across ALL snapshot × threshold)")
    out_lines.append("")
    out_lines.append("| event | count |")
    out_lines.append("|-------|------:|")
    out_lines.append(f"| sigma_floor_activated | {counters.get('sigma_floor_activated', 0)} |")
    out_lines.append(f"| - sigma_floor_blk     | {counters.get('sigma_floor_blk', 0)} |")
    out_lines.append(f"| - sigma_floor_stl     | {counters.get('sigma_floor_stl', 0)} |")
    out_lines.append(f"| - sigma_floor_fg3m    | {counters.get('sigma_floor_fg3m', 0)} |")
    out_lines.append(f"| edge_cap_triggered    | {counters.get('edge_cap_triggered', 0)} |")
    for s in STATS:
        out_lines.append(f"| - edge_cap_{s:5s}     | {counters.get(f'edge_cap_{s}', 0)} |")
    out_lines.append("")

    # ── Master per-stat × per-snapshot × per-threshold table ─────────────────
    out_lines.append("## Side-by-side: per snapshot / stat / threshold (flat ROI)")
    out_lines.append("")
    out_lines.append(
        "| snap | stat | thr | n_26 | n_29 | hit_26 | hit_29 | "
        "ROI_26 | ROI_29 | capped |"
    )
    out_lines.append(
        "|------|------|----:|-----:|-----:|-------:|-------:|"
        "-------:|-------:|-------:|"
    )

    def _f(x, fmt):
        return format(x, fmt) if x is not None else "—"

    for point in SNAPSHOT_POINTS:
        for stat in STATS:
            for thr in THRESHOLDS:
                c26 = results_iter26[point][thr][stat]
                c29 = results_iter29[point][thr][stat]
                out_lines.append(
                    f"| {point} | {stat} | {thr} | "
                    f"{c26.get('n_bets', 0)} | {c29.get('n_bets', 0)} | "
                    f"{_f(c26.get('win_rate'), '.3f')} | "
                    f"{_f(c29.get('win_rate'), '.3f')} | "
                    f"{_f(c26.get('roi_flat'), '+.4f')} | "
                    f"{_f(c29.get('roi_flat'), '+.4f')} | "
                    f"{c29.get('n_edge_capped', 0)} |"
                )
    out_lines.append("")

    # ── Per-stat pooled (across snapshots) at threshold=1.0 ─────────────────
    out_lines.append("## Per-stat pooled across snapshots at threshold=1.0")
    out_lines.append("")
    out_lines.append(
        "| stat | n_26 | n_29 | dropped | hit_26 | hit_29 | "
        "ROI_26 | ROI_29 |"
    )
    out_lines.append(
        "|------|-----:|-----:|--------:|-------:|-------:|"
        "-------:|-------:|"
    )
    for stat in STATS:
        pooled26 = {"n_bets": 0, "wins": 0, "pnl_flat": 0.0, "stake_flat": 0.0}
        pooled29 = {"n_bets": 0, "wins": 0, "pnl_flat": 0.0, "stake_flat": 0.0}
        for point in SNAPSHOT_POINTS:
            c26 = results_iter26[point][1.0][stat]
            c29 = results_iter29[point][1.0][stat]
            for k in ("n_bets", "wins", "pnl_flat", "stake_flat"):
                pooled26[k] += c26.get(k, 0)
                pooled29[k] += c29.get(k, 0)
        hit26 = (pooled26["wins"] / pooled26["n_bets"]) if pooled26["n_bets"] else None
        hit29 = (pooled29["wins"] / pooled29["n_bets"]) if pooled29["n_bets"] else None
        roi26 = (pooled26["pnl_flat"] / pooled26["stake_flat"]) if pooled26["stake_flat"] else None
        roi29 = (pooled29["pnl_flat"] / pooled29["stake_flat"]) if pooled29["stake_flat"] else None
        dropped = pooled26["n_bets"] - pooled29["n_bets"]
        out_lines.append(
            f"| {stat} | {pooled26['n_bets']} | {pooled29['n_bets']} | {dropped} | "
            f"{_f(hit26, '.3f')} | {_f(hit29, '.3f')} | "
            f"{_f(roi26, '+.4f')} | {_f(roi29, '+.4f')} |"
        )
    out_lines.append("")

    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "iter29_fix_comparison.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out_lines) + "\n")
    print(f"  wrote {out_path}")

    # ── Console summary ────────────────────────────────────────────────────
    def _show(x, fmt):
        return format(x, fmt) if x is not None else "—"

    print("\n  HEADLINE (endQ3 / threshold=1.0 pooled):")
    print(f"    iter-26: n={pooled_26['n_bets']}  "
          f"hit={_show(pooled_26['win_rate'], '.4f')}  "
          f"ROI={_show(pooled_26['roi_flat'], '+.4f')}")
    print(f"    iter-29: n={pooled_29['n_bets']}  "
          f"hit={_show(pooled_29['win_rate'], '.4f')}  "
          f"ROI={_show(pooled_29['roi_flat'], '+.4f')}  "
          f"capped={pooled_29['n_edge_capped']}")
    print(f"\n  COUNTERS (across all snapshot×threshold):")
    print(f"    sigma_floor activations: {counters.get('sigma_floor_activated', 0)}")
    print(f"      blk:  {counters.get('sigma_floor_blk', 0)}")
    print(f"      stl:  {counters.get('sigma_floor_stl', 0)}")
    print(f"      fg3m: {counters.get('sigma_floor_fg3m', 0)}")
    print(f"    edge_cap triggers:       {counters.get('edge_cap_triggered', 0)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    return run(max_games=args.max_games, output=args.output)


if __name__ == "__main__":
    sys.exit(main())
