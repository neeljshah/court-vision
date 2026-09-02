"""Per-file test for the S65 StatsBomb event-grain feasibility census.

Real corpora, no mocks for the census itself; small synthetic frames for the two
join properties that a real-data assertion could not isolate.

    python -m pytest scripts/platformkit/test_soccer_event_asof.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit import soccer_event_asof as sea


def _spine(rows):
    frame = pd.DataFrame(rows, columns=["event_id", "corpus_unit", "event_date",
                                        "home_slug", "away_slug"])
    frame["event_date"] = pd.to_datetime(frame["event_date"])
    return frame


def _meta(rows):
    frame = pd.DataFrame(rows, columns=["match_id", "corpus_unit", "match_date",
                                        "home_team", "away_team", "competition"])
    frame["match_date"] = pd.to_datetime(frame["match_date"])
    return frame


def test_crosswalk_maps_fuzzy_and_manual_and_reports_the_rest():
    """A manual name beats the fuzzy near-collision; an unknown club is REPORTED."""
    spine = _spine([("20240101-D1-hertha-union_berlin", "D1", "2024-01-01",
                     "hertha", "union_berlin"),
                    ("20240102-D1-leverkusen-m_gladbach", "D1", "2024-01-02",
                     "leverkusen", "m_gladbach")])
    meta = _meta([(1, "D1", "2024-01-01", "Hertha Berlin", "Union Berlin", "x"),
                  (2, "D1", "2024-01-02", "Bayer Leverkusen",
                   "Borussia Monchengladbach", "x"),
                  (3, "D1", "2024-01-03", "Some Unknown SV", "Union Berlin", "x")])
    crosswalk, unmapped = sea.build_crosswalk(spine, meta)
    # Hertha Berlin fuzzy-matches union_berlin above hertha -- MANUAL_TEAMS wins.
    assert crosswalk[("D1", "Hertha Berlin")] == "hertha"
    assert crosswalk[("D1", "Borussia Monchengladbach")] == "m_gladbach"
    assert crosswalk[("D1", "Bayer Leverkusen")] == "leverkusen"  # fuzzy path
    assert unmapped == [("D1", "Some Unknown SV")]


def test_overlap_is_date_exact_and_orientation_preserving():
    """A one-day slip or a swapped pair must NOT manufacture overlap."""
    spine = _spine([("20240101-E0-arsenal-chelsea", "E0", "2024-01-01",
                     "arsenal", "chelsea")])
    crosswalk = {("E0", "Arsenal"): "arsenal", ("E0", "Chelsea"): "chelsea"}
    exact = _meta([(1, "E0", "2024-01-01", "Arsenal", "Chelsea", "x")])
    off_by_one = _meta([(2, "E0", "2024-01-02", "Arsenal", "Chelsea", "x")])
    swapped = _meta([(3, "E0", "2024-01-01", "Chelsea", "Arsenal", "x")])
    assert len(sea.overlap(spine, exact, crosswalk)) == 1
    assert len(sea.overlap(spine, off_by_one, crosswalk)) == 0
    assert len(sea.overlap(spine, swapped, crosswalk)) == 0


def test_coverage_bar_is_unmoved_at_the_declared_value():
    """B10 / Q3: the verdict is only honest while the bar it misses is 0.25."""
    from scripts.platformkit.analytics_showcase.mechanism_close_effect import MIN_COVERAGE
    assert MIN_COVERAGE == 0.25


def test_census_reproduces_the_S65_denominators_on_real_data():
    """The whole CLOSED AT LIMIT verdict is these six numbers."""
    result = sea.census()
    assert result["n_spine_rows"] == 25834
    assert result["n_scored_rows"] == 16322
    assert result["n_statsbomb_in_league_in_window"] == 1815
    assert result["n_unmapped_team_names"] == 0
    assert result["n_overlap_spine"] == 1740
    assert result["n_overlap_scored"] == 160
    # Independent of the name crosswalk: StatsBomb's own scoreline reproduces the
    # spine's over-2.5 label on every joined row. A mispaired club breaks this.
    assert result["join_label_agreement"] == 1.0
    assert result["n_overlap_spine_distinct_event_ids"] == 1740
    assert result["n_overlap_spine_distinct_match_ids"] == 1740
    assert result["coverage_ceiling_scored"] < result["min_coverage_bar"]
    assert result["verdict"] == "CLOSED AT LIMIT"
    assert result["bar_moved"] is False


def test_the_eleven_mechanisms_are_enumerated_with_their_absent_ingredient():
    """n = 11 (CONSTRUCT): the enumeration is the S53 list, exhaustively."""
    assert len(sea.EVENT_GRAIN_INGREDIENTS) == 11
    assert all(isinstance(v, str) and v for v in sea.EVENT_GRAIN_INGREDIENTS.values())
