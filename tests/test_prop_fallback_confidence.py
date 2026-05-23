"""PRED-13: Tests for fallback confidence flagging in player_props."""
from pathlib import Path


def test_maybe_flag_fallback_circular_models():
    from src.prediction.player_props import _maybe_flag_fallback

    # circular models flagged when pergame path did not fire
    assert _maybe_flag_fallback(False, "ensemble") == "season_avg_fallback"
    assert _maybe_flag_fallback(False, "model") == "season_avg_fallback"

    # pergame path fired — keep as-is
    assert _maybe_flag_fallback(True, "pergame") == "pergame"

    # low-confidence non-circular values stay unchanged
    assert _maybe_flag_fallback(False, "rolling") == "rolling"
    assert _maybe_flag_fallback(False, "season") == "season"
    assert _maybe_flag_fallback(False, "default") == "default"


def test_prop_stacker_marks_circular_task():
    src = Path("src/prediction/prop_stacker.py").read_text(encoding="utf-8")
    assert '"task": "season_aggregate_circular"' in src


def test_props_lgb_marks_circular_task():
    src = Path("src/prediction/player_props.py").read_text(encoding="utf-8")
    # expects two occurrences: one for props_lgb, one for props_cb
    assert src.count('"task": "season_aggregate_circular"') >= 2
