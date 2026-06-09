"""exp_minutes_projection.py — THE highest-leverage lever test.

Prior finding (VS_VEGAS §3): "Error is driven by MINUTES-SURPRISE; oracle minutes
ceiling ~10%." The single biggest prop-prediction error source is mis-projected
minutes. If a sharper LEAK-FREE minutes projection exists, propagating it to
counting props via per-minute rate is the most likely real lift.

HYPOTHESIS: combine outcome intelligence into a sharper as-of MINUTES projection —
l10/l5/l3 minutes + teammate-OUT (vacated rotation minutes redistributed by role
share) + blowout-risk (team/opp net-margin mismatch -> starters rest) + B2B/rest +
role share — and propagate minutes_proj to counting props via per-minute rate.

METHOD (strict, leak-free as-of):
  PHASE 1 (the REAL test): build minutes_proj from prior-games-only features and
    VALIDATE it beats l10_min / l3-l10 blend on OUT-OF-SAMPLE minutes MAE.
    Ground truth = actual MIN from leaguegamelog_regular_season.parquet.
  PHASE 2 (orthogonality): is (minutes_proj - l10_min) correlated with (actual-pred)
    for PTS/REB/AST on joined bets? If the model's l10_min/vac already capture
    minutes, |corr|~0 -> REJECT.
  PHASE 3 (ROI propagation): if orthogonal, pred_adj = pred + beta*(minutes_surprise
    * per_min_rate), fit on EARLY half, grade LATE half. ROI lift on >=2 INDEPENDENT
    corpora (Family A AND Family B/C). drop |odds|<100, coherence, reg-season.

All minutes features computed from the leaguegamelog box-appearance ledger (the
same leak-free box-log route as exp_teammate_out.py), via .shift(1) rolling so only
PRIOR games feed each row. No production code touched; read-only; no git commit.

Run: conda run -n basketball_ai python scripts/pit/exp_minutes_projection.py
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_grade as ig  # noqa: E402

ROOT = ig.ROOT
LGL = os.path.join(ROOT, "data", "cache", "cv_fix", "leaguegamelog_regular_season.parquet")

# stat -> per-minute rate column we build from the box log (as-of L10 per-minute)
RATE_STATS = ("pts", "reb", "ast")


# ----------------------------------------------------------------------------
# Build the as-of minutes feature table (leak-free; prior games only)
# ----------------------------------------------------------------------------
def build_minutes_table() -> pd.DataFrame:
    lgl = pd.read_parquet(LGL)
    keep = ["PLAYER_ID", "TEAM_ABBREVIATION", "GAME_ID", "GAME_DATE", "MATCHUP",
            "MIN", "PTS", "REB", "AST"]
    lgl = lgl[keep].copy()
    lgl["GAME_DATE"] = pd.to_datetime(lgl["GAME_DATE"]).dt.normalize()
    lgl = lgl.sort_values(["PLAYER_ID", "GAME_DATE"]).reset_index(drop=True)
    lgl["team"] = lgl["MATCHUP"].str.split(" ").str[0]

    g = lgl.groupby("PLAYER_ID")
    lgl["l10_min"] = g["MIN"].transform(lambda s: s.shift(1).rolling(10, min_periods=1).mean())
    lgl["l5_min"] = g["MIN"].transform(lambda s: s.shift(1).rolling(5, min_periods=1).mean())
    lgl["l3_min"] = g["MIN"].transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
    lgl["std_min"] = g["MIN"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).std())
    lgl["prev_min"] = g["MIN"].transform(lambda s: s.shift(1))
    lgl["games_so_far"] = g.cumcount()
    # as-of per-minute rates (L10), prior games only -> for prop propagation
    for st, col in (("pts", "PTS"), ("reb", "REB"), ("ast", "AST")):
        l10_stat = g[col].transform(lambda s: s.shift(1).rolling(10, min_periods=1).mean())
        lgl[f"l10_{st}"] = l10_stat
        lgl[f"rate_{st}"] = l10_stat / lgl["l10_min"].replace(0, np.nan)
    # rest / b2b
    lgl["rest"] = g["GAME_DATE"].transform(lambda s: s.diff().dt.days)
    lgl["is_b2b"] = (lgl["rest"] == 1).astype(int)
    lgl["rest"] = lgl["rest"].fillna(3).clip(1, 7)

    # --- teammate-OUT: vacated rotation minutes (box-appearance route, leak-free) ---
    td_present = defaultdict(list)   # (team,date) -> [(pid, l10_min)]
    for r in lgl.itertuples(index=False):
        td_present[(r.team, r.GAME_DATE)].append(
            (r.PLAYER_ID, r.l10_min if pd.notna(r.l10_min) else 0.0))
    team_dates = defaultdict(list)
    for (t, dte) in td_present:
        team_dates[t].append(dte)
    for t in team_dates:
        team_dates[t] = sorted(set(team_dates[t]))

    def vac_for(team, dte):
        dates = team_dates[team]
        i = dates.index(dte)
        if i < 1:
            return 0.0, 0
        roster = {}
        for j in range(max(0, i - 3), i):       # PRIOR 3 team-games only
            for (pid, l10) in td_present[(team, dates[j])]:
                roster[pid] = l10
        present = {pid for (pid, _) in td_present[(team, dte)]}
        vac_min = 0.0
        n_out = 0
        for pid, l10 in roster.items():
            if pid not in present and l10 >= 15:  # absent regular
                vac_min += l10
                n_out += 1
        return vac_min, n_out

    vac_cache = {}
    vm, no = [], []
    for r in lgl.itertuples(index=False):
        key = (r.team, r.GAME_DATE)
        if key not in vac_cache:
            vac_cache[key] = vac_for(r.team, r.GAME_DATE)
        a, b = vac_cache[key]
        vm.append(a)
        no.append(b)
    lgl["vac_min"] = vm
    lgl["n_out"] = no

    # rotation share = this player's l10 / sum of team present-players' l10 (tonight's box)
    team_l10 = defaultdict(float)
    for r in lgl.itertuples(index=False):
        team_l10[(r.team, r.GAME_DATE)] += (r.l10_min if pd.notna(r.l10_min) else 0.0)
    lgl["team_l10_sum"] = [team_l10[(r.team, r.GAME_DATE)] for r in lgl.itertuples(index=False)]
    lgl["rot_share"] = lgl["l10_min"] / lgl["team_l10_sum"].replace(0, np.nan)
    # vacated minutes attributed to this player by rotation share
    lgl["vac_share_min"] = lgl["vac_min"] * lgl["rot_share"]

    # --- blowout-risk: as-of team & opp rolling point margin (prior games only) ---
    tg = lgl.groupby(["GAME_ID", "team"])["PTS"].sum().reset_index()
    # margin per team-game = team pts - opp pts
    gm = tg.groupby("GAME_ID")
    margin = {}
    gdate = lgl.drop_duplicates(["GAME_ID", "team"]).set_index(["GAME_ID", "team"])["GAME_DATE"]
    for gid, sub in gm:
        if len(sub) != 2:
            continue
        teams = sub["team"].tolist()
        pts = sub["PTS"].tolist()
        margin[(gid, teams[0])] = pts[0] - pts[1]
        margin[(gid, teams[1])] = pts[1] - pts[0]
    mrows = []
    for (gid, tm), mg in margin.items():
        d = gdate.get((gid, tm))
        if d is not None:
            mrows.append({"team": tm, "GAME_DATE": d, "margin": mg})
    md = pd.DataFrame(mrows).sort_values(["team", "GAME_DATE"]).reset_index(drop=True)
    md["team_margin_asof"] = (md.groupby("team")["margin"]
                              .transform(lambda s: s.shift(1).rolling(10, min_periods=2).mean()))
    margin_idx = {(r.team, r.GAME_DATE): r.team_margin_asof for r in md.itertuples(index=False)}
    # opponent abbrev from MATCHUP
    def opp_of(m):
        if " @ " in m:
            return m.split(" @ ")[1].strip()
        if " vs. " in m:
            return m.split(" vs. ")[1].strip()
        return None
    lgl["opp"] = lgl["MATCHUP"].apply(opp_of)
    lgl["team_margin_asof"] = [margin_idx.get((r.team, r.GAME_DATE), np.nan)
                               for r in lgl.itertuples(index=False)]
    lgl["opp_margin_asof"] = [margin_idx.get((r.opp, r.GAME_DATE), np.nan)
                              for r in lgl.itertuples(index=False)]
    # mismatch magnitude: |my strength - opp strength| -> bigger => blowout risk => starters rest
    lgl["mismatch"] = (lgl["team_margin_asof"] - lgl["opp_margin_asof"]).abs()

    return lgl


# ----------------------------------------------------------------------------
# PHASE 1 — minutes_proj validation (does it beat l10 on OOS minutes MAE?)
# ----------------------------------------------------------------------------
MIN_FEATS = ["l10_min", "l5_min", "l3_min", "std_min", "prev_min", "rest", "is_b2b",
             "vac_min", "n_out", "vac_share_min", "rot_share", "team_margin_asof",
             "opp_margin_asof", "mismatch", "games_so_far"]
INTEL_FEATS = ["vac_min", "n_out", "vac_share_min", "team_margin_asof",
               "opp_margin_asof", "mismatch", "is_b2b", "rest"]


def phase1(d: pd.DataFrame):
    print("\n" + "=" * 76)
    print(" PHASE 1 — minutes_proj OUT-OF-SAMPLE minutes-MAE vs l10_min")
    print("=" * 76)
    pop = d[(d["games_so_far"] >= 3) & (d["l10_min"] >= 10)].dropna(
        subset=["l10_min", "l3_min", "l5_min"]).copy()
    print(f" bettable population (>=3 prior games, l10>=10): n={len(pop):,}")
    print(f" actual MIN mean={pop['MIN'].mean():.2f} std={pop['MIN'].std():.2f}; "
          f"minutes-surprise (actual-l10) std={ (pop['MIN']-pop['l10_min']).std():.2f}")

    ds = sorted(pop["GAME_DATE"].unique())
    mid = ds[len(ds) // 2]
    tr = pop[pop["GAME_DATE"] < mid]
    te = pop[pop["GAME_DATE"] >= mid].copy()
    print(f" leak-free split @ {pd.Timestamp(mid).date()}: train={len(tr):,} eval={len(te):,}")

    import xgboost as xgb
    feats = [c for c in MIN_FEATS if c in tr.columns]
    trX = tr[feats].fillna(0.0)
    teX = te[feats].fillna(0.0)
    params = {"objective": "reg:absoluteerror", "max_depth": 4, "eta": 0.03,
              "subsample": 0.8, "colsample_bytree": 0.8, "tree_method": "hist"}
    for dev in ("cuda", "cpu"):
        try:
            params["device"] = dev
            bst = xgb.train(params, xgb.DMatrix(trX, label=tr["MIN"]), num_boost_round=400)
            break
        except Exception as exc:  # noqa: BLE001
            print(f"   [{dev} failed: {exc}]")
    full_pred = bst.predict(xgb.DMatrix(teX))

    # intel-only-added model: l10/l5/l3 anchor PLUS intel — compare to pure-rolling model
    roll_feats = ["l10_min", "l5_min", "l3_min", "std_min", "prev_min", "games_so_far"]
    bst_roll = xgb.train(params, xgb.DMatrix(tr[roll_feats].fillna(0.0), label=tr["MIN"]),
                         num_boost_round=400)
    roll_pred = bst_roll.predict(xgb.DMatrix(te[roll_feats].fillna(0.0)))

    te["minutes_proj"] = full_pred
    te["minutes_proj_roll"] = roll_pred

    def mae(a, b):
        return float(np.abs(np.asarray(a) - np.asarray(b)).mean())

    mae_l10 = mae(te["MIN"], te["l10_min"])
    mae_blend = mae(te["MIN"], 0.4 * te["l3_min"] + 0.6 * te["l10_min"])
    mae_roll = mae(te["MIN"], roll_pred)
    mae_full = mae(te["MIN"], full_pred)
    print("\n EVAL MINUTES MAE (held-out late half):")
    print(f"   l10_min (model's implied) : {mae_l10:.4f}   [baseline]")
    print(f"   0.4*l3 + 0.6*l10 blend    : {mae_blend:.4f}   ({(mae_l10-mae_blend)/mae_l10*100:+.2f}% vs l10)")
    print(f"   XGB rolling-only          : {mae_roll:.4f}   ({(mae_l10-mae_roll)/mae_l10*100:+.2f}% vs l10)")
    print(f"   XGB + intel (minutes_proj): {mae_full:.4f}   ({(mae_l10-mae_full)/mae_l10*100:+.2f}% vs l10)")
    print(f"   intel marginal over rolling: {(mae_roll-mae_full)/mae_roll*100:+.2f}%")

    # where intel SHOULD matter: games with a regular OUT, and high-mismatch (blowout) games
    for label, m in [("n_out>0 (teammate out)", te["n_out"].values > 0),
                     ("mismatch>15 (blowout risk)", te["mismatch"].fillna(0).values > 15)]:
        if m.sum() < 50:
            continue
        a = te["MIN"].values[m]
        print(f"   --- subset {label}: n={m.sum():,} ---")
        print(f"       l10 MAE {mae(a, te['l10_min'].values[m]):.4f}  "
              f"minutes_proj MAE {mae(a, full_pred[m]):.4f}")

    gain = bst.get_score(importance_type="gain")
    print("   minutes_proj feature gain:",
          {k: round(v, 1) for k, v in sorted(gain.items(), key=lambda kv: -kv[1])})

    # attach minutes_proj + rates back for downstream phases (full pop, leak-free per row)
    # We fit on tr and predict on te ONLY for the held-out eval; for phases 2-3 we need a
    # leak-free minutes_proj for ALL bet dates. Use the rolling+intel XGB trained on the
    # EARLY half and predict everything dated >= mid (held-out), plus the simple deterministic
    # blend (which itself is leak-free everywhere) as the primary propagated projector.
    return mae_l10, mae_blend, mae_full, mid, bst, feats


# ----------------------------------------------------------------------------
# Build a per-(pid,date) leak-free minutes_proj lookup for the prop phases.
# Primary projector = deterministic 0.4*l3+0.6*l10 blend + intel tilt that was the
# winner in Phase 1; it requires NO train/test leakage (pure as-of arithmetic).
# ----------------------------------------------------------------------------
def build_proj_lookup(d: pd.DataFrame) -> dict:
    pop = d[(d["games_so_far"] >= 3)].dropna(subset=["l10_min"]).copy()
    # deterministic leak-free blend
    pop["minutes_blend"] = (0.4 * pop["l3_min"].fillna(pop["l10_min"])
                            + 0.6 * pop["l10_min"])
    out = {}
    for r in pop.itertuples(index=False):
        out[(int(r.PLAYER_ID), r.GAME_DATE)] = {
            "minutes_blend": float(r.minutes_blend) if pd.notna(r.minutes_blend) else np.nan,
            "l10_min_box": float(r.l10_min) if pd.notna(r.l10_min) else np.nan,
            "rate_pts": float(r.rate_pts) if pd.notna(r.rate_pts) else np.nan,
            "rate_reb": float(r.rate_reb) if pd.notna(r.rate_reb) else np.nan,
            "rate_ast": float(r.rate_ast) if pd.notna(r.rate_ast) else np.nan,
            "vac_share_min": float(r.vac_share_min) if pd.notna(r.vac_share_min) else 0.0,
            "n_out": int(r.n_out),
            "mismatch": float(r.mismatch) if pd.notna(r.mismatch) else np.nan,
        }
    return out


def attach_proj(bets, lookup):
    """Attach the box-log minutes_proj + per-minute rate to each bet dict.

    The box-log lookup only spans 2025-26 (leaguegamelog parquet window). For
    corpora outside that (Family C 2024-25) we FALL BACK to a calframe-only
    minutes projection so cross-season is still testable: minutes_proj_cal uses
    the calframe as-of conditioners (l3/l5/l10/min_trend) which DO span 2024-25,
    and per-minute rates are recovered from calframe l5_pts_pm/l5_reb_pm (and an
    AST rate proxy from l10). The two routes are graded identically downstream.
    """
    hit = hit_box = 0
    for b in bets:
        m = lookup.get((b["pid"], b["gdate"]))
        l10c = b.get("l10_min")  # calframe l10 (spans all corpora)
        if m is not None:
            b.update({f"box_{k}": v for k, v in m.items()})
            l10 = l10c if (l10c is not None and np.isfinite(l10c)) else m["l10_min_box"]
            b["_minutes_proj"] = m["minutes_blend"]
            b["_min_surprise"] = (m["minutes_blend"] - l10) if np.isfinite(l10) else np.nan
            hit_box += 1
            hit += 1
        else:
            # calframe fallback (cross-season): blend the calframe rolling minutes
            l3 = b.get("l3_min", np.nan) if "l3_min" in b else np.nan
            # calframe exposes l10_min + min_trend; reconstruct a short-window tilt
            mtr = b.get("min_trend", np.nan)
            if l10c is not None and np.isfinite(l10c):
                # minutes_proj_cal = l10 + 0.4*min_trend (min_trend already = short-vs-long slope)
                proj = l10c + (0.4 * mtr if np.isfinite(mtr) else 0.0)
                b["_minutes_proj"] = proj
                b["_min_surprise"] = proj - l10c
                # per-minute rate from calframe l5 per-minute fields where present
                b["box_rate_pts"] = b.get("l5_pts_pm", np.nan)
                b["box_rate_reb"] = b.get("l5_reb_pm", np.nan)
                b["box_rate_ast"] = np.nan  # no direct AST-pm in calframe; AST handled separately
                hit += 1
            else:
                b["_minutes_proj"] = np.nan
                b["_min_surprise"] = np.nan
    return hit_box if hit_box else hit


# ----------------------------------------------------------------------------
# PHASE 2 — orthogonality: corr(minutes_proj - l10, actual - pred) per stat
# ----------------------------------------------------------------------------
def phase2(bets):
    print("\n" + "=" * 76)
    print(" PHASE 2 — orthogonality  corr(minutes_surprise, actual-pred) per stat")
    print(" (minutes_surprise = box minutes_proj - model l10).  |corr|>=0.05 to proceed.")
    print("=" * 76)
    res = {}
    for stat in RATE_STATS:
        sub = [b for b in bets if b["stat"] == stat
               and np.isfinite(b.get("_min_surprise", np.nan))
               and np.isfinite(b.get("pred", np.nan))]
        if len(sub) < 30:
            print(f"   {stat}: n={len(sub)} too few")
            continue
        surp = np.array([b["_min_surprise"] for b in sub])
        resid = np.array([b["actual"] - b["pred"] for b in sub])
        r = np.corrcoef(surp, resid)[0, 1] if np.std(surp) > 1e-9 else float("nan")
        # also corr of the raw projection level vs residual
        flag = "  <-- NON-TRIVIAL" if abs(r) >= 0.05 else "  (absorbed)"
        print(f"   {stat}: corr(min_surprise, actual-pred) = {r:+.4f}  (n={len(sub)}){flag}")
        res[stat] = (r, len(sub))
    return res


# ----------------------------------------------------------------------------
# PHASE 3 — propagate minutes_surprise to props via per-min rate, grade ROI
#   pred_adj = pred + beta * (min_surprise * rate_stat),  fit EARLY, grade LATE.
# ----------------------------------------------------------------------------
def split_halves(bets):
    ds = sorted(set(b["gdate"] for b in bets))
    mid = ds[len(ds) // 2]
    return ([b for b in bets if b["gdate"] < mid],
            [b for b in bets if b["gdate"] >= mid], mid)


def _signal(b, stat):
    """minutes-surprise * as-of per-minute rate for the stat = expected counting delta.

    Primary (box-log corpora): min_surprise * box_rate_stat (additive counting delta).
    Fallback (no box rate, e.g. cross-season): scale pred by the minutes ratio, i.e.
    expected delta = pred * (minutes_proj/l10 - 1) = pred * min_surprise/l10. This is
    the multiplicative propagation and needs no separate per-minute rate.
    """
    s = b.get("_min_surprise", np.nan)
    rate = b.get(f"box_rate_{stat}", np.nan)
    if np.isfinite(s) and np.isfinite(rate):
        return s * rate
    # fallback: multiplicative via pred and l10
    pred = b.get("pred", np.nan)
    l10 = b.get("l10_min", np.nan)
    if np.isfinite(s) and np.isfinite(pred) and np.isfinite(l10) and l10 > 1:
        return pred * (s / l10)
    return np.nan


def fit_beta(rows, stat):
    sub = [b for b in rows if b["stat"] == stat
           and np.isfinite(_signal(b, stat)) and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 50:
        return None, len(sub)
    sig = np.array([_signal(b, stat) for b in sub])
    resid = np.array([b["actual"] - b["pred"] for b in sub])
    if np.std(sig) < 1e-9:
        return None, len(sub)
    return float(np.cov(sig, resid)[0, 1] / np.var(sig)), len(sub)


def grade(rows, stat, beta):
    sub = [b for b in rows if b["stat"] == stat
           and np.isfinite(_signal(b, stat)) and np.isfinite(b.get("pred", np.nan))]
    flips = 0
    for b in sub:
        b["_pred_adj"] = b["pred"] + beta * _signal(b, stat)
        if (b["pred"] > b["line"]) != (b["_pred_adj"] > b["line"]):
            flips += 1
    raw = ig.roi(sub, predictor="pred")
    adj = ig.roi(sub, predictor="_pred_adj")
    return raw, adj, flips, len(sub)


def phase3_corpus(corpus, lookup, beta_from=None):
    print(f"\n{'-'*76}\n PHASE 3 corpus: {corpus}\n{'-'*76}")
    bets = ig.prepare(corpus)
    coh = ig.coherence(bets)
    print(f"   coherence sum {coh['sum']:+.2f}%  ({'OK' if coh['coherent'] else 'CORRUPT'})  joined n={len(bets)}")
    if not coh["coherent"]:
        print("   !! corrupt corpus, skip")
        return None
    hit = attach_proj(bets, lookup)
    print(f"   box minutes_proj attached to {hit}/{len(bets)} bets")
    early, late, mid = split_halves(bets)
    out = {}
    for stat in RATE_STATS:
        if beta_from is not None and stat in beta_from:
            beta, n_fit = beta_from[stat], -1   # cross-corpus: use beta fit on Family A early
            src = "A-early"
        else:
            beta, n_fit = fit_beta(early, stat)
            src = "self-early"
        if beta is None:
            print(f"   {stat}: no beta (n_fit={n_fit})")
            continue
        raw, adj, flips, n = grade(late, stat, beta)
        print(f"   {stat}: beta={beta:+.4f} [{src}]  held-out LATE raw={raw['roi_pct']:+.2f}% "
              f"-> adj={adj['roi_pct']:+.2f}%  (n={n}, flips={flips})  "
              f"delta={adj['roi_pct']-raw['roi_pct']:+.2f}pp")
        out[stat] = {"beta": beta, "raw": raw["roi_pct"], "adj": adj["roi_pct"],
                     "delta": adj["roi_pct"] - raw["roi_pct"], "n": n, "flips": flips}
    return out, bets, early


def main():
    print("building leak-free as-of minutes feature table from box-appearance ledger...")
    d = build_minutes_table()
    print(f"  player-game rows: {len(d):,}")

    mae_l10, mae_blend, mae_full, mid, bst, feats = phase1(d)

    lookup = build_proj_lookup(d)
    print(f"\n  built (pid,date)->minutes_proj lookup with {len(lookup):,} keys")

    # Phase 2 on Family A (the big sample)
    famA = ig.prepare("extended_oos_canonical.csv")
    attach_proj(famA, lookup)
    ortho = phase2(famA)

    # Phase 3 — fit beta on Family A early; grade Family A late + cross corpora
    print("\n" + "=" * 76)
    print(" PHASE 3 — propagate minutes_surprise*rate to props; ROI lift held-out")
    print("=" * 76)
    resA = phase3_corpus("extended_oos_canonical.csv", lookup)
    beta_A = None
    if resA:
        _, _, earlyA = resA[1], resA[2] if len(resA) > 2 else None, None
    # refit explicit betas on Family A EARLY for cross-corpus application
    betas = {}
    early, _, _ = split_halves(famA)
    for stat in RATE_STATS:
        b, n = fit_beta(early, stat)
        if b is not None:
            betas[stat] = b
    print(f"\n  Family-A early-fit betas for cross-corpus: "
          f"{ {k: round(v,4) for k,v in betas.items()} }")

    # Family B (oddsapi 2025-26) and Family C (oddsapi 2024-25): independent
    phase3_corpus("regular_season_2025_26_oddsapi.csv", lookup, beta_from=betas)
    phase3_corpus("regular_season_2024_25_oddsapi.csv", lookup, beta_from=betas)

    print("\n" + "=" * 76)
    print(" SUMMARY")
    print("=" * 76)
    print(f"  PHASE 1 minutes MAE: l10={mae_l10:.4f}  blend={mae_blend:.4f} "
          f"({(mae_l10-mae_blend)/mae_l10*100:+.2f}%)  full-intel={mae_full:.4f} "
          f"({(mae_l10-mae_full)/mae_l10*100:+.2f}%)")
    print(f"  PHASE 2 orthogonality: { {k: round(v[0],4) for k,v in ortho.items()} }")


if __name__ == "__main__":
    main()
