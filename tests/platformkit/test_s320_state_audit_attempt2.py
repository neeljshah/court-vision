"""Synthetic rails for the S320 state-audit route (VERSION b: 5 states per stratum)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from scripts.platformkit.ingame.s320_state_audit_attempt2 import (
    audit_states, prefix_replay, select_states, strata_census,
)


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/harness/S320_timestamp_artifact_audit_2026-09-08b_prereg.md"


def _rows() -> pd.DataFrame:
    return pd.DataFrame({
        "game_id": [1, 1, 1], "ts": [100, 200, 300], "period": [1, 1, 1],
        "game_clock_s": [500.0, 400.0, 300.0], "margin": [2, 2, 2],
        "market_prob": [0.4, 0.6, 0.8], "game_date": ["2026-01-01"] * 3,
        "received_at": ["1970-01-01T00:01:39Z", "1970-01-01T00:03:19Z", "1970-01-01T00:04:59Z"],
        "side": ["HOME"] * 3, "home": ["HOME"] * 3, "venue": ["test"] * 3,
    })


def _states() -> pd.DataFrame:
    return pd.DataFrame({"state_id": [0], "game_id": ["1"], "state_ts": ["1970-01-01T00:03:20+00:00"],
                         "ts": [200], "stratum": ["p1_m0_3_cgt_300"]})


def _selection_rows() -> pd.DataFrame:
    many = pd.DataFrame({
        "game_id": list(range(7)), "ts": [1000 + i for i in range(7)],
        "period": [1] * 7, "game_clock_s": [400.0] * 7, "margin": [2] * 7,
        "market_prob": [0.5] * 7, "game_date": ["2026-01-01"] * 7,
    })
    few = pd.DataFrame({
        "game_id": [100, 101], "ts": [2000, 2001],
        "period": [2] * 2, "game_clock_s": [400.0] * 2, "margin": [2] * 2,
        "market_prob": [0.5] * 2, "game_date": ["2026-01-01"] * 2,
    })
    return pd.concat([many, few], ignore_index=True)


def test_planted_future_record_changes_full_not_prefix_and_is_flagged() -> None:
    rows, states = _rows(), _states()
    result = prefix_replay(rows, states, lambda history, _: float(history.market_prob.iloc[-1]), "N")
    assert round(result.iloc[0].delta_b, 12) == 0.2
    assert round(result.iloc[0].delta_c, 12) == 0.4
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


def test_absent_received_at_is_not_verified_never_accepted() -> None:
    rows, states = _rows().drop(columns=["received_at"]), _states()
    audit = audit_states(rows, states)
    result = audit.loc[audit.check.eq("availability"), "verdict"].item()
    assert result == "NOT_VERIFIED"


def test_selection_draws_five_per_stratum_and_all_if_fewer() -> None:
    frame = _selection_rows()
    census = strata_census(frame).set_index("stratum")
    chosen = select_states(frame)
    counts = chosen.groupby("stratum").size()
    assert census.loc["p1_m0_3_cgt_300", "n_eligible"] == 7
    assert census.loc["p1_m0_3_cgt_300", "n_drawn"] == 5
    assert census.loc["p2_m0_3_cgt_300", "n_eligible"] == 2
    assert census.loc["p2_m0_3_cgt_300", "n_drawn"] == 2
    assert counts["p1_m0_3_cgt_300"] == 5
    assert counts["p2_m0_3_cgt_300"] == 2
    assert len(chosen) == 7


def test_prereg_seal_hashes_lf_normalized_prefix_without_git() -> None:
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    prefix, seal = raw.rsplit(b"SEAL sha256 ", 1)
    assert hashlib.sha256(prefix).hexdigest() == seal.decode("ascii").strip()
