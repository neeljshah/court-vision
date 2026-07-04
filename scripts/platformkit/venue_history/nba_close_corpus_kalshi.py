"""scripts.platformkit.venue_history.nba_close_corpus_kalshi -- Kalshi-side
builder for the NBA pregame CLOSE corpus (split out of nba_close_corpus.py to
stay under the per-file LOC budget; same module family, same invariants).

Kalshi's data/venue_history/kalshi/nba/*.jsonl are per-SIDE ticker files
(KXNBAGAME-<YY><MON><DD><AWAY+HOME concatenated>-<SIDE>.jsonl, one file per
side of each of the 53 distinct 2026-playoff events = 106 files). This module
parses each ticker via ingame.nba_outcome_resolver.parse_nba_ticker (read-only
reuse, no edits to that gated file), resolves the AWAY+HOME concatenated tail
against our own games.parquet-derived ScheduleIndex (tries every 2-way split,
keeps only a UNIQUE match -- an ambiguous/no-match split is an honest
exclusion, never a guess -- mirrors nba_outcome_resolver._split_tail), then
applies the same last-tick-before-commence_time close rule as the Polymarket
side (see nba_close_corpus.py's CLOSE DEFINITION note).

INVARIANTS: platformkit-only; <=300 LOC; ASCII only; offline; no data/registry
writes; no flag flips; no $-edge claims.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/venue_history/test_nba_close_corpus.py -q
"""
from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit.odds_provider.team_resolver import canonical
from scripts.platformkit.venue_history.nba_close_corpus import (
    CommenceIndex, ScheduleIndex, _last_tick_before,
)


def match_tail_to_schedule(tail: str, date_str: str, sched: ScheduleIndex
                           ) -> Optional[Tuple[str, str, str, Optional[float]]]:
    """Resolve a Kalshi AWAY+HOME concatenated tail against games.parquet by
    trying every 2-way split and keeping the unique split whose (unordered)
    pair matches a scheduled game on/near *date_str*. None on 0 or >=2
    matches -- never a guess (mirrors nba_outcome_resolver._split_tail)."""
    good = []
    for i in range(2, len(tail) - 1):
        a, h = tail[:i], tail[i:]
        m = sched.match(date_str, a, h)
        if m is not None:
            good.append(m)
    uniq = {(g[1], g[3]) for g in good}
    if len(uniq) != 1:
        return None
    m = good[0]
    return m[1], m[2], m[3], m[4]


def build_from_kalshi(directory: Path, sched: ScheduleIndex, comm: CommenceIndex,
                      exclusions: Dict[str, int]) -> List[Dict[str, Any]]:
    """One row per Kalshi NBA ticker file that resolves to a scheduled game
    AND has a commence_time reference AND has a tick strictly before it.
    Everything else is an honest, counted exclusion."""
    from scripts.platformkit.ingame.nba_outcome_resolver import parse_nba_ticker  # noqa: PLC0415

    rows: List[Dict[str, Any]] = []
    for fp in sorted(glob.glob(str(directory / "*.jsonl"))):
        try:
            text = Path(fp).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not text:
            continue
        try:
            doc = json.loads(text.splitlines()[0])
        except (json.JSONDecodeError, IndexError):
            continue
        ticker = str(doc.get("ticker", ""))
        parsed = parse_nba_ticker(ticker)
        if parsed is None:
            exclusions["kalshi_unparseable_ticker"] += 1
            continue
        gdate, tail, _ = parsed
        date_str = gdate.strftime("%Y-%m-%d")
        sched_pair = match_tail_to_schedule(tail, date_str, sched)
        if sched_pair is None:
            exclusions["no_schedule_match"] += 1
            continue
        game_id, real_home, real_away, home_win = sched_pair
        commence = comm.match(date_str, real_home, real_away)
        if commence is None:
            exclusions["no_commence_time_reference"] += 1
            continue
        candles = doc.get("candles") or []
        tick = _last_tick_before(candles, commence, "prob")
        if tick is None:
            exclusions["no_tick_before_tipoff"] += 1
            continue
        ts, p_side = tick
        this_team = ticker.rsplit("-", 1)[-1]
        flip = canonical("nba", this_team) != canonical("nba", real_home)
        close_prob_home = round(1.0 - p_side, 4) if flip else round(p_side, 4)
        rows.append({
            "game_id": game_id, "date": date_str, "home_team": real_home,
            "away_team": real_away, "home_win": home_win, "venue": "kalshi",
            "corpus_id": "kalshi_nba_playoffs_2026", "close_kind": "last_tick_before_commence",
            "close_ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "close_prob_home": close_prob_home,
            "commence_time": commence.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seconds_before_tip": round((commence - ts).total_seconds(), 1),
            "validation_only": True,
        })
    return rows


__all__ = ["build_from_kalshi", "match_tail_to_schedule"]
