"""S264 additive ISO-week and game-first-date partition evidence helpers.

The source S88 calibration table remains unchanged. This module adds two keys to a
new table and reproduces its calibration values through the shared CPCV evaluator.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.scoring import brier

ISO_ALIAS = "iso_week_alias"
GAME_BLOCK = "game_id_block"
SOURCE_TABLE = Path("docs/evidence/harness/s88_phase_recal_2026-09-04.csv")
OUTPUT_TABLE = Path("docs/evidence/harness/S264_s88_phase_recal_game_first_date_2026-09-04.csv")
PAIRED_SERIES = Path("docs/evidence/harness/S264_isoweek_game_id_overlap_paired_loss_2026-09-04.csv")


def iso_week(timestamp: str) -> str:
    """Return the ISO year/week key for one UTC-compatible timestamp."""
    value = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    year, week, _ = value.isocalendar()
    return "%04d-W%02d" % (year, week)


def shared_game_ids(rows: Iterable[Mapping[str, Any]], block_key: str) -> List[str]:
    """Return every game ID assigned to more than one value of ``block_key``."""
    blocks: Dict[str, set[str]] = defaultdict(set)
    for row in rows:
        blocks[str(row["game_id"])].add(str(row[block_key]))
    return sorted(game_id for game_id, values in blocks.items() if len(values) > 1)


def add_partition_keys(rows: Sequence[Mapping[str, Any]],
                       game_first_dates: Optional[Mapping[str, str]] = None) -> List[Dict[str, Any]]:
    """Copy rows and add unchanged ISO aliases plus game-first-date block keys."""
    first_timestamp: Dict[str, str] = {}
    for row in rows:
        game_id, timestamp = str(row["game_id"]), str(row["ts"])
        if game_id not in first_timestamp or timestamp < first_timestamp[game_id]:
            first_timestamp[game_id] = timestamp
    derived_dates = {game_id: timestamp[:10] for game_id, timestamp in first_timestamp.items()}
    game_blocks = dict(game_first_dates) if game_first_dates is not None else derived_dates
    missing = sorted(set(first_timestamp).difference(game_blocks))
    if missing:
        raise ValueError("missing S88 game-first-date blocks for %s" % ",".join(missing))
    return [dict(row, **{ISO_ALIAS: iso_week(str(row["ts"])),
                            GAME_BLOCK: str(game_blocks[str(row["game_id"])])})
            for row in rows]


def read_source_table(path: Path = SOURCE_TABLE) -> List[Dict[str, Any]]:
    """Read the one committed S88 calibration CSV used by this evidence pass."""
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    if not rows:
        raise ValueError("cannot write an empty evidence table")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_partition_table(rows: Sequence[Mapping[str, Any]], path: Path = OUTPUT_TABLE) -> None:
    """Write the additive table with LF row endings for deterministic evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(rows, path)


def _feature_time(timestamp: str) -> str:
    value = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    return (value - timedelta(microseconds=1)).isoformat()


def _states(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    states: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    for row in rows:
        game_id, timestamp = str(row["game_id"]), str(row["ts"])
        key = (game_id, timestamp)
        if key in seen:
            raise ValueError("duplicate source key %s %s" % key)
        seen.add(key)
        states.append({
            "game_id": game_id,
            "state_ts": timestamp.replace("Z", "+00:00"),
            "home": "home:" + game_id,
            "away": "away:" + game_id,
            "outcome": int(float(row["outcome"])),
            "devig_close_prob": float(row["market_prob"]),
            "features": {"published_recal_prob": float(row["recal_prob"])},
            "feature_avail": {"published_recal_prob": _feature_time(timestamp)},
        })
    return states


def _published_probability(_: List[dict], test_state: dict, __: bool) -> float:
    """Evaluator callback: return only the as-of published calibration probability."""
    return float(test_state["features"]["published_recal_prob"])


def cpcv_reproduce(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Produce every reproduction probability via purged, symmetric-embargo CPCV."""
    output = cpcv_evaluate(_states(rows), _published_probability, n_groups=2,
                           n_test_groups=1, embargo_days=1, strict_redaction=True)
    keys = [(str(row["game_id"]), str(row["ts"]).replace("Z", "+00:00")) for row in output]
    if len(output) != len(rows) or len(set(keys)) != len(rows):
        raise AssertionError("CPCV must emit exactly one unique probability per source row")
    return output


def calibration_by_block(rows: Sequence[Mapping[str, Any]], evaluated: Sequence[Mapping[str, Any]],
                         block_key: str) -> Dict[str, Dict[str, float]]:
    """Score evaluator outputs by one additive partition key."""
    source = {(str(row["game_id"]), str(row["ts"]).replace("Z", "+00:00")): row for row in rows}
    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for output in evaluated:
        key = (str(output["game_id"]), str(output["ts"]))
        grouped[str(source[key][block_key])].append(output)
    summary: Dict[str, Dict[str, float]] = {}
    for block, values in sorted(grouped.items()):
        original = [source[(str(value["game_id"]), str(value["ts"]))] for value in values]
        targets = [float(value["y"]) for value in values]
        summary[block] = {
            "n": float(len(values)),
            "brier_recal": brier([float(value["p_model"]) for value in values], targets),
            "brier_incumbent": brier([float(value["model_prob"]) for value in original], targets),
            "brier_market": brier([float(value["market_prob"]) for value in original], targets),
        }
    return summary


def max_abs_summary_difference(left: Mapping[str, Mapping[str, float]],
                               right: Mapping[str, Mapping[str, float]]) -> float:
    """Return the largest absolute value difference across matching summary cells."""
    if set(left) != set(right):
        raise AssertionError("partition keys differ")
    differences = [abs(float(left[key][metric]) - float(right[key][metric]))
                   for key in left for metric in left[key]
                   if metric != "n"]
    return max(differences, default=0.0)


def paired_loss_series(rows: Sequence[Mapping[str, Any]], source_evaluated: Sequence[Mapping[str, Any]],
                       output_evaluated: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Archive one source/output recalibration loss pair for every source state."""
    source = {(str(row["game_id"]), str(row["ts"])): row for row in source_evaluated}
    output = {(str(row["game_id"]), str(row["ts"])): row for row in output_evaluated}
    metadata = {(str(row["game_id"]), str(row["ts"]).replace("Z", "+00:00")): row for row in rows}
    if set(source) != set(output) or set(source) != set(metadata):
        raise AssertionError("source, output, and metadata keys must agree")
    pairs: List[Dict[str, Any]] = []
    for game_id, timestamp in sorted(source):
        source_row, output_row, row = source[(game_id, timestamp)], output[(game_id, timestamp)], metadata[(game_id, timestamp)]
        outcome = float(source_row["y"])
        source_probability, output_probability = float(source_row["p_model"]), float(output_row["p_model"])
        pairs.append({
            "game_id": game_id, "cluster_id": game_id, "ts": timestamp,
            ISO_ALIAS: str(row[ISO_ALIAS]), GAME_BLOCK: str(row[GAME_BLOCK]), "outcome": outcome,
            "source_recal_prob": source_probability, "output_recal_prob": output_probability,
            "source_loss": (source_probability - outcome) ** 2,
            "output_loss": (output_probability - outcome) ** 2,
            "loss_difference": (output_probability - outcome) ** 2 - (source_probability - outcome) ** 2,
        })
    return pairs


def write_paired_loss_series(rows: Sequence[Mapping[str, Any]], path: Path = PAIRED_SERIES) -> None:
    """Write the Q9 source/output per-state differential archive using LF endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(rows, path)
