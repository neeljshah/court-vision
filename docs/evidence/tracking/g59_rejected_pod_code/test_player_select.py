"""Tests for the tennis court-prior player selector."""
from __future__ import annotations

import numpy as np

from domains.tennis.tracking.player_select import PlayerCandidate, PlayerSelector


def _candidate(center: tuple[float, float], foot: tuple[float, float],
               confidence: float = 0.6) -> PlayerCandidate:
    return PlayerCandidate(np.asarray(center, dtype=float), np.asarray(foot, dtype=float), confidence)


def test_selects_two_on_court_players_and_keeps_courtside_people_separate() -> None:
    selector = PlayerSelector()
    near = _candidate((300, 620), (18, 8))
    far = _candidate((740, 300), (61, 28))
    umpire = _candidate((1510, 310), (65, 49), 0.9)
    staff = _candidate((1660, 420), (46, 50), 0.9)
    ball_kid = _candidate((1420, 350), (34, 41), 0.8)

    selected = selector.select([near, far, umpire, staff, ball_kid])

    assert selected[0] is near
    assert selected[1] is far
    assert [id(candidate) for candidate in selector.last_non_players] == [id(umpire), id(staff), id(ball_kid)]


def test_persistence_prefers_the_previous_on_court_player() -> None:
    selector = PlayerSelector()
    near = _candidate((300, 620), (18, 8))
    far = _candidate((740, 300), (61, 28))
    selector.select([near, far])
    continuing_near = _candidate((315, 618), (19, 8), 0.4)
    other_near = _candidate((510, 560), (25, 10), 0.95)
    continuing_far = _candidate((746, 302), (60, 28))

    selected = selector.select([continuing_near, other_near, continuing_far])

    assert selected[0] is continuing_near
    assert selected[1] is continuing_far


def test_missing_half_never_falls_back_to_an_off_court_person() -> None:
    selector = PlayerSelector()
    near = _candidate((300, 620), (18, 8))
    umpire = _candidate((1510, 310), (65, 49), 0.9)
    staff = _candidate((1660, 420), (46, 50), 0.9)
    ball_kid = _candidate((1420, 350), (34, 41), 0.8)

    selected = selector.select([near, umpire, staff, ball_kid])

    assert list(selected) == [0]
    assert selected[0] is near
    assert [id(candidate) for candidate in selector.last_non_players] == [id(umpire), id(staff), id(ball_kid)]
