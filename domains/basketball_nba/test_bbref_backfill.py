"""Offline tests for domains.basketball_nba.bbref_backfill -- zero network.

Every fetch is replaced by an injected fake fetcher returning a canned HTML
fixture, mirroring the offline-injection pattern already used by
scripts/platformkit/odds_provider/test_stealth_fetch.py. No scrapling call,
no real HTTP request, ever executes in this test file.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from domains.basketball_nba import bbref_backfill

# A trimmed but structurally faithful bbref "advanced" table fixture: two
# player rows with data-stat attributes matching the real page's schema
# (verified against src/data/bbref_scraper.py's _parse_advanced_table column
# names), wrapped exactly like bbref wraps some tables in an HTML comment.
_FIXTURE_HTML = """
<html><body>
<div id="all_advanced">
<!--
<table id="advanced">
<thead>
<tr><th data-stat="player">Player</th></tr>
</thead>
<tbody>
<tr>
<td data-stat="name_display">Jayson Tatum</td>
<td data-stat="team_name_abbr">BOS</td>
<td data-stat="obpm">4.1</td>
<td data-stat="dbpm">1.2</td>
<td data-stat="bpm">5.3</td>
<td data-stat="vorp">4.8</td>
<td data-stat="ws_per_48">0.190</td>
<td data-stat="ws">10.1</td>
<td data-stat="ows">6.2</td>
<td data-stat="dws">3.9</td>
<td data-stat="orb_pct">3.1</td>
<td data-stat="drb_pct">18.4</td>
<td data-stat="trb_pct">10.8</td>
<td data-stat="stl_pct">1.4</td>
<td data-stat="blk_pct">1.1</td>
<td data-stat="tov_pct">9.8</td>
<td data-stat="ast_pct">22.3</td>
<td data-stat="per">22.9</td>
<td data-stat="fta_per_fga_pct">0.310</td>
<td data-stat="fg3a_per_fga_pct">0.480</td>
<td data-stat="usg_pct">29.5</td>
<td data-stat="ts_pct">0.607</td>
</tr>
<tr>
<td data-stat="name_display">Jaylen Brown</td>
<td data-stat="team_name_abbr">BOS</td>
<td data-stat="obpm">2.8</td>
<td data-stat="dbpm">0.5</td>
<td data-stat="bpm">3.3</td>
<td data-stat="vorp">3.0</td>
<td data-stat="ws_per_48">0.160</td>
<td data-stat="ws">7.5</td>
<td data-stat="ows">4.5</td>
<td data-stat="dws">3.0</td>
<td data-stat="orb_pct">3.9</td>
<td data-stat="drb_pct">12.1</td>
<td data-stat="trb_pct">7.9</td>
<td data-stat="stl_pct">1.6</td>
<td data-stat="blk_pct">0.6</td>
<td data-stat="tov_pct">10.9</td>
<td data-stat="ast_pct">16.0</td>
<td data-stat="per">18.4</td>
<td data-stat="fta_per_fga_pct">0.280</td>
<td data-stat="fg3a_per_fga_pct">0.440</td>
<td data-stat="usg_pct">27.1</td>
<td data-stat="ts_pct">0.583</td>
</tr>
</tbody>
</table>
-->
</div>
</body></html>
"""


class _FakeResponse:
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body


def _fake_fetcher_ok(url: str, **kwargs):
    return _FakeResponse(200, _FIXTURE_HTML)


def _fake_fetcher_blocked(url: str, **kwargs):
    return _FakeResponse(403, "<html>Access Denied</html>")


def test_season_to_year():
    assert bbref_backfill._season_to_year("2020-21") == 2021
    assert bbref_backfill._season_to_year("2023-24") == 2024


def test_parse_advanced_table_unwraps_comment_and_extracts_rows():
    records = bbref_backfill._parse_advanced_table(_FIXTURE_HTML)
    assert len(records) == 2
    assert records[0]["name_display"] == "Jayson Tatum"
    assert records[0]["bpm"] == "5.3"


def test_normalise_rows_maps_columns_and_tags_provenance():
    records = bbref_backfill._parse_advanced_table(_FIXTURE_HTML)
    rows = bbref_backfill._normalise_rows(records, "2020-21", 2021)
    assert len(rows) == 2
    tatum = rows[0]
    assert tatum["player_name"] == "Jayson Tatum"
    assert tatum["team"] == "BOS"
    assert tatum["bpm"] == pytest.approx(5.3)
    assert tatum["vorp"] == pytest.approx(4.8)
    assert tatum["ts_pct"] == pytest.approx(0.607)
    assert tatum["season"] == "2020-21"
    assert tatum["season_year"] == 2021
    assert tatum["source"] == "bbref_backfill_2026-07-05"


def test_fetch_season_html_uses_injected_fetcher_zero_network():
    html = bbref_backfill.fetch_season_html("2020-21", fetcher=_fake_fetcher_ok)
    assert "Jayson Tatum" in html


def test_fetch_season_html_raises_on_blocked_status():
    import urllib.error
    with pytest.raises(urllib.error.HTTPError):
        bbref_backfill.fetch_season_html("2020-21", fetcher=_fake_fetcher_blocked)


def test_backfill_seasons_writes_one_parquet_per_season(tmp_path: Path):
    result = bbref_backfill.backfill_seasons(
        ["2020-21", "2021-22"], fetcher=_fake_fetcher_ok, out_dir=tmp_path,
    )
    assert result.requests_made == 2
    assert result.seasons_landed == ["2020-21", "2021-22"]
    assert result.pages_blocked == []
    assert result.rows_per_season == {"2020-21": 2, "2021-22": 2}

    written = pd.read_parquet(tmp_path / "advanced_2020-21.parquet")
    assert len(written) == 2
    assert set(written["source"]) == {"bbref_backfill_2026-07-05"}
    # matches bbref_advanced_extended.parquet's own advanced-stat column set
    for col in ("bpm", "vorp", "ws", "usg_pct", "ts_pct", "obpm", "dbpm"):
        assert col in written.columns


def test_backfill_seasons_stops_honestly_on_first_block(tmp_path: Path):
    calls = {"n": 0}

    def flaky_fetcher(url: str, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResponse(200, _FIXTURE_HTML)
        return _FakeResponse(403, "<html>blocked</html>")

    result = bbref_backfill.backfill_seasons(
        ["2020-21", "2021-22", "2022-23"], fetcher=flaky_fetcher, out_dir=tmp_path,
    )
    assert result.seasons_landed == ["2020-21"]
    assert len(result.pages_blocked) == 1
    assert "2021-22" in result.pages_blocked[0]
    # honest stop: never tried the third season after the first block
    assert calls["n"] == 2


def test_backfill_seasons_respects_max_requests_cap(tmp_path: Path):
    result = bbref_backfill.backfill_seasons(
        ["2020-21", "2021-22", "2022-23", "2023-24"],
        fetcher=_fake_fetcher_ok, out_dir=tmp_path, max_requests=2,
    )
    assert result.requests_made == 2
    assert len(result.seasons_landed) == 2


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
