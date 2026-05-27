"""backtest_inplay_real_lines.py — iter-28 (loop 6).

In-game ROI on REAL closing lines from extended_oos_canonical.csv (10,927 rows,
2024 playoffs + 2026 reg season). The natural follow-up to iter-26's L5-proxy
backtest, which produced +80% endQ3 flat ROI and the explicit caveat "real
sportsbook lines will be substantially sharper than L5; ROI numbers will be
lower." iter-28 produces the honest real-line number.

Pipeline
--------
1.  Load extended_oos_canonical.csv (date, player, opp, venue, stat,
    closing_line, over_odds, under_odds, actual_value).
2.  Build player_name -> player_id index from data/nba/boxscore_*.json
    (every player who ever appeared in a tracked game).
3.  Build game_id -> ISO date index for every game in
    data/player_quarter_stats.parquet:
      a. games_2025-26.json schedule for the 67 games with prefix 0022500XX
      b. retro_inplay_mae.find_game_date for the 889 games with prefix 002240XX
4.  Join canonical rows -> (game_id, player_id) via (date, player_name).
5.  For each joined row, reconstruct the endQ1/endQ2/endQ3 snapshot via
    retro_inplay_mae.build_snapshot, project via predict_in_game, and bet via
    backtest_inplay_edge.simulate_bets using the REAL closing_line (not the
    L5 mean) and the REAL actual_value (not the quarter_stats sum).
6.  Aggregate ROI per (snapshot_period, stat, threshold).
7.  Output side-by-side comparison to iter-26's L5-proxy numbers.

Crucially: this script is strictly READ-ONLY. No model writes, no fetches,
no edits to predict_in_game / live_engine / unified_pipeline.

Coverage caveat
---------------
The canonical CSV covers 2024-04-21..2024-05-23 (playoffs 0042 prefix, NO
quarter_stats coverage) and 2026-01-28..2026-05-11 (game_ids around
0022500677+ and 0042500311+, ALSO outside the 002240XX + 002250XX..074 window
that quarter_stats covers). The actual realized overlap is reported in the
"coverage" line of the output table and is expected to be small. The script
is the durable harness that will yield real numbers as soon as overlapping
quarter_stats data lands.

Run:
    python scripts/backtest_inplay_real_lines.py
    python scripts/backtest_inplay_real_lines.py --output scripts/_results/inplay_real_lines_v1.md
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as v1        # snapshot + helpers       # noqa: E402
import backtest_inplay_edge as bie   # simulate_bets + math     # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk")  # canonical has no tov
SNAPSHOT_POINTS = ("endQ1", "endQ2", "endQ3")
THRESHOLDS = (0.5, 1.0, 1.5, 2.0, 3.0)
DEFAULT_ODDS = -110

CANONICAL_CSV = os.path.join(
    PROJECT_DIR, "data", "external", "historical_lines",
    "extended_oos_canonical.csv")
SCHEDULE_2526 = os.path.join(PROJECT_DIR, "data", "nba", "games_2025-26.json")


# ── canonical CSV loader ──────────────────────────────────────────────────────

def load_canonical(path: str = CANONICAL_CSV) -> List[dict]:
    """Read the extended OOS canonical CSV into a list of dicts. Cast numerics."""
    out: List[dict] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                row["closing_line"] = float(row["closing_line"])
                row["actual_value"] = float(row["actual_value"])
                row["over_odds"] = int(row["over_odds"])
                row["under_odds"] = int(row["under_odds"])
            except (TypeError, ValueError):
                continue
            row["stat"] = str(row["stat"]).lower()
            out.append(row)
    return out


# ── player_name -> player_id index ────────────────────────────────────────────

def build_name_to_pid_index() -> Dict[str, int]:
    """Map player_name -> player_id by scanning every data/nba/boxscore_*.json
    (excluding boxscore_adv_*). Last-write-wins on name collisions — fine for
    our use because canonical CSV names are unambiguous in the NBA roster.
    """
    name_to_pid: Dict[str, int] = {}
    fps = [f for f in glob.glob(os.path.join(PROJECT_DIR, "data", "nba",
                                              "boxscore_*.json"))
           if "boxscore_adv" not in os.path.basename(f)]
    for fp in fps:
        try:
            with open(fp, encoding="utf-8") as fh:
                j = json.load(fh)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        for p in j.get("players", []) or []:
            name = p.get("player_name")
            pid = p.get("player_id")
            if name and pid:
                try:
                    name_to_pid[str(name)] = int(pid)
                except (TypeError, ValueError):
                    continue
    return name_to_pid


# ── game_id -> ISO date index ─────────────────────────────────────────────────

def build_gid_to_date_index(qstats_df) -> Dict[str, str]:
    """Combine the 2025-26 schedule JSON (fast) and retro_inplay_mae.
    find_game_date (slower, gamelog match) to date every game in the
    quarter_stats parquet.
    """
    gid_to_date: Dict[str, str] = {}

    # Fast path: schedule JSON for 2025-26 reg season games.
    if os.path.exists(SCHEDULE_2526):
        try:
            with open(SCHEDULE_2526, encoding="utf-8") as fh:
                sched = json.load(fh)
            for g in sched:
                gid = g.get("GAME_ID")
                d = g.get("GAME_DATE")
                if gid and d:
                    gid_to_date[gid] = d
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            pass

    # Slow path: gamelog match for everything else.
    games = sorted(qstats_df["game_id"].unique().tolist())
    for gid in games:
        if gid in gid_to_date:
            continue
        d = v1.find_game_date(gid, qstats_df)
        if d:
            gid_to_date[gid] = d
    return gid_to_date


# ── matching canonical rows -> (game_id, player_id) ───────────────────────────

def join_canonical_to_games(
    canonical: List[dict],
    name_to_pid: Dict[str, int],
    gid_to_date: Dict[str, str],
) -> Tuple[List[dict], Dict[str, int]]:
    """Annotate each canonical row with (game_id, player_id) when both
    can be matched. Returns (matched_rows, coverage_stats).

    A match requires:
      - canonical.player resolves to a player_id via boxscore index
      - canonical.date appears in gid_to_date.values()
      - there is exactly one game on that date where the player appeared
        (we cross-check by checking quarter_stats for that game_id + player_id)
    """
    # Invert gid_to_date: date -> list of game_ids.
    date_to_gids: Dict[str, List[str]] = defaultdict(list)
    for gid, d in gid_to_date.items():
        date_to_gids[d].append(gid)

    stats: Dict[str, int] = defaultdict(int)
    matched: List[dict] = []

    # Cache: (date, player_id) -> game_id.
    join_cache: Dict[Tuple[str, int], Optional[str]] = {}

    # Need quarter_stats df for player-in-game check.
    import pandas as pd
    qdf = v1.load_quarter_stats()
    # Index by (game_id, player_id) for O(1) lookup.
    qdf_keys = set(zip(qdf["game_id"].astype(str),
                       qdf["player_id"].astype(int)))

    for row in canonical:
        stats["total"] += 1
        date = row.get("date")
        player = row.get("player")
        pid = name_to_pid.get(player)
        if pid is None:
            stats["miss_player"] += 1
            continue
        stats["have_player_id"] += 1

        cache_key = (date, pid)
        if cache_key in join_cache:
            gid = join_cache[cache_key]
        else:
            gids_on_date = date_to_gids.get(date, [])
            gid = None
            for candidate in gids_on_date:
                if (candidate, pid) in qdf_keys:
                    gid = candidate
                    break
            join_cache[cache_key] = gid

        if gid is None:
            stats["miss_game"] += 1
            continue

        stats["matched"] += 1
        row2 = dict(row)
        row2["game_id"] = gid
        row2["player_id"] = pid
        matched.append(row2)

    return matched, dict(stats)


# ── simulate against REAL lines ───────────────────────────────────────────────

def simulate_real_lines(
    inplay: Dict[Tuple[str, int, str], float],
    matched: List[dict],
    threshold: float,
    odds: int = DEFAULT_ODDS,
) -> Dict[str, dict]:
    """Walk every matched canonical row; bet using REAL closing_line + REAL
    actual_value. Returns the same shape as backtest_inplay_edge.simulate_bets.
    """
    out: Dict[str, dict] = {s: {
        "n_bets": 0, "wins": 0,
        "stake_flat": 0.0, "pnl_flat": 0.0,
        "stake_kelly": 0.0, "pnl_kelly": 0.0,
    } for s in STATS}

    for row in matched:
        stat = row["stat"]
        if stat not in STATS:
            continue
        key = (row["game_id"], int(row["player_id"]), stat)
        pred = inplay.get(key)
        if pred is None:
            continue
        line = row["closing_line"]
        actual = row["actual_value"]

        edge = pred - line
        if abs(edge) < threshold:
            continue
        side = "OVER" if edge > 0 else "UNDER"
        sigma = bie._CAL_SPREAD.get(stat, 1.0) / (2.0 * 1.2816)
        prob = bie.model_hit_prob(pred, line, sigma, side)
        kf = bie.kelly_fraction(prob, odds)
        if kf <= 0:
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


# ── L5-proxy comparison numbers (iter-26 endQ3 ROI by stat × threshold) ───────
# Sourced verbatim from scripts/_results/inplay_edge_backtest_v2.md (cycle 97d)
# so the side-by-side compare doesn't require re-running iter-26.

L5_PROXY_ENDQ3_ROI: Dict[Tuple[str, float], float] = {
    ("pts", 0.5): 0.6764, ("pts", 1.0): 0.6997, ("pts", 1.5): 0.7240,
    ("pts", 2.0): 0.7409, ("pts", 3.0): 0.7745,
    ("reb", 0.5): 0.7312, ("reb", 1.0): 0.7779, ("reb", 1.5): 0.8342,
    ("reb", 2.0): 0.8587, ("reb", 3.0): 0.8754,
    ("ast", 0.5): 0.7543, ("ast", 1.0): 0.8165, ("ast", 1.5): 0.8545,
    ("ast", 2.0): 0.8980, ("ast", 3.0): 0.9091,
    ("fg3m", 0.5): 0.8176, ("fg3m", 1.0): 0.8551, ("fg3m", 1.5): 0.8766,
    ("fg3m", 2.0): 0.9091, ("fg3m", 3.0): 0.9091,
    ("stl", 0.5): 0.7827, ("stl", 1.0): 0.8949, ("stl", 1.5): 0.9028,
    ("stl", 2.0): 0.8990, ("stl", 3.0): 0.9091,
    ("blk", 0.5): 0.8269, ("blk", 1.0): 0.8870, ("blk", 1.5): 0.9091,
    ("blk", 2.0): 0.9091, ("blk", 3.0): 0.9091,
}


# ── report ────────────────────────────────────────────────────────────────────

def build_report(
    coverage: Dict[str, int],
    matched_total: int,
    real_results: Dict[str, Dict[float, Dict[str, dict]]],
    pregame_strategy_d_extended: float = 0.2329,
) -> str:
    lines: List[str] = []
    lines.append("# In-play ROI on REAL closing lines — iter-28 (loop 6)")
    lines.append("")
    lines.append(
        "Iter-26 reported +80% endQ3 flat ROI on an L5-rolling-mean line proxy "
        "and noted that real sportsbook lines would be substantially sharper. "
        "Iter-28 produces the honest real-line number using "
        "data/external/historical_lines/extended_oos_canonical.csv (10,927 "
        "rows from 2024 playoffs + 2026 reg season + 2025-26 playoffs)."
    )
    lines.append("")
    lines.append("**RESEARCH MEASUREMENT — NOT a betting recommendation.**")
    lines.append("")

    # ── coverage table ─────────────────────────────────────────────────────
    lines.append("## Coverage: canonical rows -> reconstructable in-game snapshots")
    lines.append("")
    lines.append("| metric | rows |")
    lines.append("|--------|-----:|")
    lines.append(f"| canonical rows (total) | {coverage.get('total', 0)} |")
    lines.append(f"| player_name resolved to player_id | "
                 f"{coverage.get('have_player_id', 0)} |")
    lines.append(f"| matched to a game_id in quarter_stats | "
                 f"{coverage.get('matched', 0)} |")
    lines.append(f"| miss: player not in boxscore index | "
                 f"{coverage.get('miss_player', 0)} |")
    lines.append(f"| miss: no game on date / player not in that game | "
                 f"{coverage.get('miss_game', 0)} |")
    lines.append(f"| effective coverage | "
                 f"{(coverage.get('matched', 0) / max(coverage.get('total', 1), 1)) * 100:.2f}% |")
    lines.append("")

    # ── master table: per snapshot / stat / threshold ──────────────────────
    lines.append("## Real-line in-game ROI by snapshot point, stat, and threshold")
    lines.append("")
    lines.append("| snapshot | stat | thr | n_bets | win_rate | "
                 "ROI_flat | ROI_kelly |")
    lines.append("|----------|------|----:|-------:|---------:|"
                 "---------:|----------:|")

    def _fmt(x, fmt):
        return format(x, fmt) if x is not None else "—"

    for point in SNAPSHOT_POINTS:
        for stat in STATS:
            for thr in THRESHOLDS:
                cell = real_results.get(point, {}).get(thr, {}).get(stat, {})
                if cell.get("n_bets", 0) == 0:
                    # Still emit row so the gap is visible.
                    lines.append(
                        f"| {point} | {stat} | {thr} | 0 | — | — | — |"
                    )
                    continue
                lines.append(
                    f"| {point} | {stat} | {thr} | {cell.get('n_bets', 0)} | "
                    f"{_fmt(cell.get('win_rate'), '.3f')} | "
                    f"{_fmt(cell.get('roi_flat'), '+.4f')} | "
                    f"{_fmt(cell.get('roi_kelly'), '+.4f')} |"
                )

    lines.append("")

    # ── apples-to-apples vs iter-26 L5 proxy at endQ3 ─────────────────────
    lines.append("## Real-line in-game ROI vs iter-26 L5-proxy ROI (endQ3)")
    lines.append("")
    lines.append(
        "Side-by-side: real closing lines vs the L5-rolling-mean proxy "
        "iter-26 used. The delta is the cost of pretending L5 = book."
    )
    lines.append("")
    lines.append("| stat | thr | n_real | ROI_real | ROI_L5_proxy | Δ |")
    lines.append("|------|----:|-------:|---------:|-------------:|---:|")
    for stat in STATS:
        for thr in (0.5, 1.0, 1.5):
            cell = real_results.get("endQ3", {}).get(thr, {}).get(stat, {})
            roi_real = cell.get("roi_flat")
            roi_l5 = L5_PROXY_ENDQ3_ROI.get((stat, thr))
            delta = None
            if roi_real is not None and roi_l5 is not None:
                delta = roi_real - roi_l5
            lines.append(
                f"| {stat} | {thr} | {cell.get('n_bets', 0)} | "
                f"{_fmt(roi_real, '+.4f')} | "
                f"{_fmt(roi_l5, '+.4f')} | "
                f"{_fmt(delta, '+.4f')} |"
            )
    lines.append("")

    # ── pooled headline ───────────────────────────────────────────────────
    pooled_n = pooled_pnl = pooled_stake = 0
    for stat in STATS:
        cell = real_results.get("endQ3", {}).get(1.0, {}).get(stat, {})
        pooled_n += cell.get("n_bets", 0)
        pooled_pnl += cell.get("pnl_flat", 0.0)
        pooled_stake += cell.get("stake_flat", 0.0)
    pooled_roi = (pooled_pnl / pooled_stake) if pooled_stake > 0 else None

    lines.append("## Headline: pooled real-line in-game ROI vs pregame Strategy D")
    lines.append("")
    if pooled_roi is None:
        lines.append(
            "**Inconclusive — zero matched bets at endQ3 / threshold 1.0.** "
            "The canonical CSV's date range does not overlap with the "
            "player_quarter_stats coverage (2024-25 reg season + early "
            "2025-26 thru 0022500074). To produce a real-line number we "
            "need quarter_box ingestion of the 2024 playoffs and the 2026 "
            "Jan-onward window. The script is in place; data is the gap."
        )
    else:
        lines.append(
            f"**Pooled real-line in-game ROI at endQ3, threshold 1.0: "
            f"{pooled_roi:+.4f} on {pooled_n} bets.**"
        )
        lines.append("")
        lines.append(
            f"Pregame Strategy D extended OOS ROI: "
            f"+{pregame_strategy_d_extended:.4f} (from iter-25 sweep)."
        )
        ratio = pooled_roi / pregame_strategy_d_extended
        if ratio >= 1.5:
            verdict = (f"**IN-GAME EDGE SURVIVES** — real-line in-game ROI "
                       f"is {ratio:.2f}x pregame. The L5-proxy headline "
                       f"shrinks but stays meaningfully positive.")
        elif ratio >= 1.0:
            verdict = (f"**IN-GAME EDGE PARTIALLY SURVIVES** — real-line "
                       f"in-game ROI is {ratio:.2f}x pregame. The L5 proxy "
                       f"overstated the gap but in-game still beats "
                       f"pregame.")
        else:
            verdict = (f"**IN-GAME EDGE DISAPPEARS ON REAL LINES** — "
                       f"real-line in-game ROI is only {ratio:.2f}x "
                       f"pregame. Most of iter-26's +80% was L5 proxy "
                       f"laziness, not real signal.")
        lines.append("")
        lines.append(verdict)
    lines.append("")

    # ── caveats ───────────────────────────────────────────────────────────
    lines.append("## Caveats")
    lines.append("")
    lines.append(
        "- **canonical CSV stat coverage:** PTS / REB / AST / FG3M present "
        "throughout, STL / BLK present only in the 2024 playoffs portion. "
        "(benashkar 2026 portion omits STL/BLK per iter-24 notes.) TOV is "
        "absent everywhere — not measurable here."
    )
    lines.append(
        "- **date coverage gap:** canonical CSV covers 2024-04-21..2024-05-23 "
        "(playoffs 0042 prefix, no quarter_stats coverage) and "
        "2026-01-28..2026-05-11 (game_ids around 0022500677+ and "
        "0042500311+, outside quarter_stats's 002240XX + 002250XX..074 "
        "window). Effective overlap with quarter_stats is reported in the "
        "coverage table above."
    )
    lines.append(
        "- **closing-line sharpness:** sportsbook closing lines incorporate "
        "the L5 mean plus injury, lineup, market signal, and shrinkage to "
        "season prior. ROI on real lines is structurally lower than on the "
        "L5 proxy because the model's edge above L5 partially overlaps "
        "with the line's own move."
    )
    lines.append(
        "- **vig handling:** all bets settle at -110 vs the canonical row's "
        "side. We do not split bets across sides when both have edge."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


# ── main runner ──────────────────────────────────────────────────────────────

def run(output: Optional[str] = None) -> int:
    t0 = time.time()

    # 1) Load canonical.
    print("  loading canonical CSV...")
    canonical = load_canonical()
    print(f"  canonical rows: {len(canonical)}")

    # 2) player_name -> player_id.
    print("  building player_name index from boxscores...")
    t1 = time.time()
    name_to_pid = build_name_to_pid_index()
    print(f"  player names indexed: {len(name_to_pid)} "
          f"({time.time()-t1:.1f}s)")

    # 3) quarter_stats df + game_id -> date.
    print("  loading player_quarter_stats parquet...")
    qstats_df = v1.load_quarter_stats()
    print(f"  quarter_stats rows: {len(qstats_df)}, "
          f"games: {qstats_df['game_id'].nunique()}")

    print("  building game_id -> date index...")
    t1 = time.time()
    gid_to_date = build_gid_to_date_index(qstats_df)
    print(f"  dated games: {len(gid_to_date)} "
          f"({time.time()-t1:.1f}s)")

    # 4) Join canonical -> (game_id, player_id).
    print("  joining canonical rows to games...")
    matched, coverage = join_canonical_to_games(
        canonical, name_to_pid, gid_to_date)
    print(f"  matched canonical rows: {len(matched)} / {len(canonical)} "
          f"(coverage breakdown: {coverage})")

    # 5) For each matched game, build snapshots at all 3 points + project.
    #    The cycle-88 projector is HEAVY (~1-3s per snapshot), so cache by
    #    (game_id, snapshot_point).
    print("  building snapshots + projecting...")
    t1 = time.time()
    inplay_by_point: Dict[str, Dict[Tuple[str, int, str], float]] = {
        p: {} for p in SNAPSHOT_POINTS
    }
    matched_gids = sorted({r["game_id"] for r in matched})
    for gid in matched_gids:
        for point in SNAPSHOT_POINTS:
            snap = v1.build_snapshot(gid, point, qstats_df)
            if snap is None:
                continue
            for (pid, stat), proj in v1.project_snapshot_to_finals(snap).items():
                inplay_by_point[point][(gid, pid, stat)] = float(proj)
    for point in SNAPSHOT_POINTS:
        print(f"    {point} projections: {len(inplay_by_point[point])} "
              f"({time.time()-t1:.1f}s elapsed)")

    # 6) Run real-line simulator per (point, threshold).
    print("  simulating bets on REAL closing lines...")
    real_results: Dict[str, Dict[float, Dict[str, dict]]] = {
        p: {} for p in SNAPSHOT_POINTS
    }
    for point in SNAPSHOT_POINTS:
        for thr in THRESHOLDS:
            real_results[point][thr] = simulate_real_lines(
                inplay_by_point[point], matched, thr)

    # 7) Report.
    report = build_report(coverage, len(matched), real_results)
    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "inplay_real_lines_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"  wrote {out_path}")
    print(f"  total elapsed: {time.time()-t0:.1f}s")

    # Console summary at endQ3 / threshold 1.0.
    print("\n  Real-line ROI @ endQ3, threshold 1.0:")
    print("  stat   n_bets   win_rate   ROI_real   ROI_L5    Δ")
    for stat in STATS:
        cell = real_results["endQ3"].get(1.0, {}).get(stat, {})
        nb = cell.get("n_bets", 0)
        wr = cell.get("win_rate")
        roi_real = cell.get("roi_flat")
        roi_l5 = L5_PROXY_ENDQ3_ROI.get((stat, 1.0))
        delta = None
        if roi_real is not None and roi_l5 is not None:
            delta = roi_real - roi_l5

        def _r(x, w=8):
            return f"{x:+.4f}".rjust(w) if x is not None else "    —   "
        wr_s = f"{wr:.3f}" if wr is not None else "  —  "
        print(f"  {stat:4s}   {nb:>6d}   {wr_s:>7s}   "
              f"{_r(roi_real)}   {_r(roi_l5)}   {_r(delta)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=None,
                    help="Markdown output path (default: "
                         "scripts/_results/inplay_real_lines_v1.md)")
    args = ap.parse_args()
    return run(output=args.output)


if __name__ == "__main__":
    sys.exit(main())
