"""domains.basketball_nba.bbref_backfill -- historical bbref advanced-stats
backfill (lane bbref-ingest, wave-52).

PURPOSE: fetch basketball-reference.com's per-season "advanced" table for
older seasons (2020-21 .. 2023-24) that are NOT already on disk, so the
fit-validity-gate power audit (docs/research/intel-layer
/fit_validity_gate_prereg.json) can be re-evaluated at a larger n than the
single 2024-25/2025-26 cohort currently gives (n=96 strict moves).

PROVENANCE SEPARATION (hard rail): this module NEVER reads or writes
data/cache/bbref_advanced_extended.parquet. That file is the existing,
already-verified corpus behind the frozen pre-registration and must stay
byte-identical. This module's output lives in its OWN directory
(data/cache/bbref_backfill/) with its own provenance tag
(source=bbref_backfill_2026-07-05) so the two corpora can never be silently
merged or mistaken for one another.

NETWORK SANCTION (this module's only network use, per the wave-52 brief):
keyless GET of basketball-reference.com's public season-advanced pages via
the stealth transport (scripts.platformkit.odds_provider.stealth_fetch --
already used elsewhere in this repo for bot-walled public endpoints; a plain
urllib/requests GET is confirmed 403'd on this host per the scout probe). At
most 4 page fetches (one per season) + 2 retry/aux requests, sleeping
>= max(3s, robots crawl_delay=3) between EVERY request (see _rate_limit).
If any page comes back 403/429, this module STOPS immediately, keeps
whatever already landed, and reports an honest partial (see
BackfillResult.pages_blocked).

Column set mirrors bbref_advanced_extended.parquet's own 26 columns (see
scripts/build_bbref_advanced_extended.py) so the two corpora are directly
comparable in shape, never in identity.

CLI:
    python -m domains.basketball_nba.bbref_backfill --seasons 2020-21 2021-22 2022-23 2023-24
"""
from __future__ import annotations

import json
import time
import unicodedata
import re as _re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_OUT_DIR = REPO_ROOT / "data" / "cache" / "bbref_backfill"
_BBREF_BASE = "https://www.basketball-reference.com"
_PROVENANCE = "bbref_backfill_2026-07-05"

# Same identity + advanced-stat column set as bbref_advanced_extended.parquet
# (json_key on the bbref page -> our output column name).
_ADVANCED_COLS: list[tuple[str, str]] = [
    ("obpm", "obpm"), ("dbpm", "dbpm"), ("bpm", "bpm"), ("vorp", "vorp"),
    ("ws_per_48", "ws_per_48"), ("ws", "ws"), ("ows", "ows"), ("dws", "dws"),
    ("orb_pct", "orb_pct"), ("drb_pct", "drb_pct"), ("trb_pct", "trb_pct"),
    ("stl_pct", "stl_pct"), ("blk_pct", "blk_pct"), ("tov_pct", "tov_pct"),
    ("ast_pct", "ast_pct"), ("per", "per"), ("ftr", "ftr"),
    ("three_par", "three_par"), ("usg_pct", "usg_pct"), ("ts_pct", "ts_pct"),
]
# bbref data-stat keys actually seen on the advanced table (some pages use a
# terse alias); each output column tries these in order.
_ALIASES: dict[str, list[str]] = {
    "obpm": ["obpm"], "dbpm": ["dbpm"], "bpm": ["bpm"], "vorp": ["vorp"],
    "ws_per_48": ["ws_per_48"], "ws": ["ws", "win_shares"],
    "ows": ["ows"], "dws": ["dws"],
    "orb_pct": ["orb_pct"], "drb_pct": ["drb_pct"], "trb_pct": ["trb_pct"],
    "stl_pct": ["stl_pct"], "blk_pct": ["blk_pct"], "tov_pct": ["tov_pct"],
    "ast_pct": ["ast_pct"], "per": ["per"], "ftr": ["fta_per_fga_pct", "ftr"],
    "three_par": ["fg3a_per_fga_pct", "three_par"],
    "usg_pct": ["usg_pct"], "ts_pct": ["ts_pct"],
}

RATE_LIMIT_SECONDS = 3.0  # robots.txt crawl_delay=3 (scout-verified); use the floor, never less


def _season_to_year(season: str) -> int:
    """'2020-21' -> 2021 (bbref pages are keyed on the END year)."""
    return int(season.split("-")[0]) + 1


def _unmangle_utf8(s: str) -> str:
    try:
        if s.isascii():
            return s
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _rate_limit(secs: float = RATE_LIMIT_SECONDS) -> None:
    time.sleep(max(secs, RATE_LIMIT_SECONDS))


@dataclass
class BackfillResult:
    seasons_landed: list[str] = field(default_factory=list)
    rows_per_season: dict[str, int] = field(default_factory=dict)
    pages_blocked: list[str] = field(default_factory=list)
    requests_made: int = 0
    output_paths: dict[str, str] = field(default_factory=dict)


def _parse_advanced_table(html: str) -> list[dict[str, Any]]:
    """Parse the #advanced stats table out of a bbref league-season page.

    bbref wraps some stats tables inside HTML comments; unwrap them first.
    Mirrors the parsing shape of src/data/bbref_scraper.py's
    _parse_advanced_table (read-only reference, NOT imported -- src/ is
    human-gated) reimplemented standalone here.
    """
    from bs4 import BeautifulSoup, Comment

    soup = BeautifulSoup(html, "html.parser")
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment_soup = BeautifulSoup(str(comment), "html.parser")
        if comment_soup.find("table"):
            comment.replace_with(comment_soup)

    table = soup.find("table", {"id": "advanced"})
    if table is None:
        return []

    tbody = table.find("tbody")
    if tbody is None:
        return []

    records: list[dict[str, Any]] = []
    for tr in tbody.find_all("tr"):
        if "thead" in (tr.get("class") or []):
            continue
        cells = tr.find_all(["td", "th"])
        if len(cells) < 5:
            continue
        row: dict[str, Any] = {}
        for td in cells:
            key = td.get("data-stat")
            if not key:
                continue
            val = td.get_text(strip=True)
            row[key] = val
        if row.get("name_display") or row.get("player"):
            records.append(row)
    return records


def _get(key: str, row: dict[str, Any]) -> Optional[float]:
    for alias in _ALIASES.get(key, [key]):
        v = row.get(alias)
        if v not in (None, "", "\xa0"):
            try:
                return float(v)
            except ValueError:
                continue
    return None


def _normalise_rows(records: list[dict[str, Any]], season: str, season_year: int) -> list[dict[str, Any]]:
    out_rows = []
    for row in records:
        name = _unmangle_utf8(str(row.get("name_display") or row.get("player") or "")).strip("*").strip()
        if not name:
            continue
        team = str(row.get("team_name_abbr") or row.get("team") or row.get("tm") or "").strip()
        out: dict[str, Any] = {
            "player_name": name,
            "player_id": None,  # id resolution is out of scope for this lane; downstream joins on name
            "unresolved_name": True,
            "team": team,
            "season": season,
            "season_year": season_year,
            "source": _PROVENANCE,
        }
        for _, out_col in _ADVANCED_COLS:
            out[out_col] = _get(out_col, row)
        out_rows.append(out)
    return out_rows


def fetch_season_html(
    season: str,
    *,
    fetcher: Optional[Callable[..., Any]] = None,
) -> str:
    """Fetch one season's advanced-stats page HTML via the stealth transport.

    *fetcher*, if given, replaces the real network call (offline tests inject
    a fake object exposing .status/.body -- no scrapling, no network).
    Raises on any non-2xx status (propagates the real code via the stealth
    module's own HTTPError) so the caller can classify 403/429 and stop.
    """
    from scripts.platformkit.odds_provider import stealth_fetch

    year = _season_to_year(season)
    url = f"{_BBREF_BASE}/leagues/NBA_{year}_advanced.html"

    if fetcher is not None:
        response = fetcher(url, timeout=20.0)
    else:
        if not stealth_fetch.stealth_available():
            raise stealth_fetch.StealthUnavailable("stealth transport not importable")
        response = stealth_fetch._real_fetcher(url, timeout=20.0)  # noqa: SLF001 -- reuse the exact stealth call

    status = int(getattr(response, "status", 200))
    if status >= 400:
        import urllib.error
        raise urllib.error.HTTPError(url, status, "bbref fetch blocked", None, None)

    body = getattr(response, "body", None) or getattr(response, "text", None)
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    return body


def backfill_seasons(
    seasons: list[str],
    *,
    fetcher: Optional[Callable[..., Any]] = None,
    out_dir: Path = _OUT_DIR,
    max_requests: int = 8,
) -> BackfillResult:
    """Fetch + parse + write one parquet per season. Stops on the first
    403/429 (or once max_requests is hit) and returns whatever landed --
    never raises past a single blocked page, per the wave-52 honest-partial
    rail."""
    result = BackfillResult()
    out_dir.mkdir(parents=True, exist_ok=True)

    for season in seasons:
        if result.requests_made >= max_requests:
            break
        result.requests_made += 1
        try:
            html = fetch_season_html(season, fetcher=fetcher)
        except Exception as exc:  # noqa: BLE001 -- classify below, fail closed to "blocked"
            result.pages_blocked.append(f"{season}: {exc}")
            break  # honest stop -- do not keep hammering a wall

        records = _parse_advanced_table(html)
        if not records:
            result.pages_blocked.append(f"{season}: no #advanced table parsed (empty/challenge page)")
            break

        rows = _normalise_rows(records, season, _season_to_year(season))
        df = pd.DataFrame(rows)
        out_path = out_dir / f"advanced_{season}.parquet"
        df.to_parquet(out_path, index=False, engine="pyarrow")

        result.seasons_landed.append(season)
        result.rows_per_season[season] = len(df)
        try:
            path_str = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            path_str = str(out_path)  # out_dir outside REPO_ROOT (e.g. a test tmp_path)
        result.output_paths[season] = path_str

        if season != seasons[-1]:
            _rate_limit()

    return result


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Backfill historical bbref advanced-stat seasons")
    parser.add_argument("--seasons", nargs="+", default=["2020-21", "2021-22", "2022-23", "2023-24"])
    parser.add_argument("--out-dir", type=str, default=str(_OUT_DIR))
    args = parser.parse_args(argv)

    result = backfill_seasons(args.seasons, out_dir=Path(args.out_dir))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requests_made": result.requests_made,
        "seasons_landed": result.seasons_landed,
        "rows_per_season": result.rows_per_season,
        "pages_blocked": result.pages_blocked,
        "output_paths": result.output_paths,
        "provenance": _PROVENANCE,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
