"""Per-file test for the OT-period fetch fix in fetch_per_quarter_boxscores.py.

Regression test for the bug found by composite v2 (commit 7b5ad29a): this
fetcher used to hardcode periods 1-4 only, silently dropping all OT scoring.
No network calls here -- fetch_quarter is monkeypatched.

Run:
  cd /c/Users/neelj/nba-ai-system &&
  python -m pytest scripts/test_fetch_per_quarter_boxscores.py -q
"""
from __future__ import annotations

import json
import os

import scripts.fetch_per_quarter_boxscores as m


def test_quarter_range_covers_regulation_and_4_ot_periods():
    assert m._QUARTER_RANGE[4] == (21600, 28800)
    assert m._QUARTER_RANGE[5] == (28800, 31800)  # 1st OT, 5 min
    assert m._QUARTER_RANGE[8] == (37800, 40800)  # 4th OT
    assert len(m._QUARTER_RANGE) == 4 + m._MAX_OT_PERIODS


def test_fetch_ot_periods_stops_at_first_empty_period(tmp_path, monkeypatch):
    cache_dir = str(tmp_path)
    calls = []

    def fake_fetch_quarter(game_id, period, cache_dir=cache_dir):
        calls.append(period)
        teams = [{"team_id": 1, "pts": 10}] if period == 5 else []
        payload = {"game_id": game_id, "period": period, "players": [], "teams": teams}
        with open(os.path.join(cache_dir, f"{game_id}_q{period}.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return True

    monkeypatch.setattr(m, "fetch_quarter", fake_fetch_quarter)
    written = m.fetch_ot_periods("0000000001", cache_dir=cache_dir)

    assert written == 1  # only period 5 was non-empty
    assert calls == [5, 6]  # probed 6, found it empty, stopped (never tried 7/8)


def test_fetch_ot_periods_all_regulation_no_ot(tmp_path, monkeypatch):
    cache_dir = str(tmp_path)

    def fake_fetch_quarter(game_id, period, cache_dir=cache_dir):
        payload = {"game_id": game_id, "period": period, "players": [], "teams": []}
        with open(os.path.join(cache_dir, f"{game_id}_q{period}.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return True

    monkeypatch.setattr(m, "fetch_quarter", fake_fetch_quarter)
    written = m.fetch_ot_periods("0000000002", cache_dir=cache_dir)

    assert written == 0
    assert os.path.exists(os.path.join(cache_dir, "0000000002_q5.json"))
    assert not os.path.exists(os.path.join(cache_dir, "0000000002_q6.json"))


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
