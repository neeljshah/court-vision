"""EXPERIMENT: matchup-pace possession volume beyond the model's single opp_pace.

HYPOTHESIS (basketball): counting stats (PTS/REB/AST/FG3M) scale with POSSESSIONS.
The model has an aggregate `opp_pace` conditioner, but the TRUE game pace is a
MATCHUP of BOTH teams' pace identities. A high-pace player's team vs a high-pace
opponent => more possessions => more counting-stat opportunities than `opp_pace`
alone captures. The matchup grid (team_matchup_outcome.json) finds totals are
roughly additive (b1~1.03) with a weak super-additive interaction (b2=0.024,
t=1.22). So test: own-team as-of pace + opp as-of pace (+ interaction), keyed
(player_id, date), as a residual tilt on the leak-free `pred`.

LEAK-FREE: team as-of pace = expanding mean of the team's OWN per-game pace over
its PRIOR games this season (min 3; cold-start falls back to the team's prior-
season mean). Built from data/nba/season_games_<season>.json home_pace/away_pace
(each game gives the team's own pace estimate). The player's team & opponent are
resolved from the game_id (pregame_oof) -> season_games home/away, with a corpus
`opp`+venue fallback.

ORTHOGONALITY: the load-bearing screen. The model ALREADY has `opp_pace`, so the
matchup signal can only add edge via the part orthogonal to it -- chiefly the
player's OWN-team pace and the interaction. We report:
  - corr(signal, actual-pred)                      (raw residual corr)
  - partial corr(signal, resid | model_opp_pace)   (NEW info beyond opp_pace)
If the partial corr ~ 0, the model already prices the matchup; fast-reject.

GRADING: pred_adj = pred * (1 + gamma * sig_z)  OR  pred + beta * sig, fit on the
EARLY half, graded on the HELD-OUT LATE half, per stat, on >=2 INDEPENDENT corpora
(Family A benashkar/extended_oos AND Family B oddsapi-25-26 OR Family C
oddsapi-24-25). drop |odds|<100 (grader does it), coherence guard, reg-season.

Read-only except this file + scratch. No production code, no git commit.
Run: conda run -n basketball_ai python scripts/pit/exp_matchup_pace.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_grade as ig  # noqa: E402

ROOT = ig.ROOT
STATS = ["ast", "reb", "pts", "fg3m"]
SEASONS = ("2023-24", "2024-25", "2025-26")
MIN_PRIOR = 3  # min prior games before an as-of team pace is trusted


# --------------------------------------------------------------------------- #
# 1. Leak-free as-of team pace (expanding mean over PRIOR games this season)
# --------------------------------------------------------------------------- #
def _team_game_pace_log() -> pd.DataFrame:
    recs = []
    for season in SEASONS:
        p = os.path.join(ROOT, "data", "nba", f"season_games_{season}.json")
        sg = json.load(open(p, encoding="utf-8"))
        rows = sg["rows"] if isinstance(sg, dict) else sg
        for r in rows:
            if not r.get("home_team") or not r.get("away_team"):
                continue
            d = pd.Timestamp(r["game_date"]).normalize()
            if r.get("home_pace") is not None:
                recs.append((r["home_team"], season, d, float(r["home_pace"])))
            if r.get("away_pace") is not None:
                recs.append((r["away_team"], season, d, float(r["away_pace"])))
    return pd.DataFrame(recs, columns=["team", "season", "date", "pace"]).sort_values(
        ["team", "season", "date"]).reset_index(drop=True)


def build_asof_team_pace() -> dict:
    """(team, season, date) -> as-of pace = expanding mean of PRIOR games this
    season (shift(1)). Cold-start (< MIN_PRIOR prior games) falls back to the
    team's PRIOR-season full mean (leak-free: prior season is fully in the past).
    Returns nested dict {team: {season: {date: pace_asof}}} plus a season-mean map.
    """
    log = _team_game_pace_log()
    prev_season_mean = {}  # (team, season) -> prior season full mean
    season_order = {s: i for i, s in enumerate(SEASONS)}
    full_mean = log.groupby(["team", "season"])["pace"].mean().to_dict()
    league_season_mean = log.groupby("season")["pace"].mean().to_dict()

    out: dict = {}
    for (team, season), grp in log.groupby(["team", "season"]):
        grp = grp.sort_values("date")
        expanding_prior = grp["pace"].expanding().mean().shift(1)  # strictly prior
        prior_count = np.arange(len(grp))  # number of games strictly before
        # prior-season fallback
        prev_s = None
        si = season_order[season]
        if si > 0:
            cand = SEASONS[si - 1]
            if (team, cand) in full_mean:
                prev_s = full_mean[(team, cand)]
        league_fb = league_season_mean.get(season, np.nanmean(list(league_season_mean.values())))
        d = out.setdefault(team, {}).setdefault(season, {})
        for i, (dt, ep) in enumerate(zip(grp["date"].values, expanding_prior.values)):
            if prior_count[i] >= MIN_PRIOR and np.isfinite(ep):
                val = ep
            elif prev_s is not None:
                val = prev_s
            elif np.isfinite(ep):
                val = ep
            else:
                val = league_fb
            d[pd.Timestamp(dt).normalize()] = float(val)
    return out


_ASOF = None


def asof_pace(team, season, date):
    global _ASOF
    if _ASOF is None:
        _ASOF = build_asof_team_pace()
    try:
        return _ASOF[team][season].get(pd.Timestamp(date).normalize())
    except KeyError:
        return None


# --------------------------------------------------------------------------- #
# 2. player_team / opp_team resolution (game_id -> season_games home/away)
# --------------------------------------------------------------------------- #
def _games_index() -> dict:
    games = {}
    for season in SEASONS:
        p = os.path.join(ROOT, "data", "nba", f"season_games_{season}.json")
        sg = json.load(open(p, encoding="utf-8"))
        for r in (sg["rows"] if isinstance(sg, dict) else sg):
            if not r.get("home_team") or not r.get("away_team"):
                continue
            games[str(r["game_id"])] = {
                "home": r["home_team"], "away": r["away_team"],
                "season": season, "date": pd.Timestamp(r["game_date"]).normalize(),
            }
    return games


def _oof_gameid_map() -> dict:
    oof = pd.read_parquet(os.path.join(ROOT, "data", "cache", "pregame_oof.parquet"))
    oof["d"] = pd.to_datetime(oof["game_date"]).dt.normalize()
    m = {}
    for r in oof.itertuples(index=False):
        m[(int(r.player_id), r.d, r.stat)] = str(r.game_id)
    return m


_GAMES = None
_OOFMAP = None


def resolve_teams(b):
    """Return (player_team, opp_team, season) for a bet, leak-free.
    Primary: game_id (pregame_oof) -> season_games home/away + is_home.
    Fallback: corpus opp + venue -> infer player's team's game on that date.
    """
    global _GAMES, _OOFMAP
    if _GAMES is None:
        _GAMES = _games_index()
    if _OOFMAP is None:
        _OOFMAP = _oof_gameid_map()
    gid = _OOFMAP.get((b["pid"], b["gdate"], b["stat"]))
    if gid and gid in _GAMES:
        g = _GAMES[gid]
        is_home = b.get("is_home")
        if is_home is not None and np.isfinite(is_home):
            if int(is_home) == 1:
                return g["home"], g["away"], g["season"]
            return g["away"], g["home"], g["season"]
        # no is_home: opp tells us which side the player is NOT on
        opp = b.get("opp", "")
        if opp == g["home"]:
            return g["away"], g["home"], g["season"]
        if opp == g["away"]:
            return g["home"], g["away"], g["season"]
        # default to home if ambiguous
        return g["home"], g["away"], g["season"]
    return None, None, None


# --------------------------------------------------------------------------- #
# 3. Attach matchup-pace signals to bets (leak-free)
# --------------------------------------------------------------------------- #
def attach_matchup_pace(bets):
    """Adds to each bet (when resolvable):
      team_pace_asof, opp_pace_asof  (own + opponent as-of game pace)
      mp_sum   = team_pace_asof + opp_pace_asof           (additive game pace)
      mp_inter = (team-LM)*(opp-LM)                        (super-additive term)
      mp_team_only = team_pace_asof (the NEW orthogonal piece vs model opp_pace)
    plus league-mean-centered z versions appended in run-time per split.
    """
    n_res = n_pace = 0
    for b in bets:
        pteam, oteam, season = resolve_teams(b)
        if pteam is None:
            continue
        n_res += 1
        tp = asof_pace(pteam, season, b["gdate"])
        op = asof_pace(oteam, season, b["gdate"])
        b["player_team"] = pteam
        b["opp_team"] = oteam
        if tp is None or op is None:
            continue
        n_pace += 1
        b["team_pace_asof"] = tp
        b["opp_pace_asof"] = op
        b["mp_sum"] = tp + op
        b["mp_team_only"] = tp
    print(f"    matchup-pace: teams resolved {n_res}/{len(bets)}, "
          f"pace attached {n_pace}/{len(bets)}")
    return bets


# --------------------------------------------------------------------------- #
# 4. Orthogonality screens
# --------------------------------------------------------------------------- #
def _arr(bets, key):
    return np.array([b.get(key, np.nan) for b in bets], float)


def residual_corr(bets, stat, key):
    sub = [b for b in bets if b["stat"] == stat]
    sig = _arr(sub, key)
    resid = np.array([b["actual"] - b.get("pred", np.nan) for b in sub], float)
    m = np.isfinite(sig) & np.isfinite(resid)
    if m.sum() < 30 or np.std(sig[m]) < 1e-9:
        return None, int(m.sum())
    return float(np.corrcoef(sig[m], resid[m])[0, 1]), int(m.sum())


def partial_corr(bets, stat, key, control="opp_pace"):
    """Partial corr(signal, resid | control) -- residualize both signal and the
    target residual on the model's existing conditioner, then correlate. This is
    the NEW-information-beyond-opp_pace test."""
    sub = [b for b in bets if b["stat"] == stat]
    sig = _arr(sub, key)
    ctrl = _arr(sub, control)
    resid = np.array([b["actual"] - b.get("pred", np.nan) for b in sub], float)
    m = np.isfinite(sig) & np.isfinite(resid) & np.isfinite(ctrl)
    if m.sum() < 30 or np.std(sig[m]) < 1e-9 or np.std(ctrl[m]) < 1e-9:
        return None, int(m.sum())
    sig, ctrl, resid = sig[m], ctrl[m], resid[m]

    def _resid_on(y, x):
        A = np.vstack([np.ones_like(x), x]).T
        beta, *_ = np.linalg.lstsq(A, y, rcond=None)
        return y - A @ beta

    sig_r = _resid_on(sig, ctrl)
    res_r = _resid_on(resid, ctrl)
    if np.std(sig_r) < 1e-9 or np.std(res_r) < 1e-9:
        return None, int(m.sum())
    return float(np.corrcoef(sig_r, res_r)[0, 1]), int(m.sum())


def corr_signal_vs_oppace(bets, stat, key):
    """How redundant is the matchup signal with the model's opp_pace already?"""
    sub = [b for b in bets if b["stat"] == stat]
    sig = _arr(sub, key)
    op = _arr(sub, "opp_pace")
    m = np.isfinite(sig) & np.isfinite(op)
    if m.sum() < 30 or np.std(sig[m]) < 1e-9 or np.std(op[m]) < 1e-9:
        return None
    return float(np.corrcoef(sig[m], op[m])[0, 1])


# --------------------------------------------------------------------------- #
# 5. Tilt grading (leak-free: fit early, grade late)
# --------------------------------------------------------------------------- #
def split_halves(bets):
    ds = sorted(set(b["gdate"] for b in bets))
    if len(ds) < 4:
        return bets, []
    mid = ds[len(ds) // 2]
    return [b for b in bets if b["gdate"] < mid], [b for b in bets if b["gdate"] >= mid]


def fit_beta_additive(rows, stat, key):
    sub = [b for b in rows if b["stat"] == stat and np.isfinite(b.get(key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 50:
        return None, 0
    sig = np.array([b[key] for b in sub], float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], float)
    if np.std(sig) < 1e-9:
        return None, len(sub)
    return float(np.cov(sig, resid)[0, 1] / np.var(sig)), len(sub)


def fit_z(rows, stat, key):
    """mean/std of signal on the TRAIN split (for z-scoring the multiplicative tilt)."""
    vals = [b[key] for b in rows if b["stat"] == stat and np.isfinite(b.get(key, np.nan))]
    if len(vals) < 50:
        return None, None
    return float(np.mean(vals)), float(np.std(vals) or 1.0)


def fit_gamma_mult(rows, stat, key, mu, sd):
    """Fit gamma so pred*(1+gamma*z) reduces residual: regress (actual-pred) on
    pred*z (no intercept) => gamma = sum(r*pz)/sum(pz^2)."""
    sub = [b for b in rows if b["stat"] == stat and np.isfinite(b.get(key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 50:
        return None
    pred = np.array([b["pred"] for b in sub], float)
    sig = np.array([b[key] for b in sub], float)
    z = (sig - mu) / (sd or 1.0)
    pz = pred * z
    r = np.array([b["actual"] - b["pred"] for b in sub], float)
    denom = float(np.sum(pz * pz))
    if denom < 1e-9:
        return None
    return float(np.sum(r * pz) / denom)


def grade_tilt(late, stat, key, *, beta=None, gamma=None, mu=None, sd=None, edge_min=0.0):
    sub = [b for b in late if b["stat"] == stat and np.isfinite(b.get(key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    flips = 0
    for b in sub:
        if beta is not None:
            adj = b["pred"] + beta * b[key]
        else:
            z = (b[key] - mu) / (sd or 1.0)
            adj = b["pred"] * (1.0 + gamma * z)
        b["_pred_adj"] = adj
        if (b["pred"] > b["line"]) != (adj > b["line"]):
            flips += 1
    raw = ig.roi(sub, predictor="pred", edge_min=edge_min)
    adj = ig.roi(sub, predictor="_pred_adj", edge_min=edge_min)
    return raw, adj, flips, len(sub)


# --------------------------------------------------------------------------- #
# 6. Drivers
# --------------------------------------------------------------------------- #
def prepare_with_pace(corpus):
    bets = ig.prepare(corpus)
    bets = attach_matchup_pace(bets)
    return bets


def orthogonality_block(bets, corpus):
    print(f"\n{'='*74}\n ORTHOGONALITY  ({corpus})\n{'='*74}")
    keys = [("mp_team_only", "own-team as-of pace (NEW)"),
            ("opp_pace_asof", "opp as-of pace (my build)"),
            ("mp_sum", "matchup sum (team+opp)")]
    for stat in STATS:
        n = len([b for b in bets if b["stat"] == stat and np.isfinite(b.get("mp_sum", np.nan))])
        if n < 50:
            print(f"  {stat.upper():5s} n={n} (too few, skip)")
            continue
        print(f"  {stat.upper()} (n={n}):")
        for key, lab in keys:
            r, nr = residual_corr(bets, stat, key)
            pr, npr = partial_corr(bets, stat, key, control="opp_pace")
            red = corr_signal_vs_oppace(bets, stat, key)
            flag = ""
            if pr is not None and abs(pr) >= 0.05:
                flag = "  <== NEW info beyond opp_pace"
            rs = "n/a" if r is None else f"{r:+.3f}"
            prs = "n/a" if pr is None else f"{pr:+.3f}"
            reds = "n/a" if red is None else f"{red:+.2f}"
            print(f"     {lab:26s} corr(resid)={rs}  partial|opp_pace={prs}  "
                  f"redund(vs model opp_pace)={reds}{flag}")


def grading_block(bets, corpus, fit_corpus_bets=None, label=""):
    """If fit_corpus_bets is None: in-corpus early->late. Else fit on fit_corpus
    (full) and grade on `bets` (cross-corpus)."""
    print(f"\n{'='*74}\n GRADING  {label or corpus}\n{'='*74}")
    keys = [("mp_sum", "matchup-sum"), ("mp_team_only", "own-team pace"),
            ("opp_pace_asof", "opp-pace(asof)")]
    for stat in STATS:
        nstat = len([b for b in bets if b["stat"] == stat and np.isfinite(b.get("mp_sum", np.nan))])
        if nstat < 40:
            continue
        print(f"\n  --- {stat.upper()} (gradeable n={nstat}) ---")
        if fit_corpus_bets is None:
            early, late = split_halves(bets)
        else:
            early, late = fit_corpus_bets, bets
        for key, lab in keys:
            # additive tilt
            beta, nb = fit_beta_additive(early, stat, key)
            # multiplicative tilt
            mu, sd = fit_z(early, stat, key)
            gamma = fit_gamma_mult(early, stat, key, mu, sd) if mu is not None else None
            if beta is not None:
                raw, adj, flips, ng = grade_tilt(late, stat, key, beta=beta)
                d = adj["roi_pct"] - raw["roi_pct"]
                print(f"    [{lab:13s}] ADD  beta={beta:+.4f}  "
                      f"raw {raw['roi_pct']:+6.2f}%(n{raw['n']}) -> adj {adj['roi_pct']:+6.2f}% "
                      f"[flips {flips}/{ng}]  d={d:+.2f}pp")
            if gamma is not None:
                raw, adj, flips, ng = grade_tilt(late, stat, key, gamma=gamma, mu=mu, sd=sd)
                d = adj["roi_pct"] - raw["roi_pct"]
                print(f"    [{lab:13s}] MULT gamma={gamma:+.4f} "
                      f"raw {raw['roi_pct']:+6.2f}%(n{raw['n']}) -> adj {adj['roi_pct']:+6.2f}% "
                      f"[flips {flips}/{ng}]  d={d:+.2f}pp")


def main():
    print("Building leak-free as-of team pace...")
    build_asof_team_pace()
    print("done.")

    # ---- Family A: extended_oos (== benashkar joined set), the big sample ----
    A = prepare_with_pace("extended_oos_canonical.csv")
    cohA = ig.coherence(A)
    print(f"  [A extended_oos] coherence sum {cohA['sum']:+.2f}% "
          f"({'OK' if cohA['coherent'] else 'CORRUPT'}) n={len(A)}")
    assert cohA["coherent"], "Family A corrupt"
    orthogonality_block(A, "extended_oos (Family A)")
    grading_block(A, "extended_oos (Family A)", label="extended_oos early->late (HELD-OUT)")

    # ---- Family B: oddsapi 2025-26 (independent same-season, thin) ----
    B = prepare_with_pace("regular_season_2025_26_oddsapi.csv")
    cohB = ig.coherence(B)
    print(f"\n  [B oddsapi-25-26] coherence sum {cohB['sum']:+.2f}% "
          f"({'OK' if cohB['coherent'] else 'CORRUPT'}) n={len(B)}")
    if cohB["coherent"]:
        orthogonality_block(B, "oddsapi-25-26 (Family B)")
        # fit on full Family A, grade on B (cross-corpus held-out)
        grading_block(B, "oddsapi-25-26", fit_corpus_bets=A,
                      label="fit FamilyA -> grade oddsapi-25-26 (Family B, cross-book)")

    # ---- Family C: oddsapi 2024-25 (independent cross-season) ----
    C = prepare_with_pace("regular_season_2024_25_oddsapi.csv")
    cohC = ig.coherence(C)
    print(f"\n  [C oddsapi-24-25] coherence sum {cohC['sum']:+.2f}% "
          f"({'OK' if cohC['coherent'] else 'CORRUPT'}) n={len(C)}")
    if cohC["coherent"]:
        orthogonality_block(C, "oddsapi-24-25 (Family C)")
        grading_block(C, "oddsapi-24-25", fit_corpus_bets=A,
                      label="fit FamilyA -> grade oddsapi-24-25 (Family C, cross-season)")


if __name__ == "__main__":
    main()
