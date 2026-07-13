"""Per-file test for scripts.platformkit.interaction_factory.replicate_reserve.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/interaction_factory/test_replicate_reserve.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit.interaction_factory import generator as GEN
from scripts.platformkit.interaction_factory import reserve as RESERVE
from scripts.platformkit.interaction_factory import replicate_reserve as RR


# --------------------------------------------------------------------------
# trap test: reserve_slice is the exact complement of reserve_mask's discovery
# slice -- disjoint rows, union recovers the input frame.
def test_season_axis_discovery_and_reserve_are_disjoint_and_cover_frame():
    frame = pd.DataFrame({
        "entity_id": [1, 2, 3, 4, 5],
        "season": [2022, 2022, 2023, 2023, 2024],
        "y": [0.1, 0.2, 0.3, 0.4, 0.5],
    })
    discovery, disc_name = RESERVE.reserve_mask(frame)
    reserve, res_name = RR.reserve_slice(frame)
    assert disc_name == res_name == "2023"
    assert set(discovery["entity_id"]).isdisjoint(set(reserve["entity_id"]))
    assert set(discovery["entity_id"]) | set(reserve["entity_id"]) == set(frame["entity_id"])
    assert len(discovery) + len(reserve) == len(frame)


def test_date_axis_discovery_and_reserve_are_disjoint_and_cover_frame():
    frame = pd.DataFrame({
        "game_id": list(range(8)),
        "game_date": pd.to_datetime(["2025-01-0%d" % (i + 1) for i in range(8)]),
        "y": [float(i) for i in range(8)],
    })
    discovery, disc_name = RESERVE.reserve_mask(frame)
    reserve, res_name = RR.reserve_slice(frame)
    assert disc_name == res_name == "trailing_25pct_by_game_date"
    assert set(discovery["game_id"]).isdisjoint(set(reserve["game_id"]))
    assert set(discovery["game_id"]) | set(reserve["game_id"]) == set(frame["game_id"])
    assert len(reserve) == 2  # trailing 25% of 8


def test_no_time_axis_reserve_slice_is_empty():
    frame = pd.DataFrame({"player_id": [1, 2, 3], "y": [1.0, 2.0, 3.0]})
    reserve, name = RR.reserve_slice(frame)
    assert name is None
    assert len(reserve) == 0


def test_single_season_reserve_slice_is_empty_r5():
    frame = pd.DataFrame({"season": [2024, 2024], "y": [0.1, 0.2]})
    reserve, name = RR.reserve_slice(frame)
    assert name is None
    assert len(reserve) == 0


# --------------------------------------------------------------------------
# pending selection
def _row(cid, tid, verdict="SURVIVES_PREREG_PROVISIONAL", reserved_corpus="2023",
         attr_a="a", attr_b="b", effect=0.01, p=0.001, n=1000, replication_of=None):
    row = {"candidate_id": cid, "template_id": tid, "verdict": verdict,
           "attr_a": attr_a, "attr_b": attr_b, "effect": effect, "p": p, "n": n}
    if reserved_corpus is not None:
        row["reserved_corpus"] = reserved_corpus
    if replication_of is not None:
        row["replication_of"] = replication_of
    return row


def test_pending_selection_requires_nonnull_reserved_corpus():
    rows = [
        _row("t::a__x__b", "tpl", reserved_corpus="2023"),          # pending
        _row("t::c__x__d", "tpl", reserved_corpus=None),            # no reserve -> excluded
        _row("t::e__x__f", "tpl", reserved_corpus="2023",
             verdict="NULL"),                                        # not a survivor -> excluded
        {"candidate_id": "repl_of_a", "template_id": "tpl", "verdict": "REPLICATED",
         "replication_of": "t::a__x__b", "reserved_corpus": None},   # already replicated
    ]
    pending = RR._pending_reserved_survivors(rows)
    ids = {r["candidate_id"] for r in pending}
    assert ids == set()  # the only otherwise-eligible row (t::a__x__b) already has replication_of below

    # remove the already-replicated blocker and re-check the positive case in isolation
    rows2 = [_row("t::a__x__b", "tpl", reserved_corpus="2023")]
    pending2 = RR._pending_reserved_survivors(rows2)
    assert [r["candidate_id"] for r in pending2] == ["t::a__x__b"]


def test_no_pending_reserved_survivors_is_noop(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps(_row("t::a__x__b", "tpl", reserved_corpus=None)) + "\n", encoding="ascii")
    out = RR.replicate(ledger_path=ledger)
    assert out == []


# --------------------------------------------------------------------------
# verdict vocabulary
def test_verdict_vocabulary():
    assert RR.verdict_for(0.01, None, 0.05) == "NOT_TESTABLE"
    assert RR.verdict_for(0.01, {"effect": -0.02, "p": 0.001}, 0.05) == "KILLED"
    assert RR.verdict_for(0.01, {"effect": 0.02, "p": 0.001}, 0.05) == "REPLICATED"
    assert RR.verdict_for(0.01, {"effect": 0.02, "p": 0.5}, 0.05) == "FAILED_REPLICATION_POWER_ANNOTATED"


# --------------------------------------------------------------------------
# end-to-end: a real template with a registered builder but no reserved
# survivor on record (the honest STEP-0 state today) -> no-op, and a synthetic
# reserved survivor whose template has no builder -> honest NOT_TESTABLE row.
def test_replicate_unbuildable_template_appends_not_testable(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    tpl_id = next(iter(GEN.TEMPLATES))  # any real template id (attrs won't match its builder -> NOT_TESTABLE)
    row = _row("%s::zzz__x__yyy" % tpl_id, tpl_id, reserved_corpus="2023",
                attr_a="zzz_nonexistent", attr_b="yyy_nonexistent")
    ledger.write_text(json.dumps(row) + "\n", encoding="ascii")

    out = RR.replicate(ledger_path=ledger)
    assert len(out) == 1
    assert out[0]["verdict"] == "NOT_TESTABLE"
    assert out[0]["replication_of"] == row["candidate_id"]
    assert out[0]["replication_season"] == "2023"

    persisted = [json.loads(l) for l in ledger.read_text(encoding="ascii").splitlines()]
    assert len(persisted) == 2  # discovery row untouched + 1 appended replication row

    # a second call finds nothing pending (replication_of now points at it)
    out2 = RR.replicate(ledger_path=ledger)
    assert out2 == []
