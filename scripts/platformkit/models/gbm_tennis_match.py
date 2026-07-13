"""scripts.platformkit.models.gbm_tennis_match -- GBM challenger for (tennis, match): predicts
P(p1 wins) [p1 = lower player_id, symmetric non-outcome ordering] from leak-free pregame features,
benchmarked vs the devigged Pinnacle close and the elo_platt challenger (domains.tennis.elo_tune /
proof_tennis.beat_the_close_ml[_wta], both REUSED not reimplemented: _walk_forward_blend for Elo,
_devig_market for the close). Trains ATP+WTA JOINTLY with an is_wta flag (tour heterogeneity is
real -- see surface_hold_gate_verdict.json) but always reports/verdicts per tour. p_market is the
benchmark only, never a feature.

Features (all pregame-knowable, as-of; see test_leak_trap_*): elo_diff/surface_elo_diff (walk-
forward blended Elo), hold_pct_diff/hold_pct_surf_diff (serve-hold rate asof, overall + this
match's surface), svpts_won_diff (serve-points-won rate asof -- stands in for ace/return-rate on
BOTH tours since a true return-rate asof column exists for ATP only in this corpus), rank_diff
(log1p rank, not ranking points -- not in this corpus; unranked filled at 500), best_of, is_wta,
surf_hard/clay/grass one-hot.

LEAK GUARD: p1 is always the lower player_id, independent of who won. hold_pct/svpts_won come from
asof_hold[_wta].parquet (as-of by construction). build_features never reads the current row's own
winner/score for anything but the p1_win label.

Folds: 4 chronological expanding folds by year; the FINAL fold (train<=2022, test>2022) matches
beat_the_close_ml[_wta]'s own TRAIN_YEAR_MAX=2022 split, so the vs_elo_platt section compares
GBM/close/elo_platt on the identical held-out population. Hyperparams: fixed 6-config grid, chosen
ONCE via an inner 80/20 split on the pre-fold-0 pool (year<=2018), never touching a test fold.

GPU: one job, xgboost hist/device=cuda, falls back to hist(cpu) on error (see _fit). No market
feature. No $ edge claimed (edge_claimed=False everywhere).

Run: python -m scripts.platformkit.models.gbm_tennis_match
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.tennis.elo_core import SURFACE_BLEND  # noqa: E402
from domains.tennis.elo_tune import _walk_forward_blend  # noqa: E402
from scripts.platformkit.proof_tennis.beat_the_close_ml import _devig_market  # noqa: E402
from scripts.platformkit.proof_tennis import beat_the_close_ml as _atp_close  # noqa: E402
from scripts.platformkit.proof_tennis import beat_the_close_ml_wta as _wta_close  # noqa: E402
from scripts.platformkit.benchmarks.crps_market.run_mlb import _bootstrap_ci  # noqa: E402

_TENNIS = _REPO / "data" / "domains" / "tennis"
_ARTIFACT = _REPO / "data" / "domains" / "tennis" / "gbm_match_benchmark.json"
_MODEL_OUT = _REPO / "data" / "models" / "tennis_match_gbm.json"

_SURFACES = ("Hard", "Clay", "Grass")  # Carpet/other -> hold_pct_surf_diff stays 0, one-hots 0
_FEATURES = [
    "elo_diff", "surface_elo_diff", "hold_pct_diff", "hold_pct_surf_diff", "svpts_won_diff",
    "rank_diff", "best_of", "is_wta", "surf_hard", "surf_clay", "surf_grass",
]
_GRID = [  # <=6 fixed configs; selected on TRAIN pool only, see _select_hyperparams
    {"max_depth": 2, "n_estimators": 100}, {"max_depth": 2, "n_estimators": 300},
    {"max_depth": 3, "n_estimators": 100}, {"max_depth": 3, "n_estimators": 300},
    {"max_depth": 4, "n_estimators": 100}, {"max_depth": 4, "n_estimators": 300},
]
_SEED = 0
_RANK_FILL = 500.0  # unranked-player placeholder
# (train_max_year, test_year_lo, test_year_hi=9999 means "and beyond"); final fold matches
# beat_the_close_ml's TRAIN_YEAR_MAX=2022.
_FOLD_EDGES: List[Tuple[int, int, int]] = [
    (2018, 2019, 2019), (2019, 2020, 2021), (2021, 2022, 2022), (2022, 2023, 9999),
]


def build_features(matches: pd.DataFrame, asof_hold: pd.DataFrame, is_wta: float) -> pd.DataFrame:
    """Leak-free walk-forward feature frame for one tour."""
    wf = _walk_forward_blend(matches, blend=SURFACE_BLEND)
    hold_cols = ["event_id", "p1_hold_pct_asof", "p2_hold_pct_asof", "p1_svpts_won_asof",
                 "p2_svpts_won_asof"] + [f"p{p}_hold_pct_{s.lower()}_asof" for s in _SURFACES for p in (1, 2)]
    m = wf.merge(asof_hold[hold_cols], on="event_id", how="left")

    surf = m["surface"].fillna("Unknown")
    surf_hold_diff = pd.Series(np.nan, index=m.index, dtype=float)
    for s in _SURFACES:
        mask = (surf == s).to_numpy()
        surf_hold_diff.loc[mask] = (m.loc[mask, f"p1_hold_pct_{s.lower()}_asof"]
                                     - m.loc[mask, f"p2_hold_pct_{s.lower()}_asof"])

    p1_rank = m["p1_rank"].fillna(_RANK_FILL)
    p2_rank = m["p2_rank"].fillna(_RANK_FILL)

    return pd.DataFrame({
        "event_id": m["event_id"], "date": pd.to_datetime(m["date"]),
        "elo_diff": m["p1_elo"] - m["p2_elo"],
        "surface_elo_diff": m["p1_surface_elo"] - m["p2_surface_elo"],
        "hold_pct_diff": (m["p1_hold_pct_asof"] - m["p2_hold_pct_asof"]).fillna(0.0),
        "hold_pct_surf_diff": surf_hold_diff.fillna(0.0),
        "svpts_won_diff": (m["p1_svpts_won_asof"] - m["p2_svpts_won_asof"]).fillna(0.0),
        "rank_diff": np.log1p(p2_rank) - np.log1p(p1_rank),
        "best_of": m["best_of"].astype(float),
        "is_wta": float(is_wta),
        "surf_hard": (surf == "Hard").astype(float),
        "surf_clay": (surf == "Clay").astype(float),
        "surf_grass": (surf == "Grass").astype(float),
        "p1_win": (m["winner"] == 1).astype(float),
    })


def join_market(feat: pd.DataFrame, odds: pd.DataFrame) -> pd.DataFrame:
    """Inner-join to the devigged Pinnacle close (benchmark only, never a feature)."""
    mkt = _devig_market(odds)
    m = feat.merge(mkt, on="event_id", how="inner")
    return m.dropna(subset=["p_market"]).sort_values("date").reset_index(drop=True)


def make_folds(feat: pd.DataFrame, m: pd.DataFrame) -> List[Dict]:
    """4 chronological expanding folds; train mask indexes into feat (broader pool),
    test mask indexes into m (market-overlap only). Skips folds with <30 test rows."""
    years_feat = feat["date"].dt.year
    years_m = m["date"].dt.year
    folds = []
    for train_max, lo, hi in _FOLD_EDGES:
        train_mask = years_feat <= train_max
        test_mask = (years_m >= lo) & (years_m <= hi)
        if int(test_mask.sum()) < 30:
            continue
        folds.append({"train_mask": train_mask, "test_mask": test_mask,
                       "train_max_year": train_max, "test_year_lo": lo,
                       "test_year_hi": None if hi >= 9999 else hi})
    return folds


def _fit(X: pd.DataFrame, y: pd.Series, params: dict, seed: int = _SEED):
    from xgboost import XGBClassifier
    try:
        model = XGBClassifier(tree_method="hist", device="cuda", random_state=seed,
                               eval_metric="logloss", **params)
        model.fit(X, y)
        return model, "cuda"
    except Exception:  # noqa: BLE001 -- GPU unavailable/errored, fall back to CPU hist
        model = XGBClassifier(tree_method="hist", random_state=seed,
                               eval_metric="logloss", **params)
        model.fit(X, y)
        return model, "hist(cpu)"


def _select_hyperparams(feat: pd.DataFrame, pool_mask: pd.Series) -> Tuple[dict, str]:
    """Inner chronological 80/20 split on the pre-fold-0 pool only; never touches a test fold."""
    pool = feat.loc[pool_mask].sort_values("date").reset_index(drop=True)
    cut = int(len(pool) * 0.8)
    tr, va = pool.iloc[:cut], pool.iloc[cut:]
    best, best_ll = _GRID[0], float("inf")
    for cfg in _GRID:
        model, _ = _fit(tr[_FEATURES], tr["p1_win"], cfg)
        p = np.clip(model.predict_proba(va[_FEATURES])[:, 1], 1e-6, 1 - 1e-6)
        y = va["p1_win"].to_numpy()
        ll = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
        if ll < best_ll:
            best_ll, best = ll, cfg
    return best, f"inner 80/20 split on {len(pool)} pre-fold-0 rows (year<=2018), best logloss={round(best_ll, 4)}"


def _score(p: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return (float(np.mean((p - y) ** 2)),
            float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))))


def _verdict(delta: np.ndarray) -> Tuple[str, List[float]]:
    ci = [round(v, 4) for v in _bootstrap_ci(delta)]
    if ci[1] < 0:
        return f"SHARPER: GBM beats the close outside noise (delta {round(float(delta.mean()), 4)} CI{ci})", ci
    if ci[0] > 0:
        return f"TRAILS: close beats GBM outside noise (delta {round(float(delta.mean()), 4)} CI{ci})", ci
    return f"MATCHES: CI crosses zero, not distinguishable from the close (delta {round(float(delta.mean()), 4)} CI{ci})", ci


def _matched_fold(gbm_final, y_final, tourv_final, tour_val: float, elo_rep: Dict) -> Dict:
    mask = tourv_final == tour_val
    return {"gbm_final_fold": {"n": int(mask.sum()),
                                "brier_gbm": round(_score(gbm_final[mask], y_final[mask])[0], 4)},
            "elo_platt_reference": {"n": elo_rep.get("n"), "brier": elo_rep.get("model_metric"),
                                     "logloss": elo_rep.get("model_logloss"), "verdict": elo_rep.get("verdict")}}


def _tour_report(gbm_p, mkt_p, y, tag: str) -> Dict:
    b_gbm, ll_gbm = _score(gbm_p, y)
    b_mkt, ll_mkt = _score(mkt_p, y)
    delta = (np.clip(gbm_p, 1e-6, 1 - 1e-6) - y) ** 2 - (np.clip(mkt_p, 1e-6, 1 - 1e-6) - y) ** 2
    verdict, ci = _verdict(delta)
    return {"tour": tag, "n": int(len(y)), "brier_gbm": round(b_gbm, 4), "brier_close": round(b_mkt, 4),
            "logloss_gbm": round(ll_gbm, 4), "logloss_close": round(ll_mkt, 4),
            "paired_delta_mean": round(float(delta.mean()), 4), "paired_delta_95ci": ci, "verdict": verdict}


def run(corpus: Path = None) -> Dict:
    root = corpus or _TENNIS
    matches = pd.read_parquet(root / "matches.parquet")
    wta_matches = pd.read_parquet(root / "wta_matches.parquet")
    odds = pd.read_parquet(root / "odds.parquet")
    asof_hold = pd.read_parquet(root / "asof_hold.parquet")
    asof_hold_wta = pd.read_parquet(root / "asof_hold_wta.parquet")

    feat = pd.concat([build_features(matches, asof_hold, is_wta=0.0),
                       build_features(wta_matches, asof_hold_wta, is_wta=1.0)], ignore_index=True)
    m = join_market(feat, odds)
    n = len(m)
    if n < 200:
        return {"status": "data_limited", "n_overlap": n, "edge_claimed": False}

    folds = make_folds(feat, m)
    if len(folds) < 3:
        return {"status": "insufficient_folds", "n_folds": len(folds), "edge_claimed": False}

    params, select_note = _select_hyperparams(feat, folds[0]["train_mask"])

    fold_reports, gbm_all, mkt_all, y_all, tour_all, device_used, models = [], [], [], [], [], None, []
    for j, fo in enumerate(folds):
        tr = feat.loc[fo["train_mask"]]
        te = m.loc[fo["test_mask"]]
        model, device_used = _fit(tr[_FEATURES], tr["p1_win"], params)
        models.append(model)
        p_gbm = np.clip(model.predict_proba(te[_FEATURES])[:, 1], 1e-6, 1 - 1e-6)
        p_mkt = te["p_market"].to_numpy(float)
        y = te["p1_win"].to_numpy(float)
        tourv = te["is_wta"].to_numpy(float)
        gbm_all.extend(p_gbm); mkt_all.extend(p_mkt); y_all.extend(y); tour_all.extend(tourv)
        b_gbm, _ = _score(p_gbm, y); b_mkt, _ = _score(p_mkt, y)
        fold_reports.append({
            "fold": j, "n_train": int(fo["train_mask"].sum()), "n_test": int(len(te)),
            "n_test_atp": int((tourv == 0).sum()), "n_test_wta": int((tourv == 1).sum()),
            "test_year_lo": fo["test_year_lo"], "test_year_hi": fo["test_year_hi"],
            "brier_gbm": round(b_gbm, 4), "brier_close": round(b_mkt, 4),
        })

    gbm_all, mkt_all, y_all, tour_all = map(np.array, (gbm_all, mkt_all, y_all, tour_all))
    overall = _tour_report(gbm_all, mkt_all, y_all, "overall")
    per_tour = {"atp": _tour_report(gbm_all[tour_all == 0], mkt_all[tour_all == 0], y_all[tour_all == 0], "atp"),
                "wta": _tour_report(gbm_all[tour_all == 1], mkt_all[tour_all == 1], y_all[tour_all == 1], "wta")}

    # matched-split comparison vs elo_platt: final fold only (train<=2022, test>2022) is the
    # SAME year cut beat_the_close_ml[/_wta] uses for its own TRAIN_YEAR_MAX=2022 split.
    final = folds[-1]
    te_final = m.loc[final["test_mask"]]
    tourv_final = te_final["is_wta"].to_numpy(float)
    gbm_final = np.clip(models[-1].predict_proba(te_final[_FEATURES])[:, 1], 1e-6, 1 - 1e-6)
    y_final = te_final["p1_win"].to_numpy(float)
    vs_elo_platt = {
        "matched_split": "year>2022 (final fold), same TRAIN_YEAR_MAX=2022 cut as beat_the_close_ml[_wta]",
        "atp": _matched_fold(gbm_final, y_final, tourv_final, 0.0, _atp_close.run()),
        "wta": _matched_fold(gbm_final, y_final, tourv_final, 1.0, _wta_close.run()),
    }

    gains: Dict[str, float] = {f: 0.0 for f in _FEATURES}
    for model in models:
        for f, v in model.get_booster().get_score(importance_type="gain").items():
            gains[f] = gains.get(f, 0.0) + v / len(models)
    top10 = sorted(gains.items(), key=lambda kv: -kv[1])[:10]

    final_model, _ = _fit(feat[_FEATURES], feat["p1_win"], params)
    _MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    final_model.save_model(str(_MODEL_OUT))

    return {
        "status": "ok", "edge_claimed": False,
        "features": _FEATURES,
        "hyperparams_grid": _GRID, "chosen_hyperparams": params,
        "hyperparam_selection_note": select_note, "device_used": device_used,
        "folds": fold_reports, "n_overlap": n,
        "overall": overall, "per_tour": per_tour, "vs_elo_platt": vs_elo_platt,
        "verdict": overall["verdict"],
        "top10_gain_features": [[f, round(v, 2)] for f, v in top10],
        "model_artifact": str(_MODEL_OUT.relative_to(_REPO)).replace("\\", "/"),
        "honest_note": ("Pregame-only leak-free features (elo/hold-pct/svpts-won asof, rank, "
                         "surface, best_of, tour flag); no market inputs. Trained ATP+WTA jointly "
                         "with an is_wta flag, scored per tour separately (tour heterogeneity is "
                         "real -- surface_hold_gate_verdict.json). svpts_won_asof stands in for "
                         "ace/return-rate on both tours (true return-rate asof exists for ATP "
                         "only). Ranking uses rank, not ranking points (not in this corpus). "
                         "Calibration/sharpness only. No $ edge claimed."),
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: {rep}")
        return 0
    _ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    _ARTIFACT.write_text(json.dumps(rep, indent=2))
    print(f"=== tennis match: GBM challenger vs devigged close (n={rep['n_overlap']}, "
          f"device={rep['device_used']}) ===")
    for tag, r in [("overall", rep["overall"]), ("atp", rep["per_tour"]["atp"]), ("wta", rep["per_tour"]["wta"])]:
        print(f"  {tag:>8}  n={r['n']:>6}  brier_gbm={r['brier_gbm']}  brier_close={r['brier_close']}  {r['verdict'].split(':')[0]}")
    print(f"\nVERDICT: {rep['verdict']}\nvs elo_platt (matched split year>2022): {rep['vs_elo_platt']}")
    print(f"top-10 gain features: {rep['top10_gain_features']}\nartifact -> {_ARTIFACT}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
