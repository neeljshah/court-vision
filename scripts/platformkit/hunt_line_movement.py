"""HUNT C -- line movement / freshness CLV substrate (read-only analysis).

The grounding report establishes that basketball_nba/odds_snapshots/ is NOT a
usable line-movement backtest corpus (18 lines, one Finals game, the only delta
is a 0.01-decimal h2h jitter + a vig re-split -- no real move). The genuine
open->close substrate at the price level is the open+close columns of the MLB
(2010-2021, ~28k) and Soccer (2019-2026, ~16k) odds.parquet files.

This module measures, leak-free by snapshot ordering (open precedes close):
  1. distribution of open->close moves (is the move material?)
  2. is the move PREDICTABLE from open-time info? -- specifically, does the
     disagreement between a leak-free pregame model and the OPENER predict the
     realized open->close drift? (the CLV-capture mechanism)
  3. would betting the opener on disagreement have captured CLV? in-sample,
     leak-free; CLV in-sample is SUGGESTIVE, never a $ claim.

Anti-p-hack: >=2 independent corpora (MLB NL vs AL; soccer as a different sport).
A lift on one with a drop on the other = overfit signature = REJECT. Report the
honest verdict; "market efficient here" is a recorded SUCCESS. ASCII only.

Run:  python -m scripts.platformkit.hunt_line_movement
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def am2p(a):
    a = np.asarray(a, float)
    return np.where(a < 0, -a / (-a + 100.0), 100.0 / (a + 100.0))


def devig2(ph, pa):
    s = ph + pa
    return ph / s


def _block_bootstrap_corr(x, y, blocks, n=2000, seed=0):
    """Block bootstrap of Pearson r, clustering by block id (e.g. season)."""
    rng = np.random.default_rng(seed)
    blk = pd.Series(blocks).values
    uniq = np.unique(blk)
    idx_by = {b: np.where(blk == b)[0] for b in uniq}
    r0 = np.corrcoef(x, y)[0, 1]
    rs = []
    for _ in range(n):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ii = np.concatenate([idx_by[b] for b in pick])
        xx, yy = x[ii], y[ii]
        if xx.std() > 0 and yy.std() > 0:
            rs.append(np.corrcoef(xx, yy)[0, 1])
    rs = np.array(rs)
    lo, hi = np.percentile(rs, [2.5, 97.5])
    return r0, lo, hi


def _clv_from_disagreement(df, model_col, open_col, close_col, blocks):
    """Leak-free CLV test. At OPEN time we know model_prob and the opener fair
    prob. Bet the side our model likes when it disagrees with the opener; CLV =
    (close fair - open fair) in the direction of the bet. Open precedes close,
    so this is leak-free by snapshot order. We do NOT use the result here -- CLV
    is purely a line-movement quantity.
    Returns mean signed CLV (pp), N, and a block-bootstrap CI.
    """
    model = df[model_col].values
    op = df[open_col].values
    cl = df[close_col].values
    edge = model - op                      # >0 -> we like HOME more than opener
    side = np.sign(edge)                    # +1 bet home, -1 bet away
    bet = side != 0
    # signed move in the direction of our bet:
    move_home = cl - op                     # close-open in home fair prob
    clv = np.where(side > 0, move_home, -move_home)  # away-side CLV = -(home move)
    clv = clv[bet]
    blk = pd.Series(blocks).values[bet]
    n = len(clv)
    mean = clv.mean()
    # block bootstrap CI clustered by season
    rng = np.random.default_rng(1)
    uniq = np.unique(blk)
    idx_by = {b: np.where(blk == b)[0] for b in uniq}
    means = []
    for _ in range(3000):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ii = np.concatenate([idx_by[b] for b in pick])
        means.append(clv[ii].mean())
    lo, hi = np.percentile(means, [2.5, 97.5])
    return mean, n, lo, hi, edge


# --------------------------------------------------------------------------
def analyze_mlb():
    od = pd.read_parquet("data/domains/mlb/odds.parquet")
    gm = pd.read_parquet("data/domains/mlb/games.parquet")
    af = pd.read_parquet("data/domains/mlb/asof_features.parquet")
    df = od.merge(gm[["event_id", "target_home_win", "home_league"]], on="event_id", how="inner")
    df = df.merge(af[["event_id", "sp_ra_diff_asof"]], on="event_id", how="left")
    df = df.dropna(subset=["ml_open_home_am", "ml_open_away_am",
                            "ml_close_home_am", "ml_close_away_am",
                            "target_home_win"]).copy()
    df = df[(df["ml_open_home_am"] != 0) & (df["ml_open_away_am"] != 0)]
    df = df.sort_values(["season", "date"]).reset_index(drop=True)

    oh, oa = am2p(df["ml_open_home_am"]), am2p(df["ml_open_away_am"])
    ch, ca = am2p(df["ml_close_home_am"]), am2p(df["ml_close_away_am"])
    df["fopen"] = devig2(oh, oa)
    df["fclose"] = devig2(ch, ca)
    df["move"] = df["fclose"] - df["fopen"]

    print("=== MLB (2010-2021, book=sbro_archive) ===")
    print("N games:", len(df))
    print("[1] open->close move (home fair prob): mean %+.4f  std %.4f" % (df["move"].mean(), df["move"].std()))
    print("    mean |move| = %.4f pp ;  %%|move|>1pp=%.1f  >2pp=%.1f  >3pp=%.1f"
          % (100 * df["move"].abs().mean(),
             100 * (df["move"].abs() > 0.01).mean(),
             100 * (df["move"].abs() > 0.02).mean(),
             100 * (df["move"].abs() > 0.03).mean()))

    # ---- [2] is the move PREDICTABLE at open time? ----
    # Predictor A: the opener's own deviation from a leak-free model.
    # Leak-free model = expanding-window logistic on (home flag is constant) ...
    # Simplest honest open-time model: as-of starting-pitcher RA diff -> logit,
    # fit on a PURELY PRIOR expanding window (walk-forward by season).
    df["spdiff"] = df["sp_ra_diff_asof"].fillna(0.0)
    # walk-forward logistic: train on seasons < s, predict season s
    from sklearn.linear_model import LogisticRegression
    seasons = sorted(df["season"].unique())
    df["model_p"] = np.nan
    for i, s in enumerate(seasons):
        tr = df[df["season"] < s]
        te = df[df["season"] == s]
        if len(tr) < 500:
            # cold start: use the opener itself (no model edge claimed for season 0)
            df.loc[te.index, "model_p"] = df.loc[te.index, "fopen"]
            continue
        # negative spdiff (home SP allows fewer runs) -> home better
        lr = LogisticRegression(max_iter=200)
        lr.fit(tr[["spdiff"]].values, tr["target_home_win"].values)
        df.loc[te.index, "model_p"] = lr.predict_proba(te[["spdiff"]].values)[:, 1]
    df = df.dropna(subset=["model_p"])

    # correlation: does (model - opener) predict the realized (close - open)?
    edge_open = (df["model_p"] - df["fopen"]).values
    realized = df["move"].values
    r, lo, hi = _block_bootstrap_corr(edge_open, realized, df["season"].values)
    print("[2] corr( model_p - opener , close - open )  r=%+.4f  CI95[%+.4f,%+.4f]" % (r, lo, hi))
    print("    (positive r => when our model is higher than the opener, the line tends to")
    print("     move our way by close => the move is partly predictable at open time)")

    # also: does the opener->close move just predict the RESULT better than opener?
    # i.e. is the closer sharper than the opener? (classic CLV existence test)
    from sklearn.metrics import log_loss
    y = df["target_home_win"].values
    ll_open = log_loss(y, df["fopen"].clip(1e-4, 1 - 1e-4))
    ll_close = log_loss(y, df["fclose"].clip(1e-4, 1 - 1e-4))
    print("    closer sharper than opener?  logloss open=%.4f close=%.4f  (close lower => sharper)" % (ll_open, ll_close))

    # ---- [3] CLV capture from disagreement, per corpus (NL vs AL) ----
    print("[3] CLV capture -- bet opener when model disagrees, CLV = move in bet direction (pp):")
    for lg in ["NL", "AL"]:
        sub = df[df["home_league"] == lg]
        if len(sub) < 200:
            print("    %s: N<200, skip" % lg)
            continue
        mean, n, clo, chi, _ = _clv_from_disagreement(sub, "model_p", "fopen", "fclose", sub["season"].values)
        sig = "POS-CLV" if clo > 0 else ("NEG" if chi < 0 else "~0/efficient")
        print("    %s: N=%d  mean CLV=%+.4f pp  CI95[%+.4f,%+.4f]  -> %s"
              % (lg, n, 100 * mean, 100 * clo, 100 * chi, sig))
    # whole-corpus
    mean, n, clo, chi, _ = _clv_from_disagreement(df, "model_p", "fopen", "fclose", df["season"].values)
    print("    ALL: N=%d mean CLV=%+.4f pp CI95[%+.4f,%+.4f]" % (n, 100 * mean, 100 * clo, 100 * chi))
    return df


def analyze_soccer():
    od = pd.read_parquet("data/domains/soccer/odds.parquet")
    print("\n=== SOCCER (2019-2026) -- O/U 2.5 open->close ===")
    print("cols sample:", [c for c in od.columns if "ou" in c.lower() or "open" in c.lower() or "close" in c.lower()][:12])
    need = ["ou_open_over", "ou_open_under", "ou_close_over", "ou_close_under"]
    if not all(c in od.columns for c in need):
        print("  open/close O/U cols not all present -> skip soccer price-move test")
        return None
    df = od.dropna(subset=need).copy()
    oo, ou = 1.0 / df["ou_open_over"], 1.0 / df["ou_open_under"]
    co, cu = 1.0 / df["ou_close_over"], 1.0 / df["ou_close_under"]
    df["fopen"] = oo / (oo + ou)      # fair P(over)
    df["fclose"] = co / (co + cu)
    df["move"] = df["fclose"] - df["fopen"]
    print("N:", len(df))
    print("[1] open->close move (fair P over): mean %+.4f std %.4f  mean|move|=%.4f pp  %%>1pp=%.1f >2pp=%.1f"
          % (df["move"].mean(), df["move"].std(), 100 * df["move"].abs().mean(),
             100 * (df["move"].abs() > 0.01).mean(), 100 * (df["move"].abs() > 0.02).mean()))
    # autocorrelation / mean-reversion of the move is the cheapest predictability
    # test that needs no result: does the opener's deviation from the league-avg
    # opener predict the move? (a momentum/anchoring proxy, leak-free at open)
    if "div" in df.columns:
        df["lg_mean_open"] = df.groupby("div")["fopen"].transform("mean")
        anchor = (df["fopen"] - df["lg_mean_open"]).values
        r = np.corrcoef(anchor, df["move"].values)[0, 1]
        print("[2] corr( opener - league_mean_opener , move ) r=%+.4f (mean-reversion if <0)" % r)
        # >=2 corpora: split leagues by div
        divs = df["div"].value_counts()
        print("    leagues present (div):", divs.head(6).to_dict())
    return df


def main():
    analyze_mlb()
    analyze_soccer()
    print("\n=== HONEST VERDICT printed above; CLV in-sample is SUGGESTIVE only,")
    print("    a $ edge is NOT claimed without real forward CLV capture. ===")


if __name__ == "__main__":
    main()
