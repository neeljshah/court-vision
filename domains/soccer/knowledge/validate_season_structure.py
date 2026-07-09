"""domains.soccer.knowledge.validate_season_structure -- 4 UNTESTED mechanisms
needing match date / final result, run against the 400-match match_meta slice
(corpus A=EPL 2015/16, B=FA WSL). Leak audit: split-half correlations are
within-season internal-consistency checks (no future-into-past leak); the
first-goal/momentum/rest-day checks correlate an in-match or prior-match fact
against a FINAL, already-completed result across many independent matches --
descriptive structural analysis of closed games, not a forecast fed forward,
so no leak. Momentum + rest-day are corpus-A-only: corpus B's (WSL) date
gaps are wildly irregular (multi-season pooling), so a "previous match"
adjacency there would be spurious -- see gap-distribution note inline.

Run: python -m domains.soccer.knowledge.validate_season_structure
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
from scipy import stats

from domains.soccer.knowledge._data import (LEDGER_PATH, extract_match_facts, load_events,
                                             load_match_meta)
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_SHOTS_PER_HALF = 8
SHORT_REST_DAYS = 4


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or p != p:
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _shot_rows(events: List[Dict[str, Any]]):
    """(player_id, xg, is_goal) for every shot in one match -- player-level,
    unlike _data.extract_match_facts which only keeps team-level shot facts."""
    for e in events:
        if e["type"]["name"] != "Shot":
            continue
        shot = e.get("shot") or {}
        player = (e.get("player") or {}).get("id")
        xg = shot.get("statsbomb_xg")
        if player is None or xg is None:
            continue
        yield player, float(xg), (shot.get("outcome") or {}).get("name") == "Goal"


def finishing_skill_persistence_split_half(meta: pd.DataFrame) -> Dict[str, Any]:
    """Split-half (by match date, WITHIN each corpus) Pearson r of per-player
    (goals - sum xG) -- is finishing over/under-performance a repeatable
    skill or noise? corpus A (2015/16) and corpus B (2018-21) don't overlap
    in time at all, so the median split is computed per-corpus -- a global
    median would silently put ALL of A in h1 and ALL of B in h2 (disjoint
    player pools, zero overlap by construction, not a real finding)."""
    h1_acc: Dict[int, float] = {}
    h2_acc: Dict[int, float] = {}
    h1_n: Dict[int, int] = {}
    h2_n: Dict[int, int] = {}
    for corpus, grp in meta.groupby("corpus"):
        mid = grp["match_date"].median()
        for _, row in grp.iterrows():
            target = (h1_acc, h1_n) if row["match_date"] <= mid else (h2_acc, h2_n)
            acc, cnt = target
            for player, xg, is_goal in _shot_rows(load_events(row["match_id"])):
                acc[player] = acc.get(player, 0.0) + (float(is_goal) - xg)
                cnt[player] = cnt.get(player, 0) + 1
    keep1 = {p: v for p, v in h1_acc.items() if h1_n[p] >= MIN_SHOTS_PER_HALF}
    keep2 = {p: v for p, v in h2_acc.items() if h2_n[p] >= MIN_SHOTS_PER_HALF}
    common = sorted(set(keep1) & set(keep2))
    r, p = (float("nan"), float("nan")) if len(common) < 5 else stats.pearsonr(
        [keep1[p_] for p_ in common], [keep2[p_] for p_ in common])
    return {"hypothesis": "finishing_skill_persists_split_half", "n": len(common),
            "effect": round(float(r), 4) if r == r else None, "p": float(p) if p == p else None,
            "note": "split-half Pearson r of (goals - sum xG) across %d players (>=%d shots/half)"
                    % (len(common), MIN_SHOTS_PER_HALF)}


def first_goal_timing_win_effect(meta: pd.DataFrame) -> Dict[str, Any]:
    """Does the team that scores first win the (decisive) match more than a
    coin flip would predict -- binomial test vs p=0.5, draws excluded."""
    wins, decisive = 0, 0
    for _, row in meta.iterrows():
        if row["home_score"] == row["away_score"]:
            continue
        facts = extract_match_facts(load_events(row["match_id"]))
        if not facts["goals"]:
            continue
        first_scorer = min(facts["goals"])[1]
        winner = row["home_team"] if row["home_score"] > row["away_score"] else row["away_team"]
        decisive += 1
        wins += int(first_scorer == winner)
    res = stats.binomtest(wins, decisive, p=0.5)
    return {"hypothesis": "first_goal_timing_win_effect", "n": decisive,
            "effect": round(wins / decisive - 0.5, 4), "p": float(res.pvalue),
            "note": "first-scoring team won %d/%d decisive matches (binomial vs 0.5)" % (wins, decisive)}


def _team_perspective(meta: pd.DataFrame, corpus: str) -> pd.DataFrame:
    d = meta[meta["corpus"] == corpus]
    home = d.rename(columns={"home_team": "team", "away_team": "opp",
                              "home_score": "gf", "away_score": "ga"})[
        ["match_date", "team", "opp", "gf", "ga"]]
    away = d.rename(columns={"away_team": "team", "home_team": "opp",
                              "away_score": "gf", "home_score": "ga"})[
        ["match_date", "team", "opp", "gf", "ga"]]
    both = pd.concat([home, away], ignore_index=True).sort_values(["team", "match_date"])
    both["win"] = (both["gf"] > both["ga"]).astype(int)
    both["goal_diff"] = both["gf"] - both["ga"]
    both["rest_days"] = both.groupby("team")["match_date"].diff().dt.days
    both["prev_win"] = both.groupby("team")["win"].shift(1)
    return both


def momentum_last_result_effect(meta: pd.DataFrame, corpus: str = "A") -> Dict[str, Any]:
    """Does winning the previous in-sample match predict winning this one,
    beyond a naive 50/50 -- the classic momentum/hot-hand myth, tested on the
    corpus with reliably weekly (near-contiguous) fixture spacing."""
    d = _team_perspective(meta, corpus).dropna(subset=["prev_win"])
    a, b = d[d["prev_win"] == 1]["win"], d[d["prev_win"] == 0]["win"]
    t, p = stats.ttest_ind(a, b, equal_var=False)
    return {"hypothesis": "momentum_last_result_effect", "n": int(len(d)),
            "effect": round(float(a.mean() - b.mean()), 4), "p": float(p),
            "note": "corpus %s: win-rate after a prior win (%.3f, n=%d) vs after no prior win (%.3f, n=%d)"
                    % (corpus, a.mean(), len(a), b.mean(), len(b))}


def fixture_congestion_short_rest_effect(meta: pd.DataFrame, corpus: str = "A") -> Dict[str, Any]:
    """Short-rest (<=4 days since the team's previous in-sample match) vs
    normal-rest goal differential -- does fixture congestion hurt performance."""
    d = _team_perspective(meta, corpus).dropna(subset=["rest_days"])
    short = d[d["rest_days"] <= SHORT_REST_DAYS]["goal_diff"]
    normal = d[d["rest_days"] > SHORT_REST_DAYS]["goal_diff"]
    t, p = stats.ttest_ind(short, normal, equal_var=False)
    return {"hypothesis": "fixture_congestion_short_rest_effect", "n": int(len(d)),
            "effect": round(float(short.mean() - normal.mean()), 4), "p": float(p),
            "note": "corpus %s: goal-diff short-rest<=%dd (%.3f, n=%d) vs normal-rest (%.3f, n=%d)"
                    % (corpus, SHORT_REST_DAYS, short.mean(), len(short), normal.mean(), len(normal))}


def run() -> List[Dict[str, Any]]:
    meta = load_match_meta()
    specs = [(finishing_skill_persistence_split_half, (meta,), 0.15),
             (first_goal_timing_win_effect, (meta,), 0.05),
             (momentum_last_result_effect, (meta,), 0.10),
             (fixture_congestion_short_rest_effect, (meta,), 0.15)]
    rows = []
    for fn, args, min_eff in specs:
        r = fn(*args)
        r["verdict"] = _verdict(r["p"], r["effect"], min_eff) if r["effect"] is not None else "NOT_TESTABLE"
        r["sport"] = "soccer"
        r["corpus"] = "statsbomb_match_meta__400"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
        rows.append(r)
    return rows


def main() -> int:
    for r in run():
        eff = "%+.4f" % r["effect"] if r["effect"] is not None else "--"
        p = "%.4g" % r["p"] if r["p"] is not None else "--"
        print("%-42s %-16s n=%-8d effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], eff, p, r.get("note", "")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: verdict thresholds behave as declared."""
    assert _verdict(0.001, 0.5, 0.15) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5, 0.15) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5, 0.15) == "NOT_TESTABLE"
    print("self-check OK")
