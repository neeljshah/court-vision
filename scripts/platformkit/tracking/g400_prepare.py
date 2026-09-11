"""Pure preparation rails for the G400 ball-reference growth stage."""
from __future__ import annotations

import hashlib
import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


GAMES = 30
FRAMES_PER_GAME = 10
PLANNED_STATES = GAMES * FRAMES_PER_GAME
RATER_BATCHES = 10
RATER_BATCH_SIZE = 30
KAPPA_BAR = 0.60
YIELD_LIMIT = 120
SEAL_PREFIX = b"SEAL sha256 "
LABELS = frozenset(("VISIBLE", "ABSENT", "UNKNOWN"))
PLANNED_STATUSES = frozenset(("PLANNED", "DECODE_FAILED", "UNVISITED", "REVIEWED"))


def verify_preregistration(path: Any) -> str:
    """Verify a file-read LF-normalized seal without requiring a git checkout."""
    raw = open(path, "rb").read().replace(b"\r\n", b"\n")
    body, marker, recorded = raw.rpartition(b"\n" + SEAL_PREFIX)
    if not marker or body.endswith(b"\n"):
        raise ValueError("invalid-preregistration-seal-layout")
    actual = recorded.decode("ascii").strip()
    expected = hashlib.sha256(body + b"\n").hexdigest()
    if len(actual) != 64 or actual != expected:
        raise ValueError("preregistration-seal-mismatch")
    return actual


def _rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _unique(rows: Sequence[Mapping[str, Any]], field: str) -> None:
    values = [str(row.get(field, "")) for row in rows]
    if "" in values or len(values) != len(set(values)):
        raise ValueError("duplicate-or-missing-" + field)


def draw_games(population: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Select exactly 30 frozen game identities by the G400 even-index rule."""
    rows = _rows(population)
    _unique(rows, "canonical_game")
    for row in rows:
        required = ("competition", "canonical_game", "source_digest")
        if any(not str(row.get(field, "")) for field in required):
            raise ValueError("ineligible-game-identity")
        if str(row.get("eligibility", "ELIGIBLE")) != "ELIGIBLE":
            raise ValueError("ineligible-row-in-population")
    if len(rows) < GAMES:
        raise ValueError("insufficient-eligible-games")
    ordered = sorted(rows, key=lambda row: (str(row["competition"]),
                                             str(row["canonical_game"]),
                                             str(row["source_digest"])))
    count = len(ordered)
    selected = [ordered[math.floor(index * (count - 1) / (GAMES - 1) + 0.5)]
                for index in range(GAMES)]
    _unique(selected, "canonical_game")
    return selected


def assert_frozen_draw(population: Iterable[Mapping[str, Any]],
                       selected: Iterable[Mapping[str, Any]]) -> None:
    """Refuse substitutions, reordered identity, or an altered fixed draw."""
    expected = draw_games(population)
    observed = _rows(selected)
    if len(observed) != GAMES:
        raise ValueError("selected-game-count-mismatch")
    fields = ("canonical_game", "competition", "source_digest")
    if [tuple(str(row.get(field, "")) for field in fields) for row in observed] != [
            tuple(str(row[field]) for field in fields) for row in expected]:
        raise ValueError("post-draw-substitution")


def assert_disjoint(new_rows: Iterable[Mapping[str, Any]],
                    old_rows: Iterable[Mapping[str, Any]]) -> None:
    """Reject new source identities that overlap old DEV, held-out, or context data."""
    new, old = _rows(new_rows), _rows(old_rows)
    for field in ("canonical_game", "source_digest", "context_identity"):
        left = {str(row.get(field, "")) for row in new}
        right = {str(row.get(field, "")) for row in old}
        if "" in left or "" in right:
            raise ValueError("missing-disjointness-identity-" + field)
        if left & right:
            raise ValueError("old-game-or-context-overlap-" + field)


def make_batch_plan(state_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Arrange 300 planned states into ten 30-game paired-rating rounds."""
    rows = _rows(state_rows)
    if len(rows) != PLANNED_STATES:
        raise ValueError("planned-state-denominator-mismatch")
    _unique(rows, "frame_key")
    games = sorted({str(row.get("canonical_game", "")) for row in rows})
    if len(games) != GAMES or "" in games:
        raise ValueError("planned-game-denominator-mismatch")
    by_game = {game: sorted((row for row in rows if row["canonical_game"] == game),
                            key=lambda row: str(row["frame_key"])) for game in games}
    if any(len(group) != FRAMES_PER_GAME for group in by_game.values()):
        raise ValueError("frames-per-game-mismatch")
    return [{"round": round_index + 1, "position": position + 1,
             "frame_key": by_game[game][round_index]["frame_key"],
             "canonical_game": game}
            for round_index in range(RATER_BATCHES) for position, game in enumerate(games)]


def validate_state_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Keep all planned states while distinguishing review from unvisited work."""
    materialized = _rows(rows)
    if len(materialized) != PLANNED_STATES:
        raise ValueError("whole-stage-denominator-required")
    _unique(materialized, "frame_key")
    counts: Counter[str] = Counter()
    for row in materialized:
        status = str(row.get("status", ""))
        label = str(row.get("label", ""))
        if status not in PLANNED_STATUSES:
            raise ValueError("unknown-state-status")
        if status == "UNVISITED" and label:
            raise ValueError("unvisited-cannot-have-label")
        if status == "REVIEWED" and label not in LABELS:
            raise ValueError("reviewed-state-needs-three-label")
        if status != "REVIEWED" and label:
            raise ValueError("nonreviewed-label-refused")
        counts[status] += 1
    return dict(counts)


def validate_completed_answers(rows: Iterable[Mapping[str, Any]]) -> None:
    """Refuse duplicate completed judgments per rater and planned frame key."""
    materialized = _rows(rows)
    pairs = [(str(row.get("rater", "")), str(row.get("frame_key", "")))
             for row in materialized]
    if any(not rater or not frame for rater, frame in pairs):
        raise ValueError("missing-rater-or-frame-key")
    if len(pairs) != len(set(pairs)):
        raise ValueError("duplicate-completed-answer")
    if any(str(row.get("label", "")) not in LABELS for row in materialized):
        raise ValueError("invalid-three-label-answer")


def cohen_kappa(left: Sequence[str], right: Sequence[str]) -> float | None:
    """Return raw three-label Cohen kappa; undefined agreement remains None."""
    if len(left) != len(right) or not left:
        raise ValueError("paired-labels-required")
    if set(left) - LABELS or set(right) - LABELS:
        raise ValueError("invalid-three-label-answer")
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    expected = sum(left.count(label) * right.count(label) for label in LABELS) / len(left) ** 2
    return None if math.isclose(1.0 - expected, 0.0) else (observed - expected) / (1.0 - expected)


def native_to_720p(value: float, source_height: int) -> float:
    """Convert native coordinates using actual source height, not sheet metadata."""
    if source_height <= 0:
        raise ValueError("invalid-source-height")
    return float(value) * 720.0 / float(source_height)


def native_roundtrip(value: float, source_height: int) -> float:
    """Invert the fixed height transform for planted-centre controls."""
    return native_to_720p(value, source_height) * float(source_height) / 720.0


def stage_verdict(rows: Iterable[Mapping[str, Any]], accepted_boxes: int) -> str:
    """Apply the immutable whole-stage yield denominator and training lock."""
    validate_state_rows(rows)
    if accepted_boxes < 0 or accepted_boxes > PLANNED_STATES:
        raise ValueError("invalid-accepted-box-count")
    return "CLOSED AT LIMIT" if accepted_boxes <= YIELD_LIMIT else "NEXT-STAGE-PROPOSAL-ONLY"
