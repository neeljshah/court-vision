"""Reader-only countdown for the first real match-the-close calibration readout."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


_MIN_SETTLED = 200
_SETTLEMENT_DATE_FIELDS = (
    "settled_at",
    "settled_date",
    "settlement_date",
    "settled_ts",
    "settlement_ts",
)


def _read_ledger(path: Path) -> List[Dict[str, Any]]:
    """Read nonblank JSON object lines from one supplied ledger path."""
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("ledger line %d is not a JSON object" % line_number)
            rows.append(row)
    return rows


def _parse_date(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _settled_dates(rows: Iterable[Dict[str, Any]]) -> Optional[List[str]]:
    dates: List[str] = []
    for row in rows:
        if str(row.get("status", "")).lower() != "settled":
            continue
        date = None
        for field in _SETTLEMENT_DATE_FIELDS:
            date = _parse_date(row.get(field))
            if date is not None:
                break
        if date is None:
            return None
        dates.append(date)
    return dates


def _settled_count(status: Dict[str, Any]) -> int:
    classes = status.get("row_classes")
    class_count = classes.get("settled") if isinstance(classes, dict) else None
    reported = status.get("n_settled")
    if isinstance(reported, int) and not isinstance(reported, bool):
        if isinstance(class_count, int) and reported != class_count:
            raise ValueError("n_settled and row_classes.settled disagree")
        return reported
    if isinstance(class_count, int) and not isinstance(class_count, bool):
        return class_count
    raise ValueError("execution status has no numeric settled count")


def _blockers(n_settled: int) -> List[str]:
    if n_settled >= _MIN_SETTLED:
        return []
    return [
        "S20: week bar unmet",
        "S18: blocked on S20",
    ]


def countdown(ledger_path: str, execution_status_path: str) -> Dict[str, Any]:
    """Return the current reader-only countdown from the two capture stores."""
    ledger = _read_ledger(Path(ledger_path))
    with Path(execution_status_path).open("r", encoding="utf-8") as handle:
        status = json.load(handle)
    if not isinstance(status, dict):
        raise ValueError("execution status is not a JSON object")

    n_settled = _settled_count(status)
    dates = _settled_dates(ledger)
    rate: Optional[float] = None
    if dates:
        rate = len(dates) / len(set(dates))
    days: Any = "UNDEFINED"
    if rate is not None and rate > 0.0:
        days = max(0, int(math.ceil((_MIN_SETTLED - n_settled) / rate)))

    return {
        "n_settled_today": n_settled,
        "settlement_rate_per_day": rate,
        "days_to_first_reading": days,
        "blockers": _blockers(n_settled),
    }

