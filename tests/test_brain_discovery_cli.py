"""Tests for the loop-management CLI helpers: reset_loop_state + run_discovery.

Fast-only — no heavy ``discover()`` call; the discovery engine and record_discovered
are monkeypatched where needed so the suite runs in <2 s with no GPU/data access.

Convention (brain-test style):
    sys.path is patched before any local import so both ``src.loop.*`` and the
    standalone scripts are importable regardless of cwd.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "loop"))

import pytest  # noqa: E402

from scripts.loop.reset_loop_state import (  # noqa: E402
    load_checkpoint,
    reset_state,
    save_checkpoint,
)
import scripts.loop.run_discovery as run_discovery_mod  # noqa: E402
from scripts.loop.run_discovery import run  # noqa: E402
from src.loop.signal import Verdict  # noqa: E402


# ---------------------------------------------------------------------------
# Tiny stand-in types for monkeypatching discover()
# ---------------------------------------------------------------------------

@dataclass
class _FakeTransformSpec:
    name: str
    kind: str
    cols: Tuple[str, ...]

    def family_key(self) -> str:
        return f"fk_{self.name}"


@dataclass
class _FakeGateResult:
    verdict: Verdict
    wf_all_improve: bool = False
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _FakeDiscoveryResult:
    spec: _FakeTransformSpec
    target: str
    screen_score: float
    gate: _FakeGateResult


def _make_fake_results() -> List[_FakeDiscoveryResult]:
    """Return 3 fake DiscoveryResult-like objects with distinct verdicts."""
    return [
        _FakeDiscoveryResult(
            spec=_FakeTransformSpec("disc_ship_one", "interact", ("pts_l5", "reb_l5")),
            target="pts",
            screen_score=0.42,
            gate=_FakeGateResult(verdict=Verdict.SHIP, wf_all_improve=True,
                                 metrics={"null_z": 4.1}),
        ),
        _FakeDiscoveryResult(
            spec=_FakeTransformSpec("disc_reject_two", "ratio", ("ast_l5", "tov_l5")),
            target="pts",
            screen_score=0.21,
            gate=_FakeGateResult(verdict=Verdict.REJECT, wf_all_improve=False,
                                 metrics={"null_z": 0.9}),
        ),
        _FakeDiscoveryResult(
            spec=_FakeTransformSpec("disc_variance_three", "square", ("fg3m_l5",)),
            target="pts",
            screen_score=0.18,
            gate=_FakeGateResult(verdict=Verdict.VARIANCE_ONLY, wf_all_improve=False,
                                 metrics={"null_z": 2.2}),
        ),
    ]


# ===========================================================================
# 1. reset_state — clears held_out and maxed defers, preserves iterations
# ===========================================================================

def test_reset_clears_held_out_and_maxed_defers():
    """Default reset: clear held_out, drop only maxed (>=3) defers, preserve iterations."""
    ckpt = {
        "iterations": 295,
        "held_out_spent": True,
        "defer_attempts": {"a": 3, "b": 1, "c": 3},
    }
    original_defers = dict(ckpt["defer_attempts"])  # capture for mutation check

    result = reset_state(ckpt)

    assert result["held_out_spent"] is False
    assert result["defer_attempts"] == {"b": 1}, (
        "Only maxed entries (count >= 3) should be dropped; 'b' (count=1) survives"
    )
    assert result["iterations"] == 295, "iterations must be preserved"

    # Input dict must NOT be mutated.
    assert ckpt["held_out_spent"] is True, "input dict was mutated (held_out_spent)"
    assert ckpt["defer_attempts"] == original_defers, "input dict was mutated (defer_attempts)"


# ===========================================================================
# 2. reset_state — clear_all / clear_none / keep_held_out variants
# ===========================================================================

def test_reset_clear_all_and_none():
    """clear_defers='all' empties defer_attempts; 'none' keeps all; keep-held-out preserves True."""
    ckpt = {
        "iterations": 100,
        "held_out_spent": True,
        "defer_attempts": {"x": 3, "y": 2, "z": 1},
    }

    # clear_defers="all" -> empty defer_attempts
    result_all = reset_state(ckpt, clear_defers="all")
    assert result_all["defer_attempts"] == {}, "clear_defers='all' should empty the dict"

    # clear_defers="none" -> unchanged defer_attempts
    result_none = reset_state(ckpt, clear_defers="none")
    assert result_none["defer_attempts"] == {"x": 3, "y": 2, "z": 1}, (
        "clear_defers='none' must keep every entry"
    )

    # clear_held_out=False (--keep-held-out equivalent) -> held_out_spent stays True
    result_keep = reset_state(ckpt, clear_held_out=False, clear_defers="all")
    assert result_keep["held_out_spent"] is True, (
        "clear_held_out=False must NOT change held_out_spent"
    )
    assert result_keep["defer_attempts"] == {}, "defer_attempts still cleared when asked"


# ===========================================================================
# 3. save/load roundtrip + atomic write (no leftover .tmp)
# ===========================================================================

def test_save_load_roundtrip_atomic(tmp_path):
    """Roundtrip via save_checkpoint / load_checkpoint; no leftover .tmp file."""
    ckpt = {
        "iterations": 42,
        "held_out_spent": False,
        "defer_attempts": {"foo": 2},
        "last_run": "2026-06-09T00:00:00Z",
    }
    dest = str(tmp_path / "sub" / "checkpoint.json")

    save_checkpoint(ckpt, dest)

    # No leftover .tmp
    assert not os.path.exists(dest + ".tmp"), ".tmp file must not remain after atomic write"

    # Load back and compare
    loaded = load_checkpoint(dest)
    assert loaded["iterations"] == 42
    assert loaded["held_out_spent"] is False
    assert loaded["defer_attempts"] == {"foo": 2}
    assert loaded["last_run"] == "2026-06-09T00:00:00Z"


# ===========================================================================
# 4. run() monkeypatches discover + record_discovered
# ===========================================================================

def test_run_discovery_records_and_summarizes(tmp_path, monkeypatch):
    """run() calls discover, records every result, and returns correct tally + SHIP names."""
    fake_results = _make_fake_results()
    recorded: list = []

    def _fake_discover(target, *, top_k, device, seen_families=None):
        return fake_results

    def _fake_record(dr, *, date, path=None):
        recorded.append({"name": dr.spec.name, "verdict": dr.gate.verdict.value,
                         "date": date})

    monkeypatch.setattr(run_discovery_mod, "discover", _fake_discover)
    monkeypatch.setattr(run_discovery_mod, "record_discovered", _fake_record)

    ledger = str(tmp_path / "ledger.jsonl")
    result = run(["pts"], top_k=3, device="cpu", date="2026-06-09", ledger_path=ledger)

    # Summary structure
    assert "pts" in result
    pts = result["pts"]
    assert pts["n"] == 3, "should have gated all 3 fake results"

    # Tally counts
    assert pts["tally"].get("SHIP", 0) == 1
    assert pts["tally"].get("REJECT", 0) == 1
    assert pts["tally"].get("VARIANCE_ONLY", 0) == 1

    # SHIP names collected
    assert pts["ships"] == ["disc_ship_one"]
    assert pts["variance"] == ["disc_variance_three"]

    # record_discovered was called once per result
    assert len(recorded) == 3, "record_discovered must be called for every result"
    assert all(r["date"] == "2026-06-09" for r in recorded)


# ===========================================================================
# 5. Ledger roundtrip: record_discovered -> load_discovered_families
# ===========================================================================

def test_discovered_ledger_roundtrip(tmp_path):
    """A recorded family_key is returned by load_discovered_families on reload."""
    from src.loop.discovery import (  # noqa: E402
        DiscoveryResult,
        TransformSpec,
        load_discovered_families,
        record_discovered,
    )
    from src.loop.signal import GateResult  # noqa: E402

    ledger = str(tmp_path / "disc.jsonl")

    spec = TransformSpec(kind="interact", cols=("pts_l5", "reb_l5"))
    gate_res = GateResult(signal_name=spec.name, verdict=Verdict.REJECT,
                          reason="test reject")
    dr = DiscoveryResult(spec=spec, target="pts", screen_score=0.15, gate=gate_res)

    # Before recording: family key not in ledger
    assert spec.family_key() not in load_discovered_families(ledger)

    record_discovered(dr, date="2026-06-09", path=ledger)

    # After recording: family key must be present
    families = load_discovered_families(ledger)
    assert spec.family_key() in families, (
        "family_key must be returned by load_discovered_families after recording"
    )
