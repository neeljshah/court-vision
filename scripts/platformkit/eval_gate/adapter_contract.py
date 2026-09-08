"""Shared multi-sport in-play adapter schema and pre-fit leak validator."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

from scripts.platformkit.eval_gate.walkforward import walk_forward

FEATURE_FIELDS = (
    "sport", "league", "rule_version", "game_id", "home_team_id", "away_team_id",
    "season", "corpus", "venue", "target_id", "line", "class_order", "settlement_rule",
    "void_rule", "event_id", "sequence", "event_time", "received_at",
    "feature_available_at", "prediction_at", "state", "score_home", "score_away",
    "status", "unknown_flags", "provenance", "m0_source", "m0_time",
    "m0_probabilities", "ml_source", "ml_time", "ml_probabilities",
    "candidate_probabilities", "null_probabilities", "state_key", "exclusions",
    "weight", "fold_id", "input_hash", "code_hash", "seal_hash",
    "maximum_feed_delay_seconds",
)
LABEL_FIELDS = ("game_id", "target_id", "state_key", "outcome", "outcome_known_at")
CENSUS_FIELDS = FEATURE_FIELDS + LABEL_FIELDS
_OUTCOME_WORDS = ("outcome", "final", "result", "settle", "winner")


class AdapterContractError(ValueError):
    """Raised when an adapter fails a pre-fit contract condition."""


@dataclass(frozen=True)
class AdapterSpec:
    """Static identity and embargo declaration for one sport adapter."""

    sport: str
    league: str
    rule_version: str
    maximum_feed_delay_seconds: int


@dataclass(frozen=True)
class ValidationReport:
    """Structured result from validating separate feature and label frames."""

    status: str
    violations: tuple[str, ...]
    n_features: int
    n_labels: int
    n_games: int

    @property
    def accepted(self) -> bool:
        return self.status == "ACCEPT"


def _as_rows(frame: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return list(frame)


def _stamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise TypeError("timestamp is not ISO-8601")


def _missing(row: Mapping[str, Any], fields: Sequence[str]) -> list[str]:
    return [name for name in fields if name not in row]


def _is_unknown(row: Mapping[str, Any], field: str) -> bool:
    flags = row.get("unknown_flags", ())
    return isinstance(flags, (list, tuple, set)) and field in flags


def _time_error(row: Mapping[str, Any], label: Mapping[str, Any]) -> str | None:
    try:
        received = _stamp(row["received_at"])
        available = _stamp(row["feature_available_at"])
        prediction = _stamp(row["prediction_at"])
        known = _stamp(label["outcome_known_at"])
    except (KeyError, TypeError, ValueError) as exc:
        return "unparseable time for %s: %s" % (row.get("state_key"), exc)
    if not received <= available <= prediction < known:
        return "nonmonotone times for %s" % row.get("state_key")
    return None


def _feature_leak(row: Mapping[str, Any]) -> str | None:
    payload = row.get("features", {})
    if not isinstance(payload, Mapping):
        return "features is not a mapping for %s" % row.get("state_key")
    forbidden = sorted(name for name in payload if any(word in name.lower() for word in _OUTCOME_WORDS))
    if forbidden:
        return "outcome-like feature(s) %s for %s" % (forbidden, row.get("state_key"))
    return None


def validate(features: Sequence[Mapping[str, Any]], labels: Sequence[Mapping[str, Any]]) -> ValidationReport:
    """Validate the adapter's separate frames before any predictor is invoked."""
    feature_rows, label_rows = _as_rows(features), _as_rows(labels)
    violations: list[str] = []
    labels_by_key: dict[str, Mapping[str, Any]] = {}
    for index, label in enumerate(label_rows):
        missing = _missing(label, LABEL_FIELDS)
        if missing:
            violations.append("label %d missing %s" % (index, ",".join(missing)))
            continue
        key = str(label["state_key"])
        if key in labels_by_key:
            violations.append("duplicate label state_key %s" % key)
        labels_by_key[key] = label
    seen_keys: set[str] = set()
    game_folds: dict[str, set[str]] = {}
    paired: set[tuple[str, str, str]] = set()
    for index, row in enumerate(feature_rows):
        missing = _missing(row, FEATURE_FIELDS)
        if missing:
            violations.append("feature %d missing %s" % (index, ",".join(missing)))
            continue
        key = str(row["state_key"])
        if key in seen_keys:
            violations.append("duplicate state_key %s" % key)
        seen_keys.add(key)
        label = labels_by_key.get(key)
        if label is None:
            violations.append("missing label for %s" % key)
        elif str(label["game_id"]) != str(row["game_id"]) or str(label["target_id"]) != str(row["target_id"]):
            violations.append("feature-label identity conflict for %s" % key)
        else:
            error = _time_error(row, label)
            if error:
                violations.append(error)
        flags = row["unknown_flags"]
        if not isinstance(flags, (list, tuple, set)) or not all(isinstance(item, str) for item in flags):
            violations.append("invalid unknown_flags for %s" % key)
        else:
            for flag in flags:
                if flag not in FEATURE_FIELDS:
                    violations.append("unknown_flags names undeclared field %s for %s" % (flag, key))
                elif row.get(flag) is not None:
                    violations.append("unknown_flags flag %s names a present field for %s" % (flag, key))
        for field in FEATURE_FIELDS:
            if row[field] is None and not _is_unknown(row, field):
                violations.append("undeclared unknown %s for %s" % (field, key))
        leak = _feature_leak(row)
        if leak:
            violations.append(leak)
        game_folds.setdefault(str(row["game_id"]), set()).add(str(row["fold_id"]))
        pair_key = (str(row["game_id"]), str(row["venue"]), str(row["event_id"]), str(row["sequence"]))
        if pair_key in paired:
            violations.append("paired-side conflict for %s" % (pair_key,))
        paired.add(pair_key)
    for game_id, folds in game_folds.items():
        if len(folds) > 1:
            violations.append("game crosses folds %s" % game_id)
    for key in labels_by_key:
        if key not in seen_keys:
            violations.append("orphan label %s" % key)
    return ValidationReport(
        "ACCEPT" if not violations else "REJECT", tuple(violations), len(feature_rows),
        len(label_rows), len(game_folds),
    )


def require_accepted(features: Sequence[Mapping[str, Any]], labels: Sequence[Mapping[str, Any]]) -> ValidationReport:
    """Validate and raise an explicit pre-fit error when any violation is found."""
    report = validate(features, labels)
    if not report.accepted:
        raise AdapterContractError("; ".join(report.violations))
    return report


def assert_prefix_predictions_identical(
    prefix_states: list[dict[str, Any]], extended_states: list[dict[str, Any]],
    predictor: Callable[[list[dict[str, Any]], dict[str, Any], bool], float],
) -> None:
    """Reject history-rewriting feeds by replaying a fixed prefix under strict redaction."""
    prefix = walk_forward(prefix_states, predictor, strict_redaction=True, guard_state_keys=True).records
    replay = walk_forward(extended_states[:len(prefix_states)], predictor, strict_redaction=True,
                          guard_state_keys=True).records
    if json.dumps(prefix, sort_keys=True, separators=(",", ":")) != json.dumps(replay, sort_keys=True, separators=(",", ":")):
        raise AdapterContractError("truncation replay changed prefix predictions")
