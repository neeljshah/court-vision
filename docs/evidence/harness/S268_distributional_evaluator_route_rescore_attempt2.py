"""Reproduce the sealed S268 attempt-2 sibling-route artifacts."""
from __future__ import annotations

import csv
import ctypes
import hashlib
import json
import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from scripts.platformkit.eval_gate.cpcv_engine import (
    cpcv_evaluate,
)
from scripts.platformkit.eval_gate.cpcv_distribution import cpcv_evaluate_distributional
from scripts.platformkit.mlb_batter_pitcher_line_dist import (
    empirical_crps,
    lower_nearest_rank,
    pinball,
    read_settled_corpus,
)

CORPUS = Path("data/frontend/prop_history_corpus_mlb.jsonl")
ARCHIVE = Path("docs/evidence/harness/S244_attempt_2_naive_row_series_2026-09-04.csv")
FIXTURE = Path("docs/evidence/harness/S268_distributional_evaluator_route_fixture_2026-09-04_attempt2.json")
PAIRED = Path("docs/evidence/harness/S268_distributional_evaluator_route_mlb_paired_losses_2026-09-04_attempt2.csv")
ENGINE = Path("scripts/platformkit/eval_gate/cpcv_engine.py")
MASTER_ENGINE_SHA256 = "e9fe694a721658a067bd452911b7f95627897ba4d6c6dccd86cc080f9fa6935c"


def _state(game_id: str, stamp: datetime, home: str, away: str, outcome: float,
           features: dict[str, float], **extra: object) -> dict:
    return {
        "game_id": game_id, "state_ts": stamp.isoformat(), "home": home, "away": away,
        "features": features,
        "feature_avail": {name: stamp.replace(hour=0, minute=0, second=0).isoformat()
                          for name in features},
        "devig_close_prob": 0.5, "truth_wp": 0.5, "outcome": outcome, **extra,
    }


def _fixture_states() -> list[dict]:
    rng = random.Random(268)
    start = datetime(2024, 1, 1, 19)
    target_index = 14
    states = []
    for index in range(32):
        stamp = start + timedelta(days=index)
        target = index == target_index
        states.append(_state(
            "target" if target else "regular-{0}".format(index), stamp,
            "TARGET" if target else "HOME-{0}".format(index),
            "OPPONENT" if target else "AWAY-{0}".format(index),
            float(1 if target else rng.randrange(2)), {"x": rng.random()},
        ))
    target = states[target_index]
    states.append(_state(
        "planted-leak", datetime.fromisoformat(target["state_ts"]) + timedelta(hours=47),
        "TARGET", "LEAK-OPPONENT", float(rng.randrange(2)),
        {"x": rng.random(), "planted_label": float(target["outcome"])},
    ))
    return states


def _score_brier(samples: tuple[float, ...], outcome: float) -> dict[str, float]:
    return {"brier": (samples[0] - outcome) ** 2}


def _write_fixture() -> dict[str, object]:
    states = _fixture_states()

    def forecast(train: list[dict], test: dict, select_inside: bool) -> list[float]:
        if test["game_id"] != "target":
            return [0.5]
        planted = [row for row in train if row["game_id"] == "planted-leak"]
        return [planted[0]["features"]["planted_label"]] if planted else [0.5]

    def scalar(train: list[dict], test: dict, select_inside: bool) -> float:
        return forecast(train, test, select_inside)[0]

    kwargs = {"n_groups": 33, "n_test_groups": 1, "embargo_days": 1}
    honest = cpcv_evaluate_distributional(states, forecast, _score_brier, **kwargs)
    scalar_records = cpcv_evaluate(states, scalar, **kwargs)
    leaky = cpcv_evaluate_distributional(
        states, forecast, _score_brier, **kwargs, debug_disable_purge=True)
    mean = lambda records, field: sum(float(row[field]) for row in records) / len(records)
    scalar_brier = sum((row["p_model"] - row["y"]) ** 2 for row in scalar_records) / len(scalar_records)
    target_honest = next(row["brier"] for row in honest if row["game_id"] == "target")
    target_leaky = next(row["brier"] for row in leaky if row["game_id"] == "target")
    payload = {
        "seed": 268, "regular_state_count": 32, "planted_state_count": 1,
        "normal_record_count": len(honest), "scalar_record_count": len(scalar_records),
        "normal_brier": mean(honest, "brier"), "scalar_brier": scalar_brier,
        "brier_match_delta": abs(mean(honest, "brier") - scalar_brier),
        "purge_off_brier": mean(leaky, "brier"),
        "purge_on_minus_off_brier": mean(honest, "brier") - mean(leaky, "brier"),
        "target_honest_brier": target_honest, "target_leaky_brier": target_leaky,
        "target_leaky_is_strictly_lower": target_leaky < target_honest,
        "states": states,
    }
    with FIXTURE.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return payload


def _mlb_states() -> tuple[list[dict], dict[str, int]]:
    rows = read_settled_corpus(CORPUS)
    earliest = min(row.score_date for row in rows)
    anchor = _state(
        "s268-anchor", datetime.combine(earliest - timedelta(days=1), datetime.min.time()),
        "ANCHOR-H", "ANCHOR-A", 0.0, {"x": 0.0}, player="__S268_ANCHOR__",
    )
    anchor["feature_avail"] = {"x": datetime.combine(
        earliest - timedelta(days=2), datetime.min.time()).isoformat()}
    states = [anchor]
    row_index_by_game = {}
    for row in rows:
        game_id = "mlb-{0}".format(row.row_index)
        stamp = datetime.combine(row.score_date, datetime.min.time()) + timedelta(hours=12)
        states.append(_state(
            game_id, stamp, "HOME-{0}".format(row.row_index), "AWAY-{0}".format(row.row_index),
            row.observed, {"x": 0.0}, player=row.player,
        ))
        row_index_by_game[game_id] = row.row_index
    return states, row_index_by_game


def _score_mlb() -> dict[str, object]:
    states, row_index_by_game = _mlb_states()
    cold_start: dict[str, bool] = {}

    def forecast(train: list[dict], test: dict, select_inside: bool) -> list[float]:
        test_date = date.fromisoformat(test["state_ts"][:10])
        samples = [float(row["outcome"]) for row in train
                   if row.get("player") == test["player"]
                   and date.fromisoformat(row["state_ts"][:10]) < test_date]
        cold_start[test["game_id"]] = not samples
        return samples or [0.0]

    def score(samples: tuple[float, ...], outcome: float) -> dict[str, float]:
        quantiles = {q: lower_nearest_rank(samples, q) for q in (0.10, 0.50, 0.90)}
        return {
            "crps": empirical_crps(samples, outcome),
            "pinball_q10": pinball(outcome, quantiles[0.10], 0.10),
            "pinball_q50": pinball(outcome, quantiles[0.50], 0.50),
            "pinball_q90": pinball(outcome, quantiles[0.90], 0.90),
        }

    records = cpcv_evaluate_distributional(
        states, forecast, score, n_groups=778, n_test_groups=1, embargo_days=3)
    records = [record for record in records if record["game_id"] != "s268-anchor"]
    if len(records) != 3000 or len({record["game_id"] for record in records}) != 3000:
        raise ValueError("Expected one record for each of the 3,000 corpus rows")
    with ARCHIVE.open(encoding="utf-8", newline="") as handle:
        archived = {int(row["row_index"]): row for row in csv.DictReader(handle)}
    by_date: dict[str, list[dict]] = defaultdict(list)
    output = []
    fields = ("crps", "pinball_q10", "pinball_q50", "pinball_q90")
    for record in records:
        row_index = row_index_by_game[record["game_id"]]
        old = archived[row_index]
        cluster_date = record["ts"][:10]
        paired = {
            "cluster_date": cluster_date, "row_index": row_index, "game_id": record["game_id"],
            "ts": record["ts"], "forecast_samples_json": json.dumps(record["forecast_samples"], separators=(",", ":")),
            "n_train": record["n_train"], "cold_start": int(cold_start[record["game_id"]]),
        }
        for field in fields:
            paired["archived_" + field] = old["naive_" + field]
            paired["new_" + field] = record[field]
            paired["delta_" + field] = record[field] - float(old["naive_" + field])
        output.append(paired)
        by_date[cluster_date].append(paired)
    with PAIRED.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(output, key=lambda row: int(row["row_index"])))
    summary = {"cluster_count": len(by_date), "row_count": len(output),
               "cold_start_rows": sum(int(row["cold_start"]) for row in output)}
    for field in fields:
        new_cluster_means = [sum(float(row["new_" + field]) for row in rows) / len(rows)
                             for rows in by_date.values()]
        old_cluster_means = [sum(float(row["archived_" + field]) for row in rows) / len(rows)
                             for rows in by_date.values()]
        summary["new_" + field] = sum(new_cluster_means) / len(new_cluster_means)
        summary["archived_" + field] = sum(old_cluster_means) / len(old_cluster_means)
        summary["delta_" + field] = summary["new_" + field] - summary["archived_" + field]
    return summary


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def _check_rss(label: str) -> float:
    counters = _MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MemoryCounters), ctypes.c_ulong]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    process = kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
        raise OSError("GetProcessMemoryInfo failed")
    rss_mb = counters.WorkingSetSize / (1024.0 * 1024.0)
    print("RSS_MB_{0}={1:.6f}".format(label, rss_mb))
    if rss_mb > 600.0:
        raise MemoryError("MEMORY LIMIT: RSS above 600 MB")
    return rss_mb


def main() -> None:
    engine_hash = _sha256(ENGINE)
    if engine_hash != MASTER_ENGINE_SHA256:
        raise ValueError("cpcv_engine.py does not match master bytes")
    print("CPCV_ENGINE_IDENTITY_SHA256={0}".format(engine_hash))
    _check_rss("BEFORE")
    fixture = _write_fixture()
    summary = _score_mlb()
    _check_rss("AFTER")
    print("FIXTURE_NORMAL_BRIER={0}".format(fixture["normal_brier"]))
    print("FIXTURE_SCALAR_BRIER={0}".format(fixture["scalar_brier"]))
    print("FIXTURE_BRIER_DELTA={0}".format(fixture["brier_match_delta"]))
    print("FIXTURE_PURGE_ON_MINUS_OFF={0}".format(fixture["purge_on_minus_off_brier"]))
    print("FIXTURE_TARGET_LEAKY_LOWER={0}".format(fixture["target_leaky_is_strictly_lower"]))
    for name, value in sorted(summary.items()):
        print("MLB_{0}={1}".format(name.upper(), value))
    for path in (CORPUS, ARCHIVE, FIXTURE, PAIRED):
        print("SHA256_{0}={1}".format(path.name, _sha256(path)))


if __name__ == "__main__":
    main()
