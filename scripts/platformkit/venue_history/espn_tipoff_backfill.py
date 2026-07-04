"""scripts.platformkit.venue_history.espn_tipoff_backfill -- fills the
2023-2024 tipoff-time gap in nba_close_corpus.py's CommenceIndex.

WHY: the only on-disk tipoff-time-of-day reference (data/cache/odds_api/
historical_events/*.json) starts 2024-11-15 -- see nba_close_corpus.py's
module docstring. games.parquet and every other domains/basketball_nba/*
parquet checked (games, espn_boxscores, linescores, odds) carry DATE ONLY, no
clock -- confirmed on-disk 2026-07-04, so candidate (1) (an on-disk artifact)
is genuinely exhausted, not skipped. This module is candidate (2): a keyless
ESPN historical scoreboard fetch (site.api.espn.com), politely bounded to just
the unique slate-dates the 2023 Polymarket pilot actually needs (~93 dates,
one request each, paced), cached to disk so a re-run never re-fetches.

ESPN's `scoreboard?dates=YYYYMMDD` buckets games by the SAME local slate date
convention our PM docs use (verified live 2026-07-04: date "20230223" returns
the 9-game 2023-02-23 slate, not a UTC-midnight-boundary slate), and each
event carries an explicit `homeAway` competitor split plus a real UTC start
timestamp in `date` -- exactly the tipoff-time reference CommenceIndex needs,
sourced independently of the odds_api cache.

HONESTY: a PM-pilot date with no cached/fetchable ESPN scoreboard, or whose
game does not appear in that day's ESPN slate, contributes NOTHING and is
counted by the caller as `no_commence_time_reference` -- exactly like today's
odds_api-only path. No fabricated midnight tips, ever.

OUTPUT (cache): data/cache/venue_history/espn_scoreboard/nba/<yyyymmdd>.json
(raw ESPN response, one file per date, keyed so a partial run resumes free).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/venue_history/test_espn_tipoff_backfill.py -q
"""
from __future__ import annotations

import glob
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit.odds_provider.team_resolver import canonical

_REPO_ROOT = Path(__file__).resolve().parents[3]
PM_NBA_2023 = _REPO_ROOT / "data" / "venue_history" / "polymarket" / "nba"
ESPN_CACHE_DIR = _REPO_ROOT / "data" / "cache" / "venue_history" / "espn_scoreboard" / "nba"
_UA = "Mozilla/5.0 (compatible; CourtVisionResearch/1.0)"
_PACE_SEC = 1.0
_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={yyyymmdd}"


def dates_needed_from_pm_pilot(directory: Path = PM_NBA_2023) -> List[str]:
    """Unique yyyymmdd slate dates the 2023 PM pilot's filenames carry (the
    filename's leading YYYY-MM-DD IS the slate date, same convention ESPN's
    `dates=` param buckets by -- see module docstring)."""
    out: set = set()
    for fp in sorted(glob.glob(str(directory / "*.jsonl"))):
        stem = Path(fp).stem
        d = stem[:10]
        if len(d) == 10 and d[4] == "-" and d[7] == "-":
            out.add(d.replace("-", ""))
    return sorted(out)


def _cache_path(yyyymmdd: str, cache_dir: Path) -> Path:
    return cache_dir / f"{yyyymmdd}.json"


def _fetch_scoreboard(yyyymmdd: str) -> Optional[Dict[str, Any]]:
    """One live ESPN scoreboard fetch. None on any network/parse failure --
    caller counts this as an honest miss, never a fabricated fallback."""
    req = urllib.request.Request(_SCOREBOARD_URL.format(yyyymmdd=yyyymmdd), headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError):
        return None


def ensure_cached(dates: List[str], *, cache_dir: Path = ESPN_CACHE_DIR,
                  pace_sec: float = _PACE_SEC) -> Dict[str, int]:
    """Fetch + cache every date in *dates* not already on disk. Returns
    {"fetched": n, "already_cached": n, "fetch_failed": n}. Idempotent -- a
    second run with the same dates fetches nothing new."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    counts = {"fetched": 0, "already_cached": 0, "fetch_failed": 0}
    for yyyymmdd in dates:
        dest = _cache_path(yyyymmdd, cache_dir)
        if dest.exists():
            counts["already_cached"] += 1
            continue
        doc = _fetch_scoreboard(yyyymmdd)
        if doc is None:
            counts["fetch_failed"] += 1
            continue
        dest.write_text(json.dumps(doc), encoding="utf-8")
        counts["fetched"] += 1
        time.sleep(pace_sec)
    return counts


@dataclass
class EspnCommenceIndex:
    """Cached ESPN scoreboard JSON -> same shape/contract as
    nba_close_corpus.CommenceIndex: {frozenset(pair): [(commence_dt, home, away)]}.
    A distinct source (not odds_api), used only to fill the pre-2024-11-15 gap."""

    by_pair: Dict[frozenset, List[Tuple[datetime, str, str]]] = field(default_factory=dict)
    n_events: int = 0

    @classmethod
    def load(cls, cache_dir: Path = ESPN_CACHE_DIR) -> "EspnCommenceIndex":
        idx: Dict[frozenset, List[Tuple[datetime, str, str]]] = {}
        n = 0
        for fp in sorted(glob.glob(str(cache_dir / "*.json"))):
            try:
                doc = json.loads(Path(fp).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for e in doc.get("events", []) or []:
                ct = _parse_ts(e.get("date", ""))
                if ct is None:
                    continue
                comps = (e.get("competitions") or [{}])[0].get("competitors") or []
                home = next((c.get("team", {}).get("displayName", "") for c in comps
                            if c.get("homeAway") == "home"), "")
                away = next((c.get("team", {}).get("displayName", "") for c in comps
                            if c.get("homeAway") == "away"), "")
                if not home or not away:
                    continue
                key = frozenset([canonical("nba", home), canonical("nba", away)])
                idx.setdefault(key, []).append((ct, home, away))
                n += 1
        return cls(idx, n)

    def match(self, date_str: str, team_a: str, team_b: str, *,
             tol_days: int = 2) -> Optional[datetime]:
        key = frozenset([canonical("nba", team_a), canonical("nba", team_b)])
        cands = self.by_pair.get(key, [])
        if not cands:
            return None
        try:
            gdate = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        best, best_gap = None, None
        for ct, _h, _a in cands:
            gap = abs((ct - gdate).total_seconds())
            if gap <= tol_days * 86400 and (best_gap is None or gap < best_gap):
                best, best_gap = ct, gap
        return best


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def backfill_2023_pilot(*, pm_dir: Path = PM_NBA_2023, cache_dir: Path = ESPN_CACHE_DIR,
                        pace_sec: float = _PACE_SEC) -> Dict[str, Any]:
    """One-shot: find the dates the 2023 PM pilot needs, fetch+cache any
    missing ESPN scoreboards, return a report + the built EspnCommenceIndex."""
    dates = dates_needed_from_pm_pilot(pm_dir)
    counts = ensure_cached(dates, cache_dir=cache_dir, pace_sec=pace_sec)
    idx = EspnCommenceIndex.load(cache_dir)
    return {
        "n_dates_needed": len(dates), "n_events_indexed": idx.n_events,
        **counts, "cache_dir": str(cache_dir),
        "note": ("ESPN scoreboard tipoff-time backfill for the 2023 PM pilot "
                 "window -- candidate (2) per nba_close_corpus.py's gap note; "
                 "a date with no fetchable/matching event contributes nothing "
                 "and stays an honest no_commence_time_reference exclusion"),
    }


def _main() -> int:
    rep = backfill_2023_pilot()
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
