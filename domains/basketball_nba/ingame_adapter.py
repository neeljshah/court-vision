"""NBA checkpoint-parquet adapter for the shared in-play contract."""
from __future__ import annotations

import argparse
import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.platformkit.eval_gate.adapter_contract import ValidationReport, validate

CHECKPOINT_COLUMNS = (
    "game_id", "game_date", "ts", "period", "game_clock_s", "score_home", "score_away",
    "margin", "market_prob", "traded", "market_ticker", "outcome_home_win", "venue",
)
PREREG_SEAL = "7262bbfaf65eab3709d864fbac88a972bb72d83de633c0c949494da18c61bd67"


@dataclass(frozen=True)
class AdapterFrames:
    """Separate feature and label records plus the source row count."""

    features: list[dict[str, Any]]
    labels: list[dict[str, Any]]
    source_rows: int


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _season(value: Any) -> str:
    year = int(str(value)[:4])
    return "%d-%02d" % (year if int(str(value)[5:7]) >= 7 else year - 1,
                         (year + 1 if int(str(value)[5:7]) >= 7 else year) % 100)


def load_nba_checkpoints(path: Path) -> AdapterFrames:
    """Map NBA checkpoint columns into separate contract feature and label frames."""
    import pandas as pd

    source = Path(path)
    frame = pd.read_parquet(source, columns=list(CHECKPOINT_COLUMNS)).copy()
    frame["ts"] = pd.to_datetime(frame["ts"])
    frame = frame.sort_values(["game_id", "ts"], kind="stable")
    frame["sequence"] = frame.groupby("game_id").cumcount()
    input_hash = _sha256(source)
    code_hash = _sha256(Path(__file__))
    features: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        stamp = row["ts"].to_pydatetime()
        prediction = stamp + pd.Timedelta(microseconds=1)
        known = pd.Timestamp(str(row["game_date"])).to_pydatetime() + pd.Timedelta(days=1)
        game_id, sequence = str(row["game_id"]), int(row["sequence"])
        target_id = "home_win"
        state_key = "%s|%06d|%s" % (game_id, sequence, target_id)
        market = float(row["market_prob"])
        unknown = ("home_team_id", "away_team_id", "line", "ml_source", "ml_time", "ml_probabilities")
        features.append({
            "sport": "basketball", "league": "NBA", "rule_version": "S323-v1",
            "game_id": game_id, "home_team_id": None, "away_team_id": None,
            "season": _season(row["game_date"]), "corpus": source.name, "venue": str(row["venue"]),
            "target_id": target_id,
            "line": None, "class_order": ("away", "home"), "settlement_rule": "home_win",
            "void_rule": "not_declared", "event_id": str(row["market_ticker"]), "sequence": sequence,
            "event_time": stamp.isoformat(), "received_at": stamp.isoformat(),
            "feature_available_at": stamp.isoformat(), "prediction_at": prediction.isoformat(),
            "state": {"period": int(row["period"]), "clock_seconds": float(row["game_clock_s"])},
            "score_home": int(row["score_home"]), "score_away": int(row["score_away"]),
            "status": "checkpoint", "unknown_flags": unknown,
            "provenance": {"input_path": str(source), "venue": str(row["venue"])},
            "m0_source": "checkpoint_market_prob", "m0_time": stamp.isoformat(),
            "m0_probabilities": (1.0 - market, market), "ml_source": None, "ml_time": None,
            "ml_probabilities": None, "candidate_probabilities": (1.0 - market, market),
            "null_probabilities": (1.0 - market, market), "state_key": state_key,
            "exclusions": (), "weight": 1.0, "fold_id": "unassigned", "input_hash": input_hash,
            "code_hash": code_hash, "seal_hash": PREREG_SEAL, "maximum_feed_delay_seconds": 0,
            "features": {"market_prob": market, "margin": float(row["margin"]),
                         "period": float(row["period"]), "clock_seconds": float(row["game_clock_s"])},
        })
        labels.append({"game_id": game_id, "target_id": target_id, "state_key": state_key,
                       "outcome": int(row["outcome_home_win"]), "outcome_known_at": known.isoformat()})
    return AdapterFrames(features, labels, len(frame))


def validate_nba_checkpoints(path: Path) -> tuple[AdapterFrames, ValidationReport]:
    """Load and validate the whole NBA checkpoint input without fitting a predictor."""
    frames = load_nba_checkpoints(path)
    return frames, validate(frames.features, frames.labels)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    frames, report = validate_nba_checkpoints(args.input)
    print("source_rows=%d games=%d status=%s violations=%d" %
          (frames.source_rows, report.n_games, report.status, len(report.violations)))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="", encoding="ascii") as handle:
            writer = csv.DictWriter(handle, fieldnames=("metric", "value"))
            writer.writeheader()
            writer.writerows((
                {"metric": "n_ticks", "value": "%06d" % frames.source_rows},
                {"metric": "n_games", "value": "%06d" % report.n_games},
                {"metric": "n_violations", "value": "%06d" % len(report.violations)},
                {"metric": "status", "value": report.status},
            ))
    for item in report.violations:
        print(item)


if __name__ == "__main__":
    main()
