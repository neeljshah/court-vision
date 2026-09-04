"""Pure checks for coherence between player q50s and named team q50 targets.

The input is one mapping per team-game.  Each mapping has ``game_id``,
``team_id``, a nonnegative ``overtime_periods``, and ``players``.  Every player
has a ``q50`` mapping with ``minutes``, ``pts``, ``reb``, and ``ast`` values.
``team_total_targets`` maps each stat to a mapping with ``value``,
``source_file``, and ``source_field``.  The source metadata is retained in
the result so callers name the actual game-engine output rather than invent a
team target.

This module reads no store.  Future callers can supply S241/S242 q50 rows and
the game engine's team total output directly.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


STATS = ("pts", "reb", "ast")
REGULATION_TEAM_MINUTES = 240.0
OVERTIME_TEAM_MINUTES = 5.0


def _number(value: Any, label: str) -> float:
    """Return a finite numeric input or raise a descriptive ValueError."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{label} must be finite")
    return number


def _q50(player: Mapping[str, Any], stat: str) -> float:
    values = player.get("q50")
    if not isinstance(values, Mapping) or stat not in values:
        player_id = player.get("player_id", "unknown")
        raise ValueError(f"player {player_id} is missing q50.{stat}")
    return _number(values[stat], f"q50.{stat}")


def _target_result(
    player_sum: float, target: Any, stat: str
) -> dict[str, Any]:
    if not isinstance(target, Mapping):
        return {
            "status": "EXCLUDED_MISSING_TARGET",
            "player_q50_sum": player_sum,
            "target_q50": None,
            "absolute_deviation": None,
            "pct_deviation": None,
            "source_file": None,
            "source_field": None,
        }
    source_file = target.get("source_file")
    source_field = target.get("source_field")
    value = target.get("value")
    base = {
        "player_q50_sum": player_sum,
        "source_file": source_file,
        "source_field": source_field,
    }
    if value is None:
        return {
            "status": "EXCLUDED_MISSING_TARGET",
            "target_q50": None,
            "absolute_deviation": None,
            "pct_deviation": None,
            **base,
        }
    if not isinstance(source_file, str) or not source_file:
        raise ValueError(f"team_total_targets.{stat}.source_file must name the target source")
    if not isinstance(source_field, str) or not source_field:
        raise ValueError(f"team_total_targets.{stat}.source_field must name the target field")
    team_q50 = _number(value, f"team_total_targets.{stat}.value")
    absolute_deviation = abs(player_sum - team_q50)
    if team_q50 == 0:
        return {
            "status": "EXCLUDED_ZERO_TARGET",
            "target_q50": team_q50,
            "absolute_deviation": absolute_deviation,
            "pct_deviation": None,
            **base,
        }
    return {
        "status": "OK",
        "target_q50": team_q50,
        "absolute_deviation": absolute_deviation,
        "pct_deviation": absolute_deviation / abs(team_q50),
        **base,
    }


def check_team_coherence(team_games: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return minutes and stat-sum coherence for each supplied team-game.

    Minutes use the five largest player q50 values, as required by S243.  A
    missing target is retained as an explicit exclusion and never converted to
    a zero-deviation result.
    """
    results: list[dict[str, Any]] = []
    for team_game in team_games:
        game_id = str(team_game.get("game_id", ""))
        team_id = str(team_game.get("team_id", ""))
        if not game_id or not team_id:
            raise ValueError("team-game needs game_id and team_id")
        overtime_periods = _number(team_game.get("overtime_periods", 0), "overtime_periods")
        if overtime_periods < 0 or not overtime_periods.is_integer():
            raise ValueError("overtime_periods must be a nonnegative integer")
        players = team_game.get("players")
        if not isinstance(players, list) or len(players) < 5:
            raise ValueError(f"{game_id}/{team_id} needs at least five players")

        minutes = sorted((_q50(player, "minutes") for player in players), reverse=True)
        minutes_sum = sum(minutes[:5])
        minutes_budget = REGULATION_TEAM_MINUTES + OVERTIME_TEAM_MINUTES * overtime_periods
        stat_sums = {stat: sum(_q50(player, stat) for player in players) for stat in STATS}
        targets = team_game.get("team_total_targets", {})
        if not isinstance(targets, Mapping):
            raise ValueError(f"{game_id}/{team_id} team_total_targets must be a mapping")
        results.append(
            {
                "game_id": game_id,
                "team_id": team_id,
                "overtime_periods": int(overtime_periods),
                "top5_minutes_q50_sum": minutes_sum,
                "minutes_budget": minutes_budget,
                "minutes_excess": max(0.0, minutes_sum - minutes_budget),
                "minutes_flagged": minutes_sum > minutes_budget,
                "stat_sums": {
                    stat: _target_result(stat_sums[stat], targets.get(stat), stat)
                    for stat in STATS
                },
            }
        )
    return results


def summarize_stat_deviations(results: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, float | int]]:
    """Summarize valid team-stat percentage deviations and named exclusions."""
    summary = {
        stat: {"n": 0, "excluded_missing_target": 0, "excluded_zero_target": 0, "total": 0,
               "mean_abs_pct_deviation": None}
        for stat in STATS
    }
    totals: dict[str, float] = {stat: 0.0 for stat in STATS}
    for result in results:
        stat_sums = result.get("stat_sums", {})
        for stat in STATS:
            summary[stat]["total"] += 1
            detail = stat_sums.get(stat, {}) if isinstance(stat_sums, Mapping) else {}
            status = detail.get("status") if isinstance(detail, Mapping) else None
            if status == "OK":
                summary[stat]["n"] += 1
                totals[stat] += float(detail["pct_deviation"])
            elif status == "EXCLUDED_MISSING_TARGET":
                summary[stat]["excluded_missing_target"] += 1
            elif status == "EXCLUDED_ZERO_TARGET":
                summary[stat]["excluded_zero_target"] += 1
            else:
                raise ValueError(f"unrecognized {stat} coherence status: {status}")
    for stat in STATS:
        n = int(summary[stat]["n"])
        if n:
            summary[stat]["mean_abs_pct_deviation"] = totals[stat] / n
    return summary
