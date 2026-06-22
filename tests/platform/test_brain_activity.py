"""Tests for the live-activity brain hubs (activity_sources + brain_activity).

Uses a hermetic tmp tree + synthetic on-disk stores that deliberately contain a
player name, a matchup, and a dollar figure -- the renderer must aggregate them away
(person-free, units-only) and never emit them. Honest-empty path is covered too.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.activity_sources import collect_activity
from scripts.platformkit.brain_activity import build_activity
from scripts.platformkit.graph_cleanliness import scan_vault
from scripts.platformkit.vault_person_free_lint import lint_vault


def _organized(root: Path) -> Path:
    org = root / "vault" / "_Organized"
    for sp in ("NBA", "MLB", "Soccer", "Tennis"):
        (org / sp).mkdir(parents=True, exist_ok=True)
        (org / sp / "_Index.md").write_text(f"# {sp} Index\n", encoding="utf-8")
    (org / "NBA" / "_Model_Card.md").write_text("# card\n", encoding="utf-8")
    return org


def _stores(root: Path) -> None:
    fe = root / "data" / "frontend"
    (fe / "ops").mkdir(parents=True, exist_ok=True)
    (fe / "ingame").mkdir(parents=True, exist_ok=True)
    (fe / "ops" / "supervisor_status.json").write_text(json.dumps({
        "profile": "prod", "updated_at": "2026-06-22T18:00:00Z", "all_ready": True,
        "procs": [{"name": "m1_paper", "state": "READY", "ready": True, "restarts": 0},
                  {"name": "m2_inplay", "state": "READY", "ready": True, "restarts": 1}],
    }), encoding="utf-8")
    (fe / "ops" / "autonomy_status.json").write_text(json.dumps({
        "overall": "ok", "idle_reason": "waiting on slate",
        "ratchet": {"state": "IDLE", "n_ships": 0},
        "high_water": {"mlb": {"last_decision": "NO_CANDIDATE", "n_seen": 12},
                       "soccer_intl": {"last_decision": "NO_CANDIDATE", "n_seen": 3}},
    }), encoding="utf-8")
    (fe / "ingame" / "_heartbeat.json").write_text(json.dumps({
        "as_of": "2026-06-22T18:00:00Z", "n_live": 1,
        "per_sport": {"soccer_intl": {"n_live": 1}, "mlb": {"n_live": 0}},
    }), encoding="utf-8")
    (fe / "grade_summary.json").write_text(json.dumps({
        "as_of": "2026-06-22T18:00:00Z", "n_settled": 16, "n_clv": 15,
        "mean_clv_pct": -0.204, "pct_beat_close": 18.75, "n_proxy_close": 1,
        "flat_unit_wins": 5, "flat_unit_losses": 11,
        "by_sport": {"mlb": {"n_settled": 16, "n_clv": 15, "mean_clv_pct": -0.204,
                             "pct_beat_close": 18.75, "flat_unit_wins": 5,
                             "flat_unit_losses": 11}},
    }), encoding="utf-8")
    (fe / "improve_ledger.jsonl").write_text(
        json.dumps({"ts": "2026-06-22T01:00:00Z", "sport": "nba", "n_settled": 0,
                    "verdict": "INSUFFICIENT_DATA", "reason": "cold"}) + "\n",
        encoding="utf-8")
    (fe / "prop_improve_ledger.jsonl").write_text(
        json.dumps({"ts": "2026-06-22T02:00:00Z", "sport": "mlb", "n_settled": 0,
                    "verdict": "INSUFFICIENT_DATA", "reason": "cold"}) + "\n",
        encoding="utf-8")
    (fe / "prop_history_meta.json").write_text(json.dumps({
        "n_history_folds": 6, "min_replication": 2,
        "groups": [{"sport": "mlb", "stat": "all", "n_folds": 4,
                    "replicated_verdict": "SHIP_REPLICATED", "median_delta_brier": 0.0099,
                    "any_planted_null_leak": False}],
    }), encoding="utf-8")
    # clv_ledger rows deliberately carry a player name, a matchup, and a dollar figure
    rows = [
        {"sport": "soccer_intl", "channel": "paper", "market_type": "prop",
         "status": "open", "prop_player": "Lionel Messi",
         "matchup": "Argentina vs Austria", "stake_dollars": 500},
        {"sport": "mlb", "channel": "paper", "market_type": "prop", "status": "settled",
         "prop_player": "Aaron Judge", "matchup": "Yankees vs Reds"},
        {"sport": "mlb", "channel": "paper_ingame", "market_type": "moneyline",
         "status": "open", "matchup": "Reds vs Yankees"},
    ]
    (fe / "clv_ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# ---- forbidden tokens that must NEVER reach a rendered note --------------------
_FORBIDDEN = ("Messi", "Judge", "Argentina", "Austria", "Yankees", "Reds",
              " vs ", "$", "500", "stake_dollars")


def _all_notes_text(org: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8")
                     for p in sorted(org.rglob("_Activity*.md"))
                     + sorted(org.rglob("_Whats_Happening.md")))


def test_collect_is_person_free_and_aggregated(tmp_path):
    _stores(tmp_path)
    act = collect_activity(tmp_path)
    assert act["machinery_ready"] is True
    assert act["paper"]["n_ingame"] == 1
    assert act["paper"]["by_sport"]["mlb"]["channel:paper_ingame"] == 1
    blob = json.dumps(act)
    for tok in ("Messi", "Judge", "Argentina", "Yankees", "stake_dollars", "matchup"):
        assert tok not in blob, f"leaked {tok} into the snapshot"


def test_build_writes_backbone_hubs(tmp_path):
    org = _organized(tmp_path)
    _stores(tmp_path)
    rep = build_activity(organized_root=org, repo_root=tmp_path)
    assert (org / "_Index" / "_Whats_Happening.md").is_file()
    for sp in ("NBA", "MLB", "Soccer", "Tennis"):
        assert (org / sp / "_Activity.md").is_file()
    assert rep["n_written"] == 5


def test_notes_are_person_free_units_only(tmp_path):
    org = _organized(tmp_path)
    _stores(tmp_path)
    build_activity(organized_root=org, repo_root=tmp_path)
    text = _all_notes_text(org)
    for tok in _FORBIDDEN:
        assert tok not in text, f"forbidden token {tok!r} reached a note"
    # gates: no player/match NODES, person-free lint clean
    scan = scan_vault(org)
    assert scan["player_nodes"] == 0 and scan["match_nodes"] == 0
    lint = lint_vault(org)
    assert lint["person_free"] is True, lint["leak_counts"]


def test_master_links_down_and_hubs_present(tmp_path):
    org = _organized(tmp_path)
    _stores(tmp_path)
    build_activity(organized_root=org, repo_root=tmp_path)
    master = (org / "_Index" / "_Whats_Happening.md").read_text(encoding="utf-8")
    # links DOWN to each per-sport activity note + the existing cross-sport hubs
    for sp in ("NBA", "MLB", "Soccer", "Tennis"):
        assert f"[[{sp}/_Activity" in master
    assert "[[_Calibration_Scoreboard" in master
    # live sections rendered from the stores
    assert "SHIP_REPLICATED" in master
    assert "paper_ingame" in master
    assert "m1_paper" in master
    # honest banner present (audit banner coverage) + no edge claim
    assert "calibration is not edge" in master


def test_honest_empty_when_no_stores(tmp_path):
    org = _organized(tmp_path)  # no data/frontend at all
    rep = build_activity(organized_root=org, repo_root=tmp_path)
    assert rep["n_written"] == 5
    master = (org / "_Index" / "_Whats_Happening.md").read_text(encoding="utf-8")
    assert "stack not running" in master  # honest-empty services section
    nba = (org / "NBA" / "_Activity.md").read_text(encoding="utf-8")
    assert "no live activity" in nba.lower() or "honest-empty" in nba.lower()


def test_sport_note_links_model_card_only_when_present(tmp_path):
    org = _organized(tmp_path)
    _stores(tmp_path)
    build_activity(organized_root=org, repo_root=tmp_path)
    nba = (org / "NBA" / "_Activity.md").read_text(encoding="utf-8")
    mlb = (org / "MLB" / "_Activity.md").read_text(encoding="utf-8")
    assert "[[NBA/_Model_Card" in nba          # NBA has a model card fixture
    assert "[[MLB/_Model_Card" not in mlb       # MLB has none -> not linked
