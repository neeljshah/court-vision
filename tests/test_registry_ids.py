"""
test_registry_ids.py -- adversarial correctness tests for registry/ids.py

Covers:
  - signal_id commutativity (a+b == b+a, a*b*c == c*b*a)
  - signal_id float quantization (0.1000001 == 0.1)
  - signal_id domain_tags order independence
  - signal_id distinctness on different formulas
  - normalize_formula AST canonicalization
  - normalize_formula fallback (case sensitivity confirmed bug)
  - family_key collapse on window-size variants
  - family_key with None/empty domain_tags
  - family_key regex -- [15] and [5] collapse to same family
  - model_id and engine_id stability
  - asof_fn vs asof_fn_name key split (documented spec inconsistency)
"""
from __future__ import annotations

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "team_system"))


@pytest.fixture(autouse=True)
def _add_path():
    path = os.path.join(os.path.dirname(__file__), "..", "scripts", "team_system")
    if path not in sys.path:
        sys.path.insert(0, path)


# ---------------------------------------------------------------------------
# signal_id invariants
# ---------------------------------------------------------------------------

class TestSignalId:
    def _base(self, **kw) -> dict:
        base = dict(grain="possession", entity_scope="team",
                    domain_tags=["transition", "pace"], source="pbp",
                    formula_ast="off_to_share*ppp + 0.1", transform_chain=["rate"],
                    asof_fn_name="asof_team", causal_sign=1)
        base.update(kw)
        return base

    def test_commutativity_addition(self):
        from registry.ids import signal_id
        a = self._base(formula_ast="off_to_share + ppp")
        b = self._base(formula_ast="ppp + off_to_share")
        assert signal_id(a) == signal_id(b)

    def test_commutativity_multiplication(self):
        from registry.ids import signal_id
        a = self._base(formula_ast="a * b * c")
        b = self._base(formula_ast="c * b * a")
        assert signal_id(a) == signal_id(b)

    def test_associativity_flattened(self):
        from registry.ids import signal_id
        a = self._base(formula_ast="a + (b + c)")
        b = self._base(formula_ast="(a + b) + c")
        assert signal_id(a) == signal_id(b)

    def test_float_quantization(self):
        from registry.ids import signal_id
        a = self._base(formula_ast="x * 0.1000001")
        b = self._base(formula_ast="x * 0.1")
        assert signal_id(a) == signal_id(b)

    def test_domain_tags_order_independent(self):
        from registry.ids import signal_id
        a = self._base(domain_tags=["transition", "pace"])
        b = self._base(domain_tags=["pace", "transition"])
        assert signal_id(a) == signal_id(b)

    def test_different_formula_different_id(self):
        from registry.ids import signal_id
        a = self._base(formula_ast="a + b")
        b = self._base(formula_ast="a * b")
        assert signal_id(a) != signal_id(b)

    def test_different_grain_different_id(self):
        from registry.ids import signal_id
        a = self._base()
        b = self._base(grain="player-game")
        assert signal_id(a) != signal_id(b)

    def test_none_formula_empty_string_same(self):
        from registry.ids import signal_id
        a = self._base(formula_ast=None)
        b = self._base(formula_ast="")
        assert signal_id(a) == signal_id(b)


# ---------------------------------------------------------------------------
# normalize_formula
# ---------------------------------------------------------------------------

class TestNormalizeFormula:
    def test_parseable_commutative(self):
        from registry.ids import normalize_formula
        assert normalize_formula("a+b") == normalize_formula("b+a")

    def test_parseable_multiplication_commutative(self):
        from registry.ids import normalize_formula
        assert normalize_formula("x*y*z") == normalize_formula("z*y*x")

    def test_unparseable_lowercased(self):
        from registry.ids import normalize_formula
        # Strings with spaces/special chars that are NOT valid Python -> fallback to lowercased
        r = normalize_formula("My Signal Name (v2)")
        assert r == "my signal name (v2)"
        # Plain identifiers ARE valid Python (parsed as Name node), not lowercased
        r2 = normalize_formula("Custom_Signal_Def")
        assert r2.startswith("Name("), (
            "Single-word identifiers parse as Python Name nodes, not lowercased strings"
        )

    def test_case_sensitivity_bug_confirmed(self):
        """DOCUMENTED BUG: unparseable formulas lower-cased -> false dedup on case variants."""
        from registry.ids import normalize_formula
        # Two semantically DIFFERENT descriptive formulas collapse to the same string
        fa = normalize_formula("Brunson Usage vs. Rank")
        fb = normalize_formula("brunson usage vs. rank")
        # This IS the current behavior (it's a bug but documented)
        assert fa == fb, (
            "BUG: normalize_formula lower-cases unparseable strings, "
            "so capital and lowercase variants hash identically. "
            "Fix: preserve original string case in the fallback path."
        )

    def test_none_returns_empty(self):
        from registry.ids import normalize_formula
        assert normalize_formula(None) == ""
        assert normalize_formula("") == ""
        assert normalize_formula("   ") == ""

    def test_bool_op_sorted(self):
        from registry.ids import normalize_formula
        assert normalize_formula("a and b") == normalize_formula("b and a")


# ---------------------------------------------------------------------------
# family_key
# ---------------------------------------------------------------------------

class TestFamilyKey:
    def _base(self, **kw):
        base = dict(grain="player-game", entity_scope="player",
                    domain_tags=["pace"], source="pbp", transform_chain=["roll_5"])
        base.update(kw)
        return base

    def test_same_family_different_window(self):
        from registry.ids import family_key
        f1 = self._base(transform_chain=["roll_5"])
        f2 = self._base(transform_chain=["roll_10"])
        assert family_key(f1) == family_key(f2)

    def test_different_transform_shape_differs(self):
        from registry.ids import family_key
        f1 = self._base(transform_chain=["roll_5"])
        f2 = self._base(transform_chain=["ewma_5"])
        assert family_key(f1) != family_key(f2)

    def test_none_and_empty_domain_tags_same(self):
        from registry.ids import family_key
        a = self._base(domain_tags=None, transform_chain=None)
        b = self._base(domain_tags=[], transform_chain=[])
        assert family_key(a) == family_key(b)

    def test_window_15_and_5_collapse_to_same_family(self):
        """family_key regex collapses all digit sequences to '#': roll_15 and roll_5 share family."""
        from registry.ids import family_key
        f1 = self._base(transform_chain=["roll_5"])
        f2 = self._base(transform_chain=["roll_15"])
        f3 = self._base(transform_chain=["roll_150"])
        assert family_key(f1) == family_key(f2) == family_key(f3)

    def test_different_grain_different_family(self):
        from registry.ids import family_key
        a = self._base(grain="player-game")
        b = self._base(grain="team-game")
        assert family_key(a) != family_key(b)


# ---------------------------------------------------------------------------
# model_id and engine_id
# ---------------------------------------------------------------------------

class TestModelEngineId:
    def test_model_id_order_independent(self):
        from registry.ids import model_id
        m1 = model_id(dict(domain_tag="d", entity_scope="player",
                           signal_id_set=["sig_aaa", "sig_bbb"], method="hgb"))
        m2 = model_id(dict(domain_tag="d", entity_scope="player",
                           signal_id_set=["sig_bbb", "sig_aaa"], method="hgb"))
        assert m1 == m2

    def test_engine_id_excludes_wiring_fields(self):
        from registry.ids import engine_id
        e1 = engine_id(dict(name="power_ratings", method="nnls",
                            consumes_models=["m1"], owns_nodes=["pts"]))
        e2 = engine_id(dict(name="power_ratings", method="nnls",
                            consumes_models=[], owns_nodes=[]))
        # consumes_models and owns_nodes are NOT identity fields
        assert e1 == e2

    def test_engine_id_name_change_changes_id(self):
        from registry.ids import engine_id
        e1 = engine_id(dict(name="power_ratings", method="nnls"))
        e2 = engine_id(dict(name="four_factors", method="nnls"))
        assert e1 != e2


# ---------------------------------------------------------------------------
# asof_fn vs asof_fn_name split -- documented spec inconsistency
# ---------------------------------------------------------------------------

class TestAsofFieldSplit:
    def test_asof_fn_name_affects_hash(self):
        """Different asof_fn_name -> different signal_id (hash uses asof_fn_name)."""
        from registry.ids import signal_id
        base = dict(grain="player-game", entity_scope="player", domain_tags=["pace"],
                    source="pbp", formula_ast="x+y", transform_chain=["rate"],
                    causal_sign=1)
        a = signal_id(dict(base, asof_fn="shift1", asof_fn_name="shift1"))
        b = signal_id(dict(base, asof_fn="shift1", asof_fn_name="shift_one"))
        assert a != b, (
            "asof_fn_name participates in hash so different names give different ids. "
            "But integrity check uses asof_fn (not asof_fn_name) -- they are decoupled. "
            "Fix recipe: unify def_cols and _SIGNAL_KEYS to use the same field name."
        )

    def test_asof_fn_not_in_signal_keys(self):
        """asof_fn (without _name) is NOT in _SIGNAL_KEYS -- only asof_fn_name is."""
        from registry.ids import _SIGNAL_KEYS
        assert "asof_fn_name" in _SIGNAL_KEYS
        assert "asof_fn" not in _SIGNAL_KEYS

    def test_asof_fn_in_def_cols_not_asof_fn_name(self):
        """SCHEMA def_cols uses asof_fn but _SIGNAL_KEYS uses asof_fn_name."""
        from registry.store import SCHEMAS
        def_cols = SCHEMAS["signal_registry"]["def_cols"]
        assert "asof_fn" in def_cols
        assert "asof_fn_name" not in def_cols
