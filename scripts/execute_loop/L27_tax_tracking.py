"""L27_tax_tracking.py — Tax estimation and 1099-ready export (execute_loop layer 27).

Storage: data/ledger/bets.parquet  (CSV fallback)
         data/ledger/1099_export_<year>.csv

CLI:
    python L27_tax_tracking.py report --year 2026
    python L27_tax_tracking.py quarterly --year 2026 --quarter 2
    python L27_tax_tracking.py export-1099 --year 2026 [--out path.csv]

Environment Variables:
    FEDERAL_TAX_RATE  — Federal marginal tax rate applied to net gambling winnings.
                        Float in [0, 1]. Default: 0.24 (24% bracket).
    STATE_TAX_RATE    — State marginal tax rate applied to net gambling winnings.
                        Float in [0, 1]. Default: 0.00 (no state tax; set for
                        your jurisdiction, e.g. 0.05 for 5%).
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import tempfile
import types
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

# Stub heavy imports if not present (mirrors L07 pattern)
if "src.data.nba_api_headers_patch" not in sys.modules:
    _stub = types.ModuleType("src.data.nba_api_headers_patch")
    sys.modules["src.data.nba_api_headers_patch"] = _stub

import pandas as pd  # noqa: E402

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FEDERAL_TAX_RATE: float = float(os.environ.get("FEDERAL_TAX_RATE", "0.24"))
STATE_TAX_RATE: float = float(os.environ.get("STATE_TAX_RATE", "0.00"))

# ---------------------------------------------------------------------------
# Paths (monkeypatched in tests)
# ---------------------------------------------------------------------------
_LEDGER_DIR: Path = PROJECT_DIR / "data" / "ledger"
_LEDGER_PATH: Path = _LEDGER_DIR / "bets.parquet"
_LEDGER_CSV: Path = _LEDGER_DIR / "bets.csv"

# ---------------------------------------------------------------------------
# Source type constants
# ---------------------------------------------------------------------------
_DFS_BOOKS = {"draftkings_dfs", "fanduel_dfs"}
_SPORTSBOOK_BOOKS = {"dk_props", "fd_props", "mgm"}
_PREDICTION_MARKET_BOOKS = {"kalshi", "polymarket", "sporttrade", "prophet"}
_DEFI_PREFIX = "defi_"

_ALL_SOURCE_TYPES = ("DFS", "Sportsbook", "Prediction Market", "DeFi", "Other")

# ---------------------------------------------------------------------------
# Quarterly calendar
# ---------------------------------------------------------------------------
_QUARTER_MONTHS: dict[int, tuple[int, ...]] = {
    1: (1, 2, 3),
    2: (4, 5, 6),
    3: (7, 8, 9),
    4: (10, 11, 12),
}
_QUARTER_DUE: dict[int, str] = {
    1: "{year}-04-15",
    2: "{year}-06-15",
    3: "{year}-09-15",
    4: "{next_year}-01-15",
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass
class TaxBucket:
    source_type: str          # "DFS"|"Sportsbook"|"Prediction Market"|"DeFi"|"Other"
    gross_winnings: float
    gross_losses: float
    net: float
    fed_tax_estimated: float
    state_tax_estimated: float
    ytd_total: float


# ---------------------------------------------------------------------------
# Atomic-write helpers (L24 v2 pattern)
# ---------------------------------------------------------------------------
def _atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Write *text* to *path* atomically via a sibling temp file.

    Uses tempfile.mkstemp so the temp file is always in the same directory
    (guaranteeing same-filesystem rename on every OS).  Cleans up the temp
    file if os.replace raises.
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _map_book_to_source(book: str) -> str:
    """Return source_type string for a given book value."""
    b = str(book).strip().lower()
    if b in _DFS_BOOKS:
        return "DFS"
    if b in _SPORTSBOOK_BOOKS:
        return "Sportsbook"
    if b in _PREDICTION_MARKET_BOOKS:
        return "Prediction Market"
    if b.startswith(_DEFI_PREFIX):
        return "DeFi"
    log.warning("Unknown book=%r — classified as Other", book)
    return "Other"


def _load_ledger() -> pd.DataFrame:
    """Load bets ledger from parquet, CSV, or return empty DataFrame."""
    try:
        import pyarrow  # noqa: F401
        has_parquet = True
    except ImportError:
        has_parquet = False

    if has_parquet and _LEDGER_PATH.exists():
        return pd.read_parquet(_LEDGER_PATH)
    if _LEDGER_CSV.exists():
        return pd.read_csv(_LEDGER_CSV, dtype=str)
    log.info("No ledger found at %s or %s — returning empty", _LEDGER_PATH, _LEDGER_CSV)
    return pd.DataFrame()


def _zero_buckets() -> list[TaxBucket]:
    """Return zero-filled TaxBuckets for the four standard source types."""
    return [
        TaxBucket(
            source_type=st,
            gross_winnings=0.0,
            gross_losses=0.0,
            net=0.0,
            fed_tax_estimated=0.0,
            state_tax_estimated=0.0,
            ytd_total=0.0,
        )
        for st in ("DFS", "Sportsbook", "Prediction Market", "DeFi")
    ]


def _build_bucket(source_type: str, rows: pd.DataFrame) -> TaxBucket:
    """Build a TaxBucket from a subset of settled rows for one source_type."""
    pnl = pd.to_numeric(rows["pnl"], errors="coerce").fillna(0.0)
    gross_winnings = float(pnl[pnl > 0].sum())
    gross_losses = float(abs(pnl[pnl < 0].sum()))
    net = gross_winnings - gross_losses
    fed_tax = max(0.0, net) * FEDERAL_TAX_RATE
    state_tax = max(0.0, net) * STATE_TAX_RATE
    return TaxBucket(
        source_type=source_type,
        gross_winnings=round(gross_winnings, 4),
        gross_losses=round(gross_losses, 4),
        net=round(net, 4),
        fed_tax_estimated=round(fed_tax, 4),
        state_tax_estimated=round(state_tax, 4),
        ytd_total=round(net, 4),
    )


def _filter_settled_year(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Filter to WON/LOST/PUSH rows settled in the given calendar year."""
    if df.empty:
        return df
    settled = df[df.get("status", pd.Series(dtype=str)).isin(["WON", "LOST", "PUSH"])].copy()
    if settled.empty:
        return settled
    # Parse settled_at_iso — coerce bad values to NaT
    settled["_settled_dt"] = pd.to_datetime(
        settled.get("settled_at_iso", pd.Series(dtype=str)),
        errors="coerce",
        utc=True,
    )
    return settled[settled["_settled_dt"].dt.year == year]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_tax_buckets(year: int) -> list[TaxBucket]:
    """Return one TaxBucket per source_type found in the ledger for *year*.

    Returns zero-filled buckets for the 4 standard source types if no data.
    """
    df = _load_ledger()
    if df.empty:
        log.info("compute_tax_buckets: empty ledger — returning zero buckets")
        return _zero_buckets()

    settled = _filter_settled_year(df, year)
    if settled.empty:
        log.info("compute_tax_buckets: no settled bets in year %d", year)
        return _zero_buckets()

    settled["_source_type"] = settled["book"].apply(_map_book_to_source)

    buckets: list[TaxBucket] = []
    seen_types: set[str] = set()

    for source_type, group in settled.groupby("_source_type"):
        buckets.append(_build_bucket(source_type, group))
        seen_types.add(source_type)

    # Ensure the 4 standard source types always appear (even if zero)
    for st in ("DFS", "Sportsbook", "Prediction Market", "DeFi"):
        if st not in seen_types:
            buckets.append(
                TaxBucket(
                    source_type=st,
                    gross_winnings=0.0,
                    gross_losses=0.0,
                    net=0.0,
                    fed_tax_estimated=0.0,
                    state_tax_estimated=0.0,
                    ytd_total=0.0,
                )
            )

    return buckets


def estimate_quarterly_payment(year: int, quarter: int) -> dict:
    """Estimate tax payment due for a specific calendar quarter.

    Returns dict with: quarter, due_date, federal_due, state_due, calc_basis.
    """
    if quarter not in _QUARTER_MONTHS:
        raise ValueError(f"quarter must be 1-4, got {quarter!r}")

    months = _QUARTER_MONTHS[quarter]
    df = _load_ledger()

    gross_winnings = 0.0
    gross_losses = 0.0

    if not df.empty:
        settled = _filter_settled_year(df, year)
        if not settled.empty:
            q_rows = settled[settled["_settled_dt"].dt.month.isin(months)]
            pnl = pd.to_numeric(q_rows["pnl"], errors="coerce").fillna(0.0)
            gross_winnings = float(pnl[pnl > 0].sum())
            gross_losses = float(abs(pnl[pnl < 0].sum()))

    net = gross_winnings - gross_losses
    federal_due = max(0.0, net) * FEDERAL_TAX_RATE
    state_due = max(0.0, net) * STATE_TAX_RATE

    template = _QUARTER_DUE[quarter]
    due_date = template.format(year=year, next_year=year + 1)

    return {
        "quarter": quarter,
        "due_date": due_date,
        "federal_due": round(federal_due, 4),
        "state_due": round(state_due, 4),
        "calc_basis": {
            "gross_winnings": round(gross_winnings, 4),
            "gross_losses": round(gross_losses, 4),
            "net": round(net, 4),
        },
    }


def export_1099_ready(year: int, out_path: Optional[str] = None) -> str:
    """Write a 1099-ready CSV with one row per source_type bucket.

    Columns: source_type, gross_winnings, gross_losses, net, year
    Returns the path written.
    """
    buckets = compute_tax_buckets(year)
    if out_path is None:
        _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
        dest = _LEDGER_DIR / f"1099_export_{year}.csv"
    else:
        dest = Path(out_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

    import io
    fieldnames = ["source_type", "gross_winnings", "gross_losses", "net", "year"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\r\n")
    writer.writeheader()
    for b in buckets:
        writer.writerow(
            {
                "source_type": b.source_type,
                "gross_winnings": b.gross_winnings,
                "gross_losses": b.gross_losses,
                "net": b.net,
                "year": year,
            }
        )
    _atomic_write_text(dest, buf.getvalue())
    log.info("export_1099_ready: wrote %d rows to %s", len(buckets), dest)
    return str(dest)


def annual_tax_report(year: int) -> dict:
    """Return a full annual tax summary dict.

    Keys: year, buckets, total_net, total_fed_estimated, generated_at
    """
    buckets = compute_tax_buckets(year)
    total_net = sum(b.net for b in buckets)
    total_fed = sum(b.fed_tax_estimated for b in buckets)
    return {
        "year": year,
        "buckets": [asdict(b) for b in buckets],
        "total_net": round(total_net, 4),
        "total_fed_estimated": round(total_fed, 4),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli_report(args: argparse.Namespace) -> None:
    report = annual_tax_report(args.year)
    print(json.dumps(report, indent=2))


def _cli_quarterly(args: argparse.Namespace) -> None:
    result = estimate_quarterly_payment(args.year, args.quarter)
    print(json.dumps(result, indent=2))


def _cli_export(args: argparse.Namespace) -> None:
    out = export_1099_ready(args.year, out_path=getattr(args, "out", None))
    print(f"Exported: {out}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="L27 Tax Tracking")
    sub = parser.add_subparsers(dest="cmd", required=True)

    rp = sub.add_parser("report", help="Full annual tax report")
    rp.add_argument("--year", type=int, required=True)
    rp.set_defaults(func=_cli_report)

    qp = sub.add_parser("quarterly", help="Quarterly payment estimate")
    qp.add_argument("--year", type=int, required=True)
    qp.add_argument("--quarter", type=int, required=True, choices=[1, 2, 3, 4])
    qp.set_defaults(func=_cli_quarterly)

    ep = sub.add_parser("export-1099", help="Export 1099-ready CSV")
    ep.add_argument("--year", type=int, required=True)
    ep.add_argument("--out", type=str, default=None)
    ep.set_defaults(func=_cli_export)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
