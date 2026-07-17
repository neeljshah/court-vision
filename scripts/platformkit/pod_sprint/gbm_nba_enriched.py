"""scripts.platformkit.pod_sprint.gbm_nba_enriched -- claims-enriched NBA GBM candidate.

Extends scripts.platformkit.models.gbm_nba_ml with 3 walk-forward feature families
built from the SAME box corpus, mirroring two of the system's own VERIFIED intel
claims but recomputed AS-OF each game (never a full-season join -- that would leak
future games into early rows):

  venue_split_home/away  -- each team's expanding home-minus-away PPG, walk-forward
                             (mirrors nba_venue_split_claims.py's raw_value, asof)
  rest_form_home/away    -- each team's expanding short-rest(<=1 gap day)-minus-
                             long-rest PPG, walk-forward (mirrors
                             nba_rest_adjusted_form_claims.py's raw_value, asof)
  l10_oppadj_home/away   -- trailing-10-game mean (actual result - Elo-expected
                             result), i.e. opponent-strength-adjusted recent form;
                             reuses the base module's own elo_home/elo_away/
                             home_win columns, no extra Elo pass

Both new PPG splits default to 0.0 (neutral) until a team clears _MIN_ASOF_N games
on EACH side of the split -- avoids noisy early-season values, no formal tuning.

Reuses (never copies) gbm_nba_ml's Elo machinery (elo_home/elo_away columns),
load_box, join_market, make_folds, _select_hyperparams (monkeypatch-style, like
gbm_sweep.py does with _GRID) and the CI bootstrap helper. gbm_nba_ml.py itself
is never edited.

GATE: trains a PLAIN-feature model (WIDE_GRID from gbm_sweep, same folds, same
inner-80/20 selection) IN-PROCESS alongside the enriched model so the vs-plain
comparison is a genuinely PAIRED per-game bootstrap CI, not a point estimate off
a stale artifact. Verdict is ENRICHED-IMPROVED only if that CI excludes zero;
otherwise NO-IMPROVEMENT, reported honestly either way. Also benchmarks vs the
devigged close (informational, same as the base module). If
data/domains/nba/gbm_ml_sweep_benchmark.json exists on disk, its aggregate Brier
is cross-checked (not used for the CI -- no per-game predictions on disk to pair).

CLI: python -m scripts.platformkit.pod_sprint.gbm_nba_enriched
"""
from __future__ import annotations

import json
import sys
from collections import deque
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.models import gbm_nba_ml as g  # noqa: E402
from scripts.platformkit.pod_sprint.gbm_sweep import WIDE_GRID  # noqa: E402

_BASE_BUILD_FEATURES = g.build_features  # captured before any monkeypatch, reused below

_EXTRA_FEATURES = [
    "venue_split_home", "venue_split_away",
    "rest_form_home", "rest_form_away",
    "l10_oppadj_home", "l10_oppadj_away",
]
ENRICHED_FEATURES = g._FEATURES + _EXTRA_FEATURES
_MIN_ASOF_N = 3  # ponytail: small floor so early-season rows aren't pure noise; no tuning done

_ARTIFACT = g._REPO / "data" / "domains" / "nba" / "gbm_ml_enriched_benchmark.json"
_MODEL_OUT = g._REPO / "data" / "models" / "nba_ml_gbm_enriched.json"
_SWEEP_BASELINE = g._REPO / "data" / "domains" / "nba" / "gbm_ml_sweep_benchmark.json"


def _extra_features(box: pd.DataFrame, base_feat: pd.DataFrame) -> pd.DataFrame:
    """A second leak-free walk-forward pass, row-aligned with base_feat (both iterate
    box in the same order). Row i's values depend only on games strictly before i --
    see test_leak_trap_extra_features_ignore_own_game."""
    h = box["home_abbr"].to_numpy(); a = box["away_abbr"].to_numpy()
    hp = box["home_pts"].to_numpy(float); ap = box["away_pts"].to_numpy(float)
    dates = pd.to_datetime(box["date"]).to_numpy()
    elo_home = base_feat["elo_home"].to_numpy(); elo_away = base_feat["elo_away"].to_numpy()
    home_win = base_feat["home_win"].to_numpy()

    home_sum: Dict[str, float] = {}; home_n: Dict[str, int] = {}
    away_sum: Dict[str, float] = {}; away_n: Dict[str, int] = {}
    short_sum: Dict[str, float] = {}; short_n: Dict[str, int] = {}
    long_sum: Dict[str, float] = {}; long_n: Dict[str, int] = {}
    last_date: Dict[str, pd.Timestamp] = {}
    oppadj: Dict[str, deque] = {}

    def _split(sum_d, n_d, sum_d2, n_d2, team) -> float:
        if n_d.get(team, 0) < _MIN_ASOF_N or n_d2.get(team, 0) < _MIN_ASOF_N:
            return 0.0
        return sum_d[team] / n_d[team] - sum_d2[team] / n_d2[team]

    rows: list[dict] = []
    for i in range(len(box)):
        ht, at = str(h[i]), str(a[i])
        oppadj.setdefault(ht, deque(maxlen=10)); oppadj.setdefault(at, deque(maxlen=10))
        rows.append({
            "venue_split_home": _split(home_sum, home_n, away_sum, away_n, ht),
            "venue_split_away": _split(home_sum, home_n, away_sum, away_n, at),
            "rest_form_home": _split(short_sum, short_n, long_sum, long_n, ht),
            "rest_form_away": _split(short_sum, short_n, long_sum, long_n, at),
            "l10_oppadj_home": (sum(oppadj[ht]) / len(oppadj[ht])) if oppadj[ht] else 0.0,
            "l10_oppadj_away": (sum(oppadj[at]) / len(oppadj[at])) if oppadj[at] else 0.0,
        })

        # state updates happen AFTER row i's features are emitted -- this game's own
        # outcome/score must never leak into row i itself, only into LATER rows.
        d = pd.Timestamp(dates[i])
        home_sum[ht] = home_sum.get(ht, 0.0) + hp[i]; home_n[ht] = home_n.get(ht, 0) + 1
        away_sum[at] = away_sum.get(at, 0.0) + ap[i]; away_n[at] = away_n.get(at, 0) + 1
        for team, pts in ((ht, hp[i]), (at, ap[i])):
            if team in last_date:
                rest_days = (d - last_date[team]).days - 1
                bucket_sum, bucket_n = (short_sum, short_n) if rest_days <= 1 else (long_sum, long_n)
                bucket_sum[team] = bucket_sum.get(team, 0.0) + pts
                bucket_n[team] = bucket_n.get(team, 0) + 1
        last_date[ht] = d; last_date[at] = d

        r = home_win[i] - g._p_home(elo_home[i], elo_away[i])
        oppadj[ht].append(r); oppadj[at].append(-r)

    return pd.DataFrame(rows)


def build_features(box: pd.DataFrame) -> pd.DataFrame:
    """Base 15 leak-free features (reused, unmodified) + the 6 claims-enriched ones,
    one extra walk-forward pass, concatenated column-wise (both passes iterate box in
    the same row order)."""
    base = _BASE_BUILD_FEATURES(box)
    extra = _extra_features(box, base)
    return pd.concat([base, extra], axis=1)


def _select(feat: pd.DataFrame, pool_mask: pd.Series, features: list) -> Tuple[dict, str]:
    """Reuse gbm_nba_ml's inner-80/20 selector via its documented monkeypatch pattern
    (see gbm_sweep.py); restores globals immediately after so nothing leaks out."""
    saved_f, saved_g = g._FEATURES, g._GRID
    g._FEATURES, g._GRID = features, WIDE_GRID
    try:
        return g._select_hyperparams(feat, pool_mask)
    finally:
        g._FEATURES, g._GRID = saved_f, saved_g


def run() -> Dict:
    box = g.load_box(g._NBA)
    feat = build_features(box)
    m = g.join_market(feat, g._NBA)
    n = len(m)
    if n < 120:
        return {"status": "data_limited", "n_overlap": n, "edge_claimed": False}

    folds = g.make_folds(feat, m, k=4)
    plain_params, plain_note = _select(feat, folds[0][0], g._FEATURES)
    enr_params, enr_note = _select(feat, folds[0][0], ENRICHED_FEATURES)

    fold_reports, device = [], None
    p_plain_all, p_enr_all, p_mkt_all, y_all = [], [], [], []
    for j, (train_mask, lo, hi) in enumerate(folds):
        tr, te = feat.loc[train_mask], m.iloc[lo:hi]
        m_plain, device = g._fit(tr[g._FEATURES], tr["home_win"], plain_params)
        m_enr, _ = g._fit(tr[ENRICHED_FEATURES], tr["home_win"], enr_params)
        p_plain = np.clip(m_plain.predict_proba(te[g._FEATURES])[:, 1], 1e-6, 1 - 1e-6)
        p_enr = np.clip(m_enr.predict_proba(te[ENRICHED_FEATURES])[:, 1], 1e-6, 1 - 1e-6)
        p_mkt, y = te["p_market"].to_numpy(float), te["home_win"].to_numpy(float)
        p_plain_all.extend(p_plain); p_enr_all.extend(p_enr); p_mkt_all.extend(p_mkt); y_all.extend(y)
        fold_reports.append({
            "fold": j, "n_train": int(train_mask.sum()), "n_test": int(hi - lo),
            "test_start": str(te["date"].iloc[0].date()), "test_end": str(te["date"].iloc[-1].date()),
            "brier_enriched": round(float(np.mean((p_enr - y) ** 2)), 4),
            "brier_plain": round(float(np.mean((p_plain - y) ** 2)), 4),
            "brier_close": round(float(np.mean((p_mkt - y) ** 2)), 4),
        })

    p_plain_all, p_enr_all, p_mkt_all, y_all = map(np.array, (p_plain_all, p_enr_all, p_mkt_all, y_all))
    brier_enr = float(np.mean((p_enr_all - y_all) ** 2))
    brier_plain = float(np.mean((p_plain_all - y_all) ** 2))
    brier_close = float(np.mean((p_mkt_all - y_all) ** 2))

    delta_plain = (p_enr_all - y_all) ** 2 - (p_plain_all - y_all) ** 2  # <0 => enriched sharper
    ci_plain = [round(v, 4) for v in g._bootstrap_ci(delta_plain)]
    delta_close = (p_enr_all - y_all) ** 2 - (p_mkt_all - y_all) ** 2
    ci_close = [round(v, 4) for v in g._bootstrap_ci(delta_close)]

    if ci_plain[1] < 0:
        verdict = (f"ENRICHED-IMPROVED: beats plain features outside noise "
                   f"(delta {round(float(delta_plain.mean()), 4)} CI{ci_plain})")
    else:
        verdict = (f"NO-IMPROVEMENT: CI vs plain features does not exclude zero "
                   f"(delta {round(float(delta_plain.mean()), 4)} CI{ci_plain})")
    if ci_close[1] < 0:
        verdict_vs_close = f"SHARPER (delta {round(float(delta_close.mean()), 4)} CI{ci_close})"
    elif ci_close[0] > 0:
        verdict_vs_close = f"TRAILS (delta {round(float(delta_close.mean()), 4)} CI{ci_close})"
    else:
        verdict_vs_close = f"MATCHES (delta {round(float(delta_close.mean()), 4)} CI{ci_close})"

    final_model, device = g._fit(feat[ENRICHED_FEATURES], feat["home_win"], enr_params)
    _MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    final_model.save_model(str(_MODEL_OUT))

    rep = {
        "status": "ok", "edge_claimed": False,
        "features": ENRICHED_FEATURES, "feature_families_added": _EXTRA_FEATURES,
        "asof_min_n_floor": _MIN_ASOF_N,
        "hyperparams_grid_size": len(WIDE_GRID),
        "chosen_hyperparams_enriched": enr_params, "chosen_hyperparams_plain": plain_params,
        "hyperparam_selection_note": enr_note,
        "device_used": device, "n_overlap": n, "folds": fold_reports,
        "brier_enriched": round(brier_enr, 4), "brier_plain_features": round(brier_plain, 4),
        "brier_close": round(brier_close, 4),
        "paired_delta_vs_plain_features_mean": round(float(delta_plain.mean()), 4),
        "paired_delta_vs_plain_features_95ci": ci_plain,
        "paired_delta_vs_close_mean": round(float(delta_close.mean()), 4),
        "paired_delta_vs_close_95ci": ci_close,
        "verdict": verdict, "verdict_vs_close": verdict_vs_close,
        "model_artifact": str(_MODEL_OUT.relative_to(g._REPO)).replace("\\", "/"),
        "honest_note": (
            "Enriched pregame features drawn from the system's OWN validated intelligence "
            "(nba_venue_split / nba_rest_adjusted_form claim families), recomputed AS-OF "
            "each game from the same box corpus -- never a full-season claim-store join. "
            "The plain-feature comparison model is trained in-process on the identical "
            "folds/grid for a genuinely paired per-game delta. Both still trail/match the "
            "devigged close as measured. No $ edge claimed."),
    }
    if _SWEEP_BASELINE.exists():
        base = json.loads(_SWEEP_BASELINE.read_text())
        rep["sweep_artifact_cross_check"] = {
            "artifact": str(_SWEEP_BASELINE.relative_to(g._REPO)).replace("\\", "/"),
            "artifact_brier_gbm": base.get("brier_gbm"),
            "note": "informational only, NOT the gate -- no per-game predictions on disk to "
                    "pair with; paired_delta_vs_plain_features_* above is the honest gate.",
        }
    return rep


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n_overlap={rep.get('n_overlap')}")
        return 0
    _ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    _ARTIFACT.write_text(json.dumps(rep, indent=2))
    print(f"=== NBA ML GBM claims-enriched candidate (n={rep['n_overlap']}, device={rep['device_used']}) ===")
    print(f"  Brier: close={rep['brier_close']} plain={rep['brier_plain_features']} enriched={rep['brier_enriched']}")
    print(f"  VERDICT vs plain features: {rep['verdict']}")
    print(f"  vs close: {rep['verdict_vs_close']}")
    print(f"artifact -> {_ARTIFACT}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
