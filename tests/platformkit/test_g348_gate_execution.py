"""Construct tests for G348's imported-harness accounting."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from scripts.platformkit.coordinate_provenance import stamp_court_space_rows
from scripts.platformkit.tracking.g348_gate_execution import aggregate_gates, status_map
from scripts.platformkit.tracking.g343_attack_test import GATES


def test_prereg_seal_uses_lf_normalized_prereg_bytes_not_git_show():
    prereg = Path(__file__).resolve().parents[2] / "docs/evidence/tracking/g348_prereg_2026-09-08.md"
    normalized = prereg.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    prefix, seal = normalized.rsplit(b"SEAL sha256 ", 1)
    assert hashlib.sha256(prefix).hexdigest() == seal.strip().decode("ascii")


def _valid_fixture() -> pd.DataFrame:
    rows = []
    for frame in range(60):
        for track_id, team in ((1, "A"), (2, "A"), (3, "A"), (4, "B"), (5, "B"), (6, "B")):
            rows.append({"frame": frame, "track_id": track_id, "team": team, "cls": "player",
                         "x": 8.0 + 10.0 * track_id + 0.1 * frame,
                         "y": 5.0 + 3.0 * track_id + 0.05 * frame})
        rows.append({"frame": frame, "track_id": -1, "team": "", "cls": "ball",
                     "x": 47.0, "y": 25.0})
    return stamp_court_space_rows(pd.DataFrame(rows), "basketball")


def test_synthetic_valid_fixture_reaches_every_imported_gate():
    statuses = status_map(_valid_fixture(), "A0", 60)
    assert set(GATES) | {"any_gate"} <= set(statuses)
    assert all(statuses[gate][0] == "PASS" for gate in (*GATES, "any_gate"))


def test_contract_invalid_control_is_refused_not_detected():
    statuses = status_map(_valid_fixture(), "C0_CONTRACT_INVALID", 60)
    assert statuses["coordinate_contract"][0] == "REFUSED"
    assert all(status != "REJECT" for status, _ in statuses.values())


def test_gate_denominators_sum_by_status_reason_cell():
    statuses = status_map(_valid_fixture(), "A0", 60)
    records = [{"fixture_id": "000001", "arm": "A0", "gate": gate, "status": status,
                "reason_class": "ACCEPTED", "reached": 1, "evaluated": 1,
                "rejected": 0, "refused": 0}
               for gate, (status, _) in statuses.items()]
    rows = aggregate_gates(records)
    assert sum(int(row["n"]) for row in rows) == len(records)
    assert sum(int(row["evaluated_n"]) for row in rows) == len(records)
    assert sum(int(row["rejected_n"]) for row in rows) == 0
