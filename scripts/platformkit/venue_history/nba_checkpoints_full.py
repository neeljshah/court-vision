"""scripts.platformkit.venue_history.nba_checkpoints_full -- NBA in-game
checkpoint corpus at SCALE: generalizes nba_wallclock_join's Kalshi-playoff
join (53 games) to the full Polymarket nba_2024plus archive (~1,688 games,
2024-11..2026-06, regular season + playoffs, two seasons).

REUSE, not reinvention: this module wraps nba_wallclock_join's ESPN
wallclock-state fetch/cache (fetch_states_for_event, _espn_events_for_date,
same on-disk RAW_CACHE -- resumable, shared with the playoff corpus) and its
pure join_game_states()/assemble_output() (same schema, same int64 casting,
same no-future-leak merge_asof). The only new logic here is (1) matching a
Polymarket game doc to an ESPN event by TEAM NAME instead of by Kalshi
ticker, and (2) reshaping PM price ticks into the same candle shape Kalshi
candles already use.

TEAM-NAME MATCH: PM docs carry full names ("Knicks", "Celtics"), not
tricodes. domains.basketball_nba.team_name_resolver.resolve() already maps
every ESPN displayName/abbreviation form to the SAME tricode space
espn_nba_bridge._norm_abbr() normalizes ESPN scoreboard abbreviations into
(GSW/NOP/NYK/SAS/UTA/WAS). A name that fails to resolve is honestly
excluded (unmatched_team_name), never guessed.

HOME/AWAY SWAP (measured, not assumed): the PM archive's home/away labels
are systematically INVERTED vs the real venue -- every distinct doc tested
against the cached ESPN scoreboards 2026-07-09: 0 matched as-is, 1603
matched flipped, 4 ambiguous (same matchup twice inside the +/-1-day
window, honestly excluded). The docs are internally consistent with their
own labels (prob_home and outcome_home_win both track the doc's "home"
team), so when the flipped orientation matches, market_prob (1-prob_home)
and outcome_home_win (1-outcome) are flipped TOGETHER to the real home
team -- preserving the schema invariant that market_prob, score_home and
outcome_home_win all reference the same side. Orientation is detected PER
DOC, never hardcoded.

WALLCLOCK COVERAGE: probed live 2026-07-09, event 401704627 (2024-10-22,
BOS@NY, opening night of the PM window) -- 390/390 ESPN summary plays carry
a wallclock field. Full 2024plus window has ESPN wallclock; no
NEEDS_OTHER_SOURCE season band exists for this corpus.

OUTPUT: data/cache/inplay_odds/nba_checkpoints_full.parquet -- SAME columns
as nba_checkpoints_2025_26_playoffs.parquet (game_id, game_date, ts, period,
game_clock_s, score_home, score_away, margin, market_ticker, market_prob,
traded, outcome_home_win) PLUS venue='polymarket'. market_ticker holds the
PM market_slug (no Kalshi ticker exists for this venue). traded is always
True -- Polymarket's price-history endpoint carries no traded/stale flag,
unlike Kalshi's candles (documented, not fabricated).

CALIBRATION substrate only -- no $ field, no edge claim; a join, not a model.
INVARIANTS: platformkit-only; <=300 LOC; ASCII only; local commits only;
never writes data/registry/; never flips a flag; venue_history/ read-only
(only this module's own ESPN cache dir, shared with nba_wallclock_join,
is written).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/venue_history/test_nba_checkpoints_full.py -q
CLI: python -m scripts.platformkit.venue_history.nba_checkpoints_full
"""
from __future__ import annotations

import glob
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from domains.basketball_nba.team_name_resolver import resolve as resolve_team_name
from scripts.platformkit.venue_history.nba_wallclock_join import (
    _espn_events_for_date,
    assemble_output,
    fetch_states_for_event,
    join_game_states,
)

log = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[3]
PM_DIR = _REPO / "data" / "venue_history" / "polymarket" / "nba_2024plus"
OUT_PATH = _REPO / "data" / "cache" / "inplay_odds" / "nba_checkpoints_full.parquet"


def load_pm_docs(directory: Path = PM_DIR) -> List[dict]:
    """One dict per DISTINCT PM game (event_slug-deduped: the archive
    repeats 575 docs verbatim across date-files) across every date-file in
    *directory*. A malformed line is skipped, never raises."""
    docs: List[dict] = []
    seen: set = set()
    for fp in sorted(glob.glob(str(directory / "*.jsonl"))):
        try:
            text = Path(fp).read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.strip().splitlines():
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = doc.get("event_slug")
            if key is not None and key in seen:
                continue
            seen.add(key)
            docs.append(doc)
    return docs


def resolve_teams(doc: dict) -> Optional[Tuple[str, str]]:
    """PM doc's full-name home/away -> (away_tricode, home_tricode) via the
    existing team_name_resolver. None if either side fails to resolve --
    honestly excluded, never guessed."""
    home = resolve_team_name(str(doc.get("home") or ""))
    away = resolve_team_name(str(doc.get("away") or ""))
    if home is None or away is None:
        return None
    return away, home


def pm_candles(doc: dict, flip: bool = False) -> List[dict]:
    """PM prices [{ts, prob_home}] -> the candle shape join_game_states()
    already expects ({ts, prob, traded}). *flip* re-orients prob to the REAL
    home team when the doc's labels are inverted (see module docstring).
    traded=True always -- PM's price-history carries no traded/stale flag
    (documented, not fabricated)."""
    out = []
    for p in doc.get("prices") or []:
        if not isinstance(p, dict):
            continue
        prob = p.get("prob_home")
        if flip and prob is not None:
            prob = 1.0 - float(prob)
        out.append({"ts": p.get("ts"), "prob": prob, "traded": True})
    return out


AMBIGUOUS = "AMBIGUOUS"


def resolve_event_id_by_teams(date_str: str, away: str, home: str) -> Any:
    """ESPN event_id for a (date, away, home) tricode triple, trying the PM
    doc's own date then +/-1 day, checking BOTH orientations per date (the
    archive's labels are inverted -- see module docstring). Returns
    (event_id, flipped_bool, day_delta) on a unique match, AMBIGUOUS when
    both orientations match the same date (a rematch inside the window,
    honestly excluded), None on no match. day_delta lets the caller prefer
    the exact-date doc when the archive lists one game under two dates."""
    try:
        base = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
    for delta in (0, -1, 1):
        idx = _espn_events_for_date((base + timedelta(days=delta)).strftime("%Y%m%d"))
        as_is, flipped = idx.get((away, home)), idx.get((home, away))
        if as_is is not None and flipped is not None:
            return AMBIGUOUS
        if as_is is not None:
            return as_is, False, delta
        if flipped is not None:
            return flipped, True, delta
    return None


def season_label(date_str: str) -> str:
    """'2024-10-22' -> '2024-25' (NBA season runs Aug-June; month<8 belongs
    to the season that started the previous calendar year)."""
    try:
        y, m = int(date_str[:4]), int(date_str[5:7])
    except (ValueError, IndexError, TypeError):
        return "unknown"
    start = y if m >= 8 else y - 1
    return f"{start}-{str(start + 1)[-2:]}"


@dataclass
class _Counters:
    games_total: int = 0
    unmatched_team_name: int = 0
    unresolved_outcome: int = 0
    ambiguous_orientation: int = 0
    no_espn_event_match: int = 0
    empty_pbp: int = 0
    no_candle_overlap: int = 0
    duplicate_game_doc: int = 0
    games_flipped: int = 0
    games_joined: int = 0

    def as_dict(self) -> Dict[str, int]:
        return dict(self.__dict__)


def build_checkpoints(directory: Path = PM_DIR) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Full pipeline: load PM docs -> resolve team names -> resolve ESPN
    event -> fetch wallclock states (cached, resumable) -> merge_asof-join to
    PM price ticks. Returns (checkpoints_df, exclusion_counters)."""
    docs = load_pm_docs(directory)
    c = _Counters(games_total=len(docs))
    # game_id -> (sort_key, frame, flipped); the archive lists a few games
    # under two adjacent dates -- keep ONE doc per real game, preferring the
    # exact-date match (delta 0), then the flipped orientation (the archive
    # norm; an as-is match on a shifted day is a rematch artifact).
    best: Dict[int, Tuple[Tuple[int, int], pd.DataFrame, bool]] = {}

    for doc in docs:
        pair = resolve_teams(doc)
        if pair is None:
            c.unmatched_team_name += 1
            continue
        away, home = pair
        outcome = doc.get("outcome_home_win")
        if outcome not in (0, 1):
            c.unresolved_outcome += 1
            continue
        date = str(doc.get("date") or "")
        res = resolve_event_id_by_teams(date, away, home)
        if isinstance(res, str):  # AMBIGUOUS sentinel
            c.ambiguous_orientation += 1
            continue
        if res is None:
            c.no_espn_event_match += 1
            continue
        eid, flipped, delta = res
        states = fetch_states_for_event(eid)
        if not states:
            c.empty_pbp += 1
            continue
        joined = join_game_states(states, pm_candles(doc, flip=flipped))
        if joined.empty:
            c.no_candle_overlap += 1
            continue
        slug = str(doc.get("market_slug") or doc.get("event_slug") or "")
        real_outcome = (1 - int(outcome)) if flipped else int(outcome)
        out = assemble_output(joined, int(eid), date, slug, real_outcome)
        out["venue"] = "polymarket"
        key = (abs(int(delta)), 0 if flipped else 1)
        gid = int(eid)
        if gid in best:
            c.duplicate_game_doc += 1
            if key >= best[gid][0]:
                continue
        best[gid] = (key, out, flipped)

    if not best:
        return pd.DataFrame(), c.as_dict()
    c.games_joined = len(best)
    c.games_flipped = sum(int(f) for _, _, f in best.values())
    return (pd.concat([f for _, f, _ in best.values()], ignore_index=True),
            c.as_dict())


def write(out_path: Path = OUT_PATH, directory: Path = PM_DIR) -> Tuple[Path, Dict[str, int]]:
    df, counters = build_checkpoints(directory)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not df.empty:
        df.to_parquet(out_path, index=False)
    return out_path, counters


def games_per_season(df: pd.DataFrame) -> Dict[str, int]:
    """Distinct game_id count per NBA season, for an honest per-season
    report (never claims a bucket that has zero rows)."""
    if df.empty:
        return {}
    seasons = df["game_date"].astype(str).apply(season_label)
    return (pd.Series(df["game_id"].values, index=seasons)
            .groupby(level=0).nunique().to_dict())


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    path, counters = write()
    df = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    print(f"RESULT {counters} -> {path}")
    print(f"rows={len(df)} games_per_season={games_per_season(df)}")


if __name__ == "__main__":
    _main()


__all__ = [
    "PM_DIR", "OUT_PATH", "AMBIGUOUS", "load_pm_docs", "resolve_teams",
    "pm_candles", "resolve_event_id_by_teams", "season_label",
    "build_checkpoints", "write", "games_per_season",
]
