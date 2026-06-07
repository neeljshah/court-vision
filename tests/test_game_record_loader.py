"""test_game_record_loader.py — minimal smoke test for load_model_series_game_record.

Verifies that the adapter correctly parses game_record_0042500401.jsonl and
yields projection rows with finite proj_pts/reb/ast and parseable timestamps.
"""
import math
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "ingame"))

# Skip gracefully if the fixture file is absent (e.g. fresh clone)
FIXTURE = _ROOT / "data" / "cache" / "ingame" / "game_record_0042500401.jsonl"
pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="game_record_0042500401.jsonl not present",
)


def test_loader_returns_nonempty_series():
    from grade_ingame_vs_vegas import load_model_series_game_record

    series, name_to_pid = load_model_series_game_record("0042500401")

    # Must have at least one (pid, stat) series
    assert len(series) > 0, "Expected at least one (pid, stat) series"

    # name_to_pid must have at least one mapping
    assert len(name_to_pid) > 0, "Expected at least one name->pid mapping"


def test_loader_rows_have_finite_projections():
    from grade_ingame_vs_vegas import load_model_series_game_record

    series, _ = load_model_series_game_record("0042500401")

    for (pid, stat), rows in series.items():
        assert len(rows) >= 1, f"Empty series for ({pid}, {stat})"
        for epoch_ms, period, prod_proj, unified_proj in rows:
            # epoch_ms must be a valid large integer (ms since epoch)
            assert isinstance(epoch_ms, int), "epoch_ms must be int"
            assert epoch_ms > 1_000_000_000_000, f"epoch_ms too small: {epoch_ms}"
            # period must be 1-4
            assert 1 <= period <= 4, f"period out of range: {period}"
            # unified_proj (= proj_pts/reb/ast) must be finite
            assert isinstance(unified_proj, float), "unified_proj must be float"
            assert math.isfinite(unified_proj), f"non-finite unified_proj: {unified_proj}"
            # prod_proj is None for game_record (no separate production head)
            assert prod_proj is None, f"Expected None prod_proj for game_record; got {prod_proj}"


def test_loader_covers_pts_reb_ast():
    from grade_ingame_vs_vegas import load_model_series_game_record

    series, _ = load_model_series_game_record("0042500401")

    stats_present = {stat for (_, stat) in series.keys()}
    for expected in ("pts", "reb", "ast"):
        assert expected in stats_present, f"Stat '{expected}' missing from series"


def test_loader_no_fg3m():
    """game_record has no fg3m — the loader must not fabricate it."""
    from grade_ingame_vs_vegas import load_model_series_game_record

    series, _ = load_model_series_game_record("0042500401")
    stats_present = {stat for (_, stat) in series.keys()}
    assert "fg3m" not in stats_present, "fg3m should not appear in game_record series"


def test_loader_timestamps_parseable():
    """All epoch_ms values must correspond to a date during the 2026 Finals."""
    from grade_ingame_vs_vegas import load_model_series_game_record
    from datetime import datetime, timezone

    series, _ = load_model_series_game_record("0042500401")

    # Earliest game tick: 2026-06-03 ~20:00 ET = ~00:00 UTC 06-04
    # Latest expected tick: 2026-06-04 ~03:30 UTC
    lo = 1780500000000  # 2026-06-03 ~18:40 UTC (generous lower bound)
    hi = 1780560000000  # 2026-06-04 ~11:00 UTC (generous upper bound)

    for (pid, stat), rows in series.items():
        for epoch_ms, *_ in rows:
            assert lo <= epoch_ms <= hi, (
                f"epoch_ms {epoch_ms} ({datetime.fromtimestamp(epoch_ms/1000, tz=timezone.utc)}) "
                f"outside expected game window for ({pid}, {stat})"
            )
