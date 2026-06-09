"""audit_ensemble_optimality.py — is the DEPLOYED in-game `routed` ensemble
optimal and calibrated? Read-only, instant (uses data/cache/ingame_eval_cache).

NOTHING here flips a flag, touches the live engine / golive / webpage, or trains
a model. It scores counterfactual blends/shrinks against the deployed `routed`
projection already baked into the fast cache, leak-free (fold-out-of-fold), and
reports per (stat, bucket) so any gated fix is honest.

Four audits (see docs/_audits/INGAME_ENSEMBLE_OPTIMALITY.md):
  1. RE-WEIGHT THE BLEND. Fit a leak-free per-(bucket,stat) non-negative blend of
     {snapshot, v2, l5, cur} on 3 train folds, apply to the held-out fold (true
     OOF over all 4 folds), compare MAE to `routed` on full / 200g / 500g. Try a
     ridge-shrunk-to-routed variant to fight per-cell overfit.
  2. SHRINK CURVE. Characterise early-game (the shrink regime) — is there a better
     per-stat shrink toward the L5 anchor than the deployed l5floor:12:0.30?
  3. CALIBRATION. Per-(bucket,stat) residual std of the deployed `routed` point
     projection — the basis for an HONEST in-game sigma (none is served today).
  4. PLUMBING. Any (bucket,stat) cell where `routed` MAE is WORSE than one of its
     OWN input components (snapshot|v2|l5|cur) — a blend should never lose to its
     input. Those cells are flagged as blend bugs.

Run:  python scripts/ingame/audit_ensemble_optimality.py
      python scripts/ingame/audit_ensemble_optimality.py --json out.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, ".")
from scripts.ingame._ingame_fast_harness import load_eval_frame  # noqa: E402

CORE_STATS = ("pts", "reb", "ast")
COMPONENTS = ("snapshot", "v2", "l5", "cur")
BUCKET_ORDER = [
    "02min(earlyQ1)", "04min(earlyQ1)", "06min(midQ1)", "12min(endQ1)",
    "18min(midQ2)", "24min(endQ2/half)", "30min(midQ3)", "36min(endQ3)",
    "42min(midQ4)", "44min(lateQ4)", "46min(lateQ4)",
]
EARLY_BUCKETS = {"02min(earlyQ1)", "04min(earlyQ1)", "06min(midQ1)"}
EPS = 1e-9


# --------------------------------------------------------------------------- #
# subset helpers (mirror the fast harness's chronological gate subsets)
# --------------------------------------------------------------------------- #
def first_n_games_mask(df, n):
    order = (df[["game_date", "game_id"]].drop_duplicates()
             .sort_values(["game_date", "game_id"]).head(n))
    keys = set(map(tuple, order.values.tolist()))
    gd = df["game_date"].to_numpy()
    gi = df["game_id"].to_numpy()
    return np.array([(d, g) in keys for d, g in zip(gd, gi)])


def mae(pred, truth):
    return float(np.abs(np.asarray(pred) - np.asarray(truth)).mean())


# --------------------------------------------------------------------------- #
# AUDIT 1 — leak-free optimal per-(bucket,stat) blend of the components.
# --------------------------------------------------------------------------- #
def _fit_blend_weights(X, y, shrink_to=None, lam=0.0):
    """Non-negative weights w (sum->1 enforced by appended row) minimising
    ||Xw - y||^2 + lam*||w - shrink_to||^2 via NNLS on the augmented system.

    X: (n, k) component values. y: (n,) truth. Returns length-k convex weights.
    A small ridge toward `shrink_to` (e.g. the deployed one-hot route) fights
    per-cell overfit on thin folds.
    """
    from scipy.optimize import nnls
    n, k = X.shape
    # soft sum-to-one: append a heavily weighted constraint row.
    big = 1e3
    A = np.vstack([X, big * np.ones((1, k))])
    b = np.concatenate([y, [big]])
    if lam > 0.0 and shrink_to is not None:
        s = np.asarray(shrink_to, float)
        A = np.vstack([A, np.sqrt(lam) * np.eye(k)])
        b = np.concatenate([b, np.sqrt(lam) * s])
    w, _ = nnls(A, b)
    sw = w.sum()
    if sw <= EPS:
        # degenerate -> fall back to shrink target or uniform
        return np.asarray(shrink_to, float) if shrink_to is not None else np.ones(k) / k
    return w / sw


def _deployed_onehot(df_cell):
    """Which single component the DEPLOYED routed value tracks in this cell
    (the head it is numerically closest to) — used as the ridge shrink target so
    the fitted blend only *moves* off the deployed route when the data demands."""
    best, bd = None, 1e18
    for i, c in enumerate(COMPONENTS):
        sub = df_cell.dropna(subset=[c])
        if not len(sub):
            continue
        d = float((sub["routed"] - sub[c]).abs().mean())
        if d < bd:
            bd, best = d, i
    v = np.zeros(len(COMPONENTS))
    if best is not None:
        v[best] = 1.0
    return v


def audit_blend(df, lam=2.0, verbose=True):
    """True OOF: for each held-out fold, fit per-(bucket,stat) weights on the
    OTHER folds, predict the held-out rows. Build a full-length `blend` and a
    `blend_ridge` column, then compare MAE to routed on full/200g/500g."""
    d = df[df["stat"].isin(CORE_STATS)].copy().reset_index(drop=True)
    # component matrix; cur is always present, others may have NaN (l5 rookies).
    folds = sorted(d["fold"].unique())
    blend = np.full(len(d), np.nan)
    blend_r = np.full(len(d), np.nan)

    # store learned weights (last fold) for reporting
    learned = {}

    for test_f in folds:
        tr = d[d["fold"] != test_f]
        te_idx = d.index[d["fold"] == test_f]
        for s in CORE_STATS:
            for b in BUCKET_ORDER:
                tr_cell = tr[(tr["stat"] == s) & (tr["bucket"] == b)]
                te_mask = (d["stat"] == s) & (d["bucket"] == b) & (d["fold"] == test_f)
                te_rows = d[te_mask]
                if not len(te_rows):
                    continue
                if len(tr_cell) < 50:
                    # too thin: defer to deployed routed (no change)
                    blend[te_rows.index] = te_rows["routed"].to_numpy()
                    blend_r[te_rows.index] = te_rows["routed"].to_numpy()
                    continue
                # impute NaN component with cur (the floor) for fitting+applying
                def _mat(frame):
                    cols = []
                    cur = frame["cur"].to_numpy(float)
                    for c in COMPONENTS:
                        col = frame[c].to_numpy(float)
                        col = np.where(np.isnan(col), cur, col)
                        cols.append(col)
                    return np.column_stack(cols)
                Xtr = _mat(tr_cell); ytr = tr_cell["truth"].to_numpy(float)
                Xte = _mat(te_rows)
                shrink = _deployed_onehot(tr_cell)
                w0 = _fit_blend_weights(Xtr, ytr, shrink_to=shrink, lam=0.0)
                wr = _fit_blend_weights(Xtr, ytr, shrink_to=shrink, lam=lam)
                # floor at cur (every served head is floored at current)
                cur_te = te_rows["cur"].to_numpy(float)
                blend[te_rows.index] = np.maximum(cur_te, Xte @ w0)
                blend_r[te_rows.index] = np.maximum(cur_te, Xte @ wr)
                learned[(s, b)] = (w0, wr)

    d["blend"] = blend
    d["blend_ridge"] = blend_r

    def _cmp(frame, scope):
        out = {"scope": scope, "n": int(len(frame))}
        out["routed"] = mae(frame["routed"], frame["truth"])
        out["blend"] = mae(frame["blend"], frame["truth"])
        out["blend_ridge"] = mae(frame["blend_ridge"], frame["truth"])
        out["d_blend_pct"] = (out["blend"] - out["routed"]) / out["routed"] * 100
        out["d_ridge_pct"] = (out["blend_ridge"] - out["routed"]) / out["routed"] * 100
        return out

    reports = {"full": _cmp(d, "full")}
    for n in (200, 500):
        if d["game_id"].nunique() >= n:
            m = first_n_games_mask(d, n)
            reports[f"{n}g"] = _cmp(d[m], f"{n}g")

    # per-stat full
    per_stat = {}
    for s in CORE_STATS:
        ds = d[d["stat"] == s]
        per_stat[s] = {
            "routed": mae(ds["routed"], ds["truth"]),
            "blend": mae(ds["blend"], ds["truth"]),
            "blend_ridge": mae(ds["blend_ridge"], ds["truth"]),
        }
        per_stat[s]["d_blend_pct"] = (per_stat[s]["blend"] - per_stat[s]["routed"]) / per_stat[s]["routed"] * 100
        per_stat[s]["d_ridge_pct"] = (per_stat[s]["blend_ridge"] - per_stat[s]["routed"]) / per_stat[s]["routed"] * 100

    # per (stat,bucket) OOF MAE: routed vs blend_ridge — where does blend help/hurt
    cells = {}
    for s in CORE_STATS:
        for b in BUCKET_ORDER:
            ds = d[(d["stat"] == s) & (d["bucket"] == b)]
            if not len(ds):
                continue
            r = mae(ds["routed"], ds["truth"])
            bl = mae(ds["blend_ridge"], ds["truth"])
            cells[(s, b)] = {"routed": r, "blend_ridge": bl,
                             "d_pct": (bl - r) / r * 100 if r else 0.0,
                             "n": int(len(ds))}

    if verbose:
        print("\n" + "=" * 78)
        print("AUDIT 1 — optimal leak-free per-(bucket,stat) blend vs deployed routed")
        print("=" * 78)
        print(f"  (ridge shrink lam={lam} toward deployed one-hot route; true 4-fold OOF)")
        for k, r in reports.items():
            print(f"  {r['scope']:5s} (n={r['n']:>9,}): routed={r['routed']:.4f}  "
                  f"blend={r['blend']:.4f} ({r['d_blend_pct']:+.2f}%)  "
                  f"blend_ridge={r['blend_ridge']:.4f} ({r['d_ridge_pct']:+.2f}%)")
        print("  per-stat (full):")
        for s, v in per_stat.items():
            print(f"    {s}: routed={v['routed']:.4f} blend={v['blend']:.4f} "
                  f"({v['d_blend_pct']:+.2f}%) ridge={v['blend_ridge']:.4f} "
                  f"({v['d_ridge_pct']:+.2f}%)")
        print("  cells where ridge-blend BEATS routed by >0.5% (OOF):")
        any_win = False
        for (s, b), v in sorted(cells.items(), key=lambda kv: kv[1]["d_pct"]):
            if v["d_pct"] < -0.5:
                any_win = True
                print(f"    {s:4s} {b:20s} routed={v['routed']:.3f} -> "
                      f"blend={v['blend_ridge']:.3f} ({v['d_pct']:+.2f}%) n={v['n']}")
        if not any_win:
            print("    (none > 0.5%)")
    return {"reports": reports, "per_stat": per_stat, "cells":
            {f"{s}|{b}": v for (s, b), v in cells.items()}, "lam": lam}


# --------------------------------------------------------------------------- #
# AUDIT 2 — shrink-curve optimality on the early-game rows.
# --------------------------------------------------------------------------- #
def audit_shrink(df, verbose=True):
    """The deployed early-game projection blends pregame-L5 toward the live head.
    We can't re-derive the exact l5floor:12:0.30 schedule from the point cache
    (the shrink is applied inside the serve path, not stored), but we CAN ask the
    cleaner question the cache answers leak-free: in the early buckets, what
    static convex weight a on L5 vs the live head (v2) minimises OOF MAE, and is
    the deployed `routed` (which already does this blend) near that optimum?

    For each early bucket+stat, sweep a in [0,1] for pred = max(cur, a*l5+(1-a)*v2)
    on train folds, pick best a, evaluate on held-out fold. Compare to routed."""
    d = df[df["stat"].isin(CORE_STATS)].copy()
    d = d[d["bucket"].isin(EARLY_BUCKETS)].reset_index(drop=True)
    folds = sorted(d["fold"].unique())
    alphas = np.linspace(0, 1, 21)
    pred = np.full(len(d), np.nan)
    best_a = {}
    for s in CORE_STATS:
        for b in sorted(EARLY_BUCKETS):
            ds_idx = d.index[(d["stat"] == s) & (d["bucket"] == b)]
            if not len(ds_idx):
                continue
            for test_f in folds:
                tr = d[(d["stat"] == s) & (d["bucket"] == b) & (d["fold"] != test_f)].dropna(subset=["l5", "v2"])
                te = d[(d["stat"] == s) & (d["bucket"] == b) & (d["fold"] == test_f)]
                if len(tr) < 50 or not len(te):
                    pred[te.index] = te["routed"].to_numpy()
                    continue
                cur_tr = tr["cur"].to_numpy(float)
                l5t = tr["l5"].to_numpy(float); v2t = tr["v2"].to_numpy(float)
                yt = tr["truth"].to_numpy(float)
                best, ba = 1e18, 0.0
                for a in alphas:
                    p = np.maximum(cur_tr, a * l5t + (1 - a) * v2t)
                    m = np.abs(p - yt).mean()
                    if m < best:
                        best, ba = m, a
                best_a[(s, b, test_f)] = ba
                cur_te = te["cur"].to_numpy(float)
                l5e = np.where(np.isnan(te["l5"].to_numpy(float)), cur_te, te["l5"].to_numpy(float))
                v2e = np.where(np.isnan(te["v2"].to_numpy(float)), cur_te, te["v2"].to_numpy(float))
                pred[te.index] = np.maximum(cur_te, ba * l5e + (1 - ba) * v2e)
    d["shrink_opt"] = pred

    rep = {}
    for s in CORE_STATS:
        ds = d[d["stat"] == s].dropna(subset=["shrink_opt"])
        rep[s] = {"routed": mae(ds["routed"], ds["truth"]),
                  "shrink_opt": mae(ds["shrink_opt"], ds["truth"]),
                  "n": int(len(ds))}
        rep[s]["d_pct"] = (rep[s]["shrink_opt"] - rep[s]["routed"]) / rep[s]["routed"] * 100
    # mean best-alpha per (stat,bucket)
    amean = defaultdict(list)
    for (s, b, f), a in best_a.items():
        amean[(s, b)].append(a)
    amean = {f"{s}|{b}": float(np.mean(v)) for (s, b), v in amean.items()}

    if verbose:
        print("\n" + "=" * 78)
        print("AUDIT 2 — early-game L5<->v2 shrink optimality (early buckets only)")
        print("=" * 78)
        print("  OOF best static a = weight on L5 (pred = max(cur, a*L5 + (1-a)*v2)):")
        for s in CORE_STATS:
            v = rep[s]
            print(f"    {s}: routed={v['routed']:.4f} shrink_opt={v['shrink_opt']:.4f} "
                  f"({v['d_pct']:+.2f}%) n={v['n']}")
        print("  learned mean a-on-L5 per (stat,bucket):")
        for k in sorted(amean):
            print(f"    {k:24s} a_L5={amean[k]:.2f}")
    return {"per_stat": rep, "alpha_on_l5": amean}


# --------------------------------------------------------------------------- #
# AUDIT 3 — calibration: residual std of routed by (bucket,stat).
# --------------------------------------------------------------------------- #
def audit_calibration(df, verbose=True):
    d = df[df["stat"].isin(CORE_STATS)].copy()
    d["resid"] = d["routed"] - d["truth"]
    out = {}
    for s in CORE_STATS:
        out[s] = {}
        for b in BUCKET_ORDER:
            ds = d[(d["stat"] == s) & (d["bucket"] == b)]
            if not len(ds):
                continue
            r = ds["resid"].to_numpy(float)
            out[s][b] = {
                "n": int(len(ds)),
                "mae": float(np.abs(r).mean()),
                "bias": float(r.mean()),
                "std": float(r.std(ddof=1)) if len(ds) > 1 else float("nan"),
                # robust scale: 1.4826*MAD as an outlier-resistant sigma
                "robust_sigma": float(1.4826 * np.median(np.abs(r - np.median(r)))),
            }
    if verbose:
        print("\n" + "=" * 78)
        print("AUDIT 3 — per-(bucket,stat) residual std of routed  (HONEST in-game sigma)")
        print("=" * 78)
        print(f"  {'stat':4s} {'bucket':20s} {'n':>8s} {'mae':>6s} {'bias':>7s} "
              f"{'std':>6s} {'rob_sig':>7s}")
        for s in CORE_STATS:
            for b in BUCKET_ORDER:
                if b not in out[s]:
                    continue
                v = out[s][b]
                print(f"  {s:4s} {b:20s} {v['n']:>8,} {v['mae']:6.3f} "
                      f"{v['bias']:+7.3f} {v['std']:6.3f} {v['robust_sigma']:7.3f}")
            print()
    return out


# --------------------------------------------------------------------------- #
# AUDIT 4 — plumbing: routed worse than its OWN best component (blend bug).
# --------------------------------------------------------------------------- #
def audit_plumbing(df, tol_pct=0.5, verbose=True):
    d = df[df["stat"].isin(CORE_STATS)].copy()
    flags = []
    table = {}
    for s in CORE_STATS:
        for b in BUCKET_ORDER:
            ds = d[(d["stat"] == s) & (d["bucket"] == b)]
            if not len(ds):
                continue
            rm = mae(ds["routed"], ds["truth"])
            comp = {}
            for c in COMPONENTS:
                sub = ds.dropna(subset=[c])
                comp[c] = mae(sub[c], sub["truth"]) if len(sub) else float("nan")
            best_c = min(comp, key=lambda k: comp[k] if comp[k] == comp[k] else 1e18)
            best_m = comp[best_c]
            gap_pct = (rm - best_m) / best_m * 100 if best_m else 0.0
            table[(s, b)] = {"routed": rm, **comp, "best_comp": best_c,
                             "best_mae": best_m, "gap_pct": gap_pct,
                             "n": int(len(ds))}
            if gap_pct > tol_pct:
                flags.append((s, b, rm, best_c, best_m, gap_pct, int(len(ds))))
    if verbose:
        print("\n" + "=" * 78)
        print("AUDIT 4 — BLEND BUGS: cells where routed is WORSE than its own best input")
        print("=" * 78)
        if not flags:
            print("  NONE — routed >= its best input component in every core cell. OK.")
        else:
            print(f"  {len(flags)} cell(s) where routed MAE > best-component MAE by >{tol_pct}%:")
            print(f"  {'stat':4s} {'bucket':20s} {'routed':>7s} {'bestcmp':>8s} "
                  f"{'bestMAE':>7s} {'gap%':>7s} {'n':>8s}")
            for s, b, rm, bc, bm, gp, n in sorted(flags, key=lambda x: -x[5]):
                print(f"  {s:4s} {b:20s} {rm:7.3f} {bc:>8s} {bm:7.3f} "
                      f"{gp:+7.2f} {n:>8,}")
    # SEPARATE the two late-game effects so the honest line is explicit:
    #  (a) GENUINE routing bug: late-Q4 pts/reb routed to `snapshot` when `v2` is
    #      both lower-MAE AND ~unbiased (mean-preserving) -> a clean, bet-safe fix.
    #  (b) CUR-SKEW: `cur` (the floor) wins even more on MAE but is NEGATIVELY
    #      biased (under-projects the mean) -> MAE-only, NOT bet-safe (median vs
    #      mean). We report v2's bias so the reader can tell them apart.
    routing_fix = {}
    for s in ("pts", "reb"):
        for b in ("42min(midQ4)", "44min(lateQ4)", "46min(lateQ4)"):
            ds = d[(d["stat"] == s) & (d["bucket"] == b)]
            if not len(ds):
                continue
            rm = mae(ds["routed"], ds["truth"])
            v2m = mae(ds["v2"], ds["truth"])
            v2bias = float((ds["v2"] - ds["truth"]).mean())
            curm = mae(ds["cur"], ds["truth"])
            curbias = float((ds["cur"] - ds["truth"]).mean())
            routing_fix[f"{s}|{b}"] = {
                "routed": rm, "v2": v2m, "v2_bias": v2bias,
                "v2_gain_pct": (v2m - rm) / rm * 100 if rm else 0.0,
                "cur": curm, "cur_bias": curbias,
                "cur_gain_pct": (curm - rm) / rm * 100 if rm else 0.0,
                "n": int(len(ds))}
    if verbose:
        print("\n  --- late-Q4 effect separation (honest line) ---")
        print("  v2-route = mean-preserving FIX (bet-safe); cur-hold = MAE-skew (NOT bet-safe)")
        print(f"  {'cell':22s} {'routed':>7s} {'v2':>7s} {'v2bias':>7s} {'v2gain%':>8s} "
              f"{'cur':>7s} {'curbias':>8s} {'curgain%':>9s}")
        for k, v in routing_fix.items():
            print(f"  {k:22s} {v['routed']:7.3f} {v['v2']:7.3f} {v['v2_bias']:+7.2f} "
                  f"{v['v2_gain_pct']:+8.2f} {v['cur']:7.3f} {v['cur_bias']:+8.2f} "
                  f"{v['cur_gain_pct']:+9.2f}")
    return {"flags": [{"stat": s, "bucket": b, "routed": rm, "best_comp": bc,
                       "best_mae": bm, "gap_pct": gp, "n": n}
                      for s, b, rm, bc, bm, gp, n in flags],
            "table": {f"{s}|{b}": v for (s, b), v in table.items()},
            "late_routing_fix": routing_fix}


# --------------------------------------------------------------------------- #
# RECOMMENDED GATED FIX — route late-Q4 pts/reb to v2 (mean-preserving), scored
# through the OFFICIAL fast-harness gate (full AND 200g AND 500g, no regression).
# --------------------------------------------------------------------------- #
def audit_routing_fix(df, verbose=True):
    """The clean, bet-safe lever: in the three late-Q4 buckets the deployed route
    sends pts/reb to `snapshot`; `v2` is lower-MAE AND ~unbiased there. Replace the
    remaining-projection with the v2 head's remaining for pts/reb late, scored via
    the canonical score_adjustment gate (so this is the SAME bar every other gated
    in-game fix had to clear). Implemented as a multiplier on the remaining-projection
    that retargets routed->v2: mult = (v2 - cur) / (routed - cur)."""
    from scripts.ingame._ingame_fast_harness import score_adjustment
    LATE = ("42min(midQ4)", "44min(lateQ4)", "46min(lateQ4)")

    def adjust(dd):
        m = np.ones(len(dd))
        st = dd["stat"].to_numpy(); bk = dd["bucket"].to_numpy()
        cur = dd["cur"].to_numpy(float); rt = dd["routed"].to_numpy(float)
        v2 = dd["v2"].to_numpy(float)
        rem = rt - cur
        target = v2 - cur  # v2's remaining projection
        hit = np.isin(st, ("pts", "reb")) & np.isin(bk, LATE) & (np.abs(rem) > 1e-9) & ~np.isnan(v2)
        m[hit] = target[hit] / rem[hit]
        return m

    res = score_adjustment(df, adjust, label="late_pts_reb_route_to_v2",
                           stats=("pts", "reb", "ast"), verbose=verbose)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--lam", type=float, default=2.0)
    a = ap.parse_args()
    df = load_eval_frame()
    print(f"loaded {len(df):,} rows / {df['game_id'].nunique()} games / "
          f"{sorted(df['fold'].unique())} folds")
    res = {}
    res["blend"] = audit_blend(df, lam=a.lam)
    res["shrink"] = audit_shrink(df)
    res["calibration"] = audit_calibration(df)
    res["plumbing"] = audit_plumbing(df)
    print("\n" + "=" * 78)
    print("RECOMMENDED GATED FIX — late-Q4 pts/reb: route to v2 (mean-preserving)")
    print("=" * 78)
    res["routing_fix_gate"] = audit_routing_fix(df)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2, default=float)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
