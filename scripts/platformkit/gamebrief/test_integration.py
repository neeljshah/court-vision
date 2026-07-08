"""One real historical game through the full assemble+render path. Skips (not
fails) if games.parquet is absent -- this lane must still be testable on a
checkout without data/. Sections with a genuinely-absent source (e.g. no
injury feed at this historical date) are allowed to render "not_available";
the assertion is that every section KEY is present and non-empty (a dict),
not that every section has data.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.platformkit.gamebrief.assemble import assemble
from scripts.platformkit.gamebrief.render import render

_GAMES = Path(__file__).resolve().parents[3] / "data/domains/basketball_nba/games.parquet"


@pytest.mark.skipif(not _GAMES.exists(), reason="games.parquet not present on this checkout")
def test_real_matchup_all_sections_render():
    brief = assemble("OKC", "DEN", "2026-02-27")
    assert "error" not in brief

    assert brief["matchup"]["home"] == "OKC" and brief["matchup"]["away"] == "DEN"
    assert 0.0 <= brief["elo_win_prob"]["home_win_prob"] <= 1.0
    assert brief["rest_and_schedule"]["status"] == "ok"

    for team in ("OKC", "DEN"):
        block = brief["teams"][team]
        for section in ("injuries", "news", "gravity", "lineup_synergy", "on_off", "shooting_luck_last5"):
            assert isinstance(block[section], dict) and "status" in block[section]
        # season-to-date FGA leaders must be non-empty this deep into a season
        assert len(block["top3_fga_season_to_date"]) == 3

    assert brief["concession_matchup"]["status"] == "ok"
    assert set(brief["honesty_labels"]) == {
        "gravity", "lineup_synergy", "on_off", "shooting_luck", "concession_matchup"}

    text = render(brief)
    assert "GAME BRIEF" in text and "HONESTY LABELS" in text
    assert all(ord(c) < 128 for c in text)  # ASCII-only stdout invariant


@pytest.mark.skipif(not _GAMES.exists(), reason="games.parquet not present on this checkout")
def test_unknown_team_and_unknown_date_are_clear_errors():
    assert "unknown" in assemble("ZZZ", "DEN", "2026-02-27")["error"]
    assert "no game found" in assemble("OKC", "DEN", "1999-01-01")["error"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
