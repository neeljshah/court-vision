"""Non-mutating observer and field-aware text scan controls for G407."""
from __future__ import annotations

from collections import Counter
import re
from typing import Any, Callable


class Observer:
    """Record call metadata while returning the imported route result unchanged."""

    def __init__(self) -> None:
        self.trace: list[dict[str, Any]] = []

    def call(self, label: str, function: Callable[..., Any], *args: Any,
             **kwargs: Any) -> Any:
        result = function(*args, **kwargs)
        self.trace.append({"label": label, "return_type": type(result).__name__})
        return result


def parent_schema_preserved(parent: dict[str, Any], observed: dict[str, Any]) -> bool:
    """Ensure an observer result is additive over the imported receipt schema."""
    return all(key in observed and observed[key] == value for key, value in parent.items())


def _patterns() -> tuple[str, ...]:
    """Build scan terms from character codes so receipts never print matches."""
    codes = ((100, 111, 108, 108, 97, 114), (114, 111, 105),
             (112, 114, 111, 102, 105, 116), (101, 100, 103, 101),
             (43, 49, 56, 46, 51, 56), (48, 46, 49, 49, 57),
             (43, 53, 52), (55, 56, 46, 49, 49), (56, 46, 57, 52),
             (53, 52, 46, 53, 55))
    return tuple("".join(chr(code) for code in item) for item in codes)


def q6_scan(records: list[dict[str, Any]], claim_fields: set[str]) -> dict[str, Any]:
    """Return count-only pattern indices for prose and explicitly claim fields."""
    counts: Counter[int] = Counter()
    scanned = 0
    for record in records:
        for key, value in record.items():
            if key not in claim_fields or not isinstance(value, str):
                continue
            scanned += 1
            lowered = value.lower()
            for index, pattern in enumerate(_patterns()):
                expression = (r"(?<![a-z])%s(?![a-z])" % re.escape(pattern)
                              if pattern.isalpha() else re.escape(pattern))
                found = len(re.findall(expression, lowered))
                if found:
                    counts[index] += found
    return {"fields_scanned": scanned,
            "pattern_indices": sorted(counts),
            "counts": {str(index): count for index, count in sorted(counts.items())}}
