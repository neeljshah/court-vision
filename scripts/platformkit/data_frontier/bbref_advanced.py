"""scripts.platformkit.data_frontier.bbref_advanced -- basketball-reference.com
advanced season tables (frontier census rank 4, SCRAPABLE_POLITE; robots.txt
allows /leagues/*_advanced.html and /wnba/years/*_advanced.html, Crawl-delay: 3).

NBA: the 4 relevant seasons (2022-23..2025-26, matching the games/odds corpus's
on-disk range) are ALREADY fully landed --
  data/cache/bbref_backfill/advanced_{2020-21..2023-24}.parquet
  data/external/bbref_advanced_{2024-25,2025-26}.json
via the existing domains.basketball_nba.bbref_backfill module. This module does
NOT re-scrape NBA -- it verifies that coverage (rung-2 reuse, ponytail) and only
delegates to bbref_backfill.backfill_seasons for whatever season is actually
missing (should be none, this run).

WNBA: bbref publishes an equivalent table at a DIFFERENT url shape and column
set -- /wnba/years/<year>_advanced.html (single calendar year, not "2020-21"),
and WNBA's advanced table has no BPM/OBPM/DBPM/VORP; it substitutes off_rtg/
def_rtg and uses ws_per_40 (40-minute WNBA games) instead of ws_per_48. This is
genuinely new coverage (nothing bbref-WNBA on disk before this module) for the
3 seasons the WNBA corpus covers (2024, 2025, 2026 -- data_census.json
scoreboard_linescores coverage 2024-05..2026-07).

CLI: python -m scripts.platformkit.data_frontier.bbref_advanced
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from scripts.platformkit.data_frontier._politeness import log_line

_REPO = Path(__file__).resolve().parents[3]
_NBA_BACKFILL_DIR = _REPO / "data" / "cache" / "bbref_backfill"
_NBA_EXTERNAL_DIR = _REPO / "data" / "external"
_WNBA_OUT_DIR = _REPO / "data" / "cache" / "bbref_wnba"
_LOG_FP = _REPO / "data" / "cache" / "logs" / "bbref_advanced.log"

NBA_TARGET_SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]
WNBA_TARGET_YEARS = [2024, 2025, 2026]
_RATE_LIMIT_SECONDS = 3.0  # robots.txt crawl_delay=3, same floor as bbref_backfill

_WNBA_ADVANCED_COLS = [
    "g", "mp", "per", "ts_pct", "efg_pct", "fg3a_per_fga_pct", "fta_per_fga_pct",
    "orb_pct", "trb_pct", "ast_pct", "stl_pct", "blk_pct", "tov_pct", "usg_pct",
    "off_rtg", "def_rtg", "ows", "dws", "ws", "ws_per_40",
]


def nba_coverage() -> Dict[str, bool]:
    """True per season already on disk in EITHER the backfill parquet dir or the
    data/external json dir -- both are reachable outputs of bbref_backfill."""
    cov: Dict[str, bool] = {}
    for season in NBA_TARGET_SEASONS:
        parquet_hit = (_NBA_BACKFILL_DIR / f"advanced_{season}.parquet").exists()
        json_hit = (_NBA_EXTERNAL_DIR / f"bbref_advanced_{season}.json").exists()
        cov[season] = parquet_hit or json_hit
    return cov


def ensure_nba(fetcher=None) -> Dict[str, object]:
    """Reuse domains.basketball_nba.bbref_backfill for any missing season only
    (expected: none, this pull already landed 2022-23..2025-26)."""
    cov = nba_coverage()
    missing = [s for s in NBA_TARGET_SEASONS if not cov[s]]
    if not missing:
        return {"already_covered": True, "coverage": cov, "seasons_fetched": []}
    from domains.basketball_nba.bbref_backfill import backfill_seasons
    result = backfill_seasons(missing, fetcher=fetcher)
    return {"already_covered": False, "coverage": cov,
            "seasons_fetched": result.seasons_landed,
            "pages_blocked": result.pages_blocked}


def _parse_wnba_advanced(html: str) -> List[Dict[str, Any]]:
    from bs4 import BeautifulSoup, Comment

    soup = BeautifulSoup(html, "html.parser")
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        cs = BeautifulSoup(str(comment), "html.parser")
        if cs.find("table"):
            comment.replace_with(cs)
    table = soup.find("table", {"id": "advanced"})
    if table is None:
        return []
    tbody = table.find("tbody")
    if tbody is None:
        return []
    rows: List[Dict[str, Any]] = []
    for tr in tbody.find_all("tr"):
        if "thead" in (tr.get("class") or []):
            continue
        row: Dict[str, Any] = {}
        for td in tr.find_all(["td", "th"]):
            key = td.get("data-stat")
            if key:
                row[key] = td.get_text(strip=True)
        name = row.get("player", "").strip("*").strip()
        if not name:
            continue
        rows.append(row)
    return rows


def _normalise_wnba(records: List[Dict[str, Any]], year: int) -> pd.DataFrame:
    out_rows = []
    for row in records:
        rec: Dict[str, Any] = {
            "player_name": row.get("player", "").strip("*").strip(),
            "team": row.get("team", ""),
            "pos": row.get("pos", ""),
            "season_year": year,
            "source": "bbref_wnba_frontier_2026_07_09",
        }
        for col in _WNBA_ADVANCED_COLS:
            v = row.get(col)
            if v in (None, "", "\xa0"):
                rec[col] = None
            else:
                try:
                    rec[col] = float(v)
                except ValueError:
                    rec[col] = None
        out_rows.append(rec)
    return pd.DataFrame(out_rows)


def fetch_wnba_year_html(year: int, fetcher=None) -> str:
    from scripts.platformkit.odds_provider import stealth_fetch

    url = f"https://www.basketball-reference.com/wnba/years/{year}_advanced.html"
    if fetcher is not None:
        response = fetcher(url, timeout=25.0)
    else:
        if not stealth_fetch.stealth_available():
            raise stealth_fetch.StealthUnavailable("stealth transport not importable")
        response = stealth_fetch._real_fetcher(url, timeout=25.0)  # noqa: SLF001
    status = int(getattr(response, "status", 200))
    if status >= 400:
        import urllib.error
        raise urllib.error.HTTPError(url, status, "bbref WNBA fetch blocked", None, None)
    body = getattr(response, "body", None) or getattr(response, "text", None)
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    return body


def pull_wnba(
    years: List[int] = WNBA_TARGET_YEARS,
    *,
    fetcher=None,
    out_dir: Path = _WNBA_OUT_DIR,
    log_path: Path = _LOG_FP,
) -> Dict[str, object]:
    """Skip-if-cached per year; one polite (>=3s) fetch per missing year."""
    out_dir.mkdir(parents=True, exist_ok=True)
    landed, skipped, blocked = [], [], []
    for i, year in enumerate(years):
        out_fp = out_dir / f"wnba_advanced_{year}.parquet"
        if out_fp.exists():
            skipped.append(year)
            continue
        try:
            html = fetch_wnba_year_html(year, fetcher=fetcher)
        except Exception as exc:  # noqa: BLE001 -- classify + honest stop
            blocked.append(f"{year}: {exc}")
            log_line(log_path, f"WNBA {year} BLOCKED {exc}")
            break
        records = _parse_wnba_advanced(html)
        if not records:
            blocked.append(f"{year}: no #advanced table parsed")
            log_line(log_path, f"WNBA {year} BLOCKED no table")
            break
        df = _normalise_wnba(records, year)
        df.to_parquet(out_fp, index=False)
        landed.append(year)
        log_line(log_path, f"WNBA {year} OK rows={len(df)}")
        if i != len(years) - 1:
            time.sleep(_RATE_LIMIT_SECONDS)
    return {"landed": landed, "skipped_already_cached": skipped, "blocked": blocked}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="bbref advanced tables: NBA verify + WNBA pull.")
    ap.add_argument("--skip-wnba", action="store_true")
    a = ap.parse_args(argv)
    result = {"nba": ensure_nba()}
    if not a.skip_wnba:
        result["wnba"] = pull_wnba()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = ["nba_coverage", "ensure_nba", "pull_wnba", "fetch_wnba_year_html",
           "NBA_TARGET_SEASONS", "WNBA_TARGET_YEARS", "main"]
