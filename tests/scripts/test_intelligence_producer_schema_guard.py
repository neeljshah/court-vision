"""S69: the two intelligence builders that died on ``KeyError: 'player_id'``.

The drift was NOT a rename. 355/357 NBA tracking CSVs still carry
``player_id``; what changed is that ``data/tracking/`` now also holds
sport-blind tracking runs written with the ``tracking_schema`` columns
(``track_id``/``cls``/``x``/``y``), and both builders enumerated every
subdirectory unconditionally. The guard SKIPS a foreign-schema directory --
never aliases ``track_id`` onto ``player_id``, which would fold non-NBA tracks
into a per-NBA-player artifact.

Calibration/audit fixture only: no metric, no bar, no market claim.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts import build_quarter_momentum as qm
from scripts import build_tipoff_predictability as tp

# Enough rows to clear each builder's MIN_TOTAL_ROWS floor.
_N = max(qm.MIN_TOTAL_ROWS, tp.MIN_TOTAL_ROWS) + 10


def _write(dirpath, frame) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    frame.to_csv(dirpath / "tracking_data.csv", index=False)


def _nba_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "frame": range(_N),
        "player_id": [1 + (i % 5) for i in range(_N)],
        "team": ["LAL"] * _N,
        "velocity": [4.0] * _N,
        "dist_to_basket_ft": [20.0] * _N,
        "distance_to_ball": [12.0] * _N,
    })


def _foreign_frame() -> pd.DataFrame:
    """The sport-blind tracking_schema shape -- no player_id anywhere."""
    return pd.DataFrame({
        "frame": range(_N),
        "track_id": [1 + (i % 5) for i in range(_N)],
        "cls": ["person"] * _N,
        "x": [0.5] * _N,
        "y": [0.5] * _N,
    })


@pytest.fixture
def tracking_root(tmp_path, monkeypatch):
    _write(tmp_path / "0022400001", _nba_frame())
    _write(tmp_path / "mlb_foreignschema", _foreign_frame())
    monkeypatch.setattr(qm, "TRACKING_DIR", tmp_path)
    monkeypatch.setattr(tp, "TRACKING_DIR", tmp_path)
    return tmp_path


@pytest.mark.parametrize("mod", [qm, tp], ids=["quarter_momentum", "tipoff"])
def test_foreign_schema_dir_is_skipped_not_raised(tracking_root, mod):
    assert mod._process_one_game("mlb_foreignschema") == []


@pytest.mark.parametrize("mod", [qm, tp], ids=["quarter_momentum", "tipoff"])
def test_nba_schema_dir_still_produces_rows(tracking_root, mod):
    rows = mod._process_one_game("0022400001")
    assert rows, "the guard must not drop a real NBA tracking directory"
    assert all(row["game_id"] == "0022400001" for row in rows)


# --- generated_at stamping (S69) -------------------------------------------
# gate_manifest._row_for reads `generated_at` and not the `generated` these two
# builders already wrote, so both artifacts registered mtime-sourced. The new
# key is ADDITIVE (`generated` is untouched) and UTC-aware, because the naive
# local value read 5 h stale to a UTC freshness check.

def _parsed(value):
    from datetime import datetime
    return datetime.fromisoformat(value)


def test_quarter_signatures_json_carries_both_stamps(tmp_path, monkeypatch):
    import json
    out = tmp_path / "quarter_signatures.json"
    monkeypatch.setattr(qm, "OUT_JSON", out)
    monkeypatch.setattr(qm, "INTEL_DIR", tmp_path)
    qm._write_json(pd.DataFrame(columns=["name_key"]), {"per_quarter": {}})
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["generated"], "the pre-existing key must survive"
    assert _parsed(payload["generated_at"]).tzinfo is not None


def test_tipoff_signals_carry_both_stamps_populated_and_empty():
    populated = tp._build_signals_json(pd.DataFrame([
        {"feature_name": "velocity", "window": "w100", "n": 40,
         "r_pearson": 0.9, "r2": 0.81, "p_value": 0.001},
    ]))
    assert populated["generated"]
    assert _parsed(populated["generated_at"]).tzinfo is not None
    empty = tp._build_signals_json(pd.DataFrame())
    assert empty["generated"] == "" and empty["generated_at"] == ""
