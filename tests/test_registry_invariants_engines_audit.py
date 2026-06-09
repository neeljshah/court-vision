"""Invariant guards for the team_system registry (idempotent register + integrity).

Verifies the documented registry contract used by the loop substrate:
  - register(row) is PURE/idempotent: same id twice -> no-op, no new part
  - register_many dedups against the existing index
  - integrity: two rows with the same id but DIFFERENT def_cols -> RuntimeError
  - transactional_write: a failing validator never touches the live file

All writes are redirected to a tmp registry dir so the real registry is untouched.
This file is OWNED by the engines-audit task (registry/* is in its editable set).
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "team_system"))


@pytest.fixture
def reg_module(tmp_path, monkeypatch):
    import registry.store as store
    monkeypatch.setattr(store, "REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setattr(store, "_LOCK", str(tmp_path / "registry" / ".lock"))
    return store


def test_register_is_idempotent(reg_module):
    r = reg_module.Registry("calibration_registry")
    row = dict(key="k1", shapeErr=0.5, coverage=0.8, reliability=1.0, n=100, updated_utc=1)
    id1 = r.register(row)
    parts1, len1 = len(r._parts()), len(r)
    id2 = r.register(row)  # same id -> no-op
    assert id1 == id2
    assert len(r) == len1
    assert len(r._parts()) == parts1  # NO new shard part written


def test_register_many_dedups(reg_module):
    r = reg_module.Registry("calibration_registry")
    row1 = dict(key="k1", shapeErr=0.5, coverage=0.8, reliability=1.0, n=100, updated_utc=1)
    row2 = dict(key="k2", shapeErr=0.1, coverage=0.9, reliability=1.0, n=50, updated_utc=2)
    r.register(row1)
    res = r.register_many([row1, row2])
    assert res == {"registered": 1, "skipped": 1}


def test_integrity_violation_on_conflicting_def(reg_module):
    r = reg_module.Registry("signal_registry")
    base = dict(signal_id="s1", grain="g", entity_scope="e", domain_tags="d", source="src",
                formula_ast="ast", transform_chain="tc", asof_fn="af", causal_sign="+")
    r.register(base)
    conflict = dict(base, causal_sign="-")  # same id, different DEF column
    with pytest.raises(RuntimeError, match="INTEGRITY VIOLATION"):
        r._write_part([r._coerce(conflict)])


def test_transactional_write_failed_validator_keeps_live(reg_module, tmp_path):
    live = str(tmp_path / "artifact.txt")
    with open(live, "w") as f:
        f.write("ORIGINAL")

    def _write(staging):
        with open(staging, "w") as f:
            f.write("NEW")

    def _bad_validator(staging):
        raise ValueError("rejected")

    ok = reg_module.transactional_write(live, _write, validator=_bad_validator)
    assert ok is False
    with open(live) as f:
        assert f.read() == "ORIGINAL"  # live file untouched on validator failure
    assert not os.path.exists(live + ".staging")  # staging cleaned up
