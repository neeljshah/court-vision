"""S308 nested-OOS diagnostic for the S294 STATIC conformal band."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate import cpcv_engine
from scripts.platformkit.eval_gate import ladder_block_predict as ladder
from scripts.platformkit.eval_gate import s101_aci_coverage as s101
from scripts.platformkit.eval_gate import s265_incumbent_conformal_band_sample as s265
from scripts.platformkit.eval_gate import s276_incumbent_conformal_band_full_attempt2 as s294
from scripts.platformkit.eval_gate import s86_nba_every_tick as s86

try:
    import resource
except ImportError:  # pragma: no cover - full route is pod-only
    resource = None

REPO = Path(__file__).resolve().parents[3]
PREREG = REPO / "docs/evidence/harness/S308_preregistration_attempt2_2026-09-08.md"
STEM = "S308_band_functional_validity_attempt2_2026-09-08"
OUT = REPO / "docs/evidence/harness"
JSON = OUT / (STEM + ".json")
MEMBERS = OUT / (STEM + "_memberships.csv")
DEPS = OUT / (STEM + "_train_dependencies.csv")
INTERVALS = OUT / (STEM + "_intervals.csv.gz")
GROUPS = OUT / (STEM + "_groups.csv")
LOG = OUT / (STEM + "_pod_log_tail.txt")
N_BLOCKS, EMBARGO_DAYS = 6, 1
S307_BAND = (-0.02, 0.05)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _in_band(coverage: float | None, nominal: float) -> bool | None:
    """S307's frozen ASYMMETRIC bar, aliased beside S101's symmetric within_tolerance."""
    if coverage is None:
        return None
    return bool(nominal + S307_BAND[0] <= coverage <= nominal + S307_BAND[1])


def _score_summary(frame: pd.DataFrame) -> dict[str, Any]:
    """Per-cell and ALL interval-score totals over one arm's archived group units."""
    out: dict[str, Any] = {}
    for (nominal, cell), part in frame.groupby(["nominal", "cell"]):
        out.setdefault("%.2f" % float(nominal), {})[cell] = {
            "n_groups": int(len(part)), "n_ticks": int(part.n_ticks.sum()),
            "sum_interval_score": float(part.interval_score.sum()),
            "mean_interval_score": float(part.interval_score.mean())}
    return out


def score_summaries(nested_groups: pd.DataFrame, base_groups: pd.DataFrame) -> dict[str, Any]:
    """Nested and baseline summaries with SIGNED deltas: baseline loss minus candidate loss."""
    nested, baseline = _score_summary(nested_groups), _score_summary(base_groups)
    improvement: dict[str, Any] = {}
    for key, cells in nested.items():
        for cell, value in cells.items():
            if cell not in baseline.get(key, {}):
                continue
            base = baseline[key][cell]
            improvement.setdefault(key, {})[cell] = {
                "baseline_mean_interval_score": base["mean_interval_score"],
                "nested_mean_interval_score": value["mean_interval_score"],
                "improvement_mean_interval_score": base["mean_interval_score"] - value["mean_interval_score"],
                "baseline_sum_interval_score": base["sum_interval_score"],
                "nested_sum_interval_score": value["sum_interval_score"],
                "improvement_sum_interval_score": base["sum_interval_score"] - value["sum_interval_score"],
                "baseline_n_groups": base["n_groups"], "nested_n_groups": value["n_groups"]}
    return {"nested": nested, "baseline": baseline, "improvement_baseline_minus_nested": improvement}


def prereg_seal() -> str:
    """Validate the checked-out preregistration without requiring a git index."""
    data = PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, seal = data.split(b"SEAL_SHA256:", 1)
    value = hashlib.sha256(prefix).hexdigest()
    assert value == seal.strip().decode("ascii")
    return value


def _predict(states: list[dict], groups: int, role: str) -> pd.DataFrame:
    """Run the shared CPCV evaluator and retain exactly its per-tick records."""
    predictor = ladder.BlockPredictor(states)
    details: list[dict[str, Any]] = []

    def callback(train: list[dict], test: dict, select: bool) -> float:
        block = int(test["s86_block"])
        feature = test["features"]
        p = predictor(train, test, select)
        details.append({"state_key": feature["state_key"], "source_row": feature["source_row"],
                        "game": test["game_id"], "date": test["state_ts"][:10],
                        "ts": feature["state_key"].rsplit("|", 1)[1], "phase": feature["cell"],
                        "period_bucket": feature["cell"], "cell": feature["cell"],
                        "p": p, "s86_block": block, "role": role})
        return p

    records = cpcv_engine.cpcv_evaluate(
        states, callback, n_groups=groups, n_test_groups=1, embargo_days=EMBARGO_DAYS,
        strict_redaction=True, group_key="s86_block",
        allow_keys=("state_key", "source_row", "market", "margin", "rem", "cell", "logit_p0",
                    "margin_s", "z", "s86_block"))
    out = pd.DataFrame(details)
    out["split_id"] = [r["split_id"] for r in records]
    out["n_train"] = [r["n_train"] for r in records]
    out["y"] = [r["y"] for r in records]
    out["p_evaluator"] = [r["p_model"] for r in records]
    assert len(out) == len(states) and out.state_key.nunique() == len(out)
    assert np.allclose(out.p, out.p_evaluator)
    return out


def _groups(ticks: pd.DataFrame, nominal: float, arm: str) -> tuple[dict, pd.DataFrame]:
    """Score every phase with S101 grouping and archive each group unit."""
    rows, metrics = [], {}
    alpha = 1.0 - nominal
    for cell in s265.PHASES:
        part = ticks if cell == "ALL" else ticks[ticks.phase == cell]
        metric = s101.grouped_coverage(part.p.to_numpy(float), part.y.to_numpy(float),
                                       part.lo_static.to_numpy(float), part.hi_static.to_numpy(float), nominal)
        metrics[cell] = metric
        if metric["coverage"] is None:
            continue
        ordered = part.iloc[np.argsort(part.p.to_numpy(float), kind="mergesort")]
        gids = s101._gid(len(ordered), int(metric["n_groups"]))
        for group_id in range(int(metric["n_groups"])):
            group = ordered.iloc[gids == group_id]
            observed, lo, hi = float(group.y.mean()), float(group.lo_static.mean()), float(group.hi_static.mean())
            distance = max(lo - observed, 0.0, observed - hi)
            rows.append({"nominal": nominal, "arm": arm, "cell": cell, "group_id": group_id,
                         "n_ticks": len(group), "cluster_id": ";".join(sorted(group.game.unique())),
                         "timestamp_start": str(group.ts.min()), "timestamp_end": str(group.ts.max()),
                         "mean_probability": float(group.p.mean()), "observed_frequency": observed,
                         "mean_lo": lo, "mean_hi": hi, "covered": int(distance == 0.0),
                         "half_width": (hi - lo) / 2.0, "interval_score": (hi - lo) + 2.0 * distance / alpha})
    return metrics, pd.DataFrame(rows)


def nested(raw: pd.DataFrame, date_to_block: dict[str, int]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fit calibration OOF models excluding each outer test block."""
    states = s294._states(raw, date_to_block)
    outer = _predict(states, N_BLOCKS, "outer")
    parts, memberships, dependencies = [], [], []
    for held in range(N_BLOCKS):
        development = [state for state in states if state["s86_block"] != held]
        calibration = _predict(development, N_BLOCKS - 1, "inner_oof")
        test = outer[outer.s86_block == held].copy()
        assert set(calibration.s86_block) == set(range(N_BLOCKS)) - {held}
        # MEASURED, not declared: count every held-block tick that reached the inner
        # training pool or the inner OOF calibration predictions. Both must be zero.
        in_pool = sum(1 for state in development if int(state["s86_block"]) == held)
        in_calibration = int((calibration.s86_block == held).sum())
        for inner in sorted(calibration.s86_block.unique()):
            train_blocks = sorted(set(range(N_BLOCKS)) - {held, int(inner)})
            dependencies.append({"outer_block": held, "calibration_block": int(inner),
                                 "train_blocks": ";".join(map(str, train_blocks)),
                                 "outer_label_dependency": in_pool + in_calibration,
                                 "n_outer_ticks_in_inner_train_pool": in_pool,
                                 "n_outer_ticks_in_calibration": in_calibration,
                                 "n_calibration_ticks": int((calibration.s86_block == inner).sum())})
        for nominal in s101.NOMINALS:
            scored, fit = s101.run_fold(calibration, test, "p", round(1.0 - nominal, 10))
            scored["outer_block"] = held
            scored["n_calibration_ticks"] = len(calibration)
            scored["n_calibration_games"] = calibration.game.nunique()
            scored["n_test_games"] = test.game.nunique()
            scored["pooled_half_width"] = fit["pooled_half_width"]
            parts.append(scored)
        memberships.extend({"state_key": row.state_key, "game": row.game, "outer_block": held,
                            "role": "outer_test"} for row in test.itertuples())
        memberships.extend({"state_key": row.state_key, "game": row.game, "outer_block": held,
                            "role": "calibration_oof", "calibration_block": row.s86_block}
                           for row in calibration.itertuples())
    result = pd.concat(parts, ignore_index=True)
    assert len(result) == len(states) * len(s101.NOMINALS) and result.game.nunique() == 1593
    return result, pd.DataFrame(memberships), pd.DataFrame(dependencies)


def run() -> dict[str, Any]:
    """Replay S294 unchanged, then produce only additive S308 evidence."""
    seal = prereg_seal()
    baseline = s294.run()
    raw = s86.load_ticks(s86.CHECKPOINTS)
    rows = s265._rows(raw)
    _, date_to_block = s294.s86_blocks(rows)
    ticks, memberships, dependencies = nested(raw, date_to_block)
    assert dependencies.outer_label_dependency.eq(0).all()
    metrics, groups = {}, []
    base_archive = pd.read_csv(s294.PAIR_CSV, compression="gzip")
    for nominal in s101.NOMINALS:
        sub = ticks[ticks.nominal == nominal]
        cells, archived = _groups(sub, nominal, "nested")
        for metric in cells.values():
            metric["within_s307_band"] = _in_band(metric.get("coverage"), nominal)
        metrics["%.2f" % nominal] = {"cells": cells, "n_ticks": len(sub), "n_games": sub.game.nunique()}
        groups.append(archived)
    group_frame = pd.concat(groups, ignore_index=True)
    base_groups = base_archive[base_archive.record_type == "grouped_coverage"].copy()
    # The prereg formula is width + (2 / alpha) * distance_to_interval, and the distance
    # has BOTH sides. The earlier line read np.maximum(lo - obs, 0.0, obs - hi), whose third
    # positional argument is numpy's `out=`, not a third operand, so the upper-side distance
    # was silently discarded. Both values are archived: the corrected score and the defective
    # lower-side-only one it replaces.
    width = base_groups.mean_hi - base_groups.mean_lo
    scale = 2.0 / (1.0 - base_groups.nominal.astype(float))
    lower = (base_groups.mean_lo - base_groups.observed_frequency).clip(lower=0.0)
    upper = (base_groups.observed_frequency - base_groups.mean_hi).clip(lower=0.0)
    base_groups["half_width"] = width / 2.0
    base_groups["interval_score"] = width + scale * (lower + upper)
    base_groups["interval_score_lower_side_only"] = width + scale * lower
    correction = {"n_groups": int(len(base_groups)),
                  "n_groups_changed": int((upper > 0.0).sum()),
                  "sum_before": float(base_groups.interval_score_lower_side_only.sum()),
                  "sum_after": float(base_groups.interval_score.sum())}
    baseline_all = {key: dict(baseline["static"][key]["cells"]["ALL"]) for key in baseline["static"]}
    for key, value in baseline_all.items():
        value["within_s307_band"] = _in_band(value.get("coverage"), float(key))
    summaries = score_summaries(group_frame, base_groups)
    memberships.to_csv(MEMBERS, index=False, encoding="ascii")
    dependencies.to_csv(DEPS, index=False, encoding="ascii")
    ticks.to_csv(INTERVALS, index=False, compression="gzip", encoding="ascii")
    pd.concat([group_frame, base_groups], ignore_index=True, sort=False).to_csv(GROUPS, index=False, encoding="ascii")
    report = {"row": "S308", "prereg": {"path": str(PREREG.relative_to(REPO)), "seal_sha256": seal},
              "source": {"path": str(s86.CHECKPOINTS.relative_to(REPO)), "bytes": s86.CHECKPOINTS.stat().st_size,
                         "rows": len(raw), "columns": list(raw.columns), "first_3_ids": raw.game_id.head(3).tolist()},
              "baseline": {"route": "s276_incumbent_conformal_band_full_attempt2.run", "all": baseline_all,
                           "interval_score_correction": correction},
              "design": {"engine": "cpcv_evaluate", "blocks": N_BLOCKS, "purge": "game-disjoint",
                         "symmetric_embargo_days": EMBARGO_DAYS,
                         "outer_label_dependencies": int(dependencies.outer_label_dependency.sum()),
                         "coverage_min_group": 400, "global_brier_bar": 0.004}, "nested": metrics,
              "interval_score_summaries": summaries,
              "archives": {str(p.relative_to(REPO)): _hash(p) for p in (MEMBERS, DEPS, INTERVALS, GROUPS)},
              "pod_only_archives": {"root": "/workspace/wt/a18",
                                    "not_fetched": [MEMBERS.relative_to(REPO).as_posix()]},
              "rss_peak_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 if resource else None,
              "code_identity": {p.name: _hash(p) for p in (Path(__file__), Path(cpcv_engine.__file__), Path(s294.__file__), Path(s101.__file__), Path(s265.__file__), Path(s86.__file__), Path(ladder.__file__))}}
    JSON.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="ascii")
    LOG.write_text("BASELINE_ALL_090=%s\nBASELINE_ALL_080=%s\nOUTER_LABEL_DEPENDENCIES=%d\n"
                   "S294_INTERVAL_SCORE_SUM_BEFORE=%.9f\nS294_INTERVAL_SCORE_SUM_AFTER=%.9f\n"
                   "RSS_PEAK_BYTES=%d\n" %
                   (baseline_all["0.90"], baseline_all["0.80"],
                    report["design"]["outer_label_dependencies"], correction["sum_before"],
                    correction["sum_after"], report["rss_peak_bytes"]), encoding="ascii")
    return report


if __name__ == "__main__":
    print(json.dumps(run()["nested"], sort_keys=True))
