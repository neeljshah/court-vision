"""S16: the runner screens from a claim queue, idles on empty, and never charges a T0/T1.

The ledger is always a TMP path and the results DB is always tmp_path -- the real
data/cache/eval_gate/backtest_fwer.jsonl is never opened by this file.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts.platformkit import foundry_runner as runner
from scripts.platformkit.foundry import results_db, tiers
from scripts.platformkit.foundry.grammar import Hypothesis

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md"
TEAMS = ("ATL", "BOS", "CHI", "DAL", "DEN", "GSW")
FAMILY = "s16_construct"


class _Exploded(Exception):
    """Raised if the legacy matrix is consulted on a queue pass."""


def _corpus(rows: int = 60) -> list:
    base, states = date(2026, 1, 5), []
    for index in range(rows):
        day = base + timedelta(days=(index // 5) * 7 + (index % 5))
        states.append({
            "game_id": "s%03d" % index, "state_ts": "%sT12:00:00" % day.isoformat(),
            "features": {"p_base": 0.4 + (index % 7) / 20.0},
            "feature_avail": {"p_base": "%sT00:00:00" % (day - timedelta(days=1)).isoformat()},
            "home": TEAMS[index % 6], "away": TEAMS[(index + 3) % 6],
            "outcome": int(index % 3 != 0),
            "devig_close_prob": 0.5 + 0.01 * ((index % 5) - 2)})
    return states


def _queue(tmp_path: Path, db, *, allow_charge: bool = False) -> runner.ScreenQueue:
    states = _corpus()
    rule = tiers.PromotionRule.from_spec(SPEC)
    part = tiers.partition_corpus(states, seed=rule.partition_seed)
    screen = [s for s in states if s["game_id"] in part.screen_ids]
    verdict = [s for s in states if s["game_id"] in part.verdict_ids]
    return runner.ScreenQueue(db, screen, runner._p_base_predict, part, rule,
                              tmp_path / "fwer.jsonl", verdict, "sha16", FAMILY,
                              poll_seconds=0.0, allow_charge=allow_charge)


def _isolate(tmp_path: Path, monkeypatch) -> None:
    """No production path is writable from this test: summary, heartbeat and trials are tmp."""
    monkeypatch.setattr(runner, "SUMMARY_PATH", tmp_path / "summary.jsonl")
    monkeypatch.setattr(runner, "HEARTBEAT_PATH", tmp_path / "heartbeat.json")
    monkeypatch.setattr(results_db, "TRIALS_DIR", tmp_path / "trials")
    monkeypatch.setattr(runner, "PASS_CONFIGS", _Exploded)
    monkeypatch.setattr(runner, "build_minutes_matrix",
                        lambda: (_ for _ in ()).throw(_Exploded("legacy matrix built")))


def _ledger_rows(path: Path) -> int:
    return len(path.read_text(encoding="ascii").splitlines()) if path.exists() else 0


def _seed(db, n: int) -> list:
    hashes = [db.upsert_hypothesis(
        Hypothesis("nba", "feat_%03d" % i, "raw", (), frozenset(), "pregame", "ml"),
        family=FAMILY) for i in range(n)]
    db.enqueue(hashes, "T0")
    return hashes


def test_empty_queue_idles_once_without_charging_or_building_the_legacy_matrix(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    with results_db.ResultsDB(tmp_path / "h.sqlite") as db:
        queue = _queue(tmp_path, db)
        results = runner.run(max_passes=1, queue=queue)
    assert len(results) == 1 and results[0]["idle"] is True
    assert results[0]["screens"] == 0 and results[0]["screened_n"] == {}
    assert _ledger_rows(tmp_path / "fwer.jsonl") == 0
    assert json.loads((tmp_path / "heartbeat.json").read_text(encoding="ascii"))["idle"] is True


def test_forty_seeded_hypotheses_are_screened_in_one_pass_with_zero_charges(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    with results_db.ResultsDB(tmp_path / "h.sqlite") as db:
        _seed(db, 40)
        summary = runner.run_pass(0, _queue(tmp_path, db), batch=50)
        screened = db._c.execute(
            "SELECT tier, count(*) FROM result GROUP BY tier").fetchall()
        assert not db.claim(1, tier="T0")           # every seeded row was claimed
    tiers_seen = {row[0]: row[1] for row in screened}
    assert summary["screens"] == 40 and summary["screened_n"] == {FAMILY: 40}
    assert tiers_seen["T0"] == 40 and tiers_seen["T1"] == 40
    assert summary["charges"] == 0 and summary["idle"] is False
    assert _ledger_rows(tmp_path / "fwer.jsonl") == 0
    lines = (tmp_path / "summary.jsonl").read_text(encoding="ascii").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["screened_n"] == {FAMILY: 40}


def test_a_charged_tier_is_refused_without_allow_charge(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    with results_db.ResultsDB(tmp_path / "h.sqlite") as db:
        queue = _queue(tmp_path, db)
        picks = [Hypothesis("nba", "feat_000", "raw", (), frozenset(), "pregame", "ml")]
        with pytest.raises(runner.ChargeNotAllowed):
            runner.run_charged(queue, picks, 40, FAMILY)
        assert _ledger_rows(tmp_path / "fwer.jsonl") == 0
        _seed(db, 3)
        summary = runner.run_pass(0, queue, batch=50)
    assert summary["promotions"] == 3 and summary["charges"] == 0
    assert _ledger_rows(tmp_path / "fwer.jsonl") == 0


def test_legacy_path_keeps_the_matrix_and_the_sleep_default(tmp_path, monkeypatch):
    """--legacy is the untouched path: same rotation, same 900 s default, same summary shape."""
    import inspect

    monkeypatch.setattr(runner, "SUMMARY_PATH", tmp_path / "summary.jsonl")
    monkeypatch.setattr(runner, "build_minutes_matrix", lambda: (None, []))
    monkeypatch.setattr(runner, "expanding_folds", lambda frame, folds: [(folds, folds)])
    assert inspect.signature(runner.run).parameters["sleep_seconds"].default == 900.0
    results = runner.run(max_passes=6, sleep_seconds=0)
    seen = {(item["pass_config"]["n_folds"], item["pass_config"]["embargo_blocks"])
            for item in results}
    assert seen == set(runner.PASS_CONFIGS) and len(results) == 6
    assert all("screened_n" not in item for item in results)
