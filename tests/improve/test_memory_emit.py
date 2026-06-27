"""Tests for improve.memory_emit.emit_memory_proposal (Milestone-8 ratchet).

INVARIANTS under test:
  - A SHIP verdict emits exactly one proposal artifact with the right schema shape.
  - The proposal file is valid JSON and contains all required keys.
  - apply_to_memory is always False (NEVER writes MEMORY.md).
  - REJECT/HOLD/INSUFFICIENT_DATA verdicts also emit valid artifacts.
  - A missing/corrupt verdict never raises; emits a PROPOSAL_ERROR artifact.
  - The verdict dict's metrics are faithfully copied (numerics only, not nulls).
  - The proposals_dir override works; files land in the temp dir, not the real one.
  - Writing twice for two different verdicts produces two distinct files.
  - The MEMORY.md file is NEVER created or modified (hard invariant).

stdlib only; no numpy; no gated imports.
Run: python -m pytest tests/improve/test_memory_emit.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from improve.memory_emit import emit_memory_proposal, _DEFAULT_PROPOSALS_DIR

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_MEMORY_MD = _REPO / ".claude" / "projects" / "C--Users-neelj" / "memory" / "MEMORY.md"
_REAL_MEMORY_DIR = _REPO / ".claude" / "projects" / "C--Users-neelj" / "memory"

REQUIRED_KEYS = (
    "schema", "ts", "verdict_ts", "sport", "verdict",
    "headline", "metrics", "reason", "note", "apply_to_memory", "source_ledger",
)


def _ship_verdict(sport="nba"):
    return {
        "ts": "2026-06-18T01:00:00.000000+00:00",
        "sport": sport,
        "verdict": "SHIP",
        "n_settled": 120,
        "baseline_brier": 0.24,
        "recal_brier": 0.232,
        "delta_brier": 0.008,
        "baseline_ece": 0.05,
        "recal_ece": 0.04,
        "dm_stat": 2.1,
        "dm_p": 0.036,
        "dm_n": 120,
        "reason": "recal improves Brier by +0.00800 (> 0.005) with no regression/leak",
        "note": "calibration != edge",
    }


def _reject_verdict(sport="mlb"):
    return {
        "ts": "2026-06-18T01:05:00.000000+00:00",
        "sport": sport,
        "verdict": "REJECT",
        "n_settled": 80,
        "baseline_brier": 0.25,
        "recal_brier": 0.258,
        "delta_brier": -0.008,
        "reason": "recalibrated forecaster regresses vs frozen baseline",
        "note": "calibration != edge",
    }


def _hold_verdict(sport="soccer"):
    return {
        "ts": "2026-06-18T01:10:00.000000+00:00",
        "sport": sport,
        "verdict": "HOLD",
        "n_settled": 90,
        "delta_brier": 0.001,
        "reason": "no meaningful calibration improvement",
    }


def _insuff_verdict(sport="tennis"):
    return {
        "ts": "2026-06-18T01:15:00.000000+00:00",
        "sport": sport,
        "verdict": "INSUFFICIENT_DATA",
        "n_settled": 5,
        "reason": "only 5 real settled games; need >= 60",
    }


# ---------------------------------------------------------------------------
# SHIP: shape and content
# ---------------------------------------------------------------------------


def test_ship_emits_exactly_one_file():
    """A SHIP verdict emits exactly one proposal artifact in the proposals_dir."""
    with tempfile.TemporaryDirectory() as tmp:
        proposals_dir = Path(tmp) / "proposals"
        path = emit_memory_proposal(_ship_verdict(), proposals_dir=proposals_dir)
        assert path.exists(), "emitted file does not exist: %s" % path
        files = list(proposals_dir.iterdir())
        assert len(files) == 1, "expected 1 file, got %d" % len(files)


def test_ship_valid_json():
    """The emitted proposal is valid, parseable JSON."""
    with tempfile.TemporaryDirectory() as tmp:
        path = emit_memory_proposal(_ship_verdict(), proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert isinstance(data, dict)


def test_ship_all_required_keys_present():
    """Every required schema key is present on a SHIP proposal."""
    with tempfile.TemporaryDirectory() as tmp:
        path = emit_memory_proposal(_ship_verdict(), proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        for k in REQUIRED_KEYS:
            assert k in data, "missing required key %r in proposal" % k


def test_ship_schema_is_memory_proposal_v1():
    with tempfile.TemporaryDirectory() as tmp:
        path = emit_memory_proposal(_ship_verdict(), proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert data["schema"] == "memory_proposal_v1"


def test_ship_verdict_field_is_ship():
    with tempfile.TemporaryDirectory() as tmp:
        path = emit_memory_proposal(_ship_verdict(), proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert data["verdict"] == "SHIP"


def test_ship_apply_to_memory_always_false():
    """apply_to_memory must be False; the emitter never touches MEMORY.md."""
    with tempfile.TemporaryDirectory() as tmp:
        path = emit_memory_proposal(_ship_verdict(), proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert data["apply_to_memory"] is False


def test_ship_metrics_contains_numeric_fields():
    """Numeric fields from the verdict are faithfully reproduced in metrics."""
    with tempfile.TemporaryDirectory() as tmp:
        v = _ship_verdict()
        path = emit_memory_proposal(v, proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        m = data["metrics"]
        assert "delta_brier" in m
        assert abs(m["delta_brier"] - v["delta_brier"]) < 1e-9
        assert "baseline_brier" in m
        assert "recal_brier" in m


def test_ship_sport_field_lowercase():
    with tempfile.TemporaryDirectory() as tmp:
        path = emit_memory_proposal(_ship_verdict(sport="NBA"), proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert data["sport"] == "nba"


def test_ship_reason_copied():
    with tempfile.TemporaryDirectory() as tmp:
        v = _ship_verdict()
        path = emit_memory_proposal(v, proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert v["reason"] in data["reason"]


def test_ship_headline_not_empty():
    with tempfile.TemporaryDirectory() as tmp:
        path = emit_memory_proposal(_ship_verdict(), proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert isinstance(data["headline"], str) and len(data["headline"]) > 10


def test_ship_note_contains_calibration_disclaimer():
    with tempfile.TemporaryDirectory() as tmp:
        path = emit_memory_proposal(_ship_verdict(), proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert "calibration" in data["note"].lower()
        assert "edge" in data["note"].lower()


# ---------------------------------------------------------------------------
# Other verdict types
# ---------------------------------------------------------------------------


def test_reject_verdict_emits_valid_proposal():
    with tempfile.TemporaryDirectory() as tmp:
        path = emit_memory_proposal(_reject_verdict(), proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert data["verdict"] == "REJECT"
        assert data["apply_to_memory"] is False
        for k in REQUIRED_KEYS:
            assert k in data


def test_hold_verdict_emits_valid_proposal():
    with tempfile.TemporaryDirectory() as tmp:
        path = emit_memory_proposal(_hold_verdict(), proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert data["verdict"] == "HOLD"
        assert data["apply_to_memory"] is False


def test_insufficient_data_verdict_emits_valid_proposal():
    with tempfile.TemporaryDirectory() as tmp:
        path = emit_memory_proposal(_insuff_verdict(), proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert data["verdict"] == "INSUFFICIENT_DATA"
        assert data["apply_to_memory"] is False


# ---------------------------------------------------------------------------
# Robustness / never-raises contract
# ---------------------------------------------------------------------------


def test_empty_dict_does_not_raise():
    """An empty verdict dict is handled gracefully; emits a PROPOSAL_ERROR."""
    with tempfile.TemporaryDirectory() as tmp:
        path = emit_memory_proposal({}, proposals_dir=Path(tmp))
        assert path.exists()
        data = json.loads(path.read_text(encoding="ascii"))
        assert isinstance(data["schema"], str)
        assert data["apply_to_memory"] is False


def test_none_verdict_field_does_not_raise():
    with tempfile.TemporaryDirectory() as tmp:
        path = emit_memory_proposal({"verdict": None, "sport": "nba"}, proposals_dir=Path(tmp))
        assert path.exists()
        data = json.loads(path.read_text(encoding="ascii"))
        assert "schema" in data


def test_corrupt_input_type_does_not_raise():
    """Passing a non-dict does not raise (type-ignored, best-effort)."""
    with tempfile.TemporaryDirectory() as tmp:
        # Suppress type errors; the contract is: never raise.
        try:
            path = emit_memory_proposal("not_a_dict", proposals_dir=Path(tmp))  # type: ignore
            assert path is not None
        except Exception as exc:
            raise AssertionError("emit_memory_proposal raised: %r" % exc) from exc


def test_two_verdicts_produce_two_files():
    """Emitting two different verdicts creates two distinct proposal files."""
    with tempfile.TemporaryDirectory() as tmp:
        proposals_dir = Path(tmp) / "props"
        p1 = emit_memory_proposal(_ship_verdict(), proposals_dir=proposals_dir)
        p2 = emit_memory_proposal(_reject_verdict(), proposals_dir=proposals_dir)
        assert p1 != p2
        files = list(proposals_dir.iterdir())
        assert len(files) == 2


# ---------------------------------------------------------------------------
# MEMORY.md mutation guard (the hard invariant)
# ---------------------------------------------------------------------------


def test_memory_md_never_created_or_modified(tmp_path):
    """emit_memory_proposal MUST NOT create or modify MEMORY.md."""
    # Capture mtime of the real MEMORY.md if it exists.
    real_mtime_before = _MEMORY_MD.stat().st_mtime if _MEMORY_MD.exists() else None

    emit_memory_proposal(_ship_verdict(), proposals_dir=tmp_path / "proposals")

    if real_mtime_before is not None:
        real_mtime_after = _MEMORY_MD.stat().st_mtime
        assert real_mtime_before == real_mtime_after, (
            "MEMORY.md was MODIFIED by emit_memory_proposal -- hard invariant violated"
        )
    else:
        # It did not exist before; it must still not exist.
        assert not _MEMORY_MD.exists(), (
            "MEMORY.md was CREATED by emit_memory_proposal -- hard invariant violated"
        )


def test_memory_dir_not_written(tmp_path):
    """emit_memory_proposal must not write any file under the real memory dir."""
    if _REAL_MEMORY_DIR.exists():
        before = set(_REAL_MEMORY_DIR.rglob("*"))
    else:
        before = set()

    emit_memory_proposal(_ship_verdict(), proposals_dir=tmp_path / "proposals")

    if _REAL_MEMORY_DIR.exists():
        after = set(_REAL_MEMORY_DIR.rglob("*"))
        new_files = after - before
        assert not new_files, (
            "emit_memory_proposal wrote new file(s) under memory dir: %s" % new_files
        )


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        # Inject a tmp_path arg for tests that need it.
        import inspect
        sig = inspect.signature(fn)
        if "tmp_path" in sig.parameters:
            with tempfile.TemporaryDirectory() as td:
                fn(tmp_path=Path(td))
        else:
            fn()
        print("PASS  %s" % fn.__name__)
        passed += 1
    print("\n%d/%d memory_emit tests passed." % (passed, len(fns)))
