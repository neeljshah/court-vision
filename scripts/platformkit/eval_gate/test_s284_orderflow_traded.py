import csv
import hashlib
from pathlib import Path

from scripts.platformkit.eval_gate.s284_orderflow_traded import (
    ROOT,
    enumerate_overlaps,
    parse_checkpoint_ticker,
    parse_kalshi_event_key,
)


def test_s284_parses_pairs_and_enumerates_both_orderings():
    assert parse_kalshi_event_key("KXNBAGAME-26APR26BOSPHI") == ("2026-04-26", "BOS", "PHI")
    assert parse_checkpoint_ticker("nba-bos-phi-2026-04-26") == ("2026-04-26", "BOS", "PHI")
    events = {"KXNBAGAME-26APR26BOSPHI": ("2026-04-26", "BOS", "PHI")}
    games = {"401": ("2026-04-26", "BOS", "PHI"), "402": ("2026-04-27", "BOS", "PHI")}
    rows, summary = enumerate_overlaps(events, games)
    assert len(rows) == 2
    assert summary["away_home"]["game_cluster_overlap"] == 1
    assert summary["home_away"]["game_cluster_overlap"] == 0
    assert summary["away_home"]["date_offset_distribution"] == {0: 1, 1: 1}


def test_s284_prereg_seal_and_one_archived_game_brier():
    prereg = ROOT / "docs/evidence/harness/S284_orderflow_traded_2026-09-04_preregistration.md"
    normalized = prereg.read_bytes().replace(b"\r\n", b"\n")
    body, seal_line = normalized.split(b"SEAL_SHA256: ", 1)
    assert hashlib.sha256(body).hexdigest() == seal_line.decode("ascii").strip()
    archive = ROOT / "docs/evidence/harness/S284_orderflow_traded_2026-09-04_ticks.csv"
    with archive.open(encoding="ascii", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["game_id"] == "401859963"]
    assert len(rows) == 153
    brier = sum(float(row["loss_recal_null"]) for row in rows) / len(rows)
    assert abs(brier - 0.40226636180764824) < 1e-15
    assert all(int(row["n_evaluator_records"]) == 7 for row in rows)
