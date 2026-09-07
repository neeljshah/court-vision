"""G313 construct: the ten distinct player_ids are a fixed slot pool, not a count.

n = 1 (CONSTRUCT), driven four ways (3/5/8/12 detections per team). Synthetic well-separated
detections through the REAL `_match_team_bytetrack`; no YOLO, no OSNet, no video. Nothing measures
tracking quality -- lifting the ceiling is not the same as tracking better.
Run this ONE file (conda env basketball_ai). Never a full pytest.
"""
from __future__ import annotations

from scripts.platformkit.tracking import g313_slot_cap_construct as construct


def test_slot_pool_is_eleven_fixed_slots():
    """unified_pipeline.py:821 builds 5 green + 5 white + 1 referee, and only those."""
    from src.pipeline.unified_pipeline import UnifiedPipeline

    players = UnifiedPipeline._build_players(None)
    assert len(players) == 11
    assert sorted(p.ID for p in players) == list(range(11))
    assert sorted(p.team for p in players) == ["green"] * 5 + ["referee"] + ["white"] * 5


def test_more_than_ten_detections_saturate_at_ten_ids():
    """Eight per team still yield exactly ids 1..10; six are left matcher-unmatched."""
    result = construct.run(per_team=8)
    assert result["offered"] == 16
    assert result["per_team_matched"] == {"green": 5, "white": 5, "referee": 0}
    assert result["distinct_ids"] == 10
    assert result["ids"] == list(range(1, 11))
    assert result["matcher_unmatched"] == 6


def test_ten_is_the_cap_not_a_constant():
    """Below the pool size the count follows the detections, so 10 is a ceiling."""
    assert construct.run(per_team=3)["distinct_ids"] == 6
    assert construct.run(per_team=5)["distinct_ids"] == 10
    assert construct.run(per_team=12)["distinct_ids"] == 10
