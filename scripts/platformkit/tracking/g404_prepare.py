"""Pure G404 preparation rails for the sealed play-gated collection protocol."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, Mapping, Sequence


def normalized_prereg_bytes(path: Path) -> bytes:
    """Return bytes above the seal with CRLF normalized for the landing test."""
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    cut = raw.rfind(b"SEAL sha256")
    if cut <= 0:
        raise ValueError("preregistration has no seal")
    return raw[:cut]


def prereg_seal_is_valid(path: Path) -> bool:
    """Check the embedded seal without depending on a committed Git object."""
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    cut = raw.rfind(b"SEAL sha256")
    if cut <= 0:
        return False
    fields = raw[cut:].split()
    return len(fields) >= 3 and fields[1] == b"sha256" and fields[2] == hashlib.sha256(
        raw[:cut]).hexdigest().encode("ascii")


def even_indices(size: int, count: int) -> list[int]:
    """Return the sealed whole-stratum evenly spaced indices."""
    if count < 1 or size < count:
        raise ValueError("impossible even draw")
    if count == 1:
        return [0]
    return [int((index * (size - 1) / (count - 1)) + 0.5) for index in range(count)]


def audit_draw(rows: Sequence[Mapping[str, str]], admitted: bool) -> list[dict[str, str]]:
    """Select the fixed 30 gate-audit keys before any ball draw exists."""
    wanted = "1" if admitted else "0"
    stratum = sorted((dict(row) for row in rows if row["gate_admitted"] == wanted),
                     key=lambda row: (row["canonical_game"], row["pts"], row["source_sha256"]))
    if len(stratum) < 30:
        raise ValueError("gate audit stratum has fewer than 30 rows")
    return [stratum[index] for index in even_indices(len(stratum), 30)]


def exclude_audit_context(rows: Iterable[Mapping[str, str]], audit: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    """Exclude audit keys and their sealed one-second neighborhoods from candidates."""
    by_game: dict[str, list[float]] = {}
    for item in audit:
        by_game.setdefault(item["canonical_game"], []).append(float(item["pts"]))
    kept = []
    for row in rows:
        nearby = by_game.get(row["canonical_game"], [])
        if all(abs(float(row["pts"]) - point) > 1.0 for point in nearby):
            kept.append(dict(row))
    return kept


def draw_games(rows: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    """Draw 30 games then ten admitted targets per game, all from frozen rows."""
    games: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row["gate_admitted"] == "1":
            games.setdefault(row["canonical_game"], []).append(dict(row))
    eligible = sorted((game, sorted(values, key=lambda row: float(row["pts"])))
                      for game, values in games.items() if len(values) >= 10)
    if len(eligible) < 30:
        raise ValueError("fewer than 30 games with ten admitted targets")
    output: list[dict[str, str]] = []
    for game_index in even_indices(len(eligible), 30):
        _, targets = eligible[game_index]
        output.extend(targets[index] for index in even_indices(len(targets), 10))
    return output


def assert_disjoint(candidate_games: Iterable[str], forbidden_games: Iterable[str]) -> None:
    """Reject any canonical-game overlap before a draw is made."""
    overlap = sorted(set(candidate_games).intersection(forbidden_games))
    if overlap:
        raise ValueError("canonical-game overlap: " + ",".join(overlap))


def planned_key_set(rows: Iterable[Mapping[str, str]]) -> set[str]:
    """Return stable frame keys used to require a complete later yield table."""
    keys = {row["frame_key"] for row in rows}
    if len(keys) != 300:
        raise ValueError("planned draw must contain exactly 300 unique frame keys")
    return keys
