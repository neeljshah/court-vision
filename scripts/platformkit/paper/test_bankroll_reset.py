"""Per-file test for the reversible paper-bankroll reset.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/paper/test_bankroll_reset.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.paper import bankroll_reset as R


def _seed(fe):
    (fe / "clv_ledger.jsonl").write_text(
        '{"bet_id":"a","status":"settled","unit_result":-1.0}\n', encoding="ascii")
    (fe / "paper_bankroll.json").write_text(
        json.dumps({"start_units": 100.0, "current_units": -2.0}), encoding="ascii")
    (fe / "paper_pnl_series.json").write_text("{}", encoding="ascii")


def test_reset_archives_and_reinits(tmp_path):
    fe = tmp_path / "frontend"
    fe.mkdir()
    arch = fe / "_ledger_archive"
    _seed(fe)
    out = R.reset(100.0, frontend=fe, archive_root=arch)
    # clean slate
    assert out["start_units"] == 100.0
    assert out["current_units"] == 100.0
    # the old settled ledger was MOVED (reversibly), not left to re-bleed
    assert not (fe / "clv_ledger.jsonl").exists()
    assert (out["archived"] and "clv_ledger.jsonl" in out["archived"])
    assert (fe / "paper_bankroll.json").exists()        # reinitialised
    cfg = json.loads((fe / "paper_bankroll.json").read_text(encoding="ascii"))
    assert cfg["current_units"] == 100.0
    # archive holds the preserved (reversible) copy
    arc = list((fe / "_ledger_archive").iterdir())[0]
    assert (arc / "clv_ledger.jsonl").exists()


def test_restore_round_trips(tmp_path):
    fe = tmp_path / "frontend"
    fe.mkdir()
    arch = fe / "_ledger_archive"
    _seed(fe)
    out = R.reset(100.0, frontend=fe, archive_root=arch)
    name = R.list_archives(archive_root=arch)[0]
    r = R.restore(name, frontend=fe, archive_root=arch)
    assert "clv_ledger.jsonl" in r["restored"]
    assert (fe / "clv_ledger.jsonl").exists()           # came back


def test_no_real_money_tokens():
    src = (R.__file__)
    txt = open(src, encoding="ascii").read().lower()
    # honesty rail: paper/units only, never $ / roi / profit framing in the doc
    assert "real money" in txt and "units only" in txt
