"""tests/test_place_bet.py - probe R16_E7 acceptance tests for the
record-intent-to-bet CLI (scripts/place_bet.py).

Covers:
  1. Validation: rejects invalid stat / side / stake.
  2. Stake cap: rejects stake > 5% bankroll (default).
  3. Dry-run: validates + prints summary, ledger NOT modified.
  4. Ledger append: bet_id appears in pnl_ledger.csv with correct schema.
  5. Idempotency: re-running the same placement is rejected.
  6. Copy-paste format: includes book + player + stat + side + line + odds +
     stake + payout + bet_id, and odds with explicit sign.
  7. Slate validation: bypassed with --no-slate-validate; rejected without
     match when slate is supplied.
  8. show_bet.py prefix lookup round-trip.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import tempfile
import uuid
from typing import List

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


# --------------------------------------------------------------------------- #
# Test fixtures                                                               #
# --------------------------------------------------------------------------- #
@pytest.fixture
def tmp_ledger(monkeypatch, tmp_path):
    """Redirect the ledger + bankroll log + lockfile to a tmpdir."""
    ledger = tmp_path / "pnl_ledger.csv"
    bankroll = tmp_path / "pnl_bankroll.csv"
    from src.betting import pnl_ledger as _pl
    monkeypatch.setattr(_pl, "LEDGER_CSV",   str(ledger))
    monkeypatch.setattr(_pl, "BANKROLL_CSV", str(bankroll))
    monkeypatch.setattr(_pl, "LOCK_PATH",    str(ledger) + ".lock")
    # place_bet.py imported LEDGER_CSV at module-import time -> re-bind there too.
    import scripts.place_bet as pb
    monkeypatch.setattr(pb, "LEDGER_CSV", str(ledger))
    yield ledger


@pytest.fixture
def slate_file(tmp_path):
    """Write a minimal slate JSON that contains the Keldon Johnson REB OVER 3.5 row."""
    slate = {
        "game": "SAS @ OKC Game 7 WCF",
        "captured_at": "2026-05-26T12:52:52.473415Z",
        "ranked_bets": [],
        "all_positive_bets_unfiltered": [
            {
                "player": "Keldon Johnson",
                "team": "SAS",
                "stat": "reb",
                "side": "OVER",
                "book": "pin",
                "line": 3.5,
                "model_q50": 5.17,
                "model_prob": 0.7395,
                "odds": 157,
                "edge_pct": 35.04,
                "ev_per_dollar": 0.9005,
                "kelly_pct_used": 5.0,
                "kelly_pct_full": 57.36,
            },
            {
                "player": "Victor Wembanyama",
                "team": "SAS",
                "stat": "blk",
                "side": "UNDER",
                "book": "bov",
                "line": 2.5,
                "model_q50": 2.04,
                "model_prob": 0.844,
                "odds": 200,
                "edge_pct": 51.07,
                "kelly_pct_used": 5.0,
            },
        ],
    }
    p = tmp_path / "slate.json"
    p.write_text(json.dumps(slate))
    return str(p)


def _run_main(argv: List[str]) -> int:
    """Invoke place_bet.main directly (fresh args), return exit code."""
    import scripts.place_bet as pb
    return pb.main(argv)


def _keldon_args(slate_path: str, **overrides) -> List[str]:
    # --force-stale bypasses the R17_J2 line-freshness validator. These tests
    # exercise placement / slate / ledger semantics, not live-line freshness;
    # the validator has its own dedicated suite in test_line_validator.py.
    args = {
        "--player": "Keldon Johnson", "--stat": "reb", "--side": "OVER",
        "--line": "3.5", "--book": "pinnacle", "--odds": "+157",
        "--stake": "50", "--bankroll": "1000", "--slate": slate_path,
        "--force-stale": None,
    }
    args.update(overrides)
    out: List[str] = []
    for k, v in args.items():
        out.append(k)
        if v is not None:
            out.append(str(v))
    return out


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #
def test_validation_rejects_bad_stat(tmp_ledger, slate_file, capsys):
    """Invalid stat returns non-zero exit + leaves ledger empty."""
    rc = _run_main(_keldon_args(slate_file, **{"--stat": "xyz"}))
    assert rc != 0
    assert not os.path.exists(tmp_ledger) or os.path.getsize(tmp_ledger) == 0
    out = capsys.readouterr().out
    assert "stat must be" in out


def test_stake_cap_rejects_over_5pct(tmp_ledger, slate_file, capsys):
    """Stake 51 with $1000 bankroll (5% = $50) -> rejected, ledger untouched."""
    rc = _run_main(_keldon_args(
        slate_file, **{"--stake": "51", "--no-slate-validate": None},
    ))
    assert rc == 3
    out = capsys.readouterr().out
    assert "exceeds 5.0% cap" in out or "exceeds 5%" in out
    assert not os.path.exists(tmp_ledger) or os.path.getsize(tmp_ledger) == 0


def test_dry_run_does_not_touch_ledger(tmp_ledger, slate_file, capsys):
    """--dry-run prints summary but leaves ledger empty."""
    rc = _run_main(_keldon_args(slate_file, **{"--dry-run": None}))
    assert rc == 0
    out = capsys.readouterr().out
    assert "[DRY-RUN]" in out
    assert "Keldon Johnson" in out
    assert "REB OVER 3.5" in out
    assert "+157" in out
    assert "$50.00" in out
    # No file written:
    assert not os.path.exists(tmp_ledger) or os.path.getsize(tmp_ledger) == 0


def test_ledger_append_writes_full_row(tmp_ledger, slate_file, capsys):
    """A real placement writes one row with the full schema populated."""
    rc = _run_main(_keldon_args(slate_file))
    assert rc == 0
    assert os.path.exists(tmp_ledger)
    with open(tmp_ledger, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    row = rows[0]
    assert row["player"] == "Keldon Johnson"
    assert row["stat"] == "reb"
    assert row["side"] == "OVER"
    assert row["book"] == "pin"          # canonicalised from "pinnacle"
    assert row["american_odds"] == "157"
    assert abs(float(row["line"])  - 3.5)  < 1e-6
    assert abs(float(row["stake"]) - 50.0) < 1e-6
    assert row["status"] == "open"
    assert row["bet_id"]                  # non-empty UUID
    # Model context from slate gets stamped:
    assert abs(float(row["model_pred"]) - 5.17)   < 1e-3
    assert abs(float(row["model_prob"]) - 0.7395) < 1e-3
    # R19_L2: clamp_kelly_pct stores as fraction [0, 0.25]; 5.0 pct -> 0.25 (cap).
    assert abs(float(row["kelly_pct"])  - 0.25)   < 1e-3


def test_idempotency_blocks_duplicate(tmp_ledger, slate_file, capsys):
    """Re-running the SAME placement is rejected as a duplicate of the open bet."""
    rc1 = _run_main(_keldon_args(slate_file))
    assert rc1 == 0
    capsys.readouterr()    # flush
    rc2 = _run_main(_keldon_args(slate_file))
    assert rc2 == 5
    out = capsys.readouterr().out
    assert "duplicate" in out.lower()
    # Still only one row:
    with open(tmp_ledger, encoding="utf-8") as fh:
        assert sum(1 for _ in csv.DictReader(fh)) == 1
    # --allow-duplicate forces a second row:
    rc3 = _run_main(_keldon_args(slate_file, **{"--allow-duplicate": None}))
    assert rc3 == 0
    with open(tmp_ledger, encoding="utf-8") as fh:
        assert sum(1 for _ in csv.DictReader(fh)) == 2


def test_copy_paste_format_has_all_fields(tmp_ledger, slate_file, capsys):
    """Printed summary contains book, player, stat, side, line, odds, stake,
    payout, profit, and a bet_id line."""
    rc = _run_main(_keldon_args(slate_file))
    assert rc == 0
    out = capsys.readouterr().out
    # Book uppercase
    assert "PINNACLE" in out
    # Player + stat block
    assert re.search(r"Keldon Johnson REB OVER 3\.5 @ \+157", out)
    # Stake line
    assert "Stake: $50.00" in out
    # Payout: +157 -> profit 50 * 1.57 = 78.50, total = 128.50
    assert "Potential payout: $128.50" in out
    assert "profit $+78.50" in out or "profit +$78.50" in out or "profit $78.50" in out
    # Bet ID line
    assert "Bet ID:" in out
    # And an actual UUID-ish string after it
    assert re.search(r"Bet ID:\s+[0-9a-f-]{8,}", out)


def test_slate_validation_rejects_missing_combo(tmp_ledger, slate_file, capsys):
    """A bet not in the slate (Jokic PTS) is rejected unless --no-slate-validate."""
    rc = _run_main([
        "--player", "Nikola Jokic", "--stat", "pts", "--side", "OVER",
        "--line", "27.5", "--book", "pinnacle", "--odds", "-110",
        "--stake", "25", "--bankroll", "1000", "--slate", slate_file,
    ])
    assert rc == 4
    out = capsys.readouterr().out
    assert "no slate match" in out
    # Bypass works:
    rc2 = _run_main([
        "--player", "Nikola Jokic", "--stat", "pts", "--side", "OVER",
        "--line", "27.5", "--book", "pinnacle", "--odds", "-110",
        "--stake", "25", "--bankroll", "1000",
        "--no-slate-validate", "--force-stale",
    ])
    assert rc2 == 0


def test_show_bet_prefix_lookup_round_trip(tmp_ledger, slate_file, capsys):
    """show_bet.py finds the row by bet_id prefix after placement."""
    rc = _run_main(_keldon_args(slate_file))
    assert rc == 0
    out = capsys.readouterr().out
    m = re.search(r"Bet ID:\s+([0-9a-f-]+)", out)
    assert m, f"bet_id not found in summary: {out!r}"
    bet_id = m.group(1)

    import scripts.show_bet as sb
    rc2 = sb.main([bet_id[:8], "--ledger", str(tmp_ledger)])
    assert rc2 == 0
    out2 = capsys.readouterr().out
    assert "Keldon Johnson" in out2
    assert "REB OVER" in out2
    # JSON mode round-trip
    rc3 = sb.main([bet_id, "--ledger", str(tmp_ledger), "--json"])
    assert rc3 == 0
    out3 = capsys.readouterr().out
    payload = json.loads(out3)
    assert payload["bet_id"] == bet_id


def test_potential_payout_helper():
    """Direct unit test of the payout math for +157, -110, +200."""
    import scripts.place_bet as pb
    total, profit = pb.potential_payout(50.0, 157)
    assert profit == pytest.approx(78.50, abs=0.01)
    assert total  == pytest.approx(128.50, abs=0.01)
    total2, profit2 = pb.potential_payout(110.0, -110)
    assert profit2 == pytest.approx(100.0, abs=0.01)
    total3, profit3 = pb.potential_payout(10.0, 200)
    assert profit3 == pytest.approx(20.0, abs=0.01)
    assert total3  == pytest.approx(30.0, abs=0.01)
