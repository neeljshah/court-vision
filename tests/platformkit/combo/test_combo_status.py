"""tests.platformkit.combo.test_combo_status -- non-fabricable block + jsonl records.

The combo block is read BACK from on-disk jsonl tails: it cannot claim a proposal that was
not written, an empty/missing source reads DEGRADED (never green), and a STALE/DEGRADED last
cycle reads DEGRADED. Per-file test only. ASCII; stdlib deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.combo import combo_status as ST  # noqa: E402
from scripts.platformkit.combo.combination_families import CombinationSpec  # noqa: E402
from scripts.platformkit.combo.combo_runner import ComboCycleResult  # noqa: E402


def _spec():
    return CombinationSpec("COMB_DETAIL_x_DETAIL", "nba", "winprob",
                           "comb_detail_x_detail=a:pace|b:run_diff",
                           {"a": "pace", "b": "run_diff"})


def test_missing_source_reads_degraded_never_green(tmp_path):
    blk = ST.combo_block(status_path=str(tmp_path / "none.jsonl"))
    assert blk["severity"] == ST.DEGRADED
    assert blk["n_proposals"] == 0
    assert blk["proposal_only"] is True


def test_proposal_and_reject_records_are_counted(tmp_path):
    pp = tmp_path / "prop.jsonl"
    rp = tmp_path / "rej.jsonl"
    sp = tmp_path / "stat.jsonl"
    res = ComboCycleResult(sport="nba", decision="PROPOSED", status="FRESH_NEW",
                           n_proposed=1, n_rejected=2)
    res.proposals = [ST.proposal_row(_spec(), {"n_clean": 9}, {"verdict": "SHIP", "layer": "L6"})]
    res.rejects = [ST.reject_lesson(_spec(), verdict="REJECT", reason="L5", layer="L5", k=3),
                   ST.reject_lesson(_spec(), verdict="REJECT", reason="L0", layer="L0", k=3)]
    ST.record_cycle(res, pp, rp, sp, now=1.0)
    blk = ST.combo_block(proposals_path=str(pp), reject_path=str(rp), status_path=str(sp))
    assert blk["n_proposals"] == 1
    assert blk["n_reject_lessons"] == 2
    assert blk["last_decision"] == "PROPOSED"
    assert blk["severity"] == ST.OK
    # NO market-edge CLAIM: no literal $ amount nor an roi token (the disclaimer string
    # "calibration, not edge" legitimately contains the word "edge", so we don't ban it).
    txt = (pp.read_text() + rp.read_text() + sp.read_text())
    assert "$" not in txt
    assert "roi" not in txt.lower()
    assert "UNPROVEN" in pp.read_text()  # every proposal carries the calibration-only flag


def test_degraded_cycle_block_reads_degraded(tmp_path):
    sp = tmp_path / "stat.jsonl"
    res = ComboCycleResult(sport="nba", decision="DEGRADED", status="STALE")
    ST.record_status(res, sp, now=2.0)
    blk = ST.combo_block(status_path=str(sp))
    assert blk["severity"] == ST.DEGRADED
    assert blk["last_status"] == "STALE"
