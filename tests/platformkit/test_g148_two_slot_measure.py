from scripts.platformkit.g148_two_slot_measure import evenly_spaced


def test_evenly_spaced_uses_full_decision_range_without_repeats() -> None:
    assert evenly_spaced(list(range(11)), 5) == [0, 2, 5, 8, 10]
    assert evenly_spaced([1, 2], 5) == [1, 2]
