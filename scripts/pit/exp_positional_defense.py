"""EXPERIMENT: per-stat / per-POSITION opponent positional-defense & scheme matchup.

HYPOTHESIS: the leak-free model has an AGGREGATE opp_def conditioner but maybe not
the GRANULAR positional/scheme matchup. A center vs elite rim protection scores
fewer paint points & maybe grabs fewer/more boards; a wing vs a switch-heavy /
perimeter-denial defense gets fewer 3s/assists; a team that concedes paint touches
inflates opposing C/PF REB & PTS. Prior memory: the WHOLE-atlas opp_def aggregate
was NEGATIVE for PTS, so we go PER-STAT and PER-POSITION, matching the SIGNAL to
the bettor's POSITION and STAT, to see if any stat (REB / FG3M maybe) survives.

METHOD (strict, mirrors PREDICTION_HARNESS_GUIDE §4a):
  1. resolve each bettor's POSITION bucket {G,F,C} (player_positional_defense +
     player_profile_features fallback).
  2. build a position-matched opponent matchup signal per stat from the atlases:
       - TRUE AS-OF (leak-free, date-keyed merge_asof): opp_paint_allowance.parquet
         (opp_paint_pct_allowed_z, opp_3pt_pct_allowed_z) + opp_defensive_intensity
         (opp_defensive_intensity_z, opp_avg_defender_distance_imposed_z, opp_pace_imposed_z).
       - SEASON-LEVEL team identity (quasi-leak, flagged): zone plus/minus from
         team_positional_defense_2025-26 (rim/paint/perim/mid _pct_plusminus) and
         scheme scores from defensive_schemes (paint_protection / perimeter_denial /
         pace_control). These are season aggregates (include the bet game) but are
         near-time-invariant TEAM DEFENSIVE IDENTITY; the early/late held-out beta-fit
         bounds the leak. Reported separately and never the sole basis for a SHIP.
  3. ORTHOGONALITY pre-screen per stat: corr(signal, actual-pred). |corr|>=0.05 to proceed.
  4. additive tilt pred_adj = pred + beta*signal_z, beta fit on EARLY half, graded LATE
     (held-out). ROI lift vs raw on >=2 INDEPENDENT corpora (A + (B or C)).
  5. drop |odds|<100 (grader does), coherence guard, reg-season only.

Run: conda run -n basketball_ai python scripts/pit/exp_positional_defense.py
"""
from __future__ import annotations

import os
import sys
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_grade as ig  # noqa: E402

ROOT = ig.ROOT
INTEL = os.path.join(ROOT, "data", "intelligence")

STATS = ["pts", "reb", "ast", "fg3m"]

# Corpora: Family A (big), Family B (same-season cross-book), Family C (cross-season)
CORP_A = "extended_oos_canonical.csv"
CORP_B = "regular_season_2025_26_oddsapi.csv"
CORP_C = "regular_season_2024_25_oddsapi.csv"


# --------------------------------------------------------------------------- #
#  POSITION RESOLUTION  pid -> {G,F,C}
# --------------------------------------------------------------------------- #
def _coarse_pos(raw: str) -> str:
    """Map a fine position string to G/F/C using the FIRST/primary token."""
    if not raw or not isinstance(raw, str):
        return ""
    r = raw.strip().upper()
    # player_positional_defense codes: G, F, C, G-F, F-C, C-F, F-G
    # player_profile_features codes: Guard, Forward, Center, Center-Forward, ...
    primary = r.split("-")[0]
    if primary.startswith("G"):
        return "G"
    if primary.startswith("C"):
        return "C"
    if primary.startswith("F"):
        return "F"
    return ""


def load_positions() -> dict:
    """pid -> {G,F,C}. Primary: player_positional_defense; fallback: profile_features."""
    pos: dict = {}
    p1 = os.path.join(ROOT, "data", "player_positional_defense_2025-26.parquet")
    if os.path.exists(p1):
        df = pd.read_parquet(p1)
        for r in df.itertuples(index=False):
            cp = _coarse_pos(getattr(r, "player_position", ""))
            if cp:
                pos[int(r.player_id)] = cp
    p2 = os.path.join(ROOT, "data", "cache", "player_profile_features.parquet")
    if os.path.exists(p2):
        df = pd.read_parquet(p2)
        for r in df.itertuples(index=False):
            pid = int(getattr(r, "player_id"))
            if pid in pos:
                continue
            cp = _coarse_pos(getattr(r, "position", ""))
            if cp:
                pos[pid] = cp
    return pos


# --------------------------------------------------------------------------- #
#  AS-OF DATE-KEYED SCHEME SIGNALS (leak-free)  opp_paint_allowance + intensity
# --------------------------------------------------------------------------- #
def _asof_table(path: str, cols: list) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["d"] = pd.to_datetime(df["game_date"]).dt.normalize()
    keep = ["team_id", "d"] + [c for c in cols if c in df.columns]
    df = df[keep].sort_values("d")
    return df


def attach_asof_scheme(bets: list) -> None:
    """Merge as-of (latest snapshot <= bet date) opp_paint_allowance + intensity
    keyed on opponent team. Adds leak-free z-score scheme fields to each bet."""
    paint = _asof_table(
        os.path.join(INTEL, "opp_paint_allowance.parquet"),
        ["opp_paint_pct_allowed_z", "opp_3pt_pct_allowed_z", "opp_mid_pct_allowed_z"],
    )
    inten = _asof_table(
        os.path.join(INTEL, "opp_defensive_intensity.parquet"),
        ["opp_defensive_intensity_z", "opp_avg_defender_distance_imposed_z",
         "opp_pace_imposed_z", "opp_contested_shot_rate_imposed_z"],
    )
    # team_id here is an abbreviation (object). build per-team sorted arrays.
    def _per_team(df):
        out = {}
        for tm, sub in df.groupby("team_id"):
            sub = sub.sort_values("d")
            out[tm] = (sub["d"].values, sub.drop(columns=["team_id", "d"]))
        return out
    pt = _per_team(paint)
    it = _per_team(inten)

    def _lookup(store, tm, gd):
        if tm not in store:
            return None
        dates, frame = store[tm]
        gd64 = np.datetime64(pd.Timestamp(gd).to_datetime64())
        idx = np.searchsorted(dates, gd64, side="right") - 1  # latest <= gd
        if idx < 0:
            return None
        return frame.iloc[idx].to_dict()

    for b in bets:
        opp = b["opp"]
        gd = b["gdate"]
        for store in (pt, it):
            m = _lookup(store, opp, gd)
            if m:
                for k, v in m.items():
                    b[k] = float(v) if v is not None and np.isfinite(v) else np.nan


# --------------------------------------------------------------------------- #
#  SEASON-LEVEL TEAM IDENTITY (quasi-leak, flagged)  zone +/- & scheme scores
# --------------------------------------------------------------------------- #
def load_team_identity() -> dict:
    """abbr -> dict of season-level zone plus/minus and scheme scores.
    QUASI-LEAK: season aggregates include the bet game, but they encode near-
    time-invariant TEAM DEFENSIVE IDENTITY. Used as orthogonality + tilt only;
    never the sole basis for a SHIP verdict."""
    out: dict = {}
    tpd = pd.read_parquet(os.path.join(ROOT, "data", "team_positional_defense_2025-26.parquet"))
    for r in tpd.itertuples(index=False):
        ab = getattr(r, "team_abbreviation")
        out.setdefault(ab, {}).update({
            "rim_pm": getattr(r, "rim_lt6_pct_plusminus"),
            "paint_pm": getattr(r, "paint_lt10_pct_plusminus"),
            "perim3_pm": getattr(r, "perim_3pt_pct_plusminus"),
            "mid_pm": getattr(r, "mid_gt15_pct_plusminus"),
        })
    ds = pd.read_parquet(os.path.join(INTEL, "defensive_schemes.parquet"))
    for r in ds.itertuples(index=False):
        ab = getattr(r, "team")
        out.setdefault(ab, {}).update({
            "paint_prot": getattr(r, "paint_protection_score"),
            "perim_denial": getattr(r, "perimeter_denial_score"),
            "pace_control": getattr(r, "pace_control_score"),
            "iso_force": getattr(r, "iso_force_score"),
            "closeout": getattr(r, "closeout_score"),
        })
    return out


def attach_team_identity(bets: list, ident: dict) -> None:
    for b in bets:
        d = ident.get(b["opp"])
        if d:
            for k, v in d.items():
                b["ti_" + k] = float(v) if v is not None and np.isfinite(v) else np.nan


# --------------------------------------------------------------------------- #
#  POSITION-MATCHED COMPOSITE SIGNAL per (stat, position)
# --------------------------------------------------------------------------- #
def _z(arr):
    a = np.asarray(arr, float)
    m = np.isfinite(a)
    if m.sum() < 5 or np.std(a[m]) < 1e-9:
        return np.full_like(a, np.nan)
    out = np.full_like(a, np.nan)
    out[m] = (a[m] - np.mean(a[m])) / np.std(a[m])
    return out


def build_position_matched_signals(bets: list) -> None:
    """For each bet, build position-matched matchup signals oriented so that a
    POSITIVE value => the matchup favors MORE of the stat (soft defense for that
    position+stat). Two families: '_asof_' (leak-free) and '_ident_' (season id).

    Orientation convention: higher z of 'allowed' / lower 'protection' => softer.
    We DO NOT flip sign by stat here; we let beta absorb sign and report it.
    """
    pos = load_positions()
    for b in bets:
        b["pos"] = pos.get(b["pid"], "")

    # Convenience getters
    def g(b, k):
        v = b.get(k, np.nan)
        return v if (v is not None and np.isfinite(v)) else np.nan

    # ---- AS-OF (leak-free) position-matched composites ----
    # PTS: C/F -> paint allowance (soft paint => more pts); G -> 3pt allowance
    # REB: C/F -> paint allowance + (inverse) defensive intensity (soft inside => boards)
    # FG3M: G/F -> 3pt allowance (soft perimeter => more 3s)
    # AST: G -> defensive intensity / defender distance (tight perimeter disrupts -> fewer ast)
    for b in bets:
        p = b["pos"]
        paint = g(b, "opp_paint_pct_allowed_z")
        three = g(b, "opp_3pt_pct_allowed_z")
        inten = g(b, "opp_defensive_intensity_z")
        ddist = g(b, "opp_avg_defender_distance_imposed_z")
        # PTS position-matched as-of
        if b["stat"] == "pts":
            b["_asof_match"] = paint if p in ("C", "F") else three
        elif b["stat"] == "reb":
            # soft paint => more shots miss inside => more boards; low intensity also
            b["_asof_match"] = paint if p in ("C", "F") else paint
        elif b["stat"] == "fg3m":
            b["_asof_match"] = three
        elif b["stat"] == "ast":
            # tighter perimeter (high intensity / large defender distance imposed) disrupts;
            # orient so positive => softer (more ast) => negative of intensity
            vals = [x for x in (inten, ddist) if np.isfinite(x)]
            b["_asof_match"] = -np.mean(vals) if vals else np.nan
        else:
            b["_asof_match"] = np.nan

    # ---- SEASON IDENTITY (quasi-leak) position-matched composites ----
    for b in bets:
        p = b["pos"]
        rim = g(b, "ti_rim_pm")
        paint = g(b, "ti_paint_pm")
        perim3 = g(b, "ti_perim3_pm")
        paint_prot = g(b, "ti_paint_prot")
        perim_den = g(b, "ti_perim_denial")
        if b["stat"] == "pts":
            # C/F -> rim+paint plus/minus (positive pm => allows MORE than expected => softer)
            if p in ("C", "F"):
                vals = [x for x in (rim, paint) if np.isfinite(x)]
                b["_ident_match"] = np.mean(vals) if vals else np.nan
            else:
                b["_ident_match"] = perim3
        elif b["stat"] == "reb":
            # soft rim/paint (positive pm) AND weak paint protection => more boards
            vals = []
            if np.isfinite(paint):
                vals.append(paint)
            if np.isfinite(paint_prot):
                vals.append(-paint_prot)  # low protection => soft
            b["_ident_match"] = np.mean(vals) if vals else np.nan
        elif b["stat"] == "fg3m":
            # soft perimeter (positive perim3 pm) / weak perimeter denial => more 3s
            vals = []
            if np.isfinite(perim3):
                vals.append(perim3)
            if np.isfinite(perim_den):
                vals.append(-perim_den)
            b["_ident_match"] = np.mean(vals) if vals else np.nan
        elif b["stat"] == "ast":
            # weak perimeter denial => easier passing lanes => more ast
            b["_ident_match"] = -perim_den if np.isfinite(perim_den) else np.nan
        else:
            b["_ident_match"] = np.nan

    # z-score each composite WITHIN stat (so beta scale is comparable, sign preserved)
    for fam in ("_asof_match", "_ident_match"):
        for stat in STATS:
            sub = [b for b in bets if b["stat"] == stat]
            zz = _z([b.get(fam, np.nan) for b in sub])
            for b, z in zip(sub, zz):
                b[fam + "_z"] = z


# --------------------------------------------------------------------------- #
#  CORE: orthogonality + held-out additive tilt
# --------------------------------------------------------------------------- #
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


def split_halves(bets):
    ds = sorted(set(b["gdate"] for b in bets))
    if len(ds) < 4:
        return bets, []
    mid = ds[len(ds) // 2]
    return [b for b in bets if b["gdate"] < mid], [b for b in bets if b["gdate"] >= mid]


def fit_beta(rows, stat, key):
    sub = [b for b in rows if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 40:
        return None, len(sub)
    sig = np.array([b[key] for b in sub])
    resid = np.array([b["actual"] - b["pred"] for b in sub])
    if np.std(sig) < 1e-9:
        return None, len(sub)
    return float(np.cov(sig, resid)[0, 1] / np.var(sig)), len(sub)


def grade_tilt(rows, stat, key, beta):
    sub = [b for b in rows if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan))]
    flips = 0
    for b in sub:
        b["_padj"] = b["pred"] + beta * b[key]
        if (b["pred"] > b["line"]) != (b["_padj"] > b["line"]):
            flips += 1
    raw = ig.roi(sub, predictor="pred")
    adj = ig.roi(sub, predictor="_padj")
    return raw, adj, flips, len(sub)


def prep(corpus):
    bets = ig.prepare(corpus)
    ident = load_team_identity()
    attach_asof_scheme(bets)
    attach_team_identity(bets, ident)
    build_position_matched_signals(bets)
    return bets


def coverage_report(bets):
    npos = sum(1 for b in bets if b.get("pos"))
    nasof = sum(1 for b in bets if np.isfinite(b.get("_asof_match", np.nan)))
    nident = sum(1 for b in bets if np.isfinite(b.get("_ident_match", np.nan)))
    print(f"  coverage: position {npos}/{len(bets)} | asof-signal {nasof} | ident-signal {nident}")


def run_orthogonality(corpus):
    print(f"\n{'='*74}\n ORTHOGONALITY  {corpus}\n{'='*74}")
    bets = prep(corpus)
    coh = ig.coherence(bets)
    print(f"  coherence sum {coh['sum']:+.2f}% ({'OK' if coh['coherent'] else 'CORRUPT'}) | n={len(bets)}")
    coverage_report(bets)
    if not coh["coherent"]:
        print("  !! corrupt corpus, skip")
        return None
    print("  corr(signal, actual-pred) per stat   [|r|>=0.05 = non-trivial]:")
    print(f"   {'stat':5s} {'asof_match_z':>14s} {'ident_match_z':>14s}")
    for stat in STATS:
        ra, na = residual_corr(bets, stat, "_asof_match_z")
        ri, ni = residual_corr(bets, stat, "_ident_match_z")
        fa = "*" if (ra is not None and abs(ra) >= 0.05) else " "
        fi = "*" if (ri is not None and abs(ri) >= 0.05) else " "
        sa = f"{ra:+.3f}{fa}(n{na})" if ra is not None else f"  n/a(n{na})"
        si = f"{ri:+.3f}{fi}(n{ni})" if ri is not None else f"  n/a(n{ni})"
        print(f"   {stat:5s} {sa:>14s} {si:>14s}")
    return bets


def run_heldout_tilt(corpus, family_label):
    print(f"\n{'-'*74}\n HELD-OUT TILT  {corpus}  ({family_label})\n{'-'*74}")
    bets = prep(corpus)
    if not ig.coherence(bets)["coherent"]:
        print("  corrupt, skip"); return
    early, late = split_halves(bets)
    if not late:
        print("  too few dates for halves, skip"); return
    for fam in ("_asof_match_z", "_ident_match_z"):
        tag = "ASOF(leak-free)" if "asof" in fam else "IDENT(season,quasi-leak)"
        print(f"\n  signal={fam}  [{tag}]")
        for stat in STATS:
            beta, nfit = fit_beta(early, stat, fam)
            if beta is None:
                print(f"    {stat:5s}  (insufficient fit n={nfit})")
                continue
            raw, adj, flips, n = grade_tilt(late, stat, fam, beta)
            d = adj["roi_pct"] - raw["roi_pct"]
            verdict = "LIFT" if d > 0 else "drop"
            print(f"    {stat:5s} beta={beta:+.4f} | late raw {raw['roi_pct']:+6.2f}%"
                  f" -> adj {adj['roi_pct']:+6.2f}% (n{n}, flips={flips})  d={d:+.2f}pp [{verdict}]")


def run_crosscorpus_tilt(stat, fam):
    """Fit beta on full Family A, grade on Family B and C (independent)."""
    print(f"\n  >> CROSS-CORPUS confirm: stat={stat} signal={fam}")
    a = prep(CORP_A)
    beta, nfit = fit_beta(a, stat, fam)
    if beta is None:
        print(f"     cannot fit on A (n={nfit})"); return
    print(f"     fit beta={beta:+.4f} on A (n={nfit})")
    for corp, lbl in [(CORP_A, "A(in-sample)"), (CORP_B, "B(odds-api 25-26)"),
                      (CORP_C, "C(odds-api 24-25)")]:
        bets = prep(corp)
        if not ig.coherence(bets)["coherent"]:
            print(f"     {lbl}: corrupt, skip"); continue
        raw, adj, flips, n = grade_tilt(bets, stat, fam, beta)
        d = adj["roi_pct"] - raw["roi_pct"]
        print(f"     {lbl:18s} raw {raw['roi_pct']:+6.2f}% -> adj {adj['roi_pct']:+6.2f}%"
              f" (n{n}, flips={flips})  d={d:+.2f}pp")


if __name__ == "__main__":
    print("#" * 74)
    print("# EXP: per-stat / per-position opponent positional-defense & scheme matchup")
    print("#" * 74)

    # 1. orthogonality on all three independent families
    for c in (CORP_A, CORP_B, CORP_C):
        run_orthogonality(c)

    # 2. held-out (early->late) additive tilt per family
    run_heldout_tilt(CORP_A, "Family A big sample")
    run_heldout_tilt(CORP_C, "Family C cross-season")

    # 3. cross-corpus confirm for each stat x signal-family (fit A -> grade B & C)
    print(f"\n{'#'*74}\n# CROSS-CORPUS (fit Family A -> grade B & C, independent)\n{'#'*74}")
    for stat in STATS:
        for fam in ("_asof_match_z", "_ident_match_z"):
            run_crosscorpus_tilt(stat, fam)
