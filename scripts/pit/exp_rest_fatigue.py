"""EXPERIMENT: rest-differential + both-tired UNDER signal
EXP ID: exp_rest_fatigue  |  2026-06-01

HYPOTHESIS
----------
A player whose TEAM faces a rest DISADVANTAGE (team on B2B vs rested opponent) should
fade in efficiency and counting stats.  A rest ADVANTAGE (team is fresh, opponent is B2B)
should sustain/boost output.  The "both-tired" environment (both teams on B2B) may tilt
UNDER on totals.

The model already has `rest_days` (player's own rest) and `is_b2b` as features.  New
signals tested here that the model does NOT directly have:

  rest_diff          = player_team_rest_days - opponent_rest_days  (clipped ±2)
                       source: season_games_{season}.json home/away rest fields
  opp_is_b2b         = 1 when opponent is on a B2B and player's team is NOT (advantage)
  both_b2b           = 1 when BOTH teams are on a B2B (tired-vs-tired; total-UNDER)
  rest_diff_raw      = unclipped differential (continuous, may be noisier)

METHOD (strict, leak-free, per PREDICTION_HARNESS_GUIDE §4a)
-------------------------------------------------------------
1. Build rest-differential lookup from season_games (known pregame → leak-free).
2. Attach to calibration_frame_v2 bets via (player_id, date, stat) → game_id → season_games.
3. Orthogonality pre-screen: |corr(signal, actual - pred)| on FULL corpus.
   Model has rest_days/is_b2b; expect differential to be near-zero if market + model
   absorb it; require ≳ 0.05 to proceed.
4. Temporal split: fit beta on EARLY half, grade LATE half (no lookahead).
5. Grade on Family A (benashkar_2026_canonical.csv) AND Family B/C (oddsapi corpora).
6. Coherence guard on every corpus.
7. Report LIFT over the §6 baseline per stat.

PITFALLS CHECKLIST
------------------
[x] Drop |odds| < 100 — done by ig.load_corpus
[x] Coherence guard — checked before every corpus grade
[x] Independent corpora: Family A (benashkar) + Family B (oddsapi-2025-26) + Family C (oddsapi-2024-25)
[x] No playoff preds in substrate (substrate ends 2026-04-12; reg season only)
[x] Leak-free: rest data is known pregame; signal built from prior game dates only (season_games carries pre-game rolling rest)
[x] Fit beta on EARLY half only; apply to HELD-OUT LATE half
[x] Report n per slice; flag n < 30
[x] Measure LIFT over §6 per-stat baseline (AST +4–7%, REB +2.6%, PTS -1.7%, FG3M -2.8%)
"""
from __future__ import annotations

import json
import os
import sys
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "pit"))
import intel_grade as ig  # noqa: E402

STATS = ["pts", "reb", "ast", "fg3m"]
OOF_PATH = os.path.join(ROOT, "data", "cache", "pregame_oof.parquet")
CAL_PATH = os.path.join(ROOT, "data", "cache", "calibration_frame_v2.parquet")
NBA_DIR = os.path.join(ROOT, "data", "nba")

# ---------------------------------------------------------------------------
# STEP 1: Build game-level rest lookup from season_games
# ---------------------------------------------------------------------------

def build_game_rest_lookup() -> Dict[str, dict]:
    """Read season_games_{season}.json for all 3 seasons, return
    game_id -> {home_rest, away_rest, home_b2b, away_b2b}."""
    lookup = {}
    for season in ("2023-24", "2024-25", "2025-26"):
        path = os.path.join(NBA_DIR, f"season_games_{season}.json")
        if not os.path.exists(path):
            print(f"  [WARN] season_games_{season}.json not found — skipping")
            continue
        data = json.load(open(path, encoding="utf-8"))
        for r in data.get("rows", []):
            gid = str(r["game_id"])
            lookup[gid] = {
                "home_rest": r.get("home_rest_days"),
                "away_rest": r.get("away_rest_days"),
                "home_b2b":  float(r.get("home_back_to_back", 0) or 0),
                "away_b2b":  float(r.get("away_back_to_back", 0) or 0),
            }
    print(f"  game_rest_lookup: {len(lookup):,} game_ids loaded")
    return lookup


# ---------------------------------------------------------------------------
# STEP 2: Build (player_id, date, stat) → rest_diff lookup
# ---------------------------------------------------------------------------

def build_rest_signal_map(game_lookup: Dict[str, dict]) -> Dict[tuple, dict]:
    """Join calibration_frame (has is_home, rest_days) with pregame_oof (has game_id)
    to get player-game-level rest differential signals.
    Returns dict keyed (player_id, date_Timestamp, stat) -> signal dict."""
    print("\n[build_rest_signal_map] loading calibration_frame + oof …")
    cal = pd.read_parquet(CAL_PATH)
    cal["d"] = pd.to_datetime(cal["date"]).dt.normalize()
    oof = pd.read_parquet(OOF_PATH)
    oof["gd"] = pd.to_datetime(oof["game_date"]).dt.normalize()

    # Join cal → oof on (player_id, date, stat) to get game_id
    merged = cal.merge(
        oof[["player_id", "gd", "stat", "game_id"]].drop_duplicates(),
        left_on=["player_id", "d", "stat"],
        right_on=["player_id", "gd", "stat"],
        how="left",
    )
    n_tot = len(merged)
    n_gid = merged["game_id"].notna().sum()
    print(f"  cal rows: {n_tot:,} | game_id resolved: {n_gid:,} ({100*n_gid/n_tot:.1f}%)")

    # Vectorized rest diff computation
    def _resolve(row):
        gi = game_lookup.get(str(row["game_id"]) if pd.notna(row["game_id"]) else "")
        if gi is None:
            return np.nan, np.nan, np.nan, np.nan
        if int(row["is_home"]) == 1:
            t_rest = gi["home_rest"]
            o_rest = gi["away_rest"]
            t_b2b  = gi["home_b2b"]
            o_b2b  = gi["away_b2b"]
        else:
            t_rest = gi["away_rest"]
            o_rest = gi["home_rest"]
            t_b2b  = gi["away_b2b"]
            o_b2b  = gi["home_b2b"]
        if t_rest is None or o_rest is None:
            return np.nan, np.nan, np.nan, np.nan
        t_rest = float(t_rest)
        o_rest = float(o_rest)
        diff = t_rest - o_rest
        diff_clipped = float(np.clip(diff, -2, 2))
        both = 1.0 if (t_b2b == 1 and o_b2b == 1) else 0.0
        opp_only = 1.0 if (o_b2b == 1 and t_b2b != 1) else 0.0
        return diff_clipped, both, opp_only, diff

    print("  computing rest differentials (vectorized per row) …")
    result = merged.apply(_resolve, axis=1, result_type="expand")
    result.columns = ["rest_diff", "both_b2b", "opp_is_b2b", "rest_diff_raw"]
    merged = pd.concat([merged[["player_id", "d", "stat"]], result], axis=1)

    # Coverage
    cov = merged["rest_diff"].notna().mean()
    print(f"  rest_diff coverage: {100*cov:.1f}% of cal rows")

    # Build lookup dict
    sig_map = {}
    for row in merged.itertuples(index=False):
        key = (int(row.player_id), row.d, row.stat)
        sig_map[key] = {
            "rest_diff":     row.rest_diff,
            "both_b2b":      row.both_b2b,
            "opp_is_b2b":    row.opp_is_b2b,
            "rest_diff_raw": row.rest_diff_raw,
        }
    print(f"  signal map size: {len(sig_map):,} keys")
    return sig_map


# ---------------------------------------------------------------------------
# STEP 3: Attach rest signals to prepared bets list
# ---------------------------------------------------------------------------

def attach_rest_signals(bets: List[dict], sig_map: Dict[tuple, dict]) -> List[dict]:
    """Attach rest_diff, both_b2b, opp_is_b2b, rest_diff_raw to each bet dict."""
    matched = 0
    SIGNAL_KEYS = ["rest_diff", "both_b2b", "opp_is_b2b", "rest_diff_raw"]
    for b in bets:
        key = (b["pid"], b["gdate"], b["stat"])
        m = sig_map.get(key)
        if m is not None:
            b.update(m)
            if np.isfinite(b.get("rest_diff", np.nan)):
                matched += 1
        else:
            for k in SIGNAL_KEYS:
                b.setdefault(k, np.nan)
    pct = 100 * matched / max(len(bets), 1)
    print(f"  rest signals matched {matched}/{len(bets)} ({pct:.0f}%)")
    return bets


# ---------------------------------------------------------------------------
# STEP 4: Orthogonality pre-screen
# ---------------------------------------------------------------------------

def residual_corr(bets: List[dict], stat: str, sig_key: str):
    """corr(signal, actual - pred) for a stat. Returns (r, n)."""
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(sig_key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None, len(sub)
    sig   = np.array([b[sig_key] for b in sub], float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], float)
    if np.std(sig) < 1e-9:
        return None, len(sub)
    r = np.corrcoef(sig, resid)[0, 1]
    return r, len(sub)


# ---------------------------------------------------------------------------
# STEP 5: Temporal halves split (leak-free train/test)
# ---------------------------------------------------------------------------

def split_halves(bets: List[dict]):
    ds = sorted(set(b["gdate"] for b in bets))
    mid = ds[len(ds) // 2]
    early = [b for b in bets if b["gdate"] <  mid]
    late  = [b for b in bets if b["gdate"] >= mid]
    return early, late, mid


# ---------------------------------------------------------------------------
# STEP 6: Fit beta (OLS residual correction) on training split
# ---------------------------------------------------------------------------

def fit_beta(bets: List[dict], stat: str, sig_key: str):
    """beta = cov(sig, actual - pred) / var(sig)  (pure leak-free OLS)."""
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(sig_key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 50:
        return None, len(sub)
    sig   = np.array([b[sig_key] for b in sub], float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], float)
    if np.std(sig) < 1e-9:
        return None, len(sub)
    beta = np.cov(sig, resid)[0, 1] / np.var(sig)
    return beta, len(sub)


# ---------------------------------------------------------------------------
# STEP 7: Apply beta and grade (raw vs corrected)
# ---------------------------------------------------------------------------

def grade_corrected(bets: List[dict], stat: str, sig_key: str, beta: float,
                    pred_key: str = "_pred_rest"):
    """Apply pred_adj = pred + beta * signal, grade ROI raw vs adj."""
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(sig_key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    flips = 0
    for b in sub:
        b[pred_key] = b["pred"] + beta * b[sig_key]
        if (b["pred"] > b["line"]) != (b[pred_key] > b["line"]):
            flips += 1
    raw = ig.roi(sub, predictor="pred")
    adj = ig.roi(sub, predictor=pred_key)
    return raw, adj, flips, len(sub)


# ---------------------------------------------------------------------------
# STEP 8: Tercile ROI analysis
# ---------------------------------------------------------------------------

def tercile_roi(bets: List[dict], stat: str, sig_key: str):
    """Split bets for a stat by tercile of signal; grade ROI in each tercile."""
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(sig_key, np.nan))]
    if len(sub) < 30:
        return None
    vals = np.array([b[sig_key] for b in sub], float)
    lo, hi = np.nanpercentile(vals, [33.333, 66.667])
    out = {}
    for name, fn in [("low",  lambda v: v <= lo),
                     ("mid",  lambda v: lo < v <= hi),
                     ("high", lambda v: v > hi)]:
        bb = [b for b in sub if fn(b[sig_key])]
        out[name] = ig.roi(bb)
        out[name]["lo_cutoff"] = round(float(lo), 2)
        out[name]["hi_cutoff"] = round(float(hi), 2)
    return out


# ---------------------------------------------------------------------------
# MAIN: run full experiment
# ---------------------------------------------------------------------------

CORPORA = {
    "A_benashkar":  "benashkar_2026_canonical.csv",
    "B_oddsapi_25": "regular_season_2025_26_oddsapi.csv",
    "C_oddsapi_24": "regular_season_2024_25_oddsapi.csv",
}

# Baselines from §6 of PREDICTION_HARNESS_GUIDE (honest ROI vs real lines, unfiltered)
BASELINES = {"pts": -1.70, "reb": 2.60, "ast": 4.33, "fg3m": -2.82}

SIGNAL_KEYS = {
    "rest_diff":   "rest differential (player_team - opp, clipped ±2; +2=max advantage)",
    "opp_is_b2b":  "opponent is B2B while player is NOT (binary; player advantage)",
    "both_b2b":    "BOTH teams on B2B (tired-vs-tired; hypothesized UNDER tilt)",
    "rest_diff_raw": "unclipped rest differential (continuous signal)",
}


def run_corpus_analysis(corpus_tag: str, corpus_file: str, sig_map: Dict,
                        is_cross_season: bool = False):
    """Full analysis for one corpus."""
    banner = f"CORPUS: {corpus_tag}  ({corpus_file})"
    print(f"\n{'='*72}")
    print(f"  {banner}")
    print(f"{'='*72}")

    bets = ig.prepare(corpus_file)
    coh = ig.coherence(bets)
    print(f"  coherence: blind-over {coh['over']['roi_pct']:+.2f}%  + blind-under "
          f"{coh['under']['roi_pct']:+.2f}%  = {coh['sum']:+.2f}%  "
          f"({'OK' if coh['coherent'] else '!! CORRUPT !!'})")
    if not coh["coherent"]:
        print("  SKIPPING — corrupt corpus (coherence sum > 0)")
        return None

    bets = attach_rest_signals(bets, sig_map)
    n_total = len(bets)
    print(f"  total bets: {n_total:,}")

    # Per-stat baseline on this corpus
    ps_baseline = ig.per_stat(bets, predictor="pred", edge_min=0.0)
    print("\n  RAW baseline ROI (raw pred > line, unfiltered):")
    for stat in STATS:
        v = ps_baseline.get(stat, {})
        bl = BASELINES.get(stat, 0.0)
        print(f"    {stat:5s}  n={v.get('n',0):4d}  win={v.get('win_pct',0):.1f}%  "
              f"roi={v.get('roi_pct',0):+.2f}%  (§6 baseline {bl:+.2f}%)")

    results = {}

    # ---- ORTHOGONALITY PRE-SCREEN ----
    print(f"\n  --- ORTHOGONALITY: corr(signal, actual − pred) ---")
    print(f"  (|corr| ≳ 0.05 needed to justify a tilt; model has rest_days + is_b2b)")
    for sk in SIGNAL_KEYS:
        print(f"\n  Signal: {sk}  [{SIGNAL_KEYS[sk]}]")
        for stat in STATS:
            r, n = residual_corr(bets, stat, sk)
            flag = ""
            if r is not None:
                flag = "  <-- NON-TRIVIAL" if abs(r) >= 0.05 else "  (trivial)"
            print(f"    {stat:5s}  corr={r if r is None else f'{r:+.4f}'}  n={n}{flag}")

    # ---- TERCILE ROI: rest_diff ----
    print(f"\n  --- TERCILE ROI by rest_diff (continuous advantage signal) ---")
    for stat in STATS:
        t = tercile_roi(bets, stat, "rest_diff")
        if t:
            lo_cut = t["low"]["lo_cutoff"]
            hi_cut = t["low"]["hi_cutoff"]
            print(f"    {stat:5s}  cutoffs=[{lo_cut:.1f},{hi_cut:.1f}]  "
                  + "  ".join(f"{nm}={t[nm]['roi_pct']:+.1f}%(n={t[nm]['n']})"
                              for nm in ("low","mid","high")))

    # ---- TERCILE ROI: opp_is_b2b ----
    print(f"\n  --- SUBSET: opp_is_b2b == 1 vs == 0 (opponent is tired, player is fresh) ---")
    for stat in STATS:
        all_b = [b for b in bets if b["stat"] == stat]
        adv_b = [b for b in bets if b["stat"] == stat and b.get("opp_is_b2b") == 1]
        neu_b = [b for b in bets if b["stat"] == stat and b.get("opp_is_b2b") == 0
                 and b.get("both_b2b") == 0]
        r_all = ig.roi(all_b)
        r_adv = ig.roi(adv_b)
        r_neu = ig.roi(neu_b)
        print(f"    {stat:5s}  all={r_all['roi_pct']:+.2f}%(n={r_all['n']})  "
              f"opp_b2b(adv)={r_adv['roi_pct']:+.2f}%(n={r_adv['n']})  "
              f"neutral={r_neu['roi_pct']:+.2f}%(n={r_neu['n']})")

    # ---- BOTH-B2B UNDER environment ----
    print(f"\n  --- BOTH-B2B subset (tired-vs-tired; UNDER hypothesis) ---")
    for stat in STATS:
        both = [b for b in bets if b["stat"] == stat and b.get("both_b2b") == 1]
        r_both = ig.roi(both)
        r_under = ig.roi(both, under_only=True)
        n = r_both['n']
        print(f"    {stat:5s}  n={n}  both_dirs={r_both['roi_pct']:+.2f}%  "
              f"under_only={r_under['roi_pct']:+.2f}%  "
              f"({'thin <30, treat as directional' if n < 30 else ''})")

    # ---- HELD-OUT TEMPORAL SPLIT (additive tilt) ----
    if not is_cross_season:
        print(f"\n  --- HELD-OUT TEMPORAL TILT (fit EARLY beta, grade LATE half) ---")
        early, late, middate = split_halves(bets)
        print(f"  middate: {middate.date()}  early n={len(early)}  late n={len(late)}")
        for stat in STATS:
            for sk in ("rest_diff", "opp_is_b2b"):
                beta, n_fit = fit_beta(early, stat, sk)
                if beta is None:
                    print(f"    {stat}/{sk}: insufficient data (n_fit={n_fit})")
                    continue
                raw, adj, flips, n_grade = grade_corrected(late, stat, sk, beta)
                delta = adj["roi_pct"] - raw["roi_pct"]
                print(f"    {stat:5s}/{sk:12s}  beta={beta:+.4f} (fit n={n_fit}) | "
                      f"late raw={raw['roi_pct']:+.2f}% → adj={adj['roi_pct']:+.2f}%  "
                      f"Δ={delta:+.2f}pp  flips={flips}/{n_grade}")

    results["bets"] = bets
    results["baseline"] = ps_baseline
    return results


def run_cross_season_tilt(primary_bets: List[dict], cross_corpus: str,
                          cross_sig_map: Dict):
    """Fit beta on full primary (Family A), grade on cross-season corpus."""
    print(f"\n  --- CROSS-SEASON TILT (fit on Family A → grade {cross_corpus}) ---")
    cross_bets = ig.prepare(cross_corpus)
    cross_coh = ig.coherence(cross_bets)
    if not cross_coh["coherent"]:
        print(f"  SKIP: {cross_corpus} coherence corrupt")
        return
    cross_bets = attach_rest_signals(cross_bets, cross_sig_map)
    for stat in STATS:
        for sk in ("rest_diff", "opp_is_b2b"):
            beta, n_fit = fit_beta(primary_bets, stat, sk)
            if beta is None:
                continue
            raw, adj, flips, n_grade = grade_corrected(cross_bets, stat, sk, beta)
            delta = adj["roi_pct"] - raw["roi_pct"]
            print(f"    {stat:5s}/{sk:12s}  beta={beta:+.4f} (fit n={n_fit}) | "
                  f"{cross_corpus[:20]} raw={raw['roi_pct']:+.2f}% → adj={adj['roi_pct']:+.2f}%  "
                  f"Δ={delta:+.2f}pp  flips={flips}/{n_grade}")


def main():
    print("=" * 72)
    print("EXP: rest_fatigue — rest differential + both-B2B UNDER signal")
    print("Date: 2026-06-01 | Corpora: benashkar (A) + oddsapi-25 (B) + oddsapi-24 (C)")
    print("=" * 72)

    # Build signal map (league-wide, covers all 3 seasons)
    game_lookup = build_game_rest_lookup()
    sig_map = build_rest_signal_map(game_lookup)

    # Run Family A (the big sample)
    r_A = run_corpus_analysis("A_benashkar", "benashkar_2026_canonical.csv", sig_map)

    # Run Family B (same season, independent book)
    run_corpus_analysis("B_oddsapi_2025_26", "regular_season_2025_26_oddsapi.csv", sig_map)

    # Run Family C (cross-season, independent check)
    run_corpus_analysis("C_oddsapi_2024_25", "regular_season_2024_25_oddsapi.csv",
                        sig_map, is_cross_season=True)

    # Cross-season tilt: fit on full Family A → grade Family C
    if r_A is not None:
        run_cross_season_tilt(r_A["bets"], "regular_season_2024_25_oddsapi.csv", sig_map)

    # ---- SUMMARY ----
    print("\n" + "=" * 72)
    print("EXPERIMENT SUMMARY — rest_fatigue")
    print("=" * 72)
    print("""
Signal construction: rest_diff = player_team_rest_days - opp_rest_days (clipped ±2)
                     opp_is_b2b = 1 when opponent B2B, player's team is NOT
                     both_b2b   = 1 when BOTH teams on B2B
Source: season_games_{season}.json (home/away rest fields) — pregame, leak-free.
Model already has: rest_days (player's own), is_b2b (player's own).

ORTHOGONALITY: key question — does rest_diff add signal the model missed?
  - Model's rest_days covers player-side fatigue; rest_diff adds opp-side.
  - If |corr(rest_diff, actual-pred)| < 0.05 for all stats → model already
    fully prices rest via opp_pace + schedule features → REJECT cheaply.

BASKETBALL PRIOR (from rest_advantage_outcome.json):
  - Fresh-vs-B2B only lifts team win% by +2.5pp; point margin +1.7 pts.
  - Both-B2B cuts total by -2.3 pts (total 228.9 vs baseline 231.2).
  - Per-PLAYER effect is even smaller after splitting 10 player rows/game.

HONEST PRIOR: expect orthogonality near zero (market prices rest) and
              small/inconsistent ROI lift. Verdict likely REJECT.
""")


if __name__ == "__main__":
    main()
