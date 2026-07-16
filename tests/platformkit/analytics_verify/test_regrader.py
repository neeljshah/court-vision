"""Per-file tests for the claim survival regrader.

Covers HOLDS / DECAYED / INSUFFICIENT, idempotency, and the never-mutates-claims-engine
guarantee. All synthetic against tmp_path -- the real-data path is exercised only as a
smoke check that is skipped when files are absent.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/analytics_verify/test_regrader.py -q
"""
from __future__ import annotations

import json
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import pytest  # noqa: E402

from scripts.platformkit.analytics_verify import regrader as R  # noqa: E402


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _fixture(tmp_path, verdict="VALIDATED", scope="pregame"):
    ledger = tmp_path / "card_ledger.jsonl"
    cards = tmp_path / "cards.jsonl"
    ev_pre = tmp_path / "paper_graded.jsonl"
    ev_in = tmp_path / "ingame_clv.jsonl"
    _write(ledger, [{"card_id": "c1", "verdict": verdict, "graded_at": "2026-01-01T00:00:00Z", "edge_claimed": False}])
    _write(cards, [{"card_id": "c1", "claim": "x", "expected_sign": "+",
                    "condition": {"entity": "game", "scope": scope, "sport": "nba"}, "status": "OPEN"}])
    return ledger, cards, ev_pre, ev_in


def _run(tmp_path, ledger, cards, ev_pre, ev_in, **kw):
    return R.run(
        ledger_path=ledger, cards_path=cards, ev_pregame=ev_pre, ev_ingame=ev_in,
        out_ledger=tmp_path / "regrade_ledger.jsonl", out_survival=tmp_path / "claim_survival.json", **kw,
    )


def test_holds(tmp_path):
    ledger, cards, ev_pre, ev_in = _fixture(tmp_path)
    # 30 post-validation rows, all positive CLV -> HOLDS at every horizon.
    _write(ev_pre, [{"sport": "nba", "settled_at": "2026-01-02T00:00:00Z", "clv_pct": 2.0} for _ in range(30)])
    snap = _run(tmp_path, ledger, cards, ev_pre, ev_in, min_n=25)
    assert snap["n_eligible"] == 1
    assert snap["survival"]["7d"] == 1.0 and snap["survival"]["60d"] == 1.0
    assert snap["decayed_cards"] == [] and snap["insufficient_cards"] == 0
    rows = list(R._iter_jsonl(tmp_path / "regrade_ledger.jsonl"))
    assert {r["regrade_verdict"] for r in rows} == {"HOLDS"}
    assert all(r["edge_claimed"] is False for r in rows)


def test_decayed(tmp_path):
    ledger, cards, ev_pre, ev_in = _fixture(tmp_path)
    # 30 post rows all negative CLV -> sign flip -> DECAYED.
    _write(ev_pre, [{"sport": "nba", "settled_at": "2026-01-02T00:00:00Z", "clv_pct": -3.0} for _ in range(30)])
    snap = _run(tmp_path, ledger, cards, ev_pre, ev_in, min_n=25)
    assert snap["survival"]["30d"] == 0.0
    assert len(snap["decayed_cards"]) == 1 and snap["decayed_cards"][0]["card_id"] == "c1"
    verds = {r["regrade_verdict"] for r in R._iter_jsonl(tmp_path / "regrade_ledger.jsonl")}
    assert verds == {"DECAYED"}


def test_insufficient(tmp_path):
    ledger, cards, ev_pre, ev_in = _fixture(tmp_path)
    _write(ev_pre, [{"sport": "nba", "settled_at": "2026-01-02T00:00:00Z", "clv_pct": 2.0} for _ in range(3)])
    snap = _run(tmp_path, ledger, cards, ev_pre, ev_in, min_n=25)
    assert snap["survival"]["7d"] is None  # nobody decided
    assert snap["insufficient_cards"] == 1
    verds = {r["regrade_verdict"] for r in R._iter_jsonl(tmp_path / "regrade_ledger.jsonl")}
    assert verds == {"INSUFFICIENT"}


def test_only_post_graded_evidence_counts(tmp_path):
    ledger, cards, ev_pre, ev_in = _fixture(tmp_path)
    # Rows settled BEFORE graded_at must be ignored -> stays insufficient.
    _write(ev_pre, [{"sport": "nba", "settled_at": "2025-06-01T00:00:00Z", "clv_pct": 2.0} for _ in range(40)])
    snap = _run(tmp_path, ledger, cards, ev_pre, ev_in, min_n=25)
    assert snap["insufficient_cards"] == 1


def test_ingame_scope_linkage(tmp_path):
    ledger, cards, ev_pre, ev_in = _fixture(tmp_path, scope="ingame")
    _write(ev_in, [{"bet_id": f"nba|G|win_home|home|paper_ingame|2026-02-0{(i % 9) + 1}",
                    "sport": "nba", "ingame_realized_clv_300s": 1.5} for i in range(30)])
    snap = _run(tmp_path, ledger, cards, ev_pre, ev_in, min_n=25)
    assert snap["survival"]["60d"] == 1.0
    assert {r["link_method"] for r in R._iter_jsonl(tmp_path / "regrade_ledger.jsonl")} == {"condition_match"}


def test_claim_tags_link_method(tmp_path):
    ledger, cards, ev_pre, ev_in = _fixture(tmp_path)
    _write(ev_pre, [{"sport": "other", "settled_at": "2026-01-02T00:00:00Z", "clv_pct": 1.0,
                     "claim_tags": ["c1"]} for _ in range(30)])
    snap = _run(tmp_path, ledger, cards, ev_pre, ev_in, min_n=25)
    # tag match overrides the sport mismatch
    assert {r["link_method"] for r in R._iter_jsonl(tmp_path / "regrade_ledger.jsonl")} == {"claim_tags"}
    assert snap["survival"]["7d"] == 1.0


def test_claim_tags_dict_shape(tmp_path):
    # real clv_ledger.jsonl rows carry claim_tags as {card_id: fired_bool}, not a list.
    ledger, cards, ev_pre, ev_in = _fixture(tmp_path)
    _write(ev_pre, [{"sport": "other", "settled_at": "2026-01-02T00:00:00Z", "clv_pct": 1.0,
                     "claim_tags": {"c1": True, "other_card": False}} for _ in range(30)])
    snap = _run(tmp_path, ledger, cards, ev_pre, ev_in, min_n=25)
    assert {r["link_method"] for r in R._iter_jsonl(tmp_path / "regrade_ledger.jsonl")} == {"claim_tags"}
    assert snap["survival"]["7d"] == 1.0


def test_zero_eligible_when_no_positive_verdict(tmp_path):
    ledger, cards, ev_pre, ev_in = _fixture(tmp_path, verdict="REJECTED")
    _write(ev_pre, [{"sport": "nba", "settled_at": "2026-01-02T00:00:00Z", "clv_pct": 2.0} for _ in range(30)])
    snap = _run(tmp_path, ledger, cards, ev_pre, ev_in)
    assert snap["n_eligible"] == 0 and snap["_rows_appended"] == 0
    assert snap["survival"]["7d"] is None


def test_idempotent_same_day(tmp_path):
    ledger, cards, ev_pre, ev_in = _fixture(tmp_path)
    _write(ev_pre, [{"sport": "nba", "settled_at": "2026-01-02T00:00:00Z", "clv_pct": 2.0} for _ in range(30)])
    _run(tmp_path, ledger, cards, ev_pre, ev_in)
    n1 = sum(1 for _ in R._iter_jsonl(tmp_path / "regrade_ledger.jsonl"))
    snap2 = _run(tmp_path, ledger, cards, ev_pre, ev_in)
    n2 = sum(1 for _ in R._iter_jsonl(tmp_path / "regrade_ledger.jsonl"))
    assert n1 == n2 == len(R.HORIZONS)
    assert snap2["_rows_appended"] == 0


def test_never_mutates_claims_engine_files(tmp_path):
    ledger, cards, ev_pre, ev_in = _fixture(tmp_path)
    _write(ev_pre, [{"sport": "nba", "settled_at": "2026-01-02T00:00:00Z", "clv_pct": -3.0} for _ in range(30)])
    before_l = ledger.read_bytes()
    before_c = cards.read_bytes()
    before_e = ev_pre.read_bytes()
    _run(tmp_path, ledger, cards, ev_pre, ev_in)
    assert ledger.read_bytes() == before_l
    assert cards.read_bytes() == before_c
    assert ev_pre.read_bytes() == before_e


def test_no_dollar_tokens_in_output(tmp_path):
    ledger, cards, ev_pre, ev_in = _fixture(tmp_path)
    _write(ev_pre, [{"sport": "nba", "settled_at": "2026-01-02T00:00:00Z", "clv_pct": 2.0} for _ in range(30)])
    snap = _run(tmp_path, ledger, cards, ev_pre, ev_in)
    # every emitted row + the snapshot flag must carry edge_claimed=False (no $ claims).
    assert snap["edge_claimed"] is False
    rows = list(R._iter_jsonl(tmp_path / "regrade_ledger.jsonl"))
    assert rows and all(r.get("edge_claimed") is False for r in rows)
    # numeric data rows carry no dollar/roi/bankroll tokens (prose honest_note is exempt).
    low = "".join(json.dumps({k: v for k, v in r.items() if k != "reason"}) for r in rows).lower()
    for banned in ("roi", "$", "bankroll", "pnl", "profit", '"edge_claimed": true'):
        assert banned not in low


def test_real_data_smoke():
    if not R.CARD_LEDGER.exists() or not R.CARDS.exists():
        pytest.skip("claims engine files absent")
    total, elig = R._eligible_cards(R.CARD_LEDGER, R.CARDS)
    assert total >= 0 and isinstance(elig, list)
