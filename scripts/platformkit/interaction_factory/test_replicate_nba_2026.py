"""Per-file test for scripts.platformkit.interaction_factory.replicate_nba_2026.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/interaction_factory/test_replicate_nba_2026.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.interaction_factory import replicate_nba_2026 as REPL


def test_verdict_rule():
    assert REPL.verdict_for(0.005, {"effect": 0.006, "p": 0.001, "n": 5000}) == "REPLICATED"
    assert REPL.verdict_for(0.005, {"effect": 0.004, "p": 0.20, "n": 400}) == "FAILED_REPLICATION_POWER_ANNOTATED"
    assert REPL.verdict_for(0.005, {"effect": -0.004, "p": 0.001, "n": 5000}) == "KILLED"
    assert REPL.verdict_for(0.005, None) == "NOT_TESTABLE"


def test_alpha_is_flat_bonferroni_k2():
    assert abs(REPL.ALPHA - (0.05 / 2.0)) < 1e-12


def test_pending_survivors_selects_only_unreplicated_family_rows():
    rows = [
        {"candidate_id": "nba_shot_attr_x_state::transition_efg__x__late_clock_efg",
         "template_id": REPL.TEMPLATE_ID, "verdict": "SURVIVES_PREREG_PROVISIONAL",
         "attr_a": "transition_efg", "attr_b": "late_clock_efg"},
        {"candidate_id": "nba_shot_attr_x_state::zone_efg_rim__x__late_clock_efg",
         "template_id": REPL.TEMPLATE_ID, "verdict": "SURVIVES_PREREG_PROVISIONAL",
         "attr_a": "zone_efg_rim", "attr_b": "late_clock_efg"},
        # already replicated -> excluded
        {"candidate_id": "nba_shot_attr_x_state::already_done", "template_id": REPL.TEMPLATE_ID,
         "verdict": "SURVIVES_PREREG_PROVISIONAL", "attr_a": "a", "attr_b": "b"},
        {"candidate_id": "repl_of_already_done", "template_id": REPL.TEMPLATE_ID,
         "verdict": "REPLICATED", "replication_of": "nba_shot_attr_x_state::already_done"},
        # different template / NULL verdict -> excluded
        {"candidate_id": "other_family::x", "template_id": "nba_shot_offense_x_offense",
         "verdict": "SURVIVES_PREREG_PROVISIONAL", "attr_a": "x", "attr_b": "y"},
        {"candidate_id": "nba_shot_attr_x_state::null_one", "template_id": REPL.TEMPLATE_ID,
         "verdict": "NULL", "attr_a": "c", "attr_b": "d"},
    ]
    pending = REPL._pending_survivors(rows)
    ids = {r["candidate_id"] for r in pending}
    assert ids == {
        "nba_shot_attr_x_state::transition_efg__x__late_clock_efg",
        "nba_shot_attr_x_state::zone_efg_rim__x__late_clock_efg",
    }


def test_replicate_appends_never_overwrites_and_stamps_replication_of(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    discovery_rows = [
        {"candidate_id": "nba_shot_attr_x_state::transition_efg__x__late_clock_efg",
         "template_id": REPL.TEMPLATE_ID, "verdict": "SURVIVES_PREREG_PROVISIONAL",
         "attr_a": "transition_efg", "attr_b": "late_clock_efg",
         "effect": 0.006646, "p": 0.000679, "n": 14044},
        {"candidate_id": "nba_shot_attr_x_state::zone_efg_rim__x__late_clock_efg",
         "template_id": REPL.TEMPLATE_ID, "verdict": "SURVIVES_PREREG_PROVISIONAL",
         "attr_a": "zone_efg_rim", "attr_b": "late_clock_efg",
         "effect": 0.005705, "p": 0.006111, "n": 14415},
    ]
    with ledger.open("w", encoding="ascii") as fh:
        for r in discovery_rows:
            fh.write(json.dumps(r) + "\n")

    monkeypatch.setattr(REPL.IFR, "nba_source_for_season", lambda season: tmp_path / "missing.parquet")
    verdicts_path = tmp_path / "verdicts.json"
    monkeypatch.setattr(REPL, "VERDICTS_PATH", verdicts_path)

    out = REPL.replicate(ledger_path=ledger, season="2024_25")
    assert len(out) == 2  # both pending candidates get a row, missing corpus -> honest NOT_TESTABLE
    assert {r["verdict"] for r in out} == {"NOT_TESTABLE"}
    assert {r["replication_of"] for r in out} == {r["candidate_id"] for r in discovery_rows}

    persisted = [json.loads(l) for l in ledger.read_text(encoding="ascii").splitlines()]
    assert len(persisted) == 4  # 2 discovery rows untouched + 2 appended replication rows
    assert persisted[0] == discovery_rows[0]
    assert persisted[1] == discovery_rows[1]

    assert verdicts_path.exists()
    saved = json.loads(verdicts_path.read_text(encoding="ascii"))
    for r in discovery_rows:
        assert saved[r["candidate_id"]]["verdict"] == "NOT_TESTABLE"

    # a second call finds nothing pending (both candidates now have a replication_of pointer)
    out2 = REPL.replicate(ledger_path=ledger, season="2024_25")
    assert out2 == []
