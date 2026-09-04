"""Single exhaustive construct test for S295 strict redaction isolation."""
from __future__ import annotations

from scripts.platformkit.s295_strict_redaction_wrapper import _verify_prereg, run_construct


def test_s295_six_attacks_and_valid_replay() -> None:
    """Check the sealed prereg, all six attacks, and every valid per-tick replay."""
    _verify_prereg()  # Reads the prereg file and normalizes CRLF to LF; never reads git.
    result = run_construct()
    assert result["before_condition"]["strict_redaction_default"] is False
    assert result["before_condition"]["callback_readable"] is True
    assert result["before_condition"]["oracle_brier"] < result["before_condition"]["declared_brier"]
    assert len(result["attacks"]) == 6
    assert {(item["mode"], item["form"]) for item in result["attacks"]} == {
        (mode, form) for mode in ("walk_forward", "cpcv_evaluate")
        for form in ("closure", "module_global", "default_argument")
    }
    assert all(item["rejected"] and item["exception_type"] == "TypeError" for item in result["attacks"])
    assert result["detection"]["successes"] == result["detection"]["total"] == 6
    assert len(result["replays"]) == 2
    for replay in result["replays"]:
        assert replay["replay_error"] <= 1e-12
        records = replay["isolated_records"]
        assert len(records) == 8
        assert len({record["stable_tick_key"] for record in records}) == len(records)
        assert all("loss" in record for record in records)
        assert len({record["game_id"] for record in records}) == 4  # two scored ticks per game
