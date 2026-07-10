"""Per-file tests for scripts.platformkit.data_frontier.milb_statsapi.

Offline unit tests (fake fetcher) + one REAL-DATA join-rate check of MiLB
player ids vs the mlbam ids in the savant-built profile parquets (skips
honestly if either side is absent on this box; prints the rate when run).

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/data_frontier/test_milb_statsapi.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.data_frontier import milb_statsapi as M


def _fake_http(url: str):
    if "/teams?" in url:
        return {"teams": [{"id": 512, "name": "Toledo Mud Hens", "abbreviation": "TOL",
                           "parentOrgId": 116, "parentOrgName": "Detroit Tigers"}]}
    if "/roster?" in url:
        return {"roster": [
            {"person": {"id": 685382, "fullName": "Andrew Navigato"},
             "position": {"abbreviation": "SS"},
             "status": {"code": "A", "description": "Active"}},
            {"person": {"id": 700001, "fullName": "Prospect Two"},
             "position": {"abbreviation": "C"},
             "status": {"code": "A", "description": "Active"}},
        ]}
    if "/transactions?" in url:
        return {"transactions": [
            {"id": 1, "person": {"id": 685382, "fullName": "Andrew Navigato"},
             "toTeam": {"id": 116, "name": "Detroit Tigers"},
             "fromTeam": {"id": 512, "name": "Toledo Mud Hens"},
             "date": "2026-07-08", "effectiveDate": "2026-07-08",
             "typeCode": "REC", "typeDesc": "Recalled",
             "description": "Detroit Tigers recalled SS Andrew Navigato."}]}
    raise AssertionError("unexpected url %s" % url)


def test_pull_writes_dated_jsonl_and_is_idempotent(tmp_path: Path):
    kw = dict(as_of="2026-07-09", http=_fake_http, out_dir=tmp_path,
              log_path=tmp_path / "log.txt", delay_s=0.0)
    res = M.pull([11], **kw)
    assert res["rosters"]["aaa"] == {"status": "OK", "n_teams": 1,
                                      "n_team_fail": 0, "n_rows": 2}
    assert res["transactions"]["status"] == "OK"
    # window covers BOTH UTC/ET candidate dates: [as_of-15, as_of+1]
    assert res["transactions"]["window"] == ["2026-06-24", "2026-07-10"]
    ros_fp = tmp_path / "rosters_aaa_2026-07-09.jsonl"
    tx_fp = tmp_path / "transactions_2026-07-09.jsonl"
    rows = [json.loads(l) for l in ros_fp.read_text(encoding="ascii").splitlines()]
    assert rows[0]["player_id"] == 685382 and rows[0]["parent_org_id"] == 116
    assert rows[0]["as_of"] == "2026-07-09" and rows[0]["level"] == "aaa"
    txs = [json.loads(l) for l in tx_fp.read_text(encoding="ascii").splitlines()]
    # sportId 11 AND 1 both queried -> same fake row twice, tagged per sport
    assert {t["tx_sport_id"] for t in txs} == {1, 11}
    assert txs[0]["type_code"] == "REC"
    # second call: file-existence watermark -> CACHED, no refetch
    res2 = M.pull([11], **kw)
    assert res2["rosters"]["aaa"]["status"] == "CACHED"
    assert res2["transactions"]["status"] == "CACHED"


def test_pull_rejects_unknown_sport_id(tmp_path: Path):
    with pytest.raises(ValueError):
        M.pull([2], as_of="2026-07-09", http=_fake_http, out_dir=tmp_path,
               log_path=tmp_path / "log.txt", delay_s=0.0)


def test_join_rate_unit(tmp_path: Path):
    pd = pytest.importorskip("pandas")
    ros_fp = tmp_path / "rosters_aaa_2026-07-09.jsonl"
    with open(ros_fp, "w", encoding="ascii") as f:
        for pid in (100, 200, 300, 400):
            f.write(json.dumps({"player_id": pid}) + "\n")
    pd.DataFrame({"batter": [100, 999]}).to_parquet(tmp_path / "batter_pitch_profiles.parquet")
    pd.DataFrame({"pitcher": [200, 888]}).to_parquet(tmp_path / "pitcher_pitch_profiles.parquet")
    out = M.join_rate_vs_savant(ros_fp, matchup_dir=tmp_path)
    assert out["status"] == "OK"
    assert out["n_joined"] == 2 and out["join_rate"] == 0.5


def test_debut_watch_unit(tmp_path: Path):
    pd = pytest.importorskip("pandas")
    ros_fp = tmp_path / "rosters_aaa_2026-07-09.jsonl"
    with open(ros_fp, "w", encoding="ascii") as f:
        for pid, name in ((100, "Has Profile"), (200, "Debut One"), (300, "Debut Two")):
            f.write(json.dumps({"player_id": pid, "player_name": name}) + "\n")
    profiles_fp = tmp_path / "mlb_player_profiles.parquet"
    pd.DataFrame({"entity_id": [100, 100, 999]}).to_parquet(profiles_fp)
    out = M.debut_watch(ros_fp, profiles_fp=profiles_fp)
    assert out["status"] == "OK"
    assert out["as_of"] == "2026-07-09"
    assert out["n_milb_rostered"] == 3
    assert out["n_with_mlb_profile"] == 1
    assert out["n_debut_candidates"] == 2
    assert set(out["debut_candidate_sample"]) == {"Debut One", "Debut Two"}


def test_debut_watch_no_roster(tmp_path: Path):
    out = M.debut_watch(tmp_path / "missing.jsonl", profiles_fp=tmp_path / "missing.parquet")
    assert out["status"] == "NO_ROSTER"


def test_debut_watch_no_profiles_store(tmp_path: Path):
    ros_fp = tmp_path / "rosters_aaa_2026-07-09.jsonl"
    with open(ros_fp, "w", encoding="ascii") as f:
        f.write(json.dumps({"player_id": 100, "player_name": "X"}) + "\n")
    out = M.debut_watch(ros_fp, profiles_fp=tmp_path / "missing.parquet")
    assert out["status"] == "NO_PROFILES"


def test_join_rate_real_data_honest_rate():
    """The REAL join-rate check (MiLB ids vs savant-profile mlbam ids). Low is
    expected -- only AAA players with prior MLB pitch data can join."""
    pytest.importorskip("pandas")
    if M.latest_roster_fp() is None:
        pytest.skip("no pulled AAA roster on this box")
    if not (M._MATCHUP_DIR / "batter_pitch_profiles.parquet").exists():
        pytest.skip("no savant profile parquets on this box")
    out = M.join_rate_vs_savant()
    assert out["status"] == "OK"
    assert out["n_roster_ids"] > 500  # a real 30-team AAA capture
    assert 0.0 <= out["join_rate"] <= 1.0
    print("HONEST milb-vs-savant join rate: %s (%d/%d)"
          % (out["join_rate"], out["n_joined"], out["n_roster_ids"]))
