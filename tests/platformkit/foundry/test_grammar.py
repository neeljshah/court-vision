"""Construct checks for the closed foundry hypothesis grammar."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.foundry import catalogue
from scripts.platformkit.foundry.grammar import Hypothesis, canonical_payload, enumerate_family, semantic_hash


CONDITIONINGS = (
    frozenset(("phase=1", "rest=NORMAL", "month=2026-09", "confidence=T2")),
    frozenset(("phase=2", "rest=RESTED", "month=2026-10", "confidence=T3")),
)
TRANSFORMS = ("raw", "ew", "rank_in_league", "z_vs_league", "delta_vs_prior", "ratio_to_opponent")


def test_permuted_conditioning_and_unused_params_are_identical() -> None:
    left = Hypothesis("nba", "pace_diff_asof", "raw", (("ignored", "left"),), CONDITIONINGS[0], "pregame", "ml")
    right = Hypothesis("nba", "pace_diff_asof", "raw", (("another", "right"),), frozenset(reversed(tuple(CONDITIONINGS[0]))), "pregame", "ml")
    assert semantic_hash(left) == semantic_hash(right)


def test_one_grid_step_apart_is_different() -> None:
    first = Hypothesis("nba", "pace_diff_asof", "ew", (("halflife", 3),), CONDITIONINGS[0], "pregame", "ml")
    second = Hypothesis("nba", "pace_diff_asof", "ew", (("halflife", 5),), CONDITIONINGS[0], "pregame", "ml")
    assert semantic_hash(first) != semantic_hash(second)


def test_family_and_runtime_available_do_not_move_the_hash() -> None:
    base = Hypothesis("nba", "pace_diff_asof", "raw", (), CONDITIONINGS[0], "pregame", "ml")
    tagged = Hypothesis("nba", "pace_diff_asof", "raw", (), CONDITIONINGS[0], "pregame", "ml", "s46_family", True)
    assert semantic_hash(base) == semantic_hash(tagged)
    assert (base.family, base.runtime_available) == ("", False)


def test_phase_alphabet_is_closed() -> None:
    for bad in ("phase=periods", "phase=Q1", "phase=10"):
        with pytest.raises(ValueError):
            semantic_hash(Hypothesis("nba", "pace_diff_asof", "raw", (), frozenset((bad,)), "pregame", "ml"))


def test_catalogues_enumerate_over_one_thousand_distinct_hashes_without_collisions() -> None:
    all_rows = []
    for entry in catalogue.entries():
        columns = list(pd.read_parquet(entry.path).columns)
        spec = {"sport": entry.sport, "parquet": entry.path, "transforms": TRANSFORMS,
                "conditionings": CONDITIONINGS, "horizons": ("pregame", "period", "live_tick"),
                "markets": ("ml", "total", "spread", "prop", "inplay"), "family": "s11_construct",
                "runtime_available": {column: False for column in columns}}
        all_rows.extend(enumerate_family(spec))
    by_hash: dict[str, set[str]] = {}
    for row in all_rows:
        by_hash.setdefault(semantic_hash(row), set()).add(repr(canonical_payload(row)))
    assert len(by_hash) >= 1_000
    assert not [payloads for payloads in by_hash.values() if len(payloads) != 1]
