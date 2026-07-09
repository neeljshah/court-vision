"""domains.soccer.chain_engine.corpus -- canonical POSSESSION-level state frame
from cached StatsBomb open-data events (data/cache/statsbomb/events/<match_id>.json,
already fetched read-only by domains.soccer.ingest_statsbomb_events -- this module
never re-fetches, only re-reads the cache + the already-built match_meta.parquet).

ATOMIC UNIT (declared): one POSSESSION -- StatsBomb tags every event with its own
`possession` id + `possession_team`, so possession segmentation is taken DIRECTLY
from the vendor's own chain-of-custody labelling (no home-grown segmenter needed,
unlike the NBA/MLB engines which must derive their atomic unit from raw PBP/pitch
streams). A possession's outcome (declared, mirrors sim2's possession-outcome
simplification): did it produce >=1 shot, and if so the shot's own
`shot.statsbomb_xg` + realized goal/no-goal.

TWO CORPORA (already fetched+cached, real dates, real scores):
  A = Premier League 2015/16 (men, 200 matches)   B = FA WSL pooled (women, 200
  matches, 2018-2021). Both independent (different era/gender/league) -> genuine
  cross-corpus replication, same spirit as the mlb/nba corpora. SCOPING NOTE: the
  wider StatsBomb open-data pull on disk (3,443/4,235 event files across many
  more competitions) is NOT used here -- those files lack a built match_meta
  (date/home/away/score) join; A+B is the bounded, already-metadata-complete
  slice. Expanding to the full pull is a straightforward v2 (same corpus.py, more
  match_ids) but out of scope for this pass.

WALK-FORWARD SPLIT: within EACH corpus independently, sorted by match_date, first
70% = FIT, last 30% = TEST (no season boundary in the WSL pool, so a date-fraction
split stands in for it -- declared v1 simplification).

SCORE STATE (leak-free): the score_bucket for a possession uses the score AS OF
the possessions strictly BEFORE it (goals from this possession's own shot are
applied to the running tally only AFTER the bucket is recorded).

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; no src/kernel imports; <=300 LOC.
Tests: python -m pytest domains/soccer/chain_engine/test_corpus.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
MATCH_META = _REPO / "data" / "cache" / "statsbomb" / "match_meta.parquet"
EVENTS_DIR = _REPO / "data" / "cache" / "statsbomb" / "events"
CORPORA = ("A", "B")
FIT_FRAC = 0.7

N_TIME_BUCKETS = 6     # 0-15,15-30,30-45,45-60,60-75,75-90+
N_SCORE_BUCKETS = 3    # trailing(0) / tied(1) / leading(2), possessing-team-relative


def time_bucket(minute: int) -> int:
    return min(int(minute) // 15, N_TIME_BUCKETS - 1)


def score_bucket(diff: int) -> int:
    """diff = possessing_team_goals - opponent_goals, as-of BEFORE this possession."""
    return 1 + (1 if diff > 0 else (-1 if diff < 0 else 0))


def load_match_meta() -> pd.DataFrame:
    return pd.read_parquet(MATCH_META)


def split_fit_test(meta: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Per-corpus date-sorted 70/30 split; returns (fit, test) concatenated
    across corpora, each row tagged with its own corpus."""
    fits, tests = [], []
    for tag in CORPORA:
        sub = meta[meta["corpus"] == tag].sort_values("match_date").reset_index(drop=True)
        cut = int(len(sub) * FIT_FRAC)
        fits.append(sub.iloc[:cut])
        tests.append(sub.iloc[cut:])
    return pd.concat(fits, ignore_index=True), pd.concat(tests, ignore_index=True)


def _load_events(match_id: int) -> List[dict]:
    fp = EVENTS_DIR / f"{match_id}.json"
    if not fp.exists():
        return []
    return json.loads(fp.read_text(encoding="utf-8"))


def _possession_groups(events: List[dict]) -> List[List[dict]]:
    """Contiguous runs sharing (period, possession), in event order."""
    groups: List[List[dict]] = []
    cur_key = None
    cur: List[dict] = []
    for e in events:
        key = (e.get("period"), e.get("possession"))
        if key != cur_key:
            if cur:
                groups.append(cur)
            cur, cur_key = [], key
        cur.append(e)
    if cur:
        groups.append(cur)
    return groups


def build_possession_frame(meta: pd.DataFrame) -> pd.DataFrame:
    """One row per possession across all matches in `meta`: match_id, team,
    is_home, time_bucket, score_bucket (as-of), had_shot, xg (NaN if no shot),
    goal (bool)."""
    rows: List[dict] = []
    for m in meta.itertuples(index=False):
        events = _load_events(int(m.match_id))
        if not events:
            continue
        home_goals = away_goals = 0
        for grp in _possession_groups(events):
            team = (grp[0].get("possession_team") or {}).get("name")
            if team is None:
                continue
            is_home = team == m.home_team
            minute = int(grp[0].get("minute") or 0)
            diff = (home_goals - away_goals) if is_home else (away_goals - home_goals)
            shots = [g for g in grp if (g.get("type") or {}).get("name") == "Shot"]
            had_shot = len(shots) > 0
            xg = float("nan")
            goal = False
            if had_shot:
                sh = shots[0].get("shot") or {}
                xg = float(sh.get("statsbomb_xg") or 0.0)
                goal = (sh.get("outcome") or {}).get("name") == "Goal"
            rows.append({
                "match_id": int(m.match_id), "team": team, "is_home": bool(is_home),
                "time_bucket": time_bucket(minute), "score_bucket": score_bucket(diff),
                "had_shot": had_shot, "xg": xg, "goal": goal,
            })
            if goal:
                if is_home:
                    home_goals += 1
                else:
                    away_goals += 1
    return pd.DataFrame(rows)


__all__ = ["MATCH_META", "EVENTS_DIR", "CORPORA", "FIT_FRAC", "N_TIME_BUCKETS",
           "N_SCORE_BUCKETS", "time_bucket", "score_bucket", "load_match_meta",
           "split_fit_test", "build_possession_frame"]
