"""Offline tests for the LIVING in-game refresh runner (injected clock/feeds/parquets).

Covers: refresh_cycle appends only NEW settled games (dedup by game_id); re-gates +
re-fits; honesty-gated SWAP only when the gate passes; DOWNGRADES provenance + rolls
back when an injected regression makes a sport stop replicating; checkpoint advances +
resumes without reprocessing; per-sport isolation. No network, no real corpora.
"""
from __future__ import annotations

import json
import sys
import pathlib

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.improve import artifact_store as store  # noqa: E402
from scripts.platformkit.ingame import ingame_refresh_runner as R  # noqa: E402
from scripts.platformkit.improve.checkpoint import load_checkpoint  # noqa: E402


# --------------------------------------------------------------------------- fakes
def _states_for(gid, n=3):
    """A short frozen-schema state series for one fake game."""
    return [{"sport": "mlb", "game_id": gid, "asof_idx": i,
             "state_diff": float(i - 1), "frac_elapsed": (i + 1) / 4.0,
             "p0": 0.55, "outcome": 1} for i in range(n)]


def _ingest_fn(sport, game):
    gid = game["game_id"] if isinstance(game, dict) else game
    return _states_for(gid)


class _Verdict:
    def __init__(self, v):
        self.verdict = v


def _paths(tmp_path):
    return {
        "store_root": str(tmp_path / "artifacts"),
        "state_dir": tmp_path / "states",
        "ckpt_path": str(tmp_path / "ckpt.json"),
        "proposals_path": tmp_path / "proposals.jsonl",
        "status_path": tmp_path / "status.jsonl",
    }


def _gate(verdict):
    return lambda sport: _Verdict(verdict)


def _fit(verdict, *, fit_ok=True, status="proven"):
    return lambda sport: {"sport": sport, "verdict": verdict,
                          "prior_status": status, "fit_ok": fit_ok,
                          "payload": {"fit_ok": fit_ok}}


# --------------------------------------------------------------------------- tests
def test_appends_only_new_games_dedup(tmp_path):
    import pandas as pd
    kw = _paths(tmp_path)
    feed = lambda s, since=0: [{"game_id": "G1"}, {"game_id": "G2"}]
    res = R.refresh_cycle("mlb", settled_games_fn=feed, ingest_fn=_ingest_fn,
                          gate_fn=_gate("REPLICATED"), fit_fn=_fit("REPLICATED"),
                          now=1000.0, **kw)
    assert res.n_new_games == 2
    assert res.n_new_states == 6  # 2 games * 3 states
    # states landed in the refresh corpora
    paths = R._corpus_paths("mlb", state_dir=kw["state_dir"])
    ids = R._existing_game_ids(paths)
    assert ids == {"G1", "G2"}
    # re-feed the SAME games + one new -> only the new one is folded (dedup)
    feed2 = lambda s, since=0: [{"game_id": "G1"}, {"game_id": "G3"}]
    res2 = R.refresh_cycle("mlb", settled_games_fn=feed2, ingest_fn=_ingest_fn,
                           gate_fn=_gate("REPLICATED"), fit_fn=_fit("REPLICATED"),
                           now=1001.0, **kw)
    assert res2.n_new_games == 1  # only G3
    assert R._existing_game_ids(paths) == {"G1", "G2", "G3"}


def test_swaps_artifact_only_when_gate_passes(tmp_path):
    kw = _paths(tmp_path)
    feed = lambda s, since=0: [{"game_id": "G1"}]
    res = R.refresh_cycle("mlb", settled_games_fn=feed, ingest_fn=_ingest_fn,
                          gate_fn=_gate("REPLICATED"), fit_fn=_fit("REPLICATED"),
                          now=1.0, **kw)
    assert res.decision == R.SWAPPED
    assert store.read_pointer("mlb", kw["store_root"]) == 1
    assert store.current("mlb", kw["store_root"])["payload"]["verdict"] == "REPLICATED"


def test_no_swap_when_gate_fails_from_cold(tmp_path):
    kw = _paths(tmp_path)
    feed = lambda s, since=0: [{"game_id": "G1"}]
    # REJECT with no prior verdict -> not a downgrade either -> HELD, nothing live
    res = R.refresh_cycle("mlb", settled_games_fn=feed, ingest_fn=_ingest_fn,
                          gate_fn=_gate("REJECT"), fit_fn=_fit("REJECT", status="none"),
                          now=1.0, **kw)
    assert res.decision == R.HELD
    assert store.read_pointer("mlb", kw["store_root"]) is None


def test_downgrades_provenance_when_stops_replicating(tmp_path):
    kw = _paths(tmp_path)
    # cycle 1: REPLICATED (proven) ships v1
    R.refresh_cycle("mlb", settled_games_fn=lambda s, since=0: [{"game_id": "G1"}],
                    ingest_fn=_ingest_fn, gate_fn=_gate("REPLICATED"),
                    fit_fn=_fit("REPLICATED"), now=1.0, **kw)
    assert store.current("mlb", kw["store_root"])["payload"]["prior_status"] == "proven"
    # cycle 2: MORE data -> now only REJECT (stops replicating) -> DOWNGRADE + swap
    res = R.refresh_cycle(
        "mlb", settled_games_fn=lambda s, since=0: [{"game_id": "G2"}],
        ingest_fn=_ingest_fn, gate_fn=_gate("REJECT"),
        fit_fn=_fit("REJECT", status="none"), now=2.0, **kw)
    assert res.decision == R.DOWNGRADED
    assert res.prev_verdict == "REPLICATED" and res.verdict == "REJECT"
    # served model now reflects current truth (base-only), never stale 'proven'
    live = store.current("mlb", kw["store_root"])["payload"]
    assert live["prior_status"] == "none" and live["verdict"] == "REJECT"
    # the downgrade reason was logged to proposals (NOT MEMORY.md)
    last = json.loads(kw["proposals_path"].read_text().strip().splitlines()[-1])
    assert last["decision"] == "DOWNGRADED" and last["sport"] == "mlb"


def test_auto_rollback_on_injected_regression(tmp_path):
    kw = _paths(tmp_path)
    # v1 ships clean (fit_ok True)
    R.refresh_cycle("mlb", settled_games_fn=lambda s, since=0: [{"game_id": "G1"}],
                    ingest_fn=_ingest_fn, gate_fn=_gate("REPLICATED"),
                    fit_fn=_fit("REPLICATED"), now=1.0, **kw)
    assert store.read_pointer("mlb", kw["store_root"]) == 1
    # cycle 2: gate passes but the re-fit artifact is broken (fit_ok False) ->
    # held-out check fails -> auto-rollback to v1
    res = R.refresh_cycle(
        "mlb", settled_games_fn=lambda s, since=0: [{"game_id": "G2"}],
        ingest_fn=_ingest_fn, gate_fn=_gate("REPLICATED"),
        fit_fn=_fit("REPLICATED", fit_ok=False), now=2.0, **kw)
    assert res.decision == R.ROLLED_BACK
    assert res.rolled_back_to == 1
    assert store.read_pointer("mlb", kw["store_root"]) == 1  # restored to v1
    log = (pathlib.Path(kw["store_root"]) / "mlb" / "rollback_log.jsonl").read_text()
    assert "held-out regression" in log


def test_checkpoint_advances_and_resumes_without_reprocessing(tmp_path):
    kw = _paths(tmp_path)
    served = {"sinces": []}
    # an id/date-keyed feed: each game carries a sortable key; settled_since semantics
    # are emulated by returning only games whose key > the high-water `since`.
    ALL = [{"game_id": "G%d" % i, "commence": "2026-06-1%d" % i, "key": "2026-06-1%d|G%d" % (i, i)}
           for i in range(3)]

    def feed(s, since=""):
        served["sinces"].append(since)
        return [g for g in ALL if g["key"] > (since or "")]

    R.run_refresh_forever(
        sports=["mlb"], settled_games_fn=feed, ingest_fn=_ingest_fn,
        gate_fn=_gate("REPLICATED"), fit_fn=_fit("REPLICATED"),
        clock=lambda: 1.0, sleep=lambda s: None, max_cycles=2, **kw)
    cur = load_checkpoint(kw["ckpt_path"]).cursor("mlb")
    assert cur["high_water"] == "2026-06-12|G2"  # advanced past the last folded game
    assert R._existing_game_ids(R._corpus_paths("mlb", state_dir=kw["state_dir"])) == \
        {"G0", "G1", "G2"}

    # RESTART: a fresh run resumes AT the persisted HIGH-WATER, never reprocessing.
    served["sinces"].clear()
    R.run_refresh_forever(
        sports=["mlb"], settled_games_fn=feed, ingest_fn=_ingest_fn,
        gate_fn=_gate("REPLICATED"), fit_fn=_fit("REPLICATED"),
        clock=lambda: 2.0, sleep=lambda s: None, max_cycles=1, **kw)
    assert served["sinces"][0] == "2026-06-12|G2"  # resumed at the high-water, not ""


def test_high_water_never_skips_unseen_game_across_restart(tmp_path):
    """A game that settles LATE (lower key but processed after) is still folded, never
    skipped: dedup-by-game_id + a key-filtered feed mean the cursor only advances past
    games actually folded, so a later-arriving unseen game is picked up on the next sweep.
    """
    kw = _paths(tmp_path)
    # sweep 1 sees only G_b (key 2026-06-20); sweep 2 a NEW game G_a appears with a key
    # that is HIGHER (2026-06-21) so the key filter still surfaces it -- nothing skipped.
    batches = [
        [{"game_id": "Gb", "key": "2026-06-20|Gb"}],
        [{"game_id": "Gb", "key": "2026-06-20|Gb"},   # already folded -> deduped
         {"game_id": "Ga", "key": "2026-06-21|Ga"}],  # new, unseen -> must be folded
    ]
    state = {"i": 0}

    def feed(s, since=""):
        b = batches[min(state["i"], len(batches) - 1)]
        state["i"] += 1
        return [g for g in b if g["key"] > (since or "")]

    for c in range(2):
        R.refresh_cycle("mlb", settled_games_fn=feed, ingest_fn=_ingest_fn,
                        gate_fn=_gate("REPLICATED"), fit_fn=_fit("REPLICATED"),
                        now=float(c), **kw)
    # BOTH games landed -- the unseen later-arriving game was NOT skipped.
    ids = R._existing_game_ids(R._corpus_paths("mlb", state_dir=kw["state_dir"]))
    assert ids == {"Gb", "Ga"}, ids


def test_out_of_order_late_final_is_folded_not_skipped(tmp_path):
    """BUG B regression: game A (commence 19:00) finals AFTER game B (commence 22:00)
    already advanced the cursor. A's '<commence>|<id>' key is LOWER than the high-water,
    so a key filter would SKIP it. The runner dedups by on-disk game_id and threads the
    seen set to a seen_ids-aware feed, so A IS folded on the next sweep.
    """
    kw = _paths(tmp_path)
    A = {"game_id": "Ga", "commence": "2026-06-10T19:00Z", "key": "2026-06-10T19:00Z|Ga"}
    B = {"game_id": "Gb", "commence": "2026-06-10T22:00Z", "key": "2026-06-10T22:00Z|Gb"}
    # sweeps: 1) only B final; 2) both final but A arrives late (lower key).
    boards = [[B], [A, B]]
    state = {"i": 0}

    def feed(sport, since="", seen_ids=None):
        # emulate settled_finals: dedup by seen_ids (game_id), NOT by the key filter.
        seen = set(seen_ids or ())
        b = boards[min(state["i"], len(boards) - 1)]
        state["i"] += 1
        return [g for g in b if g["game_id"] not in seen]

    # sweep 1 folds B and advances the high-water to B's (higher) key.
    R.refresh_cycle("mlb", settled_games_fn=feed, ingest_fn=_ingest_fn,
                    gate_fn=_gate("REPLICATED"), fit_fn=_fit("REPLICATED"),
                    now=1.0, **kw)
    cur = load_checkpoint(kw["ckpt_path"]).cursor("mlb")
    assert cur["high_water"] == "2026-06-10T22:00Z|Gb"  # higher than A's key
    # sweep 2: A finals LATE with a LOWER key -> must STILL be folded (not key-skipped).
    R.refresh_cycle("mlb", settled_games_fn=feed, ingest_fn=_ingest_fn,
                    gate_fn=_gate("REPLICATED"), fit_fn=_fit("REPLICATED"),
                    now=2.0, **kw)
    ids = R._existing_game_ids(R._corpus_paths("mlb", state_dir=kw["state_dir"]))
    assert ids == {"Gb", "Ga"}, ids  # the out-of-order late final A was NOT skipped


def test_downgrade_with_broken_refit_does_not_repromote_stale_proven(tmp_path):
    """BUG 3: on a DOWNGRADE whose re-fit is broken (fit_ok=False), the runner must NOT
    auto-rollback to the PREVIOUS 'proven' version it just retired -- it holds the
    downgraded base-only artifact instead. Re-promoting proven would re-serve exactly
    what the downgrade removed.
    """
    kw = _paths(tmp_path)
    # cycle 1: REPLICATED proven ships v1 (a clean fit_ok=True artifact)
    R.refresh_cycle("mlb", settled_games_fn=lambda s, since="": [{"game_id": "G1"}],
                    ingest_fn=_ingest_fn, gate_fn=_gate("REPLICATED"),
                    fit_fn=_fit("REPLICATED"), now=1.0, **kw)
    assert store.current("mlb", kw["store_root"])["payload"]["prior_status"] == "proven"
    # cycle 2: MORE data -> REJECT (downgrade) AND the downgraded re-fit is broken.
    res = R.refresh_cycle(
        "mlb", settled_games_fn=lambda s, since="": [{"game_id": "G2"}],
        ingest_fn=_ingest_fn, gate_fn=_gate("REJECT"),
        fit_fn=_fit("REJECT", status="none", fit_ok=False), now=2.0, **kw)
    # decision stays DOWNGRADED (NOT ROLLED_BACK) and current is the NEW base-only v2,
    # never the retired proven v1.
    assert res.decision == R.DOWNGRADED, res.decision
    assert res.rolled_back_to is None
    live = store.current("mlb", kw["store_root"])["payload"]
    assert live["verdict"] == "REJECT" and live["prior_status"] == "none"
    assert store.read_pointer("mlb", kw["store_root"]) == 2  # held FORWARD, not v1


def test_gate_sees_appended_game_verdict_reflects_new_data(tmp_path):
    """The loop's gate must judge the SAME corpora the runner appends + the server fits.
    Use the REAL ingame_gate_refresh.gate_refresh (not a fake verdict) and confirm that
    appending a new game flows into the gate's coverage / verdict (no stale re-glob).
    """
    from scripts.platformkit.ingame.ingame_gate_refresh import gate_refresh
    kw = _paths(tmp_path)
    seen = {"covs": []}

    def real_gate(sport):
        v = gate_refresh(sport, state_dir=str(kw["state_dir"]))
        seen["covs"].append(v.coverage)
        return v

    feed = lambda s, since="": [{"game_id": "G1"}, {"game_id": "G2"},
                                {"game_id": "G3"}, {"game_id": "G4"}]
    R.refresh_cycle("mlb", settled_games_fn=feed, ingest_fn=_ingest_fn,
                    gate_fn=real_gate, fit_fn=_fit("REPLICATED"), now=1.0, **kw)
    cov1 = seen["covs"][-1]
    n1 = cov1.get("a_states", 0) + cov1.get("b_states", 0)
    assert n1 == 12, cov1  # 4 games * 3 states each, ALL seen by the gate
    # append one more game -> the gate's coverage GROWS (it is not re-globbing a stale set)
    R.refresh_cycle("mlb", settled_games_fn=lambda s, since="": [{"game_id": "G5"}],
                    ingest_fn=_ingest_fn, gate_fn=real_gate, fit_fn=_fit("REPLICATED"),
                    now=2.0, **kw)
    cov2 = seen["covs"][-1]
    n2 = cov2.get("a_states", 0) + cov2.get("b_states", 0)
    assert n2 == 15, cov2  # the freshly-appended game's 3 states are now gated


def test_per_sport_isolation(tmp_path):
    kw = _paths(tmp_path)

    def feed(sport, since=0):
        if sport == "mlb":
            raise RuntimeError("mlb feed down")
        return [{"game_id": "S1"}]

    results = R.run_refresh_forever(
        sports=["mlb", "soccer"], settled_games_fn=feed, ingest_fn=_ingest_fn,
        gate_fn=_gate("REPLICATED"), fit_fn=_fit("REPLICATED"),
        clock=lambda: 1.0, sleep=lambda s: None, max_cycles=1, **kw)
    by_sport = {r.sport: r for r in results}
    assert by_sport["mlb"].decision == R.ERROR        # isolated, did not raise
    assert by_sport["soccer"].decision == R.SWAPPED    # other sport still ran
    assert "source_error" in kw["status_path"].read_text()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
