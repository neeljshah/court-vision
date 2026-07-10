"""Per-file test for domains.mlb.starter_table_full_seasons. Run ONLY this file:

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_starter_table_full_seasons.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from domains.mlb import starter_table_full_seasons as ST  # noqa: E402

_STATCAST = Path(__file__).resolve().parents[2] / "data" / "cache" / "statcast"
_FP2026 = _STATCAST / "starter_table__2026.parquet"


def _planted_savant_full(season: int) -> pd.DataFrame:
    """One game, one pitch-side pair -- same shape as the real savant_full pull
    (columns build_starter_table reads)."""
    return pd.DataFrame({
        "game_pk": [1, 1, 1], "game_date": [f"{season}-05-02"] * 3,
        "inning": [1, 1, 1], "inning_topbot": ["Top", "Top", "Bot"],
        "at_bat_number": [1, 2, 1], "pitch_number": [1, 1, 1],
        "pitcher": [100, 100, 200], "batter": [5, 5, 6],
        "events": ["strikeout", "field_out", "walk"],
        "release_speed": [95.0, 94.0, 90.0], "release_spin_rate": [2200.0, 2100.0, 2000.0],
        "pitch_type": ["FF", "SL", "FF"], "home_team": ["AAA"] * 3, "away_team": ["BBB"] * 3,
    })


def test_build_season_writes_parquet_from_existing_savant_full(tmp_path):
    src = ST._source_fp(2024, tmp_path)
    _planted_savant_full(2024).to_parquet(src, index=False)
    res = ST.build_season(2024, cache_dir=tmp_path)
    assert res["status"] == "OK"
    assert res["starter_starts"] == 2   # home starter 100, away starter 200
    out_fp = ST._out_fp(2024, tmp_path)
    assert out_fp.exists()
    st = pd.read_parquet(out_fp)
    assert set(["season", "game_id", "pitcher", "label_k"]).issubset(st.columns)
    assert (st["season"] == 2024).all()


def test_build_season_missing_source_is_honest_not_a_crash(tmp_path):
    res = ST.build_season(2099, cache_dir=tmp_path)
    assert res["status"] == "MISSING_SOURCE"
    assert res["starter_starts"] == 0
    assert not ST._out_fp(2099, tmp_path).exists()


def test_build_season_is_resumable_skips_existing_without_reread(tmp_path):
    src = ST._source_fp(2025, tmp_path)
    _planted_savant_full(2025).to_parquet(src, index=False)
    res1 = ST.build_season(2025, cache_dir=tmp_path)
    assert res1["status"] == "OK"
    # corrupt the source AFTER the first build -- a re-run must skip it, not re-read
    src.write_text("not a parquet file")
    res2 = ST.build_season(2025, cache_dir=tmp_path)
    assert res2["status"] == "SKIPPED_EXISTS"
    assert res2["starter_starts"] == res1["starter_starts"]


def test_build_seasons_reports_each_season():
    res = ST.build_seasons([2099, 2098])
    assert set(res["seasons"].keys()) == {"2099", "2098"}
    assert all(v["status"] == "MISSING_SOURCE" for v in res["seasons"].values())


@pytest.mark.skipif(not _FP2026.exists(),
                    reason="on-disk starter_table__2026.parquet absent (clean clone)")
def test_2026_starter_table_nonzero_and_schema_matches_2023():
    fp2023 = _STATCAST / "starter_table__2023.parquet"
    st26 = pd.read_parquet(_FP2026)
    assert len(st26) > 0
    if fp2023.exists():
        assert set(pd.read_parquet(fp2023).columns) == set(st26.columns)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
