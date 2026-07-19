"""Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/ingame/test_mlb_label_audit.py -q
"""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from scripts.platformkit.ingame import mlb_label_audit as A


def _tick(hs, aw, inn, ts, outcome, mkt):
    return json.dumps({
        "state_summary": "home_score=%s away_score=%s inning=%d half=top outs=0" % (hs, aw, inn),
        "ts": ts, "outcome": outcome, "market_prob": mkt, "model_prob": 0.5,
    })


def _write_game(d, blob_date, blob, ticks):
    # KXMLBGAME-<YY><MON><DD><HHMM><blob> ; blob = away+home Kalshi abbrs
    yy, mm, dd = blob_date[2:4], blob_date[5:7], blob_date[8:10]
    mon = {v: k for k, v in A._MON.items()}[mm]
    gid = "KXMLBGAME-%s%s%s1200%s" % (yy, mon, dd, blob)
    with open(os.path.join(d, gid + ".jsonl"), "w") as fh:
        fh.write("\n".join(ticks) + "\n")
    return gid


def _index(tmp_path, rows):
    # rows: (date, away_team, home_team, home_win) in parquet dialect
    df = pd.DataFrame([
        {"date": r[0], "away_team": r[1], "home_team": r[2],
         "target_home_win": r[3]} for r in rows
    ])
    p = str(tmp_path / "games.parquet")
    df.to_parquet(p)
    return p


@pytest.fixture()
def corpus(tmp_path):
    d = tmp_path / "mlb"
    d.mkdir()
    return d


def test_clean_game_passes(corpus, tmp_path):
    # home (CLE) beats away (TEX): last tick home ahead, outcome=1 matches independent.
    _write_game(str(corpus), "2026-07-01", "TEXCLE", [
        _tick(0, 0, 1, "2026-07-01T22:00:00Z", 1.0, 0.55),
        _tick(5, 2, 8, "2026-07-01T23:30:00Z", 1.0, 0.90),
    ])
    idx = A.build_outcome_index(_index(tmp_path, [("2026-07-01", "TEX", "CLE", 1)]))
    g = A.audit_game(sorted(str(corpus / f) for f in os.listdir(str(corpus)))[0], idx)
    assert g["resolved"] and not g["label_bug"]
    assert not g["last_tick_contradicts"]


def test_planted_wrong_label_caught(corpus, tmp_path):
    # Independent final says home LOST (0) but joined label says home WON (1) -> bug -> drop.
    _write_game(str(corpus), "2026-07-01", "TEXCLE", [
        _tick(1, 6, 8, "2026-07-01T23:30:00Z", 1.0, 0.20),
    ])
    idx = A.build_outcome_index(_index(tmp_path, [("2026-07-01", "TEX", "CLE", 0)]))
    rep = A.run_audit(str(corpus), _index(tmp_path, [("2026-07-01", "TEX", "CLE", 0)]))
    assert rep["checks"]["outcome_cross_check"]["label_bugs"] == 1
    assert rep["dropped_games"] == 1
    # dropped tick was late (inn 8) -> late drop fraction non-zero, early zero
    assert rep["dropped_tick_frac_late"] == 1.0 and rep["dropped_tick_frac_early"] == 0.0


def test_planted_frozen_market_caught(corpus, tmp_path):
    # market_prob frozen 0.50 for >30min game-time while score moves 0 -> 4 runs.
    _write_game(str(corpus), "2026-07-01", "TEXCLE", [
        _tick(0, 0, 7, "2026-07-01T22:00:00Z", 1.0, 0.50),
        _tick(4, 0, 8, "2026-07-01T23:00:00Z", 1.0, 0.50),
    ])
    idx_path = _index(tmp_path, [("2026-07-01", "TEX", "CLE", 1)])
    g = A.audit_game(sorted(str(corpus / f) for f in os.listdir(str(corpus)))[0],
                     A.build_outcome_index(idx_path))
    assert g["stale_market"] and g["stale_late"] >= 1


def test_planted_ts_regression_caught(corpus, tmp_path):
    # inning goes 5 -> 3 within the game -> time regression flag.
    _write_game(str(corpus), "2026-07-01", "TEXCLE", [
        _tick(1, 0, 5, "2026-07-01T22:00:00Z", 1.0, 0.6),
        _tick(1, 0, 3, "2026-07-01T22:30:00Z", 1.0, 0.6),
    ])
    idx_path = _index(tmp_path, [("2026-07-01", "TEX", "CLE", 1)])
    g = A.audit_game(sorted(str(corpus / f) for f in os.listdir(str(corpus)))[0],
                     A.build_outcome_index(idx_path))
    assert g["time_regression"]


def test_whole_game_drop_semantics(corpus, tmp_path):
    # one buggy + one clean game; write_clean copies only the clean one, source untouched.
    _write_game(str(corpus), "2026-07-01", "TEXCLE", [   # bug: indep=0, label=1
        _tick(1, 6, 8, "2026-07-01T23:30:00Z", 1.0, 0.2)])
    _write_game(str(corpus), "2026-07-01", "KCTB", [     # clean: indep=1, label=1
        _tick(3, 1, 8, "2026-07-01T23:30:00Z", 1.0, 0.8)])
    idx_path = _index(tmp_path, [
        ("2026-07-01", "TEX", "CLE", 0),   # TEXCLE -> home CLE lost
        ("2026-07-01", "TAM", "KAN", 1)])  # TAM@KAN -> blob TB+KC=KCTB, home KC won
    rep = A.run_audit(str(corpus), idx_path)
    assert rep["dropped_games"] == 1
    clean = tmp_path / "clean"
    kept = A.write_clean(str(corpus), rep, str(clean))
    assert kept == 1
    names = os.listdir(str(clean))
    assert len(names) == 1 and "KCTB" in names[0]
    # source dir still has BOTH games (never row-surgery / never modified in place)
    assert len(os.listdir(str(corpus))) == 2


def test_truncated_comeback_not_dropped(corpus, tmp_path):
    # last tick shows home DOWN but independent final confirms home WON -> contradiction
    # flagged (informational) but NOT a label bug -> not dropped.
    _write_game(str(corpus), "2026-07-09", "LAATEX", [
        _tick(6, 6, 9, "2026-07-09T23:30:00Z", 1.0, 0.5)])  # tie at last capture, home won
    _write_game(str(corpus), "2026-07-01", "TEXCLE", [
        _tick(1, 5, 8, "2026-07-01T23:30:00Z", 1.0, 0.3)])  # home shown losing, but won
    idx_path = _index(tmp_path, [
        ("2026-07-09", "LAA", "TEX", 1), ("2026-07-01", "TEX", "CLE", 1)])
    rep = A.run_audit(str(corpus), idx_path)
    assert rep["dropped_games"] == 0
    assert rep["checks"]["monotone_sanity"]["last_tick_contradicts_outcome"] == 1
