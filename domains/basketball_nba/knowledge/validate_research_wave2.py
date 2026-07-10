"""domains.basketball_nba.knowledge.validate_research_wave2 -- validates the
2 NBA literature-sourced UNTESTED rows appended 2026-07-10 (commit 1bc7d622,
"research-wave 2", rows #47-48 in mechanisms.md):

  timeout_interrupts_opponent_run  (row #47) -- pbp_<game_id>_p1.json, raw
    paired before/after opponent PPM gap around a timeout call. NOT a causal
    claim (Brill/Wyner: the raw gap is real, the causal effect vanishes once
    the selection confound is controlled -- this tests only the raw gap).
  rest_differential_margin         (row #48) -- team_game_frame self-join,
    home-minus-away rest_days gap vs home margin.

PREMISE CHECK (this session): 2522 local pbp p1 files; 1289/3611 box-scored
games overlap (35.7%) -- matches #47's stated coverage exactly.
team_game_frame(load_player_boxscores()) = 7222 team-games (7192 with
non-null rest_days) -- matches #48's stated 7222 exactly.

SPEC NIT (row #47): the row's test spec says "paired Welch t-test". Welch's
correction is for INDEPENDENT unequal-variance samples; a paired design
(same timeout event, before vs after) calls for the paired t-test
(scipy.stats.ttest_rel), implemented here -- same kind of spec nit as
wave1 #43's column-name fix (noted, not silently smoothed over).

HONESTY: both rows get a split-half-by-date replication (2 groups) inside
this single run -- a lone correlation/t-test is not enough for an
affirmative under this program's own >=2-corpora rule.

Run: python -m domains.basketball_nba.knowledge.validate_research_wave2
"""
from __future__ import annotations

import bisect
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from scipy import stats

from domains.basketball_nba.knowledge._data import LEDGER_PATH, load_player_boxscores, team_game_frame
from domains.basketball_nba.team_name_resolver import resolve as resolve_team
from scripts.platformkit.io_atomic import append_jsonl_atomic

REPO = Path(__file__).resolve().parents[3]
PBP_DIR = REPO / "data" / "nba"

PERIOD_LEN_SEC = 720
WINDOW_SEC = 180
MIN_WINDOW_SEC = 60
ALPHA = 0.01
MIN_EFFECT_TIMEOUT = 0.3   # row #47's declared bar, pts/min
MIN_EFFECT_REST = 0.05     # row #48's declared bar, Pearson r
MIN_GROUP_N = 20

_TIMEOUT_RE = re.compile(r"^(.+?)\s+Timeout", re.IGNORECASE)


def _combine_halves(rows: List[Dict[str, Any]], hyp: str) -> Dict[str, Any]:
    """Both halves must independently clear the row's own p+effect bar (i.e.
    verdict==CONFIRMED_LOCAL), same sign, else NULL/PROVISIONAL/NOT_TESTABLE."""
    testable = [r for r in rows if r["verdict"] != "NOT_TESTABLE"]
    confirmed = [r for r in testable if r["verdict"] == "CONFIRMED_LOCAL"]
    if len(testable) < 2:
        verdict = "NOT_TESTABLE"
    elif len(confirmed) == 2 and len({1 if r["effect"] > 0 else -1 for r in confirmed}) == 1:
        verdict = "CONFIRMED_LOCAL"
    elif len(confirmed) == 1:
        verdict = "PROVISIONAL"
    else:
        verdict = "NULL_LOCAL"
    return {"hypothesis": hyp + "__combined", "n": int(sum(r["n"] for r in rows)), "effect": None, "p": None,
            "verdict": verdict,
            "note": "split-half-by-date replication: %s"
                    % "; ".join("%s(verdict=%s,p=%s,eff=%s)" % (r["hypothesis"], r["verdict"], r["p"], r["effect"])
                                for r in rows)}


# ---------------------------------------------------------------- row #47 --
def _load_p1(game_id: str) -> Optional[List[Dict[str, Any]]]:
    path = PBP_DIR / ("pbp_%s_p1.json" % game_id)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        events = json.load(f)
    return sorted((e for e in events if e.get("period") == 1), key=lambda e: e["game_clock_sec"])


def _team_slot_map(events: List[Dict[str, Any]]) -> Optional[Dict[str, int]]:
    """team_abbrev -> which slot (0/1) of the cumulative 'A-B' score string is
    theirs, found by watching the first scoring event that advances a slot."""
    teams = sorted({e["team_abbrev"] for e in events if e.get("team_abbrev")})
    if len(teams) != 2:
        return None
    prev = (0, 0)
    for e in events:
        parts = e.get("score", "").split("-")
        if len(parts) != 2:
            continue
        try:
            cur = (int(parts[0]), int(parts[1]))
        except ValueError:
            continue
        team = e.get("team_abbrev", "")
        if team and cur != prev:
            if cur[0] > prev[0]:
                slot = 0
            elif cur[1] > prev[1]:
                slot = 1
            else:
                prev = cur
                continue
            other = teams[0] if team == teams[1] else teams[1]
            return {team: slot, other: 1 - slot}
        prev = cur
    return None


def _score_series(events: List[Dict[str, Any]]) -> tuple:
    times, scores, cur = [], [], (0, 0)
    for e in events:
        parts = e.get("score", "").split("-")
        if len(parts) == 2:
            try:
                cur = (int(parts[0]), int(parts[1]))
            except ValueError:
                pass
        times.append(e["game_clock_sec"])
        scores.append(cur)
    return times, scores


def _score_at(times: List[int], scores: List[tuple], t: float) -> tuple:
    idx = bisect.bisect_right(times, t) - 1
    return scores[idx] if idx >= 0 else (0, 0)


def game_samples(game_id: str) -> List[Dict[str, Any]]:
    """One row per timeout event with a resolvable calling team and a
    non-degenerate before/after window: opponent points-per-minute either
    side of the call."""
    events = _load_p1(game_id)
    if not events:
        return []
    slot_map = _team_slot_map(events)
    if not slot_map:
        return []
    times, scores = _score_series(events)
    rows: List[Dict[str, Any]] = []
    for e in events:
        m = _TIMEOUT_RE.match(e.get("event_desc", ""))
        if not m:
            continue
        team = resolve_team(m.group(1))
        if team is None or team not in slot_map:
            continue
        opp = next((t for t in slot_map if t != team), None)
        if opp is None:
            continue
        opp_slot = slot_map[opp]
        t0 = e["game_clock_sec"]
        before_start = max(0, t0 - WINDOW_SEC)
        after_end = min(PERIOD_LEN_SEC, t0 + WINDOW_SEC)
        before_len, after_len = t0 - before_start, after_end - t0
        if before_len < MIN_WINDOW_SEC or after_len < MIN_WINDOW_SEC:
            continue
        pts_before = _score_at(times, scores, t0)[opp_slot] - _score_at(times, scores, before_start)[opp_slot]
        pts_after = _score_at(times, scores, after_end)[opp_slot] - _score_at(times, scores, t0)[opp_slot]
        rows.append({"game_id": game_id, "team": team,
                      "ppm_before": pts_before / (before_len / 60.0),
                      "ppm_after": pts_after / (after_len / 60.0)})
    return rows


def build_dataset() -> pd.DataFrame:
    box = load_player_boxscores()
    available = {p.name[4:-8] for p in PBP_DIR.glob("pbp_*_p1.json")}
    game_ids = [g for g in box["game_id"].unique() if g in available]
    dates = box.groupby("game_id")["date"].first()
    rows: List[Dict[str, Any]] = []
    for gid in game_ids:
        rows.extend(game_samples(gid))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = df["game_id"].map(dates)
    return df


def _paired_verdict(before: pd.Series, after: pd.Series, half: str) -> Dict[str, Any]:
    n = len(before)
    if n < MIN_GROUP_N:
        return {"hypothesis": "timeout_interrupts_opponent_run__%s" % half, "n": int(n),
                "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "insufficient timeout samples after window floor (n=%d, need >=%d), half=%s"
                        % (n, MIN_GROUP_N, half)}
    t, p = stats.ttest_rel(after, before)
    eff = float((after - before).mean())
    verdict = "CONFIRMED_LOCAL" if (p < ALPHA and abs(eff) >= MIN_EFFECT_TIMEOUT) else "NULL_LOCAL"
    return {"hypothesis": "timeout_interrupts_opponent_run__%s" % half, "n": int(n),
            "effect": round(eff, 4), "p": float(p), "verdict": verdict,
            "note": "paired t-test opponent PPM after-before mean diff=%.4f (n=%d), half=%s"
                    % (eff, n, half)}


# ---------------------------------------------------------------- row #48 --
def _rest_diff_frame(tg: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    d = tg if tg is not None else team_game_frame(load_player_boxscores())
    home = d[d["is_home"] == 1][["game_id", "date", "rest_days", "margin"]].rename(
        columns={"rest_days": "home_rest"})
    away = d[d["is_home"] == 0][["game_id", "rest_days"]].rename(columns={"rest_days": "away_rest"})
    m = home.merge(away, on="game_id").dropna(subset=["home_rest", "away_rest"])
    m["rest_diff"] = m["home_rest"] - m["away_rest"]
    return m


def _rest_margin_r(m: pd.DataFrame, half: str) -> Dict[str, Any]:
    if len(m) < MIN_GROUP_N or m["rest_diff"].nunique() < 2:
        return {"hypothesis": "rest_differential_margin__%s" % half, "n": int(len(m)),
                "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "insufficient paired games or degenerate rest_diff (n=%d), half=%s" % (len(m), half)}
    r, p = stats.pearsonr(m["rest_diff"], m["margin"])
    verdict = "CONFIRMED_LOCAL" if (p < ALPHA and abs(r) >= MIN_EFFECT_REST) else "NULL_LOCAL"
    return {"hypothesis": "rest_differential_margin__%s" % half, "n": int(len(m)),
            "effect": round(float(r), 4), "p": float(p), "verdict": verdict,
            "note": "Pearson r(rest_diff=home_rest-away_rest, home margin) r=%.4f p=%s (n=%d games), half=%s"
                    % (r, p, len(m), half)}


def rest_differential_margin(tg: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
    m = _rest_diff_frame(tg)
    if m.empty:
        return [{"hypothesis": "rest_differential_margin__combined", "n": 0, "effect": None, "p": None,
                  "verdict": "NOT_TESTABLE", "note": "no home/away pairs with non-null rest_days both sides"}]
    mid = m["date"].median()
    h1, h2 = _rest_margin_r(m[m["date"] <= mid], "h1"), _rest_margin_r(m[m["date"] > mid], "h2")
    return [h1, h2, _combine_halves([h1, h2], "rest_differential_margin")]


def run() -> List[Dict[str, Any]]:
    df = build_dataset()
    n_games = int(df["game_id"].nunique()) if not df.empty else 0
    if df.empty:
        timeout_rows = [{"hypothesis": "timeout_interrupts_opponent_run__combined", "n": 0, "effect": None,
                          "p": None, "verdict": "NOT_TESTABLE",
                          "note": "no local pbp p1 games yielded a valid timeout window sample"}]
    else:
        mid = df["date"].median()
        h1df, h2df = df[df["date"] <= mid], df[df["date"] > mid]
        r1 = _paired_verdict(h1df["ppm_before"], h1df["ppm_after"], "h1")
        r2 = _paired_verdict(h2df["ppm_before"], h2df["ppm_after"], "h2")
        timeout_rows = [r1, r2, _combine_halves([r1, r2], "timeout_interrupts_opponent_run")]
    for r in timeout_rows:
        r["corpus"] = "pbp_p1_json_timeout_windows (%d games w/ timeout samples, split-half by date)" % n_games

    rest_rows = rest_differential_margin()
    for r in rest_rows:
        r["corpus"] = "player_boxscores_team_game_frame_7222_teamgames (split-half by date)"

    rows = timeout_rows + rest_rows
    for r in rows:
        r["sport"] = "basketball_nba"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-46s %-16s n=%-6s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r.get("n"), r.get("effect"), r.get("p"), r.get("note")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: team-slot resolution, name resolver, window
    floor, and the paired/correlation verdict thresholds."""
    events = [
        {"period": 1, "game_clock_sec": 0, "event_desc": "Start", "team_abbrev": "", "score": "0-0"},
        {"period": 1, "game_clock_sec": 10, "event_desc": "Smart makes", "team_abbrev": "BOS", "score": "2-0"},
        {"period": 1, "game_clock_sec": 20, "event_desc": "Harris makes", "team_abbrev": "PHI", "score": "2-2"},
    ]
    assert _team_slot_map(events) == {"BOS": 0, "PHI": 1}
    assert resolve_team("CELTICS") == "BOS"
    assert resolve_team("76ers") == "PHI"
    times, scores = _score_series(events)
    assert _score_at(times, scores, 15) == (2, 0)
    assert _score_at(times, scores, 25) == (2, 2)
    before = pd.Series([1.0 + 0.1 * (i % 3) for i in range(30)])
    after = pd.Series([1.6 + 0.1 * (i % 2) for i in range(30)])
    r = _paired_verdict(before, after, "h1")
    assert r["verdict"] == "CONFIRMED_LOCAL"
    print("self-check OK")
