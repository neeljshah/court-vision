"""golive_discover_game_ids.py — discover tonight's NBA game ids for the box poller.

Called by courtvision_golive.ps1 (G-001) when no explicit -GameId is supplied.
Prints a comma-separated list of zero-padded 10-digit NBA game ids to stdout,
one line.  Exits 0 always (failures write to stderr and print empty string so
the poller starts without crashing go-live).

Discovery order:
  1. games_lookup.json nba_stats_official entries matching the date (fast, offline).
  2. NBA ScoreboardV2 API (network, adds new entries to games_lookup.json).
  3. If both fail, prints "" and logs a warning to stderr.

Usage:
    python scripts/golive_discover_game_ids.py --date 2026-06-03
    python scripts/golive_discover_game_ids.py             # defaults to today ET
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOOKUP = os.path.join(ROOT, "data", "cache", "games_lookup.json")


# ---------------------------------------------------------------------------
# Helpers shared with cv_fix_build_slate.py (kept independent to avoid import)
# ---------------------------------------------------------------------------

def _et_date_of_start(start_time: str) -> str:
    """Convert a UTC start-time string to the NBA schedule ET date.

    NBA evening tips stored as next-UTC-day (e.g. 2026-05-31T00:10Z) belong
    to the prior ET date (2026-05-30).  Approximate ET as UTC-5 (close enough
    for evening-game routing): subtract a day when the UTC hour is < 6.
    """
    try:
        t = _dt.datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ")
        if t.hour < 6:
            t -= _dt.timedelta(days=1)
        return t.strftime("%Y-%m-%d")
    except Exception:
        return start_time[:10]


def _load_lookup() -> dict:
    try:
        with open(LOOKUP, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_lookup(lookup: dict) -> None:
    try:
        with open(LOOKUP, "w", encoding="utf-8") as fh:
            json.dump(lookup, fh, indent=1)
    except Exception as e:
        print(f"[discover] could not save games_lookup: {e}", file=sys.stderr)


def _gids_from_lookup(lookup: dict, date: str) -> list[str]:
    """Return NBA game ids already in games_lookup for *date*."""
    return [
        gid
        for gid, info in lookup.items()
        if info.get("_source") == "nba_stats_official"
        and info.get("home_abbr")
        and info.get("away_abbr")
        and _et_date_of_start(info.get("start_time", "")) == date
    ]


def _fetch_via_scoreboardv2(date: str, lookup: dict) -> list[str]:
    """Query NBA ScoreboardV2, populate games_lookup, return today's gids."""
    sys.path.insert(0, ROOT)
    from src.data import nba_api_headers_patch  # noqa: F401
    from nba_api.stats.endpoints import scoreboardv2
    from nba_api.stats.static import teams as _teams

    id2abbr = {t["id"]: t["abbreviation"] for t in _teams.get_teams()}
    sb = scoreboardv2.ScoreboardV2(game_date=date, timeout=45)
    gh = sb.game_header.get_data_frame()

    gids: list[str] = []
    added = 0
    for _, r in gh.iterrows():
        gid = str(r["GAME_ID"])
        home = id2abbr.get(int(r["HOME_TEAM_ID"]), "")
        away = id2abbr.get(int(r["VISITOR_TEAM_ID"]), "")
        if not (home and away):
            continue
        if gid not in lookup:
            est = str(r.get("GAME_DATE_EST", ""))[:10] or date
            try:
                utc_day = (
                    _dt.datetime.strptime(est, "%Y-%m-%d") + _dt.timedelta(days=1)
                ).strftime("%Y-%m-%d")
            except Exception:
                utc_day = est
            lookup[gid] = {
                "home_abbr": home,
                "away_abbr": away,
                "start_time": f"{utc_day}T00:10:00Z",
                "label": f"{away} @ {home}",
                "_source": "nba_stats_official",
            }
            added += 1
        gids.append(gid)

    if added:
        _save_lookup(lookup)
        print(f"[discover] ScoreboardV2 added {added} game(s) to games_lookup", file=sys.stderr)

    return gids


def discover(date: str) -> str:
    """Return comma-separated NBA game ids for *date*, or empty string."""
    lookup = _load_lookup()

    # Pass 1 — lookup cache (fast, offline)
    gids = _gids_from_lookup(lookup, date)

    # Pass 2 — ScoreboardV2 (network, updates cache)
    if not gids:
        try:
            gids = _fetch_via_scoreboardv2(date, lookup)
        except Exception as e:
            print(f"[discover] ScoreboardV2 fallback failed: {e}", file=sys.stderr)

    # Deduplicate while preserving insertion order
    seen: dict[str, None] = {}
    for g in gids:
        seen[g] = None
    unique = list(seen)

    if not unique:
        print(
            f"[discover] WARNING: no NBA games found for {date} in games_lookup or "
            "ScoreboardV2; box_snapshot_poller will idle",
            file=sys.stderr,
        )
        return ""

    return ",".join(unique)


def _today_et() -> str:
    """Today's date in ET (approximate: UTC-5)."""
    return (_dt.datetime.utcnow() - _dt.timedelta(hours=5)).strftime("%Y-%m-%d")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--date",
        default=_today_et(),
        help="NBA slate date YYYY-MM-DD (default: today ET)",
    )
    args = ap.parse_args(argv)
    result = discover(args.date)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
