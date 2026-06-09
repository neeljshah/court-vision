"""exp_multi_signal_portfolio.py -- combine ALL surviving SELECTION/SIZING cuts into ONE
Kelly PORTFOLIO and measure combined ROI + bankroll growth + bet volume + Sharpe vs each
individual lever and vs flat -- leak-free, on >=2 INDEPENDENT corpora.

CAMPAIGN CONTEXT (PREDICTION_HARNESS_GUIDE 6 + memory + prior audits):
  The ONLY durable edges are SELECTION/SIZING cuts on the already-winning book. The surviving
  cuts (all A-clear in prior audits, all regime-gated to 2025-26):
    L_AST  = gated-AST           (stat==ast, |pred-line|>=0.75, line<=7.5)            [the base book]
    L_BLOW = blowout-starter-UNDER (pred<line, starter L10>=28, high as-of |exp_margin|, PTS-strong)
    sizing tilts that survived as A-clear concentrations (NOT new disjoint edges):
       vac_ast / n_out>0  -> size-UP within gated-AST
       top-edge-tercile   -> Kelly concentration (already the model's own edge magnitude)
  selection_sweep C1 already showed L_AST and L_BLOW are ~DISJOINT and additive (+15.3% n418 on A).

THE PORTFOLIO QUESTION (this experiment, distinct from the sweep):
  If you actually BET this as one book -- union of the disjoint legs, each bet Kelly-sized --
  does the COMBINED portfolio's risk-adjusted return (Sharpe / terminal bankroll) beat ANY
  single lever AND beat flat-stake on >=2 INDEPENDENT corpora? Or is the "portfolio" just a
  size-weighted blend that adds volume but not edge (and dies on the 2nd corpus like every leg)?

DESIGN (all leak-free):
  - Legs are DISJOINT bet sets (union de-duped on (pid,gdate,stat,line,direction)).
  - Kelly sizing uses a leg-specific edge estimate fit ONLY on the EARLY half of Family A
    (one shared fit, applied to the held-out LATE half of A and to ALL of B and C as a
    genuine out-of-sample / cross-corpus test). No bet uses the game it predicts.
  - Metrics: flat-stake ROI (mean per-bet PnL in grader units), per-bet Sharpe
    (mean/std of unit PnL), compounded terminal bankroll under fractional Kelly, bet volume.
  - Bootstrap percentile CI on per-bet PnL for ROI and on per-bet Sharpe.

SHIP RULE (strict, same as the campaign): the PORTFOLIO is a CANDIDATE only if it BEATS the best
single lever on a risk-adjusted basis with bootstrap CI clearing 0 on A AND (B or C). Otherwise
it is at best a convenience aggregation (more volume, same regime-gated A-only edge) = INSUFFICIENT,
or REJECT if it does not even beat flat.

DISJOINT WRITE: this file + scratch + the audit md. Read-only on all data. No git commit.

Run:  conda run -n basketball_ai python scripts/pit/exp_multi_signal_portfolio.py
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

# ---- known-lever constants (match prior campaign scripts exactly) ----
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
# PnL / bootstrap helpers
# ════════════════════════════════════════════════════════════════════════════
def unit_pnl(b, predictor="pred"):
    """Per-bet PnL in UNITS (win = +decimal_odds_profit, loss = -1). None on push/no-pred."""
    p = b.get(predictor)
    if p is None or (isinstance(p, float) and not np.isfinite(p)):
        return None
    res = ig.settle(b, p)
    if res is None:
        return None
    _, won, payout = res          # payout is in 100-unit grader scale (+decimal*100 / -100)
    return payout / 100.0


def pnls_of(rows, predictor="pred"):
    out = []
    for b in rows:
        v = unit_pnl(b, predictor=predictor)
        if v is not None:
            out.append(v)
    return out


def boot_roi(pnls):
    """Bootstrap mean unit PnL (== ROI fraction) + Sharpe (mean/std)."""
    pnls = np.asarray(pnls, float)
    n = len(pnls)
    if n == 0:
        return None
    roi = float(pnls.mean())
    sd = float(pnls.std(ddof=1)) if n > 1 else float("nan")
    sharpe = roi / sd if (sd and np.isfinite(sd) and sd > 1e-12) else float("nan")
    if n < 5:
        return {"roi": roi, "ci90": (float("nan"), float("nan")), "p_le0": float("nan"),
                "n": n, "win": float((pnls > 0).mean() * 100), "sharpe": sharpe,
                "sharpe_ci90": (float("nan"), float("nan")), "sd": sd}
    idx = RNG.integers(0, n, size=(N_BOOT, n))
    sample = pnls[idx]
    means = sample.mean(axis=1)
    sds = sample.std(axis=1, ddof=1)
    sharpes = np.divide(means, sds, out=np.full_like(means, np.nan), where=sds > 1e-12)
    sh_valid = sharpes[np.isfinite(sharpes)]
    return {
        "roi": roi,
        "ci90": (float(np.percentile(means, 5)), float(np.percentile(means, 95))),
        "p_le0": float((means <= 0).mean()),
        "n": n, "win": float((pnls > 0).mean() * 100), "sharpe": sharpe, "sd": sd,
        "sharpe_ci90": (float(np.percentile(sh_valid, 5)), float(np.percentile(sh_valid, 95)))
        if len(sh_valid) > 100 else (float("nan"), float("nan")),
    }


def fmt(d):
    if d is None:
        return "n=0"
    lo, hi = d["ci90"]
    if not np.isfinite(lo):
        return f"ROI{d['roi']*100:+.1f}% n={d['n']} win{d['win']:.0f}% (CI n/a,n<5) Sh{d['sharpe']:+.3f}"
    star = " *" if lo > 0 else ("  ~" if hi > 0 else "  x")
    shlo, shhi = d["sharpe_ci90"]
    shtxt = (f" Sh{d['sharpe']:+.3f}[{shlo:+.3f},{shhi:+.3f}]"
             if np.isfinite(shlo) else f" Sh{d['sharpe']:+.3f}")
    return (f"ROI{d['roi']*100:+.1f}% n={d['n']} win{d['win']:.0f}% "
            f"90%CI[{lo*100:+.1f},{hi*100:+.1f}]% P<=0={d['p_le0']:.3f}{star}{shtxt}")


def grade(rows, predictor="pred"):
    return boot_roi(pnls_of(rows, predictor=predictor))


def boot_diff(pnls_x, pnls_y):
    """Bootstrap CI on (mean(x) - mean(y)) treating the two as independent samples.
    Used to test 'does portfolio beat the best single lever' risk-adjusted (ROI & Sharpe)."""
    x = np.asarray(pnls_x, float)
    y = np.asarray(pnls_y, float)
    if len(x) < 5 or len(y) < 5:
        return None
    ix = RNG.integers(0, len(x), size=(N_BOOT, len(x)))
    iy = RNG.integers(0, len(y), size=(N_BOOT, len(y)))
    sx, sy = x[ix], y[iy]
    droi = sx.mean(axis=1) - sy.mean(axis=1)
    sdx = sx.std(axis=1, ddof=1); sdy = sy.std(axis=1, ddof=1)
    shx = np.divide(sx.mean(axis=1), sdx, out=np.full(N_BOOT, np.nan), where=sdx > 1e-12)
    shy = np.divide(sy.mean(axis=1), sdy, out=np.full(N_BOOT, np.nan), where=sdy > 1e-12)
    dsh = shx - shy
    dsh = dsh[np.isfinite(dsh)]
    return {
        "droi": float(x.mean() - y.mean()),
        "droi_ci90": (float(np.percentile(droi, 5)), float(np.percentile(droi, 95))),
        "droi_p_le0": float((droi <= 0).mean()),
        "dsharpe": float(np.nanmean(shx) - np.nanmean(shy)),
        "dsharpe_ci90": (float(np.percentile(dsh, 5)), float(np.percentile(dsh, 95)))
        if len(dsh) > 100 else (float("nan"), float("nan")),
        "dsharpe_p_le0": float((dsh <= 0).mean()) if len(dsh) > 100 else float("nan"),
    }


# ════════════════════════════════════════════════════════════════════════════
# Leg builders (match prior campaign EXACTLY)
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
    return [b for b in bets if starter(b) and model_under(b)
            and np.isfinite(b.get("_blowout", np.nan)) and b["_blowout"] >= thr]


# ---- as-of SRS / exp_margin (leak-free), copied from exp_selection_sweep ----
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
            b["_exp_margin"] = np.nan; b["_blowout"] = np.nan; continue
        st, so = asof(pt, b["gdate"]), asof(b["opp"], b["gdate"])
        if st is None or so is None:
            b["_exp_margin"] = np.nan; b["_blowout"] = np.nan; continue
        hca = HCA if b.get("is_home") == 1 else -HCA
        em = st - so + hca
        b["_exp_margin"] = em; b["_blowout"] = abs(em); n += 1
    return n


# ════════════════════════════════════════════════════════════════════════════
# Portfolio construction
# ════════════════════════════════════════════════════════════════════════════
def edge_tercile_cut(bets):
    """Top-edge-tercile per stat (Kelly concentration leg). Returns the kept set.
    Tercile threshold per stat fit on the SAME corpus (concentration is corpus-relative;
    this is the published C3 Kelly-concentration leg)."""
    out = []
    for stat in ("ast", "reb", "pts", "fg3m"):
        rows = [b for b in bets if b["stat"] == stat and np.isfinite(b.get("pred", np.nan))]
        if len(rows) < 30:
            continue
        e = np.array([abs(b["pred"] - b["line"]) for b in rows])
        hi = np.percentile(e, 66.667)
        out += [b for b in rows if abs(b["pred"] - b["line"]) > hi]
    return out


def union_dedupe(*leg_lists):
    seen = set()
    out = []
    for leg in leg_lists:
        for b in leg:
            kk = (b["pid"], b["gdate"], b["stat"], b["line"], b["pred"] > b["line"])
            if kk not in seen:
                seen.add(kk)
                out.append(b)
    return out


def kelly_bankroll(rows, edge_fn, frac=0.25, predictor="pred"):
    """Compound a bankroll betting fractional-Kelly per bet, chronologically.
    edge_fn(b) -> estimated win prob p_hat (leak-free, fit elsewhere). Kelly f* uses the
    bet's actual decimal odds. Returns (terminal_bankroll, growth_log, n_bet)."""
    bank = 1.0
    log_growth = 0.0
    n_bet = 0
    for b in sorted(rows, key=lambda x: x["gdate"]):
        p = b.get(predictor)
        if p is None or (isinstance(p, float) and not np.isfinite(p)):
            continue
        bet_over = p > b["line"]
        odds = b["over_odds"] if bet_over else b["under_odds"]
        dec_profit = (odds / 100.0) if odds > 0 else (100.0 / abs(odds))  # net decimal odds b>0
        ph = edge_fn(b)
        if ph is None or not np.isfinite(ph):
            continue
        # Kelly fraction f* = (b*p - q)/b ; b=dec_profit, q=1-p
        b_o = dec_profit
        f_star = (b_o * ph - (1 - ph)) / b_o
        f = max(0.0, frac * f_star)
        if f <= 0:
            continue
        res = ig.settle(b, p)
        if res is None:
            continue
        _, won, payout = res
        r = (payout / 100.0)  # unit PnL: win=+dec_profit, loss=-1
        bank *= (1 + f * r)
        if bank <= 1e-9:
            bank = 1e-9
        log_growth += np.log(1 + f * r)
        n_bet += 1
    return bank, log_growth, n_bet


def run():
    print("#" * 84)
    print("# MULTI-SIGNAL PORTFOLIO -- combine surviving selection/sizing cuts (Kelly)")
    print("#" * 84)

    corp = {}
    for k in ("A", "B", "C"):
        bets = ig.prepare(CORPORA[k])
        coh = ig.coherence(bets)
        n_m = attach_margin(bets, SEASON_OF[k])
        assert coh["coherent"], f"corpus {k} corrupt"
        corp[k] = bets
        print(f"  [{k}] {CORPORA[k]}: n={len(bets)} coherent={coh['coherent']} "
              f"coh_sum={coh['sum']:+.2f}% margin-attached={n_m}")

    A, B, C = corp["A"], corp["B"], corp["C"]

    # ---- blowout threshold fit on A's starter blowouts (q75), applied cross-corpus ----
    a_sb = np.array([b["_blowout"] for b in A if starter(b) and np.isfinite(b.get("_blowout", np.nan))])
    thrA = float(np.percentile(a_sb, QUANTILE)) if len(a_sb) else np.nan
    print(f"\n  blowout q75 threshold (fit on A) = {thrA:.2f}")

    # ════════════════════════════════════════════════════════════════════
    # 1. DEFINE LEGS per corpus + overlap diagnostics
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 84)
    print("1. LEGS (per corpus): L_AST gated-AST | L_BLOW blowout-starter-UNDER | L_EDGE top-edge-tercile")
    print("=" * 84)
    legs = {}
    for k, bets in (("A", A), ("B", B), ("C", C)):
        L_AST = gated_ast(bets)
        L_BLOW = blowout_starter_under(bets, thrA)
        L_EDGE = edge_tercile_cut(bets)
        port = union_dedupe(L_AST, L_BLOW)            # primary disjoint portfolio (the 2 real edges)
        port3 = union_dedupe(L_AST, L_BLOW, L_EDGE)   # +Kelly concentration leg
        legs[k] = {"L_AST": L_AST, "L_BLOW": L_BLOW, "L_EDGE": L_EDGE,
                   "PORT": port, "PORT3": port3, "ALL": bets}

        def keys(s):
            return {(b["pid"], b["gdate"], b["stat"], b["line"], b["pred"] > b["line"]) for b in s}
        ka, kb, ke = keys(L_AST), keys(L_BLOW), keys(L_EDGE)
        print(f"  [{k}] n_AST={len(L_AST)} n_BLOW={len(L_BLOW)} n_EDGE={len(L_EDGE)} "
              f"|| AST&BLOW={len(ka & kb)} AST&EDGE={len(ka & ke)} BLOW&EDGE={len(kb & ke)} "
              f"|| PORT(union 2)={len(port)} PORT3={len(port3)}")

    # ════════════════════════════════════════════════════════════════════
    # 2. FLAT-STAKE ROI + Sharpe: each lever vs PORTFOLIO vs flat-everything
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 84)
    print("2. FLAT-STAKE ROI + per-bet SHARPE (bootstrap CI). best single lever vs PORT vs flat-ALL")
    print("=" * 84)
    grades = {}
    for k in ("A", "B", "C"):
        grades[k] = {name: grade(legs[k][name]) for name in
                     ("L_AST", "L_BLOW", "L_EDGE", "PORT", "PORT3", "ALL")}
        print(f"\n  --- corpus {k} ---")
        for name in ("ALL", "L_AST", "L_BLOW", "L_EDGE", "PORT", "PORT3"):
            print(f"    {name:6s}: {fmt(grades[k][name])}")

    # ════════════════════════════════════════════════════════════════════
    # 3. DOES PORTFOLIO BEAT THE BEST SINGLE LEVER? (bootstrap diff on ROI & Sharpe)
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 84)
    print("3. PORT vs BEST-SINGLE-LEVER and PORT vs FLAT-ALL (bootstrap diff CI)")
    print("=" * 84)
    for k in ("A", "B", "C"):
        # best single lever = the one with the higher flat ROI among L_AST / L_BLOW (the 2 real edges)
        best_name = max(("L_AST", "L_BLOW"),
                        key=lambda nm: (grades[k][nm]["roi"] if grades[k][nm] else -9))
        port_p = pnls_of(legs[k]["PORT"])
        best_p = pnls_of(legs[k][best_name])
        all_p = pnls_of(legs[k]["ALL"])
        print(f"\n  --- corpus {k} (best single lever = {best_name}) ---")
        d1 = boot_diff(port_p, best_p)
        if d1:
            lo, hi = d1["droi_ci90"]
            slo, shi = d1["dsharpe_ci90"]
            print(f"    PORT - {best_name}: dROI={d1['droi']*100:+.1f}% CI[{lo*100:+.1f},{hi*100:+.1f}]% "
                  f"P(dROI<=0)={d1['droi_p_le0']:.3f} | dSharpe={d1['dsharpe']:+.3f} "
                  f"CI[{slo:+.3f},{shi:+.3f}] P(dSh<=0)={d1['dsharpe_p_le0']:.3f}")
        else:
            print(f"    PORT - {best_name}: n too small to diff (nPort={len(port_p)} nBest={len(best_p)})")
        d2 = boot_diff(port_p, all_p)
        if d2:
            lo, hi = d2["droi_ci90"]
            print(f"    PORT - FLAT-ALL: dROI={d2['droi']*100:+.1f}% CI[{lo*100:+.1f},{hi*100:+.1f}]% "
                  f"P(dROI<=0)={d2['droi_p_le0']:.3f} | dSharpe={d2['dsharpe']:+.3f}")

    # ════════════════════════════════════════════════════════════════════
    # 4. KELLY BANKROLL GROWTH (compounded, chronological, leak-free p_hat)
    #    p_hat per leg fit on EARLY half of A only, applied to held-out LATE A + all B + all C.
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 84)
    print("4. KELLY BANKROLL (frac=0.25). p_hat per-leg fit on EARLY-A, applied OOS to LATE-A,B,C")
    print("=" * 84)
    # leak-free edge fit: empirical win rate of each leg on the EARLY half of A
    dsA = sorted({b["gdate"] for b in A}); midA = dsA[len(dsA) // 2]
    earlyA = [b for b in A if b["gdate"] < midA]
    lateA = [b for b in A if b["gdate"] >= midA]

    def leg_winrate(rows):
        wins = tot = 0
        for b in rows:
            res = ig.settle(b, b.get("pred"))
            if res is None:
                continue
            _, won, _ = res
            wins += won; tot += 1
        return (wins / tot) if tot else None, tot

    early_ast = gated_ast(earlyA)
    early_blow = blowout_starter_under(earlyA, thrA)
    p_ast, n_ast = leg_winrate(early_ast)
    p_blow, n_blow = leg_winrate(early_blow)
    # market-implied baseline p (for a -110ish line ~0.524) to contextualize
    print(f"  EARLY-A win rates: gated-AST p_hat={p_ast} (n={n_ast})  "
          f"blowout-UNDER p_hat={p_blow} (n={n_blow})")
    # guard: if p_hat unavailable, fall back to a mild +edge prior
    p_ast = p_ast if p_ast else 0.55
    p_blow = p_blow if p_blow else 0.55

    def edge_fn_factory(p_ast, p_blow, thr):
        ast_keys = None  # decide membership at call time

        def edge_fn(b):
            # AST leg?
            if (b["stat"] == "ast" and np.isfinite(b.get("pred", np.nan))
                    and abs(b["pred"] - b["line"]) >= GATE_EDGE and b["line"] <= GATE_LINE_MAX):
                return p_ast
            # BLOW leg?
            if (starter(b) and model_under(b) and np.isfinite(b.get("_blowout", np.nan))
                    and b["_blowout"] >= thr):
                return p_blow
            return None
        return edge_fn

    edge_fn = edge_fn_factory(p_ast, p_blow, thrA)

    def report_bankroll(label, rows, ef):
        bank, lg, nb = kelly_bankroll(rows, ef, frac=0.25)
        # flat baseline terminal "bankroll" = 1 + sum(unit_pnl)*flat_stake(0.01)
        flat = 1.0
        for b in sorted(rows, key=lambda x: x["gdate"]):
            v = unit_pnl(b)
            if v is not None:
                flat += 0.01 * v
        print(f"    {label:28s} Kelly-term={bank:7.3f}x  log-growth={lg:+.3f}  "
              f"n_bet={nb}  (flat-1%-stake term={flat:.3f})")

    # held-out LATE A (true OOS within A), then cross-corpus B and C
    print("  -- LATE-A (held out from p_hat fit) --")
    report_bankroll("PORT (AST+BLOW)", union_dedupe(gated_ast(lateA), blowout_starter_under(lateA, thrA)), edge_fn)
    report_bankroll("L_AST only", gated_ast(lateA), edge_fn)
    report_bankroll("L_BLOW only", blowout_starter_under(lateA, thrA), edge_fn)
    print("  -- Family B (cross-book, OOS) --")
    report_bankroll("PORT (AST+BLOW)", legs["B"]["PORT"], edge_fn)
    report_bankroll("L_AST only", legs["B"]["L_AST"], edge_fn)
    report_bankroll("L_BLOW only", legs["B"]["L_BLOW"], edge_fn)
    print("  -- Family C (cross-season, OOS) --")
    report_bankroll("PORT (AST+BLOW)", legs["C"]["PORT"], edge_fn)
    report_bankroll("L_AST only", legs["C"]["L_AST"], edge_fn)
    report_bankroll("L_BLOW only", legs["C"]["L_BLOW"], edge_fn)

    print("\n" + "#" * 84)
    print("# PORTFOLIO COMPLETE -- see docs/_audits/PRED_EXP_multi_signal_portfolio_2026-06-01.md")
    print("#" * 84)


if __name__ == "__main__":
    run()
