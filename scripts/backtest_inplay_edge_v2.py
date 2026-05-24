"""backtest_inplay_edge_v2.py — cycle 97d (loop 5). In-play ROI at endQ1/Q2/Q3.

WHY: cycle 95d (`backtest_inplay_edge.py`) measured the in-play edge against
an L5-mean line proxy ONLY at end-Q3. Cycle 93c showed end-Q2 wins 6/7 stats
on raw MAE vs pregame baseline, and cycle 94d showed end-Q3 wins 7/7 on prod
baseline. The unanswered question: does end-Q2 give competitive ROI? At
end-Q2 half the game remains, the line is still moving, so live edge has
more time to materialise. If end-Q2 ROI is >= 80% of end-Q3 ROI for some
stat, the live operator can place bets earlier with confidence.

v2 replicates cycle 95d's logic EXACTLY (same L5 proxy, same -110 odds, same
calibrated sigmas, same Kelly + settle math, same threshold sweep) but also
computes ROI at endQ1 + endQ2 — and adds an explicit "per-stat optimal
snapshot" table.

Regression gate: at endQ3 the v2 ROI table must MATCH cycle 95d's numbers
exactly (same logic, just more snapshots). Tested via
tests/test_backtest_inplay_edge_v2.py.

Strictly read-only — no model writes, no edits to predict_in_game / live_engine.

Run:
    python scripts/backtest_inplay_edge_v2.py
    python scripts/backtest_inplay_edge_v2.py --max-games 10
    python scripts/backtest_inplay_edge_v2.py --output scripts/_results/inplay_edge_backtest_v2.md
"""
from __future__ import annotations

import argparse
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

import retro_inplay_mae as v1        # snapshot + L5 helpers  # noqa: E402
import retro_inplay_mae_v2 as v2     # prod pergame builder    # noqa: E402
# Reuse cycle 95d's pure betting math + simulate_bets — same logic,
# just driven across multiple snapshot points.
import backtest_inplay_edge as bie   # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SNAPSHOT_POINTS = ("endQ1", "endQ2", "endQ3")
THRESHOLDS = (0.5, 1.0, 1.5, 2.0, 3.0)
DEFAULT_ODDS = -110

# Re-export the pure helpers so callers / tests can import them from either
# module without ambiguity. simulate_bets is the workhorse — v2 calls it once
# per (snapshot_point, threshold) pair.
american_payout = bie.american_payout
kelly_fraction = bie.kelly_fraction
model_hit_prob = bie.model_hit_prob
settle_bet = bie.settle_bet
simulate_bets = bie.simulate_bets


# ── report ────────────────────────────────────────────────────────────────────

def build_report(
    results: Dict[str, Dict[float, Dict[str, dict]]],
    pregame_results: Dict[float, Dict[str, dict]],
    n_games: int,
    n_triples_by_point: Dict[str, int],
) -> str:
    """Build the markdown report.

    `results[snapshot_point][threshold][stat]` → simulate_bets entry.
    `pregame_results[threshold][stat]`          → simulate_bets entry.
    """
    lines: List[str] = []
    lines.append("# In-play ROI at endQ1 / endQ2 / endQ3 — cycle 97d (loop 5)")
    lines.append("")
    lines.append(f"**Games analyzed:** {n_games}")
    for point in SNAPSHOT_POINTS:
        lines.append(
            f"**(game, player, stat) triples available at {point}:** "
            f"{n_triples_by_point.get(point, 0)}"
        )
    lines.append("")
    lines.append("**RESEARCH MEASUREMENT — NOT a betting recommendation.**")
    lines.append("")
    lines.append(
        "v2 of cycle 95d. Same L5-rolling-mean line proxy, same -110 odds, same "
        "calibrated sigmas, same Kelly-gated placement logic, same threshold "
        "sweep — but ROI is now reported at endQ1 + endQ2 + endQ3 so we can "
        "identify the per-stat optimal snapshot point. At end-Q2 half the game "
        "remains, so a competitive ROI there is operationally far more useful "
        "than the same ROI at end-Q3."
    )
    lines.append("")

    # ── master table: per snapshot / per stat / per threshold ──────────────
    lines.append("## ROI by snapshot point, stat, and threshold (flat $1 stakes)")
    lines.append("")
    lines.append("| snapshot | stat | thr | n_bets | win_rate | ROI_flat | ROI_kelly |")
    lines.append("|----------|------|----:|-------:|---------:|---------:|----------:|")

    def _fmt(x, fmt):
        return format(x, fmt) if x is not None else "—"

    for point in SNAPSHOT_POINTS:
        for stat in STATS:
            for thr in THRESHOLDS:
                cell = results[point].get(thr, {}).get(stat, {})
                lines.append(
                    f"| {point} | {stat} | {thr} | {cell.get('n_bets', 0)} | "
                    f"{_fmt(cell.get('win_rate'), '.3f')} | "
                    f"{_fmt(cell.get('roi_flat'), '+.4f')} | "
                    f"{_fmt(cell.get('roi_kelly'), '+.4f')} |"
                )

    lines.append("")

    # ── per-stat optimal snapshot ───────────────────────────────────────────
    lines.append("## Per-stat optimal snapshot (by ROI_flat at threshold 1.0)")
    lines.append("")
    lines.append(
        "Picks the snapshot point with the highest ROI_flat at threshold 1.0. "
        "Ties broken in favour of the EARLIER snapshot (operationally better)."
    )
    lines.append("")
    lines.append("| stat | best | endQ1 ROI | endQ2 ROI | endQ3 ROI | "
                 "endQ2 / endQ3 | endQ2 viable? |")
    lines.append("|------|------|----------:|----------:|----------:|"
                 "--------------:|---------------|")

    endq2_viable_count = 0
    for stat in STATS:
        per_point: Dict[str, Optional[float]] = {}
        for point in SNAPSHOT_POINTS:
            roi = results[point].get(1.0, {}).get(stat, {}).get("roi_flat")
            per_point[point] = roi
        # Pick best — only over snapshots that actually placed bets.
        ranked = [(p, per_point[p]) for p in SNAPSHOT_POINTS
                  if per_point[p] is not None]
        if not ranked:
            best = "—"
        else:
            # Sort by ROI desc, then by snapshot order (Q1 < Q2 < Q3 — earlier
            # wins on tie).
            best_point = max(
                ranked, key=lambda kv: (kv[1], -SNAPSHOT_POINTS.index(kv[0])))
            best = best_point[0]

        # endQ2 viability: endQ2 ROI >= 80% of endQ3 ROI (both populated).
        viable_marker = ""
        q2_roi = per_point.get("endQ2")
        q3_roi = per_point.get("endQ3")
        ratio_s = "—"
        if q2_roi is not None and q3_roi is not None and q3_roi > 0:
            ratio = q2_roi / q3_roi
            ratio_s = f"{ratio:.2f}"
            if ratio >= 0.80:
                viable_marker = "Y"
                endq2_viable_count += 1
            else:
                viable_marker = "n"

        def _r(x):
            return f"{x:+.4f}" if x is not None else "—"

        lines.append(
            f"| {stat} | {best} | "
            f"{_r(per_point.get('endQ1'))} | "
            f"{_r(per_point.get('endQ2'))} | "
            f"{_r(per_point.get('endQ3'))} | "
            f"{ratio_s} | {viable_marker} |"
        )

    lines.append("")

    # ── cycle-95d regression cross-check ────────────────────────────────────
    lines.append("## Cycle-95d regression cross-check (endQ3 ROI parity)")
    lines.append("")
    lines.append(
        "v2 reuses cycle 95d's simulate_bets verbatim. At endQ3 the ROI table "
        "below MUST match cycle 95d's `inplay_edge_backtest_v1.md` exactly — "
        "any drift would indicate a logic regression."
    )
    lines.append("")
    lines.append("| stat | thr | n_bets_endQ3 | ROI_endQ3 |")
    lines.append("|------|----:|-------------:|----------:|")
    for stat in STATS:
        for thr in THRESHOLDS:
            cell = results["endQ3"].get(thr, {}).get(stat, {})
            lines.append(
                f"| {stat} | {thr} | {cell.get('n_bets', 0)} | "
                f"{_fmt(cell.get('roi_flat'), '+.4f')} |"
            )

    lines.append("")

    # ── pregame baseline cell (one threshold, for sanity) ──────────────────
    lines.append("## Pregame baseline (L5 proxy → prod pergame) at threshold 1.0")
    lines.append("")
    lines.append("| stat | n_bets | ROI_flat |")
    lines.append("|------|-------:|---------:|")
    for stat in STATS:
        cell = pregame_results.get(1.0, {}).get(stat, {})
        lines.append(
            f"| {stat} | {cell.get('n_bets', 0)} | "
            f"{_fmt(cell.get('roi_flat'), '+.4f')} |"
        )
    lines.append("")

    # ── verdict ────────────────────────────────────────────────────────────
    lines.append("## Verdict")
    lines.append("")
    if endq2_viable_count == 0:
        lines.append(
            "**endQ2 NOT viable for any stat at threshold 1.0** — endQ3 remains "
            "the operationally correct snapshot for live betting. The half-game "
            "edge is real (vs pregame) but does not survive the 80%-of-endQ3 "
            "ROI bar. Live operator should wait until end-of-Q3."
        )
    elif endq2_viable_count <= 2:
        lines.append(
            f"**endQ2 viable for {endq2_viable_count}/7 stats at threshold 1.0.** "
            f"For the marked stats the live operator can place bets at half-time "
            f"with ROI >= 80% of the end-Q3 figure. For the rest, wait."
        )
    else:
        lines.append(
            f"**endQ2 viable for {endq2_viable_count}/7 stats at threshold 1.0.** "
            f"Half-time betting is operationally competitive for most stats — "
            f"the live edge materialises earlier than expected. The cycle-88 "
            f"system's pace + foul + blowout heuristics carry signal already by "
            f"end-of-Q2."
        )
    lines.append("")
    return "\n".join(lines) + "\n"


# ── main runner ──────────────────────────────────────────────────────────────

def run(max_games: Optional[int] = None,
        output: Optional[str] = None) -> int:
    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    print(f"  backtest_inplay_edge_v2: {len(games)} games")

    # 1) game_id → ISO date.
    game_dates: Dict[str, str] = {}
    for gid in games:
        d = v1.find_game_date(gid, qstats_df)
        if d:
            game_dates[gid] = d
    print(f"  dated games: {len(game_dates)} / {len(games)}")

    # 2) Snapshot reconstruction + projection at ALL 3 points.
    inplay_by_point: Dict[str, Dict[Tuple[str, int, str], float]] = {
        p: {} for p in SNAPSHOT_POINTS
    }
    actuals_t: Dict[Tuple[str, int, str], float] = {}
    for gid in games:
        for point in SNAPSHOT_POINTS:
            snap = v1.build_snapshot(gid, point, qstats_df)
            if snap is None:
                # cycle 88b: missing periods → skip this snapshot for this game.
                continue
            for (pid, stat), proj in v1.project_snapshot_to_finals(snap).items():
                inplay_by_point[point][(gid, pid, stat)] = float(proj)
        for (pid, stat), act in v1.actuals_for_game(gid, qstats_df).items():
            actuals_t[(gid, pid, stat)] = float(act)
    for point in SNAPSHOT_POINTS:
        print(f"  {point} projections: {len(inplay_by_point[point])}")
    print(f"  actuals: {len(actuals_t)}")

    # 3) L5 line proxy (sportsbook-line analog).
    lines = v1.pregame_predictions_via_gamelog(game_dates, qstats_df)
    print(f"  L5 line proxies: {len(lines)}")

    # 4) Pregame predictions from prod cycle-48 dispatcher (for baseline cell).
    pregame = v2.prod_pergame_predictions(game_dates, qstats_df)
    print(f"  pregame predictions: {len(pregame)}")

    # Fully-populated triples per snapshot point.
    n_triples_by_point: Dict[str, int] = {}
    for point in SNAPSHOT_POINTS:
        n = len(set(inplay_by_point[point]) & set(lines) & set(actuals_t))
        n_triples_by_point[point] = n
        print(f"  fully-populated triples at {point}: {n}")

    # 5) Run simulator at each (point × threshold).
    results: Dict[str, Dict[float, Dict[str, dict]]] = {
        p: {} for p in SNAPSHOT_POINTS
    }
    for point in SNAPSHOT_POINTS:
        for thr in THRESHOLDS:
            results[point][thr] = simulate_bets(
                inplay_by_point[point], lines, actuals_t, thr)

    pregame_results: Dict[float, Dict[str, dict]] = {}
    for thr in THRESHOLDS:
        pregame_results[thr] = simulate_bets(pregame, lines, actuals_t, thr)

    # 6) Report.
    report = build_report(results, pregame_results, len(games),
                          n_triples_by_point)
    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "inplay_edge_backtest_v2.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"  wrote {out_path}")

    # Console summary — per-stat optimal snapshot at threshold 1.0.
    print("\n  Per-stat optimal snapshot @ threshold 1.0 (flat ROI):")
    print("  stat   endQ1      endQ2      endQ3      best   endQ2 viable?")
    for stat in STATS:
        per_point = {p: results[p].get(1.0, {}).get(stat, {}).get("roi_flat")
                     for p in SNAPSHOT_POINTS}
        ranked = [(p, per_point[p]) for p in SNAPSHOT_POINTS
                  if per_point[p] is not None]
        best = "—"
        if ranked:
            best = max(ranked, key=lambda kv: (
                kv[1], -SNAPSHOT_POINTS.index(kv[0])))[0]
        q2 = per_point.get("endQ2")
        q3 = per_point.get("endQ3")
        viable = "—"
        if q2 is not None and q3 is not None and q3 > 0:
            viable = "Y" if (q2 / q3) >= 0.80 else "n"

        def _r(x):
            return f"{x:+.4f}" if x is not None else "    —   "
        print(f"  {stat:4s}   {_r(per_point['endQ1'])}  "
              f"{_r(per_point['endQ2'])}  {_r(per_point['endQ3'])}  "
              f"{best:5s}  {viable}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None,
                    help="Limit to first N games (debug).")
    ap.add_argument("--output", default=None,
                    help="Markdown output path (default: "
                         "scripts/_results/inplay_edge_backtest_v2.md)")
    args = ap.parse_args()
    return run(max_games=args.max_games, output=args.output)


if __name__ == "__main__":
    sys.exit(main())
