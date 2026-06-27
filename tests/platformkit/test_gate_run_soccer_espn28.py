"""tests.platformkit.test_gate_run_soccer_espn28 -- OFFLINE gate-run checks.

Drives scripts.platformkit.gate_run_soccer_espn28.run on SMALL synthetic matches +
match_stats corpora (no parquet read of the real data, no network). Asserts the
gate's honesty rails hold: a PLANTED-NULL noise column REJECTS through the IDENTICAL
gate, the verdict carries NO $/ROI/edge field, nothing rejected is force-fed, the
verdict JSON is written, and the ESPN-28 native feed is reported INSUFFICIENT_DATA.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import scripts.platformkit.gate_run_soccer_espn28 as G


def _make_corpus(divs, n_per_team=40, seed=0):
    """Build a synthetic league with a real home-strength signal so the EW-Poisson
    BASE is skillful (degenerate guard passes), keyed with event_ids that join to the
    discipline layer 1:1."""
    rng = np.random.default_rng(seed)
    teams = [f"{divs}_T{i}" for i in range(10)]
    strength = {t: rng.normal(0, 0.6) for t in teams}
    rows_m, rows_s = [], []
    day = 0
    for _ in range(n_per_team):
        rng.shuffle(teams)
        for i in range(0, len(teams), 2):
            h, a = teams[i], teams[i + 1]
            day += 1
            date = pd.Timestamp("2020-01-01") + pd.Timedelta(days=day)
            lam_h = max(0.3, 1.4 + strength[h] - strength[a] + 0.25)
            lam_a = max(0.3, 1.4 + strength[a] - strength[h])
            hg, ag = int(rng.poisson(lam_h)), int(rng.poisson(lam_a))
            ftr = "H" if hg > ag else ("A" if ag > hg else "D")
            eid = f"{date:%Y%m%d}-{divs}-{h}-{a}"
            rows_m.append({"event_id": eid, "date": date, "div": divs,
                           "home_team": h, "away_team": a,
                           "fthg": hg, "ftag": ag, "ftr": ftr})
            rows_s.append({"event_id": eid, "date": date, "div": divs,
                           "home_team": h, "away_team": a,
                           "home_shots": 12, "away_shots": 10,
                           "home_sot": 5, "away_sot": 3,
                           "home_corners": rng.integers(2, 9),
                           "away_corners": rng.integers(2, 9),
                           "home_fouls": rng.integers(8, 15),
                           "away_fouls": rng.integers(8, 15),
                           "home_yellow": rng.integers(0, 4),
                           "away_yellow": rng.integers(0, 4),
                           "home_red": 0, "away_red": 0,
                           "home_sot_ratio": 5 / 12, "away_sot_ratio": 3 / 10})
    return pd.DataFrame(rows_m), pd.DataFrame(rows_s)


@pytest.fixture()
def synthetic(monkeypatch):
    """Two disjoint league pairs matching G._CORPUS_A / G._CORPUS_B."""
    ms, ss = [], []
    for dv, sd in (("E0", 1), ("E1", 2), ("SP1", 3), ("I1", 4)):
        m, s = _make_corpus(dv, n_per_team=45, seed=sd)
        ms.append(m)
        ss.append(s)
    matches = pd.concat(ms, ignore_index=True)
    match_stats = pd.concat(ss, ignore_index=True)
    # point ESPN-28 status + verdict output at the real (small) files / tmp is fine;
    # we only assert the INSUFFICIENT_DATA branch which reads a real thin file or none.
    return matches, match_stats


def test_run_writes_verdict_and_null_rejects(synthetic, tmp_path, monkeypatch):
    matches, match_stats = synthetic
    out_file = tmp_path / "soccer_espn28_gate.json"
    monkeypatch.setattr(G, "_VERDICT_OUT", out_file)
    res = G.run(eps=0.05, seed=0, matches=matches, match_stats=match_stats)

    # verdict JSON written
    assert out_file.exists()
    disk = json.loads(out_file.read_text())
    assert disk["layer"] == res["layer"]

    # planted-null MUST reject through the IDENTICAL gate
    assert res["null"]["column"] == G._NULL_COL
    assert res["null_rejects"] is True
    assert res["null"]["verdict"] in ("REJECT", "INVALID_BASE", "PARTIAL")


def test_base_skillful_and_layer_verdict(synthetic, tmp_path, monkeypatch):
    matches, match_stats = synthetic
    monkeypatch.setattr(G, "_VERDICT_OUT", tmp_path / "v.json")
    res = G.run(eps=0.05, seed=0, matches=matches, match_stats=match_stats)
    # the EW-Poisson base is a genuine, skillful baseline on a real-strength corpus
    assert res["base_skillful"] is True
    # the honest expectation is REJECT-scouting (no force-feed). Verdict is one of the
    # honest closed-dead-end states, never a silent SHIP without both-direction proof.
    assert res["verdict"] in ("REJECT", "SHIP", "INVALID_BASE", "NOT_TESTABLE")


def test_no_dollar_field_anywhere(synthetic, tmp_path, monkeypatch):
    matches, match_stats = synthetic
    monkeypatch.setattr(G, "_VERDICT_OUT", tmp_path / "v.json")
    res = G.run(eps=0.05, seed=0, matches=matches, match_stats=match_stats)
    # NO $/ROI/edge as a KEY anywhere in the verdict tree (the words may appear only
    # inside an explicit "no $/ROI/edge" caveat string, never as a numeric field).
    def _keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k.lower()
                yield from _keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from _keys(v)
    keys = set(_keys(res))
    for banned in ("roi", "edge", "profit", "dollar", "bankroll", "units", "pnl"):
        assert banned not in keys, banned
    # no "$<digit>" dollar amount anywhere in the serialized tree
    import re
    assert re.search(r"\$\s*\d", json.dumps(res)) is None
    assert "calibration only" in res["vs_close"].lower()


def test_nothing_rejected_force_fed(synthetic, tmp_path, monkeypatch):
    matches, match_stats = synthetic
    monkeypatch.setattr(G, "_VERDICT_OUT", tmp_path / "v.json")
    res = G.run(eps=0.05, seed=0, matches=matches, match_stats=match_stats)
    assert res["force_fed"] is False
    assert res["proposal_only"] is True
    # a non-SHIP layer is scouting-only (kept, never force-fed as a model feature)
    if res["verdict"] != "SHIP":
        assert res["scouting_only"] is True


def test_espn28_native_feed_insufficient(synthetic, tmp_path, monkeypatch):
    matches, match_stats = synthetic
    monkeypatch.setattr(G, "_VERDICT_OUT", tmp_path / "v.json")
    res = G.run(eps=0.05, seed=0, matches=matches, match_stats=match_stats)
    st = res["espn28_native_feed"]
    # the native ESPN-28 feed is honestly INSUFFICIENT_DATA (or absent) -- never gated
    assert st["verdict"] == "INSUFFICIENT_DATA"


def test_planted_null_no_outcome_dependence(synthetic, tmp_path, monkeypatch):
    """The planted null is pure noise -> its per-corpus feat_better must not both win
    at eps (it cannot replicate a real signal)."""
    matches, match_stats = synthetic
    monkeypatch.setattr(G, "_VERDICT_OUT", tmp_path / "v.json")
    res = G.run(eps=0.05, seed=0, matches=matches, match_stats=match_stats)
    n = res["null"]
    assert not (n["a_wins"] and n["b_wins"])
