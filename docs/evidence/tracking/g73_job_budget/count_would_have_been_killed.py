"""Count daemon-ledger rows that exceed a proposed global job budget."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def count_would_have_been_killed(ledger: Path, budget_seconds: int) -> dict:
    """Return the all-row count whose recorded elapsed time exceeds a budget."""
    rows = []
    for line_number, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        entry = json.loads(line)
        try:
            seconds = int(entry["seconds"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("line %d has no integer seconds value" % line_number) from exc
        rows.append(seconds)
    return {
        "budget_seconds": budget_seconds,
        "comparison": "seconds > budget_seconds",
        "historical_rows": len(rows),
        "would_have_been_killed": sum(seconds > budget_seconds for seconds in rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--budget-seconds", type=int, default=12_000)
    args = parser.parse_args()
    print(json.dumps(count_would_have_been_killed(args.ledger, args.budget_seconds),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
