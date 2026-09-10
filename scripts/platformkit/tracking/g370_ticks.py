"""G370 evaluated-tick derivation from explicit markers or G359 ledger cadence."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

import pandas as pd

from scripts.platformkit.tracking.g359_held_position import LEDGER_FIELDS


def _present(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip()) and not pd.isna(value)


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None


def _integer_frame(frame_index: Any) -> int:
    try:
        return int(frame_index)
    except (TypeError, ValueError):
        raise ValueError("evaluated tick frame index must be an integer") from None


def _explicit_tick(current: pd.DataFrame, frame_index: Any) -> tuple[Any, bool, dict[str, Any]] | None:
    """Return a producer marker; false markers are an explicit unverified override."""
    for field in ("evaluated_tick_id", "evaluated_tick", "is_evaluated_tick"):
        if field not in current:
            continue
        values = [value for value in current[field].tolist() if _present(value)]
        if not values:
            continue
        value = values[0]
        marker = _boolean(value)
        if field == "is_evaluated_tick" and isinstance(value, (int, float)) and value in (0, 1):
            marker = bool(value)
        if marker is not None:
            tick_id = _integer_frame(frame_index) if marker else None
            return tick_id, marker, {"source": "table", "field": field, "marker": marker}
        return value, True, {"source": "table", "field": field, "marker": value}
    return None


def _ledger_input(section: Mapping[str, Any], frame_index: Any) -> tuple[Any, bool, dict[str, Any]]:
    ledger = section.get("ledger_record", section.get("ledger", {}))
    ledger = ledger if isinstance(ledger, Mapping) else {}
    record = {field: ledger.get(field, section.get("ledger_" + field)) for field in LEDGER_FIELDS}
    invalid = any(_supplied(value) and not _finite(value) for value in record.values())
    try:
        decoded, evaluated = float(record["decoded_frames"]), float(record["evaluated_frames"])
        stride = decoded / evaluated
        if invalid or not math.isfinite(stride):
            raise ValueError("invalid ledger")
    except (TypeError, ValueError, ZeroDivisionError):
        stride = float("nan")
    frame = _integer_frame(frame_index)
    verified = math.isfinite(stride) and stride > 0 and (frame / stride).is_integer()
    tick_id = int(round(frame / stride)) if verified else None
    record = {key: _json_safe(value) for key, value in record.items()}
    record.update({"source": "ledger", "implied_stride": stride if math.isfinite(stride) else None,
                   "frame_index": frame, "reason": "invalid_ledger" if invalid else None})
    return tick_id, verified, record


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _json_safe(value: Any) -> Any:
    return None if _supplied(value) and not _finite(value) else value


def _supplied(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def tick_verification(current: pd.DataFrame, section: Mapping[str, Any], frame_index: Any) -> tuple[Any, bool, dict[str, Any]]:
    """Prefer an explicit producer marker, else derive the G359 cadence from its ledger record."""
    return _explicit_tick(current, frame_index) or _ledger_input(section, frame_index)


def verification_sha256(verification_input: Mapping[str, Any]) -> str:
    """Hash the row's tick-verification evidence without exporting the raw input column."""
    payload = json.dumps(verification_input, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
