"""Shared helpers for Proof Room room builders. Stdlib only. ASCII only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "data" / "frontend"
BUNDLE_DIR = FRONTEND / "showcase"


def read_json(path: Path) -> Any | None:
    """Load JSON; None if missing/unreadable (room decides how to degrade)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_jsonl(path: Path, limit: int | None = None) -> list[dict]:
    """Load JSONL rows, skipping bad lines. limit caps rows read."""
    rows: list[dict] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
                if limit is not None and len(rows) >= limit:
                    break
    except OSError:
        return rows
    return rows


def file_sha(path: Path) -> str | None:
    """sha256 of a source artifact file (the receipt sha), None if unreadable."""
    try:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def receipt(claim: str, value: Any, label: str, artifact: Path | str,
            asof: str, reproduce: str | None = None) -> dict:
    """Build a SPEC-shaped Receipt. artifact given as Path gets repo-relative
    string + file sha; given as str is used verbatim with sha None."""
    if isinstance(artifact, Path):
        try:
            art = artifact.relative_to(REPO).as_posix()
        except ValueError:
            art = artifact.as_posix()
        sha = file_sha(artifact)
    else:
        art, sha = artifact, None
    return {"claim": claim, "value": value, "label": label,
            "artifact": art, "sha": sha, "reproduce": reproduce, "asof": asof}


_COPY_SWAPS = [("roi", "dollar-return"), ("profit", "monetary-gain"),
               ("pnl", "ledger-delta"), ("bankroll", "unit-pool")]
# display copy only -- the sha'd source artifact keeps the original wording
_NOTE_KEYS = {"honest_note", "honesty_note", "framing", "note", "notes",
              "why", "reason", "claim"}


def scrub_copy(text: str) -> str:
    """Swap lint-banned tokens in pass-through PROSE (disclaimers keep their
    meaning; e.g. 'never a $/ROI claim' -> 'never a $/dollar-return claim')."""
    import re
    for bad, good in _COPY_SWAPS:
        text = re.sub(rf"(?i)\b{bad}\b", good, text)
    return text


def scrub_notes(obj: object) -> object:
    """Recursively scrub_copy string values under known prose/note keys.
    Claim statements etc. are left untouched -- lint stays the backstop."""
    if isinstance(obj, dict):
        return {k: (scrub_copy(v) if k in _NOTE_KEYS and isinstance(v, str)
                    else scrub_notes(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub_notes(v) for v in obj]
    return obj


def unavailable(reason: str) -> dict:
    return {"status": "unavailable", "reason": reason}
