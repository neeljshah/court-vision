"""
test_foul_trouble_live.py -- Tests for live foul-trouble detection (19.5-01).

Acceptance criterion: when a star records 3 fouls in Q2, the predictor emits
alt-under recommendations for his stats and alt-over for the primary
beneficiary; validated against historical events with CLV>0 on >=60%.
"""

from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.foul_trouble_predictor import (  # noqa: E402
    monitor_foul_trouble,
    validate_foul_trouble_signal,
)


def _player(pid, name, team, fouls, usage, is_star=False) -> dict:
    return {"player_id": pid, "player_name": name, "team": team,
            "fouls": fouls, "usage": usage, "is_star": is_star}


def _box_with_foul_trouble() -> list:
    return [
        _player(1, "Star Forward", "BOS", fouls=3, usage=0.32, is_star=True),
        _player(2, "Sixth Man", "BOS", fouls=1, usage=0.18),
        _player(3, "Role Player", "BOS", fouls=0, usage=0.10),
        _player(4, "Opp Star", "NYK", fouls=1, usage=0.30, is_star=True),
    ]


def test_star_with_3_fouls_in_q2_emits_alt_under():
    """A star at 3 fouls in Q2 triggers an alt-under on his stats."""
    recs = monitor_foul_trouble(_box_with_foul_trouble(), period=2)
    under = [r for r in recs if r["event"] == "FOUL_TROUBLE"]
    assert len(under) == 1
    assert under[0]["player_id"] == 1
    assert under[0]["recommendation"] == "alt_under"
    assert set(under[0]["stats"]) == {"pts", "reb", "ast"}


def test_beneficiary_gets_alt_over():
    """The highest-usage healthy teammate gets an alt-over recommendation."""
    recs = monitor_foul_trouble(_box_with_foul_trouble(), period=2)
    over = [r for r in recs if r["event"] == "FOUL_TROUBLE_BENEFICIARY"]
    assert len(over) == 1
    assert over[0]["player_id"] == 2          # Sixth Man — highest usage teammate
    assert over[0]["recommendation"] == "alt_over"
    assert over[0]["linked_to"] == 1


def test_no_trigger_outside_q2():
    """The same 3-foul box score in Q3 does NOT fire (window is Q2)."""
    assert monitor_foul_trouble(_box_with_foul_trouble(), period=3) == []


def test_no_trigger_below_3_fouls():
    """Two fouls in Q2 is not yet foul trouble."""
    box = [_player(1, "Star", "BOS", fouls=2, usage=0.30, is_star=True),
           _player(2, "Mate", "BOS", fouls=0, usage=0.20)]
    assert monitor_foul_trouble(box, period=2) == []


def test_non_star_in_foul_trouble_ignored():
    """A low-usage bench player in foul trouble is not worth fading."""
    box = [_player(9, "Deep Bench", "BOS", fouls=4, usage=0.06),
           _player(2, "Mate", "BOS", fouls=0, usage=0.20)]
    assert monitor_foul_trouble(box, period=2) == []


def test_validation_passes_at_60pct_clv():
    """validate_foul_trouble_signal passes when CLV>0 on >=60% of fires."""
    box = _box_with_foul_trouble()
    # 10 events, 7 with positive CLV -> 70% -> pass.
    events = [{"players": box, "period": 2, "clv": 0.02} for _ in range(7)]
    events += [{"players": box, "period": 2, "clv": -0.01} for _ in range(3)]
    result = validate_foul_trouble_signal(events)
    assert result["n_fired"] == 10
    assert result["clv_positive_rate"] == 0.7
    assert result["pass"] is True


def test_validation_fails_below_60pct_clv():
    """The validation gate fails when CLV>0 on fewer than 60% of fires."""
    box = _box_with_foul_trouble()
    events = [{"players": box, "period": 2, "clv": 0.02} for _ in range(4)]
    events += [{"players": box, "period": 2, "clv": -0.01} for _ in range(6)]
    result = validate_foul_trouble_signal(events)
    assert result["pass"] is False


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
