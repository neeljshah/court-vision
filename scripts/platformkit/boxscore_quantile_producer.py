"""Produce S271 attempt-2b game-clustered quantile calibration artifacts."""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Callable, Dict, List

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

from scripts.platformkit.eval_gate.quantile_walkforward import quantile_walk_forward

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "docs" / "evidence" / "harness"
DATE = "2026-09-04_attempt2b"
PREREG_PATH = OUT_DIR / f"S271_boxscore_quantile_prereg_{DATE}.md"
MEMO_PATH = OUT_DIR / f"S271_boxscore_quantile_producer_{DATE}.md"
SUMMARY_PATH = OUT_DIR / f"S271_boxscore_quantile_producer_{DATE}.json"
SAMPLE_PATH = OUT_DIR / f"S271_boxscore_quantile_producer_sample_{DATE}.parquet"
HOLDOUT_START, HOLDOUT_END = pd.Timestamp("2025-10-01"), pd.Timestamp("2026-06-01")
FEATURES = ("prior_count", "prior_mean", "prior_std", "prior_last", "days_since_prior")
QUANTILES = (0.10, 0.50, 0.90)
SPECS = {
    "pts": (ROOT / "data/cache/pts_q50_oof_int95.parquet", "target_pts"),
    "reb": (ROOT / "data/cache/reb_q50_oof_int95.parquet", "target_reb"),
    "ast": (ROOT / "data/cache/ast_q50_oof_int95.parquet", "target_ast"),
}
GAME_LOGS = (ROOT / "data/cache/cv_fix/leaguegamelog_regular_season.parquet",
             ROOT / "data/cache/cv_fix/leaguegamelog_playoffs.parquet")


def build_features(frame: pd.DataFrame, target: str) -> pd.DataFrame:
    """Build each player's features from strictly earlier realized target dates."""
    required = {"player_id", "date", target}
    if missing := required.difference(frame.columns):
        raise ValueError(f"missing required columns: {sorted(missing)}")
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out = out.sort_values(["player_id", "date"], kind="stable").reset_index(drop=True)
    if out.duplicated(["player_id", "date"]).any():
        raise ValueError("duplicate player/date source rows cannot satisfy strict date purge")
    grouped = out.groupby("player_id", sort=False)
    prior = grouped[target]
    out["prior_count"] = grouped.cumcount().astype(float)
    out["prior_mean"] = prior.transform(lambda values: values.shift().expanding().mean()).fillna(0.0)
    out["prior_std"] = prior.transform(lambda values: values.shift().expanding().std(ddof=0)).fillna(0.0)
    out["prior_last"] = prior.shift().fillna(0.0)
    previous_date = grouped["date"].shift()
    out["days_since_prior"] = (out["date"] - previous_date).dt.days.fillna(0.0).astype(float)
    out["feature_source_max_date"] = previous_date.fillna(pd.Timestamp("1900-01-01"))
    if not (out["feature_source_max_date"] < out["date"]).all():
        raise AssertionError("feature source date is at or after scored row date")
    return out


@lru_cache(maxsize=1)
def _logs() -> pd.DataFrame:
    return pd.concat([pd.read_parquet(path) for path in GAME_LOGS], ignore_index=True)


def attach_game_ids(frame: pd.DataFrame, target: str) -> pd.DataFrame:
    """Attach exact NBA game ids using the as-of-safe player/date key only."""
    logs = _logs()[["GAME_ID", "PLAYER_ID", "GAME_DATE"]].copy()
    logs.columns = ["game_id", "player_id", "date"]
    logs["date"] = pd.to_datetime(logs["date"]).dt.normalize()
    if logs.duplicated(["player_id", "date"]).any():
        raise ValueError("ambiguous as-of-safe game-id mapping")
    out = frame.merge(logs, on=["player_id", "date"], how="left", validate="one_to_one")
    heldout = (out.date >= HOLDOUT_START) & (out.date < HOLDOUT_END)
    if out.loc[heldout, "game_id"].isna().any():
        raise AssertionError("held-out row lacks an exact NBA game id")
    out["game_id"] = out["game_id"].fillna("source:" + out.player_id.astype(str) + ":" +
                                              out.date.dt.strftime("%Y%m%d"))
    return out


def _pinball(target: np.ndarray, prediction: np.ndarray) -> np.ndarray:
    return 0.5 * np.abs(target - prediction)


def _bootstrap(groups: List[np.ndarray], reducer: Callable[[np.ndarray], float]) -> List[float]:
    generator = np.random.default_rng(271)
    estimates = [float(reducer(np.concatenate([groups[index] for index in
                 generator.integers(0, len(groups), len(groups))]))) for _ in range(2000)]
    return [float(np.quantile(estimates, 0.025)), float(np.quantile(estimates, 0.975))]


def _metrics(records: List[dict]) -> Dict[str, object]:
    scored = pd.DataFrame(records)
    if scored.empty or not scored.evaluator_output.eq(True).all():
        raise AssertionError("metrics require evaluator output records only")
    groups = [group.index.to_numpy() for _, group in scored.groupby("game_id", sort=True)]
    if len(groups) < 30:
        raise ValueError(f"only {len(groups)} game clusters; need at least 30")
    inside, loss = scored.inside_80.to_numpy(float), scored.pinball_q50.to_numpy(float)
    return {"n_rows": int(len(scored)), "n_game_clusters": int(len(groups)), "nominal_coverage": 0.80,
            "empirical_coverage": float(inside.mean()), "coverage_ci95": _bootstrap([inside[i] for i in groups], np.mean),
            "pinball_q50": float(loss.mean()), "pinball_q50_ci95": _bootstrap([loss[i] for i in groups], np.mean)}


def _states(frame: pd.DataFrame, target: str) -> List[dict]:
    return [{"game_id": str(row.game_id), "state_ts": f"{row.date:%Y-%m-%d}T12:00:00",
             "home": f"player:{row.player_id}", "away": f"game:{row.game_id}", "outcome": float(getattr(row, target)),
             "features": {name: float(getattr(row, name)) for name in FEATURES},
             "feature_avail": {name: f"{row.feature_source_max_date:%Y-%m-%d}T00:00:00" for name in FEATURES}}
            for row in frame.itertuples(index=False)]


def evaluate_states(states: List[dict], stat: str, evaluator=quantile_walk_forward) -> List[dict]:
    """Fit from evaluator train states and score evaluator-emitted quantile records."""
    def fit_predict(train_states: List[dict], tests: List[dict]) -> List[dict]:
        train_x = np.asarray([[state["features"][name] for name in FEATURES] for state in train_states])
        train_y = np.asarray([state["outcome"] for state in train_states], dtype=float)
        test_x = np.asarray([[state["features"][name] for name in FEATURES] for state in tests])
        for done in range(500, len({test["home"] for test in tests}) + 1, 500):
            print(f"FIT_PROGRESS stat={stat.upper()} players={done}")
        predicted = []
        for quantile in QUANTILES:
            model = GradientBoostingRegressor(loss="quantile", alpha=quantile, random_state=271, n_estimators=80,
                learning_rate=0.05, max_depth=2, min_samples_leaf=20, min_samples_split=40).fit(train_x, train_y)
            predicted.append(model.predict(test_x))
        return [dict(zip(("q10", "q50", "q90"), row)) for row in np.sort(np.vstack(predicted).T, axis=1)]

    def score(test: dict, prediction: dict) -> dict:
        target = float(test["outcome"])
        return {"target": target, **{key: float(value) for key, value in prediction.items()},
                "inside_80": float(prediction["q10"] <= target <= prediction["q90"]),
                "pinball_q50": float(_pinball(np.array([target]), np.array([prediction["q50"]]))[0]),
                "game_first_date": test["state_ts"][:10],
                "feature_source_max_date": next(iter(test["feature_avail"].values()))[:10], **test["features"]}
    return evaluator(states, fit_predict, score, embargo_days=1, strict_redaction=True,
                     test_filter=lambda state: HOLDOUT_START <= pd.Timestamp(state["state_ts"][:10]) < HOLDOUT_END)


def _seal() -> str:
    raw = PREREG_PATH.read_bytes().replace(b"\r\n", b"\n")
    prefix, suffix = raw.split(b"SEAL_SHA256:", 1)
    recorded = suffix.splitlines()[0].strip().decode("ascii")
    if hashlib.sha256(prefix).hexdigest() != recorded:
        raise AssertionError("preregistration seal does not match LF-normalized bytes")
    return recorded


def _rss(label: str) -> float:
    import psutil
    value = float(psutil.Process(os.getpid()).memory_info().rss / 1024**2)
    print(f"RSS_MB {label} {value:.2f}")
    return value


def _census(path: Path, target: str) -> None:
    frame = pd.read_parquet(path)
    dates = pd.to_datetime(frame.date)
    print(f"INPUT {path.as_posix()} rows={len(frame)} range={dates.min():%Y-%m-%d}..{dates.max():%Y-%m-%d}")
    for index in np.linspace(0, len(frame) - 1, 5, dtype=int):
        row = frame.iloc[index]
        print(f"REALIZED {path.stem} player_id={row.player_id} date={pd.Timestamp(row.date):%Y-%m-%d} target={row[target]:.1f}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_producer() -> Dict[str, object]:
    """Write S271 attempt-2b evidence from evaluator-owned held-out records."""
    started, seal = perf_counter(), _seal()
    for _, (path, target) in SPECS.items():
        _census(path, target)
    before, per_stat, parts = _rss("before"), {}, []
    for stat, (path, target) in SPECS.items():
        source = pd.read_parquet(path)
        records = evaluate_states(_states(attach_game_ids(build_features(source, target), target), target), stat)
        metrics = _metrics(records)
        metrics.update({"input_path": path.relative_to(ROOT).as_posix(), "input_bytes": path.stat().st_size})
        per_stat[stat], parts = metrics, parts + [pd.DataFrame(records).assign(stat=stat)]
    sample = pd.concat(parts, ignore_index=True)
    if not (pd.to_datetime(sample.feature_source_max_date) < pd.to_datetime(sample.game_first_date)).all():
        raise AssertionError("purge invariant failed before artifact write")
    sample.to_parquet(SAMPLE_PATH, index=False)
    after, wall = _rss("after"), perf_counter() - started
    routes = {path.relative_to(ROOT).as_posix(): _sha256(path) for path in
              (Path(__file__), ROOT / "scripts/platformkit/eval_gate/quantile_walkforward.py",
               ROOT / "scripts/platformkit/eval_gate/walkforward.py", ROOT / "scripts/platformkit/eval_gate/cpcv_engine.py")}
    summary = {"gap_id": "S271", "attempt": "2b", "preregistration": PREREG_PATH.relative_to(ROOT).as_posix(),
               "preregistration_seal_sha256": seal, "heldout": "2025-10-01..2026-05-31", "per_stat": per_stat,
               "feature_purge_rows_at_or_after": 0, "sample_path": SAMPLE_PATH.relative_to(ROOT).as_posix(),
               "sample_bytes": SAMPLE_PATH.stat().st_size, "rss_mb_before": before, "rss_mb_after": after,
               "wall_seconds": wall, "route_sha256": routes}
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    lines = ["# S271 attempt 2b box-score quantile producer", "", "## Result", "",
             f"Preregistration: `{summary['preregistration']}`", f"Seal SHA-256: `{seal}`", "",
             "| Stat | Rows | Game clusters | Coverage (80 pct nominal) | 95 pct CI | Q50 pinball | 95 pct CI |",
             "|---|---:|---:|---:|---|---:|---|"]
    for stat, result in per_stat.items():
        lines.append(f"| {stat.upper()} | {result['n_rows']} | {result['n_game_clusters']} | {result['empirical_coverage']:.6f} | {result['coverage_ci95']} | {result['pinball_q50']:.6f} | {result['pinball_q50_ci95']} |")
    lines.extend(["", "## Reproduction", "", "- Metrics use evaluator output records only.",
                  "- Every held-out row has an exact NBA game id; bootstrap clusters use that id.",
                  "- Fit/predict consumes only evaluator train states; the evaluator applies a symmetric one-day embargo.",
                  "- Purge assertion: 0 scored rows have a feature source date at or after their game first date.",
                  f"- Pod RSS MB before/after: {before:.2f}/{after:.2f}; wall seconds: {wall:.2f}.",
                  f"- Summary: `{SUMMARY_PATH.relative_to(ROOT).as_posix()}`.", f"- Sample: `{SAMPLE_PATH.relative_to(ROOT).as_posix()}`.",
                  "", "## NOT VERIFIED", "", "- Calibration outside the specified 2025-26 held-out period.",
                  "- Comparative or deployment behavior; this is a calibration measurement only.",
                  "- The rejected attempt's date-cluster and callback-fit limitations are not used here; this rerun uses game clusters and evaluator-owned fitting."])
    MEMO_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return summary


if __name__ == "__main__":
    report = run_producer()
    print(f"S271_ATTEMPT2B_COMPLETE rows={sum(item['n_rows'] for item in report['per_stat'].values())} rss_mb={report['rss_mb_after']:.2f} wall_seconds={report['wall_seconds']:.2f}")
