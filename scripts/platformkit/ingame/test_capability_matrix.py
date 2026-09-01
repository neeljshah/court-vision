"""Per-file tests for capability_matrix.

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_capability_matrix.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import capability_matrix as cm

_EXPECTED_SPORTS = {
    "MLB", "Soccer (domestic, e.g. EPL)", "Soccer (international / World Cup)",
    "NBA", "Tennis", "NFL",
}


def test_every_requested_sport_is_present_exactly_once() -> None:
    sports = [row["sport"] for row in cm.ROWS]
    assert set(sports) == _EXPECTED_SPORTS
    assert len(sports) == len(set(sports))


def test_viability_is_always_a_known_class() -> None:
    for row in cm.ROWS:
        assert row["viability"] in cm.VIABILITY_CLASSES


def test_no_field_is_silently_none() -> None:
    """Every field is either a real value or the literal UNMEASURED sentinel -- never None."""
    for row in cm.ROWS:
        for key, value in row.items():
            assert value is not None, "%s.%s was None instead of UNMEASURED" % (row["sport"], key)
            if isinstance(value, dict):
                assert all(v is not None for v in value.values())


def test_locked_mlb_leadoff_numbers_match_arm_registry() -> None:
    """Regression guard: the cited MLB delta_brier/n_eff must equal arm_registry's own lock."""
    from scripts.platformkit.ingame import arm_registry

    mlb = cm.by_sport("MLB")
    assert str(arm_registry.MEASURED_DELTA_BRIER_LOCK) in mlb["arm_families"][0]
    assert "n_eff=268.0" in mlb["arm_families"][0]
    assert arm_registry.MEASURED_EFFECTIVE_N_LOCK == 268.0


def test_sports_with_zero_captured_ticks_have_no_arm_families() -> None:
    """A sport with literally zero on-disk ticks (soccer domestic, tennis, NFL) cannot
    have measured arm families; NBA is DARK for its live path but still carries a
    real offline calibration corpus, so it is checked separately, not by this rule."""
    for sport in ("Soccer (domestic, e.g. EPL)", "Tennis", "NFL"):
        assert cm.by_sport(sport)["arm_families"] == []


def test_by_sport_returns_empty_dict_for_unknown_sport() -> None:
    assert cm.by_sport("NHL") == {}


def test_render_contains_every_sport_and_gate_constants() -> None:
    text = cm.render()
    for sport in _EXPECTED_SPORTS:
        assert sport in text
    assert "SLOW_STATE_TICK_P90_SEC=120.0" in text


def test_soccer_domestic_is_dark_and_soccer_intl_is_slow_state() -> None:
    assert cm.by_sport("Soccer (domestic, e.g. EPL)")["viability"] == cm.DARK
    assert cm.by_sport("Soccer (international / World Cup)")["viability"] == cm.SLOW_STATE


def test_no_sport_is_ever_classified_event_reactive_today() -> None:
    """Honest-repo invariant: every measured lag artifact found in this audit points the
    venue-ahead-of-us direction; no sport has evidence supporting EVENT_REACTIVE yet."""
    assert all(row["viability"] != cm.EVENT_REACTIVE for row in cm.ROWS)
