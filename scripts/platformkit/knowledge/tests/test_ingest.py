"""Per-file test: ingest.py -- note parsing, note_id, related edges, embed_text.

Standalone-runnable (python tests/test_ingest.py) AND pytest-discoverable.
Uses a tiny in-test vault so it never depends on the real corpus. ASCII only.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.knowledge import config  # noqa: E402
from scripts.platformkit.knowledge import ingest  # noqa: E402


def _make_vault(tmp: Path) -> Path:
    nba = tmp / "NBA" / "DefensiveSchemes"
    nba.mkdir(parents=True)
    (nba / "drop_coverage.md").write_text(
        "---\ntags: [organized, nba, defensiveschemes, concept]\n---\n\n"
        "# Drop Coverage Against the Ball Screen\n\n"
        "> boilerplate; markets efficient; no edge claimed.\n\n"
        "## Summary\nThe big drops below the screen to wall the rim.\n\n"
        "## Related\n- [[ice_blue_side_coverage|Ice Coverage]]\n"
        "- [[hedge_show_coverage]]\n", encoding="utf-8")
    (nba / "no_frontmatter.md").write_text(
        "# Bare Note\n\nNo frontmatter here at all.\n", encoding="utf-8")
    return tmp


def test_parse_note_fields(tmp_path):
    vault = _make_vault(tmp_path)
    chunk = ingest.parse_note(
        vault / "NBA" / "DefensiveSchemes" / "drop_coverage.md", "NBA", vault / "NBA")
    assert chunk.note_id == "NBA/DefensiveSchemes/drop_coverage"
    assert chunk.sport == "NBA"
    assert chunk.category == "DefensiveSchemes"
    assert chunk.title == "Drop Coverage Against the Ball Screen"
    assert "concept" in chunk.tags
    assert set(chunk.related) == {"ice_blue_side_coverage", "hedge_show_coverage"}
    assert chunk.title in chunk.embed_text
    assert chunk.embed_text.isascii()
    assert chunk.content_sha256


def test_missing_frontmatter_graceful(tmp_path):
    vault = _make_vault(tmp_path)
    chunk = ingest.parse_note(
        vault / "NBA" / "DefensiveSchemes" / "no_frontmatter.md", "NBA", vault / "NBA")
    assert chunk.title == "Bare Note"
    assert chunk.tags == []
    assert chunk.related == []


def test_title_weighting(tmp_path):
    vault = _make_vault(tmp_path)
    chunk = ingest.parse_note(
        vault / "NBA" / "DefensiveSchemes" / "drop_coverage.md", "NBA", vault / "NBA")
    assert chunk.embed_text.count(chunk.title) >= config.TITLE_WEIGHT


def test_memory_source(tmp_path):
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "feedback_x.md").write_text(
        "---\nname: feedback-x\ndescription: a memory note\n---\n\n# Feedback X\nbody\n",
        encoding="utf-8")
    chunks = ingest.walk_memory(mem)
    assert len(chunks) == 1
    assert chunks[0].sport == "MEMORY"
    assert chunks[0].category == "memory"
    assert chunks[0].note_id == "MEMORY/feedback_x"


def _run() -> int:
    fails = 0
    for fn in (test_parse_note_fields, test_missing_frontmatter_graceful,
               test_title_weighting, test_memory_source):
        with tempfile.TemporaryDirectory() as d:
            try:
                fn(Path(d))
                print("PASS", fn.__name__)
            except AssertionError as exc:
                fails += 1
                print("FAIL", fn.__name__, exc)
    return fails


if __name__ == "__main__":
    raise SystemExit(_run())
