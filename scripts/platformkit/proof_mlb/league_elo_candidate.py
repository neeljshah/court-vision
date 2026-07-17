"""scripts.platformkit.proof_mlb.league_elo_candidate — CANDIDATE experiment.

HYPOTHESIS: MLB proof V1 fails on AL 2018-19 (ECE .036, slope .661,
calib_beats_raw False) because ``p_home_elo`` comes from a single GLOBAL
``ELO_HFA`` constant (domains/mlb/config.py) applied to every league. Tests
whether a PER-LEAGUE home-field-advantage term (HFA_AL/HFA_NL, fit leak-free
on train seasons only) sharpens AL calibration.

CALIBRATION ONLY -- no dollar-edge claim anywhere in this file's output. An
honest NO-IMPROVEMENT / WORSE verdict is a successful, valid result.

Binding discipline (feedback_gate_baseline_comparability_2026_07_04): baseline
and candidate MUST differ ONLY by the hypothesis under test. Both paths here
share ELO_K, ELO_MEAN, SEASON_REGRESS, sort order, season-regression logic,
the full-corpus WARM REPLAY pattern, odds merge, devig, the isotonic-
calibration recipe, and the V1 train/eval split (proof_mlb/spec.py SPEC).
Only the additive HFA term used per game varies.

domains/mlb/** is imported READ-ONLY -- nothing under it is edited. The
league-aware replay is injected into the REAL, unmodified
``MLBAdapter.feature_bundle()`` path via a scoped ``unittest.mock.patch`` of
the ``walk_forward_elo`` name inside ``domains.mlb.adapter`` (restored right
after each call) -- reuses the existing odds-merge/context/FeatureBundle
machinery verbatim instead of duplicating it.

LEAK DISCIPLINE: HFA_AL/HFA_NL are fit by grid-searching the Brier-minimizing
per-league offset using ONLY rows whose season is in SPEC.train_seasons
(2010-2017); eval seasons (2018-19, 2020-21) are NEVER touched by the fit.
The pre-game elo_home/elo_away used for that fit come from the baseline
(unmodified) ``walk_forward_elo`` warm replay, leak-free by construction.

CEILING (ponytail): the fit uses the BASELINE Elo trajectory (under the
global HFA=24 update rule) as the diff-basis for the offset search, rather
than a fully self-consistent joint fit of HFA and the Elo update path
together -- a minimal, honest first cut, documented in the JSON honest_note.

PRIVATE: MLB odds/results are price-bearing; this script's output is
calibration metrics only (no prices, no P&L).
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import patch

import numpy as np
import pandas as pd

import domains.mlb.adapter as _adapter_mod
from domains.mlb.adapter import MLBAdapter
from domains.mlb.config import ELO_HFA, ELO_K
from domains.mlb.ratings import EloState, _maybe_regress, _sorted, walk_forward_elo
from kernel.validation.proof_metrics import brier, ece, isotonic_calibrate, reliability_slope
from scripts.platformkit.proof_mlb.spec import SPEC
from src.loop.gate import FeatureBundle
from src.loop.signal import Hypothesis

_LEAGUES = ["NL", "AL"]
_HFA_GRID = np.arange(0.0, 61.0, 1.0)
_VERDICT_EPS = 1e-4
_ARTIFACT_REL = Path("data") / "domains" / "mlb" / "league_elo_candidate.json"


# Core replay: reuses _sorted/_maybe_regress/EloState from domains.mlb.ratings
# verbatim; only the HFA lookup differs from the baseline.
def walk_forward_elo_league_hfa(
    games_df: pd.DataFrame,
    hfa_by_league: Dict[str, float],
    default_hfa: float = ELO_HFA,
) -> pd.DataFrame:
    """Leak-free walk-forward Elo replay with a PER-LEAGUE home-field term.

    Bit-identical to ``domains.mlb.ratings.walk_forward_elo`` when every value
    in ``hfa_by_league`` equals ``default_hfa`` (equivalence check in the test
    file) -- everything else (K, mean, regression, sort order) is unchanged.
    """
    df = _sorted(games_df)
    leagues = (
        df["home_league"].astype(str).to_numpy()
        if "home_league" in df.columns
        else np.full(len(df), "", dtype=object)
    )
    state = EloState()
    elo_homes: List[float] = []
    elo_aways: List[float] = []
    elo_diffs: List[float] = []
    p_homes: List[float] = []

    for i in range(len(df)):
        home = str(df["home_team"].iloc[i])
        away = str(df["away_team"].iloc[i])
        season = int(df["season"].iloc[i])
        home_runs = float(df["home_runs"].iloc[i])
        away_runs = float(df["away_runs"].iloc[i])
        hfa = float(hfa_by_league.get(leagues[i], default_hfa))

        _maybe_regress(state, home, season)
        _maybe_regress(state, away, season)

        eh = state.elo[home]
        ea = state.elo[away]
        diff = (eh + hfa) - ea
        p = 1.0 / (1.0 + math.pow(10.0, -diff / 400.0))

        elo_homes.append(eh)
        elo_aways.append(ea)
        elo_diffs.append(diff)
        p_homes.append(p)

        s_home = 1.0 if home_runs > away_runs else 0.0
        delta = ELO_K * (s_home - p)
        state.elo[home] += delta
        state.elo[away] -= delta
        state.counts[home] = state.counts.get(home, 0) + 1
        state.counts[away] = state.counts.get(away, 0) + 1
        state.n_processed += 1

    out = df.copy()
    out["elo_home"] = elo_homes
    out["elo_away"] = elo_aways
    out["elo_diff_hfa"] = elo_diffs
    out["p_home_elo"] = p_homes
    return out


# Leak-free per-league HFA fit (train seasons ONLY; never touches eval years).
def fit_league_hfa(
    games_df: pd.DataFrame,
    train_seasons: Sequence[int],
    leagues: Sequence[str] = ("AL", "NL"),
    grid: Optional[np.ndarray] = None,
    default_hfa: float = ELO_HFA,
) -> Dict[str, float]:
    """Grid-search the Brier-minimizing HFA per league, train seasons only.

    Uses the UNMODIFIED baseline ``walk_forward_elo`` (imported, not edited)
    for pre-game elo_home/elo_away -- those are leak-free snapshots by
    construction. Never reads rows outside ``train_seasons``.
    """
    grid = _HFA_GRID if grid is None else grid
    wf = walk_forward_elo(games_df)  # baseline, unmodified, full-corpus warm replay
    train = wf[wf["season"].isin(list(train_seasons))]
    fitted: Dict[str, float] = {}
    for lg in leagues:
        sub = train[train["home_league"] == lg]
        if sub.empty:
            fitted[lg] = default_hfa
            continue
        diff_base = (sub["elo_home"] - sub["elo_away"]).to_numpy(dtype=float)
        y = (sub["home_runs"].to_numpy(dtype=float) > sub["away_runs"].to_numpy(dtype=float)).astype(float)
        best_hfa, best_brier = default_hfa, float("inf")
        for hfa in grid:
            p = 1.0 / (1.0 + np.power(10.0, -(diff_base + hfa) / 400.0))
            b = float(np.mean((p - y) ** 2))
            if b < best_brier:
                best_brier, best_hfa = b, float(hfa)
        fitted[lg] = best_hfa
    return fitted


# Inject the variant into the REAL adapter.feature_bundle() code path.
def _feature_bundle_variant(
    adapter: MLBAdapter, hyp: Hypothesis, seasons: Sequence[int],
    league_filter: str, hfa_by_league: Dict[str, float],
) -> FeatureBundle:
    def _variant(games_df: pd.DataFrame) -> pd.DataFrame:
        return walk_forward_elo_league_hfa(games_df, hfa_by_league)

    with patch.object(_adapter_mod, "walk_forward_elo", _variant):
        return adapter.feature_bundle(hyp, list(seasons), league_filter=league_filter)


# Scoring (mirrors scripts.platformkit.proof_common.runner.run_v1 exactly).
def _score(train_bundle: FeatureBundle, eval_bundle: FeatureBundle) -> Dict[str, Any]:
    train_p, train_y = train_bundle.signal_col, train_bundle.target
    eval_p_raw, eval_y = eval_bundle.signal_col, eval_bundle.target
    calib_p = isotonic_calibrate(train_p, train_y, eval_p_raw)
    return {
        "n_eval": int(len(eval_y)),
        "raw_brier": brier(eval_p_raw, eval_y),
        "brier": brier(calib_p, eval_y),
        "ece": ece(calib_p, eval_y),
        "slope": reliability_slope(calib_p, eval_y),
    }


def _verdict(base: Dict[str, Any], cand: Dict[str, Any], eps: float = _VERDICT_EPS) -> str:
    """Primary criterion: calibrated Brier (sharpest single number). ECE/slope
    are printed alongside for the reviewer's own read; they do not flip this
    verdict on their own."""
    d = base["brier"] - cand["brier"]  # positive => candidate improves
    if abs(d) <= eps:
        return "NO-IMPROVEMENT"
    return "IMPROVED" if d > 0 else "WORSE"


def run_league(adapter: MLBAdapter, league: str, hfa_by_league: Dict[str, float]) -> Dict[str, Any]:
    hyp = Hypothesis(
        name="mlb_league_elo_hfa_candidate", target="winprob", scope="pregame",
        statement="Per-league HFA Elo variant vs global-HFA baseline", rationale="",
    )
    base_train = adapter.feature_bundle(hyp, SPEC.train_seasons, league_filter=league)
    cand_train = _feature_bundle_variant(adapter, hyp, SPEC.train_seasons, league, hfa_by_league)

    windows: Dict[str, Any] = {}
    for window in SPEC.eval_windows:
        base_eval = adapter.feature_bundle(hyp, window.seasons, league_filter=league)
        cand_eval = _feature_bundle_variant(adapter, hyp, window.seasons, league, hfa_by_league)
        base_cell = _score(base_train, base_eval)
        cand_cell = _score(cand_train, cand_eval)
        windows[window.label] = {
            "baseline": base_cell, "candidate": cand_cell,
            "verdict": _verdict(base_cell, cand_cell),
        }
    return windows


# Report + artifact.
def _fmt_cell(c: Dict[str, Any]) -> str:
    return (f"brier={c['brier']:.5f} ece={c['ece']:.5f} "
            f"slope={c['slope']:.4f} n={c['n_eval']}")


def print_table(results: Dict[str, Any], hfa_by_league: Dict[str, float]) -> None:
    print(f"HFA fit (train seasons {SPEC.train_seasons[0]}-{SPEC.train_seasons[-1]}, "
          f"leak-free): {hfa_by_league}  (baseline global ELO_HFA={ELO_HFA})")
    print("")
    n_improved = n_worse = n_flat = 0
    for league in _LEAGUES:
        for label, cell in results[league].items():
            v = cell["verdict"]
            if v == "IMPROVED":
                n_improved += 1
            elif v == "WORSE":
                n_worse += 1
            else:
                n_flat += 1
            print(f"[{league} {label}] {v}")
            print(f"  baseline : {_fmt_cell(cell['baseline'])}")
            print(f"  candidate: {_fmt_cell(cell['candidate'])}")
    print("")
    print(f"Overall: {n_improved} IMPROVED / {n_flat} NO-IMPROVEMENT / {n_worse} WORSE "
          f"(primary criterion: calibrated Brier, eps={_VERDICT_EPS})")


def write_artifact(repo_root: Path, results: Dict[str, Any], hfa_by_league: Dict[str, float]) -> Path:
    path = repo_root / _ARTIFACT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "edge_claimed": False,
        "honest_note": (
            "Calibration/sharpness diagnostic ONLY -- no dollar-edge claim. "
            "Tests whether a per-league home-field-advantage Elo term sharpens "
            "AL 2018-19 calibration (see docs/JOB_EVIDENCE_PACKET.md do-not-claim "
            "list). HFA_AL/HFA_NL fit leak-free on train seasons only, grid search "
            "against the baseline Elo trajectory's diff-basis -- NOT a fully "
            "self-consistent joint fit of HFA and the Elo update path together; "
            "a converged joint fit could differ. An honest NO-IMPROVEMENT or "
            "WORSE verdict here is a valid, successful result, not a failure."
        ),
        "hfa_by_league": hfa_by_league,
        "baseline_global_hfa": ELO_HFA,
        "train_seasons": list(SPEC.train_seasons),
        "results": results,
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    try:
        adapter = MLBAdapter(repo_root=repo_root)
        games_df = adapter._get_games()
    except FileNotFoundError as exc:
        print(f"[league_elo_candidate] corpus not built: {exc}")
        return 2

    hfa_by_league = fit_league_hfa(games_df, SPEC.train_seasons, leagues=tuple(_LEAGUES))

    results: Dict[str, Any] = {}
    for league in _LEAGUES:
        print(f"[league_elo_candidate] scoring league={league} ...")
        results[league] = run_league(adapter, league, hfa_by_league)

    print_table(results, hfa_by_league)
    artifact_path = write_artifact(repo_root, results, hfa_by_league)
    print(f"\nArtifact written: {artifact_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
