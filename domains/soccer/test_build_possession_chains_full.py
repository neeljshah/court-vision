"""Per-file test for build_possession_chains_full.py -- runs the REAL builder
against a small real slice (30 matches) of the on-disk statsbomb corpus, plus
unit checks on the resumability (skip-already-done) behavior with synthetic
data. Skips if the real corpus isn't present on this box (CI-safe).
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_build_possession_chains_full.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from domains.soccer import build_possession_chains_full as m

_HAVE_CORPUS = m._META_PATH.exists() and m._EVENTS_DIR.exists()


@pytest.mark.skipif(not _HAVE_CORPUS, reason="statsbomb full-pull corpus not present on this box")
def test_small_real_slice_produces_rows(tmp_path):
    meta = pd.read_parquet(m._META_PATH)
    cached = {p.stem for p in m._EVENTS_DIR.glob("*.json")}
    slice_ids = [int(mid) for mid in meta["match_id"] if str(mid) in cached][:30]
    assert len(slice_ids) >= 20, "expected >=20 real matches with cached events for the slice"

    out_path = tmp_path / "possession_chains_full.parquet"
    progress_path = tmp_path / "progress.json"
    cov = m.build(out_path=out_path, progress_path=progress_path, match_ids=slice_ids)

    assert cov["matches_processed_this_run"] == len(slice_ids)
    assert cov["stopped_reason"] is None
    assert out_path.exists()
    df = pd.read_parquet(out_path)
    assert len(df) > 0
    assert df["match_id"].nunique() == len(slice_ids)
    assert set(["match_id", "possession", "team_id", "team_name", "play_pattern",
                "xg", "year", "pattern_group", "is_counter", "team_matches"]).issubset(df.columns)
    assert (df["xg"] >= 0).all()
    assert set(df["pattern_group"].unique()).issubset({"counter", "regular", "set_piece_derived"})

    # re-run with the same slice -- resumable, zero new rows processed
    cov2 = m.build(out_path=out_path, progress_path=progress_path, match_ids=slice_ids)
    assert cov2["matches_processed_this_run"] == 0
    assert cov2["matches_done_before_run"] == len(slice_ids)
    assert cov2["possession_rows_total"] == cov["possession_rows_total"]


def test_pattern_group_bucketing():
    assert m._pattern_group("From Counter") == "counter"
    assert m._pattern_group("Regular Play") == "regular"
    assert m._pattern_group("From Corner") == "set_piece_derived"


def test_match_possessions_sums_shots_and_keeps_shotless(tmp_path):
    events = [
        {"possession": 1, "possession_team": {"id": 10, "name": "A"},
         "play_pattern": {"name": "From Counter"}, "type": {"name": "Pass"}},
        {"possession": 1, "possession_team": {"id": 10, "name": "A"},
         "play_pattern": {"name": "From Counter"}, "type": {"name": "Shot"},
         "shot": {"statsbomb_xg": 0.10}},
        {"possession": 2, "possession_team": {"id": 20, "name": "B"},
         "play_pattern": {"name": "Regular Play"}, "type": {"name": "Pass"}},
    ]
    ev_path = tmp_path / "1.json"
    ev_path.write_text(json.dumps(events), encoding="utf-8")
    rows = m._match_possessions(1, 2020, ev_path)
    assert len(rows) == 2
    by_poss = {r["possession"]: r for r in rows}
    assert abs(by_poss[1]["xg"] - 0.10) < 1e-9
    assert by_poss[2]["xg"] == 0.0


def test_missing_meta_row_skips_match(tmp_path):
    # meta with one match_id that has no cached event file -> counted missing, not crashed
    meta = pd.DataFrame([{"match_id": 999999, "match_date": "2020-01-01"}])
    meta_path = tmp_path / "meta.parquet"
    meta.to_parquet(meta_path, index=False)
    out_path = tmp_path / "out.parquet"
    progress_path = tmp_path / "progress.json"
    cov = m.build(events_dir=tmp_path, meta_path=meta_path, out_path=out_path, progress_path=progress_path)
    assert cov["matches_missing_event_file"] == 1
    assert cov["matches_processed_this_run"] == 0
    assert not out_path.exists()
