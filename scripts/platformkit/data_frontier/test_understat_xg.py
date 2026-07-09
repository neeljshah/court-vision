"""Per-file test. Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/data_frontier/test_understat_xg.py -q
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from scripts.platformkit.data_frontier import understat_xg as ux


def _robots_fetcher(body: str, status: int = 200):
    def _fetch(url, headers=None, timeout=None):
        return SimpleNamespace(status_code=status, text=body)
    return _fetch


def test_check_robots_detects_full_disallow():
    gate = ux.check_robots(fetcher=_robots_fetcher("User-agent: *\nDisallow: /\n"))
    assert gate["allowed"] is False


def test_check_robots_allows_when_disallow_scoped():
    gate = ux.check_robots(fetcher=_robots_fetcher("User-agent: *\nDisallow: /admin/\n"))
    assert gate["allowed"] is True


def test_check_robots_fails_closed_on_fetch_error():
    def _boom(url, headers=None, timeout=None):
        raise __import__("requests").RequestException("network down")
    gate = ux.check_robots(fetcher=_boom)
    assert gate["allowed"] is False


def test_pull_writes_blocked_status_and_never_scrapes(tmp_path, monkeypatch):
    monkeypatch.setattr(ux, "_STATUS_FP", tmp_path / "status.json")
    monkeypatch.setattr(ux, "_LOG_FP", tmp_path / "log.txt")
    res = ux.pull(fetcher=_robots_fetcher("User-agent: *\nDisallow: /\n"))
    assert res["verdict"] == "BLOCKED_ROBOTS"
    written = json.loads((tmp_path / "status.json").read_text())
    assert written["verdict"] == "BLOCKED_ROBOTS"


def test_parse_blob_decodes_hex_escaped_json():
    payload = json.dumps({"match_info": {"id": "26635", "home_xG": "1.83"}})
    hex_escaped = "".join(f"\\x{b:02x}" for b in payload.encode("utf-8"))
    html = f"<script>var match_info = JSON.parse('{hex_escaped}');</script>"
    decoded = ux.parse_blob(html)
    assert decoded["match_info"]["id"] == "26635"
    assert decoded["match_info"]["home_xG"] == "1.83"


def test_parse_blob_returns_none_when_no_blob_present():
    assert ux.parse_blob("<html><body>no data here</body></html>") is None


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
