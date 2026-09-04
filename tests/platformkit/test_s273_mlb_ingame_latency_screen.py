"""Focused invariants for the sealed S273 latency screen."""
from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.platformkit.ingame.s273_mlb_ingame_latency_screen import shift_records


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04_PREREG.md"


def test_named_ts_shift_and_prereg_seal() -> None:
    row = {"ts": "2026-07-01T12:00:00+00:00", "game_id": "KXMLBGAME-26JUL011310TEXCLE"}
    shifted = shift_records([row], 41.0)
    assert shifted == [{"ts": "2026-07-01T12:00:41+00:00", "game_id": row["game_id"]}]
    assert row["ts"] == "2026-07-01T12:00:00+00:00"
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n")
    header, seal_text = raw.split(b"seal_sha256: ", 1)
    assert hashlib.sha256(header).hexdigest() == seal_text.splitlines()[0].decode("ascii")
