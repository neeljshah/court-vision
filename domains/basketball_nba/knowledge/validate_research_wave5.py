"""domains.basketball_nba.knowledge.validate_research_wave5 -- the 1 NBA
literature-sourced UNTESTED row seeded 2026-07-10 by the round-5 research-wave
commit (29628281, mechanisms.md row #55): between-game starting-lineup
continuity streak vs that game's point differential.

PREMISE CHECK (this session, fresh): `stints_2023_24.parquet` /
`stints_2024_25.parquet` columns game_id/team_id/period/lineup_key/start_s/
pts_for/pts_against confirmed. Opening lineup (first period==1 stint by
start_s) gives exactly 2,460 team-game rows/season (30 teams x 1,230 games)
in BOTH seasons, matching the row's premise text. lineup_key strings are
always numerically-sorted player ids (verified on a 50-row sample), so raw
string equality is a valid same-lineup test -- no re-sorting needed.

continuity_streak: for each team's games in game_id order, the count of
CONSECUTIVE prior games with the identical opening lineup_key as the current
game -- computed as within-run cumcount() (a lineup_key run of length k
starting a new streak has cumcount 0, 1, ..., k-1 at each successive game,
which is exactly "count of consecutive prior games with this same lineup").

Run: python -m domains.basketball_nba.knowledge.validate_research_wave5
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
from scipy import stats

from domains.basketball_nba.knowledge._data import LEDGER_PATH
from domains.basketball_nba.knowledge.validate_lineup_composition import STINTS_DIR
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_ABS_R = 0.05
MIN_TEAM_GAMES = 3


def _verdict(p, effect) -> str:
    if p is None or effect is None or p != p:
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= MIN_ABS_R) else "NULL_LOCAL"


def build_team_game_frame(stints: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_id, team_id): opening lineup_key + that team-game's
    point differential (summed pts_for/pts_against across ALL periods)."""
    opening = (stints[stints["period"] == 1]
               .sort_values(["game_id", "team_id", "start_s"], kind="mergesort")
               .groupby(["game_id", "team_id"], as_index=False).first()[["game_id", "team_id", "lineup_key"]])
    totals = stints.groupby(["game_id", "team_id"], as_index=False)[["pts_for", "pts_against"]].sum()
    totals["point_diff"] = totals["pts_for"] - totals["pts_against"]
    return opening.merge(totals[["game_id", "team_id", "point_diff"]], on=["game_id", "team_id"], how="inner")


def _streak_within_team(lineup_keys: pd.Series) -> pd.Series:
    """Consecutive-prior-identical-lineup count, per game, within one team's
    chronologically-sorted lineup_key series."""
    same_as_prev = lineup_keys == lineup_keys.shift()
    run_id = (~same_as_prev).cumsum()
    return lineup_keys.groupby(run_id).cumcount()


def add_continuity_streak(tg: pd.DataFrame) -> pd.DataFrame:
    tg = tg.sort_values(["team_id", "game_id"], kind="mergesort").copy()
    tg["continuity_streak"] = tg.groupby("team_id", group_keys=False)["lineup_key"].apply(_streak_within_team)
    return tg


def lineup_continuity_streak_vs_point_diff(tg: pd.DataFrame, season_label: str) -> Dict[str, Any]:
    hyp = "lineup_continuity_streak_vs_point_diff__%s" % season_label
    if len(tg) < MIN_TEAM_GAMES:
        return {"hypothesis": hyp, "n": int(len(tg)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than %d team-game rows" % MIN_TEAM_GAMES}
    r, p = stats.pearsonr(tg["continuity_streak"], tg["point_diff"])
    return {"hypothesis": hyp, "n": int(len(tg)), "effect": round(float(r), 4), "p": float(p),
            "verdict": _verdict(p, r),
            "note": "pearson r, opening-lineup continuity streak vs team-game point differential, "
                    "n=%d team-games, season=%s, mean streak=%.2f" % (len(tg), season_label, tg["continuity_streak"].mean())}


def _combine(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Both seasons required, same sign -- house >=2-corpora replication rule."""
    testable = [r for r in rows if r["verdict"] != "NOT_TESTABLE"]
    sig = [r for r in testable if r["verdict"] == "CONFIRMED_LOCAL"]
    if len(testable) < 2:
        verdict = "NOT_TESTABLE"
    elif len(sig) == 2 and len({1 if r["effect"] > 0 else -1 for r in sig}) == 1:
        verdict = "CONFIRMED_LOCAL"
    elif len(sig) == 1:
        verdict = "PROVISIONAL"
    else:
        verdict = "NULL_LOCAL"
    return {"hypothesis": "lineup_continuity_streak_vs_point_diff__combined", "n": int(sum(r["n"] for r in rows)),
            "effect": None, "p": None, "verdict": verdict,
            "note": "2023-24 vs 2024-25 independent-corpora legs, both required same sign: %s"
                    % "; ".join("%s(verdict=%s,p=%s,eff=%s)" % (r["hypothesis"], r["verdict"], r["p"], r["effect"])
                                for r in rows)}


def run() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    per_season = []
    for season in ("2023_24", "2024_25"):
        stints = pd.read_parquet(STINTS_DIR / ("stints_%s.parquet" % season))
        tg = add_continuity_streak(build_team_game_frame(stints))
        r = lineup_continuity_streak_vs_point_diff(tg, season.replace("_", "-"))
        per_season.append(r)
        rows.append(r)
    rows.append(_combine(per_season))
    for r in rows:
        r["sport"] = "nba"
        r.setdefault("corpus", "stints_2023_24+2024_25")
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-58s %-16s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: streak logic + verdict rule on synthetic frames."""
    assert _verdict(0.001, 0.10) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.10) == "NULL_LOCAL"
    assert _verdict(0.001, 0.01) == "NULL_LOCAL"  # below MIN_ABS_R
    assert _verdict(None, 0.10) == "NOT_TESTABLE"

    tg = pd.DataFrame({
        "game_id": ["g1", "g2", "g3", "g4"], "team_id": [1, 1, 1, 1],
        "lineup_key": ["A", "A", "A", "B"], "point_diff": [5, 3, 1, -2]})
    tg = add_continuity_streak(tg)
    # A,A,A,B -> streaks 0,1,2,0 (each counts consecutive PRIOR identical games)
    assert tg["continuity_streak"].tolist() == [0, 1, 2, 0]
    print("self-check OK")
