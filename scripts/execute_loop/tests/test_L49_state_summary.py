"""tests/test_L49_state_summary.py — Tests for L49 LoopSummarizer.

Coverage:
  1. test_snapshot_reads_state_json        — rounds_completed matches state.json
  2. test_to_markdown_includes_headline_section
  3. test_to_markdown_includes_round_table
  4. test_atomic_write_target_file         — write() creates file; monkeypatched
                                             os.replace leaves original unchanged
  5. test_main_cli_writes_default_path     — main([]) writes STATE_OF_LOOP.md
  6. test_snapshot_handles_missing_l42_l47_gracefully
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Make sure the project root is on the path
# ---------------------------------------------------------------------------
_TESTS_DIR = Path(__file__).resolve().parent
_EXECUTE_LOOP = _TESTS_DIR.parent
_PROJECT_ROOT = _EXECUTE_LOOP.parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.execute_loop.L49_state_summary import (  # noqa: E402
    LoopSnapshot,
    LoopSummarizer,
    _collect_event_metadata,
    main,
    _DEFAULT_OUT,
    _DEFAULT_STATE,
)

# ---------------------------------------------------------------------------
# Minimal state.json fixture
# ---------------------------------------------------------------------------
_MINIMAL_STATE: dict = {
    "version": 2,
    "rounds_completed": 5,
    "layers": {
        "L1": {
            "name": "DK/FD slate ingester",
            "status": "shipped",
            "ships": [{"round": 1, "tests": "24/24", "loc": 437}],
        },
        "L2": {
            "name": "Fantasy points dist engine",
            "status": "shipped",
            "ships": [{"round": 1, "tests": "9/9", "loc": 271}],
        },
        "L29": {
            "name": "Multi-account orchestrator",
            "status": "gated",
        },
        "L41": {
            "name": "Integration harness (end-to-end)",
            "status": "shipped",
            "ships": [
                {
                    "round": 3,
                    "tests": "10/10",
                    "notes": "10-stage pipeline covering 10 of 40 layers",
                }
            ],
        },
    },
    "round_summaries": [
        {"round": 1, "ships": ["L1", "L2"], "tests": "33/33", "notes": "Initial build"},
        {"round": 2, "ships": ["L3"], "tests": "16/16", "notes": "Cash optimizer"},
        {"round": 3, "ships": ["L41"], "tests": "10/10", "notes": "Integration harness"},
        {"round": 4, "ships": [], "tests": "0/0", "notes": ""},
        {"round": 5, "ships": [], "tests": "0/0", "notes": ""},
    ],
    "totals": {
        "layers_shipped": 3,
        "layers_gated": 1,
        "total_layers": 4,
        "cumulative_tests": "59/59",
        "l42_audit": "PASS 10 / FAIL 0 / SKIP 2 / N/A 5",
    },
}


@pytest.fixture()
def state_file(tmp_path: Path) -> Path:
    """Write minimal state.json to a temp directory."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps(_MINIMAL_STATE), encoding="utf-8")
    return path


@pytest.fixture()
def summarizer(state_file: Path) -> LoopSummarizer:
    return LoopSummarizer(
        state_json_path=state_file,
        layers_dir=state_file.parent,
    )


# ---------------------------------------------------------------------------
# Test 1 — snapshot reads state.json correctly
# ---------------------------------------------------------------------------
def test_snapshot_reads_state_json(summarizer: LoopSummarizer):
    snap = summarizer.snapshot()
    assert snap.rounds_completed == 5
    assert snap.layers_shipped == 3
    assert snap.layers_gated == 1
    assert snap.cumulative_tests == "59/59"
    assert len(snap.rounds) == 5


# ---------------------------------------------------------------------------
# Test 2 — to_markdown includes ## Headline section
# ---------------------------------------------------------------------------
def test_to_markdown_includes_headline_section(summarizer: LoopSummarizer):
    snap = summarizer.snapshot()
    md = summarizer.to_markdown(snap)
    assert "## Headline" in md
    assert "layers shipped" in md
    assert "L42 audit" in md
    assert "L47 regression scan" in md
    assert "L41 e2e coverage" in md


# ---------------------------------------------------------------------------
# Test 3 — to_markdown includes a round table with Round column
# ---------------------------------------------------------------------------
def test_to_markdown_includes_round_table(summarizer: LoopSummarizer):
    snap = summarizer.snapshot()
    md = summarizer.to_markdown(snap)
    assert "## Round-by-Round Narrative" in md
    # Table header row
    assert "| Round |" in md
    # At least R1 row should appear
    assert "R1" in md


# ---------------------------------------------------------------------------
# Test 4 — atomic write creates file; monkeypatched os.replace leaves original
# ---------------------------------------------------------------------------
def test_atomic_write_target_file(
    summarizer: LoopSummarizer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Normal write — file should exist afterwards
    out = tmp_path / "STATE_OF_LOOP.md"
    snap = summarizer.snapshot()
    result = summarizer.write(snap, path=out)

    assert result == out
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "# Execute Loop" in content

    # Monkeypatch os.replace to raise so we can verify original is unchanged
    original_content = out.read_text(encoding="utf-8")
    call_count = {"n": 0}

    def _fail_replace(src, dst):
        call_count["n"] += 1
        # Clean up tmp
        try:
            os.unlink(src)
        except OSError:
            pass
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", _fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        summarizer.write(snap, path=out)

    # Original file must be untouched
    assert out.read_text(encoding="utf-8") == original_content
    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# Test 5 — main([]) writes to the default STATE_OF_LOOP.md path
# ---------------------------------------------------------------------------
def test_main_cli_writes_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Write state.json in a tmp directory
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_MINIMAL_STATE), encoding="utf-8")

    # Redirect the default output to tmp_path so we don't pollute the real dir
    expected_out = tmp_path / "STATE_OF_LOOP.md"
    monkeypatch.setattr(
        "scripts.execute_loop.L49_state_summary._DEFAULT_OUT", expected_out
    )
    monkeypatch.setattr(
        "scripts.execute_loop.L49_state_summary._DEFAULT_STATE", state_path
    )

    rc = main([])
    assert rc == 0
    assert expected_out.exists()
    md = expected_out.read_text(encoding="utf-8")
    assert "# Execute Loop" in md


# ---------------------------------------------------------------------------
# Test 6 — snapshot gracefully handles missing L42 / L47 (returns empty fields)
# ---------------------------------------------------------------------------
def test_snapshot_handles_missing_l42_l47_gracefully(
    summarizer: LoopSummarizer, monkeypatch: pytest.MonkeyPatch
):
    # Simulate L42 and L47 being unavailable
    monkeypatch.setattr(
        "scripts.execute_loop.L49_state_summary._L42_AVAILABLE", False
    )
    monkeypatch.setattr(
        "scripts.execute_loop.L49_state_summary._L47_AVAILABLE", False
    )
    monkeypatch.setattr(
        "scripts.execute_loop.L49_state_summary._ReadinessChecker", None
    )
    monkeypatch.setattr(
        "scripts.execute_loop.L49_state_summary._RegressionDetector", None
    )

    # Should not raise
    snap = summarizer.snapshot()

    # L47 regressions: empty list
    assert snap.l47_regressions == []

    # L42 audit: falls back to parsing state.json totals string
    # "PASS 10 / FAIL 0 / SKIP 2 / N/A 5"
    assert snap.l42_audit.get("pass") == 10
    assert snap.l42_audit.get("fail") == 0

    # to_markdown should still work without error
    md = summarizer.to_markdown(snap)
    assert "## Headline" in md
    assert "## L47 Regression Status" in md


# ---------------------------------------------------------------------------
# Test 7 — _collect_event_metadata finds producer from a synthetic module
# ---------------------------------------------------------------------------
def test_event_metadata_collection(tmp_path: Path):
    """A synthetic L*.py with _L46.publish('foo.bar', ...) should produce an entry."""
    synthetic = tmp_path / "L99_synthetic.py"
    synthetic.write_text(
        """\
_L46 = None

def do_thing():
    if _L46 is not None:
        _L46.publish("foo.bar", source="L99", payload={"x": 1})
        _L46.publish("foo.baz", source="L99", payload={"y": 2})
""",
        encoding="utf-8",
    )

    producers, subscribers = _collect_event_metadata(tmp_path)

    assert "L99" in producers, f"Expected L99 in producers, got {producers}"
    assert "foo.bar" in producers["L99"]
    assert "foo.baz" in producers["L99"]
    # No subscribes in this file
    assert "L99" not in subscribers


# ---------------------------------------------------------------------------
# Test 8 — to_markdown includes ## Event-Driven Architecture section
# ---------------------------------------------------------------------------
def test_to_markdown_includes_event_section(summarizer: LoopSummarizer):
    snap = summarizer.snapshot()
    md = summarizer.to_markdown(snap)
    assert "## Event-Driven Architecture" in md
    assert "### Event Producers" in md
    assert "### Event Subscribers" in md
    assert "Total event types in system:" in md


# ---------------------------------------------------------------------------
# Test 9 — total_event_types counts distinct event names across all producers
# ---------------------------------------------------------------------------
def test_total_event_types_count_correct(tmp_path: Path, state_file: Path):
    """Two producers sharing one event name → total_event_types counts it once."""
    # Write two synthetic layer files
    (tmp_path / "L10_alpha.py").write_text(
        """\
_L46 = None
def go():
    _L46.publish("shared.event", source="L10", payload={})
    _L46.publish("unique.alpha", source="L10", payload={})
""",
        encoding="utf-8",
    )
    (tmp_path / "L11_beta.py").write_text(
        """\
_L46 = None
def go():
    _L46.publish("shared.event", source="L11", payload={})
    _L46.publish("unique.beta", source="L11", payload={})
""",
        encoding="utf-8",
    )

    producers, subscribers = _collect_event_metadata(tmp_path)

    # Both layers see "shared.event" but total_event_types counts unique names
    all_events: set = set()
    for evts in producers.values():
        all_events.update(evts)
    total = len(all_events)

    # shared.event + unique.alpha + unique.beta = 3 distinct types
    assert total == 3, f"Expected 3 distinct event types, got {total}: {all_events}"
