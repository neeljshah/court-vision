"""Archive, p-value, schema, and migration checks for the foundry results DB.

S155 split (2026-09-04): the real ledger data/cache/eval_gate/backtest_fwer.jsonl is never touched -- every _charge_ledger call here is against tmp_path.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, replace

import pytest

from scripts.platformkit.eval_gate.backtest_runner import _charge_ledger
from scripts.platformkit.eval_gate.deflated_metrics import deflated_p
from scripts.platformkit.foundry.grammar import Hypothesis, semantic_hash
from scripts.platformkit.foundry.results_db import TierResult, recompute_deflated_p, trial_artifact_path

CONDITIONING = frozenset(("phase=period", "rest=NORMAL", "month=2026-09", "confidence=T2"))
HYPOTHESIS = Hypothesis("nba", "pace_diff_asof", "ew", (("halflife", 5),), CONDITIONING, "pregame", "ml")
CORPUS, UNIT, SHA, TIER = "nba_gate_v3", "game", "sha_corpus_v1", "T2"


def _k(ledger):
    """Current global K in a ledger file: 0 when it does not exist yet."""
    if not ledger.exists():
        return 0
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    return max((int(r["k_cumulative"]) for r in rows), default=0)


def _propose(db, hypothesis, ledger, k_now=None):
    """The proposer contract: look up first, charge only on a miss.

    Returns ("lookup", row) or ("trial", row). Indexing is not a trial.
    """
    digest = db.upsert_hypothesis(hypothesis, family="pace")
    hit = db.lookup(digest, TIER, CORPUS, UNIT, SHA, k_now=k_now)
    if hit is not None:
        return "lookup", hit
    charge = _charge_ledger(ledger, "spec:pace", "nba", "2024-10-01", "2025-04-01", family="pace", hypothesis_hash=digest, tier=TIER)
    db.record(TierResult(
        hash=digest, tier=TIER, corpus=CORPUS, corpus_unit=UNIT, corpus_sha=SHA,
        n=412, n_eff=380.5, brier_model=0.2201, brier_close=0.2198, dm_stat=-0.41,
        raw_p=0.34, k_family=charge.get("k_family"), k_global=charge["k_cumulative"],
        deflated_p=deflated_p(0.34, charge["k_cumulative"]), pbo=0.48, verdict="MATCH",
        artifact_path=str(trial_artifact_path(digest, TIER, UNIT)), prereg_sha256="0" * 64))
    return "trial", db.lookup(digest, TIER, CORPUS, UNIT, SHA, k_now=k_now)


def test_reproposal_is_a_lookup_and_charges_nothing(tmp_path, results_db):
    """Denominator = 2 proposals of the same hash. Bar = 1 trial + 1 lookup, K flat."""
    ledger = tmp_path / "backtest_fwer.jsonl"
    with results_db as db:
        first_kind, _ = _propose(db, HYPOTHESIS, ledger)
        k_after_first = _k(ledger)
        second_kind, second = _propose(db, HYPOTHESIS, ledger)
        k_after_second = _k(ledger)
        assert (first_kind, second_kind) == ("trial", "lookup")
        assert k_after_first == 1 and k_after_second == 1  # K UNCHANGED on re-proposal
        assert db._c.execute("SELECT COUNT(*) FROM result").fetchone()[0] == 1
        assert second["k_at_run"] == 1


def test_changed_corpus_sha_is_a_fresh_trial(results_db):
    """SF-13: corpus_sha is in the UNIQUE key, so a changed corpus never hits."""
    with results_db as db:
        digest = db.upsert_hypothesis(HYPOTHESIS)
        db.record(_result(digest, corpus_sha=SHA))
        assert db.lookup(digest, TIER, CORPUS, UNIT, SHA) is not None
        assert db.lookup(digest, TIER, CORPUS, UNIT, "sha_corpus_v2") is None
        db.record(_result(digest, corpus_sha="sha_corpus_v2"))
        assert db._c.execute("SELECT COUNT(*) FROM result").fetchone()[0] == 2


def test_stale_k_lookup_flags_rescore(results_db):
    """SF-14: never serve the stored deflated_p as current once K has moved."""
    with results_db as db:
        digest = db.upsert_hypothesis(HYPOTHESIS)
        db.record(_result(digest, k_global=3, raw_p=0.02, deflated_p=deflated_p(0.02, 3)))
        same = db.lookup(digest, TIER, CORPUS, UNIT, SHA, k_now=3)
        assert same["verdict_needs_rescore"] is False and same["k_at_run"] == 3
        stale = db.lookup(digest, TIER, CORPUS, UNIT, SHA, k_now=14)
        assert stale["verdict_needs_rescore"] is True and stale["k_at_run"] == 3
        assert stale["deflated_p"] == pytest.approx(0.06)
        assert recompute_deflated_p(stale, 14) == pytest.approx(0.28)


def test_same_hash_different_raw_params_raises(results_db):
    """SF-12: a grid-snap collision is surfaced as IntegrityError, never merged."""
    other = Hypothesis("nba", "pace_diff_asof", "raw", (("unused", "a"),), CONDITIONING, "pregame", "ml")
    twin = Hypothesis("nba", "pace_diff_asof", "raw", (("unused", "b"),), CONDITIONING, "pregame", "ml")
    assert semantic_hash(other) == semantic_hash(twin)  # unused params are grid-snapped away
    with results_db as db:
        db.upsert_hypothesis(other)
        db.upsert_hypothesis(other)  # identical raw params -> idempotent
        with pytest.raises(sqlite3.IntegrityError):
            db.upsert_hypothesis(twin)


def test_round_trip_every_column(results_db):
    with results_db as db:
        digest = db.upsert_hypothesis(HYPOTHESIS, family="pace", runtime_available=False, grammar_version="s11", created_at="2026-09-03T00:00:00+00:00")
        hypothesis_row = dict(db._c.execute("SELECT * FROM hypothesis").fetchone())
        assert hypothesis_row == {
            "hash": digest, "family": "pace", "sport": "nba", "feature": "pace_diff_asof",
            "transform": "ew", "params": '[["halflife", 5]]',
            "conditioning": json.dumps(sorted(CONDITIONING)), "horizon": "pregame",
            "market": "ml", "runtime_available": 0, "created_at": "2026-09-03T00:00:00+00:00",
            "grammar_version": "s11"}
        # S66: family / runtime_available now survive the round trip. Before the fix
        # this read back as HYPOTHESIS (family="") -- the stored "pace" was dropped.
        assert db.get_hypothesis(digest) == replace(HYPOTHESIS, family="pace", runtime_available=False)
        db.record(_result(digest))
        row = db.lookup(digest, TIER, CORPUS, UNIT, SHA)
        expected = {"id": 1, "hash": digest, "tier": TIER, "corpus": CORPUS,
                    "corpus_unit": UNIT, "corpus_sha": SHA, "n": 412, "n_eff": 380.5,
                    "brier_model": 0.2201, "brier_close": 0.2198, "dm_stat": -0.41,
                    "raw_p": 0.34, "k_family": 1, "k_global": 7, "deflated_p": 1.0,
                    "screen_p": None, "pbo": 0.48, "verdict": "MATCH",
                    "artifact_path": str(trial_artifact_path(digest, TIER, UNIT)),
                    "prereg_sha256": "0" * 64, "run_at": "2026-09-03T01:00:00+00:00",
                    "k_at_run": 7, "verdict_needs_rescore": False}
        assert row == expected
        assert str(trial_artifact_path(digest, TIER, UNIT)).endswith("{0}_{1}_{2}.json".format(digest, TIER, UNIT))


def test_unique_constraint_rejects_a_duplicate_trial(results_db):
    with results_db as db:
        digest = db.upsert_hypothesis(HYPOTHESIS)
        db.record(_result(digest))
        with pytest.raises(sqlite3.IntegrityError):
            db.record(_result(digest))


def test_family_p_values_tier_filter_and_screen_p_column(results_db):
    """S74 construct: T1 SCREEN p-values index separately from charged T2 p-values."""
    rows = (("screen", "fam74", "T1", None, 0.03), ("charged_one", "fam74", "T2", 0.10, None), ("charged_two", "fam74", "T2", 0.20, None), ("other", "other", "T2", 0.40, None))
    with results_db as db:
        for feature, family, tier, raw_p, screen_p in rows:
            digest = db.upsert_hypothesis(replace(HYPOTHESIS, feature="s74_" + feature, family=family))
            result = asdict(_result(digest, tier=tier, raw_p=raw_p, verdict="SCREEN" if tier == "T1" else "MATCH", deflated_p=0.0 if raw_p is None else deflated_p(raw_p, 7)))
            if screen_p is not None:
                result["screen_p"] = screen_p
            db.record(result)
        columns = [row[1] for row in db._c.execute("PRAGMA table_info(result)")]
        assert "screen_p" in columns
        assert db.family_p_values("fam74") == [0.10, 0.20]
        assert db.family_p_values("fam74", tier="T1") == [0.03]
        assert db.family_p_values("fam74", tier="T2") == [0.10, 0.20]
        assert [tuple(row) for row in db._c.execute("SELECT h.family, r.tier, r.raw_p, r.screen_p FROM result r " "JOIN hypothesis h ON h.hash=r.hash ORDER BY r.id")] == [("fam74", "T1", None, 0.03), ("fam74", "T2", 0.10, None), ("fam74", "T2", 0.20, None), ("other", "T2", 0.40, None)]


def _result(hash, **overrides):
    fields = dict(hash=hash, tier=TIER, corpus=CORPUS, corpus_unit=UNIT, corpus_sha=SHA,
                  n=412, n_eff=380.5, brier_model=0.2201, brier_close=0.2198, dm_stat=-0.41,
                  raw_p=0.34, k_family=1, k_global=7, deflated_p=deflated_p(0.34, 7), pbo=0.48,
                  verdict="MATCH", artifact_path=str(trial_artifact_path(hash, TIER, UNIT)),
                  prereg_sha256="0" * 64, run_at="2026-09-03T01:00:00+00:00")
    fields.update(overrides)
    return TierResult(**fields)
