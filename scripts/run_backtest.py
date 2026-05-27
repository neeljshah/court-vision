"""run_backtest.py — Gate-calibration backtest harness (Agent 4, overnight build).

Drives the full replay → settle → report pipeline for N historical games.
Each game is replayed through snapshot_replay to fill shadow CSVs, then
settlement.settle_day enriches them with realized outcomes, and finally
this script computes gate-calibration metrics + writes the vault report.

Complementary to scripts/_results/inplay_edge_backtest_v2.md (which measures
ROI vs L5 proxy); THIS report measures which decision_engine gates over-block
actionable edges.

Usage:
    python scripts/run_backtest.py [--n-games 50] [--date-stamp YYYY-MM-DD]
                                   [--output vault/Reports/backtest_<date>.md]
                                   [--skip-replay] [--skip-settle]
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional, Tuple

os.environ["SHADOW_LOG_ENABLED"] = "1"

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import pandas as pd  # noqa: E402

from src.prediction import snapshot_replay  # noqa: E402
from src.prediction import settlement       # noqa: E402
from src.live.time_utils import slate_date  # noqa: E402


STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
TIERS = ("S", "A", "B", "C")
SNAP_POINTS = ("endQ1", "endQ2", "endQ3")


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v) if v not in (None, "", "nan") else default
    except (ValueError, TypeError):
        return default


def _roi(rows: List[dict]) -> Tuple[float, float, int]:
    """Return (hit_rate, roi_$1, n_settled) for a list of settled rows.

    Excludes no_actual rows from hit-rate calculation but counts them in n.
    ROI is computed on all rows (no_actual contributes 0 return).
    """
    scoreable = [r for r in rows if r.get("outcome") != "no_actual"]
    hits = sum(1 for r in scoreable if r.get("outcome") == "hit")
    hit_rate = (hits / len(scoreable)) if scoreable else float("nan")
    total_return = sum(_safe_float(r.get("realized_return_$1")) for r in rows)
    n = len(rows)
    roi = total_return / n if n > 0 else float("nan")
    return hit_rate, roi, n


def _fmt_pct(v: float, decimals: int = 1) -> str:
    if math.isnan(v):
        return "—"
    return f"{v * 100:.{decimals}f}%"


def _fmt_roi(v: float) -> str:
    if math.isnan(v):
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v * 100:.2f}%"


# ── report builder ────────────────────────────────────────────────────────────

def build_report(
    df: pd.DataFrame,
    n_games_attempted: int,
    n_games_finalized: int,
    date_stamp: str,
) -> str:
    lines: List[str] = []

    lines.append(f"# Backtest Gate-Calibration Report — {date_stamp}")
    lines.append("")
    lines.append("**Purpose:** Evaluate which decision_engine gates are over-blocking "
                 "actionable edges by comparing passed-bet ROI against the "
                 "hypothetical ROI of blocked bets.")
    lines.append("")
    lines.append("**Complementary to** `scripts/_results/inplay_edge_backtest_v2.md` "
                 "(that report measures ROI vs L5 proxy; this one measures gate-calibration "
                 "evidence).")
    lines.append("")

    # ── Header stats ──────────────────────────────────────────────────────────
    total_rows = len(df)
    rows_settled = len(df[df["outcome"] != ""])
    rows_passed = len(df[df["gate_status"] == "passed"])
    rows_blocked = len(df[df["gate_status"] == "blocked"])

    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Games attempted | {n_games_attempted} |")
    lines.append(f"| Games finalized (box score available) | {n_games_finalized} |")
    lines.append(f"| Total rows logged | {total_rows} |")
    lines.append(f"| Rows settled (outcome != '') | {rows_settled} |")
    lines.append(f"| Rows passed (gate_status=passed) | {rows_passed} |")
    lines.append(f"| Rows blocked (gate_status=blocked) | {rows_blocked} |")
    lines.append("")

    # ── By tier × quarter ────────────────────────────────────────────────────
    lines.append("## Hit-rate and ROI by Tier × Quarter (passed bets only)")
    lines.append("")
    lines.append("| Tier | Snapshot | n_passed | hit_rate | ROI ($1 flat) |")
    lines.append("|------|----------|----------|----------|---------------|")

    passed_df = df[df["gate_status"] == "passed"].copy()
    for tier in TIERS:
        for snap in SNAP_POINTS:
            # Map period to snapshot point
            period_map = {"endQ1": "2", "endQ2": "3", "endQ3": "4"}
            sub = passed_df[
                (passed_df["tier"] == tier) &
                (passed_df["period"].astype(str) == period_map[snap])
            ]
            if len(sub) == 0:
                continue
            hr, roi, n = _roi(sub.to_dict("records"))
            lines.append(f"| {tier} | {snap} | {n} | {_fmt_pct(hr)} | {_fmt_roi(roi)} |")
    lines.append("")

    # ── By gate_blocked_by ───────────────────────────────────────────────────
    lines.append("## Gate Analysis — Dropped Bets vs Hypothetical ROI")
    lines.append("")
    lines.append("For each gate, shows how many bets it dropped AND what the "
                 "hypothetical hit-rate + ROI would have been if those bets "
                 "had been placed anyway. High hypothetical ROI = over-blocking evidence.")
    lines.append("")
    lines.append("| gate_blocked_by | n_dropped | hypo_hit_rate | hypo_ROI |")
    lines.append("|-----------------|-----------|---------------|----------|")

    blocked_df = df[df["gate_status"] == "blocked"].copy()
    gate_counts = blocked_df["gate_blocked_by"].value_counts()
    for gate_name, count in gate_counts.items():
        if not gate_name:
            gate_name = "(empty)"
        sub = blocked_df[blocked_df["gate_blocked_by"] == gate_name]
        hr, roi, _ = _roi(sub.to_dict("records"))
        lines.append(f"| {gate_name} | {count} | {_fmt_pct(hr)} | {_fmt_roi(roi)} |")
    lines.append("")

    # ── Calibration plot table (EV deciles) ──────────────────────────────────
    lines.append("## Calibration Table — Predicted EV Deciles vs Realized Return")
    lines.append("")
    lines.append("If the model is well-calibrated, higher predicted-EV deciles "
                 "should show higher realized returns.")
    lines.append("")

    ev_df = df[df["raw_ev"].apply(lambda x: str(x) not in ("", "nan"))].copy()
    ev_df["raw_ev_f"] = ev_df["raw_ev"].apply(_safe_float)
    ev_df["realized_f"] = ev_df["realized_return_$1"].apply(_safe_float)

    if len(ev_df) >= 10:
        try:
            ev_df["ev_decile"] = pd.qcut(ev_df["raw_ev_f"], 10, labels=False,
                                          duplicates="drop")
            lines.append("| EV Decile | n_rows | avg_predicted_ev | avg_realized_return |")
            lines.append("|-----------|--------|------------------|---------------------|")
            for dec in sorted(ev_df["ev_decile"].dropna().unique()):
                sub = ev_df[ev_df["ev_decile"] == dec]
                avg_ev = sub["raw_ev_f"].mean()
                avg_ret = sub["realized_f"].mean()
                lines.append(
                    f"| {int(dec)+1} | {len(sub)} | {avg_ev:+.4f} | {avg_ret:+.4f} |"
                )
        except Exception as e:
            lines.append(f"_Calibration table unavailable: {e}_")
    else:
        lines.append("_Insufficient data for decile analysis (n < 10)._")
    lines.append("")

    # ── Top 20 mismatches ────────────────────────────────────────────────────
    lines.append("## Top 20 Projection Mismatches (|proj − actual|)")
    lines.append("")
    lines.append("Surfaces systematic projector failures — large deviations indicate "
                 "stats or game contexts where the model over/under-projects.")
    lines.append("")

    mismatch_df = df[
        (df["model_proj"].apply(lambda x: str(x) not in ("", "nan"))) &
        (df["actual_stat"].apply(lambda x: str(x) not in ("", "nan")))
    ].copy()

    if len(mismatch_df) > 0:
        mismatch_df["proj_f"] = mismatch_df["model_proj"].apply(_safe_float)
        mismatch_df["actual_f"] = mismatch_df["actual_stat"].apply(_safe_float)
        mismatch_df["deviation"] = mismatch_df["proj_f"] - mismatch_df["actual_f"]
        mismatch_df["abs_dev"] = mismatch_df["deviation"].abs()
        top20 = mismatch_df.nlargest(20, "abs_dev")[
            ["name", "stat", "snapshot_point_label" if "snapshot_point_label" in mismatch_df.columns else "period",
             "model_proj", "actual_stat", "deviation"]
        ].copy() if "snapshot_point_label" in mismatch_df.columns else \
            mismatch_df.nlargest(20, "abs_dev")[
                ["name", "stat", "period", "model_proj", "actual_stat", "deviation"]
            ].copy()

        lines.append("| name | stat | period | model_proj | actual | deviation |")
        lines.append("|------|------|--------|-----------|--------|-----------|")
        for _, r in top20.iterrows():
            dev = _safe_float(r.get("deviation"))
            sign = "+" if dev >= 0 else ""
            lines.append(
                f"| {r.get('name','')} | {r.get('stat','')} | "
                f"{r.get('period','')} | "
                f"{_safe_float(r.get('model_proj')):.2f} | "
                f"{_safe_float(r.get('actual_stat')):.2f} | "
                f"{sign}{dev:.2f} |"
            )
    else:
        lines.append("_No settled rows with both model_proj and actual_stat._")
    lines.append("")

    # ── By stat ──────────────────────────────────────────────────────────────
    lines.append("## Hit-rate and ROI by Stat (passed bets)")
    lines.append("")
    lines.append("| stat | n_passed | hit_rate | ROI |")
    lines.append("|------|----------|----------|-----|")
    for stat in STATS:
        sub = passed_df[passed_df["stat"].str.lower() == stat]
        if len(sub) == 0:
            continue
        hr, roi, n = _roi(sub.to_dict("records"))
        lines.append(f"| {stat} | {n} | {_fmt_pct(hr)} | {_fmt_roi(roi)} |")
    lines.append("")

    # ── By book ──────────────────────────────────────────────────────────────
    lines.append("## Hit-rate and ROI by Book (passed bets)")
    lines.append("")
    lines.append("| book | n_passed | hit_rate | ROI |")
    lines.append("|------|----------|----------|-----|")
    for book in passed_df["book"].unique():
        sub = passed_df[passed_df["book"] == book]
        hr, roi, n = _roi(sub.to_dict("records"))
        lines.append(f"| {book} | {n} | {_fmt_pct(hr)} | {_fmt_roi(roi)} |")
    lines.append("")

    # ── Per-quarter overall ───────────────────────────────────────────────────
    lines.append("## Per-quarter Summary (all bets evaluated)")
    lines.append("")
    lines.append("| snapshot | total_evaluated | passed | blocked |")
    lines.append("|----------|-----------------|--------|---------|")
    period_to_snap = {"2": "endQ1", "3": "endQ2", "4": "endQ3"}
    for snap in SNAP_POINTS:
        period_str = {"endQ1": "2", "endQ2": "3", "endQ3": "4"}[snap]
        sub = df[df["period"].astype(str) == period_str]
        n_pass = len(sub[sub["gate_status"] == "passed"])
        n_block = len(sub[sub["gate_status"] == "blocked"])
        lines.append(f"| {snap} | {len(sub)} | {n_pass} | {n_block} |")
    lines.append("")

    return "\n".join(lines) + "\n"


# ── main runner ───────────────────────────────────────────────────────────────

def run(
    n_games: int = 50,
    date_stamp: Optional[str] = None,
    output: Optional[str] = None,
    skip_replay: bool = False,
    skip_settle: bool = False,
) -> int:
    if date_stamp is None:
        date_stamp = slate_date().isoformat()

    shadow_dir = os.path.join(PROJECT_DIR, "data", "shadow")
    os.makedirs(shadow_dir, exist_ok=True)

    settled_path = os.path.join(shadow_dir, f"settled_{date_stamp}.csv")
    report_path = output or os.path.join(
        PROJECT_DIR, "vault", "Reports", f"backtest_{date_stamp}.md"
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    # ── Phase 1: Replay games to fill shadow CSVs ────────────────────────────
    game_ids = snapshot_replay.list_historical_game_ids(limit=n_games)
    n_total = len(game_ids)
    print(f"[run_backtest] {n_total} game_ids found for replay")

    rows_logged_total = 0
    n_failed = 0

    if not skip_replay:
        for i, gid in enumerate(game_ids):
            try:
                n_rows = snapshot_replay.replay_game_to_shadow_log(gid)
                rows_logged_total += n_rows
            except Exception as exc:
                n_failed += 1
                print(f"  [WARN] game {gid} failed: {exc}")

            if (i + 1) % 5 == 0 or (i + 1) == n_total:
                print(f"  [{i+1}/{n_total}] gid={gid} rows_logged={rows_logged_total}")

        fail_rate = n_failed / n_total if n_total > 0 else 0.0
        if fail_rate > 0.5:
            print(f"[ABORT] {n_failed}/{n_total} games failed replay "
                  f"({fail_rate*100:.0f}%) — pipeline integration issue.")
            return 1

        print(f"[run_backtest] Replay complete: {rows_logged_total} rows logged, "
              f"{n_failed} games failed")
    else:
        print("[run_backtest] --skip-replay: using existing shadow CSVs")

    # ── Phase 2: Settle ───────────────────────────────────────────────────────
    if not skip_settle:
        print(f"[run_backtest] Running settle_day({date_stamp!r}) ...")
        n_settled = settlement.settle_day(date_stamp)
        print(f"[run_backtest] settle_day returned {n_settled} rows settled")
    else:
        print("[run_backtest] --skip-settle: skipping settlement")

    # ── Phase 3: Load settled CSV + compute metrics ───────────────────────────
    if not os.path.exists(settled_path):
        print(f"[run_backtest] No settled CSV at {settled_path} — nothing to report")
        return 0

    df = pd.read_csv(settled_path, dtype=str).fillna("")
    n_games_finalized = df["game_id"].nunique() if len(df) > 0 else 0

    print(f"[run_backtest] Loaded settled CSV: {len(df)} rows, "
          f"{n_games_finalized} games finalized")

    if len(df) < 20:
        print(f"[WARN] Only {len(df)} rows in settled CSV — "
              "report will have sparse tables")

    # ── Phase 4: Build + write report ─────────────────────────────────────────
    report_md = build_report(df, n_total, n_games_finalized, date_stamp)
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(report_md)
    print(f"[run_backtest] Report written: {report_path}")

    # ── Phase 5: Console summary ──────────────────────────────────────────────
    passed_rows = df[df["gate_status"] == "passed"].to_dict("records")
    blocked_rows = df[df["gate_status"] == "blocked"].to_dict("records")

    p_hr, p_roi, p_n = _roi(passed_rows)
    b_hr, b_roi, b_n = _roi(blocked_rows)

    biggest_gate = ""
    biggest_gate_n = 0
    blocked_df = df[df["gate_status"] == "blocked"]
    if len(blocked_df) > 0:
        vc = blocked_df["gate_blocked_by"].value_counts()
        if len(vc) > 0:
            biggest_gate = vc.index[0]
            biggest_gate_n = int(vc.iloc[0])

    print(f"\n=== BACKTEST SUMMARY ({date_stamp}) ===")
    print(f"games: {n_games_finalized} / {n_total} finalized")
    print(f"rows_passed: {p_n} (hit-rate {_fmt_pct(p_hr)}, ROI {_fmt_roi(p_roi)})")
    print(f"rows_blocked: {b_n} (would-have-hit-rate {_fmt_pct(b_hr)}, "
          f"would-have-ROI {_fmt_roi(b_roi)})")
    if biggest_gate:
        print(f"biggest filter blocker: {biggest_gate!r} dropped {biggest_gate_n} rows")
    print(f"report written: {report_path}")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Gate-calibration backtest for the in-play NBA betting model."
    )
    ap.add_argument("--n-games", type=int, default=50,
                    help="Number of historical games to replay (default 50).")
    ap.add_argument("--date-stamp", default=None,
                    help="Synthetic date for shadow CSVs (YYYY-MM-DD). "
                         "Defaults to today's ET slate date.")
    ap.add_argument("--output", default=None,
                    help="Markdown report output path. "
                         "Defaults to vault/Reports/backtest_<date>.md")
    ap.add_argument("--skip-replay", action="store_true",
                    help="Skip game replay (use existing shadow CSVs).")
    ap.add_argument("--skip-settle", action="store_true",
                    help="Skip settlement (use existing settled CSV).")
    args = ap.parse_args()
    return run(
        n_games=args.n_games,
        date_stamp=args.date_stamp,
        output=args.output,
        skip_replay=args.skip_replay,
        skip_settle=args.skip_settle,
    )


if __name__ == "__main__":
    sys.exit(main())
