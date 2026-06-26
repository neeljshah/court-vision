"""Tests for prop_close_store. Per-file:
python -m pytest scripts/platformkit/clv/test_prop_close_store.py -q
"""
from __future__ import annotations

from scripts.platformkit.clv import prop_close_store as PS


def test_prop_key_side_independent_and_normalized():
    k1 = PS.prop_key("MLB", "2026-06-25", "Hits+Runs+RBIs Guy", "Total Bases", 1.5)
    k2 = PS.prop_key("mlb", "2026-06-25", "hits runs rbis guy", "total  bases", 1.5)
    assert k1 == k2  # normalization collapses case/spaces/+


def test_record_and_get_latest_wins(tmp_path):
    sp = str(tmp_path / "pc.jsonl")
    k = PS.prop_key("mlb", "2026-06-25", "Player A", "Hits", 0.5)
    assert PS.record_quote(k, 1.9, 2.0, "2026-06-25T01:00:00Z", store_path=sp)
    assert PS.record_quote(k, 1.8, 2.1, "2026-06-25T02:00:00Z", store_path=sp)
    c = PS.get_close(k, store_path=sp)
    assert c is not None
    assert c["over_dec"] == 1.8 and c["under_dec"] == 2.1  # latest ts wins


def test_half_or_bad_price_rejected(tmp_path):
    sp = str(tmp_path / "pc.jsonl")
    k = PS.prop_key("mlb", "2026-06-25", "P", "Hits", 0.5)
    assert PS.record_quote(k, 1.0, 2.0, "t", store_path=sp) is False   # over <= 1.0
    assert PS.record_quote(k, 1.9, None, "t", store_path=sp) is False  # missing under
    assert PS.get_close(k, store_path=sp) is None


def test_key_for_row_and_close_for_row(tmp_path):
    sp = str(tmp_path / "pc.jsonl")
    row = {"sport": "mlb", "game_date": "2026-06-25", "prop_player": "Player A",
           "prop_stat": "Hits", "line": 0.5}
    k = PS.key_for_row(row)
    assert k is not None
    PS.record_quote(k, 1.95, 1.95, "2026-06-25T03:00:00Z", store_path=sp)
    c = PS.close_for_row(row, store_path=sp)
    assert c is not None and c["over_dec"] == 1.95


def test_key_for_row_none_without_identity():
    assert PS.key_for_row({"sport": "mlb"}) is None


# ---------------------------------------------------------------------------
# Non-finite guard tests
# ---------------------------------------------------------------------------

def test_record_quote_nan_over_rejected(tmp_path):
    """record_quote must return False and write nothing for NaN over_dec."""
    import os
    sp = str(tmp_path / "pc_nan.jsonl")
    k = PS.prop_key("nba", "2026-06-26", "Player X", "Points", 22.5)
    result = PS.record_quote(k, float("nan"), 1.85, "2026-06-26T01:00:00Z", store_path=sp)
    assert result is False
    assert not os.path.exists(sp)  # nothing was written


def test_record_quote_inf_under_rejected(tmp_path):
    """record_quote must return False and write nothing for infinite under_dec."""
    import os
    sp = str(tmp_path / "pc_inf.jsonl")
    k = PS.prop_key("nba", "2026-06-26", "Player Y", "Assists", 5.5)
    result = PS.record_quote(k, 1.9, float("inf"), "2026-06-26T01:00:00Z", store_path=sp)
    assert result is False
    assert not os.path.exists(sp)


def test_valid_quote_records_and_get_close_returns_it(tmp_path):
    """A finite, positive quote must still record and be retrievable."""
    sp = str(tmp_path / "pc_valid.jsonl")
    k = PS.prop_key("nba", "2026-06-26", "Player Z", "Rebounds", 8.5)
    ok = PS.record_quote(k, 1.87, 2.02, "2026-06-26T02:00:00Z", store_path=sp)
    assert ok is True
    c = PS.get_close(k, store_path=sp)
    assert c is not None
    assert c["over_dec"] == 1.87 and c["under_dec"] == 2.02


def test_load_skips_legacy_nonfinite_row(tmp_path):
    """A NaN/inf row manually written to the store must be skipped by _load /
    get_close; a prior valid row for the same key is returned instead."""
    import json
    sp = str(tmp_path / "pc_legacy.jsonl")
    k = PS.prop_key("nba", "2026-06-26", "Player W", "Points", 18.5)
    # Write a valid earlier row, then a poisoned later row.
    with open(sp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"key": k, "over_dec": 1.91, "under_dec": 1.98,
                             "ts": "2026-06-26T01:00:00Z", "source": "valid"}) + "\n")
        fh.write(json.dumps({"key": k, "over_dec": float("nan"), "under_dec": 1.95,
                             "ts": "2026-06-26T02:00:00Z", "source": "poisoned"}) + "\n")
    c = PS.get_close(k, store_path=sp)
    # Poisoned row must be skipped; the earlier valid row is returned.
    assert c is not None
    assert c["source"] == "valid"
    assert c["over_dec"] == 1.91
