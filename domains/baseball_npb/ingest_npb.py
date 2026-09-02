"""domains.baseball_npb.ingest_npb -- npb.jp monthly schedule/results scraper.

WHY THIS EXISTS
----------------
NPB (Nippon Professional Baseball) has no free JSON API equivalent to ESPN's
site.api (used for WNBA/soccer_intl/tennis). npb.jp publishes a monthly HTML
schedule+results page per (year, month): every day-of-month is one <tr id=
"dateMMDD"> row (repeated via rowspan for multi-game days), each game a <td>
block with team1/team2 (Japanese club names in kanji/katakana, e.g. Kyojin
[Giants], Hanshin [Tigers], "DeNA" -- verified live 2026-07-03; NOT English as
an earlier probe note assumed -- correcting that here) and score1/score2
<div>s.

PROBE-FACT CORRECTION (recorded honestly, not chased further per lane scope):
the inherited probe claimed "404 pre-2018". Live-checked here: 2015 and
earlier -> 404, but 2016 AND 2017 both return 200 with real per-game scores
(2016: 136/144 rows scored; 2017: 132/140). The true boundary is 2016, not
2018. This module still only backfills 2022..2026 per the assigned lane scope
("do not chase" older years) -- the correction is recorded so a future lane
does not need to re-discover it.

URL: https://npb.jp/games/{year}/schedule_{month:02d}_detail.html
  Season months actually populated with games: 03 (late-March openers) .. 11
  (Japan Series); 12/01/02 return 200 but are empty off-season templates (no
  <tr id="dateMMDD"> rows with scores) -- harmless no-ops if ever requested,
  but the default range below skips them to avoid a wasted request.

NON-GAME ROW SHAPES (excluded, not counted as ties):
  - off-day: <th rowspan="1">M/D(day)</th> followed by four "&nbsp;" <td>s,
    no team1/team2 at all.
  - postponed/no-game: team1/team2 present, but a "cancel" div reading
    "chuushi" (postponed, kanji) or "no-game" (rained-out, katakana) replaces
    the score1/score2 divs -- no score1 AND no score2 means "not a completed
    game", excluded from the parquet entirely (never a fabricated 0-0).

TIES: NPB allows draws (extra-inning game called by a curfew/inning cap with
scores still level). A completed game with score1 == score2 is a REAL tie:
recorded with home_win=None, EXCLUDED from any win-prob training corpus by
downstream ratings/gate code (which drops NaN targets), but COUNTED and
reported by the CLI/backfill summary -- never silently dropped from the
parquet, only from the label used for training.

Polite pacing: ~1 req/s (SLEEP_SECONDS between month-page fetches), plain
urllib first. If npb.jp ever bot-walls (403/999/HTML-challenge where a normal
page was expected), escalate via
scripts.platformkit.odds_provider.stealth_fetch.stealth_get_json -- reused,
never reimplemented (this module imports it lazily so a plain urllib success
path never even touches scrapling).

Network isolation: http_get is INJECTABLE; no network at import time.

PRIVATE: data/domains/npb/ is local-only, never git-tracked. No $/edge claim.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_npb/test_ingest_npb.py -q
"""
from __future__ import annotations

import logging
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_TIMEOUT = 15
_SCHEDULE_URL = "https://npb.jp/games/{year}/schedule_{month:02d}_detail.html"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "npb" / "npb_results.parquet"

# Months actually populated with regular-season/Japan-Series games. 12/01/02
# return 200 but are empty off-season shells -- skipped to save a request.
SEASON_MONTHS: tuple = (3, 4, 5, 6, 7, 8, 9, 10, 11)

SLEEP_SECONDS = 1.05  # polite pacing between month-page fetches (~1 req/s)

GAMES_COLS: tuple = (
    "date", "season", "home_team", "away_team",
    "home_score", "away_score", "home_win", "tied",
)

_ROW_RE = re.compile(
    r'<tr id="date(?P<md>\d{4})"[^>]*>(?P<block>.*?)</tr>', re.S
)
_TEAM1_RE = re.compile(r'team1">([^<]*)</div>')
_TEAM2_RE = re.compile(r'team2">([^<]*)</div>')
_SCORE1_RE = re.compile(r'score1">(\d+)</div>')
_SCORE2_RE = re.compile(r'score2">(\d+)</div>')


def _default_http_get(url: str) -> str:
    """Fetch url via urllib and return the decoded HTML body, or "" on error.

    Never raises -- a fetch failure (network, 404, timeout) yields an empty
    string, which _parse_month naturally turns into zero rows.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            log.info("npb.jp 404 (no page) url=%s", url)
        else:
            log.warning("npb.jp fetch failed url=%s status=%s", url, exc.code)
        return ""
    except Exception as exc:  # noqa: BLE001
        log.warning("npb.jp fetch failed url=%s err=%s", url, exc)
        return ""


def _stealth_http_get(url: str) -> str:
    """Escalation path for a bot-walled response: reuses the shared stealth
    fetcher (never reimplemented). Returns "" if scrapling is unavailable or
    the stealth fetch itself fails -- callers degrade to zero rows, not a
    crash."""
    try:
        # stealth_get_json expects/returns JSON; NPB pages are HTML, so we
        # reach one level lower and just get the raw body via its fetcher.
        from scrapling.fetchers import Fetcher
        resp = Fetcher.get(url, impersonate="chrome", timeout=_TIMEOUT)
        body = getattr(resp, "body", None) or getattr(resp, "text", None) or ""
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        return str(body)
    except Exception as exc:  # noqa: BLE001
        log.warning("npb.jp stealth fetch failed url=%s err=%s", url, exc)
        return ""


def _looks_bot_walled(body: str) -> bool:
    """Heuristic: a real npb.jp schedule page always contains the
    schedule_detail container; its absence (non-empty body, but no marker)
    suggests a challenge/interstitial page rather than a genuine empty month."""
    return bool(body) and "schedule_detail" not in body


def _parse_month(body: str, year: str, month: int) -> List[dict]:
    """Parsed completed-game rows from one month's schedule HTML, or [] if the
    page has no rows (off-season shell, 404-turned-empty-string, etc.).

    PURE -- no I/O. A row missing BOTH scores (off-day placeholder or a
    postponed/no-game "cancel" marker) is skipped, never fabricated.
    """
    rows: List[dict] = []
    for m in _ROW_RE.finditer(body):
        md = m.group("md")
        block = m.group("block")
        t1 = _TEAM1_RE.search(block)
        t2 = _TEAM2_RE.search(block)
        s1 = _SCORE1_RE.search(block)
        s2 = _SCORE2_RE.search(block)
        if not (t1 and t2 and s1 and s2):
            continue  # off-day placeholder OR postponed/no-game "cancel" row
        home = t1.group(1).strip()
        away = t2.group(1).strip()
        if not home or not away:
            continue
        home_score = float(s1.group(1))
        away_score = float(s2.group(1))
        tied = home_score == away_score
        rows.append({
            "date": f"{year}-{month:02d}-{md[2:]}",
            "season": str(year),
            "home_team": home, "away_team": away,
            "home_score": home_score, "away_score": away_score,
            "home_win": None if tied else (1.0 if home_score > away_score else 0.0),
            "tied": bool(tied),
        })
    return rows


def fetch_month(
    year: str, month: int, http_get: Optional[Callable] = None,
) -> List[dict]:
    """Parsed completed-game rows for one (year, month), escalating to the
    stealth fetcher if the plain response looks bot-walled (never on a clean
    200/404 -- escalation is the exception path, not the default)."""
    getter = http_get or _default_http_get
    url = _SCHEDULE_URL.format(year=year, month=month)
    body = getter(url)
    if _looks_bot_walled(body) and http_get is None:
        log.info("npb.jp looks bot-walled url=%s -- escalating to stealth", url)
        body = _stealth_http_get(url)
    return _parse_month(body, year, month)


def ingest_season(
    year: str,
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
    months: Sequence[int] = SEASON_MONTHS,
    sleep_seconds: float = SLEEP_SECONDS,
) -> Path:
    """Backfill one NPB *year* across *months*, merged/deduped into the
    parquet at out_path. Dedup key: (date, home_team, away_team) -- a re-run
    with corrected scores overwrites the stale row (keep='last')."""
    out = Path(out_path) if out_path else _DEFAULT_OUT
    getter = http_get or _default_http_get
    rows: List[dict] = []
    for i, month in enumerate(months):
        got = fetch_month(year, month, http_get=getter)
        log.info("season=%s month=%02d games=%d", year, month, len(got))
        rows.extend(got)
        if http_get is None and i < len(months) - 1:
            time.sleep(sleep_seconds)

    new_df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=list(GAMES_COLS))
    if not new_df.empty and "date" in new_df.columns:
        new_df["date"] = pd.to_datetime(new_df["date"], format="mixed", errors="coerce")

    if out.exists() and not new_df.empty:
        try:
            existing = pd.read_parquet(out)
            if "date" in existing.columns:
                existing["date"] = pd.to_datetime(existing["date"], format="mixed", errors="coerce")
            new_df = (pd.concat([existing, new_df], ignore_index=True)
                      .drop_duplicates(subset=["date", "home_team", "away_team"], keep="last"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("S95: unreadable existing parquet %s" % out) from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    if not new_df.empty:
        new_df = new_df.sort_values(
            ["date", "home_team", "away_team"], kind="mergesort"
        ).reset_index(drop=True)
        write_parquet_atomic(new_df, out)
    log.info("Wrote %d rows to %s", len(new_df), out)
    return out


def ingest_seasons(
    years: Sequence[str],
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """Backfill multiple years in sequence into the SAME parquet (dedup across
    the whole call)."""
    out = Path(out_path) if out_path else _DEFAULT_OUT
    for year in years:
        ingest_season(year, http_get=http_get, out_path=out)
    return out


def _main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Ingest npb.jp monthly schedule/results.")
    parser.add_argument("--years", nargs="+", default=["2022", "2023", "2024", "2025", "2026"])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    dest = ingest_seasons(args.years, out_path=args.out)
    df = pd.read_parquet(dest)
    n_tied = int(df["tied"].sum()) if "tied" in df.columns else 0
    print(f"Done: {dest} -- {len(df)} total games across seasons "
          f"{sorted(df['season'].unique().tolist())}; ties={n_tied} "
          f"({n_tied / len(df) * 100:.1f}%)" if len(df) else f"Done: {dest} -- 0 games")
    for s in sorted(df["season"].unique().tolist()) if len(df) else []:
        sub = df[df["season"] == s]
        print(f"  season={s}: {len(sub)} games, {int(sub['tied'].sum())} ties")


if __name__ == "__main__":
    _main()


__all__ = [
    "fetch_month", "ingest_season", "ingest_seasons",
    "SEASON_MONTHS", "SLEEP_SECONDS", "_DEFAULT_OUT", "GAMES_COLS",
]
