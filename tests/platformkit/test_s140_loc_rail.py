"""S140 construct checks: extracted names remain available from their original modules."""
from __future__ import annotations

import importlib
from pathlib import Path


def _assert_reexport(original: str, sibling: str, names: tuple[str, ...]) -> None:
    source = importlib.import_module(original)
    extracted = importlib.import_module(sibling)
    assert len(Path(source.__file__).read_text(encoding="utf-8").splitlines()) <= 300
    for name in names:
        assert getattr(source, name) is getattr(extracted, name)


def test_results_db_sql_reexports_and_loc_rail():
    _assert_reexport("scripts.platformkit.foundry.results_db",
                     "scripts.platformkit.foundry.results_db_sql",
                     ("TierResult", "_SCHEMA", "recompute_deflated_p"))


def test_corpus_cache_sources_reexports_and_loc_rail():
    _assert_reexport("scripts.platformkit.combo.corpus_cache",
                     "scripts.platformkit.combo.corpus_cache_sources",
                     ("_build_mlb", "_build_nba", "_build_soccer", "_build_tennis"))


def test_screen_predictor_supply_reexports_and_loc_rail():
    _assert_reexport("scripts.platformkit.foundry.screen_predictor",
                     "scripts.platformkit.foundry.screen_predictor_supply",
                     ("_table", "_families_of", "source_column"))
