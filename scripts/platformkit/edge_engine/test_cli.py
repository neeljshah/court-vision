"""Per-file test for cli.run_once + format_summary. No network (dry-run over injected getters)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.platformkit.edge_engine import cli, injury_facts, news_facts  # noqa: E402


def test_run_once_survives_a_dead_feed(monkeypatch, tmp_path):
    from scripts.platformkit.edge_engine import facts_store
    monkeypatch.setattr(facts_store, "FACTS_DIR", tmp_path)

    # injuries return a tiny payload; news raises -> must be reported, not fatal.
    monkeypatch.setattr(injury_facts, "fetch_injuries",
                        lambda sport, http_get=None: [
                            {"player_name": "A", "status": "OUT", "report_date": "2026-07-08",
                             "sport": sport, "source": "espn_injuries", "team": "T",
                             "detail": "", "source_url": "",
                             "fetched_at": "2026-07-08T20:00:00+00:00"}])

    def _boom(sport, http_get=None):
        raise RuntimeError("feed down")
    monkeypatch.setattr(news_facts, "fetch_news", _boom)

    results = cli.run_once(dry_run=True)
    kinds = {(r["kind"], r["sport"]): r for r in results}
    assert kinds[("injury", "nba")]["fetched"] == 1
    assert kinds[("injury", "nba")]["error"] == ""
    assert kinds[("news", "nba")]["error"] == "RuntimeError"
    # summary renders as ASCII with no exception.
    out = cli.format_summary(results)
    assert out.isascii() and "KIND" in out
