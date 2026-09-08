"""Full S255-qualified, snapshot-only simulator measurement for S287."""
from __future__ import annotations
import argparse
import gc
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence
import numpy as np
import pandas as pd
from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier, ece
from scripts.platformkit.ingame import s256_nba_sim_engine_v3 as sim
ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04"
BAR, EMBARGO_DAYS = 0.004, 3
def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _eligible(inputs: sim.Inputs, requested: Sequence[str] | None) -> pd.DataFrame:
    frame = pd.read_csv(inputs.qualification)
    frame["game"] = frame["game"].astype(str)
    dates = {key: pd.to_datetime(frame[key], errors="coerce") for key in
             ("game_date", "player_snapshot_date", "team_snapshot_date")}
    strict = (dates["player_snapshot_date"] < dates["game_date"]) & (dates["team_snapshot_date"] < dates["game_date"])
    if not (strict == frame["qualifies"].astype(bool)).all():
        raise AssertionError("S255 qualification disagrees with strict dates")
    eligible = sorted(frame.loc[strict, "game"].unique())
    chosen = eligible if requested is None else sorted(set(map(str, requested)))
    if len(eligible) != 355 or not chosen or not set(chosen).issubset(eligible):
        raise AssertionError("S287 requires S255-qualified whole-game clusters")
    return frame[frame["game"].isin(chosen)].copy()


def _grid(archive: pd.DataFrame, selected: pd.DataFrame) -> pd.DataFrame:
    dates = selected.set_index("game")[["game_date", "player_snapshot_date", "team_snapshot_date"]]
    picks = []
    for _, block in archive.groupby("game", sort=True):
        for target in sim.GRID_SECONDS:
            picked = block.assign(distance=(block["elapsed"] - target).abs()).sort_values(
                ["distance", "ts", "source_order"], kind="stable").iloc[[0]].copy()
            picked["grid_target_elapsed"] = target
            picks.append(picked)
    grid = pd.concat(picks, ignore_index=True).join(dates, on="game", how="left")
    grid["state_key"] = grid["game"] + ":" + grid["grid_target_elapsed"].astype(str)
    if not grid.state_key.is_unique or len(grid) != grid.game.nunique() * len(sim.GRID_SECONDS):
        raise AssertionError("one evaluator state is required for every game-target tick")
    return grid.sort_values(["ts", "game", "grid_target_elapsed"], kind="stable").reset_index(drop=True)


def score(requested: Sequence[str] | None = None, inputs: sim.Inputs = sim.Inputs()) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    before = {name: _sha(path) for name, path in asdict(inputs).items()}
    md5 = {name: _md5(path) for name, path in asdict(inputs).items() if name != "archive"}
    identity = {"s256_module_sha256": _sha(Path(sim.__file__)), "s287_entrypoint_sha256": _sha(Path(__file__))}
    selected = _eligible(inputs, requested)
    grid = _grid(sim.read_archive(selected.game.tolist(), inputs.archive), selected)
    pmean, tmean = sim.read_snapshots(inputs, selected)
    states, fills = sim.make_states(grid, pmean, tmean)
    del selected, pmean, tmean
    gc.collect()
    print(f"RSS BEFORE SCORING {sim._rss():.2f} MB", flush=True)
    peak = sim._rss()

    def callback(_train: list[dict], test: dict, _inside: bool) -> float:
        nonlocal peak
        value = sim.price(test["features"])
        peak = max(peak, sim._rss())
        return value

    records = cpcv_evaluate(states, callback, n_groups=8, n_test_groups=1, embargo_days=EMBARGO_DAYS, strict_redaction=True)
    pred = pd.DataFrame(records).rename(columns={"game_id": "state_key", "p_model": "p_simulator"})
    if len(pred) != len(grid) or not pred.state_key.is_unique:
        raise AssertionError("shared evaluator did not emit exactly one record per scored tick")
    scored = grid.merge(pred[["state_key", "split_id", "p_simulator", "n_train"]], on="state_key", validate="one_to_one")
    y = scored.outcome_home_win.to_numpy(float)
    arms = {"market": scored.market_prob.to_numpy(float), "recal_null": scored.p_null.to_numpy(float), "simulator": scored.p_simulator.to_numpy(float)}
    for name, values in arms.items():
        scored[f"loss_{name}"] = (values - y) ** 2
    scored["paired_loss_recal_null_minus_simulator"] = scored.loss_recal_null - scored.loss_simulator
    per_game = scored.groupby("game", as_index=False).agg(cluster_id=("cluster_id", "first"), timestamp=("state_key", "first"), n_ticks=("state_key", "size"), loss_recal_null=("loss_recal_null", "mean"), loss_simulator=("loss_simulator", "mean"), paired_loss_recal_null_minus_simulator=("paired_loss_recal_null_minus_simulator", "mean"))
    dm = diebold_mariano(scored.paired_loss_recal_null_minus_simulator, scored.cluster_id)
    after = {name: _sha(path) for name, path in asdict(inputs).items()}
    if before != after:
        raise AssertionError("input identity changed during scoring")
    improvement = float(dm.mean_diff)
    verdict = "AHEAD" if dm.ci95[0] > BAR else ("SCREEN_NULL" if improvement >= 0 else "BEHIND")
    return {"attempt": "S287 full qualified pod", "n_games": int(per_game.game.nunique()), "n_ticks": int(len(scored)), "grid_seconds": list(sim.GRID_SECONDS), "arms": {name: {"brier": brier(values, y), "ece_10": ece(values, y, bins=10)} for name, values in arms.items()}, "improvement_vs_recal_null": improvement, "ci95_game_clustered": list(dm.ci95), "bar": BAR, "verdict": verdict, "peak_rss_mb": peak, "fills": fills, "input_sha256_before": before, "input_sha256_after": after, "input_md5_pod": md5, "code_identity": identity}, scored, per_game


def _write(summary: dict, scored: pd.DataFrame, per_game: pd.DataFrame, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    scored.to_csv(out / "S287_selected_tick_series.csv", index=False)
    per_game.to_csv(out / "S287_per_game_paired_loss_series.csv", index=False)
    (out / "S287_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="ascii")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-ids")
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args()
    summary, scored, per_game = score(args.game_ids.split(",") if args.game_ids else None)
    _write(summary, scored, per_game, args.out_dir)
    for name, values in summary["arms"].items():
        print(f"ARM {name} BRIER {values['brier']:.12f} ECE {values['ece_10']:.12f}")
    print("CI95 %.12f %.12f" % tuple(summary["ci95_game_clustered"]))
    print(f"RSS PEAK {summary['peak_rss_mb']:.2f} MB")
    print("POD MD5 " + json.dumps(summary["input_md5_pod"], sort_keys=True))
    print("FINAL SHA " + _sha(args.out_dir / "S287_summary.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
