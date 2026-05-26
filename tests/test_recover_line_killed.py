"""tests/test_recover_line_killed.py — R21_N2.

Coverage for scripts/recover_line_killed.py:

  1. --list correctness with synthetic ledger (find_line_killed + is_real_bet)
  2. --refund flips status to refunded + credits bankroll
  3. --refund-all dry-run does NOT write
  4. --refund-all --commit DOES write and skips ineligible by age
  5. --reprice finds available line (exact threshold) and emits place_bet cmd
  6. --reprice gracefully reports none when no snapshot match
  7. --refund idempotency: second call is a no-op
  8. --refund on non-line_killed bet (e.g. open) is rejected as no-op
  9. CLI smoke: argparse mutually-exclusive guard + --list end-to-end
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from typing import Dict, List

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts import recover_line_killed as r  # noqa: E402


LEDGER_FIELDS = [
    "bet_id", "placed_at", "game_id", "player_id", "player", "team",
    "stat", "line", "side", "book", "american_odds", "stake",
    "model_pred", "model_prob", "model_edge", "kelly_pct",
    "status", "settled_at", "actual_stat", "profit_loss", "bankroll_after",
    "strategy",
]


def _empty_row() -> Dict[str, str]:
    return {k: "" for k in LEDGER_FIELDS}


def _write_ledger(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LEDGER_FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def _read_ledger(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _seed_bankroll(path, balance):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(r.BANKROLL_COLS)
        w.writerow([datetime.now().isoformat(timespec="seconds"),
                    f"{float(balance):.2f}", f"{float(balance):.2f}",
                    "initial"])


@pytest.fixture
def sample_ledger(tmp_path):
    """Mix of: 2 real Keldon Johnson line_killed, 1 synth line_killed,
    1 settled real bet, 1 open real bet."""
    ledger = tmp_path / "pnl_ledger.csv"
    placed_recent = datetime.now().isoformat(timespec="seconds")
    placed_old = (datetime.now() - timedelta(hours=48)).isoformat(
        timespec="seconds")

    rows = []
    # 1) real Keldon REB OVER 3.5 — old, line_killed
    rec = _empty_row()
    rec.update({"bet_id": "kj-reb-1", "placed_at": placed_old,
                "game_id": "0022501145", "player_id": "1629640",
                "player": "Keldon Johnson", "team": "SAS",
                "stat": "reb", "line": "3.50", "side": "OVER",
                "book": "fd", "american_odds": "200", "stake": "50.00",
                "status": "line_killed", "strategy": "default"})
    rows.append(rec)
    # 2) real Keldon REB OVER 2.5 — old, line_killed (second book)
    rec = _empty_row()
    rec.update({"bet_id": "kj-reb-2", "placed_at": placed_old,
                "game_id": "0022501145", "player_id": "1629640",
                "player": "Keldon Johnson", "team": "SAS",
                "stat": "reb", "line": "2.50", "side": "OVER",
                "book": "bov", "american_odds": "-135", "stake": "50.00",
                "status": "line_killed", "strategy": "default"})
    rows.append(rec)
    # 3) synth line_killed — recent (<24h, ineligible for --refund-all default)
    rec = _empty_row()
    rec.update({"bet_id": "synth-1", "placed_at": placed_recent,
                "player": "Player_999999", "stat": "pts",
                "line": "20.50", "side": "UNDER", "book": "PP",
                "american_odds": "-119", "stake": "25.00",
                "status": "line_killed"})
    rows.append(rec)
    # 4) real settled bet — untouched by any mode
    rec = _empty_row()
    rec.update({"bet_id": "real-won", "placed_at": placed_old,
                "player": "Victor Wembanyama", "stat": "blk",
                "line": "4.50", "side": "UNDER", "book": "bov",
                "american_odds": "-280", "stake": "50.00",
                "status": "won", "profit_loss": "+17.86"})
    rows.append(rec)
    # 5) open real bet — untouched
    rec = _empty_row()
    rec.update({"bet_id": "open-1", "placed_at": placed_old,
                "player": "Luke Kornet", "stat": "reb",
                "line": "3.50", "side": "OVER", "book": "pin",
                "american_odds": "131", "stake": "50.00",
                "status": "open"})
    rows.append(rec)
    _write_ledger(ledger, rows)

    bankroll = tmp_path / "pnl_bankroll.csv"
    _seed_bankroll(bankroll, 1000.0)
    return ledger, bankroll


# ── 1. --list correctness ──────────────────────────────────────────────────
def test_find_line_killed_only_returns_killed(sample_ledger):
    ledger, _ = sample_ledger
    killed = r.find_line_killed(str(ledger))
    ids = {row["bet_id"] for row in killed}
    assert ids == {"kj-reb-1", "kj-reb-2", "synth-1"}, ids


def test_is_real_bet_excludes_synthetic_player(sample_ledger):
    ledger, _ = sample_ledger
    killed = r.find_line_killed(str(ledger))
    real = [row for row in killed if r.is_real_bet(row)]
    synth = [row for row in killed if not r.is_real_bet(row)]
    assert len(real) == 2
    assert len(synth) == 1
    assert all(row["player"] == "Keldon Johnson" for row in real)
    assert synth[0]["player"] == "Player_999999"


def test_list_handles_missing_ledger(tmp_path):
    killed = r.find_line_killed(str(tmp_path / "nope.csv"))
    assert killed == []


# ── 2. --refund flips status + credits bankroll ────────────────────────────
def test_refund_bet_flips_status_and_credits_bankroll(sample_ledger):
    ledger, bankroll = sample_ledger
    res = r.refund_bet("kj-reb-1", str(ledger), str(bankroll))
    assert res["changed"] is True
    assert res["status"] == "refunded"
    assert res["credit"] == 50.0
    assert res["bankroll_after"] == 1050.0

    rows = _read_ledger(str(ledger))
    by_id = {row["bet_id"]: row for row in rows}
    assert by_id["kj-reb-1"]["status"] == "refunded"
    assert by_id["kj-reb-1"]["profit_loss"] == "0.00"
    assert by_id["kj-reb-1"]["settled_at"] != ""
    # Other rows untouched
    assert by_id["kj-reb-2"]["status"] == "line_killed"
    assert by_id["real-won"]["status"] == "won"
    assert by_id["open-1"]["status"] == "open"

    # Bankroll appended
    with open(bankroll, encoding="utf-8") as fh:
        br_rows = list(csv.DictReader(fh))
    assert br_rows[-1]["note"].startswith("refund:")
    assert float(br_rows[-1]["running_balance"]) == 1050.0


# ── 3. --refund-all dry-run does NOT write ─────────────────────────────────
def test_refund_all_dry_run_no_writes(sample_ledger):
    ledger, bankroll = sample_ledger
    before = _read_ledger(str(ledger))
    res = r.refund_all(str(ledger), str(bankroll),
                      min_age_hours=24.0, commit=False)
    after = _read_ledger(str(ledger))
    assert before == after  # no mutation
    assert res["dry_run"] is True
    assert res["n_killed"] == 3
    # Only the 2 old Keldons are eligible at min_age 24h (synth is recent)
    assert res["n_eligible"] == 2
    eligible_ids = {item["bet_id"] for item in res["eligible"]}
    assert eligible_ids == {"kj-reb-1", "kj-reb-2"}
    assert res["refunded"] == []


# ── 4. --refund-all --commit DOES write and skips ineligible ───────────────
def test_refund_all_commit_writes_only_eligible(sample_ledger):
    ledger, bankroll = sample_ledger
    res = r.refund_all(str(ledger), str(bankroll),
                      min_age_hours=24.0, commit=True)
    assert res["dry_run"] is False
    assert res["n_eligible"] == 2
    assert len(res["refunded"]) == 2
    assert all(item["changed"] for item in res["refunded"])

    rows = _read_ledger(str(ledger))
    by_id = {row["bet_id"]: row for row in rows}
    assert by_id["kj-reb-1"]["status"] == "refunded"
    assert by_id["kj-reb-2"]["status"] == "refunded"
    assert by_id["synth-1"]["status"] == "line_killed"  # too recent, skipped


# ── 5. --reprice finds available line (exact threshold) ────────────────────
def test_reprice_finds_exact_threshold_match(sample_ledger, tmp_path):
    ledger, _bankroll = sample_ledger
    lines_dir = tmp_path / "lines"
    lines_dir.mkdir()
    snap = lines_dir / "2026-05-26_fd.csv"
    with open(snap, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["captured_at", "book", "game_id", "player_id",
                    "player_name", "stat", "line", "over_price",
                    "under_price", "start_time"])
        w.writerow(["2026-05-26T18:00:00", "fd", "35639109", "1629640",
                    "Keldon Johnson", "reb", "3.5", "180", "-220",
                    "2026-05-27T00:40:00.000Z"])
    res = r.reprice_bet("kj-reb-1", str(ledger), str(lines_dir),
                        today="2026-05-26")
    assert res["found_target"] is True
    assert res["n_exact_matches"] == 1
    assert res["place_bet_commands"], "expected at least one place_bet cmd"
    cmd = res["place_bet_commands"][0]
    assert 'Keldon Johnson' in cmd
    assert "--stat reb" in cmd
    assert "--side OVER" in cmd
    assert "--line 3.5" in cmd
    assert "--book fd" in cmd
    assert "--odds 180" in cmd


# ── 6. --reprice reports none when no snapshot ─────────────────────────────
def test_reprice_no_matches(sample_ledger, tmp_path):
    ledger, _ = sample_ledger
    empty_lines = tmp_path / "empty_lines"
    empty_lines.mkdir()
    res = r.reprice_bet("kj-reb-1", str(ledger), str(empty_lines),
                        today="2026-05-26")
    assert res["found_target"] is True
    assert res["n_matches"] == 0
    assert res["place_bet_commands"] == []


def test_reprice_different_threshold_only(sample_ledger, tmp_path):
    """Snapshot has a different threshold (4.5 vs 3.5) — no exact match."""
    ledger, _ = sample_ledger
    lines_dir = tmp_path / "lines"
    lines_dir.mkdir()
    snap = lines_dir / "2026-05-26_fd.csv"
    with open(snap, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["captured_at", "book", "game_id", "player_id",
                    "player_name", "stat", "line", "over_price",
                    "under_price", "start_time"])
        w.writerow(["2026-05-26T18:00:00", "fd", "35639109", "1629640",
                    "Keldon Johnson", "reb", "4.5", "200", "-240", ""])
    res = r.reprice_bet("kj-reb-1", str(ledger), str(lines_dir),
                        today="2026-05-26")
    assert res["n_matches"] == 1
    assert res["n_exact_matches"] == 0
    assert res["place_bet_commands"] == []


# ── 7. --refund idempotency ────────────────────────────────────────────────
def test_refund_idempotent_double_call(sample_ledger):
    ledger, bankroll = sample_ledger
    first = r.refund_bet("kj-reb-1", str(ledger), str(bankroll))
    assert first["changed"] is True
    second = r.refund_bet("kj-reb-1", str(ledger), str(bankroll))
    assert second["changed"] is False
    assert second["reason"] == "already_refunded"
    # Bankroll did NOT double-credit
    rows = _read_ledger(str(ledger))
    by_id = {row["bet_id"]: row for row in rows}
    assert by_id["kj-reb-1"]["status"] == "refunded"
    with open(bankroll, encoding="utf-8") as fh:
        br_rows = list(csv.DictReader(fh))
    # exactly one refund event written
    refund_events = [row for row in br_rows
                     if row["note"].startswith("refund:")]
    assert len(refund_events) == 1


# ── 8. --refund on non-line_killed bet rejected ────────────────────────────
def test_refund_rejects_non_line_killed(sample_ledger):
    ledger, bankroll = sample_ledger
    res = r.refund_bet("open-1", str(ledger), str(bankroll))
    assert res["changed"] is False
    assert "not_line_killed" in res["reason"]
    rows = _read_ledger(str(ledger))
    by_id = {row["bet_id"]: row for row in rows}
    assert by_id["open-1"]["status"] == "open"


def test_refund_missing_bet_id(sample_ledger):
    ledger, bankroll = sample_ledger
    res = r.refund_bet("does-not-exist", str(ledger), str(bankroll))
    assert res["changed"] is False
    assert res["reason"] == "bet_id_not_found"


# ── 9. CLI smoke (--list + --json) ─────────────────────────────────────────
def test_cli_list_json_round_trip(sample_ledger):
    ledger, bankroll = sample_ledger
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = r.main(["--ledger", str(ledger), "--bankroll", str(bankroll),
                     "--list", "--json"])
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["n_killed"] == 3
    assert payload["n_real"] == 2
    assert payload["n_synth"] == 1


def test_cli_requires_a_mode(sample_ledger):
    ledger, bankroll = sample_ledger
    with pytest.raises(SystemExit):
        r.main(["--ledger", str(ledger), "--bankroll", str(bankroll)])
