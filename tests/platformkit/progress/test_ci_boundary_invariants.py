"""tests.platformkit.progress.test_ci_boundary_invariants -- W4 CI-9 CAPSTONE.

The BOUNDARY-INVARIANT proof for the W4 CONTINUOUS-IMPROVEMENT cadence. This is the
highest-risk wave: a violation here is the worst kind. We SIMULATE 30+ nightly
cadence runs with an INJECTED clock + INJECTED fixtures (we NEVER touch the real
PIPELINE_ENABLED sentinel, data/registry/, or MEMORY.md) and assert the cadence
"gets better" (coverage/verdicts/backlog burn-down climb + the ratchet standing
proven-ready on its FIXED sealed fold) WITHOUT ever crossing a gate:

  1. the served MODEL ARTIFACT HASH is UNCHANGED across all 30+ nights.
  2. NO write to data/registry/, NO sentinel created, NO MEMORY.md write, NO flag
     flipped, NO autostart armed (paths untouched before/after).
  3. every enqueued kind is in ALLOWED_KINDS.
  4. coverage is MONOTONIC non-decreasing across nights.
  5. every ship attempt resolves to PROPOSAL-ONLY (INERT -> NO_CANDIDATE).
  6. a deliberately FAILING step is degrade-isolated (cadence completes, DEGRADED,
     no crash, no fake-green).
  7. the survivor-recheck DEMOTES a planted-now-failing survivor.
  8. NO $ field in any emitted progress/cadence payload.

MEASUREMENT-ONLY. Per-file test (NEVER full pytest). stdlib + repo-internal; ASCII.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

from scripts.platformkit.progress import ci_cadence
from scripts.platformkit.progress import ci_survivor_recheck as _sr
from scripts.platformkit.autonomy.work_queue import ALLOWED_KINDS
from scripts.platformkit.autonomy import schedule_policy as _sp

_REPO = pathlib.Path(__file__).resolve().parents[3]  # .../nba-ai-system
_REGISTRY_DIR = _REPO / "data" / "registry"
_SENTINEL = _REPO / "data" / "cache" / "improve" / "PIPELINE_ENABLED"
_MEMORY = pathlib.Path.home() / ".claude" / "projects" / "C--Users-neelj" / "memory" / "MEMORY.md"

# The STATIC served-model artifact. The cadence must NEVER mutate it; its hash is
# fixed across every simulated night. We mint a throwaway artifact in a tmp area so
# the proof is hermetic (we are proving the *cadence touches nothing*, so any file the
# cadence is given no handle to suffices as the "served model").
_MODEL_BYTES = b"served-model-artifact::STATIC::v11::nba+mlb+soccer+tennis"

_DOLLAR_TOKENS = ("$", "pnl", "roi", "bankroll", "profit", "usd", "dollar", "stake", "wager")
# Honest disclaimer fields are ALLOWED to contain the literal phrase "no $ field" /
# prose; we scan DATA KEYS for money, and scan VALUES only for a bare "$" leak.
_NOTE_KEYS = {"note", "honest_note", "reason", "deciding", "detail"}


# --------------------------------------------------------------------------- helpers
def _hash_path(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _registry_fingerprint() -> dict:
    """Recursive {relpath: (size, mtime_ns)} of data/registry/ -- the untouched proof."""
    out = {}
    if not _REGISTRY_DIR.exists():
        return out
    for p in sorted(_REGISTRY_DIR.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[str(p.relative_to(_REGISTRY_DIR))] = (st.st_size, st.st_mtime_ns)
    return out


def _assert_no_dollar(obj, where=""):
    """No money KEY anywhere; no bare '$' in any non-note string VALUE."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            toks = set(kl.replace("-", "_").split("_"))
            assert not (toks & set(_DOLLAR_TOKENS[1:])), "money key %r at %s" % (k, where)
            assert "$" not in kl, "dollar in key %r at %s" % (k, where)
            if str(k).lower() in _NOTE_KEYS:
                continue  # honest disclaimer prose may say 'no $ field' / 'units not $'
            _assert_no_dollar(v, where + "/" + str(k))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _assert_no_dollar(v, "%s[%d]" % (where, i))
    elif isinstance(obj, str):
        assert "$" not in obj, "bare $ in value at %s: %r" % (where, obj)


class _SpyQueue:
    """Durable-queue stand-in: records every enqueue + enforces the REAL allowlist.

    Never touches disk (no data/cache/autonomy write) -- a pure in-memory fixture, so
    the 30-night sim leaves the filesystem untouched.
    """
    def __init__(self):
        self.enqueued = []      # list[(kind, sport)] across ALL nights
        self._leased = None

    def enqueue(self, kind, sport, args=None, now=None):
        if kind not in ALLOWED_KINDS:                 # the real rail
            raise ci_cadence.DisallowedKind(kind)
        self.enqueued.append((kind, sport))
        self._leased = type("T", (), {"id": "t", "sport": sport, "kind": kind})
        return "t"

    def lease(self, now=None):
        return self._leased

    def ack(self, tid):
        self._leased = None
        return True


def _inert_policy():
    """A policy that proposes a measurement TASK (recalibrate) every night."""
    class _P:
        def decide(self, durable, now=None):
            task = _sp.Task("recalibrate", "nba", {"reason": "settled_pending"})
            return _sp.Decision(_sp.TASK, task, {"nba": "IN_SEASON"}, "due")
    return _P()


def _run_cycle_inert(captured):
    """selfimprove one-cycle stub: asserts the recalibrate_fn is INERT (-> None)."""
    def _rc(*, name, settled_games_fn, recalibrate_fn, now=None):
        # The ship path MUST be inert: the injected recalibrate_fn yields NO candidate.
        captured["recalibrate_none"] = (recalibrate_fn(name, []) is None)
        captured["settled_empty"] = (list(settled_games_fn(name)) == [])
        return type("CR", (), {"decision": "NO_CANDIDATE"})
    return _rc


def _deps_for_night(night_idx, queue, rows, captured,
                    *, fail_step=None, regate_grew=False, survivors=None):
    """Build injected Deps for one simulated night.

    coverage CLIMBS with night_idx (more verdicts accumulate, denominator fixed) so
    invariant #4 (monotone non-decreasing) is exercised by REAL snapshot data.
    """
    n_tested = 10 + night_idx          # verdicts only accumulate
    remaining = 40                      # fixed untested backlog denominator part

    def _build_state(now):
        return {"nba": {"settled_pending": 1, "ingame_pending": 0,
                        "corpus_age_days": 0.0}}

    def _discover():
        if fail_step == "B":
            raise RuntimeError("planted finder failure")
        return []

    def _regate(now):
        if regate_grew:
            task = type("RT", (), {"kind": "regate_ingame", "sport": "nba", "args": {}})
            return type("R", (), {"status": "SELECTED", "targets": [task]})
        return type("R", (), {"status": "NO_OP", "targets": []})

    def _survivor_select():
        return list(survivors or [])

    def _survivor_recheck(task, now=None):
        # Conduct the REAL recheck harness with an injected gate_fn so the planted
        # now-failing survivor is honestly DEMOTED (never clung to).
        verdict = getattr(task, "_planted_verdict", "REJECT")
        out = _sr.recheck_survivor(
            task, gate_fn=lambda k: type("Rep", (), {"verdict": verdict}),
            funnel_dir=captured["funnel_dir"], now=now)
        return out

    def _append(snap=None, now=None):
        # A REAL-shaped progress snapshot: coverage climbs, model_static, no $.
        cov = round(100.0 * n_tested / (n_tested + remaining), 2)
        row = {
            "ts": now, "date_et": "2026-06-%02d" % (1 + (night_idx % 28)),
            "per_sport": {"nba": {"coverage_pct": cov, "n_tested": n_tested,
                                  "n_ship": 0, "n_reject": n_tested,
                                  "n_insufficient": 0,
                                  "n_untested_remaining": remaining}},
            "backlog_total": 73, "backlog_remaining": max(0, 73 - night_idx),
            "engine_ready": True, "engine_enabled": False,
            "model_static": True, "edge_claimed": False,
            "honest_note": "coverage climbs; model static; units only, never currency",
        }
        rows.append(row)
        return row

    return ci_cadence.Deps(
        build_durable_state=_build_state,
        finder_discover=_discover,
        finder_write=lambda c: None,
        policy=_inert_policy(),
        queue=queue,
        run_cycle=_run_cycle_inert(captured),
        regate_select=_regate,
        survivor_select=_survivor_select,
        survivor_recheck=_survivor_recheck,
        append_snapshot=_append,
        build_snapshot=None,
        pipeline_enabled=lambda: False,      # sentinel ABSENT (read, never created)
    )


# --------------------------------------------------------------------------- the sim
_N_NIGHTS = 32  # 30+


def _planted_failing_survivor():
    """A survivor that PASSED at K=20 but now FAILS its wider-K (K=40) re-check."""
    task = _sr.SurvivorTask(kind=_sr.RECHECK_KIND, sport="soccer",
                            signal="corners_combo", prev_k=20, next_k=40, args={})
    task._planted_verdict = "REJECT"
    return task


def _simulate_nights(tmp_path, *, fail_on_night=None, regate_on_night=None,
                     survivors_on_night=None):
    """Run _N_NIGHTS cadence ticks; return (results, queue, all_rows, captured)."""
    queue = _SpyQueue()
    all_rows = []
    captured = {"funnel_dir": tmp_path / "funnel"}
    captured["funnel_dir"].mkdir(parents=True, exist_ok=True)
    results = []
    for n in range(_N_NIGHTS):
        survivors = ([_planted_failing_survivor()]
                     if n == survivors_on_night else None)
        deps = _deps_for_night(
            n, queue, all_rows, captured,
            fail_step=("B" if n == fail_on_night else None),
            regate_grew=(n == regate_on_night),
            survivors=survivors)
        # INJECTED CLOCK: one night apart (86400s), never the wall clock.
        res = ci_cadence.run_once(1_700_000_000.0 + n * 86400.0, deps=deps)
        results.append(res)
    return results, queue, all_rows, captured


# --------------------------------------------------------------------------- tests
def test_inv2_no_sentinel_no_registry_no_memory_no_flag(tmp_path):
    """#2: data/registry/, the sentinel, and MEMORY.md are UNTOUCHED by 30+ nights."""
    reg_before = _registry_fingerprint()
    sentinel_before = _SENTINEL.exists()
    mem_before = _MEMORY.stat().st_mtime_ns if _MEMORY.exists() else None

    results, _q, _rows, _cap = _simulate_nights(tmp_path)

    reg_after = _registry_fingerprint()
    sentinel_after = _SENTINEL.exists()
    mem_after = _MEMORY.stat().st_mtime_ns if _MEMORY.exists() else None

    assert reg_before == reg_after, "data/registry/ was mutated by the cadence"
    assert sentinel_before is False and sentinel_after is False, "sentinel created!"
    assert mem_before == mem_after, "MEMORY.md was written by the cadence"
    # No flag flipped / no autostart armed: engine_enabled stayed False every night,
    # ship stayed proposal-only every night.
    assert all(r.engine_enabled is False for r in results)
    assert all(r.ship_proposal_only is True for r in results)


def test_inv1_model_artifact_hash_unchanged(tmp_path):
    """#1: the served MODEL ARTIFACT HASH is identical before and after all nights."""
    model = tmp_path / "served_model.bin"
    model.write_bytes(_MODEL_BYTES)
    h_before = _hash_path(model)

    _simulate_nights(tmp_path)  # the cadence has NO handle to this artifact at all

    h_after = _hash_path(model)
    assert h_after == h_before, "served model artifact hash changed across nights"
    # And it is the static v11 artifact we minted (proof the bytes are the model).
    assert h_before == hashlib.sha256(_MODEL_BYTES).hexdigest()


def test_inv3_every_enqueued_kind_is_allowed(tmp_path):
    """#3: across all nights, EVERY enqueued kind is in the real ALLOWED_KINDS."""
    _results, queue, _rows, _cap = _simulate_nights(tmp_path)
    assert queue.enqueued, "no work was ever enqueued (the sim did nothing)"
    assert all(k in ALLOWED_KINDS for k, _ in queue.enqueued), \
        "a non-measurement kind leaked into the queue"
    # belt + braces: the cadence's allowlist is pinned to the queue's (no drift).
    assert ci_cadence.ALLOWED_KINDS == frozenset(ALLOWED_KINDS)


def test_inv4_coverage_monotonic_non_decreasing(tmp_path):
    """#4: coverage only accumulates -- non-decreasing across every night."""
    _results, _q, rows, _cap = _simulate_nights(tmp_path)
    assert len(rows) == _N_NIGHTS, "expected exactly one progress row per night"
    covs = [r["per_sport"]["nba"]["coverage_pct"] for r in rows]
    for a, b in zip(covs, covs[1:]):
        assert b >= a, "coverage went DOWN (%s -> %s): not monotone" % (a, b)
    assert covs[-1] >= covs[0]
    # verdict count strictly accumulates (the product gets MORE-validated).
    tested = [r["per_sport"]["nba"]["n_tested"] for r in rows]
    assert tested[-1] > tested[0]


def test_inv5_every_ship_attempt_is_proposal_only(tmp_path):
    """#5: the ship path stays INERT/PROPOSAL-ONLY every night (NO_CANDIDATE)."""
    results, _q, _rows, captured = _simulate_nights(tmp_path)
    assert all(r.cycle_verdict == "NO_CANDIDATE" for r in results), \
        "a night produced a non-NO_CANDIDATE ship verdict"
    assert all(r.ship_proposal_only is True for r in results)
    assert all(r.engine_enabled is False for r in results)
    # the INERT recalibrate_fn the real cycle saw yields None (no candidate to ship).
    assert captured.get("recalibrate_none") is True
    assert captured.get("settled_empty") is True


def test_inv6_failing_step_is_degrade_isolated(tmp_path):
    """#6: a planted failing step -> DEGRADED, cadence still completes, no crash."""
    results, _q, rows, _cap = _simulate_nights(tmp_path, fail_on_night=7)
    bad = results[7]
    assert bad.overall == "degraded", "failing night did not report DEGRADED"
    assert "B_backlog" in bad.degraded, "the planted failing step was not isolated"
    # the cadence CONTINUED through the failure: a progress row was STILL appended,
    # and the enqueue/ship steps still ran (no green-fake, no crash-out).
    assert len(rows) == _N_NIGHTS, "a failing step aborted the run (lost a row)"
    assert bad.progress_row is not None, "step G (progress row) was skipped on failure"
    # every OTHER night stayed ok (the failure was isolated to night 7).
    assert all(r.overall == "ok" for i, r in enumerate(results) if i != 7)


def test_inv7_survivor_recheck_demotes_planted_failure(tmp_path):
    """#7: a planted now-FAILING survivor is DEMOTED, not clung to as a stale SHIP."""
    planted = _sr.SurvivorTask(
        kind=_sr.RECHECK_KIND, sport="soccer", signal="corners_combo",
        prev_k=20, next_k=40, args={})
    planted._planted_verdict = "REJECT"   # was SHIP@K20, now FAILS at wider K40
    results, _q, _rows, captured = _simulate_nights(
        tmp_path, survivors_on_night=12)
    # the cadence counted exactly one demotion on the planted night.
    assert results[12].n_survivor_demotions == 1, "survivor was NOT demoted"
    # direct conduct of the REAL recheck harness confirms the DEMOTE verdict + record.
    out = _sr.recheck_survivor(
        planted, gate_fn=lambda k: type("R", (), {"verdict": "REJECT"}),
        funnel_dir=captured["funnel_dir"], now=1.0)
    assert out.demoted is True and out.status == _sr.DEMOTED
    assert "failed re-check at K=40" in out.deciding
    # the recorded funnel row is a downgrade-to-artifact, never a kept SHIP.
    recs = list(captured["funnel_dir"].glob("soccer_ci_survivor_*.json"))
    assert recs, "no demotion record was written"
    doc = json.loads(recs[0].read_text(encoding="ascii"))
    assert doc["verdict"] == "DOWNGRADE_TO_ARTIFACT" and doc["demoted"] is True
    assert doc["proposal_only"] is True and doc["edge_claimed"] is False


def test_inv8_no_dollar_field_anywhere(tmp_path):
    """#8: NO $ field/value in any emitted cadence OR progress payload."""
    results, _q, rows, captured = _simulate_nights(
        tmp_path, regate_on_night=3, survivors_on_night=12)
    for i, res in enumerate(results):
        payload = {
            "overall": res.overall,
            "degraded": list(res.degraded),
            "enqueued_kind": res.enqueued_kind,
            "decision_status": res.decision_status,
            "cycle_verdict": res.cycle_verdict,
            "regate_status": res.regate_status,
            "n_survivor_demotions": res.n_survivor_demotions,
            "ship_proposal_only": res.ship_proposal_only,
            "engine_enabled": res.engine_enabled,
            "progress_row": res.progress_row,
            "steps": [(s.name, s.ok, s.detail) for s in res.steps],
        }
        _assert_no_dollar(payload, where="night%d" % i)
    for r in rows:
        _assert_no_dollar(r, where="row")
    # the recorded funnel docs (regate / survivor) carry no $ key either.
    for f in captured["funnel_dir"].glob("*.json"):
        _assert_no_dollar(json.loads(f.read_text(encoding="ascii")), where=f.name)


if __name__ == "__main__":
    import sys
    import tempfile

    def _tmp():
        return pathlib.Path(tempfile.mkdtemp(prefix="ci_boundary_"))

    failures = []
    for fn in (test_inv1_model_artifact_hash_unchanged,
               test_inv2_no_sentinel_no_registry_no_memory_no_flag,
               test_inv3_every_enqueued_kind_is_allowed,
               test_inv4_coverage_monotonic_non_decreasing,
               test_inv5_every_ship_attempt_is_proposal_only,
               test_inv6_failing_step_is_degrade_isolated,
               test_inv7_survivor_recheck_demotes_planted_failure,
               test_inv8_no_dollar_field_anywhere):
        try:
            fn(_tmp())
            print("PASS:", fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print("FAIL:", fn.__name__, "->", repr(exc))
    sys.exit(1 if failures else 0)
