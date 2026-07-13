"""scripts.platformkit.models.gbm_nba_ml -- GBM challenger for (nba, ml): predict home-win
probability from leak-free pregame-knowable features, benchmarked vs the devigged close.

REUSES the existing NBA ml corpus join + walk-forward Elo/pace machinery
(proof_nba.ml_accuracy, proof_nba.asof_box_accuracy) instead of reimplementing it. The market
close is the BENCHMARK ONLY -- p_market is never fed into the model as a feature.

Features (all pregame-knowable; walk-forward state built ONLY from games strictly BEFORE the
game being predicted -- no post-game box stats from the current game are used; see
test_gbm_nba_ml.test_leak_trap):
  elo_home, elo_away, elo_diff               -- MOV-aware Elo (ml_accuracy's update rule)
  pace_home, pace_away                        -- EW possessions/game
  offp_home, defp_home, offp_away, defp_away  -- EW points/possession
  rest_home, rest_away                        -- days since each team's last game (cap 10)
  b2b_home, b2b_away                          -- back-to-back flag (rest <= 1)
  l10_wpct_home, l10_wpct_away                -- trailing-10-game win rate (0.5 if unseen)
No injury-count feature: this corpus's espn_boxscores/odds parquets carry no injury data.

Folds: the odds corpus covers only ONE NBA season's overlap (all 743 matched games fall in
the 2025-26 season; the 2024-25 season box games have no market close) -- the brief's
">=2 held-out seasons" is not supported by this corpus today. Documented as
`season_coverage_note` below; substituted with 4 chronological expanding-window folds WITHIN
the covered season (train = all box history strictly before the fold's test window, test =
that window) -- genuinely walk-forward, just not season-granular.

Hyperparams: a fixed grid of 6 (max_depth, n_estimators) configs, selected ONCE via an inner
chronological 80/20 split carved out of the pre-fold-0 training pool only (never touches any
held-out test fold), then locked for all folds.

Run: python -m scripts.platformkit.models.gbm_nba_ml
"""
from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.proof_nba.ml_accuracy import (  # noqa: E402
    _HFA, _INIT, _K, _p_home, american_to_prob)
from scripts.platformkit.proof_nba.asof_box_accuracy import (  # noqa: E402
    _NBA, _possessions, load_box)
from scripts.platformkit.benchmarks.crps_market.run_mlb import _bootstrap_ci  # noqa: E402

_PACE0, _PPP0 = 100.5, 1.13
_FEATURES = [
    "elo_home", "elo_away", "elo_diff", "pace_home", "pace_away",
    "offp_home", "defp_home", "offp_away", "defp_away",
    "rest_home", "rest_away", "b2b_home", "b2b_away",
    "l10_wpct_home", "l10_wpct_away",
]
_GRID = [  # <=6 fixed configs; selected on TRAIN folds only, see _select_hyperparams
    {"max_depth": 2, "n_estimators": 100},
    {"max_depth": 2, "n_estimators": 300},
    {"max_depth": 3, "n_estimators": 100},
    {"max_depth": 3, "n_estimators": 300},
    {"max_depth": 4, "n_estimators": 100},
    {"max_depth": 4, "n_estimators": 300},
]
_SEED = 0
_ARTIFACT = _REPO / "data" / "domains" / "nba" / "gbm_ml_benchmark.json"
_MODEL_OUT = _REPO / "data" / "models" / "nba_ml_gbm.json"


def build_features(box: pd.DataFrame) -> pd.DataFrame:
    """One leak-free walk-forward pass over the full box corpus. Row i's features depend
    only on games strictly before i; game i's own outcome/box stats never leak into row i."""
    elo: Dict[str, float] = {}; pace: Dict[str, float] = {}
    offp: Dict[str, float] = {}; defp: Dict[str, float] = {}
    last_date: Dict[str, pd.Timestamp] = {}
    form: Dict[str, deque] = {}
    h = box["home_abbr"].to_numpy(); a = box["away_abbr"].to_numpy()
    hp = box["home_pts"].to_numpy(float); ap = box["away_pts"].to_numpy(float)
    dates = pd.to_datetime(box["date"]).to_numpy()
    gp = 0.5 * (_possessions(box, "home") + _possessions(box, "away"))
    rows: List[dict] = []
    for i in range(len(box)):
        ht, at = str(h[i]), str(a[i])
        for t in (ht, at):
            elo.setdefault(t, _INIT); pace.setdefault(t, _PACE0)
            offp.setdefault(t, _PPP0); defp.setdefault(t, _PPP0)
            form.setdefault(t, deque(maxlen=10))
        d = pd.Timestamp(dates[i])
        rest_h = min(float((d - last_date[ht]).days), 10.0) if ht in last_date else 10.0
        rest_a = min(float((d - last_date[at]).days), 10.0) if at in last_date else 10.0
        rows.append({
            "date": d, "home_abbr": ht, "away_abbr": at,
            "elo_home": elo[ht], "elo_away": elo[at], "elo_diff": elo[ht] - elo[at],
            "pace_home": pace[ht], "pace_away": pace[at],
            "offp_home": offp[ht], "defp_home": defp[ht],
            "offp_away": offp[at], "defp_away": defp[at],
            "rest_home": rest_h, "rest_away": rest_a,
            "b2b_home": float(rest_h <= 1), "b2b_away": float(rest_a <= 1),
            "l10_wpct_home": (sum(form[ht]) / len(form[ht])) if form[ht] else 0.5,
            "l10_wpct_away": (sum(form[at]) / len(form[at])) if form[at] else 0.5,
            "home_win": 1.0 if hp[i] > ap[i] else 0.0,
        })
        s = rows[-1]["home_win"]
        ph = _p_home(elo[ht], elo[at])
        elo_diff_signed = (elo[ht] - elo[at] + _HFA) * (1 if s else -1)
        mov = np.log(abs(hp[i] - ap[i]) + 1.0) * (2.2 / (elo_diff_signed * 0.001 + 2.2))
        delta = _K * mov * (s - ph)
        elo[ht] += delta; elo[at] -= delta
        p = gp[i]
        if np.isfinite(p) and p > 50:
            al = 0.05
            pace[ht] += al * (p - pace[ht]); pace[at] += al * (p - pace[at])
            offp[ht] += al * (hp[i] / p - offp[ht]); defp[ht] += al * (ap[i] / p - defp[ht])
            offp[at] += al * (ap[i] / p - offp[at]); defp[at] += al * (hp[i] / p - defp[at])
        form[ht].append(s); form[at].append(1.0 - s)
        last_date[ht] = d; last_date[at] = d
    return pd.DataFrame(rows)


def join_market(feat: pd.DataFrame, root: Path) -> pd.DataFrame:
    """Inner-join the walk-forward feature rows to the devigged market close (benchmark only,
    never a feature)."""
    raw = pd.read_parquet(root / "odds.parquet").rename(
        columns={"home_team": "home_abbr", "away_team": "away_abbr"})
    raw["date"] = pd.to_datetime(raw["date"])
    raw = raw.dropna(subset=["home_ml", "away_ml"])
    raw["imp_h"] = raw["home_ml"].map(american_to_prob)
    raw["imp_a"] = raw["away_ml"].map(american_to_prob)
    raw["p_market"] = raw["imp_h"] / (raw["imp_h"] + raw["imp_a"])
    m = feat.merge(raw[["date", "home_abbr", "away_abbr", "p_market"]],
                    on=["date", "home_abbr", "away_abbr"], how="inner")
    return m.sort_values("date").reset_index(drop=True)


def make_folds(feat: pd.DataFrame, m: pd.DataFrame, k: int = 4) -> List[Tuple[pd.Series, int, int]]:
    """K chronological expanding-window folds over the market-overlap sample m. Returns
    (train_mask_into_feat, test_lo, test_hi) tuples; skips folds with <30 test games."""
    n = len(m)
    edges = [int(round(i * n / k)) for i in range(k + 1)]
    folds = []
    for j in range(k):
        lo, hi = edges[j], edges[j + 1]
        if hi - lo < 30:
            continue
        test_start = m["date"].iloc[lo]
        folds.append((feat["date"] < test_start, lo, hi))
    return folds


def _fit(X: pd.DataFrame, y: pd.Series, params: dict, seed: int = _SEED):
    from xgboost import XGBClassifier
    try:
        m = XGBClassifier(tree_method="hist", device="cuda", random_state=seed,
                           eval_metric="logloss", **params)
        m.fit(X, y)
        return m, "cuda"
    except Exception:  # noqa: BLE001 -- GPU unavailable/errored, fall back to CPU hist
        m = XGBClassifier(tree_method="hist", random_state=seed,
                           eval_metric="logloss", **params)
        m.fit(X, y)
        return m, "hist(cpu)"


def _select_hyperparams(feat: pd.DataFrame, pool_mask: pd.Series) -> Tuple[dict, str]:
    """Grid search on the TRAIN pool only: inner chronological 80/20 split, pick the config
    with the lowest logloss on the inner validation slice. Never touches a held-out fold."""
    pool = feat.loc[pool_mask].reset_index(drop=True)
    cut = int(len(pool) * 0.8)
    tr, va = pool.iloc[:cut], pool.iloc[cut:]
    best, best_ll = _GRID[0], float("inf")
    for cfg in _GRID:
        model, _ = _fit(tr[_FEATURES], tr["home_win"], cfg)
        p = np.clip(model.predict_proba(va[_FEATURES])[:, 1], 1e-6, 1 - 1e-6)
        y = va["home_win"].to_numpy()
        ll = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
        if ll < best_ll:
            best_ll, best = ll, cfg
    return best, f"inner 80/20 split on {len(pool)} pre-fold-0 train games, best logloss={round(best_ll, 4)}"


def run(corpus: Path = None) -> Dict:
    root = corpus or _NBA
    box = load_box(root)
    feat = build_features(box)
    m = join_market(feat, root)
    n = len(m)
    if n < 120:
        return {"status": "data_limited", "n_overlap": n, "edge_claimed": False}

    folds = make_folds(feat, m, k=4)
    params, select_note = _select_hyperparams(feat, folds[0][0])

    fold_reports, gbm_p, mkt_p, elo_p, y_all, device_used, models = [], [], [], [], [], None, []
    for j, (train_mask, lo, hi) in enumerate(folds):
        tr = feat.loc[train_mask]
        te = m.iloc[lo:hi]
        model, device_used = _fit(tr[_FEATURES], tr["home_win"], params)
        models.append(model)
        p_gbm = np.clip(model.predict_proba(te[_FEATURES])[:, 1], 1e-6, 1 - 1e-6)
        p_mkt = te["p_market"].to_numpy(float)
        p_elo = np.array([_p_home(r.elo_home, r.elo_away) for r in te.itertuples()])
        y = te["home_win"].to_numpy(float)
        gbm_p.extend(p_gbm); mkt_p.extend(p_mkt); elo_p.extend(p_elo); y_all.extend(y)
        fold_reports.append({
            "fold": j, "n_train": int(train_mask.sum()), "n_test": int(hi - lo),
            "test_start": str(te["date"].iloc[0].date()), "test_end": str(te["date"].iloc[-1].date()),
            "brier_gbm": round(float(np.mean((p_gbm - y) ** 2)), 4),
            "brier_close": round(float(np.mean((p_mkt - y) ** 2)), 4),
        })

    gbm_p, mkt_p, elo_p, y_all = map(np.array, (gbm_p, mkt_p, elo_p, y_all))
    brier_gbm = float(np.mean((gbm_p - y_all) ** 2))
    brier_close = float(np.mean((mkt_p - y_all) ** 2))
    brier_elo = float(np.mean((elo_p - y_all) ** 2))
    ll_gbm = float(-np.mean(y_all * np.log(gbm_p) + (1 - y_all) * np.log(1 - gbm_p)))
    ll_close = float(-np.mean(y_all * np.log(mkt_p) + (1 - y_all) * np.log(1 - mkt_p)))
    ll_elo = float(-np.mean(y_all * np.log(elo_p) + (1 - y_all) * np.log(1 - elo_p)))
    delta = (gbm_p - y_all) ** 2 - (mkt_p - y_all) ** 2   # <0 => GBM sharper this game
    ci = [round(v, 4) for v in _bootstrap_ci(delta)]
    if ci[1] < 0:
        verdict = f"SHARPER: GBM beats the close outside noise (delta {round(float(delta.mean()),4)} CI{ci})"
    elif ci[0] > 0:
        verdict = f"TRAILS: close beats GBM outside noise (delta {round(float(delta.mean()),4)} CI{ci})"
    else:
        verdict = f"MATCHES: CI crosses zero, not distinguishable from the close (delta {round(float(delta.mean()),4)} CI{ci})"

    # feature-importance snapshot: average gain across the fold models
    gains: Dict[str, float] = {f: 0.0 for f in _FEATURES}
    for model in models:
        sc = model.get_booster().get_score(importance_type="gain")
        for f, v in sc.items():
            gains[f] = gains.get(f, 0.0) + v / len(models)
    top10 = sorted(gains.items(), key=lambda kv: -kv[1])[:10]

    # final model trained on ALL available feature rows, locked hyperparams, saved for reuse
    final_model, _ = _fit(feat[_FEATURES], feat["home_win"], params)
    _MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    final_model.save_model(str(_MODEL_OUT))

    return {
        "status": "ok", "edge_claimed": False,
        "features": _FEATURES,
        "hyperparams_grid": _GRID, "chosen_hyperparams": params,
        "hyperparam_selection_note": select_note,
        "device_used": device_used,
        "season_coverage_note": (
            "odds corpus covers only the 2025-26 season overlap (n_overlap="
            f"{n}); 2024-25 box games have no market close, so folds are 4 chronological "
            "expanding windows WITHIN the covered season, not >=2 held-out seasons."),
        "folds": fold_reports, "n_games_per_fold": [f["n_test"] for f in fold_reports],
        "n_overlap": n,
        "brier_gbm": round(brier_gbm, 4), "brier_close": round(brier_close, 4),
        "brier_existing_model": round(brier_elo, 4),
        "logloss_gbm": round(ll_gbm, 4), "logloss_close": round(ll_close, 4),
        "logloss_existing_model": round(ll_elo, 4),
        "paired_delta_gbm_vs_close_mean": round(float(delta.mean()), 4),
        "paired_delta_gbm_vs_close_95ci": ci,
        "verdict": verdict,
        "top10_gain_features": [[f, round(v, 2)] for f, v in top10],
        "model_artifact": str(_MODEL_OUT.relative_to(_REPO)).replace("\\", "/"),
        "honest_note": ("Pregame-only leak-free features (no market inputs); benchmarked "
                         "vs the devigged close on real held-out outcomes. Calibration/"
                         "sharpness comparison only. No $ edge claimed."),
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n_overlap={rep.get('n_overlap')}"); return 0
    _ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    _ARTIFACT.write_text(json.dumps(rep, indent=2))
    print(f"=== NBA moneyline: GBM challenger vs devigged close (n={rep['n_overlap']}, "
          f"device={rep['device_used']}) ===")
    print(f"  {'predictor':>16}  {'Brier':>8} {'LogLoss':>8}")
    print(f"  {'devig close':>16}  {rep['brier_close']:>8} {rep['logloss_close']:>8}")
    print(f"  {'existing (elo)':>16}  {rep['brier_existing_model']:>8} {rep['logloss_existing_model']:>8}")
    print(f"  {'GBM challenger':>16}  {rep['brier_gbm']:>8} {rep['logloss_gbm']:>8}")
    print(f"\nVERDICT: {rep['verdict']}")
    print(f"top-10 gain features: {rep['top10_gain_features']}")
    print(f"artifact -> {_ARTIFACT}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
