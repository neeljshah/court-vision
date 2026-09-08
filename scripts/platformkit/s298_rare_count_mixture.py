"""Run the sealed S298 rare-count distribution comparison."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import sys
from bisect import bisect_left
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import psutil

from scripts.platformkit.eval_gate.cpcv_vector_distribution import cpcv_evaluate_vector_distributional; from scripts.platformkit.s298_pmf_shards import pmf_shard_artifacts

ROOT = Path(__file__).resolve().parents[2]
DATE, TAIL, GROUPS, EMBARGO, BOOTS = "2026-09-07", 20, 5, 1, 4000
PREREG = ROOT / "docs/evidence/harness/S298_rare_count_mixture_2026-09-07_prereg.md"; SUPPLEMENT = ROOT / "docs/evidence/harness/S298_rare_count_mixture_2026-09-07_prereg_supplement.md"
OUT = ROOT / "docs/evidence/harness"
SOURCES = (Path("data/domains/basketball_nba/player_boxscores.parquet"),
           Path("data/cache/omni_box_refresh/nba_player_box_extension.parquet"))
STATS, FAMILIES = ("stl", "blk"), ("poisson", "nb2", "hurdle_nb2", "zinb")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rss(label: str) -> float:
    value = psutil.Process(os.getpid()).memory_info().rss / 1024**2
    print("RSS_MB {0} {1:.2f}".format(label, value), flush=True)
    return float(value)


def _seal(path: Path, marker: str) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    prefix, found, value = text.partition(marker)
    if not found:
        raise AssertionError("missing seal for " + path.name)
    actual = hashlib.sha256(prefix.encode("utf-8")).hexdigest()
    if actual != value.strip():
        raise AssertionError("seal mismatch for " + path.name)
    return actual


def _source_frame(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    handle = pq.ParquetFile(path)
    first = handle.read_row_group(0, columns=["game_id", "player_id"]).to_pydict()
    frame = handle.read(columns=["game_id", "player_id", "date", "team", "stl", "blk"]).to_pandas()
    return frame, {"path": path.as_posix(), "bytes": path.stat().st_size, "sha256": _sha(path),
                   "rows": len(frame), "resolution": "tabular; not applicable",
                   "first3": list(zip(map(str, first["game_id"][:3]), map(int, first["player_id"][:3]))),
                   "stl_zero": int((frame.stl == 0).sum()), "blk_zero": int((frame.blk == 0).sum())}


def _load() -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    frames, sources = [], []
    for path in SOURCES:
        frame, info = _source_frame(ROOT / path)
        frames.append(frame)
        sources.append(info)
    expected = [(40520, 53267), (669, 799)]
    actual = [(item["stl_zero"], item["blk_zero"]) for item in sources]
    print("S298_BINDING " + json.dumps({"sources": sources, "zero_counts": actual}, sort_keys=True), flush=True)
    if actual != expected:
        raise AssertionError("S298 binding zero-count premise falsified")
    frame = pd.concat(frames, ignore_index=True).sort_values(["date", "game_id", "player_id"], kind="stable")
    if frame.duplicated(["game_id", "player_id"]).any():
        raise AssertionError("duplicate player-game key")
    return frame.reset_index(drop=True), sources


def _states(frame: pd.DataFrame) -> list[dict[str, Any]]:
    states = []
    for row in frame.itertuples(index=False):
        stamp = pd.Timestamp(row.date).normalize() + pd.Timedelta(hours=12)
        states.append({"game_id": str(row.game_id), "state_ts": stamp.isoformat(),
                       "stable_key": "{0}|{1}".format(row.game_id, row.player_id),
                       "home": "player:{0}".format(row.player_id), "away": "team:{0}".format(row.team),
                       "features": {"strict_prior_marker": 0.0},
                       "feature_avail": {"strict_prior_marker": (stamp - pd.Timedelta(days=1)).isoformat()},
                       "outcome_vector": (int(row.stl), int(row.blk)), "player_id": int(row.player_id)})
    if len({state["stable_key"] for state in states}) != len(states):
        raise AssertionError("one evaluator state per player-game tick violated")
    return states


def _nb_params(values: np.ndarray) -> tuple[float, float]:
    mean = max(float(values.mean()), 1e-12)
    variance = float(values.var()) if len(values) > 1 else mean
    return mean, max((variance - mean) / max(mean * mean, 1e-12), 0.0)


def _poisson(mu: float) -> np.ndarray:
    out = np.array([math.exp(-mu + k * math.log(mu) - math.lgamma(k + 1)) for k in range(TAIL + 1)])
    return np.append(out, max(0.0, 1.0 - float(out.sum())))


def _nb2(mu: float, alpha: float) -> np.ndarray:
    if alpha <= 1e-12:
        return _poisson(mu)
    size, p = 1.0 / alpha, 1.0 / (1.0 + alpha * mu)
    out = np.array([math.exp(math.lgamma(k + size) - math.lgamma(size) - math.lgamma(k + 1)
                             + size * math.log(p) + k * math.log1p(-p)) for k in range(TAIL + 1)])
    return np.append(out, max(0.0, 1.0 - float(out.sum())))


def _pmf(values: np.ndarray, family: str) -> np.ndarray:
    mu, alpha = _nb_params(values)
    base = _poisson(mu) if family == "poisson" else _nb2(mu, alpha)
    if family == "poisson" or family == "nb2":
        result = base
    else:
        zero = float((values == 0).mean())
        if family == "hurdle_nb2":
            pos = max(1.0 - base[0], 1e-15)
            result = np.concatenate(([zero], (1.0 - zero) * base[1:] / pos))
        else:
            excess = max(0.0, min(0.999999, (zero - base[0]) / max(1.0 - base[0], 1e-15)))
            result = (1.0 - excess) * base
            result[0] += excess
    if not np.isfinite(result).all() or (result < -1e-14).any() or abs(float(result.sum()) - 1.0) > 1e-12:
        raise ValueError("non-finite integer CDF/PMF for " + family)
    return np.maximum(result, 0.0) / float(result.sum())


def _inner_select(values: np.ndarray) -> str:
    losses = {family: 0.0 for family in FAMILIES}
    for index in range(1, len(values)):
        for family in FAMILIES:
            losses[family] += _log_loss(_pmf(values[:index], family), int(values[index]))
    return min(FAMILIES, key=lambda family: (losses[family], family))


def _fit_predict(train: list[dict], tests: list[dict]) -> list[dict]:
    ordered = sorted(train, key=lambda state: state["state_ts"])
    stamps = [state["state_ts"] for state in ordered]
    by_player: dict[int, list[int]] = defaultdict(list)
    for index, state in enumerate(ordered):
        by_player[state["player_id"]].append(index)
    prior_vectors = np.asarray([state["outcome_vector"] for state in ordered], dtype=int).reshape(-1, 2)
    selected = {stat: _inner_select(prior_vectors[:, pos]) for pos, stat in enumerate(STATS)}
    result = []
    for test in tests:
        cutoff = bisect_left(stamps, test["state_ts"])
        prior = [index for index in by_player.get(test["player_id"], []) if index < cutoff]
        use = prior or list(range(cutoff))
        if not use:
            vectors = np.zeros((1, 2), dtype=int)
            asof_n = 0
        else:
            vectors = np.asarray([ordered[index]["outcome_vector"] for index in use], dtype=int)
            asof_n = len(use)
        pmfs = {stat: {family: _pmf(vectors[:, pos], family) for family in FAMILIES}
                for pos, stat in enumerate(STATS)}
        result.append({"pmfs": pmfs, "asof_n": asof_n, "used_player_prior": int(bool(prior)),
                       "inner_selected_family": selected, "stable_key": test["stable_key"]})
    return result


def _log_loss(pmf: np.ndarray, observed: int) -> float:
    return -math.log(max(float(pmf[observed] if observed <= TAIL else pmf[-1]), 1e-15))


def _rps(pmf: np.ndarray, observed: int) -> float:
    truth = np.zeros(TAIL + 2); truth[min(observed, TAIL + 1)] = 1.0
    return float(np.mean((np.cumsum(pmf)[:-1] - np.cumsum(truth)[:-1]) ** 2))


def _pit(pmf: np.ndarray, observed: int, key: str) -> float:
    bucket = min(observed, TAIL + 1); lo = float(pmf[:bucket].sum())
    seed = int(hashlib.sha256(key.encode("ascii")).hexdigest()[:16], 16)
    return lo + float(np.random.default_rng(seed).random()) * float(pmf[bucket])


def _score(forecast: dict, outcome: tuple[int, int]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for pos, stat in enumerate(STATS):
        observed = int(outcome[pos])
        for family, pmf in forecast["pmfs"][stat].items():
            prefix = stat + "_" + family
            scores[prefix + "_log"] = _log_loss(pmf, observed)
            scores[prefix + "_rps"] = _rps(pmf, observed)
            scores[prefix + "_zero_abs_error"] = abs(float(pmf[0]) - float(observed == 0))
            scores[prefix + "_pit"] = _pit(pmf, observed, prefix + "|" + forecast["stable_key"])
    return scores


def _summary(records: list[dict], outcomes: dict[str, tuple[int, int]]) -> tuple[list[dict], list[dict]]:
    losses, groups = [], defaultdict(list)
    for record in records:
        for pos, stat in enumerate(STATS):
            observed = int(outcomes[record["stable_key"]][pos])
            for family in FAMILIES:
                pmf = record["forecast"]["pmfs"][stat][family]
                row = {"stable_key": record["stable_key"], "game_id": record["game_id"], "date": record["ts"][:10],
                       "split_id": record["split_id"], "n_train": record["n_train"], "stat": stat, "family": family,
                       "observed": observed, "zero_flag": int(observed == 0), "asof_n": record["forecast"]["asof_n"],
                       "used_player_prior": record["forecast"]["used_player_prior"],
                       "inner_selected_family": record["forecast"]["inner_selected_family"][stat]}
                row.update({"pmf_{0}".format(index): float(value) for index, value in enumerate(pmf[:-1])})
                row["pmf_tail_gt_20"] = float(pmf[-1])
                groups["pmf"].append(row)
                if family != "poisson":
                    base = record["scores"][stat + "_poisson_log"]
                    candidate = record["scores"][stat + "_" + family + "_log"]
                    losses.append({"stable_key": record["stable_key"], "game_id": record["game_id"], "date": record["ts"][:10],
                                   "split_id": record["split_id"], "stat": stat, "family": family,
                                   "poisson_log_loss": base, "candidate_log_loss": candidate,
                                   "improvement": base - candidate, "evaluator_output": True})
    return groups["pmf"], losses


def _intervals(losses: list[dict]) -> list[dict]:
    rng, output, draws_all = np.random.default_rng(298), [], []
    for stat in STATS:
        for family in FAMILIES[1:]:
            rows = [row for row in losses if row["stat"] == stat and row["family"] == family]
            game = pd.DataFrame(rows).groupby("game_id", sort=True).improvement.mean().to_numpy()
            draws = np.array([game[rng.integers(0, len(game), len(game))].mean() for _ in range(BOOTS)])
            output.append({"stat": stat, "family": family, "n_states": len(rows), "n_game_clusters": len(game),
                           "mean_improvement": float(np.mean(game)), "paired_ci_lower": float(np.quantile(draws, .025)),
                           "paired_ci_upper": float(np.quantile(draws, .975)),
                           "one_sided_p": float(np.mean(draws <= 0.0))})
            draws_all.append(draws)
    ordered = sorted(range(len(output)), key=lambda index: output[index]["one_sided_p"])
    for rank, index in enumerate(ordered):
        alpha = .025 / (len(output) - rank)
        output[index]["holm_paired_95_lower"] = float(np.quantile(draws_all[index], alpha))
        output[index]["holm_alpha"] = alpha
    return output


def _secondary(records: list[dict], outcomes: dict[str, tuple[int, int]]) -> list[dict]:
    """Secondary diagnostics per stat and family: RPS, zero reliability, randomized PIT."""
    rows = []
    for pos, stat in enumerate(STATS):
        zeros = np.array([int(outcomes[record["stable_key"]][pos]) == 0 for record in records], dtype=float)
        for family in FAMILIES:
            grab = lambda name, _p=stat + "_" + family: np.array([record["scores"][_p + "_" + name] for record in records])
            mass = np.array([float(record["forecast"]["pmfs"][stat][family][0]) for record in records]); pit = np.sort(grab("pit"))
            rows.append({"stat": stat, "family": family, "n_scored_states": len(records),
                         "mean_log_score": float(grab("log").mean()), "mean_rps": float(grab("rps").mean()),
                         "predicted_zero_mass": float(mass.mean()), "observed_zero_rate": float(zeros.mean()),
                         "zero_reliability_abs_error": float(abs(mass.mean() - zeros.mean())),
                         "mean_state_zero_abs_error": float(grab("zero_abs_error").mean()), "pit_mean": float(pit.mean()),
                         "pit_ks_uniform": float(np.max(np.abs(pit - np.arange(1, len(pit) + 1) / len(pit))))})
    return rows


def _per_fold(records: list[dict]) -> list[dict]:
    """Per-fold held-out state and game-cluster counts; the spec n rail is asserted here."""
    folds: dict[int, list[dict]] = defaultdict(list)
    for record in records:
        folds[record["split_id"]].append(record)
    rows = []
    for split_id in sorted(folds):
        games = {record["game_id"] for record in folds[split_id]}
        assert len(games) >= 30, "fold {0} held out {1} game clusters (< 30)".format(split_id, len(games))
        rows.append({"split_id": split_id, "n_states": len(folds[split_id]), "n_game_clusters": len(games),
                     "n_train": int(folds[split_id][0]["n_train"])})
    return rows


def main() -> None:
    seal, supplement_seal, started, before = _seal(PREREG, "S298_PREREG_SEAL_SHA256="), _seal(SUPPLEMENT, "S298_SUPPLEMENT_SEAL_SHA256="), perf_counter(), _rss("before")
    frame, inputs = _load()
    states = _states(frame)
    records = cpcv_evaluate_vector_distributional(states, _fit_predict, _score, n_groups=GROUPS,
        n_test_groups=1, embargo_days=EMBARGO, strict_redaction=True, allow_keys=("stable_key", "player_id"))
    outcomes = {state["stable_key"]: state["outcome_vector"] for state in states}
    per_fold, secondary = _per_fold(records), _secondary(records, outcomes)
    pmfs, losses = _summary(records, outcomes); intervals = _intervals(losses)
    prefix = OUT / ("S298_rare_count_mixture_" + DATE)
    pmf_path, loss_path, summary_path = Path(str(prefix) + "_pmfs.csv.gz"), Path(str(prefix) + "_paired_losses.csv.gz"), Path(str(prefix) + ".json")
    for path, rows in ((pmf_path, pmfs), (loss_path, losses)):
        with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
            pd.DataFrame(rows).to_csv(handle, index=False)
    after = _rss("after")
    payload = {"prereg_path": PREREG.relative_to(ROOT).as_posix(), "prereg_seal_sha256": seal, "supplement_path": SUPPLEMENT.relative_to(ROOT).as_posix(), "supplement_seal_sha256": supplement_seal,
               "inputs": inputs, "tail_cutoff": TAIL, "n_states": len(records), "n_game_clusters": int(frame.game_id.nunique()),
               "folds": GROUPS, "symmetric_embargo_days": EMBARGO, "intervals": intervals,
               "per_fold": per_fold, "secondary": secondary,
               "route_sha256": {_path.relative_to(ROOT).as_posix(): _sha(_path) for _path in (Path(__file__), ROOT / "scripts/platformkit/eval_gate/cpcv_vector_distribution.py", ROOT / "scripts/platformkit/eval_gate/cpcv_engine.py")},
               "rss_mb_before": before, "rss_mb_after": after, "wall_seconds": perf_counter() - started,
               "artifacts": {"pmfs": pmf_path.name, "paired_losses": loss_path.name, **pmf_shard_artifacts()}}
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("S298_COMPLETE " + json.dumps({"summary": summary_path.as_posix(), "states": len(records), "rss_mb": after}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
