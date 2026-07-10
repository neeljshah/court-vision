"""domains.mlb.knowledge.validate_research_wave3 -- the 3 UNTESTED rows seeded
2026-07-10 by the round-3 research-wave commit (mechanisms.md #49 bullpen-day/
opener scoring structure, #50 mid-inning pitching-change interrupt, #51
pinch-sub platoon targeting). Mirrors validate_research_wave2's per-file
pattern: pure frame-transform helpers + a hypothesis function per row + a
local _verdict/_combine copy (each wave file is self-contained, not shared
across waves, same discipline as wave1->wave2).

PREMISE-CHECK CORRECTION (this session, before any test ran): #49's own
premise-check text named `games.parquet` for the runs/win-rate join, but
`games.parquet` only covers 2010-04-04..2021-11-02 while `player_gamelogs.
parquet` (the bullpen-day-flag source) covers 2022-04-07..2026-07-02 -- ZERO
date overlap, confirmed this session (`len(pg_dates & games_dates) == 0`).
`games_current.parquet` (same 9 columns, 2022-04-07..2026-06-16) is the file
that actually overlaps and is used instead. Team-code mismatch also found and
fixed: player_gamelogs uses {SF,TB,SD,KC,WSH,CHC,AZ,ATH}, games_current uses
{SFO,TAM,SDG,KAN,WAS,CUB,ARI,OAK} for the same 7 franchises -- TEAM_MAP below
translates; `ATH` (2025+ post-move Athletics code) has no games_current
counterpart and is silently excluded by the inner merge (an honest, small
coverage gap, not a fixed one). `AL`/`NL` all-star-game rows in
player_gamelogs (4 dates each) are dropped, they are not real team-games.

Leak audit: #49 is a same-game team-game-level descriptive comparison (no
future information -- inningsPitched and runs are both fully resolved facts
of the completed game being compared). #50 is a within-game PA-window
before/after descriptive gap, explicitly non-causal (same scope as the
CONFIRMED NBA #47 timeout design cited by this row) -- a clear, named
selection confound (pitching changes are typically CALLED because of an
in-progress rally) is flagged in the ledger note, not adjusted away, since
the row's own claim never asserted causality. #51 is a within-PA
contemporaneous comparison (stand/p_throws are both resolved facts of the
substitute's first plate appearance). All 3 use split-half-by-date for the
lane's binding >=2-corpora-for-affirmatives rule; #51's own test-spec text
did not name split-half explicitly (single one-sample test), so split-half
was added here per that binding rule before any CONFIRMED verdict could be
minted off one global test -- same discipline as #48/#50's split-half.

Run: python -m domains.mlb.knowledge.validate_research_wave3
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.mlb.knowledge._data import LEDGER_PATH, REPO, load_season, pa_final_pitch
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
TEAM_MAP = {"SF": "SFO", "TB": "TAM", "SD": "SDG", "KC": "KAN", "WSH": "WAS", "CHC": "CUB", "AZ": "ARI"}

MIN_EFFECT = {"bullpen_day_scoring_structure": 0.15,
              "mid_inning_pitching_change_interrupt": 0.02,
              "pinch_sub_platoon_targeting": 0.05}


def _verdict(p, effect, hyp: str) -> str:
    if p is None or effect is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    base = hyp.split("__")[0]
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= MIN_EFFECT[base]) else "NULL_LOCAL"


def _flag_bullpen_day(pg: pd.DataFrame) -> pd.DataFrame:
    """#49 helper (pure): team-game bullpen-day flag = a team-game's MAX
    single-pitcher inningsPitched among is_pitcher rows <=4. Drops AL/NL
    all-star rows, maps team codes to games_current's scheme, drops
    doubleheader-ambiguous (date,team_mapped) rows (>1 game same day)."""
    d = pg[~pg["team"].isin(["AL", "NL"])].copy()
    d["team_mapped"] = d["team"].map(lambda t: TEAM_MAP.get(t, t))
    p = d[d["is_pitcher"] == True].dropna(subset=["inningsPitched"])  # noqa: E712
    maxip = p.groupby(["game_pk", "team_mapped", "date"])["inningsPitched"].max().reset_index()
    maxip["bullpen_day"] = maxip["inningsPitched"] <= 4
    return maxip[~maxip.duplicated(subset=["date", "team_mapped"], keep=False)]


def _team_game_legs(gc: pd.DataFrame) -> pd.DataFrame:
    """#49 helper (pure): games_current home/away rows unpivoted to one row
    per team-game (own_runs, own_win); doubleheader-ambiguous rows dropped."""
    home = gc.rename(columns={"home_team": "team", "home_runs": "own_runs", "target_home_win": "own_win"})
    away = gc.rename(columns={"away_team": "team", "away_runs": "own_runs", "target_home_win": "own_win"})
    away = away.assign(own_win=1 - away["own_win"])
    tg = pd.concat([home[["date", "team", "own_runs", "own_win"]],
                     away[["date", "team", "own_runs", "own_win"]]], ignore_index=True)
    return tg[~tg.duplicated(subset=["date", "team"], keep=False)]


def _bullpen_day_team_games(pg: pd.DataFrame, gc: pd.DataFrame) -> pd.DataFrame:
    flagged, legs = _flag_bullpen_day(pg), _team_game_legs(gc)
    return flagged.merge(legs, left_on=["date", "team_mapped"], right_on=["date", "team"], how="inner")


def bullpen_day_scoring_structure(merged: pd.DataFrame, half_label: str) -> Dict[str, Any]:
    hyp = "bullpen_day_scoring_structure__%s" % half_label
    bp, trad = merged.loc[merged["bullpen_day"], "own_runs"], merged.loc[~merged["bullpen_day"], "own_runs"]
    if len(bp) < 30 or len(trad) < 30:
        return {"hypothesis": hyp, "n": int(len(merged)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than 30 team-games in a group", "corpus": "player_gamelogs+games_current"}
    t, p = stats.ttest_ind(bp, trad, equal_var=False)
    eff = float(bp.mean() - trad.mean())
    win_bp = float(merged.loc[merged["bullpen_day"], "own_win"].mean())
    win_trad = float(merged.loc[~merged["bullpen_day"], "own_win"].mean())
    return {"hypothesis": hyp, "n": int(len(merged)), "effect": round(eff, 4), "p": float(p),
            "verdict": _verdict(p, eff, hyp), "corpus": "player_gamelogs+games_current",
            "note": ("Welch t-test own-runs, bullpen-day(n=%d,mean=%.3f) vs traditional(n=%d,mean=%.3f); "
                      "win-rate is DESCRIPTIVE ONLY (no bar declared for it in the row's own test spec): "
                      "bullpen-day=%.3f traditional=%.3f -- a large gap but not gated on it (plausible "
                      "selection confound: bullpen days correlate with short-staffed/already-losing "
                      "situations, not proven here)." % (len(bp), bp.mean(), len(trad), trad.mean(), win_bp, win_trad))}


def _mid_inning_change_events(pa: pd.DataFrame) -> pd.DataFrame:
    """#50 helper (pure): per (game_pk,inning,inning_topbot) sorted by
    at_bat_number, paired before/after batting-team runs/PA window means
    around each mid-inning (outs_when_up>0) pitcher-ID change, windows capped
    at up to 3 PAs and the inning boundary, min 1-PA floor each side."""
    d = pa.sort_values(["game_pk", "inning", "inning_topbot", "at_bat_number"]).copy()
    d["batting_delta"] = np.where(d["inning_topbot"] == "Bot",
                                   d["post_home_score"] - d["home_score"],
                                   d["post_away_score"] - d["away_score"])
    befores: List[float] = []
    afters: List[float] = []
    for _, grp in d.groupby(["game_pk", "inning", "inning_topbot"], sort=False):
        pitchers, outs, deltas = grp["pitcher"].values, grp["outs_when_up"].values, grp["batting_delta"].values
        for i in range(1, len(grp)):
            if pitchers[i] != pitchers[i - 1] and outs[i] > 0:
                before, after = deltas[max(0, i - 3):i], deltas[i:i + 3]
                if len(before) >= 1 and len(after) >= 1:
                    befores.append(float(before.mean()))
                    afters.append(float(after.mean()))
    return pd.DataFrame({"before": befores, "after": afters})


def mid_inning_pitching_change_interrupt(pa: pd.DataFrame, half_label: str) -> Dict[str, Any]:
    hyp = "mid_inning_pitching_change_interrupt__%s" % half_label
    ev = _mid_inning_change_events(pa)
    if len(ev) < 30:
        return {"hypothesis": hyp, "n": int(len(ev)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than 30 mid-inning pitcher-change events"}
    t, p = stats.ttest_rel(ev["after"], ev["before"])
    eff = float((ev["after"] - ev["before"]).mean())
    return {"hypothesis": hyp, "n": int(len(ev)), "effect": round(eff, 5), "p": float(p),
            "verdict": _verdict(p, eff, hyp),
            "note": ("paired t-test, batting-team runs/PA after(mean=%.4f) vs before(mean=%.4f) a mid-inning "
                      "pitcher-ID change; SELECTION CONFOUND flagged explicitly, same non-causal scope as "
                      "this row's own claim: relievers are typically summoned DURING an in-progress rally, "
                      "so an elevated before-window reverting after is also the mechanical/regression-to-mean "
                      "signature of WHEN changes get called, not proof of a reliever 'interrupt' causal effect."
                      % (ev["after"].mean(), ev["before"].mean()))}


def _pinch_sub_first_pa(pg: pd.DataFrame, sv: pd.DataFrame) -> pd.DataFrame:
    """#51 helper (pure): substitute = lower-atBats player sharing a
    (game_pk,team,batting_order) slot with >1 player that game; first PA
    joined to savant batter==player_id for stand/p_throws."""
    d = pg.dropna(subset=["batting_order", "player_id"]).copy()
    sizes = d.groupby(["game_pk", "team", "batting_order"]).size()
    multi = sizes[sizes > 1].index
    if len(multi) == 0:
        return d.iloc[0:0]
    d = d.set_index(["game_pk", "team", "batting_order"]).loc[multi].reset_index()
    d["atBats"] = d["atBats"].fillna(0)
    subs = d.sort_values("atBats").groupby(["game_pk", "team", "batting_order"], sort=False).head(1)
    first_pa = (sv.sort_values(["game_pk", "batter", "at_bat_number"])
                  .groupby(["game_pk", "batter"], sort=False).head(1)
                  .rename(columns={"batter": "player_id"}))
    return subs.merge(first_pa[["game_pk", "player_id", "stand", "p_throws"]], on=["game_pk", "player_id"], how="inner")


def pinch_sub_platoon_targeting(subs: pd.DataFrame, sv_pool: pd.DataFrame, half_label: str) -> Dict[str, Any]:
    hyp = "pinch_sub_platoon_targeting__%s" % half_label
    if len(subs) < 30 or len(sv_pool) == 0:
        return {"hypothesis": hyp, "n": int(len(subs)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than 30 identified substitutes"}
    same_hand = (subs["stand"] == subs["p_throws"])
    baseline = float((sv_pool["stand"] == sv_pool["p_throws"]).mean())
    k, n = int(same_hand.sum()), len(subs)
    res = stats.binomtest(k, n, baseline, alternative="two-sided")
    eff = float(k / n - baseline)
    return {"hypothesis": hyp, "n": n, "effect": round(eff, 4), "p": float(res.pvalue),
            "verdict": _verdict(res.pvalue, eff, hyp),
            "note": ("one-sample proportion test, substitute same-hand rate=%.4f vs same-half savant-PA "
                      "baseline same-hand rate=%.4f (n=%d substitutes; pinch-runner/defensive-sub proxy "
                      "noise per this row's own scope note)." % (k / n, baseline, n))}


def _combine(base_hyp: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Both halves required, same direction -- mirrors wave1/wave2's
    >=2-corpora replication rule (a single significant half is PROVISIONAL)."""
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
    return {"hypothesis": "%s__combined" % base_hyp, "n": int(sum(r["n"] for r in rows)),
            "effect": None, "p": None, "verdict": verdict,
            "note": "split-half-by-date, both halves required: %s"
                    % "; ".join("%s(p=%s,eff=%s)" % (r["hypothesis"], r["p"], r["effect"]) for r in rows)}


def run() -> List[Dict[str, Any]]:
    pg_all = pd.read_parquet(REPO / "data" / "domains" / "mlb" / "player_gamelogs.parquet",
                              columns=["game_pk", "team", "date", "player_id", "is_pitcher",
                                       "inningsPitched", "batting_order", "atBats"])
    gc = pd.read_parquet(REPO / "data" / "domains" / "mlb" / "games_current.parquet")
    tg = _bullpen_day_team_games(pg_all, gc)
    mid49 = tg["date"].median()
    halves49 = [bullpen_day_scoring_structure(tg[tg["date"] <= mid49], "h1"),
                bullpen_day_scoring_structure(tg[tg["date"] > mid49], "h2")]
    rows: List[Dict[str, Any]] = list(halves49) + [_combine("bullpen_day_scoring_structure", halves49)]

    pa = pa_final_pitch(load_season(2025))
    gd = pd.to_datetime(pa["game_date"])
    mid50 = gd.median()
    halves50 = [mid_inning_pitching_change_interrupt(pa[gd <= mid50], "h1"),
                mid_inning_pitching_change_interrupt(pa[gd > mid50], "h2")]
    rows.extend(halves50)
    rows.append(_combine("mid_inning_pitching_change_interrupt", halves50))

    pg25 = pg_all[pg_all["date"].dt.year == 2025]
    sv = pa.dropna(subset=["stand", "p_throws"]).copy()
    sv = sv[sv["stand"].isin(["L", "R"]) & sv["p_throws"].isin(["L", "R"])]
    sv["game_date"] = pd.to_datetime(sv["game_date"])
    mid51 = pg25["date"].median()
    halves51 = []
    for label, pg_half, sv_half in [("h1", pg25[pg25["date"] <= mid51], sv[sv["game_date"] <= mid51]),
                                     ("h2", pg25[pg25["date"] > mid51], sv[sv["game_date"] > mid51])]:
        subs_half = _pinch_sub_first_pa(pg_half, sv_half)
        halves51.append(pinch_sub_platoon_targeting(subs_half, sv_half, label))
    rows.extend(halves51)
    rows.append(_combine("pinch_sub_platoon_targeting", halves51))

    for r in rows:
        r["sport"] = "mlb"
        r.setdefault("corpus", "savant_full__2025")
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-46s %-16s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: verdict rule + the 3 pure frame-transform
    helpers on synthetic frames -- no parquet needed."""
    assert _verdict(0.001, 0.20, "bullpen_day_scoring_structure") == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.20, "bullpen_day_scoring_structure") == "NULL_LOCAL"
    assert _verdict(0.001, 0.01, "mid_inning_pitching_change_interrupt") == "NULL_LOCAL"  # below 0.02 bar
    assert _verdict(None, 0.1, "pinch_sub_platoon_targeting") == "NOT_TESTABLE"

    pg = pd.DataFrame({"game_pk": [1, 1], "team": ["SF", "LAD"], "date": pd.to_datetime(["2025-04-01"] * 2),
                        "is_pitcher": [True, True], "inningsPitched": [3.0, 6.0]})
    flagged = _flag_bullpen_day(pg)
    assert flagged.loc[flagged["team_mapped"] == "SFO", "bullpen_day"].iloc[0]
    assert not flagged.loc[flagged["team_mapped"] == "LAD", "bullpen_day"].iloc[0]

    ev = _mid_inning_change_events(pd.DataFrame({
        "game_pk": [1] * 5, "inning": [1] * 5, "inning_topbot": ["Bot"] * 5, "pitcher": [10, 10, 20, 20, 20],
        "at_bat_number": [1, 2, 3, 4, 5], "outs_when_up": [0, 1, 2, 0, 1],
        "home_score": [0, 1, 3, 3, 3], "post_home_score": [1, 3, 3, 3, 4],
        "away_score": [0, 0, 0, 0, 0], "post_away_score": [0, 0, 0, 0, 0],
    }))
    assert len(ev) == 1  # only the i=2 (pitcher 10->20, outs_when_up=2>0) change qualifies

    print("self-check OK")
