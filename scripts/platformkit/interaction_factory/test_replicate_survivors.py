"""Per-file test for scripts.platformkit.interaction_factory.replicate_survivors.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/interaction_factory/test_replicate_survivors.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.interaction_factory import replicate_survivors as REPL


def test_verdict_rule():
    # same sign, well below the flat K=6 Bonferroni bar -> REPLICATED
    assert REPL.verdict_for(0.005, {"effect": 0.006, "p": 0.0001, "n": 5000}) == "REPLICATED"
    # same sign, above the bar -> FAILED_REPLICATION_POWER_ANNOTATED (a power miss, not a kill)
    assert REPL.verdict_for(0.005, {"effect": 0.004, "p": 0.20, "n": 400}) == "FAILED_REPLICATION_POWER_ANNOTATED"
    # sign flip -> KILLED
    assert REPL.verdict_for(0.005, {"effect": -0.004, "p": 0.001, "n": 5000}) == "KILLED"
    # unbuildable -> NOT_TESTABLE
    assert REPL.verdict_for(0.005, None) == "NOT_TESTABLE"


def test_alpha_is_flat_bonferroni_k6():
    # eps_eff(0.05, 6) -- a FIXED bar, not batch-1's sequential-tightening.
    assert abs(REPL.ALPHA - (0.05 / 6.0)) < 1e-12


def test_replicate_appends_never_overwrites(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    b1_rows = [
        {"candidate_id": "nba_shot_offense_x_offense::halfcourt_efg__x__late_clock_efg",
         "template_id": REPL.TEMPLATE_ID, "verdict": "SURVIVES_PREREG_PROVISIONAL",
         "attr_a": "halfcourt_efg", "attr_b": "late_clock_efg",
         "effect": 0.0052, "p": 0.0006, "n": 15697},
    ]
    for r in b1_rows:
        ledger.write_text(json.dumps(r) + "\n", encoding="ascii")

    monkeypatch.setattr(REPL.IFR, "nba_source_for_season", lambda season: tmp_path / "missing.parquet")
    verdicts_path = tmp_path / "verdicts.json"
    monkeypatch.setattr(REPL, "VERDICTS_PATH", verdicts_path)

    out = REPL.replicate(ledger_path=ledger, season="2024_25")
    assert len(out) == 1
    assert out[0]["verdict"] == "NOT_TESTABLE"  # source missing -> honest NOT_TESTABLE, not a crash

    persisted = [json.loads(l) for l in ledger.read_text(encoding="ascii").splitlines()]
    assert len(persisted) == 2  # batch-1 row untouched + one appended replication row
    assert persisted[0] == b1_rows[0]  # batch-1 row byte-identical, never overwritten
    assert persisted[1]["replication_of"] == b1_rows[0]["candidate_id"]

    assert verdicts_path.exists()
    saved = json.loads(verdicts_path.read_text(encoding="ascii"))
    assert saved[b1_rows[0]["candidate_id"]]["verdict"] == "NOT_TESTABLE"
