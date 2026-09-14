"""scripts.platformkit.proof_nba.prop_game_model -- player-GAME grain prop challenger (Q15).

Rebuilds src/prediction/player_props.py's player-SEASON grain trainer (noised-label
features, zero-filled tracking columns) at player-GAME grain, strictly as-of, vs a
trailing-10-game Marcel-style baseline. Two paired game-clustered bootstraps: CRPS (the
row's acceptance metric, `verdict_crps`) and pinball (`verdict_pinball`, secondary). NB
GLM head reported alongside the quantile-GBM head; ablation without `starter` included.

CALIBRATION ONLY -- see .claude/rules/no-edge-claims.md. `edge_claimed` is fixed False;
that literal field name is the deliverable's fixed contract, not a claim.
INVARIANTS: no src/kernel/api/intel edits; <=300 LOC; ASCII only; n_jobs=2.
Run: python -m scripts.platformkit.proof_nba.prop_game_model --stats pts,reb,ast \
     --corpora 2023-24,2024-25 --out data/cache/props_game_model/
"""
from __future__ import annotations

import argparse, json, sys, warnings
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from scripts.platformkit.dist_metrics import (  # noqa: E402
    crps_ensemble_rows, interval_coverage)
try:
    import lightgbm as lgb
    _HAVE_LGB = True
except ImportError:  # pragma: no cover
    from sklearn.ensemble import HistGradientBoostingRegressor
    _HAVE_LGB = False
try:
    import statsmodels.api as sm
    from scipy.stats import nbinom
    _HAVE_SM = True
except ImportError:  # pragma: no cover
    _HAVE_SM = False
_NBA = _REPO / "data" / "domains" / "basketball_nba"
_ADV = _REPO / "data" / "player_adv_stats.parquet"
FEATURE_STATS = ("min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "usagepercentage", "trueshootingpercentage")
FEATURE_SET_LABEL = "as-of prior games plus pregame-announced lineup status (starter)"
WINDOWS = (5, 10, 20)
HALFLIFE = 10
TAUS = (0.1, 0.25, 0.5, 0.75, 0.9)
N_BOOT = 2000
EMBARGO_DAYS = 3
RNG_SEED = 13
def load_frame() -> tuple:
    """Player-game rows, min>0, left-joined to advanced stats, sorted chronologically.
    Returns (df, adv_join_match_rate)."""
    box = pd.read_parquet(_NBA / "player_boxscores.parquet")
    adv = pd.read_parquet(_ADV).drop(columns=["game_date"], errors="ignore")
    df = box.merge(adv, on=["player_id", "game_id"], how="left", indicator="_m")
    df = df[df["min"] > 0].copy()
    match_rate = float((df["_m"] == "both").mean())
    df = df.drop(columns=["_m"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["player_id", "date", "game_id"], kind="mergesort").reset_index(drop=True)
    return df, match_rate
def _trail(s: pd.Series, pid: pd.Series, window: Optional[int], halflife: Optional[int]) -> pd.Series:
    """Prior-games-only trailing mean or EWM: shift(1) THEN roll/ewm, per player."""
    g = s.groupby(pid).shift(1).groupby(pid)
    out = g.apply(lambda x: x.ewm(halflife=halflife, min_periods=1).mean()) if halflife \
        else g.rolling(window, min_periods=1).mean()
    out.index = out.index.droplevel(0)
    return out.reindex(s.index)
def build_player_features(df: pd.DataFrame) -> list:
    """As-of trailing/EWM stats + games played + rest days + is_home + starter (pregame-announced, not as-of shifted -- see FEATURE_SET_LABEL). Returns the feature list."""
    for stat in FEATURE_STATS:
        for w in WINDOWS:
            df[f"{stat}_ma{w}"] = _trail(df[stat], df["player_id"], w, None)
        df[f"{stat}_ewm{HALFLIFE}"] = _trail(df[stat], df["player_id"], None, HALFLIFE)
    cols = [f"{s}_ma{w}" for s in FEATURE_STATS for w in WINDOWS] + [f"{s}_ewm{HALFLIFE}" for s in FEATURE_STATS]
    df["games_played"] = df.groupby("player_id").cumcount().astype("float64")
    df["rest_days"] = (df["date"] - df.groupby("player_id")["date"].shift(1)).dt.days.astype("float64")
    df["is_home"] = df["is_home"].astype("float64"); df["starter"] = df["starter"].astype("float64")
    return cols + ["games_played", "rest_days", "is_home", "starter"]
def build_opp_allowed(df: pd.DataFrame, stat: str) -> np.ndarray:
    """Opponent's as-of trailing-10 mean of `stat` allowed (team-game agg, shifted)."""
    tg = df.groupby(["game_id", "date", "team"])[stat].sum().reset_index()
    paired = tg.merge(tg, on="game_id", suffixes=("", "_opp"))
    paired = paired[paired["team"] != paired["team_opp"]].sort_values(["team", "date"], kind="mergesort")
    paired["opp_allowed"] = paired.groupby("team")[f"{stat}_opp"].transform(
        lambda s: s.shift(1).rolling(10, min_periods=1).mean())
    key = paired[["game_id", "team", "opp_allowed"]].rename(columns={"team": "opp"})
    return df[["game_id", "opp"]].merge(key, on=["game_id", "opp"], how="left")["opp_allowed"].to_numpy()
def season_to_date(df: pd.DataFrame, stat: str) -> pd.Series:
    """Second baseline: as-of (prior games only) mean within the current season."""
    key = df["player_id"].astype(str) + "|" + df["season"].astype(str)
    out = df[stat].groupby(key).shift(1).groupby(key).expanding().mean()
    out.index = out.index.droplevel(0)
    return out.reindex(df.index)
def split_corpus(df: pd.DataFrame, test_season: str) -> tuple:
    """Cross-season (prior seasons -> this season, embargoed); within-season 70/30 fallback when no prior season exists in this table (true for 2023-24, the table's first season)."""
    seasons = sorted(df["season"].unique())
    prior = seasons[:seasons.index(test_season)]
    test_df = df[df["season"] == test_season].sort_values("date", kind="mergesort")
    if prior:
        train_df = df[df["season"].isin(prior)].copy()
        cutoff = test_df["date"].min() - pd.Timedelta(days=EMBARGO_DAYS)
        train_df = train_df[train_df["date"] <= cutoff]
        meta = {"split": "cross_season", "prior_seasons": prior}
    else:
        cutoff_date = test_df["date"].iloc[int(len(test_df) * 0.7)]
        train_df = test_df[test_df["date"] < cutoff_date - pd.Timedelta(days=EMBARGO_DAYS)].copy()
        test_df = test_df[test_df["date"] >= cutoff_date].copy()
        meta = {"split": "within_season_fallback",
                "note": "no prior season in table; trained on this season's first ~70pct of dates (embargoed), not a prior season"}
    return train_df.reset_index(drop=True), test_df.reset_index(drop=True), meta
def lgb_quantiles(xtr: pd.DataFrame, ytr: pd.Series, xte: pd.DataFrame) -> np.ndarray:
    preds = np.zeros((len(xte), len(TAUS)))
    for i, tau in enumerate(TAUS):
        m = lgb.LGBMRegressor(objective="quantile", alpha=tau, n_estimators=200, num_leaves=15,
                               min_child_samples=30, n_jobs=2, random_state=RNG_SEED,
                               deterministic=True, force_row_wise=True, verbosity=-1) if _HAVE_LGB else \
            HistGradientBoostingRegressor(loss="quantile", quantile=tau, max_iter=200, random_state=RNG_SEED)
        preds[:, i] = m.fit(xtr, ytr).predict(xte)
    preds.sort(axis=1)
    return preds
def nb_quantiles(xtr: pd.DataFrame, ytr: pd.Series, xte: pd.DataFrame):
    """Negative-binomial GLM (statsmodels nb2, MLE alpha) -> quantiles via scipy nbinom.ppf."""
    if not _HAVE_SM:
        return {"status": "statsmodels_unavailable"}
    try:
        a_tr = np.column_stack([np.ones(len(xtr)), xtr.to_numpy(dtype=float)])
        a_te = np.column_stack([np.ones(len(xte)), xte.to_numpy(dtype=float)])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = sm.NegativeBinomial(ytr.to_numpy(dtype=float), a_tr, loglike_method="nb2").fit(disp=0, maxiter=200, method="bfgs")
        mu = np.clip(res.predict(a_te), 1e-6, None)
        n_param = 1.0 / max(float(res.params[-1]), 1e-6); p_param = n_param / (n_param + mu)
        preds = np.stack([nbinom.ppf(t, n_param, p_param) for t in TAUS], axis=1).astype(float)
        preds.sort(axis=1)
        return preds
    except Exception as exc:  # noqa: BLE001 -- head is best-effort, error passed through honestly
        return {"status": "fit_failed", "error": str(exc)[:200]}
def baseline_quantiles(train_df: pd.DataFrame, test_df: pd.DataFrame, stat: str) -> np.ndarray:
    """Trailing-10-game mean + empirical train residual quantiles (Marcel-style)."""
    ma_col = f"{stat}_ma10"
    resid = (train_df[stat] - train_df[ma_col]).dropna().to_numpy()
    qs = np.quantile(resid if len(resid) else np.array([0.0]), TAUS)
    base = test_df[ma_col].fillna(train_df[stat].mean()).to_numpy()
    preds = base[:, None] + qs[None, :]
    preds.sort(axis=1)
    return preds
def _pinball_rows(y: np.ndarray, q_pred: np.ndarray) -> np.ndarray:
    diff = y[:, None] - q_pred
    taus = np.array(TAUS)[None, :]
    return np.where(diff >= 0, taus * diff, (taus - 1.0) * diff).mean(axis=1)
def score_quantiles(y: np.ndarray, q_pred) -> Optional[dict]:
    """Report-only: pinball avg, CRPS approx (dist_metrics, quantiles as pseudo-samples), 10-90 coverage, MAE of the median -- over ONE shared finite mask; n_scored recorded."""
    if not isinstance(q_pred, np.ndarray):
        return None
    mask = np.isfinite(y) & np.isfinite(q_pred).all(axis=1); ym, qm = y[mask], q_pred[mask]
    if len(ym) == 0:
        return {"pinball_avg": float("nan"), "crps_approx": float("nan"), "coverage_10_90": float("nan"),
                "mae_median": float("nan"), "n_scored": 0}
    return {"pinball_avg": float(_pinball_rows(ym, qm).mean()),
            "crps_approx": float(np.nanmean(crps_ensemble_rows(ym, qm))),
            "coverage_10_90": interval_coverage(ym, qm[:, 0], qm[:, -1])["coverage"],
            "mae_median": float(np.mean(np.abs(ym - qm[:, len(TAUS) // 2]))), "n_scored": int(mask.sum())}
def clustered_ci(row_delta: np.ndarray, game_ids: np.ndarray) -> dict:
    """Game-clustered bootstrap CI on mean(baseline_loss - model_loss); >0 = model better. Metric-agnostic: caller passes pinball-row or CRPS-row deltas."""
    s = pd.Series(row_delta)
    sum_g, cnt_g = s.groupby(game_ids).sum().to_numpy(), s.groupby(game_ids).count().to_numpy()
    rng = np.random.default_rng(RNG_SEED)
    n_g = len(sum_g)
    means = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx = rng.integers(0, n_g, n_g)
        means[b] = sum_g[idx].sum() / cnt_g[idx].sum()
    lo, hi = np.percentile(means, [2.5, 97.5])
    point = float(sum_g.sum() / cnt_g.sum())
    verdict = "AHEAD" if lo > 0 else ("BEHIND" if hi < 0 else "UNDERPOWERED")
    return {"point": point, "ci_lo": float(lo), "ci_hi": float(hi), "verdict": verdict}
def _delta_ci(y: np.ndarray, q_base: np.ndarray, q_model: np.ndarray, gids: np.ndarray, rowfn) -> dict:
    """Shared finite mask over (y, q_base, q_model) -> clustered_ci(baseline_row - model_row)."""
    m = np.isfinite(y) & np.isfinite(q_base).all(1) & np.isfinite(q_model).all(1)
    return clustered_ci(rowfn(y[m], q_base[m]) - rowfn(y[m], q_model[m]), gids[m])
def _rd(ci: dict) -> dict:
    return {"point": round(ci["point"], 5), "ci_lo": round(ci["ci_lo"], 5), "ci_hi": round(ci["ci_hi"], 5)}
def secondary_tscv(df: pd.DataFrame, cols: list, stat: str, test_season: str) -> Optional[dict]:
    """Secondary view: within-season expanding TimeSeriesSplit(4) on UNIQUE DATES (not rows), LightGBM pinball only."""
    from sklearn.model_selection import TimeSeriesSplit
    sdf = df[df["season"] == test_season].sort_values("date", kind="mergesort").reset_index(drop=True)
    if len(sdf) < 400:
        return None
    fcols = cols + [f"opp_allowed_{stat}_10"]
    dates = np.sort(sdf["date"].unique())
    losses = []
    for tr_d, te_d in TimeSeriesSplit(n_splits=4).split(dates):
        tr, te = sdf[sdf["date"].isin(dates[tr_d])], sdf[sdf["date"].isin(dates[te_d])]
        med = tr[fcols].median()
        q = lgb_quantiles(tr[fcols].fillna(med).fillna(0.0), tr[stat].astype(float),
                           te[fcols].fillna(med).fillna(0.0))
        losses.append(float(_pinball_rows(te[stat].astype(float).to_numpy(), q).mean()))
    return {"n_splits": 4, "fold_pinball_avg": losses, "mean_pinball_avg": float(np.mean(losses))}
def run_stat(df: pd.DataFrame, cols: list, stat: str, corpus: str) -> dict:
    train_df, test_df, split_meta = split_corpus(df, corpus)
    if len(train_df) < 200 or len(test_df) < 50:
        return {"stat": stat, "corpus": corpus, "status": "UNDERPOWERED_DATA",
                "n_train": int(len(train_df)), "n_test": int(len(test_df)),
                "edge_claimed": False, **split_meta}
    fcols = cols + [f"opp_allowed_{stat}_10"]
    med = train_df[fcols].median()
    xtr, xte = train_df[fcols].fillna(med).fillna(0.0), test_df[fcols].fillna(med).fillna(0.0)
    ytr, yte = train_df[stat].astype(float), test_df[stat].astype(float).to_numpy()
    game_ids = test_df["game_id"].to_numpy()
    imputed_share = float(test_df[fcols].isna().any(axis=1).mean())
    q_model = lgb_quantiles(xtr, ytr, xte)
    q_base = baseline_quantiles(train_df, test_df, stat)
    q_nb = nb_quantiles(xtr, ytr, xte)
    ci_pb = _delta_ci(yte, q_base, q_model, game_ids, _pinball_rows)
    ci_crps = _delta_ci(yte, q_base, q_model, game_ids, crps_ensemble_rows)
    fcols_ns = [c for c in fcols if c != "starter"]  # ablation: drop pregame lineup status
    med_ns = train_df[fcols_ns].median()
    q_model_ns = lgb_quantiles(train_df[fcols_ns].fillna(med_ns).fillna(0.0), ytr, test_df[fcols_ns].fillna(med_ns).fillna(0.0))
    ci_pb_ns = _delta_ci(yte, q_base, q_model_ns, game_ids, _pinball_rows)
    std_pred = test_df[f"{stat}_std"].fillna(train_df[stat].mean()).to_numpy()
    s_nb = score_quantiles(yte, q_nb) if isinstance(q_nb, np.ndarray) else q_nb
    return {
        "stat": stat, "corpus": corpus, "status": "OK",
        "n_train": int(len(train_df)), "n_test": int(len(test_df)),
        "n_games_test": int(pd.unique(game_ids).size), "n_players_test": int(test_df["player_id"].nunique()),
        **split_meta, "imputed_share": round(imputed_share, 4),
        "lightgbm_quantile": score_quantiles(yte, q_model),
        "baseline_trailing10_marcel": score_quantiles(yte, q_base),
        "negbinom_glm": s_nb,
        "baseline_season_to_date_mae": round(float(np.mean(np.abs(yte - std_pred))), 4),
        "delta_baseline_minus_model_pinball": {"positive_means_model_better": True, **_rd(ci_pb)},
        "delta_baseline_minus_model_crps": {"positive_means_model_better": True, **_rd(ci_crps)},
        "verdict_crps": ci_crps["verdict"], "verdict_pinball": ci_pb["verdict"],
        "ablation_no_starter": {"feature_set": "as_of_prior_games_only_no_pregame_lineup",
                                 "delta_pinball": _rd(ci_pb_ns), "verdict": ci_pb_ns["verdict"]},
        "secondary_within_season_tscv": secondary_tscv(df, cols, stat, corpus),
        "edge_claimed": False,
    }
def _cov(d) -> str:
    return f"{d['coverage_10_90']:.3f}" if isinstance(d, dict) and "coverage_10_90" in d else "NA"
def markdown_table(results: list) -> str:
    ok = [r for r in results if r["status"] == "OK"]
    cap = []
    if results:
        cap.append(f"split: {results[0].get('split', '?')} | baseline = trailing-10-game mean, not a market line; calibration only")
    if ok:
        cap.append("coverage(0.1-0.9): " + " | ".join(
            f"{r['stat']}: lgb={_cov(r['lightgbm_quantile'])} base={_cov(r['baseline_trailing10_marcel'])} nb={_cov(r['negbinom_glm'])}"
            for r in ok))
    lines = cap + ["", "| stat | n_test | verdict_crps | verdict_pinball | model_pinball | "
                    "baseline_pinball | delta_pinball_ci |", "|---|---|---|---|---|---|---|"]
    for r in results:
        if r["status"] != "OK":
            lines.append(f"| {r['stat']} | {r.get('n_test', 0)} | {r['status']} | - | - | - | - |")
            continue
        d = r["delta_baseline_minus_model_pinball"]
        lines.append(f"| {r['stat']} | {r['n_test']} | {r['verdict_crps']} | {r['verdict_pinball']} | "
                      f"{r['lightgbm_quantile']['pinball_avg']:.4f} | "
                      f"{r['baseline_trailing10_marcel']['pinball_avg']:.4f} | "
                      f"{d['point']:.4f} [{d['ci_lo']:.4f}, {d['ci_hi']:.4f}] |")
    return "\n".join(lines)
def run(stats: list, corpora: list, out_dir: Path) -> dict:
    df, adv_join_match_rate = load_frame()
    cols = build_player_features(df)
    for stat in stats:
        df[f"opp_allowed_{stat}_10"] = build_opp_allowed(df, stat)
        df[f"{stat}_std"] = season_to_date(df, stat)
    out_dir.mkdir(parents=True, exist_ok=True)
    import sklearn  # noqa: E402
    lib_versions = {"pandas": pd.__version__, "numpy": np.__version__, "sklearn": sklearn.__version__,
                     "lightgbm": lgb.__version__ if _HAVE_LGB else "not_installed_used_hgb_fallback",
                     "statsmodels": sm.__version__ if _HAVE_SM else "not_installed"}
    acceptance = {"met": False, "reasons": [
        f"{len(stats)} of 7 target stats covered this run (need >=5 for the row's acceptance rule)",
        "nightly train/inference byte-identity fixture not built"]}
    artifacts = {}
    for corpus in corpora:
        results = [run_stat(df, cols, stat, corpus) for stat in stats]
        cdf = df[df["season"] == corpus]
        artifact = {
            "corpus": corpus, "n_rows_total": int(len(cdf)), "n_games_total": int(cdf["game_id"].nunique()),
            "n_players_total": int(cdf["player_id"].nunique()), "feature_list": cols, "taus": list(TAUS),
            "feature_set_label": FEATURE_SET_LABEL, "adv_join_match_rate": round(adv_join_match_rate, 4),
            "n_boot": N_BOOT, "library_versions": lib_versions, "acceptance_rule_met": acceptance,
            "results": results, "markdown_summary": markdown_table(results), "edge_claimed": False,
        }
        path = out_dir / f"prop_game_model_{corpus.replace('-', '_')}.json"
        path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8"); artifacts[corpus] = artifact
        print(f"=== {corpus} ===\n{artifact['markdown_summary']}\nwrote {path}")
    return artifacts
def _main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--stats", default="pts,reb,ast"); p.add_argument("--corpora", default="2023-24,2024-25")
    p.add_argument("--out", default="data/cache/props_game_model/")
    args = p.parse_args()
    run([s.strip() for s in args.stats.split(",") if s.strip()],
        [c.strip() for c in args.corpora.split(",") if c.strip()], Path(args.out))
    return 0
if __name__ == "__main__":
    sys.exit(_main())
