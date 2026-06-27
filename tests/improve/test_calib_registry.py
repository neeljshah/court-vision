"""Per-file test for the calibration-artifact registry (Milestone-8 ratchet).

Run ONLY this file (the box freezes on a bare pytest):
    cd /c/Users/neelj/nba-ai-system && \
      conda run -n <env> python -m pytest tests/improve/test_calib_registry.py -q

Covers the ratchet's CURRENT-pointer contract:
  - save + promote + current round-trip,
  - an n_features_in mismatch BLOCKS promote (parity invariant),
  - a simulated PARTIAL/torn swap leaves the prior CURRENT intact + current()
    degrades to None on a garbage pointer (never raises),
  - rollback re-promotes the previous version.
"""
from __future__ import annotations

import os
import sys
import json
import pathlib

import pytest

# Import via the `improve.` package path so the CalibArtifact class the test
# constructs is byte-identical to the one registry.py imports (a sys.path inject
# of improve/ would create a *second* module object and break isinstance).
_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from improve.calib_artifact import CalibArtifact, integrity_ok  # noqa: E402
from improve import registry  # noqa: E402


def _mk(version=1, kind="unit_kind", n_features_in=8, declare_meta=True):
    meta = {"corpora": ["A", "B"], "kfold": 4}
    if declare_meta:
        meta["n_features_in"] = n_features_in
    return CalibArtifact(
        version=version,
        created_at="2026-06-18T00:00:00+00:00",
        kind=kind,
        n_features_in=n_features_in,
        params={"a": [1.0, 2.0], "b": 0.5},
        meta=meta,
    )


def test_save_promote_current_round_trip(tmp_path):
    root = str(tmp_path)
    art = _mk(n_features_in=8)
    path = registry.save_version(art, root=root)
    assert path.exists()
    assert registry.list_versions("unit_kind", root=root) == [1]
    # nothing live until promoted
    assert registry.current("unit_kind", root=root) is None
    assert registry.promote("unit_kind", 1, root=root) is True
    live = registry.current("unit_kind", root=root)
    assert live is not None
    assert live.version == 1
    assert live.n_features_in == 8
    assert live.params == {"a": [1.0, 2.0], "b": 0.5}
    # round-trips through dict/json cleanly
    assert CalibArtifact.from_dict(live.to_dict()) == live


def test_save_version_is_monotone_and_append_only(tmp_path):
    root = str(tmp_path)
    registry.save_version(_mk(), root=root)
    registry.save_version(_mk(), root=root)
    registry.save_version(_mk(), root=root)
    assert registry.list_versions("unit_kind", root=root) == [1, 2, 3]


def test_feature_mismatch_blocks_promote(tmp_path):
    root = str(tmp_path)
    # artifact claims 8 features but its meta declares 7 -> integrity FAILS.
    bad = CalibArtifact(
        version=1,
        created_at="2026-06-18T00:00:00+00:00",
        kind="unit_kind",
        n_features_in=8,
        params={},
        meta={"n_features_in": 7},
    )
    assert integrity_ok(bad) is False
    registry.save_version(bad, root=root)
    assert registry.promote("unit_kind", 1, root=root) is False
    # nothing went live
    assert registry.current("unit_kind", root=root) is None


def test_integrity_ok_against_external_meta():
    art = _mk(n_features_in=8, declare_meta=False)
    assert integrity_ok(art, {"n_features_in": 8}) is True
    assert integrity_ok(art, {"n_features_in": 9}) is False


def test_partial_swap_leaves_prior_current_intact(tmp_path):
    root = str(tmp_path)
    registry.save_version(_mk(), root=root)
    registry.save_version(_mk(), root=root)
    assert registry.promote("unit_kind", 1, root=root) is True
    assert registry.current("unit_kind", root=root).version == 1

    # Simulate a TORN swap: a leftover .tmp pointer + a half-written CURRENT.
    pointer = tmp_path / "unit_kind" / "CURRENT.json"
    torn_tmp = pointer.with_name(pointer.name + ".tmp.999")
    torn_tmp.write_text('{"version": 2', encoding="ascii")  # truncated json

    # The real CURRENT pointer is untouched -> v1 still live, no raise.
    assert registry.current("unit_kind", root=root).version == 1

    # If CURRENT itself is garbage, current() degrades to None (never raises).
    pointer.write_text("{not json", encoding="ascii")
    assert registry.current("unit_kind", root=root) is None


def test_current_none_on_missing_kind(tmp_path):
    assert registry.current("never_saved", root=str(tmp_path)) is None


def test_rollback_to_previous_version(tmp_path):
    root = str(tmp_path)
    registry.save_version(_mk(), root=root)
    registry.save_version(_mk(), root=root)
    assert registry.promote("unit_kind", 2, root=root) is True
    assert registry.current("unit_kind", root=root).version == 2
    rolled = registry.rollback("unit_kind", root=root)
    assert rolled == 1
    assert registry.current("unit_kind", root=root).version == 1
    # no further fallback below v1
    assert registry.rollback("unit_kind", root=root) is None


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
