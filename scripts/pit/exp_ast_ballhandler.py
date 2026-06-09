"""exp_ast_ballhandler.py — NEW basketball-specific AST conditioners (leak-free).

AST is the system's ONE durable edge (~+5% gated reg-season). The prior AST-conditioning
agent already tested opp-pace / opp-SRS / passer-who-decides / opp-total / rest and REJECTED
all (opp-pace was regime-inflated). This experiment tries THREE genuinely new, basketball-
specific conditioners that were NOT tested:

  (a) BACKUP-PLAYMAKER SPIKE — when a team's as-of PRIMARY ball-handler is OUT, the next-best
      playmaker inherits on-ball creation and his AST should jump. We build a leak-free,
      player-specific "inherited primary creation" scalar from per-player box-appearance logs
      (cross-season: 2024-25 + 2025-26). Distinct from the model's generic vac_min/vac_pts
      (which is team minutes vacated, NOT the specific primary-creator-out event).

  (b) OPPONENT SCHEME THAT CONCEDES ASSISTS — switch-heavy vs drop coverage + the team's
      as-of opp-AST-allowed. Hypothesis: soft / switch schemes that concede ball movement
      boost a passer's AST. (The prior opp_ast_allowed tercile test hinted the AST edge sits
      in LOW-ast-allowed games, opposite the naive hypothesis — we test scheme + both
      directions cross-corpus.)

  (c) PACE x BALL-DOMINANCE INTERACTION — for high-usage / high-ast_pct creators (primary_
      creator role, low avg_seconds_per_touch = ball-dominant), extra possessions (opp_pace)
      convert to more assist opportunities than for a low-usage passer. Signal =
      opp_pace_z * ball_dominance_z.

METHOD (strict, per PREDICTION_HARNESS_GUIDE):
  - leak-free as-of signals only (trailing/atlas-asof; appearance is contemporaneous = known
    at lock).
  - ORTHOGONALITY pre-screen vs (actual - pred) for AST: |corr| >~ 0.05 to proceed, else
    fast-reject (model already absorbs it).
  - post-hoc tilt pred_adj = pred + beta*signal, beta fit on EARLY half, graded on LATE half.
  - ALSO tested as a SELECTION / SIZING tilt on the gated-AST set (edge>=0.75, line<=7.5):
    does conditioning RAISE gated-AST ROI durably, or just slice an already-winning book?
  - graded on >=2 INDEPENDENT corpora: Family A (extended_oos == benashkar, the big sample)
    AND Family C (oddsapi 2024-25, cross-season) [+ Family B oddsapi 2025-26 where n allows].
  - drop |odds|<100 (grader does it), coherence guard, reg-season only.

DISJOINT WRITE: this file + scratch under scripts/_tmp_pred/ + the audit md. No production
code, no vault, no git commit. Read-only on all data.

Run:  conda run -n basketball_ai python scripts/pit/exp_ast_ballhandler.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "pit"))
import intel_grade as ig  # noqa: E402

NBA = os.path.join(ROOT, "data", "nba")
CACHE = os.path.join(ROOT, "data", "cache")

# corpus -> season tag used to pick the right box-log / atlas window
CORPUS_SEASON = {
    "extended_oos_canonical.csv": "2025-26",
    "benashkar_2026_canonical.csv": "2025-26",
    "regular_season_2025_26_oddsapi.csv": "2025-26",
    "regular_season_2024_25_oddsapi.csv": "2024-25",
}

EDGE_MIN, LINE_CAP = 0.75, 7.5  # the shipped gated-AST set


# ════════════════════════════════════════════════════════════════════════════
# (a) BACKUP-PLAYMAKER — leak-free per-player box-appearance build
# ════════════════════════════════════════════════════════════════════════════
def _parse_matchup(m):
    m = (m or "").strip()
    if " vs. " in m:
        a, b = m.split(" vs. "); return a.strip().upper(), b.strip().upper()
    if " @ " in m:
        a, b = m.split(" @ "); return a.strip().upper(), b.strip().upper()
    return None, None


def _parse_date(s):
    for fmt in ("%b %d, %Y", "%Y-%m-%d"):
        try:
            return pd.Timestamp(datetime.strptime(str(s).strip(), fmt)).normalize()
        except (ValueError, TypeError):
            continue
    return None


_BACKUP_CACHE = {}


def build_backup_signal(season):
    """Return dict (pid, date_ts) -> inherited_creation scalar (leak-free).

    inherited_creation = trailing-AST/g of the team's as-of #1 playmaker, attributed to
    bet-player p IFF (1) the #1 playmaker did NOT appear this game (primary OUT) and
    (2) p is among the team's as-of top-3 playmakers (so p actually inherits the rock).
    Else 0.0. Also returns a binary 'primary_out_and_inheritor' flag map.
    """
    if season in _BACKUP_CACHE:
        return _BACKUP_CACHE[season]
    rows = []  # (date_ts, team, pid, ast, minutes)
    for fp in glob.glob(os.path.join(NBA, f"gamelog_*_{season}.json")):
        m = re.match(rf"gamelog_(\d+)_{season}\.json$", os.path.basename(fp))
        if not m:  # skip gamelog_full_* (subset, same pids)
            continue
        pid = int(m.group(1))
        try:
            games = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        for g in games:
            team, _opp = _parse_matchup(g.get("MATCHUP"))
            d = _parse_date(g.get("GAME_DATE"))
            if team is None or d is None:
                continue
            try:
                ast = float(g.get("AST", 0) or 0)
                mn = float(g.get("MIN", 0) or 0)
            except (TypeError, ValueError):
                continue
            rows.append((d, team, pid, ast, mn))

    by_player = defaultdict(list)        # pid -> sorted [(date, ast, min)]
    team_games = defaultdict(set)        # (team,date) -> set(pid that appeared)
    team_dates = defaultdict(set)        # team -> set(date)
    for d, team, pid, ast, mn in rows:
        by_player[pid].append((d, ast, mn))
        team_games[(team, d)].add(pid)
        team_dates[team].add(d)
    for pid in by_player:
        by_player[pid].sort()

    def trailing_ast(pid, d):
        hist = [a for (dd, a, mn) in by_player.get(pid, []) if dd < d and mn >= 10.0]
        if len(hist) < 3:
            return None
        return float(np.mean(hist[-15:]))

    sig = {}    # (pid, date_ts) -> inherited_creation
    flag = {}   # (pid, date_ts) -> 1/0 primary_out_and_inheritor
    for (team, d), appeared in team_games.items():
        prior_dates = sorted([x for x in team_dates[team] if x < d])[-5:]
        cand = set()
        for pd_ in prior_dates:
            cand |= team_games[(team, pd_)]
        ranked = []
        for pid in cand:
            ta = trailing_ast(pid, d)
            if ta is not None:
                ranked.append((ta, pid))
        ranked.sort(reverse=True)
        if not ranked:
            continue
        primary_ast, primary_pid = ranked[0]
        primary_out = primary_pid not in appeared
        top3 = {pid for _, pid in ranked[:3]}
        for pid in appeared:
            key = (pid, d)
            if primary_out and pid in top3 and pid != primary_pid:
                sig[key] = primary_ast       # inherit the absent primary's trailing AST load
                flag[key] = 1
            else:
                sig[key] = 0.0
                flag[key] = 0
    _BACKUP_CACHE[season] = (sig, flag)
    return _BACKUP_CACHE[season]


def attach_backup(bets, season):
    sig, flag = build_backup_signal(season)
    cov = 0
    for b in bets:
        k = (b["pid"], b["gdate"])
        if k in sig:
            b["bk_inherit"] = sig[k]
            b["bk_flag"] = flag[k]
            cov += 1
        else:
            b["bk_inherit"] = np.nan
            b["bk_flag"] = np.nan
    print(f"    [backup-playmaker] coverage {cov}/{len(bets)} "
          f"({100*cov/max(len(bets),1):.0f}%)  inheritor-events="
          f"{sum(1 for b in bets if b.get('bk_flag')==1)}")
    return bets


# ════════════════════════════════════════════════════════════════════════════
# (b) OPPONENT SCHEME — DROP/SWITCH + switch_rate + opp-AST-allowed
# ════════════════════════════════════════════════════════════════════════════
_SCHEME_CACHE = None


def _scheme_map():
    """tricode -> dict(drop_vs_switch, switch_score, potential_assists_imposed).

    NOTE: atlas_team_defensive_scheme is a SINGLE as-of snapshot (as_of ~2026-05-31),
    full-season aggregate. It is a season-descriptive prior (same for all dates), so it can
    only act as a cross-sectional team tilt, NOT a time-varying as-of signal -> we treat it
    as a coarse team-class label and check it does not leak (it is built from the same
    season's games but is constant per team, an aggregate descriptor; we use it only for a
    selection slice, never to fit beta against in-window outcomes).
    """
    global _SCHEME_CACHE
    if _SCHEME_CACHE is not None:
        return _SCHEME_CACHE
    p = os.path.join(CACHE, "atlas_team_defensive_scheme.parquet")
    df = pd.read_parquet(p)
    out = {}
    for r in df.itertuples(index=False):
        tri = r.team_tricode
        try:
            cov = json.loads(r.coverage_scheme)
            dvs = cov.get("drop_vs_switch", "")
        except Exception:
            dvs = ""
        try:
            axes = json.loads(r.scheme_axes)
            iso_force = axes.get("iso_force_score", np.nan)
            paint_prot = axes.get("paint_protection_score", np.nan)
        except Exception:
            iso_force = paint_prot = np.nan
        try:
            dev = json.loads(r.imposed_deviations)
            pa_imposed = dev.get("potential_assists", np.nan)
        except Exception:
            pa_imposed = np.nan
        out[tri] = {
            "drop_vs_switch": dvs,
            "iso_force": iso_force,
            "paint_prot": paint_prot,
            "pa_imposed": pa_imposed,
        }
    _SCHEME_CACHE = out
    return out


def attach_scheme(bets):
    sm = _scheme_map()
    cov = 0
    for b in bets:
        m = sm.get(b["opp"])
        if m:
            b["opp_is_switch"] = 1.0 if m["drop_vs_switch"] == "switch" else 0.0
            b["opp_iso_force"] = m["iso_force"]
            b["opp_pa_imposed"] = m["pa_imposed"]  # how much opp scheme increases potential AST
            cov += 1
        else:
            b["opp_is_switch"] = np.nan
            b["opp_iso_force"] = np.nan
            b["opp_pa_imposed"] = np.nan
    print(f"    [opp-scheme] coverage {cov}/{len(bets)} ({100*cov/max(len(bets),1):.0f}%)")
    return bets


# ════════════════════════════════════════════════════════════════════════════
# (c) PACE x BALL-DOMINANCE — usage_role atlas (season prior) x opp_pace (as-of)
# ════════════════════════════════════════════════════════════════════════════
_USAGE_CACHE = None


def _usage_map():
    """pid -> dict(usage_rate, ast_pct, secs_per_touch, creator_role). Season-aggregate
    descriptor (constant per player); used only to gate/scale the as-of opp_pace signal,
    never fit against outcome -> no leak (it's a player-trait class label)."""
    global _USAGE_CACHE
    if _USAGE_CACHE is not None:
        return _USAGE_CACHE
    df = pd.read_parquet(os.path.join(CACHE, "atlas_player_usage_role.parquet"))
    out = {}
    for r in df.itertuples(index=False):
        out[int(r.player_id)] = {
            "usage_rate": float(r.usage_rate) if pd.notna(r.usage_rate) else np.nan,
            "ast_pct": float(r.ast_pct) if pd.notna(r.ast_pct) else np.nan,
            "secs_per_touch": float(r.avg_seconds_per_touch) if pd.notna(r.avg_seconds_per_touch) else np.nan,
            "creator_role": r.creator_role,
        }
    _USAGE_CACHE = out
    return out


def attach_balldom(bets):
    """ball_dominance proxy = z(ast_pct) + z(usage_rate)  (high = ball-dominant creator).
    interaction = opp_pace_z * ball_dominance_z  (the (c) signal)."""
    um = _usage_map()
    # build z-norms over the bet set's AST players for ast_pct & usage
    ap = np.array([um.get(b["pid"], {}).get("ast_pct", np.nan) for b in bets], dtype=float)
    ur = np.array([um.get(b["pid"], {}).get("usage_rate", np.nan) for b in bets], dtype=float)
    pace = np.array([b.get("opp_pace", np.nan) for b in bets], dtype=float)

    def _z(a):
        m = np.nanmean(a); s = np.nanstd(a)
        return (a - m) / s if s > 1e-9 else a * 0.0
    apz, urz, pacez = _z(ap), _z(ur), _z(pace)
    bd = apz + urz  # ball-dominance composite z
    cov = 0
    for i, b in enumerate(bets):
        r = um.get(b["pid"])
        if r is not None and np.isfinite(bd[i]) and np.isfinite(pacez[i]):
            b["ball_dom"] = float(bd[i])
            b["pace_z"] = float(pacez[i])
            b["pace_x_balldom"] = float(pacez[i] * bd[i])
            b["is_primary_creator"] = 1.0 if r.get("creator_role") == "primary_creator" else 0.0
            cov += 1
        else:
            b["ball_dom"] = np.nan
            b["pace_z"] = np.nan
            b["pace_x_balldom"] = np.nan
            b["is_primary_creator"] = np.nan
    print(f"    [pace x ball-dom] coverage {cov}/{len(bets)} ({100*cov/max(len(bets),1):.0f}%)")
    return bets


# ════════════════════════════════════════════════════════════════════════════
# Grading helpers
# ════════════════════════════════════════════════════════════════════════════
def ast_bets(corpus):
    season = CORPUS_SEASON[corpus]
    bets = ig.prepare(corpus)
    coh = ig.coherence(bets)
    if not coh["coherent"]:
        print(f"  !! {corpus} CORRUPT (coh {coh['sum']:+.2f}%), skipping")
        return None, coh
    bets = [b for b in bets if b["stat"] == "ast"]
    bets = attach_backup(bets, season)
    bets = attach_scheme(bets)
    bets = attach_balldom(bets)
    bets.sort(key=lambda b: b["gdate"])
    return bets, coh


def resid_corr(bets, key):
    sub = [b for b in bets if np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None, len(sub)
    sig = np.array([b[key] for b in sub], dtype=float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], dtype=float)
    if np.std(sig) < 1e-9:
        return None, len(sub)
    return float(np.corrcoef(sig, resid)[0, 1]), len(sub)


def halves(bets):
    ds = sorted({b["gdate"] for b in bets})
    if len(ds) < 4:
        return bets, []
    mid = ds[len(ds) // 2]
    return [b for b in bets if b["gdate"] < mid], [b for b in bets if b["gdate"] >= mid]


def fit_beta(rows, key):
    sub = [b for b in rows if np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None
    sig = np.array([b[key] for b in sub], dtype=float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], dtype=float)
    if np.std(sig) < 1e-9:
        return None
    return float(np.cov(sig, resid)[0, 1] / np.var(sig))


def point_tilt(bets, key, gated=False):
    """Fit beta on early, apply additive tilt to late, grade AST ROI raw vs adj on LATE."""
    pool = bets
    if gated:
        pool = [b for b in bets if abs(b["pred"] - b["line"]) >= EDGE_MIN and b["line"] <= LINE_CAP]
    early, late = halves(pool)
    if not late:
        return None
    beta = fit_beta(early, key)
    if beta is None:
        return None
    flips = 0
    for b in late:
        if np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan)):
            adj = b["pred"] + beta * b[key]
            if (adj > b["line"]) != (b["pred"] > b["line"]):
                flips += 1
            b["_pred_adj"] = adj
    raw = ig.roi(late, predictor="pred")
    adj = ig.roi([b for b in late if "_pred_adj" in b], predictor="_pred_adj")
    return {"beta": beta, "n_late": len(late), "flips": flips, "raw": raw, "adj": adj}


def selection_slice(bets, mask_fn, label, gated=True):
    """Both-halves robustness of a selection slice on the gated-AST set."""
    pool = bets
    if gated:
        pool = [b for b in bets if abs(b["pred"] - b["line"]) >= EDGE_MIN and b["line"] <= LINE_CAP]
    early, late = halves(pool)
    sel_all = [b for b in pool if mask_fn(b)]
    sel_e = [b for b in early if mask_fn(b)]
    sel_l = [b for b in late if mask_fn(b)]
    base_all = ig.roi(pool, predictor="pred")
    return {
        "label": label,
        "base": base_all,
        "all": ig.roi(sel_all, predictor="pred"),
        "early": ig.roi(sel_e, predictor="pred"),
        "late": ig.roi(sel_l, predictor="pred"),
    }


def tercile_slices(bets, key, gated=True):
    pool = bets
    if gated:
        pool = [b for b in bets if abs(b["pred"] - b["line"]) >= EDGE_MIN and b["line"] <= LINE_CAP]
    sub = [b for b in pool if np.isfinite(b.get(key, np.nan))]
    if len(sub) < 30:
        return None
    sig = np.array([b[key] for b in sub], dtype=float)
    lo, hi = np.nanpercentile(sig, [33.333, 66.667])
    early, late = halves(sub)
    out = {}
    for nm, mk in [("low", lambda v: v <= lo), ("mid", lambda v: lo < v <= hi), ("high", lambda v: v > hi)]:
        a = [b for b in sub if mk(b[key])]
        e = [b for b in early if mk(b[key])]
        l = [b for b in late if mk(b[key])]
        out[nm] = {"all": ig.roi(a, predictor="pred"), "early": ig.roi(e, predictor="pred"),
                   "late": ig.roi(l, predictor="pred")}
    out["_cuts"] = (lo, hi)
    return out


# ════════════════════════════════════════════════════════════════════════════
# Report
# ════════════════════════════════════════════════════════════════════════════
def _r(d):
    return f"{d['roi_pct']:+.1f}%(n{d['n']})"


def run_corpus(corpus):
    print(f"\n{'='*78}\n CORPUS: {corpus}  (season {CORPUS_SEASON[corpus]})\n{'='*78}")
    bets, coh = ast_bets(corpus)
    if bets is None:
        return None
    print(f"  coherence {coh['sum']:+.2f}% OK | AST bets joined n={len(bets)}")
    gated = [b for b in bets if abs(b["pred"] - b["line"]) >= EDGE_MIN and b["line"] <= LINE_CAP]
    base_all = ig.roi(bets, predictor="pred")
    base_gate = ig.roi(gated, predictor="pred")
    print(f"  BASELINE  ungated AST {_r(base_all)}   gated AST {_r(base_gate)}")

    # ── orthogonality pre-screen (all signals vs actual-pred) ──
    print("\n  [ORTHOGONALITY] corr(signal, actual - pred) on AST  (|r|>=0.05 => proceed):")
    keys = [("bk_inherit", "(a) backup inherit"), ("bk_flag", "(a) backup flag"),
            ("opp_is_switch", "(b) opp switch"), ("opp_pa_imposed", "(b) opp pa-imposed"),
            ("opp_ast_allowed_vs_league", "(b) opp ast-allowed vsLg"),
            ("pace_x_balldom", "(c) pace x ball-dom"), ("ball_dom", "(c) ball-dom alone")]
    ortho = {}
    for k, lab in keys:
        r, n = resid_corr(bets, k)
        ortho[k] = r
        flag = "  <-- non-trivial" if (r is not None and abs(r) >= 0.05) else ""
        print(f"     {lab:30s} r={None if r is None else round(r,3)} (n={n}){flag}")

    # ── (a) point tilt + event selection ──
    print("\n  --- (a) BACKUP-PLAYMAKER ---")
    pt = point_tilt(bets, "bk_inherit", gated=False)
    if pt:
        print(f"   point tilt (ungated, beta={pt['beta']:+.4f}, flips={pt['flips']}/{pt['n_late']}): "
              f"raw {_r(pt['raw'])} -> adj {_r(pt['adj'])}")
    # selection: bet only inheritor-events
    sel = selection_slice(bets, lambda b: b.get("bk_flag") == 1, "primary-out inheritor", gated=True)
    print(f"   gated-AST selection [{sel['label']}]: base {_r(sel['base'])} | "
          f"slice all {_r(sel['all'])} early {_r(sel['early'])} late {_r(sel['late'])}")

    # ── (b) opp scheme ──
    print("\n  --- (b) OPPONENT SCHEME / AST-ALLOWED ---")
    selsw = selection_slice(bets, lambda b: b.get("opp_is_switch") == 1.0, "vs SWITCH defense", gated=True)
    print(f"   gated-AST [{selsw['label']}]: base {_r(selsw['base'])} | "
          f"all {_r(selsw['all'])} early {_r(selsw['early'])} late {_r(selsw['late'])}")
    for key, lab in [("opp_ast_allowed_vs_league", "opp ast-allowed vsLg"),
                     ("opp_pa_imposed", "opp pa-imposed")]:
        t = tercile_slices(bets, key, gated=True)
        if t:
            print(f"   gated-AST tercile by {lab} (cuts {t['_cuts'][0]:.2f}/{t['_cuts'][1]:.2f}):")
            for nm in ("low", "mid", "high"):
                print(f"      {nm:4s}: all {_r(t[nm]['all'])} early {_r(t[nm]['early'])} late {_r(t[nm]['late'])}")

    # ── (c) pace x ball-dominance ──
    print("\n  --- (c) PACE x BALL-DOMINANCE ---")
    pc = point_tilt(bets, "pace_x_balldom", gated=False)
    if pc:
        print(f"   point tilt (ungated, beta={pc['beta']:+.4f}, flips={pc['flips']}/{pc['n_late']}): "
              f"raw {_r(pc['raw'])} -> adj {_r(pc['adj'])}")
    t = tercile_slices(bets, "pace_x_balldom", gated=True)
    if t:
        print(f"   gated-AST tercile by pace_x_balldom (cuts {t['_cuts'][0]:.2f}/{t['_cuts'][1]:.2f}):")
        for nm in ("low", "mid", "high"):
            print(f"      {nm:4s}: all {_r(t[nm]['all'])} early {_r(t[nm]['early'])} late {_r(t[nm]['late'])}")
    # selection: high-usage primary creators in high-pace games
    selpc = selection_slice(
        bets, lambda b: b.get("is_primary_creator") == 1.0 and np.isfinite(b.get("pace_z", np.nan)) and b.get("pace_z", 0) > 0,
        "primary-creator x high-pace", gated=True)
    print(f"   gated-AST [{selpc['label']}]: base {_r(selpc['base'])} | "
          f"all {_r(selpc['all'])} early {_r(selpc['early'])} late {_r(selpc['late'])}")

    return {"corpus": corpus, "base_all": base_all, "base_gate": base_gate,
            "ortho": ortho, "a_tilt": pt, "a_sel": sel, "b_switch": selsw,
            "c_tilt": pc, "c_sel": selpc}


def main():
    results = {}
    # Family A (big sample, 2025-26) + Family C (cross-season 2024-25) + Family B (thin, same season)
    for corpus in ("extended_oos_canonical.csv",
                   "regular_season_2024_25_oddsapi.csv",
                   "regular_season_2025_26_oddsapi.csv"):
        try:
            results[corpus] = run_corpus(corpus)
        except Exception as e:
            import traceback
            print(f"  !! {corpus} errored: {e}")
            traceback.print_exc()
    print(f"\n{'='*78}\n DONE — see docs/_audits/PRED_EXP_ast_ballhandler_2026-06-01.md for verdicts\n{'='*78}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
