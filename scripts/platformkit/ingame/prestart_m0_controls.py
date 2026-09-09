"""Small deterministic controls for the additive S327 attempt-2 census."""
from __future__ import annotations

import random
from collections import defaultdict
from datetime import date
from typing import Any


def dedupe_by_event_key(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Keep the first stable event key and report the raw archive-event count."""
    kept: dict[str, dict[str, Any]] = {}
    for event in events:
        kept.setdefault(str(event["event_key"]), event)
    return list(kept.values()), len(events)


def permute_dates(events: list[dict[str, Any]], seed: int = 327) -> list[dict[str, Any]]:
    """Deterministically shuffle dates only; any residual join is a finding."""
    ordered = sorted(events, key=lambda event: event["event_key"])
    dates = [event["date"] for event in ordered]
    random.Random(seed).shuffle(dates)
    return [{**event, "date": value} for event, value in zip(ordered, dates)]


def _day(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def collision_census(events: list[dict[str, Any]]) -> dict[str, int]:
    """Measure candidate ambiguity; a key retains its lexically first event."""
    pairs: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    teams: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    rematches: dict[frozenset[str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        home, away, day = event.get("home", ""), event.get("away", ""), event.get("date", "")
        if not (home and away):
            continue
        pairs[(day, home, away)].append(event)
        rematches[frozenset((home, away))].append(event)
        for team in (home, away):
            teams[(day, team)].append(event)

    def _collision(groups: dict[Any, list[dict[str, Any]]]) -> tuple[int, int, int]:
        collided = [group for group in groups.values() if len(group) > 1]
        return len(collided), len({event["event_key"] for group in collided for event in group}), sum(len(group) - 1 for group in collided)

    pair_keys, pair_events, pair_dropped = _collision(pairs)
    team_keys, team_events, team_dropped = _collision(teams)
    rematch_pairs, rematch_events = 0, set()
    for group in rematches.values():
        ordered = sorted(((event.get("date", ""), event) for event in group), key=lambda item: item[0])
        for (_, left), (_, right) in zip(ordered, ordered[1:]):
            start, stop = _day(left.get("date", "")), _day(right.get("date", ""))
            if start and stop and 0 < (stop - start).days <= 7:
                rematch_pairs += 1
                rematch_events.update((left["event_key"], right["event_key"]))
    return {
        "n_events": len(events), "doubleheader_keys": pair_keys,
        "doubleheader_events": pair_events, "rematch_pairs": rematch_pairs,
        "rematch_events": len(rematch_events), "date_team_collision_keys": team_keys,
        "date_team_collision_events": team_events,
        "multi_candidate_events": len({event["event_key"] for group in list(pairs.values()) + list(teams.values()) if len(group) > 1 for event in group}),
        "resolved_kept_first_bypair": pair_dropped,
        "resolved_kept_first_bydateteam": team_dropped,
        "resolved_kept_all": 0,
    }
