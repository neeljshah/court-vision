"""scripts.platformkit.pod_sprint.gbm_family_p -- Family P (player-grain availability +
value) GBM candidate: the market knows who plays tonight; Elo is player-blind.

Joins the 8 walk-forward features from player_value_asof (P1 roster_value_asof, P2
star_absence_delta, P3 continuity, P4 top_heavy -- each home/away) onto gbm_nba_ml's base
per-GAME frame by (date, team_abbr) -- two independent leak-free walk-forward passes over
the SAME box corpus (player_value_asof carries its own leak trap). Missing player_boxscores
coverage defaults to 0.0 (neutral), counted honestly. Tested ALONE vs plain features per
DEEP_FEATURES_PREREG.md (not stacked on gbm_nba_enriched's claims-features). Same honest
gate: in-process PAIRED bootstrap CI vs plain features (same folds/WIDE_GRID/inner-80/20
selection) + vs close. edge_claimed always False.

CLI: python -m scripts.platformkit.pod_sprint.gbm_family_p
"""
from __future__ import annotations

import json
import sys
from typing import Dict

import numpy as np
import pandas as pd

from scripts.platformkit.models import gbm_nba_ml as g  # noqa: E402
from scripts.platformkit.pod_sprint.gbm_sweep import WIDE_GRID  # noqa: E402
from scripts.platformkit.pod_sprint.player_value_asof import build_player_value_features  # noqa: E402

_HOME_COLS = ["home_roster_value_asof", "home_star_absence_delta", "home_continuity", "home_top_heavy"]
_AWAY_COLS = ["away_roster_value_asof", "away_star_absence_delta", "away_continuity", "away_top_heavy"]
_EXTRA_FEATURES = _HOME_COLS + _AWAY_COLS
_PV_COLS = ["roster_value_asof", "star_absence_delta", "continuity", "top_heavy"]
FAMILY_P_FEATURES = g._FEATURES + _EXTRA_FEATURES

_ARTIFACT = g._REPO / "data" / "domains" / "nba" / "gbm_family_p_benchmark.json"
_MODEL_OUT = g._REPO / "data" / "models" / "nba_ml_gbm_family_p.json"
_PLAYER_BOX = g._NBA / "player_boxscores.parquet"

def _side_pv(pv: pd.DataFrame, side: str, cols: list) -> pd.DataFrame:
    ren = dict(zip(["team_abbr"] + _PV_COLS, [f"{side}_abbr"] + cols))
    return pv.rename(columns=ren)[["date", f"{side}_abbr"] + cols]

def build_features(box: pd.DataFrame) -> pd.DataFrame:
    """Base 15 leak-free features (unmodified) + Family P's 8, joined by (date, team_abbr)."""
    base = g.build_features(box)
    pv = build_player_value_features(pd.read_parquet(_PLAYER_BOX))
    merged = base.merge(_side_pv(pv, "home", _HOME_COLS), on=["date", "home_abbr"], how="left")
    merged = merged.merge(_side_pv(pv, "away", _AWAY_COLS), on=["date", "away_abbr"], how="left")
    merged.attrs["n_missing_player_coverage"] = int(merged[_HOME_COLS[0]].isna().sum())
    merged[_EXTRA_FEATURES] = merged[_EXTRA_FEATURES].fillna(0.0)
    return merged

def _select(feat: pd.DataFrame, pool_mask: pd.Series, features: list):
    """Reuse gbm_nba_ml's inner-80/20 selector (monkeypatch-and-restore, like gbm_sweep.py)."""
    saved_f, saved_g = g._FEATURES, g._GRID
    g._FEATURES, g._GRID = features, WIDE_GRID
    try:
        return g._select_hyperparams(feat, pool_mask)
    finally:
        g._FEATURES, g._GRID = saved_f, saved_g

def run() -> Dict:
    box = g.load_box(g._NBA)
    feat = build_features(box)
    n_missing = int(feat.attrs.get("n_missing_player_coverage", 0))
    m = g.join_market(feat, g._NBA)
    n = len(m)
    if n < 120:
        return {"status": "data_limited", "n_overlap": n, "edge_claimed": False}

    folds = g.make_folds(feat, m, k=4)
    plain_params, _ = _select(feat, folds[0][0], g._FEATURES)
    fp_params, fp_note = _select(feat, folds[0][0], FAMILY_P_FEATURES)

    fold_reports, device = [], None
    p_plain_all, p_fp_all, p_mkt_all, y_all = [], [], [], []
    for j, (train_mask, lo, hi) in enumerate(folds):
        tr, te = feat.loc[train_mask], m.iloc[lo:hi]
        m_plain, device = g._fit(tr[g._FEATURES], tr["home_win"], plain_params)
        m_fp, _ = g._fit(tr[FAMILY_P_FEATURES], tr["home_win"], fp_params)
        p_plain = np.clip(m_plain.predict_proba(te[g._FEATURES])[:, 1], 1e-6, 1 - 1e-6)
        p_fp = np.clip(m_fp.predict_proba(te[FAMILY_P_FEATURES])[:, 1], 1e-6, 1 - 1e-6)
        p_mkt, y = te["p_market"].to_numpy(float), te["home_win"].to_numpy(float)
        p_plain_all.extend(p_plain); p_fp_all.extend(p_fp); p_mkt_all.extend(p_mkt); y_all.extend(y)
        fold_reports.append({
            "fold": j, "n_train": int(train_mask.sum()), "n_test": int(hi - lo),
            "brier_family_p": round(float(np.mean((p_fp - y) ** 2)), 4),
            "brier_plain": round(float(np.mean((p_plain - y) ** 2)), 4),
            "brier_close": round(float(np.mean((p_mkt - y) ** 2)), 4),
        })

    p_plain_all, p_fp_all, p_mkt_all, y_all = map(np.array, (p_plain_all, p_fp_all, p_mkt_all, y_all))
    brier_fp = float(np.mean((p_fp_all - y_all) ** 2))
    brier_plain = float(np.mean((p_plain_all - y_all) ** 2))
    brier_close = float(np.mean((p_mkt_all - y_all) ** 2))

    delta_plain = (p_fp_all - y_all) ** 2 - (p_plain_all - y_all) ** 2  # <0 => family-P sharper
    ci_plain = [round(v, 4) for v in g._bootstrap_ci(delta_plain)]
    delta_close = (p_fp_all - y_all) ** 2 - (p_mkt_all - y_all) ** 2
    ci_close = [round(v, 4) for v in g._bootstrap_ci(delta_close)]
    dp_mean, dc_mean = round(float(delta_plain.mean()), 4), round(float(delta_close.mean()), 4)

    verdict = (f"FAMILY-P-IMPROVED: beats plain features outside noise (delta {dp_mean} CI{ci_plain})"
               if ci_plain[1] < 0 else
               f"NO-IMPROVEMENT: CI vs plain features does not exclude zero (delta {dp_mean} CI{ci_plain})")
    verdict_vs_close = (f"SHARPER (delta {dc_mean} CI{ci_close})" if ci_close[1] < 0 else
                         f"TRAILS (delta {dc_mean} CI{ci_close})" if ci_close[0] > 0 else
                         f"MATCHES (delta {dc_mean} CI{ci_close})")

    final_model, device = g._fit(feat[FAMILY_P_FEATURES], feat["home_win"], fp_params)
    _MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    final_model.save_model(str(_MODEL_OUT))

    return {
        "status": "ok", "edge_claimed": False,
        "features": FAMILY_P_FEATURES, "feature_family": "P (player-grain availability + value)",
        "n_missing_player_coverage": n_missing, "hyperparams_grid_size": len(WIDE_GRID),
        "chosen_hyperparams_family_p": fp_params, "chosen_hyperparams_plain": plain_params,
        "hyperparam_selection_note": fp_note, "device_used": device, "n_overlap": n,
        "folds": fold_reports,
        "brier_family_p": round(brier_fp, 4), "brier_plain_features": round(brier_plain, 4),
        "brier_close": round(brier_close, 4),
        "paired_delta_vs_plain_features_mean": dp_mean, "paired_delta_vs_plain_features_95ci": ci_plain,
        "paired_delta_vs_close_mean": dc_mean, "paired_delta_vs_close_95ci": ci_close,
        "verdict": verdict, "verdict_vs_close": verdict_vs_close,
        "model_artifact": str(_MODEL_OUT.relative_to(g._REPO)).replace("\\", "/"),
        "honest_note": (
            "Family P per DEEP_FEATURES_PREREG.md, tested ALONE vs plain features: walk-forward "
            "per-player EW per-minute value (plus_minus/min, shrunk to the global as-of mean by "
            "career minutes) aggregated per team-game, joined by (date, team_abbr) -- never "
            "same-game participation. Paired bootstrap CI vs plain features is the honest gate. "
            "No $ edge claimed."),
    }

def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n_overlap={rep.get('n_overlap')}")
        return 0
    _ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    _ARTIFACT.write_text(json.dumps(rep, indent=2))
    print(f"=== NBA ML GBM Family P (n={rep['n_overlap']}, device={rep['device_used']}) ===")
    print(f"  Brier: close={rep['brier_close']} plain={rep['brier_plain_features']} family_p={rep['brier_family_p']}")
    print(f"  VERDICT vs plain: {rep['verdict']}")
    print(f"  vs close: {rep['verdict_vs_close']}")
    print(f"  n_missing_player_coverage: {rep['n_missing_player_coverage']}/{rep['n_overlap']}")
    print(f"artifact -> {_ARTIFACT}")
    return 0

if __name__ == "__main__":
    sys.exit(_main())
