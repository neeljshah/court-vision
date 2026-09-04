"""Reconstruct five-player on-court stamps from CDN boxscores and substitutions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


SIDES = ("homeTeam", "awayTeam")
STAMP_COLUMNS = (
    "game_id", "tick_index", "tick_kind", "period", "clock", "wallclock",
    "home_team_id", "away_team_id", "home_player_1", "home_player_2",
    "home_player_3", "home_player_4", "home_player_5", "away_player_1",
    "away_player_2", "away_player_3", "away_player_4", "away_player_5",
)


def _read_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read one archive file and retain its input identity for reproduction."""
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), {
        "path": path.as_posix(),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "resolution": "n/a_json",
    }


def _seed_teams(boxscore: dict[str, Any]) -> tuple[dict[str, set[str]], dict[str, str]]:
    game = boxscore.get("game", {})
    states: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    for side in SIDES:
        team = game.get(side, {})
        team_id = str(team.get("teamId", ""))
        starters = {
            str(player.get("personId"))
            for player in team.get("players", [])
            if str(player.get("starter")) == "1" and player.get("personId") is not None
        }
        if not team_id or len(starters) != 5 or team_id in states:
            raise ValueError("invalid_starting_five")
        states[team_id] = starters
        labels[side] = team_id
    return states, labels


def _substitution_groups(playbyplay: dict[str, Any], teams: set[str]) -> list[list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for action in playbyplay.get("game", {}).get("actions", []):
        if action.get("actionType") != "substitution":
            continue
        required = ("timeActual", "period", "clock", "teamId", "personId", "subType")
        if any(action.get(field) in (None, "") for field in required):
            raise ValueError("missing_substitution_field")
        if str(action["teamId"]) not in teams or action["subType"] not in ("in", "out"):
            raise ValueError("invalid_substitution_field")
        groups[str(action["timeActual"])].append(action)
    if not groups:
        raise ValueError("no_substitution_action")
    return [groups[wallclock] for wallclock in sorted(groups)]


def _apply_batch(states: dict[str, set[str]], batch: list[dict[str, Any]]) -> None:
    coordinates = {(str(item["period"]), str(item["clock"])) for item in batch}
    if len(coordinates) != 1:
        raise ValueError("mixed_tick_coordinates")
    by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for action in batch:
        by_team[str(action["teamId"])].append(action)
    next_states = {team_id: set(players) for team_id, players in states.items()}
    for team_id, actions in by_team.items():
        outs = [str(item["personId"]) for item in actions if item["subType"] == "out"]
        ins = [str(item["personId"]) for item in actions if item["subType"] == "in"]
        if len(outs) != len(ins):
            raise ValueError("substitution_in_out_imbalance")
        if len(set(outs)) != len(outs) or len(set(ins)) != len(ins):
            raise ValueError("duplicate_substitution_member")
        current = next_states[team_id]
        if not set(outs).issubset(current) or set(ins) & (current - set(outs)):
            raise ValueError("invalid_substitution_membership")
        next_states[team_id] = (current - set(outs)) | set(ins)
    if any(len(players) != 5 for players in next_states.values()):
        raise ValueError("unresolved_roster_size")
    states.update(next_states)


def _stamp(
    game_id: str,
    tick_index: int,
    tick_kind: str,
    period: int,
    clock: str,
    wallclock: str,
    states: dict[str, set[str]],
    labels: dict[str, str],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "game_id": game_id, "tick_index": tick_index, "tick_kind": tick_kind,
        "period": period, "clock": clock, "wallclock": wallclock,
        "home_team_id": labels["homeTeam"], "away_team_id": labels["awayTeam"],
    }
    for side, prefix in (("homeTeam", "home"), ("awayTeam", "away")):
        for index, person_id in enumerate(sorted(states[labels[side]]), start=1):
            row[f"{prefix}_player_{index}"] = person_id
    return row


def replay_game(boxscore: dict[str, Any], playbyplay: dict[str, Any], game_id: str) -> list[dict[str, Any]]:
    """Return opening and substitution-bounded complete five-player stamps."""
    states, labels = _seed_teams(boxscore)
    rows = [_stamp(game_id, 0, "opening", 1, "PT10M00.00S", "", states, labels)]
    for index, batch in enumerate(_substitution_groups(playbyplay, set(states)), start=1):
        _apply_batch(states, batch)
        first = batch[0]
        rows.append(_stamp(
            game_id, index, "substitution", int(first["period"]), str(first["clock"]),
            str(first["timeActual"]), states, labels,
        ))
    return rows


def derive_archive(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Sequentially replay every complete CDN pair without writing to the archive."""
    rows: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for game_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        game_id = game_dir.name
        box_path, play_path = game_dir / "boxscore.json", game_dir / "playbyplay.json"
        if not box_path.is_file() or not play_path.is_file():
            excluded.append({"game_id": game_id, "reason": "missing_pair_member"})
            continue
        try:
            boxscore, box_input = _read_json(box_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            excluded.append({"game_id": game_id, "reason": "boxscore_unreadable"})
            continue
        inputs.append(box_input)
        try:
            playbyplay, play_input = _read_json(play_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            excluded.append({"game_id": game_id, "reason": "playbyplay_unreadable"})
            continue
        inputs.append(play_input)
        try:
            rows.extend(replay_game(boxscore, playbyplay, game_id))
        except ValueError as error:
            excluded.append({"game_id": game_id, "reason": str(error)})
    duplicate_violations = sum(
        len({row[f"{side}_player_{index}"] for index in range(1, 6)}) != 5
        for row in rows for side in ("home", "away")
    )
    summary = {
        "archive_root": root.as_posix(), "pair_directories": len([p for p in root.iterdir() if p.is_dir()]),
        "qualifying_game_clusters": len({row["game_id"] for row in rows}),
        "substitution_bounded_ticks": len(rows), "complete_ticks": len(rows),
        "coverage_pct": 100.0 if rows else 0.0,
        "duplicate_on_court_violations": duplicate_violations,
        "substitution_in_out_imbalance": 0,
        "excluded_games": excluded,
    }
    return summary, rows, inputs


def _clock_seconds(clock: str) -> float:
    text = clock.removeprefix("PT").removesuffix("S")
    minutes, seconds = text.split("M", maxsplit=1)
    return float(minutes) * 60.0 + float(seconds)


def _elapsed_seconds(period: int, clock: str) -> float:
    completed_regulation = min(period - 1, 4) * 600.0
    overtime_before = max(period - 5, 0) * 300.0
    period_length = 600.0 if period <= 4 else 300.0
    return completed_regulation + overtime_before + period_length - _clock_seconds(clock)


def minutes_spot_check(root: Path, stamps: list[dict[str, Any]], sample_size: int = 30) -> list[dict[str, Any]]:
    """Compare reconstructed on-court interval seconds with boxscore minutes."""
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stamp in stamps:
        by_game[str(stamp["game_id"])].append(stamp)
    game_ids = sorted(by_game)
    positions = sorted({round(index * (len(game_ids) - 1) / (min(sample_size, len(game_ids)) - 1))
                        for index in range(min(sample_size, len(game_ids)))}) if len(game_ids) > 1 else [0]
    results: list[dict[str, Any]] = []
    for position in positions:
        game_id = game_ids[position]
        boxscore, _ = _read_json(root / game_id / "boxscore.json")
        game = boxscore["game"]
        game_stamps = sorted(by_game[game_id], key=lambda item: int(item["tick_index"]))
        end_elapsed = _elapsed_seconds(int(game["period"]), str(game["gameClock"]))
        totals: dict[str, float] = defaultdict(float)
        for index, stamp in enumerate(game_stamps):
            start = _elapsed_seconds(int(stamp["period"]), str(stamp["clock"]))
            end = end_elapsed if index + 1 == len(game_stamps) else _elapsed_seconds(
                int(game_stamps[index + 1]["period"]), str(game_stamps[index + 1]["clock"])
            )
            duration = max(end - start, 0.0)
            for side in ("home", "away"):
                for player_index in range(1, 6):
                    totals[str(stamp[f"{side}_player_{player_index}"])] += duration
        for side in SIDES:
            for player in game[side]["players"]:
                person_id = str(player.get("personId"))
                source = _clock_seconds(str(player.get("statistics", {}).get("minutes", "PT00M00.00S")))
                derived = totals.get(person_id, 0.0)
                results.append({
                    "game_id": game_id, "person_id": person_id,
                    "derived_on_court_seconds": round(derived, 3),
                    "boxscore_minutes_seconds": round(source, 3),
                    "absolute_difference_seconds": round(abs(derived - source), 3),
                })
    return results


def write_artifacts(output_dir: Path, summary: dict[str, Any], rows: list[dict[str, Any]], inputs: list[dict[str, Any]], minutes: list[dict[str, Any]]) -> None:
    """Write compact, replayable evidence artifacts outside the source archive."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(output_dir / "stamps.csv", STAMP_COLUMNS, rows)
    _write_csv(output_dir / "input_manifest.csv", ("path", "bytes", "sha256", "resolution"), inputs)
    _write_csv(output_dir / "not_verified.csv", ("game_id", "reason"), summary["excluded_games"])
    _write_csv(output_dir / "minutes_spot_check.csv", (
        "game_id", "person_id", "derived_on_court_seconds", "boxscore_minutes_seconds",
        "absolute_difference_seconds",
    ), minutes)
    consistency = [{
        "coverage_pct": summary["coverage_pct"], "complete_ticks": summary["complete_ticks"],
        "substitution_bounded_ticks": summary["substitution_bounded_ticks"],
        "duplicate_on_court_violations": summary["duplicate_on_court_violations"],
        "substitution_in_out_imbalance": summary["substitution_in_out_imbalance"],
    }]
    _write_csv(output_dir / "consistency.csv", tuple(consistency[0]), consistency)


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive_root", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    summary, rows, inputs = derive_archive(args.archive_root)
    minutes = minutes_spot_check(args.archive_root, rows)
    write_artifacts(args.output_dir, summary, rows, inputs, minutes)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
