"""S270 pooled in-game screen feasibility and sealed S82 re-screen helpers."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.walkforward import walk_forward

ROOT = Path(__file__).resolve().parents[2]
BAR = 0.004
MDE_Z80 = 2.872


@dataclass(frozen=True)
class Screen:
    name: str
    n_eff: float
    mde80: float


@dataclass(frozen=True)
class Pool:
    name: str
    paths: tuple[str, ...]
    column: str
    eligible: bool = True
    note: str = ""


SCREENS = (
    Screen("S06", 296.610988, 0.060079477584),
    Screen("S117", 14.681646, 0.402243272317),
    Screen("S119", 214.827112, 0.007536047364),
    Screen("S58_trial1", 467.272882, 0.034040382412),
    Screen("S79", 800.0, 0.006839709886),
    Screen("S80", 79.251785, 0.042909657298),
    Screen("S82", 214.827112, 0.007536047364),
    Screen("S84", 894.356175, 0.004947967696),
)
RAW_MLB = "data/cache/ingame_grade_joined/mlb"
POOLS = {
    "S06": (Pool("s06_archived_series", ("data/cache/eval_gate/s06_stacker_series_2026-09-03.csv",), "game"),
            Pool("mlb_joined_prefix", (RAW_MLB,), "game_id")),
    "S117": (Pool("s117_archived_series", ("data/cache/eval_gate/s117_soccer_ingame_screen_2026-09-03_series.csv",), "game"),
             Pool("s117_mintrain200_series", ("data/cache/eval_gate/s117_soccer_ingame_screen_mintrain200_2026-09-03_series.csv",), "game")),
    "S119": (Pool("s119_archived_series", ("data/cache/eval_gate/s119_real_game_series_2026-09-03.csv",), "game"),
             Pool("mlb_joined_prefix", (RAW_MLB,), "game_id", False,
                  "s119 is archive-only; pool cannot refit it")),
    "S58_trial1": (Pool("s58_archived_series", ("data/cache/eval_gate/s58_trial1_e2_slice_series_2026-09-03.csv",), "game"),
                  Pool("mlb_joined_prefix", (RAW_MLB,), "game_id")),
    "S79": (Pool("s79_mlb_archived_series", ("data/cache/eval_gate/s79_family_combo_2026-09-03_mlb_gate.csv",), "cluster"),),
    "S80": (Pool("s80_archived_series", ("data/cache/eval_gate/s80_player_grain_2026-09-03.csv",), "game"),
            Pool("mlb_joined_prefix", (RAW_MLB,), "game_id")),
    "S82": (Pool("s82_archived_series", ("data/cache/eval_gate/s82_ingame_screen_series_2026-09-03.csv",), "game"),
            Pool("mlb_joined_prefix", (RAW_MLB,), "game_id")),
    "S84": (Pool("s84_archived_series", ("data/cache/eval_gate/s84_nba_lineup_2026-09-03.csv",), "game"),
            Pool("ingame_eval_cache", ("data/cache/ingame_eval_cache.parquet",), "game_id", False,
                 "incompatible NBA-Stats player-projection key and no on-floor state")),
}


def required_n_eff(screen: Screen) -> float:
    """Closed-form S224 scaling to the frozen +0.004 calibration bar."""
    return screen.n_eff * (screen.mde80 / BAR) ** 2


def _files(paths: Iterable[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        path = ROOT / raw
        if not path.exists():
            print("ABSENT-IN-WORKTREE %s" % raw)
            raise SystemExit(2)
        got = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
        if not got:
            print("ABSENT-IN-WORKTREE %s" % raw)
            raise SystemExit(2)
        out.extend(got)
    return out


def _ids(path: Path, column: str) -> Iterable[str]:
    if path.suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                yield str(row[column])
    elif path.suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield str(json.loads(line)[column])
    elif path.suffix == ".parquet":
        import pyarrow.parquet as pq
        for batch in pq.ParquetFile(path).iter_batches(columns=[column], batch_size=65536):
            yield from (str(value) for value in batch.column(0).to_pylist())
    else:
        raise ValueError("unsupported pool store %s" % path)


def count_pool(pool: Pool) -> dict:
    """Count IDs from exactly one requested column per store, one file at a time."""
    files, values = _files(pool.paths), set()
    for path in files:
        values.update(_ids(path, pool.column))
    return {"name": pool.name, "paths": [str(p.relative_to(ROOT)).replace("\\", "/") for p in files],
            "bytes": sum(p.stat().st_size for p in files), "id_column": pool.column,
            "clusters": len(values), "eligible": pool.eligible, "note": pool.note}


def build_table(counts: dict[str, list[dict]]) -> list[dict]:
    """Return all eight S259 underpowered rows with a deterministic best pool."""
    rows = []
    for screen in SCREENS:
        pools = counts[screen.name]
        eligible = [p for p in pools if p["eligible"]]
        best = max(eligible, key=lambda p: (p["clusters"], p["name"]))
        need = required_n_eff(screen)
        rows.append({"screen": screen.name, "current_n_eff": screen.n_eff, "current_mde80": screen.mde80,
                     "required_n_eff": need, "pools": pools, "best_pool": best["name"],
                     "available_clusters": best["clusters"], "feasible": best["clusters"] >= need,
                     "shortfall": max(0.0, need - best["clusters"])})
    assert len(rows) == 8
    return rows


def feasibility(output: Path) -> dict:
    """Write the S270 real-store feasibility JSON without computing a score."""
    counts = {screen.name: [count_pool(pool) for pool in POOLS[screen.name]] for screen in SCREENS}
    report = {"spec": "S270", "bar": BAR, "rows": build_table(counts)}
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    return report


def _rss_mb() -> float:
    import psutil
    return psutil.Process().memory_info().rss / (1024.0 * 1024.0)


def _states(frame: pd.DataFrame, probabilities: pd.Series) -> list[dict]:
    """One canonical median-tick state per game, matching the shared evaluator grain."""
    states = []
    copied = frame.copy()
    copied["_p"] = probabilities
    for _, block in copied.groupby("game", sort=True):
        row = block.sort_values("ts", kind="stable").iloc[len(block) // 2]
        probability = row._p
        if not np.isfinite(probability):
            continue
        stamp = pd.Timestamp(row["ts"]).to_pydatetime()
        states.append({"game_id": str(row["game"]), "state_ts": stamp.isoformat(),
                       "home": str(row["game"]), "away": str(row["game"]), "outcome": int(row["y"]),
                       "devig_close_prob": float(row["market"]), "features": {"p": float(probability)},
                       "feature_avail": {"p": (stamp - timedelta(microseconds=1)).isoformat()}})
    return states


def _records(states: list[dict]) -> list[dict]:
    return walk_forward(states, lambda _train, test, _inside: test["features"]["p"],
                        select_inside=True).records


def census_identity(loaded: int, exclusions: list[dict], scored_ids: set[str]) -> dict:
    """Validate and summarize the named, game-level S82 score denominator."""
    ids = [str(row["game_id"]) for row in exclusions]
    assert len(ids) == len(set(ids)), "excluded games must be named once"
    assert not set(ids) & scored_ids, "excluded and scored games must be disjoint"
    pre = sum(row["stage"] == "before_eligibility" for row in exclusions)
    no_oof = sum(row["stage"] == "without_finite_oof" for row in exclusions)
    assert loaded == pre + no_oof + len(scored_ids), "census identity failed"
    reasons = {}
    for row in exclusions:
        reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
    return {"loaded_games": loaded, "eligible_games": loaded - pre,
            "finite_oof_games": len(scored_ids), "excluded_before_eligibility": pre,
            "without_finite_oof_prediction": no_oof, "scored_games": len(scored_ids),
            "exclusion_reason_counts": dict(sorted(reasons.items()))}


def _census(ticks, e4, rows: pd.DataFrame, candidate: pd.Series,
            null: pd.Series, paired: pd.DataFrame) -> tuple[dict, list[dict]]:
    loaded_ids = {str(tick["game"]) for tick in ticks}
    eligible_ids = set(rows["game"].astype(str))
    exclusions = []
    for game_id in sorted(loaded_ids - eligible_ids):
        pairs = [(e4[i], tick.get("market_prob")) for i, tick in enumerate(ticks)
                 if str(tick["game"]) == game_id]
        has_e4 = any(value is not None and np.isfinite(float(value)) for value, _ in pairs)
        has_market = any(value is not None and np.isfinite(float(value)) for _, value in pairs)
        reason = "NO_FINITE_E4" if not has_e4 else (
            "NO_FINITE_MARKET_PROB" if not has_market else "NO_FINITE_E4_MARKET_PAIR")
        exclusions.append({"game_id": game_id, "stage": "before_eligibility", "reason": reason})
    paired_ids = set(paired["game_id"].astype(str))
    for game_id in sorted(eligible_ids - paired_ids):
        block = rows[rows["game"].astype(str) == game_id].sort_values("ts", kind="stable")
        index = block.index[len(block) // 2]
        c_ok, n_ok = np.isfinite(candidate.loc[index]), np.isfinite(null.loc[index])
        reason = "NO_FINITE_CANDIDATE_OR_NULL_OOF_AT_MEDIAN_TICK"
        if c_ok and n_ok:
            reason = "NOT_PAIRED_BY_SHARED_EVALUATOR"
        exclusions.append({"game_id": game_id, "stage": "without_finite_oof", "reason": reason})
    census = census_identity(len(loaded_ids), exclusions, paired_ids)
    assert census["eligible_games"] == len(eligible_ids)
    return census, exclusions


def _unchanged_scored_numbers(result: dict) -> None:
    baseline = ROOT / "docs/evidence/harness/S270_attempt_1c_S82_rescreen_2026-09-04_v2.json"
    before = json.loads(baseline.read_text(encoding="utf-8"))
    keys = ("bar", "brier_null", "brier_candidate", "brier_delta", "mde80", "n_ticks",
            "n_game_clusters", "folds")
    unchanged = all(result[key] == before[key] for key in keys)
    print("UNCHANGED_NUMBER_CHECK %s keys=%s" %
          ("PASS" if unchanged else "FAIL", ",".join(keys)))
    if not unchanged:
        raise AssertionError("scored quantities changed; reseal required before reporting")


def rescreen_s82(output_csv: Path, output_json: Path, excluded_csv: Path) -> dict:
    """Re-run frozen S82 predictions, then aggregate only shared-evaluator callbacks."""
    from scripts.platformkit import hedge_trial_arms as arms
    from scripts.platformkit.foundry import ingame_screen as screen
    from scripts.platformkit.eval_gate.stacker import _first_dates, e4_gd_series
    from scripts.platformkit.ingame_replay_scoreboard import discover_store
    ticks, feats = arms.load_corpus(discover_store(ROOT / "data" / "cache"), "mlb")
    source = screen.causal_source(ticks)
    table = screen.build_features(source)
    e4 = e4_gd_series(ticks, feats)
    rows = screen.screen_rows(ticks, e4, table, _first_dates(ticks))
    candidate, null, folds = screen.walk_forward_feature(rows, "tick_index_in_game")
    before = _rss_mb()
    candidate_records, null_records = _records(_states(rows, candidate)), _records(_states(rows, null))
    after = _rss_mb()
    print("RSS_MB before_scoring %.3f after_scoring %.3f" % (before, after))
    if max(before, after) > 600.0:
        raise MemoryError("MEMORY LIMIT %.3f MB" % max(before, after))
    paired = pd.DataFrame(candidate_records).merge(pd.DataFrame(null_records), on=["game_id", "ts", "y"],
                                                    suffixes=("_candidate", "_null"), validate="one_to_one")
    paired["loss_candidate"] = (paired.p_model_candidate - paired.y) ** 2
    paired["loss_null"] = (paired.p_model_null - paired.y) ** 2
    paired["delta"] = paired.loss_null - paired.loss_candidate
    census, exclusions = _census(ticks, e4, rows, candidate, null, paired)
    print("CENSUS loaded=%d eligible=%d finite_oof=%d" %
          (census["loaded_games"], census["eligible_games"], census["finite_oof_games"]))
    print("CENSUS_IDENTITY loaded=%d = excluded_before_eligibility=%d + "
          "without_finite_oof_prediction=%d + scored=%d" %
          (census["loaded_games"], census["excluded_before_eligibility"],
           census["without_finite_oof_prediction"], census["scored_games"]))
    print("EXCLUSION_REASON_COUNTS %s" % census["exclusion_reason_counts"])
    cluster = paired.groupby("game_id", sort=True).delta.mean()
    se = float(cluster.std(ddof=1) / math.sqrt(len(cluster)))
    result = {"screen": "S82", "bar": BAR, "n_ticks": int(len(paired)), "n_game_clusters": int(len(cluster)),
              "brier_null": float(paired.loss_null.mean()), "brier_candidate": float(paired.loss_candidate.mean()),
              "brier_delta": float(paired.delta.mean()), "mde80": MDE_Z80 * se, "folds": folds,
              "rss_mb_before_scoring": before, "rss_mb_after_scoring": after,
              "route_sha256": hashlib.sha256(Path(screen.__file__).read_bytes()).hexdigest(),
              "census": census,
              "evaluator": "scripts.platformkit.eval_gate.walkforward.walk_forward (two callbacks)"}
    paired[["game_id", "ts", "loss_null", "loss_candidate", "delta"]].to_csv(output_csv, index=False)
    pd.DataFrame(exclusions, columns=["game_id", "stage", "reason"]).to_csv(excluded_csv, index=False)
    output_json.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="ascii", newline="\n")
    _unchanged_scored_numbers(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feasibility-json", type=Path)
    parser.add_argument("--rescreen-csv", type=Path)
    parser.add_argument("--rescreen-json", type=Path)
    parser.add_argument("--rescreen-excluded-csv", type=Path)
    args = parser.parse_args()
    if args.feasibility_json:
        feasibility(args.feasibility_json)
    if args.rescreen_csv and args.rescreen_json and args.rescreen_excluded_csv:
        rescreen_s82(args.rescreen_csv, args.rescreen_json, args.rescreen_excluded_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
