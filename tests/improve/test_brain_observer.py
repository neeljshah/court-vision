"""Tests for improve.brain_observer (Milestone-8 ratchet).

INVARIANTS under test:
  - summarize(history) is deterministic: same input -> same output.
  - summarize([]) returns a valid (non-raising) empty summary.
  - summarize(history) with injected history reflects the right verdict counts.
  - observe(history) writes exactly one proposal artifact with the right shape.
  - The observation proposal schema is "brain_observation_v1".
  - apply_to_memory is always False (never mutates anything).
  - observe() and summarize() never raise on missing/corrupt inputs.
  - The proposal contains all required top-level keys.
  - The patterns list is non-empty when history is non-empty.
  - next_to_try is non-empty (always actionable, even on cold start).

stdlib only; no numpy; no gated imports.
Run: python -m pytest tests/improve/test_brain_observer.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from improve.brain_observer import observe, summarize

REQUIRED_OBS_KEYS = (
    "schema", "ts", "n_verdicts", "sport_verdicts",
    "recent_ships", "recent_rejects", "scoreboard", "proof_artifacts",
    "patterns", "next_to_try", "note", "apply_to_memory",
)

REQUIRED_SUMM_KEYS = (
    "n_verdicts", "sport_verdicts", "recent_ships",
    "recent_rejects", "patterns", "next_to_try", "note",
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_history(verdicts):
    """Build a minimal history list from (sport, verdict) pairs."""
    records = []
    for i, (sport, verdict) in enumerate(verdicts):
        r = {
            "ts": "2026-06-18T01:%02d:00+00:00" % i,
            "sport": sport,
            "verdict": verdict,
            "n_settled": 70 + i,
        }
        if verdict in ("SHIP", "REJECT"):
            r["delta_brier"] = 0.008 if verdict == "SHIP" else -0.003
            r["baseline_brier"] = 0.25
            r["recal_brier"] = 0.242 if verdict == "SHIP" else 0.253
            r["reason"] = "test reason for %s" % verdict
        else:
            r["reason"] = "test reason for %s" % verdict
        records.append(r)
    return records


_MIXED_HISTORY = _make_history([
    ("nba", "SHIP"),
    ("nba", "HOLD"),
    ("mlb", "REJECT"),
    ("soccer", "INSUFFICIENT_DATA"),
    ("tennis", "INSUFFICIENT_DATA"),
    ("nba", "SHIP"),
])


# ---------------------------------------------------------------------------
# summarize() -- pure, never-raises, deterministic
# ---------------------------------------------------------------------------


def test_summarize_empty_history_does_not_raise():
    result = summarize([])
    assert isinstance(result, dict)


def test_summarize_empty_has_required_keys():
    result = summarize([])
    for k in REQUIRED_SUMM_KEYS:
        assert k in result, "missing key %r in summarize([])" % k


def test_summarize_empty_n_verdicts_is_zero():
    result = summarize([])
    assert result["n_verdicts"] == 0


def test_summarize_empty_next_to_try_not_empty():
    """Even on cold start, next_to_try should provide a hint."""
    result = summarize([])
    assert len(result["next_to_try"]) >= 1


def test_summarize_mixed_history_verdict_counts():
    result = summarize(_MIXED_HISTORY)
    sv = result["sport_verdicts"]
    assert sv.get("nba", {}).get("SHIP", 0) == 2
    assert sv.get("nba", {}).get("HOLD", 0) == 1
    assert sv.get("mlb", {}).get("REJECT", 0) == 1
    assert sv.get("soccer", {}).get("INSUFFICIENT_DATA", 0) == 1


def test_summarize_n_verdicts_matches_history_length():
    result = summarize(_MIXED_HISTORY)
    assert result["n_verdicts"] == len(_MIXED_HISTORY)


def test_summarize_patterns_non_empty_on_non_empty_history():
    result = summarize(_MIXED_HISTORY)
    assert len(result["patterns"]) >= 1


def test_summarize_patterns_mention_totals():
    result = summarize(_MIXED_HISTORY)
    totals_line = result["patterns"][0]
    assert "6" in totals_line  # total cycles
    assert "SHIP" in totals_line
    assert "REJECT" in totals_line


def test_summarize_recent_ships_at_most_3():
    """recent_ships should contain at most 3 entries."""
    long_history = _make_history([("nba", "SHIP")] * 5)
    result = summarize(long_history)
    assert len(result["recent_ships"]) <= 3


def test_summarize_recent_rejects_at_most_3():
    long_history = _make_history([("mlb", "REJECT")] * 5)
    result = summarize(long_history)
    assert len(result["recent_rejects"]) <= 3


def test_summarize_is_deterministic():
    """Same input -> same output (no randomness)."""
    r1 = summarize(_MIXED_HISTORY)
    r2 = summarize(_MIXED_HISTORY)
    assert r1["patterns"] == r2["patterns"]
    assert r1["next_to_try"] == r2["next_to_try"]
    assert r1["n_verdicts"] == r2["n_verdicts"]


def test_summarize_note_contains_calibration_disclaimer():
    result = summarize(_MIXED_HISTORY)
    assert "calibration" in result["note"].lower()


def test_summarize_corrupt_entry_does_not_raise():
    """A history list with a corrupt (non-dict) entry is handled gracefully."""
    bad_history = [{"sport": "nba", "verdict": "SHIP"}, "bad_entry", None]
    try:
        result = summarize(bad_history)  # type: ignore
        assert isinstance(result, dict)
    except Exception as exc:
        raise AssertionError("summarize() raised on corrupt input: %r" % exc) from exc


def test_summarize_hold_patterns_mention_freshness():
    """3+ HOLDs should surface a freshness suggestion."""
    hold_history = _make_history([("nba", "HOLD")] * 3)
    result = summarize(hold_history)
    combined = " ".join(result["next_to_try"]).lower()
    assert "freshness" in combined or "calibrated" in combined


# ---------------------------------------------------------------------------
# observe() -- writes a proposal file
# ---------------------------------------------------------------------------


def test_observe_writes_exactly_one_file():
    with tempfile.TemporaryDirectory() as tmp:
        proposals_dir = Path(tmp) / "proposals"
        path = observe(_MIXED_HISTORY, proposals_dir=proposals_dir)
        assert path.exists(), "observe() did not write a file"
        files = list(proposals_dir.iterdir())
        assert len(files) == 1


def test_observe_valid_json():
    with tempfile.TemporaryDirectory() as tmp:
        path = observe(_MIXED_HISTORY, proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert isinstance(data, dict)


def test_observe_all_required_keys_present():
    with tempfile.TemporaryDirectory() as tmp:
        path = observe(_MIXED_HISTORY, proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        for k in REQUIRED_OBS_KEYS:
            assert k in data, "missing key %r in observe() proposal" % k


def test_observe_schema_is_brain_observation_v1():
    with tempfile.TemporaryDirectory() as tmp:
        path = observe(_MIXED_HISTORY, proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert data["schema"] == "brain_observation_v1"


def test_observe_apply_to_memory_always_false():
    with tempfile.TemporaryDirectory() as tmp:
        path = observe(_MIXED_HISTORY, proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert data["apply_to_memory"] is False


def test_observe_n_verdicts_matches():
    with tempfile.TemporaryDirectory() as tmp:
        path = observe(_MIXED_HISTORY, proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert data["n_verdicts"] == len(_MIXED_HISTORY)


def test_observe_sport_verdicts_nba_ships():
    with tempfile.TemporaryDirectory() as tmp:
        path = observe(_MIXED_HISTORY, proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert data["sport_verdicts"].get("nba", {}).get("SHIP", 0) == 2


def test_observe_patterns_non_empty():
    with tempfile.TemporaryDirectory() as tmp:
        path = observe(_MIXED_HISTORY, proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert len(data["patterns"]) >= 1


def test_observe_next_to_try_non_empty():
    with tempfile.TemporaryDirectory() as tmp:
        path = observe(_MIXED_HISTORY, proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert len(data["next_to_try"]) >= 1


def test_observe_note_contains_calibration():
    with tempfile.TemporaryDirectory() as tmp:
        path = observe(_MIXED_HISTORY, proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert "calibration" in data["note"].lower()


def test_observe_empty_history_does_not_raise():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            path = observe([], proposals_dir=Path(tmp))
            assert path.exists()
            data = json.loads(path.read_text(encoding="ascii"))
            assert data["n_verdicts"] == 0
        except Exception as exc:
            raise AssertionError("observe([]) raised: %r" % exc) from exc


def test_observe_scoreboard_field_exists_and_is_none_or_dict():
    """scoreboard field may be None (file absent) or a dict (file present)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = observe([], proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert "scoreboard" in data
        assert data["scoreboard"] is None or isinstance(data["scoreboard"], dict)


def test_observe_proof_artifacts_is_list():
    with tempfile.TemporaryDirectory() as tmp:
        path = observe([], proposals_dir=Path(tmp))
        data = json.loads(path.read_text(encoding="ascii"))
        assert isinstance(data["proof_artifacts"], list)


def test_observe_does_not_raise_on_corrupt_history():
    """observe() with a partially-corrupt history list must not raise."""
    bad = [{"sport": "nba", "verdict": "SHIP"}, None, 42, "garbage"]
    with tempfile.TemporaryDirectory() as tmp:
        try:
            path = observe(bad, proposals_dir=Path(tmp))  # type: ignore
            assert path is not None
        except Exception as exc:
            raise AssertionError("observe() raised on corrupt history: %r" % exc) from exc


def test_two_observations_produce_two_distinct_files():
    with tempfile.TemporaryDirectory() as tmp:
        proposals_dir = Path(tmp) / "obs"
        p1 = observe(_MIXED_HISTORY, proposals_dir=proposals_dir)
        p2 = observe(_make_history([("nba", "REJECT")]), proposals_dir=proposals_dir)
        assert p1 != p2
        files = list(proposals_dir.iterdir())
        assert len(files) == 2


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print("PASS  %s" % fn.__name__)
        passed += 1
    print("\n%d/%d brain_observer tests passed." % (passed, len(fns)))
