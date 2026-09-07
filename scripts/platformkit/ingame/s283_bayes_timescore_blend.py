"""S283: CPCV measurement of an NBA empirical time-score calibration blend."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psutil

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.s86_nba_every_tick import load_ticks
from scripts.platformkit.eval_gate.s94_nba_early_shrinkage import _recal, logit
from scripts.platformkit.eval_gate.scoring import ece

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs" / "evidence" / "harness"
STEM = "S283_bayes_timescore_blend_2026-09-04"
PREREG = EVIDENCE / "S283_bayes_timescore_blend_2026-09-04_prereg_attempt2.md"
PREREG_SHA256 = "e60457016bc5cb8ba10ed8d460a4593334456bed9a55ea2aedca3bfcd97cf224"
GRID = (0.5, 1.0, 2.0, 4.0)
MIN_CELL_TRAIN, N_GROUPS, EMBARGO_DAYS = 200, 5, 1
BOOTSTRAPS, SEED, BAR = 10_000, 283, 0.004


def verify_preregistration() -> None:
    """Check the committed seal using file bytes normalized to LF (Q1)."""
    data = PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, seal = data.split(b"Seal SHA-256: ", 1)
    assert hashlib.sha256(prefix).hexdigest() == PREREG_SHA256
    assert seal.decode("ascii").strip() == PREREG_SHA256


def _stamp(value: Any) -> str:
    return pd.Timestamp(value, unit="s", tz="UTC").isoformat()


def states_from_ticks(ticks: pd.DataFrame) -> list[dict]:
    """Create exactly one vintage-checked evaluator state for each tick."""
    ordered = ticks.sort_values(["ts", "game_id", "period", "game_clock_s"], kind="stable").reset_index(drop=True)
    out = []
    for ordinal, row in ordered.iterrows():
        stamp = _stamp(row["ts"])
        key = "%s|%s|%s|%s|%d" % (row["game_id"], row["ts"], row["period"], row["game_clock_s"], ordinal)
        features = {"market_prob": float(row["market_prob"]), "period_bucket": str(row["period_bucket"]),
                    "margin_bucket": str(row["margin_bucket"]), "rem_bucket": str(row["rem_bucket"]),
                    "rem_fraction": float(np.clip(float(row["rem"]) / 48.0, 0.0, 1.0)),
                    "cluster_id": str(row["game_id"])}
        available = (pd.Timestamp(stamp) - pd.Timedelta(microseconds=1)).isoformat()
        out.append({"game_id": key, "state_ts": stamp, "home": str(row["home"]), "away": str(row["away"]),
                    "outcome": int(row["y"]), "features": features,
                    "feature_avail": {name: available for name in features}})
    assert len(out) == len(ticks) == len({state["game_id"] for state in out})
    return out


def _fit_table(train_states: list[dict]) -> tuple[dict[tuple[str, str, str], tuple[int, float]], dict[str, tuple[int, float]]]:
    full: dict[tuple[str, str, str], list[float]] = {}
    parent: dict[str, list[float]] = {}
    for state in train_states:
        feature, y = state["features"], float(state["outcome"])
        key = (feature["period_bucket"], feature["margin_bucket"], feature["rem_bucket"])
        full.setdefault(key, [0.0, 0.0]); full[key][0] += 1; full[key][1] += y
        period = feature["period_bucket"]
        parent.setdefault(period, [0.0, 0.0]); parent[period][0] += 1; parent[period][1] += y
    return ({key: (int(value[0]), value[1] / value[0]) for key, value in full.items()},
            {key: (int(value[0]), value[1] / value[0]) for key, value in parent.items()})


def table_probability(feature: dict, full: dict, parent: dict) -> tuple[float, str]:
    key = (feature["period_bucket"], feature["margin_bucket"], feature["rem_bucket"])
    count, probability = full.get(key, (0, 0.0))
    if count >= MIN_CELL_TRAIN:
        return float(probability), "full_cell"
    parent_count, parent_probability = parent[feature["period_bucket"]]
    assert parent_count > 0
    return float(parent_probability), "period_bucket_parent"


def blend_probability(feature: dict, full: dict, parent: dict, k: float) -> tuple[float, str]:
    table_prob, fallback = table_probability(feature, full, parent)
    weight = float(feature["rem_fraction"]) ** float(k)
    probability = (1.0 - weight) * table_prob + weight * float(feature["market_prob"])
    return float(np.clip(probability, 0.0, 1.0)), fallback


def _fit_candidate(train_states: list[dict]) -> dict:
    full, parent = _fit_table(train_states)
    grid_losses: dict[str, float] = {}
    for k in GRID:
        losses = [(blend_probability(state["features"], full, parent, k)[0] - state["outcome"]) ** 2
                  for state in train_states]
        grid_losses[str(k)] = float(np.mean(losses))
    chosen = min(GRID, key=lambda value: (grid_losses[str(value)], value))
    fallback = sum(table_probability(state["features"], full, parent)[1] == "period_bucket_parent"
                   for state in train_states)
    return {"full": full, "parent": parent, "k": chosen, "grid_brier": grid_losses,
            "train_rows": len(train_states), "train_parent_fallback_rows": fallback}


def _candidate_records(states: list[dict]) -> tuple[list[dict], list[dict]]:
    models: dict[int, dict] = {}
    ordered_models: list[dict] = []

    def predictor(train: list[dict], test: dict, inside: bool) -> float:
        assert inside
        identity = id(train)
        if identity not in models:
            models[identity] = _fit_candidate(train)
            ordered_models.append(models[identity])
        model = models[identity]
        probability, _ = blend_probability(test["features"], model["full"], model["parent"], model["k"])
        return probability

    return cpcv_evaluate(states, predictor, n_groups=N_GROUPS, n_test_groups=1,
                         embargo_days=EMBARGO_DAYS, strict_redaction=True), ordered_models


def _recal_records(states: list[dict]) -> list[dict]:
    models: dict[int, Any] = {}

    def predictor(train: list[dict], test: dict, inside: bool) -> float:
        assert inside
        identity = id(train)
        if identity not in models:
            frame = pd.DataFrame({"logit_market": logit([s["features"]["market_prob"] for s in train]),
                                  "y": [s["outcome"] for s in train]})
            models[identity] = _recal(frame)
        return float(models[identity].predict_proba(logit([test["features"]["market_prob"]]).reshape(-1, 1))[0, 1])

    return cpcv_evaluate(states, predictor, n_groups=N_GROUPS, n_test_groups=1,
                         embargo_days=EMBARGO_DAYS, strict_redaction=True)


def paired_records(states: list[dict]) -> tuple[pd.DataFrame, list[dict]]:
    candidate, folds = _candidate_records(states)
    recal = _recal_records(states)
    cand, null = pd.DataFrame(candidate), pd.DataFrame(recal)
    keys = ["game_id", "ts", "split_id", "n_train", "y"]
    paired = cand.merge(null[keys + ["p_model"]].rename(columns={"p_model": "recal_null"}),
                        on=keys, validate="one_to_one")
    assert len(paired) == len(states) and paired["game_id"].is_unique
    metadata = []
    for split_id, model in enumerate(folds):
        split_rows = paired[paired["split_id"] == split_id]
        assert not split_rows.empty and int(split_rows["n_train"].iloc[0]) == model["train_rows"]
        metadata.append({"split_id": split_id, "n_train": model["train_rows"], "chosen_k": model["k"],
                         "train_grid_brier": model["grid_brier"],
                         "train_parent_fallback_rows": model["train_parent_fallback_rows"],
                         "n_scored_ticks": int(len(split_rows))})
    lookup = {state["game_id"]: state["features"] for state in states}
    paired["cluster_id"] = paired["game_id"].map(lambda key: lookup[key]["cluster_id"])
    paired["market_prob"] = paired["game_id"].map(lambda key: lookup[key]["market_prob"])
    paired["table_source"] = paired.apply(
        lambda row: blend_probability(lookup[row["game_id"]], folds[int(row["split_id"])]["full"],
                                      folds[int(row["split_id"])]["parent"], folds[int(row["split_id"])]["k"])[1], axis=1)
    paired = paired.rename(columns={"p_model": "blended"})
    paired["loss_recal_null"] = (paired["recal_null"] - paired["y"]) ** 2
    paired["loss_blended"] = (paired["blended"] - paired["y"]) ** 2
    return paired, metadata


def _cluster_ci(rows: pd.DataFrame) -> list[float]:
    grouped = rows.groupby("cluster_id", sort=True).agg(
        n=("y", "size"), null_loss=("loss_recal_null", "sum"), blend_loss=("loss_blended", "sum"))
    assert len(grouped) >= 30
    rng = np.random.default_rng(SEED)
    values = np.empty(BOOTSTRAPS)
    n, null, blend = (grouped[column].to_numpy(float) for column in ("n", "null_loss", "blend_loss"))
    for index in range(BOOTSTRAPS):
        draw = rng.integers(0, len(grouped), len(grouped))
        values[index] = (null[draw].sum() - blend[draw].sum()) / n[draw].sum()
    return [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]


def summarize(rows: pd.DataFrame, folds: list[dict]) -> dict:
    metrics = {"recal_null_brier": float(rows["loss_recal_null"].mean()),
               "blended_brier": float(rows["loss_blended"].mean()),
               "recal_null_ece": float(ece(rows["recal_null"], rows["y"])),
               "blended_ece": float(ece(rows["blended"], rows["y"]))}
    metrics["improvement"] = metrics["recal_null_brier"] - metrics["blended_brier"]
    metrics["improvement_ci95"] = _cluster_ci(rows)
    verdict = "ACCEPT" if metrics["improvement"] >= BAR and metrics["improvement_ci95"][0] > 0.0 else "BELOW_FROZEN_BAR"
    return {"verdict": verdict, "bar": BAR, "evaluation": {"engine": "cpcv_evaluate", "n_groups": N_GROUPS,
            "n_test_groups": 1, "embargo_days": EMBARGO_DAYS, "symmetric_purge": True}, "metrics": metrics,
            "n_ticks": int(len(rows)), "n_game_clusters": int(rows["cluster_id"].nunique()), "folds": folds,
            "sparsity": {"full_cell_ticks": int((rows["table_source"] == "full_cell").sum()),
                           "period_bucket_parent_ticks": int((rows["table_source"] == "period_bucket_parent").sum())}}


def memo(summary: dict) -> str:
    metric = summary["metrics"]
    rows = ["# S283 NBA Bayesian time-score blend", "", "## Verdict: " + summary["verdict"], "",
            "Preregistration: `docs/evidence/harness/S283_bayes_timescore_blend_2026-09-04_prereg_attempt2.md`", "",
            "Preregistration SHA-256: `" + PREREG_SHA256 + "`", "",
            "Premise binding re-run before scoring: `load_ticks` returned 465249 ticks / 1593 games. The source search found no empirical NBA time-score table in `scripts/platformkit` or `tests/platformkit`.",
            "", "| arm | Brier | ECE |", "|---|---:|---:|",
            "| recal_null | %.9f | %.9f |" % (metric["recal_null_brier"], metric["recal_null_ece"]),
            "| blended | %.9f | %.9f |" % (metric["blended_brier"], metric["blended_ece"]), "",
            "Improvement (recal_null Brier minus blended Brier): %+.9f [%.9f, %.9f]. Frozen bar: +0.004." % tuple([metric["improvement"], *metric["improvement_ci95"]]),
            "", "## Sparsity and train-only selection", "",
            "Scored ticks used full cells: %d; named period_bucket parent fallback: %d." % (summary["sparsity"]["full_cell_ticks"], summary["sparsity"]["period_bucket_parent_ticks"]),
            "", "| split | train ticks | scored ticks | chosen k | train Brier grid | train parent fallback ticks |", "|---:|---:|---:|---:|---|---:|"]
    for fold in summary["folds"]:
        rows.append("| %d | %d | %d | %.1f | `%s` | %d |" % (fold["split_id"], fold["n_train"], fold["n_scored_ticks"], fold["chosen_k"], json.dumps(fold["train_grid_brier"], sort_keys=True), fold["train_parent_fallback_rows"]))
    rows += ["", "## Method and reproduction", "", "The shared evaluator ran once for each arm on identical per-tick states, with its symmetric purge and one-day embargo. Both callbacks fit only their supplied train membership. The recal_null callback applies the same `_recal` logistic calibration used by `apply_incumbent(kind=\"recal_null\")`; the candidate callback builds the empirical table and selects k from the frozen grid on that membership.",
             "", "The paired CSV is evaluator records only: each row stores both callback probabilities, losses, stable tick key, cluster id, timestamp, split, and train size. The archive is sufficient to recompute all reported Brier values and the clustered interval.",
             "", "Input: `data/cache/inplay_odds/nba_checkpoints_full.parquet` (2829826 bytes; tabular tick resolution). Route SHA-256: `" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest() + "`. RSS at write: %d bytes." % summary["rss_bytes"],
             "", "Focused test: `python -m pytest tests/platformkit/ingame/test_s283_bayes_timescore_blend.py -q`."]
    return "\n".join(rows) + "\n"


def run(output_dir: Path = EVIDENCE) -> dict:
    verify_preregistration()
    output_dir = Path(output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    ticks = load_ticks()
    states = states_from_ticks(ticks)
    paired, folds = paired_records(states)
    summary = summarize(paired, folds)
    summary.update({"preregistration_path": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
                    "prereg_sha256": PREREG_SHA256, "paired_loss_path": str((output_dir / (STEM + "_paired_loss.csv.gz")).relative_to(ROOT)).replace("\\", "/"),
                    "input": {"path": "data/cache/inplay_odds/nba_checkpoints_full.parquet", "bytes": 2829826,
                              "resolution": "tabular tick", "rows": int(len(ticks))},
                    "rss_bytes": int(psutil.Process().memory_info().rss),
                    "route_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    output_dir.mkdir(parents=True, exist_ok=True)
    paired.to_csv(output_dir / (STEM + "_paired_loss.csv.gz"), index=False, encoding="ascii")
    (output_dir / (STEM + "_summary.json")).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    (output_dir / (STEM + ".md")).write_text(memo(summary), encoding="ascii")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    summary = run(args.output_dir)
    print("S283 verdict=%s improvement=%+.9f clusters=%d" % (summary["verdict"], summary["metrics"]["improvement"], summary["n_game_clusters"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
