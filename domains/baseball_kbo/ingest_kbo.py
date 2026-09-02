"""domains.baseball_kbo.ingest_kbo -- koreabaseball.com GetScheduleList scraper.

SOLVED RECIPE (prior wave; followed exactly, recorded so it is never
re-discovered): POST
https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList with headers
User-Agent=<real browser UA>,
Content-Type=application/x-www-form-urlencoded; charset=UTF-8,
Referer=https://www.koreabaseball.com/Schedule/Schedule.aspx. Body
form-urlencoded (NOT JSON -- JSON returns 401): leId=1, srIdList=0,9,6
(regular season), seasonId=YYYY, gameMonth=MM, teamId= (empty -- REQUIRED;
omitting it 500s with body text "parameter missing. teamId"). The Referer is
LOAD-BEARING: without it the endpoint returns HTTP 200 with an HTML error
page (NOT a 4xx) -- CHECK THE BODY PARSES AS JSON, never trust the status
code alone; a non-JSON 200 degrades to zero rows, never a crash.

WHOLE-SEASON SHORTCUT (verified live 2026-07-04): gameMonth='' returns the
ENTIRE season in ONE request (2025-05 alone: 147 games via gameMonth='05';
gameMonth='' for the same season: 804 play-cells spanning 03.22-10.04). Tried
FIRST by default; months=SEASON_MONTHS forces the per-month loop.

Response shape: JSON {"rows": [...]}, each a row-group {"row": [cell, ...]}.
A multi-game day has ONE cell with Class=="day" shared by that day's first
row-group; subsequent row-groups OMIT the day cell (RowSpan-merge) -- date
CARRIES FORWARD, never re-derived. The game lives in the Class=="play" cell:
  "<span>AWAY</span><em><span class=X>N</span><span>vs</span>
   <span class=Y>M</span></em><span>HOME</span>"
X/Y in {"win","lose","same"} ("same" on both = a tie). AWAY is the FIRST
outer <span>, HOME is the LAST (verified: "KT vs Doosan" at Jamsil, Doosan's
home park, confirms KT=away/Doosan=home).

POSTPONED/UNPLAYED (excluded, never fabricated): a "play" cell for an
incomplete game has NO score spans -- "<span>AWAY</span><em><span>vs</span>
</em><span>HOME</span>" -- skipped entirely (84/804 2025-season play-cells).

TIES: KBO games can end level (extra-inning curfew). Both score spans
class=="same" -> home_win=None, EXCLUDED from win-prob training but COUNTED,
never silently dropped. EXCEPTION -- an in-progress/not-final game renders
the SAME same/same markup but with both scores exactly 0 (found live
2026-07-04: 5/5 today's games, still playing; 0 real 0-0 ties exist across
the 3255-row historical parquet) -- 0-0/same/same is "not final yet", so it
is skipped, not fabricated as a tie. A real tie (e.g. 3-3) is unaffected.

Depth floor: seasonId=2001 returns real games; seasonId=2000 returns a valid
empty {"rows": []} (not an error) -- backfills 2022..2026 per lane scope.

Polite pacing ~1.05s between requests, plain urllib only (never observed to
bot-wall). Network isolation: http_get is INJECTABLE; no network at import.

PRIVATE: data/domains/kbo/ is local-only, never git-tracked. No $/edge claim.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_kbo/test_ingest_kbo.py -q
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd

from domains.baseball_kbo.team_map import normalize_team
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_TIMEOUT = 15
_URL = "https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList"
_REFERER = "https://www.koreabaseball.com/Schedule/Schedule.aspx"
_LE_ID = "1"
_SR_ID_LIST = "0,9,6"  # regular season series ids

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "kbo" / "kbo_results.parquet"

# Months actually populated with games (KBO regular season runs late-March
# through early-October). Only used by the per-month FALLBACK path -- the
# default path uses gameMonth='' (whole season in one request).
SEASON_MONTHS: tuple = (3, 4, 5, 6, 7, 8, 9, 10)

SLEEP_SECONDS = 1.05  # polite pacing between requests (~1 req/s)

GAMES_COLS: tuple = ("date", "season", "home_team", "away_team",
                     "home_score", "away_score", "home_win", "tied")

# "<span>AWAY</span><em><span class=X>N</span><span>vs</span><span class=Y>M</span></em><span>HOME</span>"
_PLAY_SCORED_RE = re.compile(
    r'<span>(?P<away>[^<]*)</span>'
    r'<em><span class="(?P<xc>win|lose|same)">(?P<as_>\d+)</span>'
    r'<span>vs</span>'
    r'<span class="(?P<yc>win|lose|same)">(?P<hs>\d+)</span></em>'
    r'<span>(?P<home>[^<]*)</span>'
)
_DAY_LABEL_RE = re.compile(r'^(?P<mm>\d{2})\.(?P<dd>\d{2})')


def _default_http_get(url: str, body: str) -> str:
    """POST *body* (already form-urlencoded) to *url* and return the decoded
    response text, or "" on error. Never raises."""
    req = urllib.request.Request(
        url, data=body.encode("utf-8"), method="POST",
        headers={"User-Agent": _UA,
                 "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                 "Referer": _REFERER},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        log.warning("koreabaseball.com fetch failed url=%s status=%s", url, exc.code)
        try:
            return exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return ""
    except Exception as exc:  # noqa: BLE001
        log.warning("koreabaseball.com fetch failed url=%s err=%s", url, exc)
        return ""


def _is_json_body(body: str) -> bool:
    """True iff *body* parses as JSON -- the load-bearing check that catches a
    200-with-HTML-error-page response (missing Referer, etc.)."""
    if not body:
        return False
    try:
        json.loads(body)
        return True
    except (ValueError, TypeError):
        return False


def _parse_schedule(body: str, season: str) -> List[dict]:
    """Parsed completed-game rows from one response body, or [] if not valid
    JSON / no rows. PURE -- no I/O. A "play" cell missing the win/lose/same
    score-span pattern (postponed/unplayed) is skipped. Date carries forward
    from the last-seen "day" cell (RowSpan-merge: later row-groups of a
    multi-game day omit the day cell entirely)."""
    if not _is_json_body(body):
        return []
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return []

    rows = data.get("rows", []) if isinstance(data, dict) else []
    out: List[dict] = []
    cur_month: Optional[int] = None
    cur_day: Optional[int] = None

    for rg in rows:
        cells = rg.get("row", []) if isinstance(rg, dict) else []
        for cell in cells:
            cls = cell.get("Class")
            text = cell.get("Text", "") or ""
            if cls == "day":
                m = _DAY_LABEL_RE.match(text)
                if m:
                    cur_month = int(m.group("mm"))
                    cur_day = int(m.group("dd"))
            elif cls == "play":
                if cur_month is None or cur_day is None:
                    continue  # no day context yet -- skip rather than guess
                m = _PLAY_SCORED_RE.search(text)
                if not m:
                    continue  # postponed/unplayed -- no score spans at all
                away = normalize_team(m.group("away"))
                home = normalize_team(m.group("home"))
                if not away or not home:
                    continue
                away_score = float(m.group("as_"))
                home_score = float(m.group("hs"))
                tied = (m.group("xc") == "same") and (m.group("yc") == "same")
                if tied and away_score == 0.0 and home_score == 0.0:
                    continue  # in-progress/not-yet-final placeholder, not a real 0-0 tie
                out.append({
                    "date": f"{season}-{cur_month:02d}-{cur_day:02d}",
                    "season": str(season),
                    "home_team": home, "away_team": away,
                    "home_score": home_score, "away_score": away_score,
                    "home_win": None if tied else (1.0 if home_score > away_score else 0.0),
                    "tied": bool(tied),
                })
    return out


def _build_body(season: str, game_month: str) -> str:
    params = {"leId": _LE_ID, "srIdList": _SR_ID_LIST,
              "seasonId": str(season), "gameMonth": game_month, "teamId": ""}
    return urllib.parse.urlencode(params)


def fetch_season_whole(season: str, http_get: Optional[Callable] = None) -> List[dict]:
    """Whole-season fetch via gameMonth='' (single request). Returns []
    (never raises) if the response is not valid JSON."""
    getter = http_get or _default_http_get
    body = getter(_URL, _build_body(season, ""))
    return _parse_schedule(body, season)


def fetch_month(season: str, month: int, http_get: Optional[Callable] = None) -> List[dict]:
    """One (season, month) fetch -- the fallback path if the whole-season
    shortcut is ever unavailable."""
    getter = http_get or _default_http_get
    body = getter(_URL, _build_body(season, f"{month:02d}"))
    return _parse_schedule(body, season)


def ingest_season(season: str, http_get: Optional[Callable] = None,
                   out_path: Optional[Path] = None, months: Optional[Sequence[int]] = None,
                   sleep_seconds: float = SLEEP_SECONDS, whole_season_first: bool = True) -> Path:
    """Backfill one KBO *season* into the parquet at out_path (dedup key:
    date+home_team+away_team, keep='last'). Default: ONE request via
    gameMonth='' (whole_season_first=True); falls back to the per-month loop
    over SEASON_MONTHS if that returns zero rows and months is None. Passing
    months explicitly forces the per-month loop regardless."""
    out = Path(out_path) if out_path else _DEFAULT_OUT
    getter = http_get or _default_http_get

    rows: List[dict] = []
    if months is None and whole_season_first:
        rows = fetch_season_whole(season, http_get=getter)
        log.info("season=%s whole-season fetch games=%d", season, len(rows))
    if not rows:
        use_months = months if months is not None else SEASON_MONTHS
        for i, month in enumerate(use_months):
            got = fetch_month(season, month, http_get=getter)
            log.info("season=%s month=%02d games=%d", season, month, len(got))
            rows.extend(got)
            if http_get is None and i < len(use_months) - 1:
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
            ["date", "home_team", "away_team"], kind="mergesort").reset_index(drop=True)
        write_parquet_atomic(new_df, out)
    log.info("Wrote %d rows to %s", len(new_df), out)
    return out


def ingest_seasons(seasons: Sequence[str], http_get: Optional[Callable] = None,
                    out_path: Optional[Path] = None) -> Path:
    """Backfill multiple seasons in sequence into the SAME parquet (dedup
    across the whole call). ~1.05s pacing between seasons (whole-season path
    is one request per season, so this is the only inter-season pause)."""
    out = Path(out_path) if out_path else _DEFAULT_OUT
    getter = http_get or _default_http_get
    for i, season in enumerate(seasons):
        ingest_season(season, http_get=getter, out_path=out)
        if http_get is None and i < len(seasons) - 1:
            time.sleep(SLEEP_SECONDS)
    return out


def _main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Ingest koreabaseball.com GetScheduleList.")
    parser.add_argument("--seasons", nargs="+", default=["2022", "2023", "2024", "2025", "2026"])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    dest = ingest_seasons(args.seasons, out_path=args.out)
    df = pd.read_parquet(dest)
    if not len(df):
        print(f"Done: {dest} -- 0 games")
        return
    n_tied = int(df["tied"].sum()) if "tied" in df.columns else 0
    print(f"Done: {dest} -- {len(df)} total games across seasons "
          f"{sorted(df['season'].unique().tolist())}; ties={n_tied} "
          f"({n_tied / len(df) * 100:.1f}%)")
    for s in sorted(df["season"].unique().tolist()):
        sub = df[df["season"] == s]
        print(f"  season={s}: {len(sub)} games, {int(sub['tied'].sum())} ties")


if __name__ == "__main__":
    _main()


__all__ = ["fetch_season_whole", "fetch_month", "ingest_season", "ingest_seasons",
           "SEASON_MONTHS", "SLEEP_SECONDS", "_DEFAULT_OUT", "GAMES_COLS"]
