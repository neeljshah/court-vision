"""Red-team regression tests (fix phase 2026-09-01).

Pins the fixes for the confirmed breaches:
  - walk_forward deep-copies states: predictor-side dict mutation cannot poison
    a later invocation over the same list (attack a, leak-contract ledger);
  - the test view never carries the raw-row "index" pointer (attack c);
  - backtest_runner refuses a corpus with duplicate game_id (close side-table
    collapse + double-weighted headline scores);
  - combo_search refuses an unregistered search (rotated ledger path or
    narrowed lambda grid) without the explicit labelled override (R13);
  - concurrent ledger charges neither tear the file nor lose updates.
"""
from __future__ import annotations

import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scripts.platformkit.eval_gate import backtest_runner, combo_search
from scripts.platformkit.eval_gate.walkforward import walk_forward


def _state(game_id: str, ts: str, home: str, away: str) -> dict:
    return {"game_id": game_id, "state_ts": ts, "home": home, "away": away,
            "features": {"x": 0.5}, "feature_avail": {"x": ts[:10] + "T00:00:00"},
            "devig_close_prob": 0.6, "truth_wp": 0.5, "outcome": 1}


def _states(n: int = 6) -> list[dict]:
    # distinct teams -> no purge/embargo, every prior state lands in train
    return [_state(f"g{i}", f"2024-02-{10 + i:02d}T19:00:00", f"H{i}", f"V{i}")
            for i in range(n)]


def test_predictor_mutation_cannot_poison_later_invocations():
    states = _states()
    snapshot = copy.deepcopy(states)
    stash: dict = {}

    def malicious(train, test, _inside):
        stash[test["game_id"]] = test["features"]        # keep the handed-out dict
        for row in train:                                 # outcome visible via train
            if row["game_id"] in stash:
                stash[row["game_id"]]["own_outcome"] = float(row["outcome"])
                row["features"]["plant"] = 1.0            # poison attempt via train
        return 0.5

    walk_forward(states, malicious)
    assert states == snapshot                             # caller's list untouched

    leaked = []

    def probe(train, test, _inside):
        if "own_outcome" in test["features"] or "plant" in test["features"]:
            leaked.append(test["game_id"])
        return 0.5

    walk_forward(states, probe)
    assert leaked == []


def test_index_key_never_reaches_the_test_view():
    states = _states(3)
    for i, s in enumerate(states):
        s["index"] = i

    def probe(train, test, _inside):
        assert "index" not in test
        return 0.5

    walk_forward(states, probe)


def test_duplicate_game_id_is_refused(tmp_path: Path, monkeypatch):
    dup = [_state("same", "2024-02-10T19:00:00", "H0", "V0"),
           _state("same", "2024-02-11T19:00:00", "H1", "V1")]
    monkeypatch.setattr(backtest_runner, "load_states", lambda *a, **k: dup)
    with pytest.raises(ValueError, match="duplicate game_id"):
        backtest_runner.run_backtest(
            "scripts.platformkit.eval_gate.backtest_runner:uniform_half",
            "basketball_nba", "2024-02-01", "2024-02-28",
            ledger_path=tmp_path / "fwer.jsonl", allow_noncanonical_ledger=True)


def test_unregistered_search_is_refused(tmp_path: Path):
    # The registration guard runs before anything else touches frame or ledger.
    with pytest.raises(ValueError, match="unregistered search"):
        combo_search.run_combo_search(None, ["noise"],
                                      ledger_path=tmp_path / "rotated.json")
    with pytest.raises(ValueError, match="unregistered search"):
        combo_search.run_combo_search(None, ["noise"],
                                      ledger_path=combo_search.CANONICAL_LEDGER,
                                      lambdas=(0.1,))


def test_concurrent_family_ledger_charges_neither_tear_nor_lose(tmp_path: Path):
    path = tmp_path / "k.json"
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(lambda _i: combo_search._ledger(path, 1), range(40)))
    data = json.loads(path.read_text(encoding="ascii"))   # never torn
    assert data[combo_search.FAMILY] == 40                # no lost updates


def test_concurrent_backtest_charges_do_not_lose_updates(tmp_path: Path):
    path = tmp_path / "fwer.jsonl"
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(lambda i: backtest_runner._charge_ledger(path, f"p{i}", "nba", "a", "b"),
                    range(30)))
    rows = [json.loads(line) for line in path.read_text(encoding="ascii").splitlines() if line.strip()]
    assert len(rows) == 30
    assert max(r["k_cumulative"] for r in rows) == 30


def test_ledger_write_survives_a_transient_replace_failure(tmp_path: Path, monkeypatch):
    # A Windows sharing violation on os.replace used to crash a live gate call
    # (2/60 concurrent charges); the replace is retried instead.
    path = tmp_path / "k.json"
    real, calls = os.replace, {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(5, "Access is denied")
        return real(src, dst)

    monkeypatch.setattr(combo_search.os, "replace", flaky)
    assert combo_search._ledger(path, 3) == 3
    assert calls["n"] == 2
    assert json.loads(path.read_text(encoding="ascii"))[combo_search.FAMILY] == 3
