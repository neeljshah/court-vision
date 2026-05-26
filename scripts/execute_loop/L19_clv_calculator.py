"""L19_clv_calculator.py — CLV (Closing Line Value) Calculator + Nightly Report.

Reads the L07 ledger (data/ledger/bets.parquet) and PrizePicks snapshots
(scripts/validation/real_lines_check/snapshots/prizepicks_*.csv) to compute
CLV per bet, produce a nightly JSON report, and flag drift.

Public API
----------
    CLVPoint                dataclass
    compute_clv(bet, line_at_bet, line_at_close) -> CLVPoint
    load_snapshots(start_date, end_date, book_filter) -> pd.DataFrame
    join_bets_to_closes(bets_df, snapshots_df) -> pd.DataFrame
    nightly_clv_report(date) -> dict
    rolling_clv_trend(days) -> dict
    alert_clv_drift(window_days, threshold_pp) -> list

CLI
---
    python L19_clv_calculator.py report [--date YYYY-MM-DD]
    python L19_clv_calculator.py trend  [--days 30]
    python L19_clv_calculator.py alert  [--window 14 --threshold -2.0]

Paper vs Live Mode — MODE GATING: N/A
--------------------------------------
L19 is a **read-only analytics layer** — it makes no API calls and has no
execution-mode toggle.  The constant ``_MARKET_TYPE_LIVE`` (= ``"live"``)
is a **data classification**: bets whose ``market`` column contains this
value were placed after tip-off (in-game prop markets) and are excluded
from CLV calculations because no pre-game closing line exists.  It is NOT
an environment-mode gate such as ``if mode == "live"``.  L19 runs
identically in paper and production environments.  No paper/live mode
switch is required or applicable.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_LEDGER_DIR = PROJECT_DIR / "data" / "ledger"
_BETS_PARQUET = _LEDGER_DIR / "bets.parquet"
_BETS_CSV = _LEDGER_DIR / "bets.csv"
_SNAPSHOT_DIR = (
    PROJECT_DIR
    / "scripts"
    / "validation"
    / "real_lines_check"
    / "snapshots"
)

# ---------------------------------------------------------------------------
# Sigma constants for CLV probability conversion
# ---------------------------------------------------------------------------
SIGMA_MULT: dict[str, float] = {
    "pts": 1.07, "reb": 1.07, "ast": 0.99,
    "fg3m": 1.44, "stl": 1.76, "blk": 1.95, "tov": 1.30,
}
BASE_SIGMA: dict[str, float] = {
    "pts": 6.0, "reb": 2.5, "ast": 1.85,
    "fg3m": 1.3, "stl": 1.0, "blk": 0.75, "tov": 1.2,
}

# ---------------------------------------------------------------------------
# Data-classification constants
# ---------------------------------------------------------------------------
# _MARKET_TYPE_LIVE identifies in-game prop markets (placed after tip-off).
# This is a DATA label on the bet's `market` column — NOT an execution-mode
# flag.  L19 makes no API calls and runs identically in paper and production.
_MARKET_TYPE_LIVE = "live"  # noqa: paper-default — data classification, not mode gate

try:
    from scipy.stats import norm as _norm
    _PDF0 = float(_norm.pdf(0))          # ≈ 0.3989422804014327
except ImportError:
    _PDF0 = 0.3989


# ---------------------------------------------------------------------------
# CLVPoint
# ---------------------------------------------------------------------------
@dataclass
class CLVPoint:
    bet_id: str
    book: str
    market: str
    line_at_bet: float
    line_at_close: float
    side: str          # "OVER" | "UNDER"
    clv_units: float
    clv_prob_pts: float
    model_p: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _atomic_write_json(path: Path, data: dict) -> None:
    """Write *data* as JSON to *path* atomically via a sibling .tmp file + os.replace."""
    import os
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _norm_player(name: str) -> str:
    """Lowercase + strip combining marks (accents)."""
    nfkd = unicodedata.normalize("NFKD", str(name))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _sigma(stat: str) -> float:
    s = stat.lower()
    return BASE_SIGMA.get(s, 1.0) * SIGMA_MULT.get(s, 1.0)


def _parse_snapshot_ts(filename: str) -> Optional[datetime]:
    """Extract datetime from prizepicks_YYYY-MM-DD_HHMM.csv."""
    m = re.search(r"prizepicks_(\d{4}-\d{2}-\d{2})_(\d{4})", filename)
    if not m:
        return None
    date_str, time_str = m.group(1), m.group(2)
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H%M")


# ---------------------------------------------------------------------------
# Core CLV computation
# ---------------------------------------------------------------------------
def compute_clv(
    bet,
    line_at_bet: float,
    line_at_close: float,
    *,
    stat: str = "",
    model_p: float = 0.0,
) -> CLVPoint:
    """Compute CLV for one bet.

    Parameters
    ----------
    bet : dict-like or BetRow with .bet_id, .book, .market, .side, .stat, .model_p_side
    line_at_bet   : float  — line when bet was placed
    line_at_close : float  — line at market close / tipoff

    Returns CLVPoint with clv_units and clv_prob_pts filled.
    """
    # Accept dict or dataclass
    if hasattr(bet, "__getitem__"):
        bet_id = str(bet.get("bet_id", ""))
        book = str(bet.get("book", ""))
        market = str(bet.get("market", ""))
        side = str(bet.get("side", "OVER")).upper()
        stat = str(bet.get("stat", stat)).lower()
        model_p = float(bet.get("model_p_side", model_p) or model_p)
    else:
        bet_id = str(getattr(bet, "bet_id", ""))
        book = str(getattr(bet, "book", ""))
        market = str(getattr(bet, "market", ""))
        side = str(getattr(bet, "side", "OVER")).upper()
        stat = str(getattr(bet, "stat", stat)).lower()
        model_p = float(getattr(bet, "model_p_side", model_p) or model_p)

    if side == "OVER":
        clv_units = line_at_bet - line_at_close
    else:  # UNDER
        clv_units = line_at_close - line_at_bet

    sigma = _sigma(stat)
    clv_prob_pts = (clv_units / sigma) * 100.0 * _PDF0

    return CLVPoint(
        bet_id=bet_id,
        book=book,
        market=market,
        line_at_bet=line_at_bet,
        line_at_close=line_at_close,
        side=side,
        clv_units=round(clv_units, 4),
        clv_prob_pts=round(clv_prob_pts, 4),
        model_p=model_p,
    )


# ---------------------------------------------------------------------------
# Snapshot loading
# ---------------------------------------------------------------------------
def load_snapshots(
    start_date: str,
    end_date: str,
    book_filter: list[str] = None,
) -> pd.DataFrame:
    """Load all PrizePicks snapshots between start_date and end_date (inclusive).

    Returns DataFrame with columns:
        snapshot_ts (datetime), player_norm, stat, line (float), book
    """
    if not _SNAPSHOT_DIR.exists():
        log.warning("load_snapshots: snapshot dir not found: %s", _SNAPSHOT_DIR)
        return pd.DataFrame()

    frames = []
    for csv_path in sorted(_SNAPSHOT_DIR.glob("prizepicks_*.csv")):
        ts = _parse_snapshot_ts(csv_path.name)
        if ts is None:
            continue
        date_str = ts.strftime("%Y-%m-%d")
        if date_str < start_date or date_str > end_date:
            continue
        try:
            df = pd.read_csv(csv_path, dtype=str)
        except Exception as exc:
            log.warning("load_snapshots: failed reading %s: %s", csv_path.name, exc)
            continue

        if "player" not in df.columns or "stat" not in df.columns or "line" not in df.columns:
            continue

        df["snapshot_ts"] = ts
        df["player_norm"] = df["player"].apply(_norm_player)
        df["line"] = pd.to_numeric(df["line"], errors="coerce")
        df["book"] = df.get("book", pd.Series(["prizepicks"] * len(df), dtype=str))
        frames.append(df[["snapshot_ts", "player_norm", "stat", "line", "book"]].dropna(subset=["line"]))

    if not frames:
        log.warning("load_snapshots: no valid snapshot files in [%s, %s]", start_date, end_date)
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)

    # Alt-line collapse: per (player_norm, stat, snapshot_ts) keep line nearest to median
    if len(result) > 0:
        grp = result.groupby(["player_norm", "stat", "snapshot_ts"])["line"]
        medians = grp.transform("median")
        result["_dist"] = (result["line"] - medians).abs()
        result = (
            result.sort_values("_dist")
            .drop_duplicates(subset=["player_norm", "stat", "snapshot_ts"])
            .drop(columns=["_dist"])
            .reset_index(drop=True)
        )

    if book_filter:
        book_filter_lower = [b.lower() for b in book_filter]
        result = result[result["book"].str.lower().isin(book_filter_lower)]

    return result


# ---------------------------------------------------------------------------
# Join bets to closing lines
# ---------------------------------------------------------------------------
def join_bets_to_closes(
    bets_df: pd.DataFrame,
    snapshots_df: pd.DataFrame,
) -> pd.DataFrame:
    """For each bet find line_at_bet and line_at_close from snapshots.

    Adds columns: line_at_bet_snap, line_at_close_snap, clv_units, clv_prob_pts,
                  skipped_reason  ('' = ok, 'no_close', 'live_bet')
    """
    if bets_df.empty or snapshots_df.empty:
        bets_df = bets_df.copy()
        for col in ("line_at_bet_snap", "line_at_close_snap",
                    "clv_units", "clv_prob_pts", "skipped_reason"):
            bets_df[col] = None
        return bets_df

    snap_indexed = snapshots_df.copy()

    result_rows = []
    for _, bet in bets_df.iterrows():
        player_norm = _norm_player(str(bet.get("player", "")))
        stat = str(bet.get("stat", "")).lower()
        side = str(bet.get("side", "OVER")).upper()
        book = str(bet.get("book", "")).lower()
        placed_raw = str(bet.get("placed_at_iso", ""))
        line_placed = float(bet.get("line", 0.0) or 0.0)

        row = bet.to_dict()
        row["line_at_bet_snap"] = None
        row["line_at_close_snap"] = None
        row["clv_units"] = None
        row["clv_prob_pts"] = None
        row["skipped_reason"] = ""

        # Parse placed_at
        try:
            placed_dt = datetime.fromisoformat(placed_raw.replace("Z", "+00:00"))
            if placed_dt.tzinfo is not None:
                placed_dt = placed_dt.replace(tzinfo=None)
        except (ValueError, AttributeError):
            row["skipped_reason"] = "no_close"
            result_rows.append(row)
            continue

        # Data classification: skip in-game (live) prop markets — no pre-game close exists
        market_val = str(bet.get("market", "")).lower()
        if _MARKET_TYPE_LIVE in market_val:
            row["skipped_reason"] = "live_bet"
            result_rows.append(row)
            continue

        # Filter snapshots to this player + stat
        mask = (
            (snap_indexed["player_norm"] == player_norm)
            & (snap_indexed["stat"].str.lower() == stat)
        )
        if book and book != "":
            mask &= snap_indexed["book"].str.lower().str.contains(
                "prizepicks" if "prize" in book else book, na=False
            )

        player_snaps = snap_indexed[mask].copy()
        if player_snaps.empty:
            row["skipped_reason"] = "no_close"
            result_rows.append(row)
            continue

        # line_at_bet = snapshot with max ts <= placed_at
        before_bet = player_snaps[player_snaps["snapshot_ts"] <= placed_dt]
        if not before_bet.empty:
            bet_snap = before_bet.loc[before_bet["snapshot_ts"].idxmax()]
            row["line_at_bet_snap"] = float(bet_snap["line"])
        else:
            row["line_at_bet_snap"] = line_placed  # fallback to recorded line

        # line_at_close = last snapshot of the day (proxy for tipoff close)
        date_str = placed_dt.strftime("%Y-%m-%d")
        eod = datetime.strptime(date_str + " 23:59", "%Y-%m-%d %H:%M")
        day_snaps = player_snaps[
            (player_snaps["snapshot_ts"] >= placed_dt)
            & (player_snaps["snapshot_ts"] <= eod)
        ]
        if day_snaps.empty:
            # fall back to all snaps on or before placed_dt
            day_snaps = before_bet
        if day_snaps.empty:
            row["skipped_reason"] = "no_close"
            result_rows.append(row)
            continue

        close_snap = day_snaps.loc[day_snaps["snapshot_ts"].idxmax()]
        row["line_at_close_snap"] = float(close_snap["line"])

        # Compute CLV
        lbet = float(row["line_at_bet_snap"])
        lclose = float(row["line_at_close_snap"])
        stat_key = stat
        if side == "OVER":
            clv_u = lbet - lclose
        else:
            clv_u = lclose - lbet
        sigma = _sigma(stat_key)
        clv_pp = (clv_u / sigma) * 100.0 * _PDF0
        row["clv_units"] = round(clv_u, 4)
        row["clv_prob_pts"] = round(clv_pp, 4)

        result_rows.append(row)

    return pd.DataFrame(result_rows)


# ---------------------------------------------------------------------------
# Ledger loader
# ---------------------------------------------------------------------------
def _load_bets() -> pd.DataFrame:
    """Load bets from parquet (preferred) or CSV fallback."""
    try:
        if _BETS_PARQUET.exists():
            return pd.read_parquet(_BETS_PARQUET)
    except Exception as exc:
        log.warning("_load_bets: parquet read failed: %s — trying CSV", exc)
    if _BETS_CSV.exists():
        return pd.read_csv(_BETS_CSV, dtype=str)
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Nightly report
# ---------------------------------------------------------------------------
def nightly_clv_report(date: str = None) -> dict:
    """Produce a nightly CLV report for `date` (defaults to today).

    Writes data/ledger/clv_report_<date>.json and returns the dict.
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    bets_df = _load_bets()
    if bets_df.empty:
        log.warning("nightly_clv_report: L07 ledger is empty or missing")
        return {}

    # Filter to bets placed on `date`
    if "placed_at_iso" not in bets_df.columns:
        log.warning("nightly_clv_report: ledger missing placed_at_iso column")
        return {}

    day_bets = bets_df[bets_df["placed_at_iso"].astype(str).str[:10] == date].copy()
    if day_bets.empty:
        log.warning("nightly_clv_report: no bets on %s", date)

    snaps = load_snapshots(date, date)
    joined = join_bets_to_closes(day_bets, snaps)

    live_mask = joined["skipped_reason"].fillna("") == "live_bet"
    no_close_mask = joined["skipped_reason"].fillna("") == "no_close"
    ok_mask = joined["skipped_reason"].fillna("") == ""

    clv_rows = joined[ok_mask & joined["clv_units"].notna()]
    n_with = int(ok_mask.sum())
    n_live = int(live_mask.sum())
    n_no_close = int(no_close_mask.sum())

    mean_clv_u = round(float(clv_rows["clv_units"].mean()), 4) if not clv_rows.empty else 0.0
    mean_clv_pp = round(float(clv_rows["clv_prob_pts"].mean()), 4) if not clv_rows.empty else 0.0
    pct_pos = round(float((clv_rows["clv_units"] > 0).sum() / max(len(clv_rows), 1)), 4)

    # Per-stat breakdown
    per_stat: dict[str, dict] = {}
    if not clv_rows.empty and "stat" in clv_rows.columns:
        for stat_key, grp in clv_rows.groupby(clv_rows["stat"].str.lower()):
            per_stat[str(stat_key)] = {
                "n": int(len(grp)),
                "mean_clv_units": round(float(grp["clv_units"].mean()), 4),
                "mean_clv_prob_pts": round(float(grp["clv_prob_pts"].mean()), 4),
                "pct_positive_clv": round(float((grp["clv_units"] > 0).mean()), 4),
            }

    # Per-book breakdown
    per_book: dict[str, dict] = {}
    if not clv_rows.empty and "book" in clv_rows.columns:
        for book_key, grp in clv_rows.groupby(clv_rows["book"].str.lower()):
            per_book[str(book_key)] = {
                "n": int(len(grp)),
                "mean_clv_units": round(float(grp["clv_units"].mean()), 4),
                "mean_clv_prob_pts": round(float(grp["clv_prob_pts"].mean()), 4),
            }

    # Top/bottom bets
    def _row_summary(row: pd.Series) -> dict:
        return {
            "bet_id": str(row.get("bet_id", "")),
            "player": str(row.get("player", "")),
            "stat": str(row.get("stat", "")),
            "side": str(row.get("side", "")),
            "line_at_bet": float(row.get("line_at_bet_snap") or row.get("line", 0)),
            "line_at_close": float(row.get("line_at_close_snap") or 0),
            "clv_units": float(row.get("clv_units", 0)),
            "clv_prob_pts": float(row.get("clv_prob_pts", 0)),
        }

    top5: list = []
    bottom5: list = []
    if not clv_rows.empty:
        sorted_rows = clv_rows.sort_values("clv_units", ascending=False)
        top5 = [_row_summary(r) for _, r in sorted_rows.head(5).iterrows()]
        bottom5 = [_row_summary(r) for _, r in sorted_rows.tail(5).iterrows()]

    # Rolling 14-day for drift warning
    rolling = rolling_clv_trend(days=14)
    drift_warn = bool(alert_clv_drift(window_days=14, threshold_pp=-2.0))

    report = {
        "date": date,
        "n_bets_with_clv": n_with,
        "n_skipped_no_close": n_no_close,
        "n_skipped_live": n_live,
        "mean_clv_units": mean_clv_u,
        "mean_clv_prob_pts": mean_clv_pp,
        "pct_positive_clv": pct_pos,
        "per_stat_clv": per_stat,
        "per_book_clv": per_book,
        "top5_best": top5,
        "top5_worst": bottom5,
        "rolling14d": rolling.get("daily_trend", []),
        "drift_warning": drift_warn,
    }

    # Write to disk atomically (tmp → replace) to avoid partial-read races
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _LEDGER_DIR / f"clv_report_{date}.json"
    _atomic_write_json(out_path, report)
    log.info("nightly_clv_report: wrote %s", out_path)
    return report


# ---------------------------------------------------------------------------
# Rolling trend + drift alert
# ---------------------------------------------------------------------------
def rolling_clv_trend(days: int = 30) -> dict:
    """Compute daily mean CLV (prob_pts) over the past `days` days.

    Returns:
        {"days": 30, "overall_mean_clv_pp": x, "daily_trend": [{"date": ..., "mean_clv_pp": ...}]}
    """
    bets_df = _load_bets()
    if bets_df.empty:
        return {"days": days, "overall_mean_clv_pp": None, "daily_trend": []}

    today = datetime.now().date()
    start = (today - timedelta(days=days - 1)).isoformat()
    end = today.isoformat()

    snaps = load_snapshots(start, end)
    if "placed_at_iso" not in bets_df.columns:
        return {"days": days, "overall_mean_clv_pp": None, "daily_trend": []}

    window_bets = bets_df[
        (bets_df["placed_at_iso"].astype(str).str[:10] >= start)
        & (bets_df["placed_at_iso"].astype(str).str[:10] <= end)
    ].copy()

    if window_bets.empty:
        return {"days": days, "overall_mean_clv_pp": None, "daily_trend": []}

    joined = join_bets_to_closes(window_bets, snaps)
    ok = joined[joined["skipped_reason"].fillna("") == ""]
    ok = ok[ok["clv_prob_pts"].notna()]

    daily: list[dict] = []
    if not ok.empty and "placed_at_iso" in ok.columns:
        ok = ok.copy()
        ok["_date"] = ok["placed_at_iso"].astype(str).str[:10]
        for d, grp in ok.groupby("_date"):
            daily.append({"date": str(d), "mean_clv_pp": round(float(grp["clv_prob_pts"].mean()), 4)})

    overall = round(float(ok["clv_prob_pts"].mean()), 4) if not ok.empty else None
    return {"days": days, "overall_mean_clv_pp": overall, "daily_trend": daily}


def alert_clv_drift(
    window_days: int = 14,
    threshold_pp: float = -2.0,
) -> list:
    """Return list of Alert dicts if mean CLV prob_pts over `window_days` < threshold_pp.

    Each alert dict: {"type": "CLV_DRIFT", "window_days": int, "mean_clv_pp": float,
                      "threshold_pp": float, "message": str}
    """
    trend = rolling_clv_trend(days=window_days)
    mean_pp = trend.get("overall_mean_clv_pp")
    if mean_pp is None:
        return []
    if mean_pp < threshold_pp:
        return [{
            "type": "CLV_DRIFT",
            "window_days": window_days,
            "mean_clv_pp": mean_pp,
            "threshold_pp": threshold_pp,
            "message": (
                f"CLV drift detected: {window_days}d mean = {mean_pp:.2f} pp "
                f"(threshold = {threshold_pp:.2f} pp)"
            ),
        }]
    return []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli_report(args) -> None:
    report = nightly_clv_report(date=args.date)
    if not report:
        print("[L19] no report data")
        return
    print(f"[L19] CLV report {report['date']}")
    print(f"  bets_with_clv : {report['n_bets_with_clv']}")
    print(f"  mean_clv_units: {report['mean_clv_units']:.4f}")
    print(f"  mean_clv_pp   : {report['mean_clv_prob_pts']:.4f}")
    print(f"  pct_positive  : {report['pct_positive_clv']:.1%}")
    print(f"  drift_warning : {report['drift_warning']}")


def _cli_trend(args) -> None:
    trend = rolling_clv_trend(days=args.days)
    print(f"[L19] CLV trend last {trend['days']}d  overall={trend['overall_mean_clv_pp']}")
    for entry in trend["daily_trend"]:
        print(f"  {entry['date']}  {entry['mean_clv_pp']:+.4f} pp")


def _cli_alert(args) -> None:
    alerts = alert_clv_drift(window_days=args.window, threshold_pp=args.threshold)
    if not alerts:
        print("[L19] no CLV drift alerts")
    for a in alerts:
        print(f"[L19] ALERT: {a['message']}")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="L19_clv_calculator")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_report = sub.add_parser("report", help="Nightly CLV report")
    p_report.add_argument("--date", default=None, help="YYYY-MM-DD (defaults to today)")
    p_report.set_defaults(func=_cli_report)

    p_trend = sub.add_parser("trend", help="Rolling CLV trend")
    p_trend.add_argument("--days", type=int, default=30)
    p_trend.set_defaults(func=_cli_trend)

    p_alert = sub.add_parser("alert", help="CLV drift alert check")
    p_alert.add_argument("--window", type=int, default=14)
    p_alert.add_argument("--threshold", type=float, default=-2.0)
    p_alert.set_defaults(func=_cli_alert)

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
