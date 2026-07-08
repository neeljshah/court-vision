"""Leak guard for the checkpoint extractor: a checkpoint feature must depend
ONLY on events at elapsed <= t. Post-checkpoint events (that flip the score)
must NOT change any checkpoint state -- this is the by-construction defence
against the retracted endQ3 Q4-leak."""
from scripts.platformkit.ingame_compose.checkpoints import (
    CHECKPOINTS,
    _before,
    _timed_actions,
    extract_checkpoints,
)


def _act(an, period, clock, sh, sa, at="x"):
    return {"actionNumber": an, "period": period, "clock": clock,
            "scoreHome": str(sh), "scoreAway": str(sa), "actionType": at}


def _base_game():
    # reaches past q4_6min (elapsed 2620) so all four checkpoints are present.
    return {"game": {"actions": [
        _act(1, 1, "PT12M00.00S", 0, 0),      # elapsed 0
        _act(2, 1, "PT00M00.00S", 20, 18),    # elapsed 720   endQ1  -> +2
        _act(3, 2, "PT00M00.00S", 45, 44),    # elapsed 1440  half   -> +1
        _act(4, 3, "PT00M00.00S", 70, 72),    # elapsed 2160  endQ3  -> -2
        _act(5, 4, "PT06M00.00S", 88, 85),    # elapsed 2520  q4_6min-> +3
        _act(6, 4, "PT05M00.00S", 90, 85),    # elapsed 2620  (ensures reached)
    ]}}


def test_future_events_never_change_a_checkpoint():
    """Append huge score-flipping events AFTER the last checkpoint; every
    checkpoint state must be byte-identical to the un-appended game."""
    base = _base_game()
    leaked = _base_game()
    leaked["game"]["actions"] += [
        _act(7, 4, "PT02M00.00S", 130, 90),   # elapsed 2820, flips lead
        _act(8, 4, "PT00M00.00S", 131, 150),  # elapsed 2880, flips the other way
    ]
    assert extract_checkpoints(base) == extract_checkpoints(leaked)


def test_state_at_t_ignores_all_elapsed_gt_t():
    """Directly: state_at(t) over the full stream equals state_at(t) over only
    the <=t prefix, for every checkpoint -- proves zero future dependence."""
    timed = _timed_actions(_base_game()["game"]["actions"])
    for _cid, t, _trf in CHECKPOINTS:
        prefix = [a for a in timed if a[0] <= t]
        assert _before(timed, t) == _before(prefix, t)


def test_expected_values_and_boundary_inclusive():
    st = extract_checkpoints(_base_game())
    assert st["endQ1"].score_diff == 2.0 and st["endQ1"].event_count == 2
    assert st["half"].score_diff == 1.0
    assert st["endQ3"].score_diff == -2.0
    assert st["q4_6min"].score_diff == 3.0   # PT06M00 is elapsed 2520, inclusive


def test_missing_checkpoint_returns_none():
    """A game that stops in Q2 has no Q3/Q4 checkpoints -> None (never imputed)."""
    short = {"game": {"actions": [
        _act(1, 1, "PT12M00.00S", 0, 0),
        _act(2, 1, "PT00M00.00S", 20, 18),
        _act(3, 2, "PT06M00.00S", 33, 30),   # elapsed 1080, before halftime
    ]}}
    st = extract_checkpoints(short)
    assert st["endQ1"] is not None
    assert st["half"] is None and st["endQ3"] is None and st["q4_6min"] is None


if __name__ == "__main__":
    test_future_events_never_change_a_checkpoint()
    test_state_at_t_ignores_all_elapsed_gt_t()
    test_expected_values_and_boundary_inclusive()
    test_missing_checkpoint_returns_none()
    print("checkpoints leak-guard tests PASS")
