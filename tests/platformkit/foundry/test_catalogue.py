"""Construct checks for the shared foundry catalogue-to-sport mapping."""
from __future__ import annotations

import pytest

from scripts.platformkit.foundry import catalogue


# S111 (a) built three of the five the S11 spec named absent (asof_features_wta,
# asof_return_wta, asof_meta_wta); S122 built schedule_density_wta and NAMED its sibling
# travel_scouting_wta (domains/tennis/wta_schedule_travel.py). One soccer table is left.
ABSENT_2026_09_03 = (
    "data/domains/soccer/asof_discipline_features.parquet",
)


def test_absent_named_parquets_are_exactly_the_one_still_unbuilt() -> None:
    measured = tuple(path.relative_to(catalogue.ROOT).as_posix() for path in catalogue.absent())
    assert measured == ABSENT_2026_09_03
    assert len(catalogue.NAMED) == 37


def test_every_present_entry_carries_a_known_sport() -> None:
    rows = catalogue.entries()
    assert len(rows) >= 69  # 27 present named + 4 pit + 38 ingame on 2026-09-03
    assert {row.sport for row in rows} <= catalogue.SPORTS
    assert len({row.path for row in rows}) == len(rows)


@pytest.mark.parametrize(("path", "sport"), [
    ("data/cache/combo/gate_corpus_nba.parquet", "nba"),
    ("data/cache/combo/gate_corpus_tennis.parquet", "tennis"),
    ("data/domains/basketball_nba/asof_team_adv.parquet", "nba"),
    ("data/domains/mlb/asof_inning.parquet", "mlb"),
    ("data/cache/pit/opp_allowed_asof_2023_24.parquet", "nba"),
    ("data/cache/ingame/pbp_states_2024_25.parquet", "nba"),
    ("data/cache/ingame/possession_states_2024_25.parquet", "nba"),
    ("data/cache/ingame/mlb_pitch_states__2024.parquet", "mlb"),
    ("data/cache/ingame/soccer_shotstates__eng1.parquet", "soccer"),
    ("data/cache/ingame/tennis_states__wta.parquet", "tennis"),
])
def test_sport_of_labels_each_catalogue_shape(path: str, sport: str) -> None:
    assert catalogue.sport_of(path) == sport


def test_sport_of_refuses_an_unlabellable_path() -> None:
    with pytest.raises(ValueError):
        catalogue.sport_of("data/cache/ingame/curling_states__x.parquet")
