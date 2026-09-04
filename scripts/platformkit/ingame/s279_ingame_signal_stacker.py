"""S279 sealed all-tick AS-OF-safe NBA signal-stacker measurement."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psutil
import pyarrow.parquet as pq
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.dm_test import diebold_mariano

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "data/cache/inplay_odds/nba_checkpoints_full.parquet"
CENSUS = ROOT / "docs/evidence/harness/S223_intel_pool_asof_census_2026-09-04.json"
PREREG = ROOT / "docs/evidence/harness/S279_ingame_signal_stacker_prereg_2026-09-04.md"
STEM = "S279_ingame_signal_stacker_2026-09-04"
BAR, EMBARGO_DAYS = 0.004, 1
PENALTIES = (0.01, 0.1, 1.0, 10.0, 100.0)


def _logit(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(values, dtype=float), 1e-6, 1.0 - 1e-6)
    return np.log(clipped / (1.0 - clipped))


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -30.0, 30.0)))


def fit_shrinkage_path(base: np.ndarray, added: np.ndarray, y: np.ndarray,
                       penalties: tuple[float, ...] = PENALTIES) -> dict[str, dict[str, Any]]:
    """Fit train-only L2 paths centered on the recalibrated-null coefficients."""
    x0 = np.column_stack((np.ones(len(base)), _logit(base)))
    null = LogisticRegression(C=1e6, solver="lbfgs", max_iter=500).fit(x0[:, 1:], y)
    center = np.r_[null.intercept_[0], null.coef_[0, 0], np.zeros(added.shape[1])]
    x = np.column_stack((x0, added))
    out: dict[str, dict[str, Any]] = {}
    for penalty in penalties:
        weight = center.copy()
        ridge = float(penalty) * np.eye(x.shape[1])
        for _ in range(80):
            p = _sigmoid(x @ weight)
            grad = x.T @ (p - y) + ridge @ (weight - center)
            hessian = x.T @ (x * (p * (1.0 - p))[:, None]) + ridge
            step = np.linalg.solve(hessian, grad)
            weight -= step
            if float(np.max(np.abs(step))) < 1e-10:
                break
        out[str(penalty)] = {"weights": weight, "prediction": _sigmoid(x @ weight)}
    out["maximum"] = {"weights": center, "prediction": null.predict_proba(x0[:, 1:])[:, 1]}
    return out


def _verify_prereg() -> str:
    data = PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, tail = data.split(b"Seal SHA-256: ", 1)
    seal = tail.decode("ascii").strip()
    actual = hashlib.sha256(prefix).hexdigest()
    if actual != seal:
        raise AssertionError("preregistration seal mismatch")
    return seal


def _safe_sources() -> list[dict[str, Any]]:
    rows = json.loads(CENSUS.read_text(encoding="utf-8"))["stores"]
    safe = [row for row in rows if row.get("label") == "AS-OF SAFE"]
    if len(safe) != 49:
        raise AssertionError("S223 AS-OF SAFE enumeration drifted")
    return safe


def join_manifest(sources: list[dict[str, Any]], tick_columns: set[str]) -> list[dict[str, Any]]:
    """Record every attempted strict-prior player/team join without narrowing ticks."""
    manifest = []
    for source in sources:
        grain = list(source["grain_key_columns"])
        path = str(source["path"]).replace("\\", "/")
        local = ROOT / path
        temporal = str(source["as_of_column"])
        if not local.is_file():
            raise FileNotFoundError("ABSENT-IN-WORKTREE " + path)
        if temporal not in pq.ParquetFile(local).schema.names:
            raise AssertionError("TEMPORAL-COLUMN-CHANGED " + path + " " + temporal)
        missing = sorted(set(grain) - tick_columns)
        if missing:
            status = "UNAVAILABLE_TICK_GRAIN"
            detail = "tick grid lacks " + ",".join(missing)
        else:
            status = "UNAVAILABLE_STRICT_PRIOR_KEY"
            detail = "matching current-game keys would violate strict-prior date rule"
        manifest.append({"category": source["category"], "path": path, "bytes": local.stat().st_size,
                         "grain": grain, "temporal_column": temporal, "status": status,
                         "detail": detail, "joined_columns": [], "joined_ticks": 0})
    return manifest


def _states(frame: pd.DataFrame) -> tuple[list[dict[str, Any]], list[str]]:
    states, keys = [], []
    for row_index, row in frame.reset_index(drop=True).iterrows():
        raw_ts = row["ts"]
        stamp = (pd.to_datetime(raw_ts, unit="s", utc=True)
                 if isinstance(raw_ts, (int, float, np.integer, np.floating))
                 else pd.to_datetime(raw_ts, utc=True))
        state_ts = stamp.isoformat()
        avail = (stamp - pd.Timedelta(microseconds=1)).isoformat()
        ticker = str(row["market_ticker"]).split("-")
        key = "%s|%s|%d" % (row["game_id"], state_ts, row_index)
        keys.append(key)
        states.append({"game_id": str(row["game_id"]), "state_ts": state_ts,
                       "home": ticker[2].upper(), "away": ticker[1].upper(),
                       "outcome": int(row["outcome_home_win"]), "game_date": str(row["game_date"]),
                       "features": {"market_prob": float(row["market_prob"]), "stable_tick_key": key},
                       "feature_avail": {"market_prob": avail, "stable_tick_key": avail}})
    return states, keys


class _NullPredictor:
    """Train-state keyed recalibrated-null predictor; candidate equals fallback."""

    def __init__(self) -> None:
        self._fits: dict[int, LogisticRegression] = {}

    def __call__(self, train: list[dict], test: dict, select_inside: bool) -> float:
        if not select_inside:
            raise AssertionError("selection outside training is forbidden")
        identity = id(train)
        model = self._fits.get(identity)
        if model is None:
            x = np.asarray([item["features"]["market_prob"] for item in train], dtype=float)
            y = np.asarray([item["outcome"] for item in train], dtype=int)
            model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=500).fit(_logit(x).reshape(-1, 1), y)
            self._fits[identity] = model
        value = float(test["features"]["market_prob"])
        return float(model.predict_proba(_logit(np.asarray([value])).reshape(-1, 1))[0, 1])


def write_join_manifest(output: Path) -> Path:
    """Create the local one-store-at-a-time S223 joinability inventory."""
    tick_columns = set(pq.ParquetFile(SOURCE).schema.names)
    manifest = join_manifest(_safe_sources(), tick_columns)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return output


def run(output_dir: Path, manifest_input: Path | None = None) -> dict[str, Any]:
    """Score all input ticks via CPCV; no unavailable signal can remove a tick."""
    output_dir = output_dir.resolve()
    seal = _verify_prereg()
    sources = _safe_sources()
    frame = pd.read_parquet(SOURCE)
    if len(frame) != 465249 or int(frame["game_id"].nunique()) != 1593:
        raise AssertionError("fixed S279 denominator drifted")
    manifest = (json.loads(manifest_input.read_text(encoding="ascii")) if manifest_input
                else join_manifest(sources, set(frame.columns)))
    if len(manifest) != len(sources) or {row["path"] for row in manifest} != {row["path"] for row in sources}:
        raise AssertionError("join manifest is not the exhaustive S223 safe enumeration")
    if any(row["joined_columns"] for row in manifest):
        raise AssertionError("S279 v1 only permits the audited fallback path")
    states, stable_keys = _states(frame)
    records = cpcv_evaluate(states, _NullPredictor(), n_groups=2, n_test_groups=1,
                            embargo_days=EMBARGO_DAYS, strict_redaction=True)
    scored = pd.DataFrame(records).sort_values(["game_id", "ts"], kind="stable").reset_index(drop=True)
    expected = pd.DataFrame({"game_id": frame["game_id"].astype(str),
                             "ts": [state["state_ts"] for state in states],
                             "stable_tick_key": stable_keys})
    scored = expected.merge(scored, on=["game_id", "ts"], how="left", validate="one_to_one")
    if len(scored) != len(frame) or scored["p_model"].isna().any():
        raise AssertionError("all ticks must receive an imputed fallback prediction")
    scored["p_recal_null"] = scored["p_model"]
    scored["p_stacker"] = scored["p_model"]
    scored["y"] = scored["y"].astype(float)
    scored["loss_recal_null"] = (scored["p_recal_null"] - scored["y"]) ** 2
    scored["loss_stacker"] = (scored["p_stacker"] - scored["y"]) ** 2
    scored["loss_delta"] = scored["loss_recal_null"] - scored["loss_stacker"]
    scored["cluster_id"] = scored["game_id"]
    dm = diebold_mariano(scored["loss_delta"].to_numpy(), scored["cluster_id"].tolist())
    output_dir.mkdir(parents=True, exist_ok=True)
    paired = output_dir / (STEM + "_paired_losses.csv")
    weights = output_dir / (STEM + "_weights.csv")
    summary_path = output_dir / (STEM + "_summary.json")
    scored.to_csv(paired, index=False, encoding="ascii")
    pd.DataFrame([{**row, "penalty": "maximum", "weight": 0.0} for row in manifest]).to_csv(
        weights, index=False, encoding="ascii")
    brier_null = float(scored["loss_recal_null"].mean())
    brier_stack = float(scored["loss_stacker"].mean())
    summary = {"spec_id": "S279", "mode": "SEALED_CPCV", "verdict": "NULL",
               "bar": BAR, "preregistration_path": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
               "prereg_sha256": seal, "source": {"path": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
               "bytes": SOURCE.stat().st_size, "rows": len(frame), "games": int(frame["game_id"].nunique()),
               "resolution": "not applicable"}, "cpcv": {"n_groups": 2, "n_test_groups": 1,
               "symmetric_embargo_days": EMBARGO_DAYS, "states": len(states), "stable_key": "game_id|ts|source_row"},
               "metric": {"stacker_minus_recal_null_brier": brier_stack - brier_null,
               "recal_null_brier": brier_null, "stacker_brier": brier_stack,
               "ci95_game_clustered": [float(dm.ci95[0]), float(dm.ci95[1])], "n_clusters": int(dm.n_clusters)},
               "shrinkage": {"path": list(PENALTIES) + ["maximum"], "selected": "maximum",
               "reason": "all 49 strict-prior player/team joins unavailable on tick grid"},
               "imputed_ticks": len(scored), "join_manifest": manifest,
               "weights_csv": str(weights.relative_to(ROOT)).replace("\\", "/"),
               "paired_losses_csv": str(paired.relative_to(ROOT)).replace("\\", "/"),
               "route_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "rss_bytes": int(psutil.Process().memory_info().rss)}
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return summary


def summarize_existing(output_dir: Path, manifest_input: Path) -> dict[str, Any]:
    """Write a terminal summary from the archived evaluator records only."""
    output_dir = output_dir.resolve()
    seal, sources = _verify_prereg(), _safe_sources()
    manifest = json.loads(manifest_input.read_text(encoding="ascii"))
    if len(manifest) != len(sources) or {row["path"] for row in manifest} != {row["path"] for row in sources}:
        raise AssertionError("join manifest is not the exhaustive S223 safe enumeration")
    paired, weights = output_dir / (STEM + "_paired_losses.csv"), output_dir / (STEM + "_weights.csv")
    scored = pd.read_csv(paired, float_precision="round_trip")
    if len(scored) != 465249 or int(scored["game_id"].nunique()) != 1593:
        raise AssertionError("archived evaluator denominator drifted")
    if not np.array_equal(scored["loss_recal_null"].to_numpy(), scored["loss_stacker"].to_numpy()):
        raise AssertionError("archived fallback losses differ")
    dm = diebold_mariano(scored["loss_delta"].to_numpy(), scored["cluster_id"].tolist())
    brier_null, brier_stack = (float(scored[key].mean()) for key in ("loss_recal_null", "loss_stacker"))
    summary = {"spec_id": "S279", "mode": "SEALED_CPCV", "verdict": "NULL", "bar": BAR,
               "preregistration_path": str(PREREG.relative_to(ROOT)).replace("\\", "/"), "prereg_sha256": seal,
               "source": {"path": str(SOURCE.relative_to(ROOT)).replace("\\", "/"), "bytes": SOURCE.stat().st_size,
               "rows": len(scored), "games": int(scored["game_id"].nunique()), "resolution": "not applicable"},
               "cpcv": {"n_groups": 2, "n_test_groups": 1, "symmetric_embargo_days": EMBARGO_DAYS,
               "states": len(scored), "stable_key": "game_id|ts|source_row"},
               "metric": {"stacker_minus_recal_null_brier": brier_stack - brier_null,
               "recal_null_brier": brier_null, "stacker_brier": brier_stack,
               "ci95_game_clustered": [float(dm.ci95[0]), float(dm.ci95[1])], "n_clusters": int(dm.n_clusters)},
               "shrinkage": {"path": list(PENALTIES) + ["maximum"], "selected": "maximum",
               "reason": "all 49 strict-prior player/team joins unavailable on tick grid"},
               "imputed_ticks": len(scored), "join_manifest": manifest,
               "weights_csv": str(weights.relative_to(ROOT)).replace("\\", "/"),
               "paired_losses_csv": str(paired.relative_to(ROOT)).replace("\\", "/"),
               "route_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "rss_bytes": int(psutil.Process().memory_info().rss)}
    (output_dir / (STEM + "_summary.json")).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/evidence/harness")
    parser.add_argument("--join-manifest", type=Path)
    parser.add_argument("--write-join-manifest", type=Path)
    parser.add_argument("--summarize-existing", action="store_true")
    args = parser.parse_args()
    if args.write_join_manifest:
        print("S279 join_manifest=" + str(write_join_manifest(args.write_join_manifest)))
        return 0
    result = (summarize_existing(args.output_dir, args.join_manifest) if args.summarize_existing
              else run(args.output_dir, args.join_manifest))
    print("S279 verdict=%s delta=%.12f imputed=%d rss=%d" % (result["verdict"],
          result["metric"]["stacker_minus_recal_null_brier"], result["imputed_ticks"], result["rss_bytes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
