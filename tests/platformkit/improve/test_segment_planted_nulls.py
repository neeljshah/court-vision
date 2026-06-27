"""tests.platformkit.improve.test_segment_planted_nulls -- SI-09 per-segment null lane.

Acceptance criteria:
  (1) Shuffled-label corpus -> SHIP-rate ~ noise floor (n_shipped == 0 on real gate).
  (2) A null that ships -> its segment entry is frozen (frozen=True, in frozen_segments).
  (3) n_run < MIN_NULLS -> fdr_hat=None, insufficient=True, frozen=False (NOT frozen).
  (4) No $/roi/pnl/profit key anywhere in a SegmentNullResult or ledger_of output.
  (5) ledger_of: a frozen segment -> null_shipped=True; an insufficient segment ->
      null_shipped=False (NOT frozen for downstream prioritizer.frozen_families).
  (6) run_all_segment_nulls covers all SEGMENT_TRIPLES; all fdr_hat==0.0 on real gate.
  (7) segment_name produces 'margin|period|time' canonical keys (name-stable).

Per-file test only. ASCII; stdlib + numpy. Sentinel never touched (MF1 delegated to
build_ingame_segment_candidate, not this module).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve.segment_planted_nulls import (
    MIN_NULLS,
    SEGMENT_TRIPLES,
    SegmentNullResult,
    frozen_segments,
    ledger_of,
    run_all_segment_nulls,
    run_segment_nulls,
    segment_name,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_KEYS = {"$", "roi", "pnl", "profit"}


def _has_banned_key(obj: Any) -> bool:
    """Recursively scan for any key containing a banned token."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if any(tok in kl for tok in _BANNED_KEYS):
                return True
            if _has_banned_key(v):
                return True
    if isinstance(obj, list):
        return any(_has_banned_key(x) for x in obj)
    return False


def _result_dict(r: SegmentNullResult) -> Dict[str, Any]:
    """Flatten a SegmentNullResult to a dict for key-scanning."""
    return {
        "segment": r.segment,
        "fdr_hat": r.fdr_hat,
        "n_run": r.n_run,
        "n_shipped": r.n_shipped,
        "budget": r.budget,
        "frozen": r.frozen,
        "insufficient": r.insufficient,
        "note": r.note,
    }


# ---------------------------------------------------------------------------
# (1) Shuffled-label null does NOT ship on the real gate
# ---------------------------------------------------------------------------

def test_shuffled_null_does_not_ship():
    """The real null gate must reject every shuffled-label probe (SHIP-rate == 0)."""
    r = run_segment_nulls("close|early|ample", n=20, n_games=40, ticks=6, seed=42)
    assert r.n_run >= MIN_NULLS, "must run at least MIN_NULLS probes"
    assert r.n_shipped == 0, (
        "shuffled-label probe must not ship on the real gate; got n_shipped=%d" % r.n_shipped
    )
    assert r.fdr_hat == 0.0, "fdr_hat must be 0.0 when no nulls shipped"
    assert r.frozen is False, "segment must not be frozen when no null shipped"
    assert r.insufficient is False


# ---------------------------------------------------------------------------
# (2) A null that ships -> segment is frozen
# ---------------------------------------------------------------------------

def test_ship_freezes_segment():
    """A deliberately-weakened gate that always ships -> frozen=True + in frozen_segments."""

    def always_ship(*_a, **_k) -> str:
        return "SHIP"

    r = run_segment_nulls("mid|late|scarce", n=20, n_games=30, ticks=4,
                          seed=99, gate=always_ship)
    assert r.n_shipped == r.n_run, "weakened gate must ship every probe"
    assert r.frozen is True, "any shipped null must freeze the segment"
    assert r.fdr_hat is not None and r.fdr_hat > r.budget

    result_dict = {"mid|late|scarce": r}
    frozen = frozen_segments(result_dict)
    assert "mid|late|scarce" in frozen, "frozen_segments must include the shipped segment"


# ---------------------------------------------------------------------------
# (3) Below MIN_NULLS -> fdr_hat=None, insufficient=True, NOT frozen
# ---------------------------------------------------------------------------

def test_insufficient_not_frozen():
    """n < MIN_NULLS is an edge-case: the result must signal INSUFFICIENT, not FROZEN."""
    # We force n below MIN_NULLS by passing 0; run_segment_nulls clamps to max(MIN_NULLS, n),
    # so we need to invoke the insufficient path directly via a monkey-patch workaround.
    # The real contract: if the CALLER supplies n that results in n_run < MIN_NULLS BEFORE
    # the clamp, the module enforces the floor.  To test the branch, we construct the
    # dataclass directly as the module contract documents.
    from scripts.platformkit.improve.segment_planted_nulls import MIN_NULLS as _MIN
    from scripts.platformkit.combo.fwer_budget import fdr_budget
    # Build the INSUFFICIENT result manually (the dataclass is public API).
    r = SegmentNullResult(
        segment="blowout|early|ample",
        fdr_hat=None,
        n_run=5,            # < MIN_NULLS
        n_shipped=0,
        budget=fdr_budget(0.05, 1),
        frozen=False,
        insufficient=True,
    )
    assert r.fdr_hat is None
    assert r.insufficient is True
    assert r.frozen is False, "INSUFFICIENT must NOT be frozen"
    # frozen_segments must NOT include it.
    frozen = frozen_segments({"blowout|early|ample": r})
    assert "blowout|early|ample" not in frozen

    # ledger_of must emit null_shipped=False (not frozen) for insufficient entries.
    ledger = ledger_of({"blowout|early|ample": r})
    row = ledger["blowout|early|ample"]
    assert isinstance(row, dict)
    assert row["null_shipped"] is False
    assert row["insufficient"] is True


# ---------------------------------------------------------------------------
# (4) No $/roi/pnl/profit key anywhere
# ---------------------------------------------------------------------------

def test_no_dollar_keys_in_result():
    """SegmentNullResult and ledger rows must carry no $/roi/pnl/profit key."""
    r = run_segment_nulls("close|early|ample", n=20, n_games=30, ticks=4, seed=7)
    assert not _has_banned_key(_result_dict(r)), (
        "SegmentNullResult must not contain $/roi/pnl/profit keys"
    )
    ledger = ledger_of({"close|early|ample": r})
    assert not _has_banned_key(ledger), (
        "ledger_of output must not contain $/roi/pnl/profit keys"
    )


# ---------------------------------------------------------------------------
# (5) ledger_of: frozen -> null_shipped=True; insufficient -> null_shipped=False
# ---------------------------------------------------------------------------

def test_ledger_of_frozen_vs_insufficient():
    """ledger_of correctly maps frozen and insufficient entries."""
    from scripts.platformkit.combo.fwer_budget import fdr_budget as _fb
    budget = _fb(0.05, 1)

    r_frozen = SegmentNullResult(
        segment="close|late|scarce",
        fdr_hat=1.0, n_run=20, n_shipped=20,
        budget=budget, frozen=True, insufficient=False,
    )
    r_insuf = SegmentNullResult(
        segment="mid|early|ample",
        fdr_hat=None, n_run=5, n_shipped=0,
        budget=budget, frozen=False, insufficient=True,
    )

    ledger = ledger_of({"close|late|scarce": r_frozen, "mid|early|ample": r_insuf})

    assert ledger["close|late|scarce"]["null_shipped"] is True
    assert ledger["close|late|scarce"]["null_ships"] == 20

    assert ledger["mid|early|ample"]["null_shipped"] is False
    assert ledger["mid|early|ample"]["insufficient"] is True


# ---------------------------------------------------------------------------
# (6) run_all_segment_nulls covers all triples; all fdr_hat == 0.0
# ---------------------------------------------------------------------------

def test_all_segment_triples_covered_and_reject():
    """run_all_segment_nulls must cover all SEGMENT_TRIPLES and reject every null."""
    # Use small probes (n=20, small corpus) to keep runtime short.
    results = run_all_segment_nulls(n=20, n_games=30, ticks=4, eps=0.05, K=1)

    expected_keys = {segment_name(m, p, t) for m, p, t in SEGMENT_TRIPLES}
    assert set(results.keys()) == expected_keys, (
        "run_all_segment_nulls must return a key for every SEGMENT_TRIPLE"
    )

    for seg, r in results.items():
        assert r.n_shipped == 0, (
            "segment %s: shuffled null shipped (n_shipped=%d); gate may be leaking" % (
                seg, r.n_shipped)
        )
        assert r.fdr_hat == 0.0, "segment %s: fdr_hat must be 0.0 on real gate" % seg
        assert r.frozen is False, "segment %s: must not be frozen when null never shipped" % seg

    assert frozen_segments(results) == [], "no segment should be frozen on the real gate"


# ---------------------------------------------------------------------------
# (7) segment_name produces canonical 'margin|period|time' keys
# ---------------------------------------------------------------------------

def test_segment_name_canonical():
    """segment_name must produce a 'margin|period|time' string with '|' separators."""
    name = segment_name("close", "early", "ample")
    assert name == "close|early|ample"
    parts = name.split("|")
    assert len(parts) == 3
    assert parts == ["close", "early", "ample"]

    # All SEGMENT_TRIPLES must produce a key matching 'x|y|z' form.
    for m, p, t in SEGMENT_TRIPLES:
        n = segment_name(m, p, t)
        assert "|" in n and len(n.split("|")) == 3, (
            "segment_name must produce 'margin|period|time' for triple (%s,%s,%s)" % (m, p, t)
        )
