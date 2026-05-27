"""daily_roi.py — Daily ROI report for shadow-log settlements.

Reads data/shadow/settled_<date>.csv and produces a markdown report covering:
hit-rate, ROI, calibration, and breakdowns by tier / stat / book / quarter.

This is COMPLEMENTARY to scripts/clv_report.py (CLV / placed-bet ledger).
That lens: did we beat the closing line?  This lens: did the engine make money
against realized outcomes?

Public API
----------
load_settled_day(date_str, base_dir=None) -> pd.DataFrame
build_daily_report(date_str, base_dir=None)  -> str   (markdown)
write_daily_report(date_str, out_path=None, base_dir=None) -> str  (written path)

CLI
---
python -m src.reporting.daily_roi --date YYYY-MM-DD [--output PATH] [--base-dir DIR]
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

try:
    import pandas as pd
except ImportError as exc:
    raise ImportError("pandas is required: pip install pandas") from exc

# Reuse payout math — do not reimplement.
from src.betting.pnl_ledger import american_to_payout  # noqa: E402

SHADOW_DIR   = os.path.join(PROJECT_DIR, "data", "shadow")
REPORTS_DIR  = os.path.join(PROJECT_DIR, "vault", "Reports")

_TIER_ORDER  = ["S", "A", "B", "C"]
_STAT_ORDER  = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
_QUARTER_MAP = {"2": "endQ1", "3": "endQ2", "4": "endQ3"}


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_settled_day(date_str: str, base_dir: Optional[str] = None) -> "pd.DataFrame":
    """Load data/shadow/settled_<date>.csv.  Returns empty DataFrame if absent."""
    shadow_dir = base_dir or SHADOW_DIR
    path = os.path.join(shadow_dir, f"settled_{date_str}.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path, dtype=str, low_memory=False)
    # Coerce numeric columns
    for col in ("raw_ev", "realized_return_$1", "line", "odds", "model_proj",
                "current_stat", "sigma", "kelly", "actual_stat"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["period"] = df["period"].astype(str).str.strip()
    for col in ("tier", "stat", "book", "gate_status", "outcome", "side"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    return df


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _roi_fmt(roi: float) -> str:
    sign = "+" if roi >= 0 else ""
    return f"{sign}{roi * 100:.2f}%"


def _hit_rate_fmt(rate: float) -> str:
    return f"{rate * 100:.1f}%"


def _group_stats(sub: "pd.DataFrame") -> tuple:
    """Return (n, n_hit, n_miss, n_push, hit_rate, roi) for a subset."""
    n     = len(sub)
    hits  = (sub["outcome"] == "hit").sum()
    miss  = (sub["outcome"] == "miss").sum()
    push  = (sub["outcome"] == "push").sum()
    n_dec = hits + miss
    hr    = (hits / n_dec) if n_dec > 0 else float("nan")
    roi   = (sub["realized_return_$1"].sum() / n) if n > 0 else float("nan")
    return n, int(hits), int(miss), int(push), hr, roi


def _md_table(headers: list, rows: list) -> str:
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    lines = ["| " + " | ".join(headers) + " |", sep]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _section_summary(df: "pd.DataFrame", date_str: str) -> str:
    passed  = df[df["gate_status"] == "passed"]
    settled = df[df["outcome"].isin(["hit", "miss", "push"])]
    n_games = df["game_id"].nunique() if "game_id" in df.columns else 0
    lines = [
        f"# Daily ROI Report — {date_str}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Date | {date_str} |",
        f"| Games | {n_games} |",
        f"| Total rows logged | {len(df):,} |",
        f"| Rows passed | {len(passed):,} |",
        f"| Rows settled | {len(settled):,} |",
    ]
    if len(passed) > 0:
        n, hits, miss, push, hr, roi = _group_stats(passed[passed["outcome"].isin(["hit","miss","push"])])
        lines += [
            f"| Passed hit-rate | {_hit_rate_fmt(hr) if not math.isnan(hr) else 'N/A'} |",
            f"| Passed ROI (flat $1) | {_roi_fmt(roi) if not math.isnan(roi) else 'N/A'} |",
        ]
    return "\n".join(lines)


def _section_top20(df: "pd.DataFrame") -> str:
    passed = df[df["gate_status"] == "passed"].copy()
    if passed.empty or "raw_ev" not in passed.columns:
        return "## Top 20 Picks by EV\n\n_No passed bets._"

    cols_present = [c for c in ["name","stat","side","line","book","odds",
                                 "raw_ev","tier","outcome","realized_return_$1"]
                    if c in passed.columns]
    top = passed.sort_values("raw_ev", ascending=False).head(20)[cols_present]

    headers = [c.replace("realized_return_$1","return_$1") for c in cols_present]
    rows = []
    for _, r in top.iterrows():
        row = []
        for c in cols_present:
            v = r[c]
            if c == "raw_ev" and not (isinstance(v, str)):
                row.append(f"{v:+.4f}" if not math.isnan(float(v)) else "")
            elif c == "realized_return_$1" and not (isinstance(v, str)):
                row.append(f"{float(v):+.4f}" if not math.isnan(float(v)) else "")
            else:
                row.append(str(v) if v is not None else "")
        rows.append(row)

    return "## Top 20 Picks by EV\n\n" + _md_table(headers, rows)


def _section_tier_roi(df: "pd.DataFrame") -> str:
    passed = df[df["gate_status"] == "passed"]
    if passed.empty:
        return "## ROI by Tier\n\n_No passed bets._"

    header_rows = ["## ROI by Tier", "", "_(S/A/B/C — flat $1 stakes, passed bets only)_", ""]
    tbl_headers = ["Tier", "n", "Hit", "Miss", "Push", "Hit Rate", "ROI"]
    tbl_rows = []
    for tier in _TIER_ORDER:
        sub = passed[passed["tier"] == tier]
        if sub.empty:
            continue
        dec = sub[sub["outcome"].isin(["hit","miss","push"])]
        n, hits, miss, push, hr, roi = _group_stats(dec)
        tbl_rows.append([
            tier, n, hits, miss, push,
            _hit_rate_fmt(hr) if not math.isnan(hr) else "N/A",
            _roi_fmt(roi) if not math.isnan(roi) else "N/A",
        ])
    tbl_rows.sort(key=lambda r: float(r[6].replace("%","").replace("+","")) if r[6] != "N/A" else -999, reverse=True)
    return "\n".join(header_rows) + _md_table(tbl_headers, tbl_rows)


def _section_calibration(df: "pd.DataFrame") -> str:
    all_rows = df[df["outcome"].isin(["hit","miss","push"])].copy()
    if all_rows.empty or "raw_ev" not in all_rows.columns:
        return "## Calibration (EV Deciles vs Realized Return)\n\n_Insufficient data._"

    valid = all_rows.dropna(subset=["raw_ev","realized_return_$1"])
    if len(valid) < 10:
        return "## Calibration (EV Deciles vs Realized Return)\n\n_Insufficient data._"

    valid = valid.copy()
    valid["ev_decile"] = pd.qcut(valid["raw_ev"], q=10, labels=False, duplicates="drop") + 1
    grp = valid.groupby("ev_decile").agg(
        n=("realized_return_$1","count"),
        avg_ev=("raw_ev","mean"),
        avg_ret=("realized_return_$1","mean"),
    ).reset_index()

    tbl_headers = ["EV Decile", "n", "avg_predicted_ev", "avg_realized_return"]
    tbl_rows = []
    for _, r in grp.iterrows():
        tbl_rows.append([
            int(r["ev_decile"]), int(r["n"]),
            f"{r['avg_ev']:+.4f}", f"{r['avg_ret']:+.4f}",
        ])
    return "## Calibration (EV Deciles vs Realized Return)\n\n" + _md_table(tbl_headers, tbl_rows)


def _section_quarter(df: "pd.DataFrame") -> str:
    passed = df[df["gate_status"] == "passed"]
    if passed.empty:
        return "## Per-Quarter Breakdown\n\n_No passed bets._"

    tbl_headers = ["Quarter", "n_passed", "Hit", "Miss", "Push", "Hit Rate", "ROI"]
    tbl_rows = []
    for period_val, label in sorted(_QUARTER_MAP.items()):
        sub = passed[passed["period"] == period_val]
        if sub.empty:
            continue
        dec = sub[sub["outcome"].isin(["hit","miss","push"])]
        n, hits, miss, push, hr, roi = _group_stats(dec)
        tbl_rows.append([
            label, n, hits, miss, push,
            _hit_rate_fmt(hr) if not math.isnan(hr) else "N/A",
            _roi_fmt(roi) if not math.isnan(roi) else "N/A",
        ])
    return "## Per-Quarter Breakdown\n\n" + _md_table(tbl_headers, tbl_rows)


def _section_stat(df: "pd.DataFrame") -> str:
    passed = df[df["gate_status"] == "passed"]
    if passed.empty:
        return "## Per-Stat Breakdown\n\n_No passed bets._"

    tbl_headers = ["Stat", "n", "Hit", "Miss", "Push", "Hit Rate", "ROI"]
    tbl_rows = []
    stats_present = [s for s in _STAT_ORDER if s in passed["stat"].unique()]
    for stat in stats_present:
        sub = passed[passed["stat"] == stat]
        dec = sub[sub["outcome"].isin(["hit","miss","push"])]
        n, hits, miss, push, hr, roi = _group_stats(dec)
        tbl_rows.append([
            stat, n, hits, miss, push,
            _hit_rate_fmt(hr) if not math.isnan(hr) else "N/A",
            _roi_fmt(roi) if not math.isnan(roi) else "N/A",
        ])
    tbl_rows.sort(key=lambda r: float(r[6].replace("%","").replace("+","")) if r[6] != "N/A" else -999, reverse=True)
    return "## Per-Stat Breakdown\n\n" + _md_table(tbl_headers, tbl_rows)


def _section_book(df: "pd.DataFrame") -> str:
    passed = df[df["gate_status"] == "passed"]
    if passed.empty or "book" not in passed.columns:
        return "## Per-Book Breakdown\n\n_No passed bets._"

    books = sorted(passed["book"].dropna().unique())
    tbl_headers = ["Book", "n", "Hit", "Miss", "Push", "Hit Rate", "ROI"]
    tbl_rows = []
    for book in books:
        sub = passed[passed["book"] == book]
        dec = sub[sub["outcome"].isin(["hit","miss","push"])]
        n, hits, miss, push, hr, roi = _group_stats(dec)
        tbl_rows.append([
            book, n, hits, miss, push,
            _hit_rate_fmt(hr) if not math.isnan(hr) else "N/A",
            _roi_fmt(roi) if not math.isnan(roi) else "N/A",
        ])
    tbl_rows.sort(key=lambda r: float(r[6].replace("%","").replace("+","")) if r[6] != "N/A" else -999, reverse=True)
    return "## Per-Book Breakdown\n\n" + _md_table(tbl_headers, tbl_rows)


def _section_footer(date_str: str) -> str:
    cal_path = os.path.join(REPORTS_DIR, f"filter_calibration_{date_str}.md")
    if os.path.exists(cal_path):
        return f"\n---\n\n_See also: [filter_calibration_{date_str}.md](filter_calibration_{date_str}.md)_"
    return "\n---\n\n_Generated by `src.reporting.daily_roi`. No filter_calibration file for this date._"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_daily_report(date_str: str, base_dir: Optional[str] = None) -> str:
    """Build and return the markdown report string for date_str."""
    df = load_settled_day(date_str, base_dir)
    if df.empty:
        return (
            f"# Daily ROI Report — {date_str}\n\n"
            f"_No settled data found for {date_str}. "
            f"Run `src.prediction.settlement.settle_day('{date_str}')` first._"
        )

    sections = [
        _section_summary(df, date_str),
        "",
        _section_top20(df),
        "",
        _section_tier_roi(df),
        "",
        _section_calibration(df),
        "",
        _section_quarter(df),
        "",
        _section_stat(df),
        "",
        _section_book(df),
        _section_footer(date_str),
    ]
    return "\n".join(sections)


def write_daily_report(
    date_str: str,
    out_path: Optional[str] = None,
    base_dir: Optional[str] = None,
) -> str:
    """Write report to vault/Reports/daily_roi_<date>.md (or out_path).

    Returns the path that was written.
    """
    if out_path is None:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        out_path = os.path.join(REPORTS_DIR, f"daily_roi_{date_str}.md")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    report = build_daily_report(date_str, base_dir)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _console_summary(date_str: str, df: "pd.DataFrame", out_path: str) -> None:
    """Print a short console summary after writing the report."""
    if df.empty:
        print(f"[daily_roi] {date_str} — no settled data")
        return
    passed  = df[df["gate_status"] == "passed"]
    dec     = passed[passed["outcome"].isin(["hit","miss","push"])]
    n_rows  = len(df)
    n_pass  = len(passed)
    roi_val = dec["realized_return_$1"].sum() / len(dec) if len(dec) > 0 else float("nan")
    roi_str = _roi_fmt(roi_val) if not math.isnan(roi_val) else "N/A"

    top_ev  = passed.sort_values("raw_ev", ascending=False).head(20) if not passed.empty else passed
    n_top   = len(top_ev)

    print(f"[daily_roi] Report written -> {out_path}")
    print(f"  Date         : {date_str}")
    print(f"  Rows logged  : {n_rows:,}")
    print(f"  Rows passed  : {n_pass:,}")
    print(f"  Top picks    : {n_top}")
    print(f"  Agg ROI      : {roi_str} (passed, flat $1)")


def main(argv=None) -> int:
    from src.live.time_utils import slate_date

    ap = argparse.ArgumentParser(description="Daily ROI report from shadow-log settlements.")
    ap.add_argument("--date", default=str(slate_date()),
                    help="Settlement date YYYY-MM-DD (default: today's slate date)")
    ap.add_argument("--output", default=None, help="Override output .md path")
    ap.add_argument("--base-dir", default=None,
                    help="Override data/shadow directory")
    args = ap.parse_args(argv)

    df = load_settled_day(args.date, args.base_dir)
    out_path = write_daily_report(args.date, args.output, args.base_dir)
    _console_summary(args.date, df, out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
