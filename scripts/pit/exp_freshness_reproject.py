"""exp_freshness_reproject.py — THE FRESHNESS LEVER experiment.

The one thing Wave L said might still work: SAME-DAY FRESHNESS. Every HISTORICAL
feature is already absorbed/priced vs the CLOSING line, but the model is uncertain
pregame about WHO PLAYS. Conditioning on the CONFIRMED inactive set (knowable ~1hr
pre-tip) is information the pregame OOF substrate does not have — and, critically,
the model has NO `vac_ast` feature at all (calibration_frame_v2 has vac_min/vac_pts
only). When a primary CREATOR is confirmed OUT, his assists re-route to teammates;
that is a concrete, named gap in the one stat we beat Vegas on (AST).

TWO TESTS (read-only, leak-free, default-OFF reference impl, no prod edits):

  TEST 1 — THE vac_ast GAP
    Build a leak-free `vac_ast` (vacated assists from confirmed-OUT regulars, by the
    box-appearance recipe of exp_teammate_out.py, extended to AST). Screen
    orthogonality corr(vac_ast, actual-pred) on AST, then a held-out additive tilt +
    selection/sizing, graded on >=2 INDEPENDENT corpora. Report SPECIFICALLY on the
    confirmed-OUT subset (n_out>0) where freshness matters, not just the full book.

  TEST 2 — CONFIRMED-INACTIVE RE-PROJECTION + CLV FRAMING
    reproject_on_confirmed_inactives(base_pred, confirmed_out_set, ...): recompute
    vac_min/vac_pts/vac_ast from the CONFIRMED set and re-project beneficiaries.
    Using box-appearance as ground-truth "confirmed out", measure
      (a) MAE improvement of the re-projection vs the pregame baseline on
          confirmed-out games (the accuracy lift; should approach the oracle), AND
      (b) ROI vs CLOSING lines (expect ~0 — the close already adjusted; CONFIRM it,
          it explains the Wave L rejects).
    Then frame the real edge honestly: it is CLV/timing (bet the OPENER before the
    close moves on the news), which a closing-line backtest cannot measure — quantify
    the closing-vs-implied-pre-news line MOVE on confirmed-out beneficiary games as a
    proxy for the capturable CLV.

DELIVERABLE: `reproject_on_confirmed_inactives` is a clean, GATED (default-OFF,
byte-identical when off) reference implementation the live path could later call when
REAL inactive news arrives. It is NOT wired into prod.

Run:  conda run -n basketball_ai python scripts/pit/exp_freshness_reproject.py
Discipline: drops |odds|<100 (grader does it), coherence guard, reg-season,
Family A (benashkar/extended_oos 2025-26) + Family C (oddsapi 2024-25) — independent.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_grade as ig  # noqa: E402

ROOT = ig.ROOT
NBA = os.path.join(ROOT, "data", "nba")

# corpus -> gamelog season slug used to build vac_* (box-appearance source)
CORPUS_SEASON = {
    "extended_oos_canonical.csv": "2025-26",
    "benashkar_2026_canonical.csv": "2025-26",
    "regular_season_2025_26_oddsapi.csv": "2025-26",
    "regular_season_2024_25_oddsapi.csv": "2024-25",
}

# ----------------------------------------------------------------------------
# 0. helpers
# ----------------------------------------------------------------------------

def _team_of(matchup):
    if not matchup:
        return None
    if " @ " in matchup:
        return matchup.split(" @ ")[0].strip()
    if " vs. " in matchup:
        return matchup.split(" vs. ")[0].strip()
    return None


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------
# 1. LEAK-FREE vac_* BUILDER (box-appearance, extended to AST) — per season
#    Returns, per (pid, iso-date):
#       vac_min, vac_pts, vac_ast, n_out  (vacated L10 load of confirmed-OUT regulars)
#    AND the team-side ground-truth needed for re-projection:
#       own_team, own_l10_ast, own_l10_min, team_played_ids, team_out_ids,
#       team_played_l10ast_sum (for share-based re-projection)
# ----------------------------------------------------------------------------
_SIG_CACHE: dict = {}


def build_vac_signals(season: str) -> dict:
    """Leak-free per-(pid,date) vacated load incl. AST + team context for re-proj.

    A 'regular' = a teammate whose as-of L10 MIN >= 15 who appeared in any of the
    team's previous 3 games. Confirmed-OUT = a regular who did NOT appear this game
    (box-appearance is the ground-truth 'confirmed inactive'). Everything as-of
    prior games only => leak-free.
    """
    if season in _SIG_CACHE:
        return _SIG_CACHE[season]

    # Pass 1: per player, chronological as-of L10 min/pts/ast BEFORE each game.
    rows_by_td = defaultdict(list)   # (team, iso) -> [{pid,l10_min,l10_pts,l10_ast}]
    for fp in glob.glob(os.path.join(NBA, f"gamelog_*_{season}.json")):
        try:
            pid = int(os.path.basename(fp).split("_")[1])
            log = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        recs = []
        for g in log:
            d = pd.to_datetime(g.get("GAME_DATE"), errors="coerce")
            if pd.isna(d):
                continue
            recs.append((d, g))
        recs.sort(key=lambda kv: kv[0])
        mins, ptss, asts = [], [], []
        for d, g in recs:
            team = _team_of(g.get("MATCHUP"))
            l10_min = float(np.mean(mins[-10:])) if mins else 0.0
            l10_pts = float(np.mean(ptss[-10:])) if ptss else 0.0
            l10_ast = float(np.mean(asts[-10:])) if asts else 0.0
            ds = d.date().isoformat()
            if team:
                rows_by_td[(team, ds)].append(
                    {"pid": pid, "l10_min": l10_min, "l10_pts": l10_pts,
                     "l10_ast": l10_ast})
            m = _f(g.get("MIN"))
            if m is not None and m >= 1:
                mins.append(m)
                ptss.append(_f(g.get("PTS")) or 0.0)
                asts.append(_f(g.get("AST")) or 0.0)

    team_dates = defaultdict(list)
    for (team, ds) in rows_by_td:
        team_dates[team].append(ds)
    for t in team_dates:
        team_dates[t] = sorted(set(team_dates[t]))

    def recent_roster(team, ds):
        dates = team_dates[team]
        i = dates.index(ds)
        roster = {}
        for j in range(max(0, i - 3), i):
            for rec in rows_by_td[(team, dates[j])]:
                roster[rec["pid"]] = rec   # last-seen L10 carries
        return roster

    out = {}            # (pid, iso) -> signal dict
    for (team, ds), played in rows_by_td.items():
        if ds not in team_dates[team]:
            continue
        if team_dates[team].index(ds) < 3:
            continue   # need >=3 prior team games for a roster
        played_ids = {r["pid"] for r in played}
        roster = recent_roster(team, ds)
        vac_min = vac_pts = vac_ast = 0.0
        n_out = 0
        out_ids = []
        for pid, rec in roster.items():
            if pid in played_ids:
                continue
            if rec["l10_min"] >= 15:
                vac_min += rec["l10_min"]
                vac_pts += rec["l10_pts"]
                vac_ast += rec["l10_ast"]
                n_out += 1
                out_ids.append(pid)
        # team-side share denominator: sum of L10 AST of players who PLAYED
        # (the beneficiaries of vacated assists), for share-based re-projection
        team_played_l10ast = sum(r["l10_ast"] for r in played)
        team_played_l10min = sum(r["l10_min"] for r in played)
        for r in played:
            out[(r["pid"], ds)] = {
                "own_team": team,
                "vac_min": vac_min, "vac_pts": vac_pts, "vac_ast": vac_ast,
                "n_out": n_out,
                "own_l10_min": r["l10_min"], "own_l10_ast": r["l10_ast"],
                "team_played_l10ast": team_played_l10ast,
                "team_played_l10min": team_played_l10min,
            }
    _SIG_CACHE[season] = out
    return out


def attach_vac(bets, season):
    """Attach the leak-free vac_* (incl vac_ast) to bet dicts by (pid, iso-date).
    Bets keep going if unmatched (NaN) so coverage is visible. Returns match count."""
    sig = build_vac_signals(season)
    matched = 0
    for b in bets:
        ds = b["gdate"].date().isoformat()
        m = sig.get((b["pid"], ds))
        if m is not None:
            for k, v in m.items():
                b["va_" + k] = v
            matched += 1
        else:
            for k in ("vac_min", "vac_pts", "vac_ast", "n_out", "own_l10_min",
                      "own_l10_ast", "team_played_l10ast", "team_played_l10min"):
                b.setdefault("va_" + k, np.nan)
            b.setdefault("va_own_team", None)
    return matched


# ----------------------------------------------------------------------------
# 2. THE GATED REFERENCE IMPLEMENTATION (default-OFF, byte-identical when off)
#    reproject_on_confirmed_inactives(base_pred, confirmed_out_set, ...)
#    Live path could later call this when REAL inactive news arrives.
# ----------------------------------------------------------------------------

def reproject_on_confirmed_inactives(
    base_pred: float,
    stat: str,
    *,
    enabled: bool = False,
    vac_ast: float = 0.0,
    vac_pts: float = 0.0,
    vac_min: float = 0.0,
    own_l10_ast: float = 0.0,
    own_l10_min: float = 0.0,
    team_played_l10ast: float = 0.0,
    team_played_l10min: float = 0.0,
    ast_beta: float = 0.0,
    pts_beta: float = 0.0,
) -> float:
    """Re-project a pregame point prediction onto the CONFIRMED-inactive set.

    GATED: when `enabled=False` (default) returns `base_pred` UNCHANGED — byte
    identical — so wiring this into a live path is a no-op until a caller flips the
    flag with a real confirmed-out set. NOT wired into prod.

    Mechanism (AST): vacated assists from confirmed-out creators re-route to the
    players who actually take the floor, in proportion to each surviving player's
    share of the team's remaining L10 assist production. A surviving primary handler
    absorbs `share * vac_ast` extra assists; we damp by `ast_beta` (fit leak-free).
        share          = own_l10_ast / team_played_l10ast
        delta_ast      = ast_beta * share * vac_ast
    (PTS analog uses minutes-share of vacated points, damped by `pts_beta`.)
    """
    if not enabled:
        return base_pred
    pred = base_pred
    if stat == "ast" and np.isfinite(vac_ast) and vac_ast > 0:
        denom = team_played_l10ast if (np.isfinite(team_played_l10ast)
                                       and team_played_l10ast > 1e-6) else None
        if denom and np.isfinite(own_l10_ast):
            share = own_l10_ast / denom
            pred = pred + ast_beta * share * vac_ast
    elif stat == "pts" and np.isfinite(vac_pts) and vac_pts > 0:
        denom = team_played_l10min if (np.isfinite(team_played_l10min)
                                       and team_played_l10min > 1e-6) else None
        if denom and np.isfinite(own_l10_min):
            share = own_l10_min / denom
            pred = pred + pts_beta * share * vac_pts
    return pred


def _assert_gate_off_byte_identical():
    """Prove default-OFF => byte-identical (the gating contract)."""
    rng = np.random.default_rng(0)
    ok = True
    for _ in range(2000):
        bp = float(rng.normal(5, 3))
        st = rng.choice(["ast", "pts", "reb", "fg3m"])
        r = reproject_on_confirmed_inactives(
            bp, st, enabled=False,
            vac_ast=float(rng.uniform(0, 12)), vac_pts=float(rng.uniform(0, 40)),
            vac_min=float(rng.uniform(0, 80)), own_l10_ast=float(rng.uniform(0, 9)),
            own_l10_min=float(rng.uniform(0, 38)),
            team_played_l10ast=float(rng.uniform(5, 30)),
            team_played_l10min=float(rng.uniform(100, 240)),
            ast_beta=0.7, pts_beta=0.7)
        if r != bp:
            ok = False
            break
    print(f"[GATE] default-OFF byte-identical: {'PASS' if ok else 'FAIL'}")
    return ok


# ----------------------------------------------------------------------------
# 3. shared split / fit utilities
# ----------------------------------------------------------------------------

def split_halves(bets):
    ds = sorted(set(b["gdate"] for b in bets))
    if len(ds) < 4:
        return bets, []
    mid = ds[len(ds) // 2]
    return [b for b in bets if b["gdate"] < mid], [b for b in bets if b["gdate"] >= mid]


def residual_corr(bets, stat, key, out_only=False):
    sub = [b for b in bets if b["stat"] == stat]
    if out_only:
        sub = [b for b in sub if (b.get("va_n_out") or 0) > 0]
    sig = np.array([b.get(key, np.nan) for b in sub], float)
    pred = np.array([b.get("pred", np.nan) for b in sub], float)
    act = np.array([b.get("actual", np.nan) for b in sub], float)
    resid = act - pred
    m = np.isfinite(sig) & np.isfinite(resid)
    if m.sum() < 30 or np.std(sig[m]) < 1e-9:
        return None, int(m.sum())
    return float(np.corrcoef(sig[m], resid[m])[0, 1]), int(m.sum())


def fit_beta(bets, stat, key, out_only=False):
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan))]
    if out_only:
        sub = [b for b in sub if (b.get("va_n_out") or 0) > 0]
    if len(sub) < 30:
        return None, len(sub)
    sig = np.array([b[key] for b in sub], float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], float)
    if np.std(sig) < 1e-9:
        return None, len(sub)
    return float(np.cov(sig, resid)[0, 1] / np.var(sig)), len(sub)


# ============================================================================
# TEST 1 — THE vac_ast GAP
# ============================================================================

def test1_vac_ast_gap(corpus):
    print(f"\n{'='*78}\n TEST 1 — vac_ast GAP  |  CORPUS: {corpus}\n{'='*78}")
    season = CORPUS_SEASON[corpus]
    bets = ig.prepare(corpus)
    coh = ig.coherence(bets)
    print(f"  coherence sum {coh['sum']:+.2f}% ({'OK' if coh['coherent'] else 'CORRUPT'}) "
          f" joined n={len(bets)}")
    if not coh["coherent"]:
        print("  !! corrupt corpus — refuse to grade")
        return None
    nv = attach_vac(bets, season)
    ast = [b for b in bets if b["stat"] == "ast"]
    ast_out = [b for b in ast if (b.get("va_n_out") or 0) > 0]
    print(f"  vac attached {nv}/{len(bets)} ({100*nv/max(len(bets),1):.0f}%); "
          f"AST bets n={len(ast)}, of which confirmed-OUT (n_out>0) n={len(ast_out)} "
          f"({100*len(ast_out)/max(len(ast),1):.0f}%)")
    if ast_out:
        va = np.array([b["va_vac_ast"] for b in ast_out], float)
        print(f"  mean vac_ast on confirmed-out AST bets = {np.nanmean(va):.2f} "
              f"(max {np.nanmax(va):.1f})")

    # --- orthogonality: is vac_ast information the model lacks? ---
    print("\n  [orthogonality] corr(vac_ast, actual-pred) on AST:")
    r_all, n_all = residual_corr(bets, "ast", "va_vac_ast")
    r_out, n_out = residual_corr(bets, "ast", "va_vac_ast", out_only=True)
    print(f"    full AST       r={r_all} (n={n_all}) "
          f"{'<-- non-trivial' if (r_all is not None and abs(r_all)>=0.05) else ''}")
    print(f"    confirmed-OUT  r={r_out} (n={n_out}) "
          f"{'<-- non-trivial' if (r_out is not None and abs(r_out)>=0.05) else ''}")
    # control: vac_min/vac_pts (model HAS these) for contrast
    r_vm, _ = residual_corr(bets, "ast", "va_vac_min", out_only=True)
    print(f"    (control vac_min on OUT) r={r_vm}")

    # --- held-out additive tilt on AST (fit EARLY, grade LATE), confirmed-out focus ---
    early, late = split_halves(bets)
    print("\n  [held-out tilt] fit beta(vac_ast) on EARLY AST, grade LATE:")
    for label, oo in [("ALL AST", False), ("confirmed-OUT AST", True)]:
        beta, nf = fit_beta(early, "ast", "va_vac_ast", out_only=oo)
        if beta is None:
            print(f"    {label}: n={nf} too few to fit")
            continue
        sub = [b for b in late if b["stat"] == "ast"
               and np.isfinite(b.get("va_vac_ast", np.nan))]
        if oo:
            sub = [b for b in sub if (b.get("va_n_out") or 0) > 0]
        flips = 0
        for b in sub:
            b["_pa_t1"] = b["pred"] + beta * b["va_vac_ast"]
            if (b["pred"] > b["line"]) != (b["_pa_t1"] > b["line"]):
                flips += 1
        raw = ig.roi(sub, predictor="pred")
        adj = ig.roi(sub, predictor="_pa_t1")
        print(f"    {label}: beta={beta:+.4f} (fit n={nf}) | raw {raw['roi_pct']:+.2f}%"
              f"(n{raw['n']}) -> adj {adj['roi_pct']:+.2f}%(n{adj['n']}) "
              f"[flips={flips}/{len(sub)}] delta={adj['roi_pct']-raw['roi_pct']:+.2f}pp")

    # --- selection/sizing: AST bets where a creator is OUT (vac_ast high) ---
    print("\n  [selection] AST ROI by vac_ast presence (raw model bets):")
    no_out = [b for b in ast if (b.get("va_n_out") or 0) == 0]
    big_vac = [b for b in ast_out if (b.get("va_vac_ast") or 0) >= 3.0]
    for label, bb in [("no creator out", no_out), ("any reg out", ast_out),
                      ("vac_ast>=3", big_vac)]:
        r = ig.roi(bb, predictor="pred")
        print(f"    {label:18s}: {r['roi_pct']:+.2f}% (n{r['n']}, win {r['win_pct']:.1f}%)")
    # does vac_ast ADD to the KNOWN gated AST edge (edge>=0.75, line<=7.5)?
    print("  [adds-to-known-edge] gated AST (edge>=0.75) by vacancy:")
    for label, bb in [("no creator out", no_out), ("vac_ast>=3", big_vac)]:
        g = [b for b in bb if (b.get("line") or 99) <= 7.5]
        r = ig.roi(g, predictor="pred", edge_min=0.75)
        print(f"    {label:18s}: {r['roi_pct']:+.2f}% (n{r['n']}, win {r['win_pct']:.1f}%)")
    # both-halves robustness of the confirmed-out AST slice
    print("  [both-halves] confirmed-OUT AST raw ROI:")
    for nm, half in [("early", early), ("late", late)]:
        bb = [b for b in half if b["stat"] == "ast" and (b.get("va_n_out") or 0) > 0]
        r = ig.roi(bb, predictor="pred")
        print(f"    {nm}: {r['roi_pct']:+.2f}% (n{r['n']})")
    return {"r_out": r_out, "n_ast_out": len(ast_out)}


# ============================================================================
# TEST 2 — RE-PROJECTION + CLV FRAMING
# ============================================================================

def _fit_share_beta(bets, stat, season):
    """Leak-free: fit the re-projection damping so that
       share*vac drives (actual-pred). beta = cov(x, resid)/var(x),
       x = share*vac on confirmed-out rows of this stat."""
    xs, rs = [], []
    for b in bets:
        if b["stat"] != stat or (b.get("va_n_out") or 0) == 0:
            continue
        if stat == "ast":
            vac = b.get("va_vac_ast"); own = b.get("va_own_l10_ast")
            den = b.get("va_team_played_l10ast")
        else:
            vac = b.get("va_vac_pts"); own = b.get("va_own_l10_min")
            den = b.get("va_team_played_l10min")
        pred = b.get("pred"); act = b.get("actual")
        if not all(np.isfinite([vac, own, den, pred, act])) or den <= 1e-6 or vac <= 0:
            continue
        xs.append((own / den) * vac)
        rs.append(act - pred)
    if len(xs) < 30:
        return None, len(xs)
    xs = np.array(xs); rs = np.array(rs)
    if np.std(xs) < 1e-9:
        return None, len(xs)
    return float(np.cov(xs, rs)[0, 1] / np.var(xs)), len(xs)


def test2_reprojection_clv(corpus):
    print(f"\n{'='*78}\n TEST 2 — RE-PROJECTION + CLV  |  CORPUS: {corpus}\n{'='*78}")
    season = CORPUS_SEASON[corpus]
    bets = ig.prepare(corpus)
    coh = ig.coherence(bets)
    if not coh["coherent"]:
        print("  !! corrupt corpus — refuse to grade")
        return None
    attach_vac(bets, season)
    early, late = split_halves(bets)

    for stat in ("ast", "pts"):
        print(f"\n  --- {stat.upper()} re-projection ---")
        # fit damping beta on EARLY confirmed-out rows (leak-free)
        beta, nf = _fit_share_beta(early, stat, season)
        if beta is None:
            print(f"    too few confirmed-out {stat} rows to fit (n={nf})")
            continue
        bkey = "ast_beta" if stat == "ast" else "pts_beta"
        # apply gated re-projection to LATE confirmed-out rows
        out_rows = [b for b in late if b["stat"] == stat and (b.get("va_n_out") or 0) > 0]
        usable = []
        for b in out_rows:
            kw = dict(
                enabled=True, stat=stat,
                vac_ast=b.get("va_vac_ast", 0.0) or 0.0,
                vac_pts=b.get("va_vac_pts", 0.0) or 0.0,
                vac_min=b.get("va_vac_min", 0.0) or 0.0,
                own_l10_ast=b.get("va_own_l10_ast", 0.0) or 0.0,
                own_l10_min=b.get("va_own_l10_min", 0.0) or 0.0,
                team_played_l10ast=b.get("va_team_played_l10ast", 0.0) or 0.0,
                team_played_l10min=b.get("va_team_played_l10min", 0.0) or 0.0,
            )
            kw[bkey] = beta
            b["_reproj"] = reproject_on_confirmed_inactives(b["pred"], **kw)
            if np.isfinite(b.get("actual", np.nan)) and np.isfinite(b["pred"]):
                usable.append(b)
        if len(usable) < 20:
            print(f"    held-out confirmed-out {stat} rows n={len(usable)} (<20) — directional only")
        # (a) MAE lift on confirmed-out games vs baseline + vs ORACLE ceiling
        base_mae = float(np.mean([abs(b["actual"] - b["pred"]) for b in usable]))
        rep_mae = float(np.mean([abs(b["actual"] - b["_reproj"]) for b in usable]))
        # oracle ceiling = best possible additive constant per row in the re-proj
        # direction (i.e. if we knew the realized residual sign+mag for vac rows):
        # use the in-sample optimal beta on the SAME late rows (upper bound the
        # mechanism can reach), to bound how much headroom remains.
        bstar, _ = _fit_share_beta(late, stat, season)
        oracle_mae = base_mae
        if bstar is not None:
            o_rows = []
            for b in usable:
                kw = dict(
                    enabled=True, stat=stat,
                    vac_ast=b.get("va_vac_ast", 0.0) or 0.0,
                    vac_pts=b.get("va_vac_pts", 0.0) or 0.0,
                    vac_min=b.get("va_vac_min", 0.0) or 0.0,
                    own_l10_ast=b.get("va_own_l10_ast", 0.0) or 0.0,
                    own_l10_min=b.get("va_own_l10_min", 0.0) or 0.0,
                    team_played_l10ast=b.get("va_team_played_l10ast", 0.0) or 0.0,
                    team_played_l10min=b.get("va_team_played_l10min", 0.0) or 0.0,
                )
                kw[bkey] = bstar
                o_rows.append(abs(b["actual"] - reproject_on_confirmed_inactives(b["pred"], **kw)))
            oracle_mae = float(np.mean(o_rows))
        print(f"    fit beta(share*vac)={beta:+.4f} on EARLY (n={nf}); "
              f"held-out confirmed-out n={len(usable)}")
        print(f"    MAE  baseline       : {base_mae:.4f}")
        print(f"    MAE  re-projection  : {rep_mae:.4f}  ({(base_mae-rep_mae)/base_mae*100:+.2f}%)")
        print(f"    MAE  oracle ceiling : {oracle_mae:.4f}  ({(base_mae-oracle_mae)/base_mae*100:+.2f}%) "
              f"[in-sample best beta on held-out rows]")
        # (b) ROI vs CLOSING lines (expect ~0 — close already adjusted)
        raw = ig.roi(usable, predictor="pred")
        rep = ig.roi(usable, predictor="_reproj")
        flips = sum((b["pred"] > b["line"]) != (b["_reproj"] > b["line"]) for b in usable)
        print(f"    ROI vs CLOSE  baseline {raw['roi_pct']:+.2f}%(n{raw['n']}) "
              f"-> re-proj {rep['roi_pct']:+.2f}%(n{rep['n']}) "
              f"[flips={flips}/{len(usable)}] delta={rep['roi_pct']-raw['roi_pct']:+.2f}pp")

    # ---- CLV PROXY: closing-vs-implied-pre-news line move on confirmed-out games ----
    print("\n  --- CLV PROXY (closing vs implied pre-news line) ---")
    _clv_proxy(bets, season)
    return None


def _clv_proxy(bets, season):
    """A closing-line backtest CANNOT see the timing edge. Proxy the capturable CLV
    by the line MOVE the news forces: estimate the implied PRE-news line as the
    model's own pregame `pred` proxy for what the opener reflected (no inactive
    knowledge), and measure how far the CLOSING line sits from the freshness-aware
    re-projected number on confirmed-out beneficiary games.

    Two complementary proxies, AST (the bettable stat), confirmed-out beneficiary
    rows (own_l10_ast high => the creator's assists re-route to them):
      (1) |closing_line - pred|  on confirmed-out vs no-out AST rows: if the close
          already moved on the news, the close sits FURTHER from the stale pregame
          pred on out-games (the market priced freshness we didn't).
      (2) reproject delta = beta*share*vac_ast = the size of the freshness adjustment;
          the part of it the CLOSE has NOT yet absorbed is the capturable CLV at the
          OPENER. We report the mean reproject delta in line-points (the bet-able
          line move you race the close for).
    """
    beta, nf = _fit_share_beta(bets, "ast", season)
    ast = [b for b in bets if b["stat"] == "ast"]
    out_b = [b for b in ast if (b.get("va_n_out") or 0) > 0
             and (b.get("va_vac_ast") or 0) > 0]
    no_b = [b for b in ast if (b.get("va_n_out") or 0) == 0]
    # beneficiaries = confirmed-out rows where this player is a meaningful assist source
    benef = [b for b in out_b if (b.get("va_own_l10_ast") or 0) >= 2.0]

    def mean_abs_gap(rows):
        g = [abs(b["closing_line"] if False else b["line"] - b["pred"])
             for b in rows if np.isfinite(b.get("pred", np.nan))]
        return (float(np.mean(g)), len(g)) if g else (float("nan"), 0)

    g_out, n_o = mean_abs_gap(out_b)
    g_no, n_n = mean_abs_gap(no_b)
    g_ben, n_b = mean_abs_gap(benef)
    print(f"    mean |closing_line - pregame_pred| (AST):")
    print(f"      no creator out : {g_no:.3f} (n{n_n})")
    print(f"      confirmed-out  : {g_out:.3f} (n{n_o})")
    print(f"      beneficiaries  : {g_ben:.3f} (n{n_b})")

    if beta is not None and benef:
        deltas = []
        for b in benef:
            own = b.get("va_own_l10_ast"); den = b.get("va_team_played_l10ast")
            vac = b.get("va_vac_ast")
            if all(np.isfinite([own, den, vac])) and den > 1e-6 and vac > 0:
                deltas.append(beta * (own / den) * vac)
        if deltas:
            deltas = np.array(deltas)
            print(f"    freshness re-projection delta on beneficiary AST (the line "
                  f"move you race the close for):")
            print(f"      mean = {deltas.mean():+.3f} ast-line-pts  | "
                  f"median {np.median(deltas):+.3f} | p90 {np.percentile(deltas,90):+.3f} "
                  f"(n{len(deltas)}, fit beta={beta:+.4f})")
            # how much bigger is the move on big-vacancy games
            big = deltas[deltas >= np.percentile(deltas, 75)]
            print(f"      top-quartile vacancy mean delta = {big.mean():+.3f} ast-line-pts")


# ============================================================================
def main():
    print("#" * 78)
    print("# FRESHNESS LEVER EXPERIMENT — vac_ast gap + confirmed-inactive re-proj")
    print("# leak-free | drop|odds|<100 | coherence | reg-season | Family A + C")
    print("#" * 78)
    _assert_gate_off_byte_identical()

    FAMILY_A = "extended_oos_canonical.csv"        # 2025-26 DK/FD/MGM (big sample)
    FAMILY_C = "regular_season_2024_25_oddsapi.csv"  # 2024-25 odds-api (independent, cross-season)

    print("\n" + "=" * 78)
    print(" PART 1: THE vac_ast GAP (2 independent corpora)")
    print("=" * 78)
    test1_vac_ast_gap(FAMILY_A)
    test1_vac_ast_gap(FAMILY_C)

    print("\n" + "=" * 78)
    print(" PART 2: RE-PROJECTION + CLV (2 independent corpora)")
    print("=" * 78)
    test2_reprojection_clv(FAMILY_A)
    test2_reprojection_clv(FAMILY_C)

    print("\n" + "#" * 78)
    print("# DONE — see docs/_audits/PRED_EXP_freshness_reproject_2026-06-01.md for verdict")
    print("#" * 78)


if __name__ == "__main__":
    main()
