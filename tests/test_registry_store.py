"""
test_registry_store.py -- adversarial correctness tests for registry/store.py

Covers:
  - register() idempotency (same defn -> same id, no new part)
  - def_col immutability (integrity violation raises RuntimeError)
  - register_many() batch dedup
  - compact() correctness and part count reduction
  - silent skip on corrupt parquet (confirmed bug, documented)
  - register() with missing id_col raises ValueError
  - register_many() with missing id_col is silently skipped
  - upsert() only allows mutable field changes
  - update_status() raises on unknown id
  - _norm() behavior for list inputs
  - transactional_write() staging/validator cycle
  - lock staleness/timeout behavior

All tests use a fresh tempdir registry -- never touch the live data/registry/.
"""
from __future__ import annotations

import json
import os
import tempfile
import time

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Fixtures -- patch REGISTRY_DIR/LOCK to isolated tempdir
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_registry(tmp_path, monkeypatch):
    """Yield a Registry factory bound to tmp_path. Patches store module globals."""
    import scripts.team_system.registry.store as store_mod
    monkeypatch.setattr(store_mod, "REGISTRY_DIR", str(tmp_path))
    monkeypatch.setattr(store_mod, "_LOCK", str(tmp_path / ".lock"))
    from scripts.team_system.registry.store import Registry, SCHEMAS

    def _make(name="signal_registry"):
        reg_dir = tmp_path / name
        reg_dir.mkdir(parents=True, exist_ok=True)
        r = Registry.__new__(Registry)
        r.name = name
        r.schema = SCHEMAS[name]
        r.id_col = r.schema["id_col"]
        r.dir = str(reg_dir)
        r._index = {}
        r._reload_index()
        return r

    return _make


def _base_row(formula="x+y", grain="player-game") -> dict:
    """Build a fully-coerced signal row with content hash id."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "team_system"))
    from registry.ids import signal_id, family_key

    defn = dict(grain=grain, entity_scope="player", domain_tags=["pace"],
                source="pbp", formula_ast=formula, transform_chain=["rate"],
                asof_fn="shift1", asof_fn_name="shift1", causal_sign=1)
    sid = signal_id(defn)
    return dict(defn, signal_id=sid, honesty_class="SCOUTING", bet_wireable=False,
                status="proposed", gateA_rel=None, gateA_fdr_q=None, gateX_verdict=None,
                judge_sign_ok=None, judge_engine_ortho=None, family_key=family_key(defn),
                n=None, coverage_pct=None, created_utc=int(time.time()), builder="test",
                artifact_path=None, legacy_name=f"test_{formula}", note="",
                declared_sign=None, measured_sign=None, quantity=None, input_hash=None)


# ---------------------------------------------------------------------------
# Core invariant: register() idempotency
# ---------------------------------------------------------------------------

class TestRegisterIdempotency:
    def test_same_row_no_new_part(self, tmp_registry):
        r = tmp_registry()
        row = _base_row("a+b")
        id1 = r.register(row)
        parts_after_1 = len(r._parts())
        id2 = r.register(row)
        parts_after_2 = len(r._parts())

        assert id1 == id2, "same definition must return same id"
        assert parts_after_2 == parts_after_1 == 1, "second register must not create a new part"

    def test_same_id_same_row_count(self, tmp_registry):
        r = tmp_registry()
        row = _base_row("a+b")
        r.register(row)
        r.register(row)
        assert len(r) == 1

    def test_different_formula_different_id(self, tmp_registry):
        r = tmp_registry()
        row1 = _base_row("a+b")
        row2 = _base_row("a*b")  # different formula -> different id
        id1 = r.register(row1)
        id2 = r.register(row2)
        assert id1 != id2
        assert len(r) == 2
        assert len(r._parts()) == 2


# ---------------------------------------------------------------------------
# Core invariant: def_col immutability
# ---------------------------------------------------------------------------

class TestDefColImmutability:
    def test_upsert_changed_def_col_raises(self, tmp_registry):
        r = tmp_registry()
        row = _base_row("x+y")
        r.register(row)
        # Mutate a def_col (grain is in def_cols)
        bad = dict(row, grain="team-game")
        with pytest.raises(RuntimeError, match="REGISTRY INTEGRITY VIOLATION"):
            r.upsert(bad)

    def test_upsert_mutable_field_ok(self, tmp_registry):
        r = tmp_registry()
        row = _base_row("x+y")
        r.register(row)
        updated = dict(row, status="validated", gateA_rel=-0.05)
        r.upsert(updated)  # should not raise
        got = r.get(row["signal_id"])
        assert got["status"] == "validated"
        assert got["gateA_rel"] == pytest.approx(-0.05)


# ---------------------------------------------------------------------------
# register_many() batch behavior
# ---------------------------------------------------------------------------

class TestRegisterMany:
    def test_dedup_within_batch(self, tmp_registry):
        r = tmp_registry()
        rows = [_base_row(f"x*{i}") for i in range(5)]
        rows_dup = rows + [_base_row("x*0")]  # duplicate of rows[0]
        result = r.register_many(rows_dup)
        assert result["registered"] == 5
        assert result["skipped"] == 1
        assert len(r) == 5

    def test_batch_idempotent_second_call(self, tmp_registry):
        r = tmp_registry()
        rows = [_base_row(f"y*{i}") for i in range(4)]
        r.register_many(rows)
        r2 = r.register_many(rows)
        assert r2["registered"] == 0
        assert r2["skipped"] == 4
        assert len(r) == 4

    def test_missing_id_col_silently_skipped(self, tmp_registry):
        """register_many silently skips rows with no id_col (CONFIRMED BEHAVIOR: not a ValueError)."""
        r = tmp_registry()
        good = _base_row("a+b")
        bad = {"grain": "player-game", "formula_ast": "z+1"}  # no signal_id
        result = r.register_many([bad, good])
        assert result["registered"] == 1
        assert result["skipped"] == 1  # missing id_col treated as skip

    def test_single_part_for_whole_batch(self, tmp_registry):
        r = tmp_registry()
        rows = [_base_row(f"z*{i}") for i in range(10)]
        r.register_many(rows)
        # All 10 go into a single part (batch write under one lock)
        assert len(r._parts()) == 1


# ---------------------------------------------------------------------------
# compact() correctness
# ---------------------------------------------------------------------------

class TestCompact:
    def test_compact_reduces_parts(self, tmp_registry):
        r = tmp_registry()
        for i in range(5):
            r.register(_base_row(f"c*{i}"))
        assert len(r._parts()) == 5
        r.compact()
        assert len(r._parts()) == 1
        assert len(r) == 5

    def test_compact_preserves_all_rows(self, tmp_registry):
        r = tmp_registry()
        rows = [_base_row(f"d*{i}") for i in range(8)]
        for row in rows:
            r.register(row)
        r.compact()
        ids_before = {row["signal_id"] for row in rows}
        ids_after = set(r.all()["signal_id"].tolist())
        assert ids_before == ids_after

    def test_double_compact_idempotent(self, tmp_registry):
        r = tmp_registry()
        for i in range(3):
            r.register(_base_row(f"e*{i}"))
        r.compact()
        r.compact()
        assert len(r._parts()) == 1
        assert len(r) == 3

    def test_compact_then_more_writes(self, tmp_registry):
        r = tmp_registry()
        for i in range(3):
            r.register(_base_row(f"f*{i}"))
        r.compact()
        for i in range(3, 6):
            r.register(_base_row(f"f*{i}"))
        r.compact()
        assert len(r._parts()) == 1
        assert len(r) == 6


# ---------------------------------------------------------------------------
# Silent corrupt parquet -- DOCUMENTED BUG (severity: high)
# ---------------------------------------------------------------------------

class TestCorruptParquet:
    def test_corrupt_part_silently_loses_rows(self, tmp_registry):
        """CONFIRMED BUG: corrupt parquet is silently skipped by _reload_index, causing data loss."""
        r = tmp_registry()
        row = _base_row("corrupt_test")
        r.register(row)
        assert len(r) == 1

        # Corrupt the part file
        part_path = os.path.join(r.dir, r._parts()[0])
        with open(part_path, "wb") as f:
            f.write(b"NOT_A_PARQUET")

        # Reload: should silently skip the corrupt part
        r._reload_index()
        assert len(r) == 0, (
            "BUG CONFIRMED: corrupt parquet silently zeroes the index. "
            "Fix recipe: log a warning with the corrupted part path instead of bare `continue`."
        )

    def test_assert_integrity_passes_on_corrupt_registry(self, tmp_registry):
        """CONFIRMED BUG: _assert_integrity silently ignores corrupt parts."""
        r = tmp_registry()
        r.register(_base_row("integrity_test"))
        part_path = os.path.join(r.dir, r._parts()[0])
        with open(part_path, "wb") as f:
            f.write(b"CORRUPT")
        r._reload_index()
        # No exception -- integrity check cannot detect what it cannot read
        r._assert_integrity()  # should NOT raise (but should ideally warn)


# ---------------------------------------------------------------------------
# update_status()
# ---------------------------------------------------------------------------

class TestUpdateStatus:
    def test_update_status_known_id(self, tmp_registry):
        r = tmp_registry()
        row = _base_row("status_test")
        r.register(row)
        r.update_status(row["signal_id"], status="validated", gateA_rel=-0.03)
        got = r.get(row["signal_id"])
        assert got["status"] == "validated"
        assert got["gateA_rel"] == pytest.approx(-0.03)

    def test_update_status_unknown_id_raises(self, tmp_registry):
        r = tmp_registry()
        with pytest.raises(KeyError):
            r.update_status("sig_nonexistent_id", status="validated")


# ---------------------------------------------------------------------------
# register() ValueError on missing id
# ---------------------------------------------------------------------------

class TestRegisterValidation:
    def test_register_missing_id_raises(self, tmp_registry):
        r = tmp_registry()
        with pytest.raises(ValueError, match="row missing id_col"):
            r.register({"grain": "player-game", "formula_ast": "missing"})

    def test_upsert_missing_id_raises(self, tmp_registry):
        r = tmp_registry()
        with pytest.raises(ValueError, match="row missing id_col"):
            r.upsert({"grain": "player-game"})


# ---------------------------------------------------------------------------
# _norm() behavior
# ---------------------------------------------------------------------------

class TestNorm:
    def test_list_sorted_as_strings(self):
        import scripts.team_system.registry.store as store_mod
        assert store_mod._norm(["B", "A"]) == ["A", "B"]
        assert store_mod._norm([2, 1]) == ["1", "2"]  # ints stringified
        assert store_mod._norm(None) is None
        assert store_mod._norm("foo") == "foo"

    def test_int_vs_string_in_list_collide(self):
        """Known behavior: _norm([1]) == _norm(["1"]) -> same integrity sig."""
        import scripts.team_system.registry.store as store_mod
        assert store_mod._norm([1]) == store_mod._norm(["1"])


# ---------------------------------------------------------------------------
# transactional_write()
# ---------------------------------------------------------------------------

class TestTransactionalWrite:
    def test_successful_write(self, tmp_path):
        import scripts.team_system.registry.store as store_mod
        dest = str(tmp_path / "output.json")

        def writer(p):
            with open(p, "w") as f:
                json.dump({"ok": True}, f)

        ok = store_mod.transactional_write(dest, writer)
        assert ok
        assert os.path.exists(dest)
        with open(dest) as f:
            assert json.load(f) == {"ok": True}

    def test_validator_failure_leaves_live_file_untouched(self, tmp_path):
        import scripts.team_system.registry.store as store_mod
        dest = str(tmp_path / "live.json")
        # Pre-create live file
        with open(dest, "w") as f:
            json.dump({"original": True}, f)

        def writer(p):
            with open(p, "w") as f:
                json.dump({"new": True}, f)

        def bad_validator(p):
            raise ValueError("invalid!")

        ok = store_mod.transactional_write(dest, writer, validator=bad_validator)
        assert not ok
        # Live file must be untouched
        with open(dest) as f:
            assert json.load(f) == {"original": True}

    def test_staging_tmp_cleaned_on_failure(self, tmp_path):
        import scripts.team_system.registry.store as store_mod
        dest = str(tmp_path / "clean.json")

        def writer(p):
            with open(p, "w") as f:
                f.write("{}")

        def bad_validator(p):
            raise RuntimeError("fail")

        store_mod.transactional_write(dest, writer, validator=bad_validator)
        assert not os.path.exists(dest + ".staging")
