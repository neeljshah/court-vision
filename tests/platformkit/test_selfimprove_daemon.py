"""Offline tests for the self-improvement daemon (injected clock/feeds/store).

Covers: ship a passing+improving+replicated candidate; reject+ledger a gate-failer;
atomic versioned-swap + current pointer; auto-rollback on injected regression;
checkpoint persists + run_forever RESUMES without reprocessing; REPLICATION_PENDING
on a single corpus; per-source error isolation. No network, no real corpora.
"""
from __future__ import annotations

import json
import os
import sys
import pathlib

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.improve import artifact_store as store  # noqa: E402
from scripts.platformkit.improve import selfimprove_daemon as D  # noqa: E402
from scripts.platformkit.improve.checkpoint import load_checkpoint  # noqa: E402


# --------------------------------------------------------------------------- helpers
def _two_corpus_folds():
    """Primary + one extra corpus, every fold positive -> 2 corpora replicated."""
    fold_results = [{"delta": 0.01, "metric": "brier", "fold_id": 0},
                    {"delta": 0.02, "metric": "brier", "fold_id": 1}]
    corpora = [{"corpus_id": "B", "folds": [{"delta": 0.005, "metric": "brier"}]}]
    return fold_results, corpora


def _candidate(*, ship=True, oos=True, two_corpora=True, held_out_regress=False,
               payload=None):
    """A gate-agnostic candidate: we use an INJECTED gate_fn so the verdict is fixed."""
    folds, corpora = _two_corpus_folds()
    if not two_corpora:
        corpora = []  # only the primary corpus replicates
    cand = {
        "base_preds": [0.5, 0.5], "cand_preds": [0.4, 0.6], "y": [0, 1], "kind": "prob",
        "fold_results": folds, "corpora": corpora,
        "stability_metric_fn": lambda a, b: 0.0, "stability_data": [],
        "train_features": {}, "infer_features": {},
        "artifact": None, "oos_improves": oos,
        "payload": payload or {"map": "v1"},
    }
    if held_out_regress:
        cand["held_out_check"] = lambda rec: True   # always "regressed"
    else:
        cand["held_out_check"] = lambda rec: False
    cand["_ship"] = ship
    return cand


def _gate_fn_from_candidate(candidate):
    """Injected gate: returns ship per the candidate's _ship flag (no real math)."""
    if candidate.get("_ship"):
        return {"ship": True, "gate_results": {}, "reasons": ["passed every gate"]}
    return {"ship": False, "gate_results": {}, "reasons": ["seed_stability: unstable"]}


def _paths(tmp_path):
    root = str(tmp_path / "artifacts")
    ckpt = str(tmp_path / "checkpoint.json")
    proposals = tmp_path / "proposals.jsonl"
    reject = tmp_path / "reject.jsonl"
    status = tmp_path / "status.jsonl"
    return root, ckpt, proposals, reject, status


def _kid(i):
    """An id/date-keyed settled game (game_id + sortable high-water key)."""
    return {"game_id": "G%02d" % i, "commence": "2026-06-%02d" % (i + 1),
            "key": "2026-06-%02d|G%02d" % (i + 1, i)}


def _keyed_feed(ids):
    """A feed that returns the games in `ids` whose key > the high-water `since`."""
    games = [_kid(i) for i in ids]
    return lambda n, since="": [g for g in games if g["key"] > (since or "")]


def _run(name, candidate, tmp_path, **kw):
    root, ckpt, proposals, reject, status = _paths(tmp_path)
    return D.run_cycle(
        name=name,
        settled_games_fn=_keyed_feed([0, 1, 2]),
        recalibrate_fn=lambda n, settled, window: candidate,
        gate_fn=_gate_fn_from_candidate,
        store_root=root, ckpt_path=ckpt,
        proposals_path=proposals, reject_path=reject, status_path=status,
        now=1000.0, **kw)


# --------------------------------------------------------------------------- tests
def test_ship_passing_improving_replicated(tmp_path):
    root, ckpt, proposals, _, _ = _paths(tmp_path)
    res = _run("nba_winprob", _candidate(), tmp_path)
    assert res.decision == D.SHIP
    assert res.shipped_version == 1
    # atomic versioned-swap + current pointer
    assert store.read_pointer("nba_winprob", root) == 1
    rec = store.current("nba_winprob", root)
    assert rec["payload"]["map"] == "v1"
    # proposal emitted, NOT to MEMORY.md
    lines = proposals.read_text().strip().splitlines()
    assert json.loads(lines[-1])["decision"] == D.SHIP


def test_reject_gate_failer_is_ledgered(tmp_path):
    root, _, _, reject, _ = _paths(tmp_path)
    res = _run("nba_winprob", _candidate(ship=False), tmp_path)
    assert res.decision == D.REJECT
    assert store.read_pointer("nba_winprob", root) is None  # nothing went live
    led = [json.loads(x) for x in reject.read_text().strip().splitlines()]
    assert led and led[-1]["decision"] == D.REJECT


def test_replication_pending_on_one_corpus(tmp_path):
    res = _run("nba_winprob", _candidate(two_corpora=False), tmp_path)
    assert res.decision == D.REPLICATION_PENDING
    assert res.shipped_version is None  # never ship on one corpus


def test_atomic_versioned_swap_and_prev_retention(tmp_path):
    root, ckpt, proposals, reject, status = _paths(tmp_path)
    # first cycle ships v1
    _run("k", _candidate(payload={"map": "v1"}), tmp_path)
    # second cycle: a NEW settled game (higher key than cycle-1's high-water) ships v2
    D.run_cycle(name="k",
                settled_games_fn=_keyed_feed([9]),
                recalibrate_fn=lambda n, s, w: _candidate(payload={"map": "v2"}),
                gate_fn=_gate_fn_from_candidate, store_root=root, ckpt_path=ckpt,
                proposals_path=proposals, reject_path=reject, status_path=status,
                now=1001.0)
    assert store.list_versions("k", root) == [1, 2]
    assert store.read_pointer("k", root) == 2
    assert store.current("k", root)["payload"]["map"] == "v2"


def test_auto_rollback_on_injected_regression(tmp_path):
    root, ckpt, proposals, reject, status = _paths(tmp_path)
    # v1 ships clean
    _run("k", _candidate(payload={"map": "v1"}), tmp_path)
    assert store.read_pointer("k", root) == 1
    # v2 ships then its held-out check reports a regression -> auto-rollback to v1
    res = D.run_cycle(
        name="k",
        settled_games_fn=_keyed_feed([9]),
        recalibrate_fn=lambda n, s, w: _candidate(payload={"map": "v2"},
                                                  held_out_regress=True),
        gate_fn=_gate_fn_from_candidate, store_root=root, ckpt_path=ckpt,
        proposals_path=proposals, reject_path=reject, status_path=status, now=1002.0)
    assert res.decision == D.REJECT  # rolled back -> not a live ship
    assert res.rolled_back_to == 1
    assert store.read_pointer("k", root) == 1  # live pointer restored to v1
    # rollback audit row written
    log = (pathlib.Path(root) / "k" / "rollback_log.jsonl").read_text()
    assert "held-out regression" in log


def test_per_source_error_isolation(tmp_path):
    root, ckpt, _, _, status = _paths(tmp_path)

    def _dead(n, since=0):
        raise RuntimeError("source down")

    res = D.run_cycle(
        name="k", settled_games_fn=_dead,
        recalibrate_fn=lambda n, s, w: _candidate(),
        gate_fn=_gate_fn_from_candidate, store_root=root, ckpt_path=ckpt,
        status_path=status, now=1.0)
    assert res.decision == D.ERROR  # isolated, did not raise
    assert "source_error" in status.read_text()


def test_checkpoint_persists_and_run_forever_resumes(tmp_path):
    root, ckpt, proposals, reject, status = _paths(tmp_path)
    # 5 id/date-keyed games. The feed returns one NEW game per cursor advance (those
    # whose key > the high-water), so each cycle folds exactly the next game in order.
    GAMES = [_kid(i) for i in range(5)]
    served = {"calls": []}

    def feed(n, since=""):
        served["calls"].append(since)
        nxt = [g for g in GAMES if g["key"] > (since or "")]
        return nxt[:1]  # one new game per cycle, strictly after the cursor

    def recal(n, s, w):
        return _candidate(payload={"w": w})

    D.run_forever(
        names=["k"], settled_games_fn=feed, recalibrate_fn=recal,
        gate_fn=_gate_fn_from_candidate, clock=lambda: 1.0,
        sleep=lambda s: None, max_cycles=2, store_root=root, ckpt_path=ckpt,
        proposals_path=proposals, reject_path=reject, status_path=status)
    ck = load_checkpoint(ckpt)
    assert ck.cursor("k")["high_water"] == GAMES[1]["key"]  # folded G0,G1

    # RESTART: a brand-new run_forever resumes from the persisted HIGH-WATER, never
    # re-serving already-folded games (since starts at the persisted key, not "").
    served["calls"].clear()
    D.run_forever(
        names=["k"], settled_games_fn=feed, recalibrate_fn=recal,
        gate_fn=_gate_fn_from_candidate, clock=lambda: 2.0,
        sleep=lambda s: None, max_cycles=2, store_root=root, ckpt_path=ckpt,
        proposals_path=proposals, reject_path=reject, status_path=status)
    assert served["calls"][0] == GAMES[1]["key"]  # resumed at high-water, not ""
    assert load_checkpoint(ckpt).cursor("k")["high_water"] == GAMES[3]["key"]


def test_out_of_order_late_settle_is_not_skipped(tmp_path):
    """BUG B regression: a game that settles OUT OF ORDER (earlier commence -> LOWER key
    than an already-advanced high-water) is still folded. Dedup is by seen_ids (game_id),
    and the daemon threads seen_ids to a seen_ids-aware feed -- never a key-skip.
    """
    root, ckpt, proposals, reject, status = _paths(tmp_path)
    A = {"game_id": "Ga", "commence": "2026-06-10", "key": "2026-06-10|Ga"}
    B = {"game_id": "Gb", "commence": "2026-06-11", "key": "2026-06-11|Gb"}  # higher key
    boards = [[B], [A, B]]
    st = {"i": 0}

    def feed(n, since="", seen_ids=None):  # seen_ids-aware -> daemon passes the seen set
        seen = set(seen_ids or ())
        b = boards[min(st["i"], len(boards) - 1)]
        st["i"] += 1
        return [g for g in b if g["game_id"] not in seen]

    kw = dict(recalibrate_fn=lambda n, s, w: _candidate(), gate_fn=_gate_fn_from_candidate,
              store_root=root, ckpt_path=ckpt, proposals_path=proposals,
              reject_path=reject, status_path=status)
    # cycle 1 folds B, advances high-water to B's (higher) key
    D.run_cycle(name="k", settled_games_fn=feed, now=1.0, **kw)
    assert load_checkpoint(ckpt).cursor("k")["high_water"] == "2026-06-11|Gb"
    # cycle 2: A settles late with a LOWER key -> must STILL be folded (seen=Gb only)
    res = D.run_cycle(name="k", settled_games_fn=feed, now=2.0, **kw)
    assert res.n_new == 1  # Ga was folded, not key-skipped
    assert "Ga" in set(load_checkpoint(ckpt).cursor("k")["seen_ids"])


def test_count_replicated_corpora_dedups_by_corpus_id():
    """The primary corpus must not be DOUBLE-COUNTED when it also appears in `corpora`
    under the same id -- two listings of ONE corpus is still ONE replicated corpus.
    """
    folds = [{"delta": 0.01}, {"delta": 0.02}]              # primary: all-positive
    # the SAME corpus listed again with the primary's id -> must collapse to 1
    dup = {"primary_corpus_id": "A", "fold_results": folds,
           "corpora": [{"corpus_id": "A", "folds": [{"delta": 0.03}]}]}
    assert D._count_replicated_corpora(dup) == 1, "double-counted one corpus"
    # a genuinely DISTINCT second corpus -> 2
    two = {"primary_corpus_id": "A", "fold_results": folds,
           "corpora": [{"corpus_id": "B", "folds": [{"delta": 0.03}]}]}
    assert D._count_replicated_corpora(two) == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
