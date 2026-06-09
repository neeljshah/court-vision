"""Structural test for the CLV capture pipeline (clv_capture): append-only + idempotent + open/close collapse.

The freshness/CLV edge (EDGE_GATE iter-17) needs OPEN/CLOSE odds pairs. This locks the capture log's invariants:
append-only dedup (re-ingest is idempotent) and the open=first-snap / close=last-snap collapse.
"""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts", "team_system"))

import clv_capture as cc  # noqa: E402


def _synthetic_log(tmp_path):
    # two snapshots of one prop: open (ts0, line 6.5 @ -110) then close (ts1, line 6.5 @ -130)
    rows = [
        ["t0", "ct", "2026-01-01", "A@B", "player_assists", "Player X", 6.5, "dk", -110.0, -110.0, "prop"],
        ["t1", "ct", "2026-01-01", "A@B", "player_assists", "Player X", 6.5, "dk", -130.0, +105.0, "prop"],
    ]
    return pd.DataFrame(rows, columns=cc.COLS)


def test_append_is_idempotent(tmp_path, monkeypatch):
    log = os.path.join(tmp_path, "clv_log.parquet")
    monkeypatch.setattr(cc, "LOG", log)
    monkeypatch.setattr(cc, "CLV_DIR", str(tmp_path))
    df = _synthetic_log(tmp_path)
    cc._append(df.values.tolist())
    n1 = len(pd.read_parquet(log))
    cc._append(df.values.tolist())          # re-ingest the SAME rows
    n2 = len(pd.read_parquet(log))
    assert n1 == n2 == 2                      # dedup -> idempotent, no duplicate rows


def test_open_close_collapse(tmp_path, monkeypatch, capsys):
    log = os.path.join(tmp_path, "clv_log.parquet")
    monkeypatch.setattr(cc, "LOG", log)
    monkeypatch.setattr(cc, "CLV_DIR", str(tmp_path))
    cc._append(_synthetic_log(tmp_path).values.tolist())
    merged = cc.open_close("player_assists")
    assert len(merged) == 1
    r = merged.iloc[0]
    assert r["snap_ts_open"] == "t0" and r["snap_ts_close"] == "t1"   # first=open, last=close
    assert r["over_price_open"] == -110.0 and r["over_price_close"] == -130.0   # the captured move


def test_cols_schema_stable():
    assert cc.COLS[:7] == ["snap_ts", "commence_ts", "date", "game", "market", "selection", "line"]
    assert "grain" in cc.COLS
