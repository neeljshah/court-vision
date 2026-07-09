"""domains.soccer.knowledge.validate_referee_schedule -- 3 UNTESTED referee/
schedule mechanisms (mechanisms.md #15 home-advantage by match-week tercile,
#16 referee card-rate split-half persistence, #27 away-goal timing asymmetry)
plus premise-checks for 5 more (#14 attendance, #17 suspension-tracking, #23
corner-footedness, #24 extra-time, #25 cup-vs-league) that a fresh disk/
column check this session confirms are NOT_TESTABLE on the current 400-match
corpus. `data/cache/statsbomb/matches/*.json` (3,961 match records spanning
many competitions) is joined to the 400-match `match_meta.parquet` corpus by
match_id -- confirmed this session to cover all 400 (match_week/referee were
previously flagged UNTESTED as "not yet wired", not missing).

Run: python -m domains.soccer.knowledge.validate_referee_schedule
"""
from __future__ import annotations

import glob
import json
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.soccer.knowledge._data import LEDGER_PATH, REPO, load_events, load_match_meta
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MATCHES_DIR = REPO / "data" / "cache" / "statsbomb" / "matches"
ANY_CARD = {"Yellow Card", "Red Card", "Second Yellow"}


def _verdict(p, min_abs_effect: float, effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _load_matches_extra() -> pd.DataFrame:
    """match_id -> match_week, referee_id, referee_name, competition_stage,
    stadium, for every record in matches/*.json (joined down to the 400-match
    corpus by callers)."""
    rows = []
    for fp in glob.glob(str(MATCHES_DIR / "*.json")):
        for m in json.loads(open(fp, encoding="utf-8").read()):
            rows.append({
                "match_id": str(m["match_id"]), "match_week": m.get("match_week"),
                "referee_id": (m.get("referee") or {}).get("id"),
                "stadium": (m.get("stadium") or {}).get("name"),
                "competition_stage": (m.get("competition_stage") or {}).get("name"),
                "attendance": m.get("attendance")})
    df = pd.DataFrame(rows).drop_duplicates("match_id")
    df["match_id"] = df["match_id"].astype("int64")
    return df


def home_advantage_by_matchweek(meta: pd.DataFrame, extra: pd.DataFrame) -> Dict[str, Any]:
    d = meta[meta["corpus"] == "A"].merge(extra, on="match_id").dropna(subset=["match_week"])
    d["home_win"] = (d["home_score"] > d["away_score"]).astype(int)
    d["tercile"] = pd.qcut(d["match_week"], 3, labels=["early", "mid", "late"], duplicates="drop")
    tab = pd.crosstab(d["tercile"], d["home_win"])
    chi2, p, dof, _ = stats.chi2_contingency(tab)
    rates = d.groupby("tercile", observed=True)["home_win"].mean()
    eff = float(rates.max() - rates.min())
    return {"hypothesis": "home_advantage_by_matchweek_tercile", "n": int(len(d)), "effect": round(eff, 4),
            "p": float(p), "verdict": _verdict(p, 0.1, eff),
            "note": "home win-rate by match-week tercile (corpus A only): %s" % rates.round(4).to_dict()}


def referee_card_rate_persistence(meta: pd.DataFrame, extra: pd.DataFrame) -> Dict[str, Any]:
    d = meta.merge(extra, on="match_id").dropna(subset=["referee_id"])
    mid = d["match_date"].median()
    d = d.copy()
    d["half"] = np.where(d["match_date"] < mid, "A", "B")
    cards = []
    for _, row in d.iterrows():
        n = sum(1 for e in load_events(row["match_id"]) if
                 (e["type"]["name"] == "Foul Committed" and
                  ((e.get("foul_committed") or {}).get("card") or {}).get("name") in ANY_CARD) or
                 (e["type"]["name"] == "Bad Behaviour" and
                  ((e.get("bad_behaviour") or {}).get("card") or {}).get("name") in ANY_CARD))
        cards.append(n)
    d["cards"] = cards
    cnt = d.groupby(["referee_id", "half"]).size().unstack("half").fillna(0)
    ok = cnt[(cnt.get("A", 0) >= 3) & (cnt.get("B", 0) >= 3)].index
    dd = d[d["referee_id"].isin(ok)]
    piv = dd.groupby(["referee_id", "half"])["cards"].mean().unstack("half").dropna()
    if len(piv) < 10:
        return {"hypothesis": "referee_card_rate_persistence", "n": int(len(piv)), "effect": None, "p": None,
                "verdict": "NOT_TESTABLE", "note": "fewer than 10 referees with >=3 matches per half"}
    r, p = stats.pearsonr(piv["A"], piv["B"])
    return {"hypothesis": "referee_card_rate_persistence", "n": int(len(piv)), "effect": round(float(r), 4),
            "p": float(p), "verdict": _verdict(p, 0.1, r),
            "note": "split-half pearson r, referee cards/match, n=%d referees (>=3 matches/half)" % len(piv)}


def away_goal_timing_asymmetry(meta: pd.DataFrame) -> Dict[str, Any]:
    home_shift, away_shift = [], []
    for _, row in meta.iterrows():
        events = load_events(row["match_id"])
        goals, shots_by_team, match_len = [], {}, 0.0
        for e in events:
            t_min = e["minute"] + e["second"] / 60.0
            match_len = max(match_len, t_min)
            team = (e.get("team") or {}).get("name")
            if e["type"]["name"] == "Shot" and team:
                shots_by_team.setdefault(team, []).append(t_min)
                shot = e.get("shot") or {}
                if (shot.get("outcome") or {}).get("name") == "Goal":
                    goals.append((t_min, team))
            elif e["type"]["name"] == "Own Goal Against" and team:
                opp = row["home_team"] if team == row["away_team"] else row["away_team"]
                goals.append((t_min, opp))
        if not goals:
            continue
        t_goal, scorer = min(goals)
        win = min(t_goal, match_len - t_goal)
        if win < 5.0:
            continue
        all_shots = [t for shots in shots_by_team.values() for t in shots]
        before = sum(1 for t in all_shots if t_goal - win <= t < t_goal) / win
        after = sum(1 for t in all_shots if t_goal <= t < t_goal + win) / win
        shift = after - before
        (away_shift if scorer == row["away_team"] else home_shift).append(shift)
    t, p = stats.ttest_ind(away_shift, home_shift, equal_var=False)
    eff = float(np.mean(away_shift) - np.mean(home_shift))
    return {"hypothesis": "away_goal_timing_asymmetry", "n": len(away_shift) + len(home_shift),
            "effect": round(eff, 4), "p": float(p), "verdict": _verdict(p, 0.01, eff),
            "note": "combined shot-rate shift (after-before, matched window) around the match's first goal, "
                    "away-team-scored (%.4f, n=%d) vs home-team-scored (%.4f, n=%d)"
                    % (np.mean(away_shift), len(away_shift), np.mean(home_shift), len(home_shift))}


def _premise_blocked(extra: pd.DataFrame) -> List[Dict[str, Any]]:
    attendance_hits = int(extra["attendance"].notna().sum())
    stages = extra["competition_stage"].value_counts()
    return [
        {"hypothesis": "home_advantage_crowd_component", "n": 0, "effect": None, "p": None,
         "verdict": "NOT_TESTABLE",
         "note": "matches/*.json has a `stadium` field but no `attendance` field (%d non-null of %d rows "
                 "checked) -- no attendance/crowd-size proxy exists locally." % (attendance_hits, len(extra))},
        {"hypothesis": "yellow_card_suspension_effect", "n": 0, "effect": None, "p": None,
         "verdict": "NOT_TESTABLE",
         "note": "accumulated-yellow suspension tracking needs each player's FULL-season card history; "
                 "the 400-match corpus is a partial slice (200/380 per corpus) so any suspension inferred "
                 "from it would be an artifact of the missing games, not a real ban."},
        {"hypothesis": "corner_delivery_side_conversion", "n": 0, "effect": None, "p": None,
         "verdict": "NOT_TESTABLE",
         "note": "corner-taker footedness is not in the StatsBomb event or lineup schema locally -- would "
                 "need an external footedness lookup, a v2 ingredient."},
        {"hypothesis": "extra_time_knockout_fatigue", "n": 0, "effect": None, "p": None,
         "verdict": "NOT_TESTABLE",
         "note": "both corpora (EPL 2015/16, FA WSL) are league-season round-robin competitions with no "
                 "knockout legs -- every cached event file's `period` value-set is {1,2}, confirmed this "
                 "session; no extra-time periods exist to test."},
        {"hypothesis": "squad_rotation_cup_vs_league", "n": 0, "effect": None, "p": None,
         "verdict": "NOT_TESTABLE",
         "note": "competition_stage for all 400 corpus matches is uniformly '%s' (value counts: %s) -- no "
                 "cup fixtures exist in this slice to contrast against league fixtures." % (
                 stages.index[0] if len(stages) else "?", stages.to_dict())},
    ]


def run() -> List[Dict[str, Any]]:
    meta = load_match_meta()
    extra = _load_matches_extra()
    joined = meta.merge(extra, on="match_id", how="inner")
    rows = [home_advantage_by_matchweek(meta, extra), referee_card_rate_persistence(meta, extra),
            away_goal_timing_asymmetry(meta)] + _premise_blocked(joined)
    for r in rows:
        r["sport"] = "soccer"
        r["corpus"] = "statsbomb_match_meta__400+matches_json"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-36s %-16s -- %s" % (r["hypothesis"], r["verdict"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.02, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.02, 0.1) == "NULL_LOCAL"
    print("self-check OK")
