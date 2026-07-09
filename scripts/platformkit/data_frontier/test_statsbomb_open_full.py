"""Per-file test. Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/data_frontier/test_statsbomb_open_full.py -q
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from scripts.platformkit.data_frontier import statsbomb_open_full as sb


def _tree_fetcher(ids):
    tree = {"tree": [{"path": f"data/events/{i}.json"} for i in ids] +
                     [{"path": "data/matches/2/27.json"}, {"path": "data/lineups/1.json"}]}

    def _fetch(url, headers=None, timeout=None):
        return SimpleNamespace(status_code=200, json=lambda: tree, content=b"{}")
    return _fetch


def test_fetch_event_id_list_filters_events_only(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "_TREE_CACHE", tmp_path / "_tree_full.json")
    ids = sb.fetch_event_id_list(fetcher=_tree_fetcher(["101", "102", "103"]))
    assert ids == ["101", "102", "103"]


def test_pull_skips_already_cached_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "_TREE_CACHE", tmp_path / "_tree_full.json")
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    (events_dir / "101.json").write_bytes(b'[{"already": "cached"}]')

    calls = []

    def _raw_fetch(url, headers=None, timeout=None):
        calls.append(url)
        return SimpleNamespace(status_code=200, content=b'[{"id": 1}]')

    def _fetcher(url, headers=None, timeout=None):
        if "git/trees" in url:
            return _tree_fetcher(["101", "102"])(url, headers, timeout)
        return _raw_fetch(url, headers, timeout)

    res = sb.pull(
        fetcher=_fetcher, events_dir=events_dir,
        log_path=tmp_path / "log.txt", progress_path=tmp_path / "progress.json",
        delay_s=0.0,
    )
    assert calls == ["https://raw.githubusercontent.com/statsbomb/open-data/master/data/events/102.json"]
    assert res["fetched_this_run"] == 1
    assert res["already_cached_before_run"] == 1
    assert res["now_cached"] == 2
    assert (events_dir / "102.json").exists()


def test_pull_stops_after_consecutive_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "_TREE_CACHE", tmp_path / "_tree_full.json")
    monkeypatch.setattr(sb, "_MAX_CONSECUTIVE_FAILURES", 2)
    events_dir = tmp_path / "events"
    events_dir.mkdir()

    def _fetcher(url, headers=None, timeout=None):
        if "git/trees" in url:
            return _tree_fetcher([str(i) for i in range(10)])(url, headers, timeout)
        return SimpleNamespace(status_code=500, content=b"")

    res = sb.pull(
        fetcher=_fetcher, events_dir=events_dir,
        log_path=tmp_path / "log.txt", progress_path=tmp_path / "progress.json",
        delay_s=0.0,
    )
    assert res["stopped_reason"] == "consecutive_failures"
    assert res["fetched_this_run"] == 0
    assert res["failed_this_run"] == 2


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
