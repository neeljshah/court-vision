"""S278 pooled CPCV power re-screens for S82 and S119.

Both routes reuse S82's frozen MLB state builder and ``tick_index_in_game``
feature.  S119 additionally uses its existing real-game cluster mapping.  One
evaluator state is constructed for every scored tick; CPCV callbacks produce
both model probabilities and all archived losses are derived from those records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate

ROOT = Path(__file__).resolve().parents[2]
BAR = 0.004
MDE_Z80 = 2.872
N_GROUPS = 5
EMBARGO_DAYS = 1
FEATURE = "tick_index_in_game"


def mde80_from_losses(loss_null: pd.Series, loss_candidate: pd.Series,
                      clusters: pd.Series) -> float:
    """Return the frozen S224 MDE80 from the complete scored cluster series."""
    delta = pd.DataFrame({"delta": loss_null - loss_candidate, "cluster": clusters})
    per_cluster = delta.groupby("cluster", sort=True).delta.mean()
    if len(per_cluster) < 2:
        raise ValueError("at least two scored clusters are required")
    return float(MDE_Z80 * per_cluster.std(ddof=1) / math.sqrt(len(per_cluster)))


def _lf_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _load_rows() -> tuple[list[dict], pd.DataFrame]:
    """Load only the named MLB store through the frozen S82 builders."""
    from scripts.platformkit import hedge_trial_arms as arms
    from scripts.platformkit.eval_gate.stacker import _first_dates, e4_gd_series
    from scripts.platformkit.foundry import ingame_screen as screen

    ticks, features = arms.load_corpus(ROOT / "data" / "cache" / "ingame_grade_joined", "mlb")
    if features is None:
        raise ValueError("MLB feature route unexpectedly absent")
    source = screen.causal_source(ticks)
    table = screen.build_features(source)
    e4 = e4_gd_series(ticks, features)
    return ticks, screen.screen_rows(ticks, e4, table, _first_dates(ticks))


def _cluster_ids(screen_name: str, ticks: list[dict], rows: pd.DataFrame) -> pd.Series:
    if screen_name == "S82":
        return rows["game"].astype(str)
    if screen_name != "S119":
        raise ValueError("unsupported screen %s" % screen_name)
    from scripts.platformkit.foundry.ingame_supply_mlb import real_game_map

    mapping = real_game_map(pd.DataFrame({"game_id": [t["game"] for t in ticks],
                                          "ts": [t["timestamp"] for t in ticks],
                                          "state_summary": [t.get("state_summary", "") for t in ticks]}))
    mapping.pop("_summary")
    keys = list(zip(rows["game"].astype(str), rows["ts"].astype(str)))
    values = pd.Series([mapping.get(key) for key in keys], index=rows.index)
    if values.isna().any():
        raise AssertionError("S119 real-game mapping omitted a scored tick")
    return rows["game"].astype(str) + "#" + values.astype(int).astype(str)


def _states(rows: pd.DataFrame, clusters: pd.Series) -> tuple[list[dict], pd.DataFrame]:
    """Create exactly one stable-key state per scored tick for CPCV."""
    frame = rows.copy().reset_index(drop=True)
    frame["cluster_id"] = clusters.to_numpy()
    frame["state_key"] = ["%s::%d" % (game, row_id)
                          for game, row_id in zip(frame["game"].astype(str), frame["row_id"])]
    if frame["state_key"].duplicated().any():
        raise AssertionError("stable tick keys must be unique")
    states = []
    for row in frame.itertuples(index=False):
        stamp = pd.Timestamp(row.ts).to_pydatetime()
        states.append({"game_id": row.state_key, "state_ts": stamp.isoformat(),
                       "home": str(row.game), "away": str(row.game),
                       "outcome": int(row.y), "devig_close_prob": float(row.market),
                       "features": {"p_e4": float(row.p_e4), "x": float(getattr(row, FEATURE))},
                       "feature_avail": {"p_e4": (stamp - pd.Timedelta(microseconds=1)).isoformat(),
                                         "x": (stamp - pd.Timedelta(microseconds=1)).isoformat()}})
    return states, frame[["state_key", "game", "cluster_id", "ts"]]


def _predictor(candidate: bool) -> Callable[[list[dict], dict, bool], float]:
    """Fit S82's unchanged logistic arms once per CPCV training path."""
    from scripts.platformkit.foundry import ingame_screen as screen
    from scripts.platformkit.foundry.screen_predictor import _logit

    cache: dict[int, tuple[list[dict], tuple]] = {}

    def predict(train: list[dict], test: dict, _select_inside: bool) -> float:
        key = id(train)
        if key not in cache:
            fitted = screen._fit(pd.DataFrame({
                "p_e4": [state["features"]["p_e4"] for state in train],
                "x": [state["features"]["x"] for state in train],
                "y": [state["outcome"] for state in train],
            }), "x")
            if fitted is None:
                raise ValueError("CPCV path has no fit under frozen S82 minimums")
            cache[key] = (train, fitted)  # retain train: ids cannot be recycled across paths
        coef, null, mu, sd = cache[key][1]
        p_e4, x = test["features"]["p_e4"], test["features"]["x"]
        anchor = _logit(p_e4)
        eta = ((coef[0] + coef[1] * anchor + coef[2] * (x - mu) / sd) if candidate
               else (null[0] + null[1] * anchor))
        return float(np.clip(1.0 / (1.0 + np.exp(-eta)), 0.001, 0.999))

    return predict


def rescreen(screen_name: str, output_csv: Path) -> dict:
    """Score one frozen route through CPCV and archive its evaluator-only losses."""
    ticks, rows = _load_rows()
    clusters = _cluster_ids(screen_name, ticks, rows)
    states, meta = _states(rows, clusters)
    candidate = cpcv_evaluate(states, _predictor(True), n_groups=N_GROUPS,
                              n_test_groups=1, embargo_days=EMBARGO_DAYS)
    null = cpcv_evaluate(states, _predictor(False), n_groups=N_GROUPS,
                         n_test_groups=1, embargo_days=EMBARGO_DAYS)
    candidate_frame = pd.DataFrame(candidate).rename(columns={"p_model": "p_candidate"})
    null_frame = pd.DataFrame(null).rename(columns={"p_model": "p_null"})
    joined = candidate_frame.merge(null_frame, on=["split_id", "game_id", "ts", "y", "n_train"],
                                   validate="one_to_one")
    if len(joined) != len(states) or joined["game_id"].duplicated().any():
        raise AssertionError("one evaluator record per scored tick is required")
    paired = joined.merge(meta.drop(columns=["ts"]), left_on="game_id", right_on="state_key",
                          validate="one_to_one")
    paired["loss_null"] = (paired["p_null"] - paired["y"]) ** 2
    paired["loss_candidate"] = (paired["p_candidate"] - paired["y"]) ** 2
    paired["loss_delta"] = paired["loss_null"] - paired["loss_candidate"]
    paired = paired[["state_key", "cluster_id", "game", "ts", "split_id", "n_train", "y",
                     "p_null", "p_candidate", "loss_null", "loss_candidate", "loss_delta"]]
    paired.to_csv(output_csv, index=False)
    result = {"screen": screen_name, "bar": BAR, "evaluator":
              "scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate",
              "n_groups": N_GROUPS, "n_test_groups": 1, "embargo_days_symmetric_nonzero": EMBARGO_DAYS,
              "n_ticks": int(len(paired)), "available_clusters": int(paired.cluster_id.nunique()),
              "brier_null": float(paired.loss_null.mean()),
              "brier_candidate": float(paired.loss_candidate.mean()),
              "brier_delta": float(paired.loss_delta.mean()),
              "mde80": mde80_from_losses(paired.loss_null, paired.loss_candidate, paired.cluster_id),
              "paired_loss_csv": str(output_csv.resolve().relative_to(ROOT)).replace("\\", "/")}
    return result


def summary_from_archive(screen_name: str, path: Path) -> dict:
    """Recompute the required S278 fields only from an evaluator-loss archive."""
    paired = pd.read_csv(path)
    return {"screen": screen_name, "bar": BAR, "evaluator":
            "scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate",
            "n_groups": N_GROUPS, "n_test_groups": 1, "embargo_days_symmetric_nonzero": EMBARGO_DAYS,
            "n_ticks": int(len(paired)), "available_clusters": int(paired.cluster_id.nunique()),
            "brier_null": float(paired.loss_null.mean()),
            "brier_candidate": float(paired.loss_candidate.mean()),
            "brier_delta": float(paired.loss_delta.mean()),
            "mde80": mde80_from_losses(paired.loss_null, paired.loss_candidate, paired.cluster_id),
            "paired_loss_csv": str(path.resolve().relative_to(ROOT)).replace("\\", "/")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--screen", choices=("S82", "S119"))
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    names = (args.screen,) if args.screen else ("S82", "S119")
    paths = {name: args.output_dir / ("S278_%s_paired_losses_2026-09-04.csv" % name) for name in names}
    reports = ([summary_from_archive(name, path) for name, path in paths.items()] if args.summarize_only
               else [rescreen(name, path) for name, path in paths.items()])
    summary = {"row": "S278", "bar": BAR, "input_store": "data/cache/ingame_grade_joined/mlb",
               "preregistrations": {name: "docs/evidence/harness/S278_%s_prereg_2026-09-04.md" % name
                                      for name in names}, "screens": reports}
    output = args.output_dir / "S278_pooled_power_rescreen_2026-09-04.json"
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    for report in reports:
        print("%s clusters=%d mde80=%.12f brier_delta=%+.12f" %
              (report["screen"], report["available_clusters"], report["mde80"], report["brier_delta"]))
    print("SUMMARY %s" % output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
