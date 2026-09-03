"""Shared fixtures for foundry tests."""
from __future__ import annotations

import pytest

from scripts.platformkit.foundry.results_db import ResultsDB


@pytest.fixture
def results_db(tmp_path):
    """Provide a fresh results database isolated under pytest's tmp_path."""
    return ResultsDB(tmp_path / "hypotheses.sqlite")
