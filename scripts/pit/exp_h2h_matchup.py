"""exp_h2h_matchup.py — H2H "guarded by / torches this opponent" intelligence graded
as a leak-free prop conditioner vs real posted lines.

HYPOTHESIS (the original CourtVision scouting moat): a scorer who historically TORCHES a
specific opponent (production-vs-baseline ratio > 1.15) should go OVER vs them; one who gets
LOCKED DOWN (ratio < 0.85) should go UNDER. Never graded as a prop conditioner OOS.

SIGNAL (leak-free, strictly-prior-only): for each (player, opponent_team, bet_date) build the
player's prior production-vs-this-opponent average / prior overall average from multi-season
box logs (gamelog_<pid>_<season>.json). Team-level (robust) is the primary lens; the brief
notes specific-defender tails are too noisy. Require >=2 prior meetings.

  h2h_n     = # prior games vs this opp (strictly before bet date)
  h2h_ratio = mean(stat vs opp, prior) / mean(stat overall, prior)     (feast>1.15 / lockdown<0.85)
  h2h_delta = mean(stat vs opp, prior) - mean(stat overall, prior)     (raw scale, for additive tilt)

METHOD: orthogonality pre-screen vs (actual - pred); if |corr| >~ 0.05, fit additive tilt
beta on EARLY half, grade LATE half; also test feast/lockdown agreement selection. Grade
per-stat ROI lift via intel_grade on >=2 INDEPENDENT corpora (Family A + B/C). Coherence guard,
drop |odds|<100 (intel_grade does both), reg-season only.

READ-ONLY except this file + scratch. No production code, no git commit.
Run: conda run -n basketball_ai python scripts/pit/exp_h2h_matchup.py
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "pit"))
import intel_grade as ig  # noqa: E402

BOXLOG = os.path.join(ROOT, "scripts", "_tmp_pred", "player_boxlog.parquet")
STAT_COL = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M"}
MIN_PRIOR_MEETINGS = 2      # robust aggregate, not single-game tail
MIN_PRIOR_OVERALL = 5       # need a stable baseline denominator
FEAST = 1.15
LOCKDOWN = 0.85

# ------------------------------------------------------------------ signal build
_BOX = None


def _opp_from_matchup(m):
    if not isinstance(m, str):
        return None
    toks = m.replace("vs.", "vs").split()
    return toks[-1] if toks else None


def _build_boxlog() -> pd.DataFrame:
    """Combined leak-free multi-season player box log from per-player gamelog JSONs
    (2024-25 + 2025-26). One row per (player, game): player_id, game_date, opp, box stats."""
    import glob
    import json
    import re
    rows = []
    files = (glob.glob(os.path.join(ROOT, "data", "nba", "gamelog_*_2024-25.json"))
             + glob.glob(os.path.join(ROOT, "data", "nba", "gamelog_*_2025-26.json")))
    for f in files:
        m = re.search(r"gamelog_(\d+)_(\d{4}-\d{2})\.json", os.path.basename(f))
        if not m:
            continue
        pid = int(m.group(1))
        try:
            j = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(j, list):
            continue
        for r in j:
            try:
                gd = pd.to_datetime(r["GAME_DATE"], format="%b %d, %Y")
            except Exception:
                continue
            opp = _opp_from_matchup(r.get("MATCHUP"))
            if opp is None:
                continue
            rows.append({"player_id": pid, "game_date": gd, "opp": opp,
                         "PTS": r.get("PTS"), "REB": r.get("REB"),
                         "AST": r.get("AST"), "FG3M": r.get("FG3M")})
    df = pd.DataFrame(rows).dropna(subset=["game_date", "opp"])
    df = df.drop_duplicates(subset=["player_id", "game_date"])
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.normalize()
    df = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)
    try:
        os.makedirs(os.path.dirname(BOXLOG), exist_ok=True)
        df.to_parquet(BOXLOG, index=False)
    except Exception:
        pass
    return df


def _box() -> pd.DataFrame:
    global _BOX
    if _BOX is None:
        if os.path.exists(BOXLOG):
            df = pd.read_parquet(BOXLOG)
            df["game_date"] = pd.to_datetime(df["game_date"]).dt.normalize()
            _BOX = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)
        else:
            _BOX = _build_boxlog()
            print(f"    [built box log: {len(_BOX)} rows, {_BOX['player_id'].nunique()} players, "
                  f"{_BOX['game_date'].min().date()}..{_BOX['game_date'].max().date()}]")
    return _BOX


def attach_h2h(bets):
    """Add h2h_n / h2h_ratio / h2h_delta per bet (strictly-prior-only, leak-free).
    Leaves NaN where insufficient prior history."""
    box = _box()
    # group box rows by player for fast prior slicing
    by_pid = {pid: g for pid, g in box.groupby("player_id")}
    for b in bets:
        col = STAT_COL.get(b["stat"])
        b["h2h_n"] = np.nan
        b["h2h_ratio"] = np.nan
        b["h2h_delta"] = np.nan
        if col is None:
            continue
        g = by_pid.get(b["pid"])
        if g is None:
            continue
        prior = g[g["game_date"] < b["gdate"]]
        if len(prior) < MIN_PRIOR_OVERALL:
            continue
        overall_mean = prior[col].mean()
        if not np.isfinite(overall_mean) or overall_mean <= 1e-6:
            continue
        vs_opp = prior[prior["opp"] == b["opp"]]
        if len(vs_opp) < MIN_PRIOR_MEETINGS:
            continue
        vs_mean = vs_opp[col].mean()
        b["h2h_n"] = float(len(vs_opp))
        b["h2h_ratio"] = float(vs_mean / overall_mean)
        b["h2h_delta"] = float(vs_mean - overall_mean)
    cov = np.mean([np.isfinite(b["h2h_ratio"]) for b in bets])
    print(f"    h2h coverage: {cov*100:.1f}% of bets have a leak-free H2H signal "
          f"(>= {MIN_PRIOR_MEETINGS} prior meetings, >= {MIN_PRIOR_OVERALL} prior games)")
    return bets


# ------------------------------------------------------------------ analysis helpers
def residual_corr(bets, stat, key):
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None, len(sub)
    sig = np.array([b[key] for b in sub])
    resid = np.array([b["actual"] - b["pred"] for b in sub])
    if np.std(sig) < 1e-9:
        return None, len(sub)
    return float(np.corrcoef(sig, resid)[0, 1]), len(sub)


def fit_beta(rows, stat, key):
    sub = [b for b in rows if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None, len(sub)
    sig = np.array([b[key] for b in sub])
    resid = np.array([b["actual"] - b["pred"] for b in sub])
    if np.std(sig) < 1e-9:
        return None, len(sub)
    return float(np.cov(sig, resid)[0, 1] / np.var(sig)), len(sub)


def split_halves(bets):
    ds = sorted({b["gdate"] for b in bets})
    if len(ds) < 4:
        return [], []
    mid = ds[len(ds) // 2]
    return [b for b in bets if b["gdate"] < mid], [b for b in bets if b["gdate"] >= mid]


def grade_tilt(bets, stat, key, label):
    """Fit additive beta on early half, apply to late half. Return raw vs adj ROI on late."""
    early, late = split_halves(bets)
    beta, n_fit = fit_beta(early, stat, key)
    if beta is None:
        return None
    flips = 0
    for b in late:
        if b["stat"] == stat and np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan)):
            adj = b["pred"] + beta * b[key]
            old_dir = b["pred"] > b["line"]
            new_dir = adj > b["line"]
            if old_dir != new_dir:
                flips += 1
            b["_h2h_adj"] = adj
    late_stat = [b for b in late if b["stat"] == stat]
    have_adj = [b for b in late_stat if "_h2h_adj" in b]
    raw = ig.roi(late_stat, predictor="pred")
    adj = ig.roi(have_adj, predictor="_h2h_adj")
    return {"label": label, "stat": stat, "beta": beta, "n_fit": n_fit,
            "n_late": raw["n"], "flips": flips, "raw": raw, "adj": adj}


def grade_agreement(bets, stat):
    """Selection: keep bets where model direction AGREES with feast/lockdown tilt.
    feast (ratio>FEAST) => expect OVER; lockdown (ratio<LOCKDOWN) => expect UNDER.
    Grade only those agreement bets at raw pred (no point shift). OOS: fit nothing, just select."""
    early, late = split_halves(bets)
    out = {}
    for name, rows in (("EARLY", early), ("LATE", late)):
        sub = [b for b in rows if b["stat"] == stat and np.isfinite(b.get("h2h_ratio", np.nan))
               and np.isfinite(b.get("pred", np.nan))]
        agree, base = [], []
        for b in sub:
            model_over = b["pred"] > b["line"]
            feast = b["h2h_ratio"] > FEAST
            lock = b["h2h_ratio"] < LOCKDOWN
            base.append(b)
            if (feast and model_over) or (lock and not model_over):
                agree.append(b)
        out[name] = {
            "n_all": len(base), "all_roi": ig.roi(base, predictor="pred"),
            "n_agree": len(agree), "agree_roi": ig.roi(agree, predictor="pred"),
        }
    return out


def grade_buckets(bets, stat):
    """Diagnostic: raw model ROI within feast vs neutral vs lockdown H2H buckets (full sample)."""
    sub = [b for b in bets if b["stat"] == stat and np.isfinite(b.get("h2h_ratio", np.nan))]
    feast = [b for b in sub if b["h2h_ratio"] > FEAST]
    lock = [b for b in sub if b["h2h_ratio"] < LOCKDOWN]
    neut = [b for b in sub if LOCKDOWN <= b["h2h_ratio"] <= FEAST]
    return {
        "feast": (len(feast), ig.roi(feast, predictor="pred")),
        "neutral": (len(neut), ig.roi(neut, predictor="pred")),
        "lockdown": (len(lock), ig.roi(lock, predictor="pred")),
    }


# ------------------------------------------------------------------ driver
def run_corpus(corpus):
    print(f"\n{'='*78}\n===== {corpus} =====\n{'='*78}")
    bets = ig.prepare(corpus)
    coh = ig.coherence(bets)
    print(f"  joined-to-pred: {len(bets)} bets")
    print(f"  COHERENCE sum {coh['sum']:+.2f}%  ({'OK' if coh['coherent'] else 'CORRUPT'})")
    if not coh["coherent"]:
        print("  !! corrupt corpus, refusing to grade")
        return
    attach_h2h(bets)

    stats = ["pts", "reb", "ast", "fg3m"]
    print("\n  --- ORTHOGONALITY pre-screen: corr(signal, actual-pred) ---")
    ortho = {}
    for st in stats:
        for key in ("h2h_ratio", "h2h_delta"):
            c, n = residual_corr(bets, st, key)
            ortho[(st, key)] = (c, n)
            cs = f"{c:+.3f}" if c is not None else "  n/a"
            flag = ""
            if c is not None and abs(c) >= 0.05:
                flag = "  <-- passes |corr|>=0.05"
            print(f"    {st:4s} {key:10s} corr={cs}  n={n:5d}{flag}")

    print("\n  --- FEAST/LOCKDOWN buckets (raw model ROI by H2H bucket, full sample) ---")
    for st in stats:
        bk = grade_buckets(bets, st)
        line = "  ".join(f"{k}: n={v[0]:4d} roi={v[1]['roi_pct']:+6.2f}%" for k, v in bk.items())
        print(f"    {st:4s} | {line}")

    print("\n  --- ADDITIVE TILT (fit beta EARLY, grade LATE held-out) ---")
    tilt_results = {}
    for st in stats:
        for key in ("h2h_delta", "h2h_ratio"):
            r = grade_tilt(bets, st, key, key)
            if r is None:
                continue
            tilt_results[(st, key)] = r
            d = r["adj"]["roi_pct"] - r["raw"]["roi_pct"]
            print(f"    {st:4s} {key:10s} beta={r['beta']:+.3f} n_fit={r['n_fit']:4d} "
                  f"n_late={r['n_late']:4d} flips={r['flips']:3d} | "
                  f"raw={r['raw']['roi_pct']:+6.2f}% adj={r['adj']['roi_pct']:+6.2f}% "
                  f"LIFT={d:+6.2f}%")

    print("\n  --- FEAST/LOCKDOWN AGREEMENT selection (no point shift; select where model agrees) ---")
    for st in stats:
        ag = grade_agreement(bets, st)
        for half in ("EARLY", "LATE"):
            h = ag[half]
            print(f"    {st:4s} {half:5s} | all n={h['n_all']:4d} roi={h['all_roi']['roi_pct']:+6.2f}%"
                  f"  -> AGREE n={h['n_agree']:4d} roi={h['agree_roi']['roi_pct']:+6.2f}%")
    return bets, ortho, tilt_results


if __name__ == "__main__":
    corpora = sys.argv[1:] or [
        "benashkar_2026_canonical.csv",        # Family A
        "regular_season_2025_26_oddsapi.csv",  # Family B (independent, same season)
        "regular_season_2024_25_oddsapi.csv",  # Family C (independent, cross season)
    ]
    for c in corpora:
        run_corpus(c)
