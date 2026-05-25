"""backtest_midQ3_snapshot.py — cycle 99d (loop 5). Mid-Q3 PROXY ROI backtest.

WHY: cycle 97d found that endQ2 ROI is >= 80% of endQ3 ROI for 5/7 stats —
half-time is operationally a viable betting snapshot. The next operational
question: what about MID-Q3 (period=3, clock=6:00)? If mid-Q3 ROI is >= 90%
of endQ3 ROI for the 5 endQ2-viable stats, the betting window opens 6
minutes EARLIER than endQ3 — even more line movement available before settle.

This script answers that empirically — with one important caveat: we do NOT
have measured mid-Q3 stat lines in `data/player_quarter_stats.parquet`, only
per-quarter totals. So mid-Q3 is PROXIED by interpolation: assume each
player accumulated a known FRACTION of their Q3 stat by the mid-Q3 point.
The default fraction is 0.5 (linear pro-ration); we also sweep 0.25 (early
Q3, 9:00 left) and 0.75 (late Q3, 3:00 left) for sensitivity.

The proxy is OPTIMISTIC about scoring evenness within Q3 — real Q3 minutes
are bursty (lineup changes, fouls, runs). Reported numbers are UPPER-BOUND
estimates of mid-Q3 ROI; the true number is likely 5-15% lower per stat.
Documented in the verdict section of the output report.

Strictly read-only — no edits to predict_in_game / live_engine / cycle 97d
files. ROI per snapshot is computed via the SAME simulate_bets helper
(cycle 95d) used by cycles 97d and 98d, so the column is directly
comparable.

Run:
    python scripts/backtest_midQ3_snapshot.py
    python scripts/backtest_midQ3_snapshot.py --max-games 10
    python scripts/backtest_midQ3_snapshot.py --output scripts/_results/midQ3_snapshot_v1.md
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

import retro_inplay_mae as v1            # snapshot + L5 helpers  # noqa: E402
import backtest_inplay_edge as bie       # simulate_bets, math    # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SENSITIVITY_FRACTIONS = (0.25, 0.50, 0.75)
DEFAULT_FRACTION = 0.50

# clock_remaining strings keyed by Q3-elapsed fraction (Q3 length = 12 min):
#   0.25 elapsed -> 9:00 remaining (early Q3)
#   0.50 elapsed -> 6:00 remaining (mid Q3)
#   0.75 elapsed -> 3:00 remaining (late Q3)
_CLOCK_FOR_FRACTION = {0.25: "9:00", 0.50: "6:00", 0.75: "3:00"}


# ── synthetic mid-Q3 snapshot construction ──────────────────────────────────

def build_midq3_synthetic_snapshot(
    game_id: str,
    qstats_df,
    fraction: float = DEFAULT_FRACTION,
) -> Optional[dict]:
    """Reconstruct a SYNTHETIC mid-Q3 snapshot for `game_id`.

    Players accumulate Q1 + Q2 + (Q3 stat * fraction) — a proxy for their
    true mid-Q3 totals (which aren't measured). Period is set to 3, clock to
    the value matching `fraction` (0.25 -> "9:00", 0.5 -> "6:00", 0.75 -> "3:00").

    Returns None when the parquet doesn't have Q1+Q2+Q3 for this game (caller
    should skip — same convention as v1.build_snapshot).
    """
    if not 0.0 <= fraction <= 1.0:
        raise ValueError(f"fraction must be in [0, 1], got {fraction}")
    clock = _CLOCK_FOR_FRACTION.get(fraction)
    if clock is None:
        # Allow arbitrary fractions for sweep-style exploration; derive clock
        # by linear interpolation (12 min Q3).
        remaining_min = max(0.0, 12.0 * (1.0 - fraction))
        mm = int(remaining_min)
        ss = int(round((remaining_min - mm) * 60))
        if ss == 60:
            mm += 1
            ss = 0
        clock = f"{mm}:{ss:02d}"

    game_df = qstats_df[qstats_df["game_id"] == game_id]
    if game_df.empty:
        return None
    have_periods = set(int(p) for p in game_df["period"].unique())
    # Mid-Q3 needs Q1 + Q2 + Q3 data so we can pro-rate Q3.
    if not {1, 2, 3}.issubset(have_periods):
        return None

    # Per-quarter player rows (we need Q1+Q2 in full + Q3 scaled).
    q12 = game_df[game_df["period"].isin([1, 2])]
    q3 = game_df[game_df["period"] == 3]

    # Sum Q1+Q2 cumulative.
    q12_sum = q12.groupby("player_id").agg({
        "min":  "sum", "pts": "sum", "reb": "sum", "ast": "sum",
        "fg3m": "sum", "stl": "sum", "blk": "sum", "tov": "sum",
        "pf":   "sum",
    })
    # Q3 stats — keyed by player_id (one row each since groupby on period 3).
    q3_idx = q3.set_index("player_id")

    # Union of player_ids across Q1+Q2 and Q3 — covers anyone who saw any
    # of the first three quarters.
    all_pids = set(q12_sum.index) | set(q3_idx.index)

    pid_to_team, home, away = v1.load_team_map(game_id)
    # Per-period MIN map for bench-detection (min_q1..min_qN).
    per_q_min: Dict[int, Dict[int, float]] = defaultdict(dict)
    for _, row in game_df.iterrows():
        per_q_min[int(row["player_id"])][int(row["period"])] = float(row["min"])

    players: List[dict] = []
    home_pts = away_pts = 0.0
    stat_cols = ("min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "pf")

    for pid in all_pids:
        pid = int(pid)
        team = pid_to_team.get(pid, "")
        # Q1+Q2 portion (0 if player didn't play).
        if pid in q12_sum.index:
            q12_row = q12_sum.loc[pid]
            q12_vals = {c: float(q12_row[c]) for c in stat_cols}
        else:
            q12_vals = {c: 0.0 for c in stat_cols}
        # Q3 portion scaled by `fraction`. Empty Q3 → zero contribution.
        if pid in q3_idx.index:
            q3_row = q3_idx.loc[pid]
            q3_vals = {c: float(q3_row[c]) * fraction for c in stat_cols}
        else:
            q3_vals = {c: 0.0 for c in stat_cols}
        # Synthetic cumulative through mid-Q3 = Q1+Q2 + fraction*Q3.
        combined = {c: q12_vals[c] + q3_vals[c] for c in stat_cols}

        rec = {
            "player_id": pid,
            "name": f"pid_{pid}",
            "team": team,
            "min":  combined["min"],
            "pts":  combined["pts"],
            "reb":  combined["reb"],
            "ast":  combined["ast"],
            "fg3m": combined["fg3m"],
            "stl":  combined["stl"],
            "blk":  combined["blk"],
            "tov":  combined["tov"],
            "pf":   combined["pf"],
        }
        # min_q1..min_q4 for bench-detection. Q1 + Q2 unchanged; Q3 partial.
        for q in (1, 2):
            rec[f"min_q{q}"] = float(per_q_min[pid].get(q, 0.0))
        rec["min_q3"] = float(per_q_min[pid].get(3, 0.0)) * fraction
        rec["min_q4"] = 0.0
        players.append(rec)
        if team == home:
            home_pts += rec["pts"]
        elif team == away:
            away_pts += rec["pts"]

    return {
        "game_id": game_id,
        "period": 3,
        "clock": clock,
        "home_team": home,
        "away_team": away,
        "home_score": home_pts,
        "away_score": away_pts,
        "players": players,
    }


def project_midq3_via_live_engine(snap: dict) -> Dict[Tuple[int, str], float]:
    """Project the synthetic mid-Q3 snapshot via live_engine.project_from_snapshot.

    Returns {(pid, stat): projected_final}. Mirrors v1.project_snapshot_to_finals
    but uses the production live_engine entrypoint (so any future shim or
    instrumentation in live_engine is exercised by this backtest).
    """
    from src.prediction.live_engine import project_from_snapshot  # noqa: PLC0415

    out: Dict[Tuple[int, str], float] = {}
    rows = project_from_snapshot(snap)
    for r in rows:
        pid = r.get("player_id")
        if pid is None:
            continue
        try:
            pid_i = int(pid)
        except (TypeError, ValueError):
            continue
        out[(pid_i, r["stat"])] = float(r["projected_final"])
    return out


# ── per-fraction ROI table ────────────────────────────────────────────────────

def compute_roi_table(
    fractions: Tuple[float, ...],
    games: List[str],
    qstats_df,
    lines: Dict[Tuple[str, int, str], float],
    actuals_t: Dict[Tuple[str, int, str], float],
    threshold: float = 1.0,
) -> Dict[float, Dict[str, dict]]:
    """For each fraction, build synthetic mid-Q3 snapshots and run simulate_bets.

    Returns {fraction: {stat: simulate_bets cell}}.
    """
    out: Dict[float, Dict[str, dict]] = {}
    for frac in fractions:
        midq3_proj: Dict[Tuple[str, int, str], float] = {}
        n_snap = 0
        for gid in games:
            snap = build_midq3_synthetic_snapshot(gid, qstats_df, fraction=frac)
            if snap is None:
                continue
            n_snap += 1
            for (pid, stat), proj in project_midq3_via_live_engine(snap).items():
                midq3_proj[(gid, pid, stat)] = float(proj)
        print(f"  fraction={frac}: mid-Q3 snapshots built for {n_snap} games "
              f"({len(midq3_proj)} projections)")
        out[frac] = bie.simulate_bets(midq3_proj, lines, actuals_t, threshold)
    return out


# ── report ────────────────────────────────────────────────────────────────────

def build_report(
    midq3_roi_by_frac: Dict[float, Dict[str, dict]],
    endq2_roi: Dict[str, dict],
    endq3_roi: Dict[str, dict],
    n_games: int,
    n_snapshots_default: int,
) -> str:
    lines: List[str] = []
    lines.append("# Mid-Q3 PROXY snapshot ROI — cycle 99d (loop 5)")
    lines.append("")
    lines.append(f"**Games analyzed:** {n_games}")
    lines.append(f"**Synthetic mid-Q3 snapshots built (fraction=0.5):** "
                 f"{n_snapshots_default}")
    lines.append("")
    lines.append("**RESEARCH MEASUREMENT — NOT a betting recommendation.**")
    lines.append("")
    lines.append(
        "**PROXY warning:** `data/player_quarter_stats.parquet` only contains "
        "per-quarter TOTALS; we do NOT measure true mid-Q3 stat lines. This "
        "backtest synthesises mid-Q3 totals as Q1 + Q2 + (Q3 stat * fraction) "
        "— a linear interpolation that ASSUMES uniform within-quarter scoring. "
        "Real NBA Q3 minutes are bursty (lineup changes, foul-trouble swaps, "
        "scoring runs), so the reported mid-Q3 ROI is an UPPER-BOUND estimate. "
        "True mid-Q3 ROI is likely 5-15% lower per stat. This cycle is "
        "research-only; production mid-Q3 mode requires real mid-quarter "
        "snapshots from the cycle 88a live_game_poll loop or a v2 quarter-stats "
        "parquet."
    )
    lines.append("")
    lines.append(
        "Comparison columns: mid-Q3 ROI (fraction=0.5, period=3 clock=6:00), "
        "end-Q2 ROI (from cycle 97d's `inplay_edge_backtest_v2.md`), and "
        "end-Q3 ROI (cycle 95d's primary number, also re-validated by 97d). "
        "All three use the same L5-rolling-mean line proxy and -110 odds."
    )
    lines.append("")

    # ── main table: mid-Q3 vs endQ2 vs endQ3 ────────────────────────────────
    lines.append("## Per-stat ROI at threshold 1.0 (flat $1, fraction=0.5)")
    lines.append("")
    lines.append("| stat | n_mid | midQ3 ROI | endQ2 ROI | endQ3 ROI | "
                 "midQ3 / endQ3 | midQ3 / endQ2 |")
    lines.append("|------|------:|----------:|----------:|----------:|"
                 "--------------:|--------------:|")

    midq3_cells = midq3_roi_by_frac[DEFAULT_FRACTION]

    def _r(x):
        return f"{x:+.4f}" if x is not None else "—"

    def _ratio(a, b):
        if a is None or b is None or b == 0:
            return "—"
        return f"{a / b:.2f}"

    for stat in STATS:
        mid_cell = midq3_cells.get(stat, {})
        q2_cell = endq2_roi.get(stat, {})
        q3_cell = endq3_roi.get(stat, {})
        mid_roi = mid_cell.get("roi_flat")
        q2_roi = q2_cell.get("roi_flat")
        q3_roi = q3_cell.get("roi_flat")
        lines.append(
            f"| {stat} | {mid_cell.get('n_bets', 0)} | "
            f"{_r(mid_roi)} | {_r(q2_roi)} | {_r(q3_roi)} | "
            f"{_ratio(mid_roi, q3_roi)} | {_ratio(mid_roi, q2_roi)} |"
        )
    lines.append("")

    # ── sensitivity sweep ───────────────────────────────────────────────────
    lines.append("## Sensitivity sweep — fraction in {0.25, 0.50, 0.75}")
    lines.append("")
    lines.append(
        "fraction = 0.25 → early-Q3 snapshot (9:00 remaining); "
        "0.50 → mid-Q3 (6:00); "
        "0.75 → late-Q3 (3:00). "
        "All three feed `live_engine.project_from_snapshot` exactly the same "
        "way; only the per-player Q3 contribution differs."
    )
    lines.append("")
    lines.append("| stat | n_0.25 | ROI_0.25 | n_0.50 | ROI_0.50 | n_0.75 | "
                 "ROI_0.75 | endQ3 ROI |")
    lines.append("|------|-------:|---------:|-------:|---------:|-------:|"
                 "---------:|----------:|")
    for stat in STATS:
        row = [f"| {stat} |"]
        for frac in SENSITIVITY_FRACTIONS:
            cell = midq3_roi_by_frac[frac].get(stat, {})
            row.append(f" {cell.get('n_bets', 0)} |")
            row.append(f" {_r(cell.get('roi_flat'))} |")
        q3_roi = endq3_roi.get(stat, {}).get("roi_flat")
        row.append(f" {_r(q3_roi)} |")
        lines.append("".join(row))
    lines.append("")

    # ── verdict ─────────────────────────────────────────────────────────────
    lines.append("## Verdict")
    lines.append("")
    # Count stats where mid-Q3 ROI (fraction=0.5) >= 90% of endQ3 ROI.
    viable90 = 0
    counted = 0
    for stat in STATS:
        mid_roi = midq3_cells.get(stat, {}).get("roi_flat")
        q3_roi = endq3_roi.get(stat, {}).get("roi_flat")
        if mid_roi is None or q3_roi is None or q3_roi <= 0:
            continue
        counted += 1
        if mid_roi / q3_roi >= 0.90:
            viable90 += 1
    if counted == 0:
        lines.append(
            "**Inconclusive — no overlapping populated stats between mid-Q3 "
            "and endQ3 systems.**"
        )
    elif viable90 >= 5:
        lines.append(
            f"**Mid-Q3 PROXY viable for {viable90}/{counted} stats at the 90% "
            f"endQ3 bar (fraction=0.5).** Subject to the proxy caveat above "
            f"(true mid-Q3 ROI likely 5-15% lower), the cycle 98d recommender "
            f"COULD be extended with a mid-Q3 mode after a real mid-Q3 "
            f"snapshot fixture is collected. Recommended: instrument "
            f"live_game_poll to write a mid-period checkpoint and re-run."
        )
    elif viable90 >= 3:
        lines.append(
            f"**Mid-Q3 PROXY partially viable — {viable90}/{counted} stats "
            f"clear the 90%-of-endQ3 bar (fraction=0.5).** Marginal — even "
            f"with the optimistic uniformity proxy, only a subset of stats "
            f"survives the early-snapshot ROI haircut. Sensitivity sweep "
            f"shows how robust this is to the 0.5 assumption."
        )
    else:
        lines.append(
            f"**Mid-Q3 PROXY NOT viable — only {viable90}/{counted} stats "
            f"clear the 90%-of-endQ3 ROI bar (fraction=0.5).** Even with "
            f"the optimistic linear-interpolation proxy the mid-Q3 ROI "
            f"falls short of the 90% bar for most stats. endQ3 stays the "
            f"recommended snapshot for live betting; endQ2 is the earliest "
            f"viable point per cycle 97d's analysis."
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
    print(f"  backtest_midQ3_snapshot: {len(games)} games")

    # 1) game_id -> ISO date (needed for L5 line proxy).
    game_dates: Dict[str, str] = {}
    for gid in games:
        d = v1.find_game_date(gid, qstats_df)
        if d:
            game_dates[gid] = d
    print(f"  dated games: {len(game_dates)} / {len(games)}")

    # 2) Actuals (full-game totals).
    actuals_t: Dict[Tuple[str, int, str], float] = {}
    for gid in games:
        for (pid, stat), act in v1.actuals_for_game(gid, qstats_df).items():
            actuals_t[(gid, pid, stat)] = float(act)
    print(f"  actuals: {len(actuals_t)}")

    # 3) L5 line proxy (sportsbook-line analog — same as cycles 95d, 97d).
    line_proxies = v1.pregame_predictions_via_gamelog(game_dates, qstats_df)
    print(f"  L5 line proxies: {len(line_proxies)}")

    # 4) endQ2 + endQ3 projections via v1 helpers (real measured snapshots).
    endq2_proj: Dict[Tuple[str, int, str], float] = {}
    endq3_proj: Dict[Tuple[str, int, str], float] = {}
    for gid in games:
        for point, sink in (("endQ2", endq2_proj), ("endQ3", endq3_proj)):
            snap = v1.build_snapshot(gid, point, qstats_df)
            if snap is None:
                continue
            for (pid, stat), proj in v1.project_snapshot_to_finals(snap).items():
                sink[(gid, pid, stat)] = float(proj)
    print(f"  endQ2 projections: {len(endq2_proj)}")
    print(f"  endQ3 projections: {len(endq3_proj)}")

    endq2_roi = bie.simulate_bets(endq2_proj, line_proxies, actuals_t, 1.0)
    endq3_roi = bie.simulate_bets(endq3_proj, line_proxies, actuals_t, 1.0)

    # 5) Mid-Q3 sensitivity sweep at fractions {0.25, 0.5, 0.75}.
    midq3_roi_by_frac = compute_roi_table(
        SENSITIVITY_FRACTIONS, games, qstats_df, line_proxies, actuals_t, 1.0)
    n_snap_default = sum(
        1 for gid in games
        if build_midq3_synthetic_snapshot(gid, qstats_df, DEFAULT_FRACTION)
        is not None
    )

    # 6) Report.
    report = build_report(
        midq3_roi_by_frac, endq2_roi, endq3_roi, len(games), n_snap_default)
    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "midQ3_snapshot_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"  wrote {out_path}")

    # Console summary.
    print("\n  Per-stat ROI @ threshold 1.0 (fraction=0.5):")
    print("  stat   midQ3       endQ2       endQ3       mid/endQ3")
    midq3_cells = midq3_roi_by_frac[DEFAULT_FRACTION]
    for stat in STATS:
        mid = midq3_cells.get(stat, {}).get("roi_flat")
        q2 = endq2_roi.get(stat, {}).get("roi_flat")
        q3 = endq3_roi.get(stat, {}).get("roi_flat")

        def _r(x):
            return f"{x:+.4f}" if x is not None else "    —   "
        ratio = "—"
        if mid is not None and q3 is not None and q3 > 0:
            ratio = f"{mid / q3:.2f}"
        print(f"  {stat:4s}   {_r(mid)}   {_r(q2)}   {_r(q3)}   {ratio}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None,
                    help="Limit to first N games (debug).")
    ap.add_argument("--output", default=None,
                    help="Markdown output path (default: "
                         "scripts/_results/midQ3_snapshot_v1.md)")
    args = ap.parse_args()
    return run(max_games=args.max_games, output=args.output)


if __name__ == "__main__":
    sys.exit(main())
