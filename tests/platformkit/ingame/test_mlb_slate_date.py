"""S184 construct checks for consistent MLB live-slate date resolution."""
from datetime import datetime, timedelta, timezone

from scripts.platformkit.ingame.mlb_book_capture import capture_once


def _resolved_date(now: datetime, date_str: str | None = None) -> str:
    seen = []

    def fake_live_games(_client, resolved, _state):
        seen.append(resolved)
        return []

    capture_once(now=now, date_str=date_str, state={}, live_games_fn=fake_live_games)
    return seen[0]


def test_capture_slate_date_matches_gumbo_default_for_all_utc_hours():
    rows = []
    for hour in range(24):
        now = datetime(2026, 9, 2, hour, tzinfo=timezone.utc)
        resolved = _resolved_date(now)
        gumbo_default = (now - timedelta(hours=10)).strftime("%Y-%m-%d")
        rows.append((hour, resolved, gumbo_default))

    assert len(rows) == 24
    assert [hour for hour, resolved, gumbo_default in rows if resolved != gumbo_default] == []


def test_capture_explicit_date_str_still_overrides_slate_date():
    now = datetime(2026, 9, 2, 3, tzinfo=timezone.utc)

    assert _resolved_date(now, date_str="2026-09-08") == "2026-09-08"
