"""domains.mlb.ingest_current -- fetch CURRENT MLB results (2022..present) from the
free official MLB Stats API and materialize a games_current.parquet that extends the
frozen 2010-2021 SBR corpus.

The frozen corpus (data/domains/mlb/games.parquet) ends 2021-11-02 -> today's MLB
predictions would otherwise run on ~4.6yr-stale Elo. This module pulls FINAL game
results from statsapi.mlb.com (sportId=1, gameType=R, no API key) and maps the full
team names onto the SAME non-standard SBR 3-letter codes the frozen corpus uses, so
the two corpora concatenate cleanly and the SAME walk_forward_elo replays across both.

This is an INGEST/build module: it writes only to data/domains/mlb/ (gitignored,
local). It does NOT touch the frozen games.parquet and imports nothing from the
frozen pipeline beyond the schema it must match. <=300 LOC.

DATA SOURCE: https://statsapi.mlb.com/api/v1/schedule (free, official, no key).
The endpoint 406s a non-browser UA, so a browser UA header is required.

HONEST: results-only ingest. No odds, no edge claim. Final games only (leak-free:
no in-progress scores). Run: python -m domains.mlb.ingest_current
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

# Full MLB team name -> SBR 3-letter code used by the frozen 2010-2021 corpus.
# The frozen corpus uses these non-standard codes (verified against the 2021 season):
#   CUB=Cubs, SDG=Padres, SFO=Giants, KAN=Royals, TAM=Rays, WAS=Nationals,
#   CWS=White Sox, LAD=Dodgers, CLE=Guardians(was Indians), OAK=Athletics.
NAME_TO_CODE: Dict[str, str] = {
    "Arizona Diamondbacks": "ARI",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CUB",
    "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Cleveland Indians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KAN",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Athletics": "OAK",            # post-2024 rebrand (Sacramento/Las Vegas A's)
    "Oakland Athletics": "OAK",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SDG",
    "San Francisco Giants": "SFO",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TAM",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WAS",
}

# AL/NL league of each SBR code (matches domains/mlb/config.LEAGUE_MAP for the
# 2022+ era; HOU is AL throughout this window).
LEAGUE_OF_CODE: Dict[str, str] = {
    "ARI": "NL", "ATL": "NL", "CUB": "NL", "CIN": "NL", "COL": "NL",
    "LAD": "NL", "MIA": "NL", "MIL": "NL", "NYM": "NL", "PHI": "NL",
    "PIT": "NL", "SDG": "NL", "SFO": "NL", "STL": "NL", "WAS": "NL",
    "BAL": "AL", "BOS": "AL", "CWS": "AL", "CLE": "AL", "DET": "AL",
    "HOU": "AL", "KAN": "AL", "LAA": "AL", "MIN": "AL", "NYY": "AL",
    "OAK": "AL", "SEA": "AL", "TAM": "AL", "TEX": "AL", "TOR": "AL",
}

_REPO = Path(__file__).resolve().parents[2]
_RAW_DIR = _REPO / "data" / "domains" / "mlb" / "_raw" / "statsapi"
_OUT = _REPO / "data" / "domains" / "mlb" / "games_current.parquet"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_BASE = "https://statsapi.mlb.com/api/v1/schedule"

# statuses that mean the game is OVER with a settled result (leak-free)
_FINAL = {"Final", "Game Over", "Completed Early"}


def _fetch_season(year: int, end_date: Optional[dt.date]) -> Path:
    """Curl one season's schedule JSON to the raw dir; return the path.

    WebFetch 406s this API, so we shell out to curl with a browser UA (the only
    reliable path on this box). Cached by year file; re-fetch the current season.
    """
    _RAW_DIR.mkdir(parents=True, exist_ok=True)
    end = f"{year}-12-31"
    if end_date is not None and end_date.year == year:
        end = end_date.isoformat()
    url = (f"{_BASE}?sportId=1&startDate={year}-01-01&endDate={end}"
           f"&gameType=R")
    out = _RAW_DIR / f"sched_{year}.json"
    subprocess.run(
        ["curl", "-s", "-H", f"User-Agent: {_UA}", url, "-o", str(out)],
        check=True,
    )
    return out


def _parse_season(path: Path, end_date: Optional[dt.date]) -> List[dict]:
    """Parse one schedule JSON into game-result rows (FINAL games only)."""
    d = json.loads(path.read_text(encoding="utf-8"))
    rows: List[dict] = []
    seq_by_day: Dict[str, int] = {}
    for day in d.get("dates", []):
        date_str = day["date"]
        gdate = dt.date.fromisoformat(date_str)
        if end_date is not None and gdate > end_date:
            continue
        for g in day.get("games", []):
            state = g.get("status", {}).get("detailedState", "")
            if state not in _FINAL:
                continue
            t = g["teams"]
            hn = t["home"]["team"]["name"]
            an = t["away"]["team"]["name"]
            hs = t["home"].get("score")
            as_ = t["away"].get("score")
            if hs is None or as_ is None or hn not in NAME_TO_CODE or an not in NAME_TO_CODE:
                continue
            home, away = NAME_TO_CODE[hn], NAME_TO_CODE[an]
            seq_by_day[date_str] = seq_by_day.get(date_str, 0) + 1
            rows.append({
                "event_id": f"{date_str}-{home}-{away}-{seq_by_day[date_str]}",
                "date": gdate,
                "season": int(g.get("season", gdate.year)),
                "home_team": home,
                "away_team": away,
                "home_runs": int(hs),
                "away_runs": int(as_),
                "target_home_win": 1 if int(hs) > int(as_) else 0,
                "game_seq": seq_by_day[date_str],
                "home_league": LEAGUE_OF_CODE.get(home, ""),
            })
    return rows


def build_current(
    start_year: int = 2022,
    end_date: Optional[dt.date] = None,
    fetch: bool = True,
) -> "object":
    """Build games_current.parquet for [start_year-01-01 .. end_date] (FINAL games).

    end_date=None (default) resolves to YESTERDAY (dt.date.today() - 1 day) so a
    no-arg call always ingests through "present" -- a frozen literal here
    (formerly dt.date(2026, 6, 16), the authoring date) is exactly what let
    games_current.parquet go 27 days stale silently: every default-arg call kept
    re-stopping at that fixed date forever. Explicit end_date args are unaffected.

    Returns the DataFrame. Schema matches the frozen games.parquet exactly so the
    two concatenate. Writes to data/domains/mlb/games_current.parquet (local).
    """
    import pandas as pd  # noqa: PLC0415

    if end_date is None:
        end_date = dt.date.today() - dt.timedelta(days=1)

    rows: List[dict] = []
    for year in range(start_year, end_date.year + 1):
        path = _RAW_DIR / f"sched_{year}.json"
        if fetch or not path.exists():
            path = _fetch_season(year, end_date)
        rows.extend(_parse_season(path, end_date))

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "home_team", "away_team", "game_seq"]).reset_index(drop=True)
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_OUT, index=False)
    return df


def _main() -> int:
    df = build_current()
    print(f"games_current.parquet: {len(df)} FINAL games")
    print(f"  date range: {df['date'].min().date()} .. {df['date'].max().date()}")
    print(f"  seasons: {sorted(df['season'].unique())}")
    print(f"  teams: {len(set(df['home_team']) | set(df['away_team']))}")
    print(f"  wrote {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
