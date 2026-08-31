"""Cross-check broadcast tracking coverage against official NBA box scores."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


def _clean_jersey(value: Any) -> str | None:
    """Return a canonical jersey number, or None for an unavailable value."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "unknown"}:
        return None
    try:
        return str(int(float(text)))
    except ValueError:
        return text.upper()


def _pick_column(columns: Iterable[str], choices: Iterable[str]) -> str | None:
    by_lower = {column.lower(): column for column in columns}
    return next((by_lower[name] for name in choices if name in by_lower), None)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index + 1
        while end < len(order) and values[order[end]] == values[order[index]]:
            end += 1
        rank = (index + 1 + end) / 2.0
        for position in order[index:end]:
            ranks[position] = rank
        index = end
    return ranks


def _spearman(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2:
        return None
    left_ranks, right_ranks = _ranks(left), _ranks(right)
    left_mean, right_mean = _mean(left_ranks), _mean(right_ranks)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left_ranks, right_ranks))
    left_scale = math.sqrt(sum((value - left_mean) ** 2 for value in left_ranks))
    right_scale = math.sqrt(sum((value - right_mean) ** 2 for value in right_ranks))
    if not left_scale or not right_scale:
        return None
    return round(numerator / (left_scale * right_scale), 4)


def _tracking_summary(rows: list[dict[str, str]]) -> tuple[dict[str, int], set[str], int, int | None]:
    if not rows:
        return {}, set(), 0, None
    columns = rows[0].keys()
    jersey_column = _pick_column(columns, ("jersey_number", "jersey_num", "jersey"))
    identity_column = _pick_column(columns, ("player_id", "track_id"))
    frame_column = _pick_column(columns, ("frame", "frame_id"))
    event_column = _pick_column(columns, ("event", "event_type"))
    if not identity_column:
        raise ValueError("tracking CSV needs player_id or track_id")

    frames: dict[str, set[str]] = defaultdict(set)
    identities: dict[str, str | None] = {}
    for row_number, row in enumerate(rows):
        identity = row.get(identity_column, "").strip()
        if not identity:
            continue
        jersey = _clean_jersey(row.get(jersey_column)) if jersey_column else None
        identities.setdefault(identity, jersey)
        frame = row.get(frame_column, "") if frame_column else str(row_number)
        frames[identity].add(frame or str(row_number))

    by_jersey: dict[str, int] = defaultdict(int)
    for identity, jersey in identities.items():
        if jersey:
            by_jersey[jersey] += len(frames[identity])
    shot_count = None
    if event_column:
        shot_count = sum(
            1 for row in rows if "shot" in row.get(event_column, "").lower()
        )
    return dict(by_jersey), set(by_jersey), len(identities), shot_count


def crosscheck(tracking_csv: Path, boxscore_json: Path, shot_tolerance: float = 0.25) -> dict[str, Any]:
    """Compare a tracking CSV with the official box score for the same game."""
    with tracking_csv.open(newline="", encoding="utf-8-sig") as handle:
        tracking_rows = list(csv.DictReader(handle))
    with boxscore_json.open(encoding="utf-8") as handle:
        boxscore = json.load(handle)

    frame_counts, tracked_jerseys, n_tracked, shot_count = _tracking_summary(tracking_rows)
    players = boxscore.get("players", [])
    active_players = [player for player in players if float(player.get("min") or 0) > 0]
    box_by_jersey = {
        jersey: player
        for player in active_players
        if (jersey := _clean_jersey(player.get("jersey_num"))) is not None
    }
    box_jerseys = set(box_by_jersey)
    matched = sorted(box_jerseys & tracked_jerseys)
    missed = sorted(box_jerseys - tracked_jerseys)
    extra = sorted(tracked_jerseys - box_jerseys)
    jersey_match_pct = round(len(matched) / len(box_jerseys), 4) if box_jerseys else 0.0

    pairs = [(frame_counts[jersey], float(box_by_jersey[jersey]["min"])) for jersey in matched]
    minutes_spearman = _spearman([pair[0] for pair in pairs], [pair[1] for pair in pairs])
    if jersey_match_pct >= 0.6 and minutes_spearman is not None and minutes_spearman >= 0.5:
        verdict = "OK"
    elif jersey_match_pct >= 0.3 or (minutes_spearman is not None and minutes_spearman >= 0.3):
        verdict = "WEAK"
    else:
        verdict = "FAIL"

    result: dict[str, Any] = {
        "game_id": str(boxscore.get("game_id") or boxscore_json.stem.removeprefix("boxscore_")),
        "n_box_players": len(active_players),
        "n_tracked": n_tracked,
        "jersey_match_pct": jersey_match_pct,
        "minutes_spearman": minutes_spearman,
        "verdict": verdict,
        "jerseys": {"matched": matched, "missed": missed, "extra": extra},
        "minutes_pairs": len(pairs),
    }
    if shot_count is not None:
        box_fga = sum(int(player.get("fga") or 0) for player in active_players)
        difference = abs(shot_count - box_fga)
        result["shots"] = {
            "tracking_count": shot_count,
            "box_fga": box_fga,
            "difference": difference,
            "within_tolerance": difference <= max(1, math.ceil(box_fga * shot_tolerance)),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tracking_csv", type=Path)
    parser.add_argument("boxscore_json", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("data/tracking_reports/crosscheck"))
    parser.add_argument("--shot-tolerance", type=float, default=0.25)
    args = parser.parse_args()
    result = crosscheck(args.tracking_csv, args.boxscore_json, args.shot_tolerance)
    args.output_root.mkdir(parents=True, exist_ok=True)
    output_path = args.output_root / f"{result['game_id']}.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(str(output_path))


if __name__ == "__main__":
    main()
