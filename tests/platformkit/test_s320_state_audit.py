"""Synthetic rails for the prepared S320 state-audit route."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from scripts.platformkit.ingame.s320_state_audit import audit_states, prefix_replay


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/harness/S320_timestamp_artifact_audit_2026-09-08_prereg.md"


def _rows() -> pd.DataFrame:
    return pd.DataFrame({
        "game_id": [1, 1, 1], "ts": [100, 200, 300], "period": [1, 1, 1],
        "game_clock_s": [500.0, 400.0, 300.0], "margin": [2, 2, 2],
        "market_prob": [0.4, 0.6, 0.8], "game_date": ["2026-01-01"] * 3,
        "received_at": ["1970-01-01T00:01:39Z", "1970-01-01T00:03:19Z", "1970-01-01T00:04:59Z"],
        "side": ["HOME"] * 3, "home": ["HOME"] * 3, "venue": ["test"] * 3,
    })


def _states() -> pd.DataFrame:
    return pd.DataFrame({"game_id": ["1"], "state_ts": ["1970-01-01T00:03:20+00:00"],
                         "ts": [200], "stratum": ["p1_m0_3_cgt_300"]})


def test_planted_future_record_changes_full_not_prefix_and_is_flagged() -> None:
    rows, states = _rows(), _states()
    result = prefix_replay(rows, states, lambda history, _: float(history.market_prob.iloc[-1]), "N")
    assert round(result.iloc[0].abs_b_minus_a, 12) == 0.2
    assert round(result.iloc[0].abs_c_minus_a, 12) == 0.4
    assert result.iloc[0].verdict == "VIOLATION"


def test_terminal_state_is_rejected() -> None:
    rows, states = _rows(), _states()
    rows.loc[1, ["period", "game_clock_s"]] = [4, 0.0]
    audit = audit_states(rows, states)
    assert audit.loc[audit.check.eq("status"), "verdict"].item() == "VIOLATION"


def test_duplicate_key_is_rejected() -> None:
    rows, states = _rows(), _states()
    rows = pd.concat([rows, rows.iloc[[1]]], ignore_index=True)
    audit = audit_states(rows, states)
    assert audit.loc[audit.check.eq("duplicate"), "verdict"].item() == "VIOLATION"


def test_clean_construct_passes_every_check() -> None:
    audit = audit_states(_rows(), _states())
    assert set(audit.verdict) == {"ACCEPTED"}


def test_prereg_seal_hashes_lf_normalized_prefix_without_git() -> None:
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    prefix, seal = raw.rsplit(b"SEAL sha256 ", 1)
    assert hashlib.sha256(prefix).hexdigest() == seal.decode("ascii").strip()
