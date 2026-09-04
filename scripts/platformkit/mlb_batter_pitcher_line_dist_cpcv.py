"""S274 adapter for shared CPCV scoring of MLB empirical line forecasts."""
from __future__ import annotations

import csv
import ctypes
import hashlib
import json
from collections import defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Iterable

from scripts.platformkit.eval_gate.cpcv_distribution import cpcv_evaluate_distributional
from scripts.platformkit.mlb_batter_pitcher_line_dist import (
    CorpusRow,
    empirical_crps,
    lower_nearest_rank,
    pinball,
    read_settled_corpus,
)

CORPUS = Path("data/frontend/prop_history_corpus_mlb.jsonl")
ARCHIVED = Path("docs/evidence/harness/S244_attempt_2_naive_row_series_2026-09-04.csv")
SUMMARY = Path("docs/evidence/harness/S274_mlb_distribution_evaluator_route_2026-09-04.json")
PAIRED = Path("docs/evidence/harness/S274_mlb_distribution_evaluator_route_paired_losses_2026-09-04.csv")
EVALUATOR = Path("scripts/platformkit/eval_gate/cpcv_distribution.py")
BASELINE = Path("scripts/platformkit/mlb_batter_pitcher_line_dist.py")
EMBARGO_DAYS = 3
N_GROUPS = 778
ARCHIVED_METRICS = {
    "crps": 0.5098297809224259,
    "pinball_q10": 0.08655308369594088,
    "pinball_q50": 0.37323931073931077,
    "pinball_q90": 0.2013804110232682,
}
QUANTILES = (0.10, 0.50, 0.90)


class _MemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def sha256(path: Path) -> str:
    """Return a file's SHA-256 without changing the file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rss_mb(label: str) -> float:
    """Print and enforce this task's Windows working-set limit."""
    counters = _MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MemoryCounters), ctypes.c_ulong]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise OSError("GetProcessMemoryInfo failed")
    value = counters.WorkingSetSize / (1024.0 * 1024.0)
    print("RSS_MB_{0}={1:.6f}".format(label, value))
    if value > 600.0:
        raise MemoryError("MEMORY LIMIT: RSS above 600 MB")
    return value


def _state(row: CorpusRow) -> dict:
    stamp = datetime.combine(row.score_date, time(hour=12))
    return {
        "game_id": "mlb-prop-{0}".format(row.row_index),
        "state_ts": stamp.isoformat(),
        "home": row.player,
        "away": "MLB-LINE",
        "features": {"asof_marker": 0.0},
        "feature_avail": {"asof_marker": stamp.replace(hour=0).isoformat()},
        "outcome": row.observed,
        "player": row.player,
        "row_index": row.row_index,
    }


def build_states(rows: Iterable[CorpusRow]) -> tuple[list[dict], dict[str, int]]:
    """Map every row to one valid evaluator state plus a declared pre-corpus anchor."""
    corpus = list(rows)
    if not corpus:
        raise ValueError("Corpus is empty")
    earliest = min(row.score_date for row in corpus)
    anchor_stamp = datetime.combine(earliest - timedelta(days=1), time(hour=12))
    anchor = {
        "game_id": "s274-pre-corpus-anchor",
        "state_ts": anchor_stamp.isoformat(), "home": "S274-ANCHOR-H", "away": "S274-ANCHOR-A",
        "features": {"asof_marker": 0.0},
        "feature_avail": {"asof_marker": (anchor_stamp - timedelta(days=1)).isoformat()},
        "outcome": 0.0, "player": "__S274_ANCHOR__", "row_index": 0,
    }
    states = [anchor] + [_state(row) for row in corpus]
    return states, {state["game_id"]: int(state["row_index"]) for state in states[1:]}


def distribution_losses(samples: Iterable[float], outcome: float) -> dict[str, float]:
    """Return every preregistered distributional loss for one evaluator callback."""
    values = tuple(float(value) for value in samples)
    quantiles = {q: lower_nearest_rank(values, q) for q in QUANTILES}
    return {
        "crps": empirical_crps(values, outcome),
        "pinball_q10": pinball(outcome, quantiles[0.10], 0.10),
        "pinball_q50": pinball(outcome, quantiles[0.50], 0.50),
        "pinball_q90": pinball(outcome, quantiles[0.90], 0.90),
    }


def _forecast(train: list[dict], test: dict, select_inside: bool) -> list[float]:
    test_date = datetime.fromisoformat(test["state_ts"]).date()
    for state in train:
        train_date = datetime.fromisoformat(state["state_ts"]).date()
        assert abs((train_date - test_date).days) > EMBARGO_DAYS, "symmetric embargo violation"
    samples = [
        float(state["outcome"]) for state in train
        if state.get("player") == test["player"]
        and datetime.fromisoformat(state["state_ts"]).date() < test_date
    ]
    return samples or [0.0]


def _archive_by_index(path: Path) -> dict[int, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {int(row["row_index"]): row for row in csv.DictReader(handle)}


def score(rows: list[CorpusRow], archive_path: Path = ARCHIVED) -> tuple[dict, list[dict]]:
    """Score all corpus rows only through the shared distributional evaluator."""
    states, index_by_game = build_states(rows)
    records = cpcv_evaluate_distributional(
        states, _forecast, distribution_losses, n_groups=N_GROUPS,
        n_test_groups=1, embargo_days=EMBARGO_DAYS, strict_redaction=True,
        allow_keys=("player", "row_index"),
    )
    real_records = [record for record in records if record["game_id"] != "s274-pre-corpus-anchor"]
    if len(real_records) != len(rows) or len({row["game_id"] for row in real_records}) != len(rows):
        raise ValueError("Expected exactly one evaluator record for every corpus row")
    archive = _archive_by_index(archive_path)
    if len(archive) != len(rows):
        raise ValueError("Archived S244 row denominator differs from the corpus")
    by_date: dict[str, list[dict]] = defaultdict(list)
    paired: list[dict] = []
    for record in real_records:
        row_index = index_by_game[record["game_id"]]
        old = archive[row_index]
        item = {
            "cluster_date": record["ts"][:10], "row_index": row_index,
            "game_id": record["game_id"], "ts": record["ts"],
            "forecast_samples_json": json.dumps(record["forecast_samples"], separators=(",", ":")),
            "n_train": record["n_train"],
            "cold_start": int(tuple(record["forecast_samples"]) == (0.0,)),
        }
        for name in ARCHIVED_METRICS:
            item["archived_" + name] = float(old["naive_" + name])
            item["route_" + name] = float(record[name])
            item["delta_" + name] = item["route_" + name] - item["archived_" + name]
        paired.append(item)
        by_date[item["cluster_date"]].append(item)
    summary: dict[str, object] = {
        "cluster_count": len(by_date), "row_count": len(paired),
        "cold_start_rows": sum(int(row["cold_start"]) for row in paired),
        "market_arm": "NULL: premise census has zero non-null market_prob rows",
        "embargo_days": EMBARGO_DAYS, "n_groups": N_GROUPS, "n_test_groups": 1,
        "metrics": {},
    }
    for name, target in ARCHIVED_METRICS.items():
        route = sum(sum(float(row["route_" + name]) for row in group) / len(group)
                    for group in by_date.values()) / len(by_date)
        archived = sum(sum(float(row["archived_" + name]) for row in group) / len(group)
                       for group in by_date.values()) / len(by_date)
        delta = route - archived
        if abs(delta) > 1e-9 or abs(archived - target) > 1e-9:
            raise ValueError("S274 fixed reproduction bar not met for {0}".format(name))
        summary["metrics"][name] = {"archived": archived, "route": route, "delta": delta}
    return summary, sorted(paired, key=lambda row: int(row["row_index"]))


def write_evidence(summary: dict, paired: list[dict], before_rss: float, after_rss: float) -> None:
    """Write the new dated JSON and complete Q9 paired-loss archive."""
    with PAIRED.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(paired[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(paired)
    summary["rss_mb"] = {"before": before_rss, "after": after_rss, "limit": 600.0}
    summary["input"] = {"path": str(CORPUS), "bytes": CORPUS.stat().st_size, "sha256": sha256(CORPUS)}
    with SUMMARY.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> None:
    """Run the sealed S274 local evaluation and archive its evidence."""
    protected_before = {str(path): sha256(path) for path in (EVALUATOR, BASELINE)}
    before = rss_mb("BEFORE")
    summary, paired = score(read_settled_corpus(CORPUS))
    after = rss_mb("AFTER")
    protected_after = {str(path): sha256(path) for path in (EVALUATOR, BASELINE)}
    if protected_before != protected_after:
        raise AssertionError("protected evaluator or baseline identity changed during scoring")
    summary["protected_route_sha256_before"] = protected_before
    summary["protected_route_sha256_after"] = protected_after
    write_evidence(summary, paired, before, after)
    print("S274_ROWS={0}".format(summary["row_count"]))
    print("S274_CLUSTERS={0}".format(summary["cluster_count"]))
    print("S274_MARKET_ARM={0}".format(summary["market_arm"]))
    for name, values in summary["metrics"].items():
        print("S274_{0}_ROUTE={1}".format(name.upper(), values["route"]))
        print("S274_{0}_DELTA={1}".format(name.upper(), values["delta"]))


if __name__ == "__main__":
    main()
