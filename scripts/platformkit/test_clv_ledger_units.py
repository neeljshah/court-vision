"""Per-file tests: UNITS-ONLY clv_ledger writer + bet_id + migration.

Run ONLY this file (full suite freezes the box):
    python -m pytest scripts/platformkit/test_clv_ledger_units.py -q

Asserts the honesty rails for the canonical ledger:
  * record_bet writes NO dollar/pnl/stake/bankroll key -- only stake_units;
  * bet_id is durable (independent of the write ts);
  * migrate_ledger_to_units strips $ keys idempotently + atomically (backup made).
"""
from __future__ import annotations

import json

from scripts.platformkit.clv_ledger import bet_id, load_ledger, record_bet
from scripts.platformkit.clv_ledger_migrate import (
    BANNED_KEYS,
    migrate_ledger_to_units,
    row_has_dollars,
    to_units_row,
)

_BANNED = set(BANNED_KEYS)


def test_record_bet_writes_units_no_dollars(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    rec = record_bet("nba", "A @ B", "home", "FanDuel", 2.5,
                     model_prob=0.55, stake_units=1.25, path=ledger)
    assert rec["stake_units"] == 1.25
    keys = set(rec)
    assert not (_BANNED & keys), "record_bet leaked $ keys: %s" % (_BANNED & keys)
    on_disk = load_ledger(ledger)[0]
    assert not (_BANNED & set(on_disk)), "ledger row has $ keys"
    assert on_disk["stake_units"] == 1.25


def test_record_bet_legacy_stake_kwarg_maps_to_units(tmp_path):
    """The deprecated stake= kwarg is interpreted as UNITS, never written as $."""
    ledger = tmp_path / "clv_ledger.jsonl"
    rec = record_bet("nba", "A @ B", "home", "FanDuel", 2.5, stake=3.0, path=ledger)
    assert "stake" not in rec
    assert rec["stake_units"] == 3.0


def test_record_bet_stamps_durable_bet_id(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    rec = record_bet("nba", "A @ B", "home", "FanDuel", 2.5,
                     event_id="evt1", game_date="2026-06-19", path=ledger)
    assert rec["bet_id"] == "nba|evt1|moneyline|home|FanDuel|2026-06-19"


def test_bet_id_independent_of_write_ts():
    base = {"sport": "nba", "event_id": "evt1", "market": "moneyline",
            "side": "home", "taken_book": "FanDuel", "game_date": "2026-06-19"}
    a = bet_id({**base, "ts": "2026-06-19T23:59:00+00:00"})
    b = bet_id({**base, "ts": "2026-06-20T00:01:00+00:00"})
    assert a == b, "bet_id must not depend on the write ts"


def test_to_units_row_strips_dollars_idempotent():
    row = {"sport": "nba", "matchup": "A@B", "side": "home", "taken_book": "FD",
           "ts": "2026-06-19T00:00:00+00:00", "stake": 315.41, "pnl": 25.3,
           "paper_roi": 5.0, "bankroll": 10000, "taken_decimal": 2.5}
    out = to_units_row(row)
    assert not row_has_dollars(out)
    assert out["stake_units"] == 315.41  # magnitude relabelled as units
    assert out.get("bet_id")
    # idempotent: re-running changes nothing of substance
    again = to_units_row(out)
    assert again == out


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return path


def test_migrate_strips_dollars_and_backs_up(tmp_path):
    ledger = _write(tmp_path / "clv_ledger.jsonl", [
        {"sport": "nba", "matchup": "A@B", "side": "home", "taken_book": "FD",
         "ts": "2026-06-18T00:00:00+00:00", "stake": 315.41, "pnl": 25.3,
         "taken_decimal": 2.5, "status": "open"},
        {"sport": "mlb", "matchup": "C@D", "side": "away", "taken_book": "DK",
         "ts": "2026-06-18T00:00:00+00:00", "stake_units": 1.0,
         "taken_decimal": 1.9, "status": "open"},
    ])
    res = migrate_ledger_to_units(ledger)
    assert res["status"] == "ok"
    assert res["rows"] == 2 and res["changed"] >= 1
    rows = load_ledger(ledger)
    for r in rows:
        assert not (_BANNED & set(r)), "migrated row still has $ keys: %s" % r
        assert r.get("bet_id")
    # backup written
    assert (tmp_path / "clv_ledger.jsonl.bak").exists()


def test_migrate_is_idempotent(tmp_path):
    ledger = _write(tmp_path / "clv_ledger.jsonl", [
        {"sport": "nba", "matchup": "A@B", "side": "home", "taken_book": "FD",
         "ts": "2026-06-18T00:00:00+00:00", "stake": 50.0, "taken_decimal": 2.5,
         "status": "open"},
    ])
    migrate_ledger_to_units(ledger)
    first = ledger.read_text(encoding="utf-8")
    res2 = migrate_ledger_to_units(ledger)
    assert res2["status"] == "ok" and res2["changed"] == 0
    assert ledger.read_text(encoding="utf-8") == first


def test_migrate_missing_file(tmp_path):
    res = migrate_ledger_to_units(tmp_path / "nope.jsonl")
    assert res["status"] == "no_file"
