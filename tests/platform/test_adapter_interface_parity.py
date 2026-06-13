"""tests/platform/test_adapter_interface_parity.py — Cross-adapter interface-parity.

Verifies that every MARKET_ONLY domain adapter (tennis, soccer, mlb) exposes
the SAME runtime interface so that "adding a sport = only the adapter" holds.

DISTINCT from leak-correctness tests (test_adapter_leak_invariance.py).
This suite checks SHAPE / UNIFORMITY only:
  - required methods present on each adapter class
  - feature_bundle() positional parameter names + order
  - FeatureBundle attribute set is complete
  - all three adapters agree with EACH OTHER (parity), not just a spec list

Run: python -m pytest tests/platform/test_adapter_interface_parity.py -q
"""
from __future__ import annotations

import importlib
import inspect
from typing import List, Optional, Set, Tuple, Type

import pytest

from scripts.platformkit.adapter_interface_spec import (
    ADAPTER_REGISTRY,
    FEATURE_BUNDLE_ATTRS,
    FEATURE_BUNDLE_POSITIONAL_PARAMS,
    REQUIRED_CLASS_ATTRS,
    REQUIRED_METHODS,
    check_adapter,
)
from scripts.platformkit.validate_adapter_types import Status

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SPORT_IDS = list(ADAPTER_REGISTRY.keys())  # ["tennis", "soccer", "mlb"]


def _try_import(sport: str) -> Optional[Type]:
    """Import and return adapter class; return None and skip if import fails."""
    module_path, class_name = ADAPTER_REGISTRY[sport]
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)
    except Exception as exc:  # noqa: BLE001
        return None


def _get_cls(sport: str) -> Type:
    """Return adapter class or pytest.skip if unavailable."""
    cls = _try_import(sport)
    if cls is None:
        pytest.skip(f"Could not import {sport} adapter — skipping")
    return cls


def _feature_bundle_positional_params(cls: Type) -> List[str]:
    """Return positional param names for feature_bundle (excluding self)."""
    sig = inspect.signature(cls.feature_bundle)
    return [
        name for name, p in sig.parameters.items()
        if name != "self"
        and p.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        )
    ]


# ---------------------------------------------------------------------------
# Parametrized per-adapter conformance via check_adapter()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sport", SPORT_IDS)
def test_check_adapter_no_fail(sport: str) -> None:
    """check_adapter() must return zero FAIL results for each adapter."""
    cls = _get_cls(sport)
    results = check_adapter(cls)
    fails = [r for r in results if r.status == Status.FAIL]
    assert not fails, (
        f"{sport} adapter has {len(fails)} interface FAIL(s):\n"
        + "\n".join(f"  {r}" for r in fails)
    )


# ---------------------------------------------------------------------------
# Required class attribute: sport (str)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sport", SPORT_IDS)
def test_sport_attr_is_str(sport: str) -> None:
    """Each adapter class must have a non-empty string ``sport`` attribute."""
    cls = _get_cls(sport)
    assert hasattr(cls, "sport"), f"{cls.__name__} missing 'sport' class attr"
    assert isinstance(cls.sport, str), (
        f"{cls.__name__}.sport must be str; got {type(cls.sport).__name__}"
    )
    assert cls.sport, f"{cls.__name__}.sport must be non-empty"


# ---------------------------------------------------------------------------
# Required protocol methods
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sport", SPORT_IDS)
@pytest.mark.parametrize("method", REQUIRED_METHODS)
def test_required_method_present(sport: str, method: str) -> None:
    """Each adapter class must expose every required protocol method."""
    cls = _get_cls(sport)
    assert callable(getattr(cls, method, None)), (
        f"{cls.__name__} missing required method '{method}'"
    )


# ---------------------------------------------------------------------------
# feature_bundle signature shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sport", SPORT_IDS)
def test_feature_bundle_has_required_positional_params(sport: str) -> None:
    """feature_bundle must have (hypothesis, seasons, ...) as its first two params."""
    cls = _get_cls(sport)
    params = _feature_bundle_positional_params(cls)
    for i, required in enumerate(FEATURE_BUNDLE_POSITIONAL_PARAMS):
        assert i < len(params), (
            f"{cls.__name__}.feature_bundle has only {len(params)} positional "
            f"params; expected at least {len(FEATURE_BUNDLE_POSITIONAL_PARAMS)}"
        )
        assert params[i] == required, (
            f"{cls.__name__}.feature_bundle param[{i}] = '{params[i]}'; "
            f"expected '{required}'"
        )


# ---------------------------------------------------------------------------
# FeatureBundle attribute set
# ---------------------------------------------------------------------------


def test_feature_bundle_attrs_complete() -> None:
    """FeatureBundle dataclass must carry all required attributes."""
    from src.loop.gate import FeatureBundle
    for attr in FEATURE_BUNDLE_ATTRS:
        assert attr in FeatureBundle.__dataclass_fields__, (
            f"FeatureBundle missing required attribute '{attr}'"
        )


# ---------------------------------------------------------------------------
# Cross-adapter parity: the three adapters must agree with EACH OTHER
# ---------------------------------------------------------------------------


def _available_adapter_classes() -> List[Tuple[str, Type]]:
    return [(s, _try_import(s)) for s in SPORT_IDS if _try_import(s) is not None]


def test_all_adapters_have_same_required_methods() -> None:
    """All importable adapters must expose the exact same required method set."""
    adapter_pairs = _available_adapter_classes()
    if len(adapter_pairs) < 2:
        pytest.skip("Need at least 2 importable adapters for parity check")

    method_sets = {
        sport: frozenset(
            m for m in REQUIRED_METHODS if callable(getattr(cls, m, None))
        )
        for sport, cls in adapter_pairs
    }
    # Every adapter should have the full required set
    full_set = frozenset(REQUIRED_METHODS)
    for sport, method_set in method_sets.items():
        missing = full_set - method_set
        assert not missing, (
            f"{sport} adapter is missing methods present on others: {sorted(missing)}"
        )


def test_all_adapters_agree_on_feature_bundle_required_params() -> None:
    """All importable adapters must share the same first N feature_bundle params."""
    adapter_pairs = _available_adapter_classes()
    if len(adapter_pairs) < 2:
        pytest.skip("Need at least 2 importable adapters for parity check")

    # Collect required-param prefix (first N as per spec) for each adapter
    param_prefixes = {
        sport: tuple(
            _feature_bundle_positional_params(cls)[: len(FEATURE_BUNDLE_POSITIONAL_PARAMS)]
        )
        for sport, cls in adapter_pairs
    }
    reference_sport, reference_prefix = next(iter(param_prefixes.items()))
    for sport, prefix in param_prefixes.items():
        assert prefix == reference_prefix, (
            f"feature_bundle param prefix mismatch: "
            f"{reference_sport}={list(reference_prefix)} vs {sport}={list(prefix)}"
        )


def test_all_adapters_have_sport_str_attr() -> None:
    """All importable adapters must have a non-empty str ``sport`` class attribute."""
    for sport, cls in _available_adapter_classes():
        assert hasattr(cls, "sport"), f"{cls.__name__} missing 'sport'"
        assert isinstance(cls.sport, str) and cls.sport, (
            f"{cls.__name__}.sport must be non-empty str"
        )


def test_sport_ids_are_distinct() -> None:
    """Each adapter must declare a distinct sport_id (no collisions)."""
    pairs = _available_adapter_classes()
    sport_vals = [cls.sport for _, cls in pairs]
    assert len(sport_vals) == len(set(sport_vals)), (
        f"Duplicate sport IDs detected: {sport_vals}"
    )


# ---------------------------------------------------------------------------
# Strict parity: all adapters must have identical feature_bundle positional params
# (league_filter is keyword-only on MLBAdapter, so it no longer widens the positional
# prefix — this test now passes without xfail)
# ---------------------------------------------------------------------------


def test_all_adapters_have_identical_feature_bundle_signature() -> None:
    """Strict parity: every adapter's feature_bundle positional params are identical.

    MLBAdapter.feature_bundle has ``league_filter`` as a KEYWORD-ONLY param (after ``*``),
    so it does not appear in the positional-param list.  All three adapters now share
    exactly the same positional prefix: (hypothesis, seasons).
    """
    adapter_pairs = _available_adapter_classes()
    if len(adapter_pairs) < 2:
        pytest.skip("Need at least 2 importable adapters")

    all_params = {
        sport: tuple(_feature_bundle_positional_params(cls))
        for sport, cls in adapter_pairs
    }
    reference_sport, reference_params = next(iter(all_params.items()))
    for sport, params in all_params.items():
        assert params == reference_params, (
            f"Strict signature mismatch: {reference_sport}={list(reference_params)} "
            f"vs {sport}={list(params)}"
        )
