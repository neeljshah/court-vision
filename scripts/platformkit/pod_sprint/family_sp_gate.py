"""scripts.platformkit.pod_sprint.family_sp_gate -- Family SP1 honest gate:
does as-of starter quality (domains.mlb.sp_quality_asof) predict the MLB
pregame outcome beyond a base with NO starting-pitcher info at all?

PREREG (DEEP_FEATURES_PREREG.md lines 54-56): "SP1 as-of starter quality
from statcast (EW xwOBA-against last 6 starts, walk-forward) -- kills
pitcher-blindness with data already on the pod."

COMPARABILITY (base and candidate differ ONLY by the SP1 feature): BASE =
domains.mlb.ratings.walk_forward_elo's leak-free pre-game p_home_elo alone
(a linear-probability fit of home_win ~ const + p_home_elo). CANDIDATE = the
SAME p_home_elo PLUS sp_diff = home_sp_xwoba_against_asof -
away_sp_xwoba_against_asof (home_win ~ const + p_home_elo + sp_diff). Higher
xwOBA-against means a WORSE pitcher, so a positive sp_diff (home pitcher
worse than away) should, if the hypothesis holds, push AWAY from a home win.

GRAIN: simplest defensible split -- fit both models' coefficients on
TRAIN_SEASON only (2022), score the PAIRED squared-error delta
out-of-sample on TEST_SEASON only (2023): strictly walk-forward, no
coefficient ever sees test-season outcomes. Two outcomes scored in
parallel: win (home_win 0/1) and margin (home_runs - away_runs).

PREREG FLOORS (declared before any scoring): MIN_N_TRAIN=100, MIN_N_TEST=200.
Verdict per outcome: UNDERPOWERED if n_train or n_test is below its floor;
else SP1_DETECTED if the paired-delta 95% bootstrap CI upper bound < 0
(candidate strictly sharper than base); else NULL_LOCAL. NOT_TESTABLE if
either data source is absent/empty (fails closed -- this worktree has no
data/; the real run happens on the pod). edge_claimed is always False.

CLI: python -m scripts.platformkit.pod_sprint.family_sp_gate
     writes data/domains/mlb/family_sp_gate_verdict.json
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.mlb.config import GAMES_PARQUET  # noqa: E402
from domains.mlb.ratings import walk_forward_elo  # noqa: E402
from domains.mlb.sp_quality_asof import DEFAULT_STATCAST_PATHS, build_sp_quality_asof  # noqa: E402
from scripts.platformkit.io_atomic import write_json_atomic  # noqa: E402

_OUT = _REPO / "data" / "domains" / "mlb" / "family_sp_gate_verdict.json"
_GAMES_PATH = _REPO / GAMES_PARQUET

TRAIN_SEASON = 2022
TEST_SEASON = 2023
MIN_N_TRAIN = 100
MIN_N_TEST = 200


def _bootstrap_ci(delta: np.ndarray, b: int = 3000, seed: int = 0) -> List[float]:
    """Percentile bootstrap 95% CI of the mean paired delta."""
    rng = np.random.default_rng(seed)
    n = len(delta)
    means = [rng.choice(delta, size=n, replace=True).mean() for _ in range(b)]
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def build_sp_diff(sp_quality: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Join home/away starter asof values onto games by (date, team); sp_diff
    = home - away, NaN (dropped) unless BOTH sides have a prior start."""
    if sp_quality.empty or games.empty:
        return pd.DataFrame()
    sp = sp_quality.copy()
    sp["game_date"] = pd.to_datetime(sp["game_date"]).dt.date
    g = games.copy()
    g["date"] = pd.to_datetime(g["date"]).dt.date

    home = sp.rename(columns={"team": "home_team", "sp_xwoba_against_asof": "home_sp_asof"})
    away = sp.rename(columns={"team": "away_team", "sp_xwoba_against_asof": "away_sp_asof"})
    merged = g.merge(home[["game_date", "home_team", "home_sp_asof"]],
                      left_on=["date", "home_team"], right_on=["game_date", "home_team"], how="left")
    merged = merged.merge(away[["game_date", "away_team", "away_sp_asof"]],
                           left_on=["date", "away_team"], right_on=["game_date", "away_team"], how="left")
    merged["sp_diff"] = merged["home_sp_asof"] - merged["away_sp_asof"]
    return merged.drop(columns=["game_date_x", "game_date_y"], errors="ignore")


def _fit(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def _score(train: pd.DataFrame, test: pd.DataFrame, y_col: str, clip01: bool) -> Dict[str, object]:
    xb_tr = np.column_stack([np.ones(len(train)), train["p_home_elo"]])
    xc_tr = np.column_stack([np.ones(len(train)), train["p_home_elo"], train["sp_diff"]])
    y_tr = train[y_col].to_numpy(dtype=float)
    beta_base, beta_cand = _fit(xb_tr, y_tr), _fit(xc_tr, y_tr)

    xb_te = np.column_stack([np.ones(len(test)), test["p_home_elo"]])
    xc_te = np.column_stack([np.ones(len(test)), test["p_home_elo"], test["sp_diff"]])
    y_te = test[y_col].to_numpy(dtype=float)
    pred_base, pred_cand = xb_te @ beta_base, xc_te @ beta_cand
    if clip01:
        pred_base, pred_cand = np.clip(pred_base, 1e-6, 1 - 1e-6), np.clip(pred_cand, 1e-6, 1 - 1e-6)

    delta = (pred_cand - y_te) ** 2 - (pred_base - y_te) ** 2  # <0 => candidate sharper
    ci = [round(v, 4) for v in _bootstrap_ci(delta)]
    mean = round(float(delta.mean()), 4)

    n_train, n_test = len(train), len(test)
    if n_train < MIN_N_TRAIN or n_test < MIN_N_TEST:
        verdict = "UNDERPOWERED"
    elif ci[1] < 0:
        verdict = "SP1_DETECTED"
    else:
        verdict = "NULL_LOCAL"
    return {
        "n_train": n_train, "n_test": n_test,
        "brier_or_mse_base": round(float(np.mean((pred_base - y_te) ** 2)), 4),
        "brier_or_mse_candidate": round(float(np.mean((pred_cand - y_te) ** 2)), 4),
        "paired_delta_mean": mean, "paired_delta_95ci": ci, "verdict": verdict,
    }


def _not_testable(reason: str) -> Dict[str, object]:
    return {
        "family": "SP1", "hypothesis": "sp_quality_asof_diff",
        "verdict": {"win": "NOT_TESTABLE", "margin": "NOT_TESTABLE"},
        "effect": None, "ci": None, "n": {"train": 0, "test": 0},
        "edge_claimed": False, "honest_note": reason,
    }


def run(games: Optional[pd.DataFrame] = None, sp_quality: Optional[pd.DataFrame] = None) -> Dict[str, object]:
    if games is None:
        games = pd.read_parquet(_GAMES_PATH) if _GAMES_PATH.exists() else pd.DataFrame()
    if games.empty:
        return _not_testable(f"games.parquet absent/empty at {_GAMES_PATH} -- fail-closed, no scoring run.")

    if sp_quality is None:
        sp_quality = build_sp_quality_asof(DEFAULT_STATCAST_PATHS)
    if sp_quality.empty:
        return _not_testable("statcast starter-asof frame empty (parquets absent in this worktree) "
                              "-- fail-closed, no scoring run. Real run happens on the pod.")

    elo = walk_forward_elo(games)
    analysis = build_sp_diff(sp_quality, elo)
    if analysis.empty:
        return _not_testable("home/away asof join produced zero rows (no (date, team) overlap).")

    analysis["home_win"] = (analysis["home_runs"] > analysis["away_runs"]).astype(float)
    analysis["margin"] = analysis["home_runs"] - analysis["away_runs"]
    analysis = analysis.dropna(subset=["sp_diff", "p_home_elo", "home_win", "margin"])

    train = analysis[analysis["season"] == TRAIN_SEASON]
    test = analysis[analysis["season"] == TEST_SEASON]
    if train.empty or test.empty:
        return _not_testable(f"no rows in train season {TRAIN_SEASON} or test season {TEST_SEASON} "
                              "after the sp_diff/elo join -- fail-closed.")

    win_report = _score(train, test, "home_win", clip01=True)
    margin_report = _score(train, test, "margin", clip01=False)

    return {
        "family": "SP1", "hypothesis": "sp_quality_asof_diff",
        "train_season": TRAIN_SEASON, "test_season": TEST_SEASON,
        "min_n_train_floor": MIN_N_TRAIN, "min_n_test_floor": MIN_N_TEST,
        "win": win_report, "margin": margin_report,
        "verdict": {"win": win_report["verdict"], "margin": margin_report["verdict"]},
        "effect": {"win_paired_delta_mean": win_report["paired_delta_mean"],
                   "margin_paired_delta_mean": margin_report["paired_delta_mean"]},
        "ci": {"win": win_report["paired_delta_95ci"], "margin": margin_report["paired_delta_95ci"]},
        "n": {"train": win_report["n_train"], "test": win_report["n_test"]},
        "edge_claimed": False,
        "honest_note": (
            "Family SP1 per DEEP_FEATURES_PREREG.md lines 54-56: base=p_home_elo alone "
            "(walk_forward_elo, no SP info) vs candidate=base+sp_diff (as-of EW xwOBA-against "
            "diff, last 6 starts). Coefficients fit on TRAIN_SEASON only, scored strictly "
            "out-of-sample on TEST_SEASON. Paired bootstrap CI of squared-error delta is the "
            "honest gate. No $/edge claimed either way."),
    }


def _print(rep: Dict[str, object]) -> None:
    if rep["effect"] is None:
        print(f"Family SP1: {rep['honest_note']}")
        return
    print(f"Family SP1 (train={rep['train_season']} n={rep['n']['train']}, "
          f"test={rep['test_season']} n={rep['n']['test']})")
    for outcome in ("win", "margin"):
        r = rep[outcome]
        print(f"  {outcome}: base={r['brier_or_mse_base']} candidate={r['brier_or_mse_candidate']} "
              f"delta={r['paired_delta_mean']} CI{r['paired_delta_95ci']} -> {r['verdict']}")
    print(f"edge_claimed={rep['edge_claimed']}")


def main() -> int:
    rep = run()
    _print(rep)
    write_json_atomic(_OUT, rep, indent=2)
    print(f"wrote {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
