"""domains.soccer.knowledge._data -- shared StatsBomb loaders for the mechanism
validation scripts in this package. Two corpora:

* `iter_all_event_files()` -- ALL locally cached event files (glob
  data/cache/statsbomb/events/*.json, ~3,400 matches), no home/away/date
  metadata attached. Use for within-match structural checks (a mechanism that
  only needs event order inside one match, e.g. "shots before vs after a red
  card") -- leak-free by construction since nothing crosses a match boundary.
* `load_match_meta()` -- the 400-match date/home-away/final-score slice
  (corpus A=EPL 2015/16, B=FA WSL). Use for anything needing match date, a
  final result, or team identity across matches.

ponytail: no caching layer -- the 400-match corpus loads in seconds and the
full event glob is read once per validate_*.py run; add an lru_cache if a
script starts re-reading the same match_id repeatedly.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
STATSBOMB_DIR = REPO / "data" / "cache" / "statsbomb"
EVENTS_DIR = STATSBOMB_DIR / "events"
MATCH_META_PATH = STATSBOMB_DIR / "match_meta.parquet"
LEDGER_PATH = Path(__file__).resolve().parent / "validation_ledger.jsonl"

SENDOFF_CARDS = {"Red Card", "Second Yellow"}


def load_match_meta() -> pd.DataFrame:
    """400-match corpus: match_id, match_date, home_team, away_team,
    home_score, away_score, corpus in {A, B}."""
    df = pd.read_parquet(MATCH_META_PATH)
    df["match_date"] = pd.to_datetime(df["match_date"])
    return df


def load_events(match_id: Any) -> List[Dict[str, Any]]:
    """Raw StatsBomb event list for one match_id."""
    with open(EVENTS_DIR / ("%s.json" % match_id), encoding="utf-8") as f:
        return json.load(f)


def iter_all_event_files() -> Iterator[Tuple[str, List[Dict[str, Any]]]]:
    """(match_id, events) for every cached match file -- no match_meta join."""
    for fp in glob.glob(str(EVENTS_DIR / "*.json")):
        match_id = Path(fp).stem
        with open(fp, encoding="utf-8") as f:
            yield match_id, json.load(f)


def extract_match_facts(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One pass over a match's events -> the facts the validate_*.py scripts
    need, so each script reads a match's JSON exactly once. `minute`/`second`
    are StatsBomb's own elapsed-match-time fields (period-cumulative), used
    directly as the leak-free "as-of" clock -- no derived/aggregate timing.
    """
    teams: List[str] = []
    shots: List[Tuple[str, float, bool, Any]] = []  # (team, t_min, is_goal, shot_type)
    goal_events: List[Tuple[float, str]] = []  # (t_min, team_or_owngoal_marker)
    red_cards: List[Tuple[float, str]] = []
    subs_by_team: Dict[str, float] = {}
    t_max = 0.0
    for e in events:
        t_min = e["minute"] + e["second"] / 60.0
        t_max = max(t_max, t_min)
        team = (e.get("team") or {}).get("name")
        if team and team not in teams:
            teams.append(team)
        etype = e["type"]["name"]
        if etype == "Shot":
            shot = e.get("shot") or {}
            is_goal = (shot.get("outcome") or {}).get("name") == "Goal"
            shot_type = (shot.get("type") or {}).get("name")
            shots.append((team, t_min, is_goal, shot_type))
            if is_goal:
                goal_events.append((t_min, team))
        elif etype == "Own Goal Against":
            goal_events.append((t_min, ("_OG_AGAINST_", team)))
        elif etype == "Foul Committed":
            card = ((e.get("foul_committed") or {}).get("card") or {}).get("name")
            if card in SENDOFF_CARDS:
                red_cards.append((t_min, team))
        elif etype == "Bad Behaviour":
            card = ((e.get("bad_behaviour") or {}).get("card") or {}).get("name")
            if card in SENDOFF_CARDS:
                red_cards.append((t_min, team))
        elif etype == "Substitution" and team not in subs_by_team:
            subs_by_team[team] = t_min

    goals: List[Tuple[float, str]] = []
    for t_min, marker in goal_events:
        if isinstance(marker, tuple) and marker[0] == "_OG_AGAINST_":
            committer = marker[1]
            opponents = [t for t in teams if t != committer]
            goals.append((t_min, opponents[0] if opponents else committer))
        else:
            goals.append((t_min, marker))

    return {"teams": teams, "match_len": t_max, "shots": shots, "goals": goals,
            "red_cards": red_cards, "subs": subs_by_team}


__all__ = ["REPO", "STATSBOMB_DIR", "EVENTS_DIR", "MATCH_META_PATH", "LEDGER_PATH",
           "SENDOFF_CARDS", "load_match_meta", "load_events", "iter_all_event_files",
           "extract_match_facts"]
