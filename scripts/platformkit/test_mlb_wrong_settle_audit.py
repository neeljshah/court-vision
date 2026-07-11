"""Per-file test for scripts.platformkit.mlb_wrong_settle_audit (no network).

Run ONLY this file (full suite freezes the box):
    python -m pytest scripts/platformkit/test_mlb_wrong_settle_audit.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.mlb_wrong_settle_audit import find_wrong_settles, run_audit


def _settled_row(bet_id, settled_at, home_score, away_score, matchup="COL @ SF"):
    return {"sport": "mlb", "status": "settled", "matchup": matchup, "side": "home",
            "bet_id": bet_id, "settled_at": settled_at,
            "home_score": home_score, "away_score": away_score}


def test_flags_settled_before_ticket_date():
    """The proven trap: a ticket dated 26JUL11 whose settled_at is 07-09 -- the
    game could not possibly have been final before its own date started."""
    rows = [_settled_row("pm|kalshi|KXMLBGAME-26JUL111400COLSF|home",
                         "2026-07-09T23:00:00+00:00", 8, 2)]
    flags = find_wrong_settles(rows)
    assert len(flags) == 1
    assert "settled_before_ticket_date" in flags[0]["reasons"]


def test_flags_same_final_reused_across_dates():
    """Same literal final (identical score, same team pairing) bound to bets
    ticketed on THREE different dates -- the actual live COL@SF collision."""
    rows = [
        _settled_row("pm|kalshi|KXMLBGAME-26JUL091400COLSF|home",
                     "2026-07-09T23:00:00+00:00", 8, 2),
        _settled_row("pm|kalshi|KXMLBGAME-26JUL101400COLSF|home",
                     "2026-07-10T01:00:00+00:00", 8, 2),
        _settled_row("pm|kalshi|KXMLBGAME-26JUL111400COLSF|home",
                     "2026-07-10T01:00:00+00:00", 8, 2),
    ]
    flags = find_wrong_settles(rows)
    bet_ids = {f["bet_id"] for f in flags}
    assert bet_ids == {r["bet_id"] for r in rows}
    assert all("same_final_reused_across_dates" in f["reasons"] for f in flags)


def test_paper_ingame_channel_never_flagged():
    """paper_ingame settles via a DIFFERENT resolver (exact game_id match) --
    two genuinely distinct games that happen to share a final score must NOT be
    flagged just because they share a team pairing (verified live: 407 real
    paper_ingame rows share the KXMLBGAME ticket pattern but none went through
    the buggy team+date fuzzy matcher this audit targets)."""
    rows = [
        {"sport": "mlb", "status": "settled", "channel": "paper_ingame",
         "bet_id": "mlb|KXMLBGAME-26JUN301840TEXCLE|win_home|home|paper_ingame|2026-06-30",
         "settled_at": "2026-07-01T23:34:31.951449+00:00", "home_score": 2, "away_score": 4},
        {"sport": "mlb", "status": "settled", "channel": "paper_ingame",
         "bet_id": "mlb|KXMLBGAME-26JUL011310TEXCLE|win_home|home|paper_ingame|2026-07-01",
         "settled_at": "2026-07-01T23:34:32.059448+00:00", "home_score": 2, "away_score": 4},
    ]
    assert find_wrong_settles(rows) == []


def test_no_flags_for_clean_distinct_settles():
    """3 distinct games, distinct scores, ticket date == settle date -> nothing
    flagged (never a false positive on an honestly-settled row)."""
    rows = [
        _settled_row("a|KXMLBGAME-26JUL091400COLSF|home", "2026-07-09T23:00:00+00:00", 8, 2),
        _settled_row("b|KXMLBGAME-26JUL101400COLSF|home", "2026-07-10T23:00:00+00:00", 4, 1),
        _settled_row("c|KXMLBGAME-26JUL091400NYYBOS|home", "2026-07-09T23:00:00+00:00",
                     3, 2, matchup="NYY @ BOS"),
    ]
    assert find_wrong_settles(rows) == []


def test_run_audit_writes_quarantine_file_and_never_touches_ledger(tmp_path, monkeypatch):
    ledger = tmp_path / "clv_ledger.jsonl"
    row = _settled_row("pm|kalshi|KXMLBGAME-26JUL111400COLSF|home",
                       "2026-07-09T23:00:00+00:00", 8, 2)
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    flags_path = tmp_path / "mlb_wrong_settle_quarantine.json"
    before = ledger.read_text(encoding="utf-8")

    report = run_audit(ledger_path=ledger, flags_path=flags_path)

    assert report["n_flagged"] == 1
    assert flags_path.exists()
    written = json.loads(flags_path.read_text(encoding="utf-8"))
    assert written["n_flagged"] == 1
    assert ledger.read_text(encoding="utf-8") == before  # ledger never rewritten


def test_flags_settled_before_scheduled_start():
    """2026-07-11 AZLAD wrong-settle: SAME calendar date as the ticket (check 1
    misses this -- dates are equal), but settled_at is hours BEFORE the ticket's
    own embedded ET start time -- definitionally impossible."""
    rows = [_settled_row("pm|kalshi|KXMLBGAME-26JUL112110AZLAD|away",
                         "2026-07-11T05:27:10.197994+00:00", 3, 9,
                         matchup="Los Angeles D vs Arizona")]
    flags = find_wrong_settles(rows)
    assert len(flags) == 1
    assert "settled_before_scheduled_start" in flags[0]["reasons"]
    assert "settled_before_ticket_date" not in flags[0]["reasons"]  # dates ARE equal


def test_run_audit_is_append_only_never_rewrites_existing_flag(tmp_path):
    """A prior quarantine file's existing entries must survive byte-identical
    across a re-run that ALSO finds a brand-new flag -- human-gated quarantine,
    never a silent overwrite of a row already under review."""
    flags_path = tmp_path / "mlb_wrong_settle_quarantine.json"
    prior_entry = {"bet_id": "pm|kalshi|KXMLBGAME-26JUL081840ATLPIT|away",
                   "matchup": "Pittsburgh vs Atlanta", "reasons": ["same_final_reused_across_dates"],
                   "settled_at": "2026-07-08T02:45:21.906163+00:00",
                   "ticker_date": "2026-07-08", "home_score": 12, "away_score": 4}
    flags_path.write_text(json.dumps({"component": "mlb_wrong_settle_audit",
                                      "flags": [prior_entry], "n_flagged": 1,
                                      "generated_at": "2026-07-08T03:00:00+00:00",
                                      "n_settled_mlb_ticker_scanned": 1}), encoding="utf-8")
    ledger = tmp_path / "clv_ledger.jsonl"
    new_row = _settled_row("pm|kalshi|KXMLBGAME-26JUL112110AZLAD|away",
                           "2026-07-11T05:27:10.197994+00:00", 3, 9,
                           matchup="Los Angeles D vs Arizona")
    ledger.write_text(json.dumps(new_row) + "\n", encoding="utf-8")

    report = run_audit(ledger_path=ledger, flags_path=flags_path)

    written = json.loads(flags_path.read_text(encoding="utf-8"))
    assert written["n_flagged"] == 2
    by_id = {f["bet_id"]: f for f in written["flags"]}
    assert by_id[prior_entry["bet_id"]] == prior_entry  # untouched, byte-identical
    assert "settled_before_scheduled_start" in by_id[new_row["bet_id"]]["reasons"]
