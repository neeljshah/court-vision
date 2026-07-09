"""Per-file test. Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/data_frontier/test_bbref_advanced.py -q
"""
from __future__ import annotations

from types import SimpleNamespace

from scripts.platformkit.data_frontier import bbref_advanced as ba

_WNBA_HTML = """
<table id="advanced">
<tbody>
<tr><td data-stat="player">A'ja Wilson</td><td data-stat="team">LVA</td>
<td data-stat="pos">F</td><td data-stat="g">40</td><td data-stat="mp">1300</td>
<td data-stat="per">32.1</td><td data-stat="ts_pct">.640</td>
<td data-stat="efg_pct">.600</td><td data-stat="fg3a_per_fga_pct">.050</td>
<td data-stat="fta_per_fga_pct">.300</td><td data-stat="orb_pct">10.0</td>
<td data-stat="trb_pct">20.0</td><td data-stat="ast_pct">15.0</td>
<td data-stat="stl_pct">2.0</td><td data-stat="blk_pct">3.0</td>
<td data-stat="tov_pct">10.0</td><td data-stat="usg_pct">30.0</td>
<td data-stat="off_rtg">120</td><td data-stat="def_rtg">95</td>
<td data-stat="ows">5.0</td><td data-stat="dws">3.0</td><td data-stat="ws">8.0</td>
<td data-stat="ws_per_40">.300</td></tr>
<tr class="thead"><td data-stat="player">Player</td></tr>
<tr><td data-stat="player"></td></tr>
</tbody>
</table>
"""


def test_parse_wnba_advanced_extracts_one_real_row_skips_header_and_blank():
    records = ba._parse_wnba_advanced(_WNBA_HTML)
    assert len(records) == 1
    assert records[0]["player"] == "A'ja Wilson"


def test_normalise_wnba_maps_columns_and_year():
    records = ba._parse_wnba_advanced(_WNBA_HTML)
    df = ba._normalise_wnba(records, 2025)
    row = df.iloc[0]
    assert row["player_name"] == "A'ja Wilson"
    assert row["team"] == "LVA"
    assert row["off_rtg"] == 120.0
    assert row["season_year"] == 2025
    assert "bpm" not in df.columns  # WNBA table has no BPM/VORP family


def test_pull_wnba_skips_already_cached_year(tmp_path):
    out_dir = tmp_path / "bbref_wnba"
    out_dir.mkdir()
    (out_dir / "wnba_advanced_2024.parquet").write_bytes(b"placeholder")

    calls = []

    def _fetcher(url, timeout=None):
        calls.append(url)
        return SimpleNamespace(status=200, body=_WNBA_HTML)

    res = ba.pull_wnba([2024, 2025], fetcher=_fetcher, out_dir=out_dir,
                        log_path=tmp_path / "log.txt")
    assert res["skipped_already_cached"] == [2024]
    assert res["landed"] == [2025]
    assert len(calls) == 1
    assert (out_dir / "wnba_advanced_2025.parquet").exists()


def test_nba_coverage_true_when_parquet_or_json_present(tmp_path, monkeypatch):
    backfill_dir = tmp_path / "bbref_backfill"
    external_dir = tmp_path / "external"
    backfill_dir.mkdir()
    external_dir.mkdir()
    monkeypatch.setattr(ba, "_NBA_BACKFILL_DIR", backfill_dir)
    monkeypatch.setattr(ba, "_NBA_EXTERNAL_DIR", external_dir)
    monkeypatch.setattr(ba, "NBA_TARGET_SEASONS", ["2022-23", "2024-25"])
    (backfill_dir / "advanced_2022-23.parquet").write_bytes(b"x")
    (external_dir / "bbref_advanced_2024-25.json").write_text("[]")

    cov = ba.nba_coverage()
    assert cov == {"2022-23": True, "2024-25": True}


def test_ensure_nba_skips_network_when_fully_covered(tmp_path, monkeypatch):
    monkeypatch.setattr(ba, "nba_coverage", lambda: {"2022-23": True, "2024-25": True})
    monkeypatch.setattr(ba, "NBA_TARGET_SEASONS", ["2022-23", "2024-25"])
    res = ba.ensure_nba()
    assert res["already_covered"] is True
    assert res["seasons_fetched"] == []


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
