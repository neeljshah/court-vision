"""EXPERIMENT (pit, prediction-integration): pregame BLOWOUT-RISK x role tilt.

HYPOTHESIS (basketball): in games projected to be BLOWOUTS (big matchup mismatch)
the favored team's STARTERS sit the 4th quarter -> fewer minutes -> UNDER on their
minutes-sensitive counting props (pts/reb/ast); and the favored team's BENCH players
get garbage-time minutes -> OVER. The leak-free OOF model has no explicit pregame
blowout-risk feature, so this MAY be a new signal -- but blowout risk is partly
encoded in minutes/vacated/usage features, so we must check ORTHOGONALITY first.

LEAK-FREE SIGNAL (prior-games SRS only):
  exp_margin(player) = asof_srs(player_team) - asof_srs(opp) + HCA*(home? +1 : -1)
  asof_srs is a strength-of-schedule-adjusted running margin computed ONLY from games
  strictly before the bet date (rebuilt here from realized team margins; validated
  corr 0.845 vs the repo's season_games as-of srs). For the 2024-25 corpus, where no
  realized-margin league log exists locally, we fall back to season_games as-of srs
  (which that 0.845 check shows is a legitimate as-of quantity).

ROLE (leak-free): as-of L10 minutes already on the bet dict (`l10_min`).
  STARTER := l10_min >= 28 ; BENCH := l10_min <= 22 (gap drops swing rotation).

DIRECTION (basketball):
  favored side  := exp_margin > 0  (player's team expected to win big)
  blowout risk  := |exp_margin|
  STARTER on a likely-blowout side  -> pred DOWN  (sit 4Q)
  BENCH   on a favored blowout side -> pred UP    (garbage-time minutes)
We encode a single signed signal per role and fit an additive beta (cov/var) on an
EARLY split, apply to a disjoint LATE split, and grade ROI lift vs raw `pred`.

Also: a pure UNDER-SELECTION filter -- starters in the top-quartile blowout-risk
games, bet UNDER only -- graded vs all starter bets.

DISCIPLINE: read-only except this file + scratch; drop |odds|<100 (grader does it);
coherence guard; reg-season corpora only; >=2 INDEPENDENT corpora (Family A + C);
fit early / grade late; orthogonality pre-screen before grading. No git commit.

Run: conda run -n basketball_ai python scripts/pit/exp_blowout_minutes.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "pit"))
import intel_grade as ig  # noqa: E402

HCA = 2.5          # home-court points
STARTER_MIN = 28.0  # as-of L10 minutes threshold for starter
BENCH_MIN = 22.0    # as-of L10 minutes threshold for bench
STATS = ["pts", "reb", "ast"]
LGLOG = os.path.join(ROOT, "data", "cache", "cv_fix", "leaguegamelog_regular_season.parquet")


# ------------------------------------------------------------------ SRS (2025-26)
def _build_asof_srs_2025_26():
    """Leak-free strength-adjusted running margin per (team, as-of date) from realized
    margins. Returns (asof_srs(team, date), pid_team(pid, date))."""
    df = pd.read_parquet(LGLOG)
    df["d"] = pd.to_datetime(df["GAME_DATE"]).dt.normalize()
    tg = df.groupby(["GAME_ID", "d", "TEAM_ABBREVIATION"], as_index=False)["PTS"].sum()
    g = tg.merge(tg, on="GAME_ID", suffixes=("", "_opp"))
    g = g[g["TEAM_ABBREVIATION"] != g["TEAM_ABBREVIATION_opp"]].copy()
    g["margin"] = g["PTS"] - g["PTS_opp"]
    g = g.sort_values(["d", "GAME_ID"]).reset_index(drop=True)
    games = list(g.itertuples(index=False))

    team_hist = defaultdict(list)
    asof_mov = {}
    for r in games:                       # own as-of avg margin (prior games only)
        prior = team_hist[r.TEAM_ABBREVIATION]
        asof_mov[(r.GAME_ID, r.TEAM_ABBREVIATION)] = float(np.mean(prior)) if prior else 0.0
        team_hist[r.TEAM_ABBREVIATION].append(r.margin)

    opp_hist = defaultdict(list)
    asof_sos = {}
    for r in games:                       # as-of avg of opponents' as-of margin (SOS)
        prior = opp_hist[r.TEAM_ABBREVIATION]
        asof_sos[(r.GAME_ID, r.TEAM_ABBREVIATION)] = float(np.mean(prior)) if prior else 0.0
        opp_hist[r.TEAM_ABBREVIATION].append(asof_mov.get((r.GAME_ID, r.TEAM_ABBREVIATION_opp), 0.0))

    team_date = defaultdict(list)
    for r in games:
        srs = asof_mov[(r.GAME_ID, r.TEAM_ABBREVIATION)] + 0.5 * asof_sos[(r.GAME_ID, r.TEAM_ABBREVIATION)]
        team_date[r.TEAM_ABBREVIATION].append((r.d, srs))
    for t in team_date:
        team_date[t].sort()

    def asof_srs(team, date):
        arr = team_date.get(team)
        if not arr:
            return None
        val = None
        for dd, s in arr:
            if dd < date:        # strictly before -> leak-free
                val = s
            else:
                break
        return val

    pid_team = {(int(r.PLAYER_ID), r.d): r.TEAM_ABBREVIATION for r in df.itertuples()}
    pid_team_date = defaultdict(dict)
    for (pid, d), t in pid_team.items():
        pid_team_date[pid][d] = t
    return asof_srs, pid_team, pid_team_date


# ------------------------------------------------------- SRS / team (season_games)
def _build_season_games_srs(season):
    """as-of srs + (team-name) per game from season_games_<season>.json. Used as a
    leak-free fallback for corpora without a realized-margin league log (2024-25).
    Also yields (player not available here) so we map player_team via MATCHUP later."""
    rows = json.load(open(os.path.join(ROOT, "data", "nba", f"season_games_{season}.json"),
                        encoding="utf-8"))["rows"]
    team_date = defaultdict(list)
    # (date)-> list of (home_team, away_team) so we can infer a player's team from opp+venue
    games_by_date = defaultdict(list)
    for r in rows:
        if "home_team" not in r or "home_srs" not in r:
            continue
        d = pd.Timestamp(r["game_date"]).normalize()
        team_date[r["home_team"]].append((d, float(r["home_srs"])))
        team_date[r["away_team"]].append((d, float(r["away_srs"])))
        games_by_date[d].append((r["home_team"], r["away_team"]))
    for t in team_date:
        team_date[t].sort()

    def asof_srs(team, date):
        arr = team_date.get(team)
        if not arr:
            return None
        # season_games srs at game date D already reflects prior games (as-of); take the
        # entry exactly at D (its value was computed pre-game), else most recent before.
        val = None
        for dd, s in arr:
            if dd <= date:
                val = s
            if dd > date:
                break
        return val

    def player_team(opp, venue, date):
        """Infer the bettor's team from (opponent, venue) using the day's schedule."""
        for h, a in games_by_date.get(date, []):
            if h == opp:
                return a
            if a == opp:
                return h
        return None

    return asof_srs, player_team


# --------------------------------------------------------------- signal attachment
def attach_signal(bets, asof_srs, pid_team_date=None, player_team_fn=None):
    """Attach exp_margin, blowout-risk, role to each bet. Returns count attached."""
    n = 0
    for b in bets:
        pt = None
        if pid_team_date is not None:
            pt = pid_team_date.get(b["pid"], {}).get(b["gdate"])
        if pt is None and player_team_fn is not None:
            pt = player_team_fn(b["opp"], b.get("venue", ""), b["gdate"])
        if pt is None:
            continue
        s_team = asof_srs(pt, b["gdate"])
        s_opp = asof_srs(b["opp"], b["gdate"])
        if s_team is None or s_opp is None:
            continue
        hca = HCA if b.get("is_home") == 1 else -HCA
        em = s_team - s_opp + hca
        b["_exp_margin"] = em
        b["_blowout"] = abs(em)
        b["_favored"] = 1 if em > 0 else 0
        l10 = b.get("l10_min", np.nan)
        if np.isfinite(l10) and l10 >= STARTER_MIN:
            b["_role"] = "starter"
        elif np.isfinite(l10) and l10 <= BENCH_MIN:
            b["_role"] = "bench"
        else:
            b["_role"] = "swing"
        # signed minutes-impact signal:
        #   favored starter -> sits 4Q  -> negative (pred down) proportional to blowout
        #   favored bench   -> garbage  -> positive (pred up)  proportional to blowout
        #   underdog in blowout: starter may also sit if losing big -> treat by |em| too
        if b["_role"] == "starter":
            b["_sig"] = -b["_blowout"]                 # blowouts (either side) trim starter mins
        elif b["_role"] == "bench":
            b["_sig"] = b["_blowout"] * (1 if b["_favored"] else 0.5)  # favored bench gains most
        else:
            b["_sig"] = 0.0
        n += 1
    return n


# --------------------------------------------------------------- analysis helpers
def _arr(rows, key):
    return np.array([r.get(key, np.nan) for r in rows], dtype=float)


def orthogonality(bets, stat, role=None):
    sub = [b for b in bets if b["stat"] == stat and "_blowout" in b
           and (role is None or b.get("_role") == role)]
    sig = _arr(sub, "_blowout")
    resid = np.array([b["actual"] - b["pred"] for b in sub], dtype=float)
    m = np.isfinite(sig) & np.isfinite(resid)
    if m.sum() < 30 or np.std(sig[m]) < 1e-9:
        return None, int(m.sum())
    return float(np.corrcoef(sig[m], resid[m])[0, 1]), int(m.sum())


def fit_beta(rows, stat, role):
    sub = [b for b in rows if b["stat"] == stat and b.get("_role") == role
           and np.isfinite(b.get("_sig", np.nan)) and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None, len(sub)
    sig = _arr(sub, "_sig")
    resid = np.array([b["actual"] - b["pred"] for b in sub], dtype=float)
    if np.std(sig) < 1e-9:
        return None, len(sub)
    return float(np.cov(sig, resid)[0, 1] / np.var(sig)), len(sub)


def temporal_halves(bets):
    ds = sorted({b["gdate"] for b in bets})
    if len(ds) < 4:
        return bets, []
    mid = ds[len(ds) // 2]
    return [b for b in bets if b["gdate"] < mid], [b for b in bets if b["gdate"] >= mid]


# --------------------------------------------------------------------- run a corpus
def run_corpus(corpus, asof_srs, pid_team_date=None, player_team_fn=None, label=""):
    print(f"\n{'='*74}\n CORPUS: {corpus}   {label}\n{'='*74}")
    bets = ig.prepare(corpus)
    coh = ig.coherence(bets)
    print(f" coherence sum {coh['sum']:+.2f}% ({'OK' if coh['coherent'] else 'CORRUPT'}) | joined n={len(bets)}")
    if not coh["coherent"]:
        print(" !! corrupt corpus, skipping"); return None
    nat = attach_signal(bets, asof_srs, pid_team_date, player_team_fn)
    sig_bets = [b for b in bets if "_blowout" in b]
    roles = defaultdict(int)
    for b in sig_bets:
        roles[b["_role"]] += 1
    print(f" signal attached to {nat}/{len(bets)} bets | roles: "
          + " ".join(f"{k}={v}" for k, v in sorted(roles.items())))
    if not sig_bets:
        print(" !! no signal coverage"); return None

    # ---- 1. ORTHOGONALITY pre-screen: corr(blowout, actual-pred) overall + per role
    print("\n [1] ORTHOGONALITY corr(|exp_margin|, actual-pred):")
    for stat in STATS:
        r_all, n_all = orthogonality(sig_bets, stat)
        r_st, n_st = orthogonality(sig_bets, stat, "starter")
        r_bn, n_bn = orthogonality(sig_bets, stat, "bench")
        def fmt(r, n):
            if r is None:
                return f"n/a(n{n})"
            flag = " *" if abs(r) >= 0.05 else ""
            return f"{r:+.3f}(n{n}){flag}"
        print(f"   {stat:4s} all={fmt(r_all,n_all)}  starter={fmt(r_st,n_st)}  bench={fmt(r_bn,n_bn)}")

    # ---- 2. POINT TILT: fit beta(_sig->resid) on EARLY, grade LATE, per stat x role
    early, late = temporal_halves(sig_bets)
    print(f"\n [2] POINT TILT (fit early n={len(early)} / grade late n={len(late)}):")
    for role in ("starter", "bench"):
        for stat in STATS:
            beta, ntr = fit_beta(early, stat, role)
            if beta is None:
                continue
            late_sub = [b for b in late if b["stat"] == stat and b.get("_role") == role
                        and np.isfinite(b.get("_sig", np.nan)) and np.isfinite(b.get("pred", np.nan))]
            for b in late_sub:
                b["_pred_adj"] = b["pred"] + beta * b["_sig"]
            if len(late_sub) < 20:
                continue
            raw = ig.roi(late_sub, predictor="pred")
            adj = ig.roi([b for b in late_sub if "_pred_adj" in b], predictor="_pred_adj")
            flips = sum(1 for b in late_sub
                        if (b["pred"] > b["line"]) != (b.get("_pred_adj", b["pred"]) > b["line"]))
            lift = adj["roi_pct"] - raw["roi_pct"]
            tag = "  <<< LIFT" if lift > 0 else ""
            print(f"   {role:7s} {stat:4s} beta={beta:+.4f} | raw={raw['roi_pct']:+6.2f}%(n{raw['n']}) "
                  f"adj={adj['roi_pct']:+6.2f}%(n{adj['n']}) lift={lift:+6.2f}pp flips={flips}{tag}")

    # ---- 3. UNDER-SELECTION FILTER: top-quartile-blowout STARTERS, bet UNDER only
    print("\n [3] UNDER-SELECTION: starters in top-quartile blowout-risk, UNDER only:")
    for stat in STATS:
        st = [b for b in sig_bets if b["stat"] == stat and b.get("_role") == "starter"
              and np.isfinite(b.get("_blowout", np.nan))]
        if len(st) < 40:
            continue
        q75 = np.nanpercentile(_arr(st, "_blowout"), 75)
        hi = [b for b in st if b["_blowout"] >= q75]
        all_roi = ig.roi(st, predictor="pred")
        # pure UNDER selection: force every bet to be UNDER (ignore model direction) in hi-blowout
        for b in hi:
            b["_pred_under"] = b["line"] - 1.0    # force pred<line => UNDER
        und_model = ig.roi(hi, predictor="pred", under_only=True)        # model's own UNDERs in hi
        und_force = ig.roi([b for b in hi if "_pred_under" in b], predictor="_pred_under")
        print(f"   {stat:4s} all-starter={all_roi['roi_pct']:+6.2f}%(n{all_roi['n']}) "
              f"| hi-blowout model-UNDER={und_model['roi_pct']:+6.2f}%(n{und_model['n']}) "
              f"forced-UNDER={und_force['roi_pct']:+6.2f}%(n{und_force['n']})")

    # ---- 4. BENCH-OVER on favored blowout side (basketball-symmetric test)
    print("\n [4] OVER-SELECTION: bench on favored top-quartile blowout side, OVER only:")
    for stat in STATS:
        bn = [b for b in sig_bets if b["stat"] == stat and b.get("_role") == "bench"
              and b.get("_favored") == 1 and np.isfinite(b.get("_blowout", np.nan))]
        if len(bn) < 30:
            print(f"   {stat:4s} bench-favored n={len(bn)} (<30, skip)")
            continue
        q75 = np.nanpercentile(_arr(bn, "_blowout"), 75)
        hi = [b for b in bn if b["_blowout"] >= q75]
        all_roi = ig.roi(bn, predictor="pred")
        for b in hi:
            b["_pred_over"] = b["line"] + 1.0     # force OVER
        ov_model = ig.roi(hi, predictor="pred", over_only=True)
        ov_force = ig.roi([b for b in hi if "_pred_over" in b], predictor="_pred_over")
        print(f"   {stat:4s} all-bench-fav={all_roi['roi_pct']:+6.2f}%(n{all_roi['n']}) "
              f"| hi-blowout model-OVER={ov_model['roi_pct']:+6.2f}%(n{ov_model['n']}) "
              f"forced-OVER={ov_force['roi_pct']:+6.2f}%(n{ov_force['n']})")

    # ---- 5. ISOLATION test (leak-free): does the BLOWOUT FILTER add ROI to the
    #         model's own UNDERs out-of-sample? Compare, on the HELD-OUT late half:
    #         (a) all model-UNDER starter bets  vs  (b) model-UNDER starter bets in
    #         hi-blowout games only. The blowout quartile threshold is fit on EARLY.
    #         If (b) >> (a) on late only, the blowout filter -- not model skill --
    #         is doing the work. If (b) <= (a), the model already prices blowouts.
    print("\n [5] ISOLATION (leak-free early->late): does hi-blowout FILTER lift model-UNDER?")
    early, late = temporal_halves(sig_bets)
    for stat in STATS:
        e_st = [b for b in early if b["stat"] == stat and b.get("_role") == "starter"
                and np.isfinite(b.get("_blowout", np.nan))]
        l_st = [b for b in late if b["stat"] == stat and b.get("_role") == "starter"
                and np.isfinite(b.get("_blowout", np.nan))]
        if len(e_st) < 30 or len(l_st) < 30:
            print(f"   {stat:4s} thin (early n={len(e_st)} late n={len(l_st)}), skip")
            continue
        thr = np.nanpercentile(_arr(e_st, "_blowout"), 75)       # threshold from EARLY only
        l_all = ig.roi(l_st, predictor="pred", under_only=True)  # all model-UNDERs, late
        l_hi = ig.roi([b for b in l_st if b["_blowout"] >= thr],
                      predictor="pred", under_only=True)         # + hi-blowout filter, late
        lift = l_hi["roi_pct"] - l_all["roi_pct"]
        tag = "  <<< FILTER ADDS" if lift > 0 and l_hi["n"] >= 20 else ""
        print(f"   {stat:4s} LATE model-UNDER all={l_all['roi_pct']:+6.2f}%(n{l_all['n']}) "
              f"hi-blowout={l_hi['roi_pct']:+6.2f}%(n{l_hi['n']}) lift={lift:+6.2f}pp{tag}")
    return True


def main():
    asof_2526, _pid_team, pid_team_date = _build_asof_srs_2025_26()
    # Family A (DK/FD/MGM 2025-26, big sample) -- realized-margin SRS + leaguegamelog team
    run_corpus("benashkar_2026_canonical.csv", asof_2526,
               pid_team_date=pid_team_date, label="[Family A | leak-free realized-margin SRS]")
    # Family B (odds-api 2025-26, thin, independent of A)
    run_corpus("regular_season_2025_26_oddsapi.csv", asof_2526,
               pid_team_date=pid_team_date, label="[Family B | odds-api 2025-26, independent]")
    # Family C (odds-api 2024-25, cross-season) -- season_games as-of srs + schedule team map
    asof_2425, pteam_2425 = _build_season_games_srs("2024-25")
    run_corpus("regular_season_2024_25_oddsapi.csv", asof_2425,
               player_team_fn=pteam_2425, label="[Family C | season_games as-of srs, cross-season]")


if __name__ == "__main__":
    main()
