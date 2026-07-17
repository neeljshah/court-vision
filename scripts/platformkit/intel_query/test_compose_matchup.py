"""Per-file tests for compose_matchup (matchup-preview fan-out composer).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_query/test_compose_matchup.py -q

Sub-resolvers are monkeypatched at the module level compose_matchup imports
them into -- covers: full assembly with every block "ok", one sub-resolver
returning no_data leaves that block (and only that block) absent while the
overall preview still reports status "ok", and the CLI entrypoint.
"""
from __future__ import annotations

import json

from scripts.platformkit.intel_query import ask as ask_mod
from scripts.platformkit.intel_query import compose_matchup as cm


def _ok(category, **extra):
    return {"status": "ok", "category": category, **extra}


def _stub_all_ok(monkeypatch):
    monkeypatch.setattr(cm, "winprob_dispatch", lambda sport, home, away: _ok("winprob", p_home_win=0.55))
    monkeypatch.setattr(cm, "_team_profile_block", lambda sport, team, top_n=10: _ok("team_profile_summary", team=team))
    monkeypatch.setattr(cm, "_style_matchup_block", lambda sport: _ok("style_matchup", claim_id="x"))
    monkeypatch.setattr(cm, "injury_report", lambda sport, team=None, player=None: _ok("edge_facts_injury_report", team=team))
    monkeypatch.setattr(cm, "schedule_resolve", lambda sport, team, date=None: _ok("schedule_context", team=team))


def test_all_blocks_ok(monkeypatch):
    _stub_all_ok(monkeypatch)
    result = cm.compose_matchup("mlb", "NYY", "BOS")
    assert result["status"] == "ok"
    assert result["category"] == "matchup_preview"
    assert set(result["blocks"]) == {
        "win_prob", "home_profile", "away_profile", "style_matchup",
        "home_injury_report", "away_injury_report",
        "home_schedule_context", "away_schedule_context",
    }
    assert sorted(result["blocks_ok"]) == sorted(result["blocks"])
    assert result["blocks_absent"] == []
    assert result["home"] == "NYY" and result["away"] == "BOS"
    # every block cited verbatim, not re-derived
    assert result["blocks"]["win_prob"]["p_home_win"] == 0.55


def test_one_subresolver_no_data_leaves_only_that_block_absent(monkeypatch):
    _stub_all_ok(monkeypatch)
    monkeypatch.setattr(cm, "injury_report", lambda sport, team=None, player=None:
                         {"status": "no_data", "category": "edge_facts_injury_report",
                          "note": "injury facts store not built in this clone"})
    result = cm.compose_matchup("mlb", "NYY", "BOS")
    assert result["status"] == "ok"  # overall preview never fails on a block miss
    assert "home_injury_report" in result["blocks_absent"]
    assert "away_injury_report" in result["blocks_absent"]
    assert "win_prob" in result["blocks_ok"]
    assert result["blocks"]["home_injury_report"]["status"] == "no_data"


def test_style_matchup_not_supported_for_unwired_sport():
    result = cm._style_matchup_block("mlb")
    assert result["status"] == "not_supported"
    assert result["sport"] == "mlb"


def test_style_block_never_reads_other_stores(tmp_path, monkeypatch):
    """P0 proof: a bare load_verified_claims() whole-loads every *.jsonl under
    data/cache/intel_claims/ (nba_player_box_rate is 2.8GB / 59k VERIFIED
    rows) just to keep the tiny nba_lineup_* style family -- the 6.1GB-RSS
    incident on resolve('matchup preview ...'). _style_matchup_block must
    route through pairs_for_claim_stores so a decoy 'fat' store sitting right
    next to it is NEVER opened."""
    style_path = tmp_path / "nba_lineup_synergy_claims.jsonl"
    style_validation = tmp_path / "nba_lineup_synergy_claims_validation.json"
    decoy_path = tmp_path / "nba_player_box_rate.jsonl"
    decoy_validation = tmp_path / "nba_player_box_rate_validation.json"

    style_path.write_text(json.dumps(
        {"claim_id": "nba_lineup_synergy_pair_v1", "kind": "ranking",
         "criteria": {"metric": "synergy", "window": "season"},
         "computed_at": "2026-07-01T00:00:00+00:00",
         "ranking": [{"pairing_key": "High_vs_Low", "value": 1.2, "rank": 1}]}) + "\n",
        encoding="ascii")
    style_validation.write_text(json.dumps(
        {"details": [{"claim_id": "nba_lineup_synergy_pair_v1", "verdict": "VERIFIED"}]}), encoding="ascii")

    decoy_path.write_text(json.dumps({"claim_id": "decoy_fat_claim", "kind": "ranking"}) + "\n", encoding="ascii")
    decoy_validation.write_text(json.dumps(
        {"details": [{"claim_id": "decoy_fat_claim", "verdict": "VERIFIED"}]}), encoding="ascii")

    monkeypatch.setattr(ask_mod, "CLAIM_SOURCE_PAIRS", (
        (style_validation, style_path),
        (decoy_validation, decoy_path),
    ))

    opened = []
    real_load_jsonl = ask_mod._load_jsonl

    def _tracking_load_jsonl(path, max_lines=None):
        opened.append(path)
        return real_load_jsonl(path, max_lines)

    monkeypatch.setattr(ask_mod, "_load_jsonl", _tracking_load_jsonl)

    out = cm._style_matchup_block("nba")

    assert style_path in opened
    assert decoy_path not in opened            # the declared-store scope, proven
    assert out["status"] == "ok"
    assert out["claim_id"] == "nba_lineup_synergy_pair_v1"


def test_team_profile_block_no_parquet_is_no_data():
    result = cm._team_profile_block("mlb", "NYY", )
    # mlb_team_profiles.parquet is not built in this clone -> honest no_data
    assert result["status"] in ("no_data",)
    assert result["category"] == "team_profile_summary"


def test_main_cli_prints_json(monkeypatch, capsys):
    _stub_all_ok(monkeypatch)
    rc = cm.main(["mlb", "NYY", "BOS"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["category"] == "matchup_preview"
