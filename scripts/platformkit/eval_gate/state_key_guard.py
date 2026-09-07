"""Optional duplicate evaluator-state key guard."""
from __future__ import annotations

from collections.abc import Iterable, Mapping


def assert_unique_state_keys(states: Iterable[Mapping[str, object]]) -> None:
    """Reject duplicate stable ``(game_id, state_ts)`` evaluator keys."""
    seen: set[str] = set()
    for state in states:
        key = f"{state['game_id']}|{state['state_ts']}"
        if key in seen:
            raise ValueError(f"duplicate state key: {key}")
        seen.add(key)
