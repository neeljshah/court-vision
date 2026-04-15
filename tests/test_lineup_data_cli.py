"""
test_lineup_data_cli.py — Task 7: --bulk CLI dry-run tests.

Verifies the python -m src.data.lineup_data --season X --bulk entry point
works without making any NBA API calls (dry-run mode).
"""
import pytest


class TestLineupDataCLI:
    """Tests for the python -m src.data.lineup_data CLI entry point."""

    def test_bulk_dry_run_no_api_calls(self, capsys, monkeypatch):
        """--bulk --dry-run prints plan without making any API calls."""
        from src.data.lineup_data import _main

        called = []
        monkeypatch.setattr(
            "src.data.lineup_data.scrape_all_teams",
            lambda seasons=None, force=False, min_minutes=5.0: called.append(seasons) or {},
        )

        _main(["--season", "2024-25", "--bulk", "--dry-run"])

        out = capsys.readouterr().out
        assert "DRY-RUN" in out, f"Expected DRY-RUN label, got: {out!r}"
        assert "30 teams" in out, f"Expected team count, got: {out!r}"
        assert not called, "scrape_all_teams must NOT be called in dry-run mode"

    def test_bulk_flag_calls_scrape_all_teams(self, monkeypatch):
        """--bulk (without --dry-run) calls scrape_all_teams with the requested season."""
        from src.data.lineup_data import _main

        calls = []
        monkeypatch.setattr(
            "src.data.lineup_data.scrape_all_teams",
            lambda seasons=None, force=False, min_minutes=5.0: calls.append(seasons) or {},
        )

        _main(["--season", "2024-25", "--bulk"])

        assert len(calls) == 1, f"Expected 1 call, got {len(calls)}"
        assert calls[0] == ["2024-25"], f"Expected ['2024-25'], got {calls[0]}"

    def test_dry_run_without_bulk_covers_multi_season(self, capsys, monkeypatch):
        """--dry-run without --bulk uses the default multi-season list."""
        from src.data.lineup_data import _main

        monkeypatch.setattr(
            "src.data.lineup_data.scrape_all_teams",
            lambda **kw: None,
        )

        _main(["--dry-run"])

        out = capsys.readouterr().out
        # Default seasons is 3 → total requests > 30
        assert "DRY-RUN" in out
        # Should mention more than 30 requests (30 teams × 3 seasons = 90)
        import re
        m = re.search(r"= (\d+) requests", out)
        assert m and int(m.group(1)) >= 60, f"Expected >= 60 requests, got: {out!r}"
