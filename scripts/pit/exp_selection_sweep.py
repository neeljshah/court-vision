"""exp_selection_sweep.py -- SELECTION/SIZING-lever sweep on the prop book (leak-free).

CAMPAIGN LESSON (PREDICTION_HARNESS_GUIDE 6 + memory): POINT features reject
(absorbed/priced) but a SELECTION/SIZING cut on an already-winning book can concentrate ROI.
Two cuts survived prior campaigns (both regime-gated to 2025-26):
  L_AST  = gated-AST edge      (stat==ast, |pred-line|>=0.75, line<=7.5) -- the base book
  L_BLOW = blowout-starter-UNDER (model-UNDER, starter L10>=28, high as-of |exp_margin|),
           strongest on PTS.
This script SWEEPS for MORE selection/sizing levers and -- crucially -- checks each against
the two known levers so we can tell a NEW edge from a re-slice of the AST edge.

Every candidate is graded leak-free as a SELECTION cut on the MODEL's own bet direction
(pred>line), at POSTED odds via intel_grade, on >=2 INDEPENDENT corpora:
  Family A = benashkar_2026_canonical.csv  (DK/FD/MGM 2025-26, big sample n=4068)
  Family B = regular_season_2025_26_oddsapi.csv  (odds-api, same season, independent book, thin)
  Family C = regular_season_2024_25_oddsapi.csv  (odds-api, cross-season, thin)
Bootstrap percentile CI on per-bet PnL (ROI% == mean PnL in grader units). Coherence-guarded,
|odds|<100 dropped (grader does it), reg-season only.

SHIP RULE (strict): a cut SHIPS only if its 90% CI clears 0 on >=2 INDEPENDENT corpora
(A AND (B or C)). A single-corpus win is a regime-gated CANDIDATE, not a ship. Re-slices of
the AST edge that add no lift over plain gated-AST are flagged HONESTLY as such.

DISJOINT WRITE: this file + scratch scripts/_tmp_pred/ + the audit md. No production code,
no vault, no git commit. Read-only on all data.

Run:  conda run -n basketball_ai python scripts/pit/exp_selection_sweep.py
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

LGLOG = os.path.join(ROOT, "data", "cache", "cv_fix", "leaguegamelog_regular_season.parquet")

# ---- known-lever constants (match the prior campaign scripts exactly) ----
GATE_EDGE = 0.75
GATE_LINE_MAX = 7.5
HCA = 2.5
STARTER_MIN = 28.0
QUANTILE = 75.0          # blowout top-quartile

N_BOOT = 20000
RNG = np.random.default_rng(20260601)

CORPORA = {
    "A": "benashkar_2026_canonical.csv",
    "B": "regular_season_2025_26_oddsapi.csv",
    "C": "regular_season_2024_25_oddsapi.csv",
}
SEASON_OF = {"A": "2025-26", "B": "2025-26", "C": "2024-25"}


# ════════════════════════════════════════════════════════════════════════════
# Bootstrap
# ════════════════════════════════════════════════════════════════════════════
def pnls_of(rows, predictor="pred"):
    """Per-bet PnL list (model direction = predictor>line), pushes dropped."""
    out = []
    for b in rows:
        p = b.get(predictor)
        if p is None or (isinstance(p, float) and not np.isfinite(p)):
            continue
        res = ig.settle(b, p)
        if res is None:
            continue
        _, won, payout = res
        out.append(payout)
    return out


def boot(pnls):
    pnls = np.asarray(pnls, float)
    n = len(pnls)
    if n == 0:
        return None
    if n < 5:  # too few to bootstrap meaningfully
        return {"roi": float(pnls.mean()), "ci90": (float("nan"), float("nan")),
                "p_le0": float("nan"), "n": n, "win": float((pnls > 0).mean() * 100)}
    idx = RNG.integers(0, n, size=(N_BOOT, n))
    means = pnls[idx].mean(axis=1)
    return {"roi": float(pnls.mean()),
            "ci90": (float(np.percentile(means, 5)), float(np.percentile(means, 95))),
            "p_le0": float((means <= 0).mean()),
            "n": n, "win": float((pnls > 0).mean() * 100)}


def fmt(d):
    if d is None:
        return "n=0"
    if not np.isfinite(d["ci90"][0]):
        return f"ROI{d['roi']:+.1f}% n={d['n']} win{d['win']:.0f}% (CI n/a, n<5)"
    lo, hi = d["ci90"]
    star = " *" if lo > 0 else ("  ~" if hi > 0 else "  x")
    return (f"ROI{d['roi']:+.1f}% n={d['n']} win{d['win']:.0f}% "
            f"90%CI[{lo:+.1f},{hi:+.1f}] P<=0={d['p_le0']:.3f}{star}")


def grade(rows, predictor="pred"):
    return boot(pnls_of(rows, predictor=predictor))


# ════════════════════════════════════════════════════════════════════════════
# Known-lever set builders
# ════════════════════════════════════════════════════════════════════════════
def gated_ast(bets):
    return [b for b in bets if b["stat"] == "ast"
            and np.isfinite(b.get("pred", np.nan))
            and abs(b["pred"] - b["line"]) >= GATE_EDGE and b["line"] <= GATE_LINE_MAX]


def starter(b):
    l10 = b.get("l10_min", np.nan)
    return np.isfinite(l10) and l10 >= STARTER_MIN


def model_under(b):
    return np.isfinite(b.get("pred", np.nan)) and b["pred"] < b["line"]


def blowout_starter_under(bets, thr):
    """L_BLOW selection at a given blowout threshold thr (fit elsewhere, leak-free)."""
    return [b for b in bets if starter(b) and model_under(b)
            and np.isfinite(b.get("_blowout", np.nan)) and b["_blowout"] >= thr]


# ════════════════════════════════════════════════════════════════════════════
# as-of SRS / exp_margin (for L_BLOW + as a candidate signal) -- leak-free
# ════════════════════════════════════════════════════════════════════════════
def build_asof_srs_2025_26():
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
    for r in games:
        prior = team_hist[r.TEAM_ABBREVIATION]
        asof_mov[(r.GAME_ID, r.TEAM_ABBREVIATION)] = float(np.mean(prior)) if prior else 0.0
        team_hist[r.TEAM_ABBREVIATION].append(r.margin)
    opp_hist = defaultdict(list)
    asof_sos = {}
    for r in games:
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
            if dd < date:
                val = s
            else:
                break
        return val

    pid_team_date = defaultdict(dict)
    for r in df.itertuples():
        pid_team_date[int(r.PLAYER_ID)][r.d] = r.TEAM_ABBREVIATION
    return asof_srs, pid_team_date


def build_season_games_srs(season):
    rows = json.load(open(os.path.join(ROOT, "data", "nba", f"season_games_{season}.json"),
                          encoding="utf-8"))["rows"]
    team_date = defaultdict(list)
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
        val = None
        for dd, s in arr:
            if dd <= date:
                val = s
            if dd > date:
                break
        return val

    def player_team(opp, venue, date):
        for h, a in games_by_date.get(date, []):
            if h == opp:
                return a
            if a == opp:
                return h
        return None

    return asof_srs, player_team


def attach_margin(bets, season):
    if season == "2025-26":
        asof, pid_team_date = build_asof_srs_2025_26()
        pteam_fn = None
    else:
        asof, pteam_fn = build_season_games_srs(season)
        pid_team_date = None
    n = 0
    for b in bets:
        pt = None
        if pid_team_date is not None:
            pt = pid_team_date.get(b["pid"], {}).get(b["gdate"])
        if pt is None and pteam_fn is not None:
            pt = pteam_fn(b["opp"], b.get("venue", ""), b["gdate"])
        if pt is None:
            b["_exp_margin"] = np.nan
            b["_blowout"] = np.nan
            continue
        st, so = asof(pt, b["gdate"]), asof(b["opp"], b["gdate"])
        if st is None or so is None:
            b["_exp_margin"] = np.nan
            b["_blowout"] = np.nan
            continue
        hca = HCA if b.get("is_home") == 1 else -HCA
        em = st - so + hca
        b["_exp_margin"] = em
        b["_blowout"] = abs(em)
        n += 1
    return n


# ════════════════════════════════════════════════════════════════════════════
# Generic selection-cut grading on a stat-set (the workhorse)
# ════════════════════════════════════════════════════════════════════════════
def cut_table(label, base_rows, mask_kept, mask_dropped=None):
    """Grade base / kept(mask) / dropped(complement) for one selection cut on a stat-set.
    Returns dict of bootstrap results. base_rows already restricted to the stat/book."""
    kept = [b for b in base_rows if mask_kept(b)]
    if mask_dropped is None:
        dropped = [b for b in base_rows if not mask_kept(b)]
    else:
        dropped = [b for b in base_rows if mask_dropped(b)]
    return {"label": label, "base": grade(base_rows), "kept": grade(kept), "dropped": grade(dropped)}


def overlap(set_a, set_b):
    """Bet-key overlap between two bet lists on (pid, gdate, stat, line)."""
    def keys(s):
        return {(b["pid"], b["gdate"], b["stat"], b["line"]) for b in s}
    ka, kb = keys(set_a), keys(set_b)
    inter = ka & kb
    return {"n_a": len(ka), "n_b": len(kb), "n_inter": len(inter),
            "jac": len(inter) / max(len(ka | kb), 1),
            "frac_a_in_b": len(inter) / max(len(ka), 1),
            "frac_b_in_a": len(inter) / max(len(kb), 1)}


# ════════════════════════════════════════════════════════════════════════════
# Per-corpus prepare with all signals attached
# ════════════════════════════════════════════════════════════════════════════
def prepare_corpus(key):
    corpus = CORPORA[key]
    season = SEASON_OF[key]
    bets = ig.prepare(corpus)
    coh = ig.coherence(bets)
    n_m = attach_margin(bets, season)
    print(f"  [{key}] {corpus}: n={len(bets)} coherent={coh['coherent']} "
          f"coh_sum={coh['sum']:+.2f} margin-attached={n_m}")
    return bets, coh


# ════════════════════════════════════════════════════════════════════════════
# CANDIDATE SWEEP
# ════════════════════════════════════════════════════════════════════════════
def edge_terciles(rows, label):
    """C3: model-edge-magnitude terciles |pred-line| per stat-set. Concentration baseline."""
    sub = [b for b in rows if np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None
    e = np.array([abs(b["pred"] - b["line"]) for b in sub])
    lo, hi = np.percentile(e, [33.333, 66.667])
    out = {"_cuts": (lo, hi)}
    out["low"] = grade([b for b in sub if abs(b["pred"] - b["line"]) <= lo])
    out["mid"] = grade([b for b in sub if lo < abs(b["pred"] - b["line"]) <= hi])
    out["high"] = grade([b for b in sub if abs(b["pred"] - b["line"]) > hi])
    return out


def line_buckets_ast(rows):
    """C4: prop-line-value buckets for AST. low<=4.5, mid 5-6.5, high>=7."""
    a = [b for b in rows if b["stat"] == "ast" and np.isfinite(b.get("pred", np.nan))]
    out = {}
    out["lo(<=4.5)"] = grade([b for b in a if b["line"] <= 4.5])
    out["mid(5-6.5)"] = grade([b for b in a if 4.5 < b["line"] <= 6.5])
    out["hi(>=7)"] = grade([b for b in a if b["line"] > 6.5])
    return out


def run():
    print("#" * 80)
    print("# SELECTION/SIZING-LEVER SWEEP")
    print("#" * 80)

    corp = {}
    for k in ("A", "B", "C"):
        corp[k] = prepare_corpus(k)
    A, cohA = corp["A"]
    B, cohB = corp["B"]
    C, cohC = corp["C"]
    for k, (bets, coh) in corp.items():
        assert coh["coherent"], f"corpus {k} corrupt"

    # ---------------- known-lever baselines + their bet sets ----------------
    print("\n" + "=" * 80)
    print("KNOWN LEVERS (baseline + bet sets for overlap analysis)")
    print("=" * 80)
    gA = gated_ast(A); gB = gated_ast(B); gC = gated_ast(C)
    print(f"  L_AST  gated-AST   A:{fmt(grade(gA))}")
    print(f"                     B:{fmt(grade(gB))}")
    print(f"                     C:{fmt(grade(gC))}")
    # blowout threshold fit on A's starter blowouts (q75), applied to all corpora (cross-corpus)
    a_starter_blow = np.array([b["_blowout"] for b in A
                               if starter(b) and np.isfinite(b.get("_blowout", np.nan))])
    thrA = float(np.percentile(a_starter_blow, QUANTILE)) if len(a_starter_blow) else np.nan
    blA = blowout_starter_under(A, thrA)
    blB = blowout_starter_under(B, thrA)
    blC = blowout_starter_under(C, thrA)
    print(f"  L_BLOW blowout-starter-UNDER (thr={thrA:.2f} q75 fit on A)")
    print(f"                     A:{fmt(grade(blA))}")
    print(f"                     B:{fmt(grade(blB))}")
    print(f"                     C:{fmt(grade(blC))}")
    blA_pts = [b for b in blA if b["stat"] == "pts"]
    print(f"         L_BLOW PTS-only A:{fmt(grade(blA_pts))}")

    # =====================================================================
    # CANDIDATE 1 -- STACK / OVERLAP of the two known levers
    # =====================================================================
    print("\n" + "=" * 80)
    print("C1 -- STACK: do L_AST and L_BLOW overlap or are they disjoint? Combined ROI?")
    print("=" * 80)
    ov = overlap(gA, blA)
    print(f"  Family A overlap(L_AST gated-AST n={ov['n_a']}, L_BLOW n={ov['n_b']}): "
          f"intersection={ov['n_inter']}  jaccard={ov['jac']:.3f}  "
          f"frac_AST_in_BLOW={ov['frac_a_in_b']:.3f} frac_BLOW_in_AST={ov['frac_b_in_a']:.3f}")
    # L_BLOW is model-UNDER; gated-AST is both-direction AST -> by construction nearly disjoint
    # (AST<=7.5 lines, blowout is mostly PTS/REB starters). Combined = union, graded.
    union_keys = set()
    combined = []
    for b in gA + blA:
        kk = (b["pid"], b["gdate"], b["stat"], b["line"], b["pred"] > b["line"])
        if kk not in union_keys:
            union_keys.add(kk)
            combined.append(b)
    print(f"  COMBINED union (A): {fmt(grade(combined))}  (n_union={len(combined)})")
    print(f"    -> if intersection~0 the two are DISJOINT bet sets; combined ROI is a "
          f"size-weighted blend, portfolio-additive not interacting.")
    # also B/C combined
    for key, g_, bl_ in [("B", gB, blB), ("C", gC, blC)]:
        uk = set(); comb = []
        for b in g_ + bl_:
            kk = (b["pid"], b["gdate"], b["stat"], b["line"], b["pred"] > b["line"])
            if kk not in uk:
                uk.add(kk); comb.append(b)
        ovx = overlap(g_, bl_)
        print(f"  COMBINED union ({key}): {fmt(grade(comb))}  inter={ovx['n_inter']}")

    # =====================================================================
    # CANDIDATE 2 -- opp-PACE as SIZING tilt on gated-AST
    # =====================================================================
    print("\n" + "=" * 80)
    print("C2 -- opp-PACE as SIZING (high-pace tercile) on gated-AST [2 corpora]")
    print("=" * 80)
    for key, g_ in [("A", gA), ("B", gB), ("C", gC)]:
        sub = [b for b in g_ if np.isfinite(b.get("opp_pace", np.nan))]
        if len(sub) < 10:
            print(f"  [{key}] gated-AST w/pace n={len(sub)} (too few)")
            continue
        pace = np.array([b["opp_pace"] for b in sub])
        thr = np.percentile(pace, 66.667)
        high = [b for b in sub if b["opp_pace"] > thr]
        lowmid = [b for b in sub if b["opp_pace"] <= thr]
        print(f"  [{key}] thr_p66={thr:.1f}  HIGH:{fmt(grade(high))}")
        print(f"        LOW+MID:{fmt(grade(lowmid))}")

    # =====================================================================
    # CANDIDATE 3 -- MODEL-EDGE-MAGNITUDE terciles per stat (Kelly baseline)
    # =====================================================================
    print("\n" + "=" * 80)
    print("C3 -- MODEL-EDGE-MAGNITUDE terciles |pred-line| per stat (Kelly concentration)")
    print("=" * 80)
    for stat in ("ast", "reb", "pts", "fg3m"):
        print(f"  --- {stat.upper()} ---")
        for key, bets in [("A", A), ("B", B), ("C", C)]:
            rows = [b for b in bets if b["stat"] == stat]
            t = edge_terciles(rows, f"{key}-{stat}")
            if t is None:
                print(f"   [{key}] n<30 skip")
                continue
            print(f"   [{key}] cuts={t['_cuts'][0]:.2f}/{t['_cuts'][1]:.2f}  "
                  f"low:{fmt(t['low'])}")
            print(f"        mid:{fmt(t['mid'])}")
            print(f"        high:{fmt(t['high'])}")

    # =====================================================================
    # CANDIDATE 4 -- PROP-LINE-VALUE buckets for AST
    # =====================================================================
    print("\n" + "=" * 80)
    print("C4 -- PROP-LINE-VALUE buckets for AST (model-direction ROI per line range)")
    print("=" * 80)
    for key, bets in [("A", A), ("B", B), ("C", C)]:
        lb = line_buckets_ast(bets)
        print(f"  [{key}] lo(<=4.5):{fmt(lb['lo(<=4.5)'])}")
        print(f"        mid(5-6.5):{fmt(lb['mid(5-6.5)'])}")
        print(f"        hi(>=7):{fmt(lb['hi(>=7)'])}")

    # =====================================================================
    # CANDIDATE 5 -- HOME/ROAD and REST as a selection cut on gated-AST
    # =====================================================================
    print("\n" + "=" * 80)
    print("C5 -- HOME/ROAD + REST selection cut on gated-AST")
    print("=" * 80)
    for key, g_ in [("A", gA), ("B", gB), ("C", gC)]:
        home = [b for b in g_ if b.get("is_home") == 1]
        road = [b for b in g_ if b.get("is_home") == 0]
        print(f"  [{key}] HOME:{fmt(grade(home))}")
        print(f"        ROAD:{fmt(grade(road))}")
        # rest: rested (rest_days>=2 and not b2b) vs b2b
        rested = [b for b in g_ if b.get("is_b2b") == 0 and b.get("rest_days", 0) >= 2]
        b2b = [b for b in g_ if b.get("is_b2b") == 1]
        print(f"        RESTED(>=2,!b2b):{fmt(grade(rested))}")
        print(f"        B2B:{fmt(grade(b2b))}")

    # =====================================================================
    # CANDIDATE 6 -- STARTER vs BENCH role cut per stat
    # =====================================================================
    print("\n" + "=" * 80)
    print("C6 -- STARTER (L10>=28) vs BENCH role cut per stat (model-direction ROI)")
    print("=" * 80)
    for stat in ("ast", "reb", "pts", "fg3m"):
        print(f"  --- {stat.upper()} ---")
        for key, bets in [("A", A), ("B", B), ("C", C)]:
            rows = [b for b in bets if b["stat"] == stat and np.isfinite(b.get("l10_min", np.nan))]
            if len(rows) < 20:
                print(f"   [{key}] n<20 skip")
                continue
            st = [b for b in rows if starter(b)]
            bn = [b for b in rows if not starter(b)]
            print(f"   [{key}] STARTER:{fmt(grade(st))}  BENCH:{fmt(grade(bn))}")

    # =====================================================================
    # CANDIDATE 7a -- VACATED-LOAD (n_out / vac_min) as selection on gated-AST
    #   basketball: teammate(s) OUT -> playmaker inherits creation -> AST up
    # =====================================================================
    print("\n" + "=" * 80)
    print("C7a -- VACATED-LOAD (n_out>0, vac_pts top-tercile) selection on gated-AST")
    print("=" * 80)
    for key, g_ in [("A", gA), ("B", gB), ("C", gC)]:
        nout = [b for b in g_ if b.get("n_out", 0) and b["n_out"] > 0]
        no0 = [b for b in g_ if b.get("n_out", -1) == 0]
        print(f"  [{key}] n_out>0:{fmt(grade(nout))}  n_out=0:{fmt(grade(no0))}")
        vp = np.array([b.get("vac_pts", np.nan) for b in g_], float)
        if np.isfinite(vp).sum() >= 15:
            thr = np.nanpercentile(vp, 66.667)
            hi = [b for b in g_ if np.isfinite(b.get("vac_pts", np.nan)) and b["vac_pts"] > thr]
            lo = [b for b in g_ if np.isfinite(b.get("vac_pts", np.nan)) and b["vac_pts"] <= thr]
            print(f"        vac_pts hi(>{thr:.0f}):{fmt(grade(hi))}  lo:{fmt(grade(lo))}")

    # =====================================================================
    # CANDIDATE 7b -- BLOWOUT-FAVORITE STARTER-UNDER vs UNDERDOG (sign of margin)
    #   basketball: favorites blow leads -> starters rest; underdogs get garbage-time run-up
    #   test the L_BLOW mechanism split by FAVORED sign (only favored should rest starters)
    # =====================================================================
    print("\n" + "=" * 80)
    print("C7b -- L_BLOW split by FAVORED sign (favored team starters rest in blowouts)")
    print("=" * 80)
    for key, bets in [("A", A), ("B", B), ("C", C)]:
        bl = blowout_starter_under(bets, thrA)
        fav = [b for b in bl if b.get("_exp_margin", 0) > 0]   # bet-player on FAVORED team
        dog = [b for b in bl if b.get("_exp_margin", 0) < 0]   # bet-player on UNDERDOG
        print(f"  [{key}] L_BLOW FAVORED-team:{fmt(grade(fav))}  UNDERDOG-team:{fmt(grade(dog))}")

    # =====================================================================
    # CANDIDATE 7c -- HIGH-MINUTES-VOLATILITY UNDER (std_min top tercile) per stat
    #   basketball: high minutes variance => fat left tail => UNDER lands more
    # =====================================================================
    print("\n" + "=" * 80)
    print("C7c -- HIGH std_min (minutes volatility) x model-UNDER, per stat")
    print("=" * 80)
    for stat in ("pts", "reb", "ast"):
        print(f"  --- {stat.upper()} ---")
        for key, bets in [("A", A), ("B", B), ("C", C)]:
            rows = [b for b in bets if b["stat"] == stat and model_under(b)
                    and np.isfinite(b.get("std_min", np.nan))]
            if len(rows) < 20:
                print(f"   [{key}] under n<20 skip")
                continue
            thr = np.percentile([b["std_min"] for b in rows], 66.667)
            hi = [b for b in rows if b["std_min"] > thr]
            lo = [b for b in rows if b["std_min"] <= thr]
            print(f"   [{key}] UNDER hi-std:{fmt(grade(hi))}  lo-std:{fmt(grade(lo))}")

    print("\n" + "#" * 80)
    print("# SWEEP COMPLETE -- see docs/_audits/PRED_EXP_selection_sweep_2026-06-01.md")
    print("#" * 80)


if __name__ == "__main__":
    run()
