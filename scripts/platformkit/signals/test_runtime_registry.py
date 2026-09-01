"""Focused tests for the fail-closed N15 runtime availability registry."""
from __future__ import annotations

import pytest

from scripts.platformkit.signals import runtime_registry
from scripts.platformkit.signals.runtime_registry import (
    MARKET_MICRO,
    PRODUCER_MODULES,
    REGISTRY,
    RUNTIME,
    RuntimeRegistryError,
    SignalRegistration,
    assert_registered_producers_match,
    assert_runtime_safe,
    declared_output_columns,
    registered_columns,
    validate_registry,
)


def test_installed_producers_exactly_match_their_registry_rows():
    discovered = assert_registered_producers_match()
    assert set(discovered) == set(PRODUCER_MODULES)
    for module_name, columns in discovered.items():
        if columns is not None:
            assert columns == registered_columns(module_name)


def test_missing_producer_is_explicitly_reported_as_absent():
    assert declared_output_columns("scripts.platformkit.signals.not_built_yet") is None


def test_present_producer_must_declare_registered_columns(monkeypatch):
    class Producer:
        OUTPUT_COLUMNS = ("price_drift_T6_to_T1", "cross_book_dispersion")

    monkeypatch.setattr(runtime_registry, "import_module", lambda _: Producer)
    assert declared_output_columns(MARKET_MICRO) == frozenset(Producer.OUTPUT_COLUMNS)
    assert registered_columns(MARKET_MICRO) != frozenset(Producer.OUTPUT_COLUMNS)


def test_runtime_columns_declaration_is_supported(monkeypatch):
    class Producer:
        RUNTIME_COLUMNS = ("venue_id",)

    monkeypatch.setattr(runtime_registry, "import_module", lambda _: Producer)
    assert declared_output_columns("example") == frozenset(Producer.RUNTIME_COLUMNS)


def test_runtime_guard_rejects_unregistered_and_train_columns():
    assert_runtime_safe(["rest_differential"])
    with pytest.raises(RuntimeRegistryError, match="unregistered"):
        assert_runtime_safe(["not_registered"])
    with pytest.raises(RuntimeRegistryError, match="non-runtime"):
        assert_runtime_safe(["crew_foul_rate_prior"])


@pytest.mark.parametrize("registry", ({}, None))
def test_empty_or_missing_registry_fails_closed(monkeypatch, registry):
    monkeypatch.setattr(runtime_registry, "REGISTRY", registry)
    with pytest.raises(RuntimeRegistryError, match="missing or empty"):
        assert_runtime_safe(["rest_differential"])


def test_train_prior_requires_frozen_prior_date():
    row = SignalRegistration(
        tag="TRAIN_PRIOR",
        producing_module="example",
        as_of_rule="frozen before scoring",
        source="example",
        license="internal",
        added_on="2026-08-31",
    )
    with pytest.raises(RuntimeRegistryError, match="lacks frozen prior date"):
        validate_registry({"example_prior": row})


def test_registered_runtime_row_has_required_metadata():
    row = REGISTRY["rest_differential"]
    assert row.tag == RUNTIME
    assert row.producing_module in PRODUCER_MODULES
