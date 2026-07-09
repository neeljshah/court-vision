"""scripts.platformkit.benchmarks.crps_market.mlb_join -- bridges MLB Statcast
game_pk (domains/mlb/pitch_engine corpus, keyed on game_pk) to our own scraped
odds feed's game_id (data/cache/line_history/mlb/<date>.jsonl, ESPN numeric id,
keyed on home/away display names + commence_time).

No existing bridge covers this pair directly: domains/mlb/game_pk_bridge.py maps
game_pk -> a THIRD event_id scheme (games_current.parquet, 2022-2021 era, not our
odds feed) and scripts/platformkit/ingame/game_pk_bridge_live.py hits live network
feeds for "today". Both are reused for team-name canonicalization philosophy
(domains.mlb.team_name_resolver) but this is a new, offline, date+team-pair join
over our own two on-disk corpora -- no new team dialect table, only reuse.

JOIN KEY: (commence date, unordered canonical team-pair). commence_time is UTC and
Statcast's game_date is the (US) home-team-local calendar date, so a night game's
UTC commence_time can roll to the next date -- both the commence date and the day
before are tried; a match is accepted only if the two candidate dates resolve to
exactly ONE distinct game_pk (an ambiguous pair, e.g. a doubleheader sharing both
teams+date, is left unresolved -- never guessed).

INVARIANTS: new file, scripts/platformkit/benchmarks/crps_market/ only; ASCII;
no src/kernel/api imports; <=300 LOC; accuracy/coverage only, no $ claim.
Tests: python -m pytest tests/platformkit/test_crps_market_mlb.py -q
"""
from __future__ import annotations

import glob
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from domains.mlb.team_name_resolver import resolve

_REPO = Path(__file__).resolve().parents[4]
_LINE_HISTORY = _REPO / "data" / "cache" / "line_history" / "mlb"
_STATCAST = _REPO / "data" / "cache" / "statcast"


def _pair_key(a: str, b: str) -> Optional[str]:
    ca, cb = resolve(a), resolve(b)
    if not ca or not cb:
        return None
    return "|".join(sorted((ca, cb)))


def load_statcast_games(season: int) -> pd.DataFrame:
    """One row per game_pk: game_date (date), pair_key, realized_total (runs)."""
    path = _STATCAST / ("savant_full__%d.parquet" % season)
    df = pd.read_parquet(path, columns=["game_pk", "game_date", "home_team",
                                         "away_team", "post_home_score", "post_away_score"])
    tot = df.groupby("game_pk").agg(
        game_date=("game_date", "first"),
        home_team=("home_team", "first"),
        away_team=("away_team", "first"),
        home_score=("post_home_score", "max"),
        away_score=("post_away_score", "max"),
    ).reset_index()
    tot["pair_key"] = [_pair_key(h, a) for h, a in zip(tot["home_team"], tot["away_team"])]
    tot["game_date"] = pd.to_datetime(tot["game_date"]).dt.date
    tot["realized_total"] = tot["home_score"] + tot["away_score"]
    return tot.dropna(subset=["pair_key"])


def load_line_history_totals(start: str, end: str) -> pd.DataFrame:
    """All market_type=='total' rows across data/cache/line_history/mlb/<date>.jsonl
    in [start, end] (inclusive, YYYY-MM-DD). One row per raw capture."""
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    rows: List[dict] = []
    for fp in sorted(glob.glob(str(_LINE_HISTORY / "*.jsonl"))):
        day = Path(fp).stem
        if not (lo <= pd.Timestamp(day) <= hi):
            continue
        for line in open(fp, encoding="utf-8"):
            d = json.loads(line)
            if d.get("market_type") == "total":
                rows.append(d)
    if not rows:
        return pd.DataFrame(columns=["game_id", "home", "away", "line", "side",
                                      "devigged_prob", "book", "captured_at",
                                      "commence_time"])
    df = pd.DataFrame(rows)
    df["commence_time"] = pd.to_datetime(df["commence_time"], utc=True, format="ISO8601")
    df["captured_at"] = pd.to_datetime(df["captured_at"], utc=True, format="ISO8601")
    # LEAK GUARD: the feed keeps re-polling a game's line for hours after it starts
    # (frozen value, but still a live/in-progress capture) -- keep only PRE-game
    # snapshots so "market" always means the pregame close, never an in-game price.
    return df[df["captured_at"] <= df["commence_time"]].reset_index(drop=True)


def build_game_join(statcast_games: pd.DataFrame,
                     line_totals: pd.DataFrame) -> Dict[str, int]:
    """game_id -> game_pk for every UNAMBIGUOUS (date, team-pair) match.
    A game_id whose candidate dates resolve to 0 or >1 distinct game_pk is
    dropped, never guessed."""
    by_key: Dict[Tuple, List[int]] = {}
    for pk, dt, key in zip(statcast_games["game_pk"], statcast_games["game_date"],
                           statcast_games["pair_key"]):
        by_key.setdefault((dt, key), []).append(int(pk))

    out: Dict[str, int] = {}
    meta = line_totals.drop_duplicates("game_id")[["game_id", "home", "away", "commence_time"]]
    for gid, home, away, ct in zip(meta["game_id"], meta["home"], meta["away"],
                                    meta["commence_time"]):
        key = _pair_key(home, away)
        if key is None:
            continue
        # Prefer the exact commence date; only fall back to the day before (the
        # UTC-rollover case) when the exact date has NO candidate at all -- teams
        # play multi-game series on consecutive days, so unioning both dates
        # would make every back-to-back game falsely "ambiguous".
        d0 = ct.date()
        candidates = by_key.get((d0, key), [])
        if not candidates:
            candidates = by_key.get((d0 - timedelta(days=1), key), [])
        if len(candidates) == 1:
            out[gid] = candidates[0]
    return out


__all__ = ["load_statcast_games", "load_line_history_totals", "build_game_join"]
