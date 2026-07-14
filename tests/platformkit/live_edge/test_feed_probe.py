"""Per-file test for scripts.platformkit.live_edge.shadow.feed_probe.

No live network calls here -- probes are injected fakes (mirrors
test_news_parse.py's discipline for news/probe.py). The real network probe is
run manually (python -m scripts.platformkit.live_edge.shadow.feed_probe), not
from the test suite.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_feed_probe.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.live_edge.shadow import feed_probe as fp


def test_run_probe_no_sleep_between_last_candidate(tmp_path):
    calls = {"sleeps": 0}
    probes = {
        "a": lambda: {"verdict": "REACHABLE", "status": 200, "n_items": 3},
        "b": lambda: {"verdict": "BLOCKED", "status": 403, "error": "forbidden"},
    }
    out = fp.run_probe(probes, sleep_fn=lambda s: calls.__setitem__("sleeps", calls["sleeps"] + 1))
    assert calls["sleeps"] == 1  # jitter only BETWEEN candidates, never after the last
    assert out["a"]["verdict"] == "REACHABLE"
    assert out["b"]["verdict"] == "BLOCKED"
    assert "latency_sec" in out["a"]


def test_write_probe_md_writes_table_and_raw_json(tmp_path):
    results = {
        "kalshi_KXNBAMIN": {"verdict": "BLOCKED", "status": 200, "n_markets": 0,
                             "error": "0 open markets", "latency_sec": 0.1},
        "fanduel_nba_page": {"verdict": "DEAD", "status": None,
                              "error": "TimeoutError: x", "latency_sec": 0.2},
    }
    out_path = tmp_path / "PROBE.md"
    path = fp.write_probe_md(results, out_path=out_path)
    assert path == out_path
    text = out_path.read_text(encoding="ascii")
    assert "kalshi_KXNBAMIN" in text and "BLOCKED" in text
    assert "fanduel_nba_page" in text and "DEAD" in text
    raw = json.loads(text.split("```json\n", 1)[1].rsplit("```", 1)[0])
    assert raw["kalshi_KXNBAMIN"]["error"] == "0 open markets"


def test_kalshi_probe_classifies_http_error_codes(monkeypatch):
    import urllib.error

    def _raise_403(url, timeout=None):
        raise urllib.error.HTTPError(url, 403, "forbidden", {}, None)

    monkeypatch.setattr(fp, "resilient_get_json", _raise_403)
    out = fp._probe_kalshi_series("KXNBAMIN")
    assert out["verdict"] == "BLOCKED"
    assert out["status"] == 403


def test_kalshi_probe_dead_on_unexpected_exception(monkeypatch):
    def _raise(url, timeout=None):
        raise TimeoutError("no route")

    monkeypatch.setattr(fp, "resilient_get_json", _raise)
    out = fp._probe_kalshi_series("KXNBAMIN")
    assert out["verdict"] == "DEAD"


def test_kalshi_probe_reachable_with_markets(monkeypatch):
    monkeypatch.setattr(fp, "resilient_get_json", lambda url, timeout=None: {"markets": [{"ticker": "x"}]})
    out = fp._probe_kalshi_series("KXNBAMIN")
    assert out["verdict"] == "REACHABLE"
    assert out["n_markets"] == 1
