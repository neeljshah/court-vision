"""Construct checks for the closed foundry hypothesis grammar."""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.foundry.grammar import Hypothesis, canonical_payload, enumerate_family, semantic_hash


ROOT = Path(__file__).resolve().parents[3]
CONDITIONINGS = (
    frozenset(("phase=period", "rest=NORMAL", "month=2026-09", "confidence=T2")),
    frozenset(("phase=quarter", "rest=RESTED", "month=2026-10", "confidence=T3")),
)


def test_permuted_conditioning_and_unused_params_are_identical() -> None:
    left = Hypothesis("nba", "pace_diff_asof", "raw", (("ignored", "left"),), CONDITIONINGS[0], "pregame", "ml")
    right = Hypothesis("nba", "pace_diff_asof", "raw", (("another", "right"),), frozenset(reversed(tuple(CONDITIONINGS[0]))), "pregame", "ml")
    assert semantic_hash(left) == semantic_hash(right)


def test_one_grid_step_apart_is_different() -> None:
    first = Hypothesis("nba", "pace_diff_asof", "ew", (("halflife", 3),), CONDITIONINGS[0], "pregame", "ml")
    second = Hypothesis("nba", "pace_diff_asof", "ew", (("halflife", 5),), CONDITIONINGS[0], "pregame", "ml")
    assert semantic_hash(first) != semantic_hash(second)


def test_catalogues_enumerate_over_one_thousand_distinct_hashes_without_collisions() -> None:
    paths = [
        *sorted((ROOT / "data/cache/combo").glob("gate_corpus_*.parquet")),
        *sorted((ROOT / "data/domains/basketball_nba").glob("*.parquet")),
        *sorted((ROOT / "data/domains/mlb").glob("*.parquet")),
        *sorted((ROOT / "data/domains/soccer").glob("*.parquet")),
        *sorted((ROOT / "data/domains/tennis").glob("*.parquet")),
        *sorted((ROOT / "data/cache/pit").glob("opp_allowed_asof_*.parquet")),
        *sorted((ROOT / "data/cache/ingame").glob("*states*.parquet")),
    ]
    all_rows = []
    for path in paths:
        lowered = path.as_posix().lower()
        sport = "nba" if "basketball_nba" in lowered or "/pit/" in lowered or "pbp_" in path.name or "possession_" in path.name else (
            "mlb" if "mlb" in lowered else "soccer" if "soccer" in lowered else "tennis")
        import pandas as pd
        columns = list(pd.read_parquet(path).columns)
        spec = {"sport": sport, "parquet": path, "transforms": ("raw", "ew", "rank_in_league", "z_vs_league", "delta_vs_prior", "ratio_to_opponent"),
                "conditionings": CONDITIONINGS, "horizons": ("pregame", "period", "live_tick"),
                "markets": ("ml", "total", "spread", "prop", "inplay"), "family": "s11_construct",
                "runtime_available": {column: False for column in columns}}
        all_rows.extend(enumerate_family(spec))
    by_hash = {}
    for row in all_rows:
        by_hash.setdefault(semantic_hash(row), set()).add(repr(canonical_payload(row)))
    assert len(by_hash) >= 1_000
    assert not [payloads for payloads in by_hash.values() if len(payloads) != 1]
