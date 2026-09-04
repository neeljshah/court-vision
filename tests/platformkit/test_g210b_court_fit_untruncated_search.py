"""Focused contracts for the G210b full-set measurement harness."""

import inspect

from scripts.platformkit.tracking.g210b_court_fit_untruncated_search import _space, fit_image, oracle_fit


def test_full_configuration_accounting_and_label_boundary_are_explicit():
    assert _space(24) == 9_180_864
    assert _space(82) > _space(24)
    assert list(inspect.signature(fit_image).parameters) == ["image", "sport"]
    assert "targets" in inspect.signature(oracle_fit).parameters
