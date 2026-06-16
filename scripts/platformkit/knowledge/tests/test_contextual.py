"""Per-file test: contextual.py -- offline template backend + stamping.

The Haiku backend is an optional upgrade and is NOT exercised (no API). Standalone +
pytest-discoverable. ASCII.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.knowledge import contextual as C  # noqa: E402
from scripts.platformkit.knowledge.ingest import NoteChunk  # noqa: E402


def _chunk():
    return NoteChunk(note_id="NBA/Tactics/drop_coverage", sport="NBA",
                     category="Tactics", title="Drop Coverage",
                     tags=["nba", "concept"], body="Wall the rim.")


def test_template_prefix_deterministic_ascii():
    b = C.TemplateBackend()
    p1 = b.prefix(_chunk())
    p2 = b.prefix(_chunk())
    assert p1 == p2                          # deterministic
    assert p1.isascii()
    assert "NBA" in p1 and "Drop Coverage" in p1 and "Tactics" in p1
    assert b.backend_id == "template-offline-v1"


def test_get_backend_defaults_to_template():
    assert isinstance(C.get_backend("template"), C.TemplateBackend)
    assert isinstance(C.get_backend(None), C.TemplateBackend)


def test_stamp_prefixes_rebuilds_embed_text():
    ch = _chunk()
    before = ch.embed_text
    C.stamp_prefixes([ch], C.TemplateBackend())
    assert ch.contextual
    assert ch.embedded_with == "template-offline-v1"
    assert ch.contextual.split("\n")[0] in ch.embed_text
    assert ch.embed_text != before or before == ""


def _run() -> int:
    fails = 0
    for fn in (test_template_prefix_deterministic_ascii,
               test_get_backend_defaults_to_template,
               test_stamp_prefixes_rebuilds_embed_text):
        try:
            fn()
            print("PASS", fn.__name__)
        except AssertionError as exc:
            fails += 1
            print("FAIL", fn.__name__, exc)
    return fails


if __name__ == "__main__":
    raise SystemExit(_run())
