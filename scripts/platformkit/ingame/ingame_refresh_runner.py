"""scripts.platformkit.ingame.ingame_refresh_runner -- the LIVING in-game loop:
continuously fold newly-SETTLED in-season games into a sport's in-game corpora,
RE-GATE, RE-FIT the served model, and HONESTLY update (or DOWNGRADE) its provenance.

The capstone that turns the static in-game gate into a self-improving engine. GLUE
ONLY (no new math): reuses ingame_gate_refresh (re-gate), ingame_serve.fit_servable
(re-fit), improve.artifact_store (versioned atomic swap + rollback), improve.checkpoint
(resumable cursor). Feeds injected: settled_games_fn(sport, since=high_water) -> finals;
ingest_fn(sport, game) -> frozen rows {game_id, asof_idx, state_diff, frac, p0, outcome}.

ONE CYCLE (refresh_cycle, idempotent -- a restart never reprocesses NOR skips):
  1. Fetch newly-settled finals since the per-sport id/date HIGH-WATER cursor (NOT a
     count -- a count desyncs from dedup and can skip games); DEDUP by game_id vs disk.
  2. Reconstruct each game's states + APPEND atomically to the sport's two refresh
     corpora, assigning each NEW game to A/B by a stable game_id hash (balanced,
     leak-free). NEVER fabricates; a game yielding no states is skipped.
  3. RE-GATE (gate_refresh) the corpora the runner appends + server fits + RE-FIT.
  4. HONESTY-GATED SWAP: atomic-swap `current` to the fresh artifact when the gate
     PASSES; if MORE data makes the sport STOP replicating, swap to the DOWNGRADED
     artifact too (proven -> experimental/none) so the served model reflects current
     truth, never a stale 'proven'. auto_rollback re-promotes the prior version on a
     held-out regression. Every verdict change is logged.
  5. Emit a proposal row to data/cache/improve/proposals.jsonl (NOT MEMORY.md / registry)
     + advance the cursor on every non-error cycle (per-sport).
run_refresh_forever (loop body in ingame_refresh_runner_io): per-sport isolated (one
failure never stops the others), checkpoint-resumable, polite hourly cadence.

INVARIANTS: never edits MEMORY.md, never writes data/registry/, never flips a flag.
Calibration (held-out Brier), NEVER a market edge. ASCII; numpy/pandas + stdlib; <=300 LOC.
"""
from __future__ import annotations

import pathlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.improve import artifact_store as _store
from scripts.platformkit.improve.checkpoint import load_checkpoint, save_checkpoint
from scripts.platformkit.improve.cursor_util import key as _game_key
from scripts.platformkit.ingame.ingame_refresh_corpora import (
    FROZEN_COLS, append_states, corpus_for, corpus_paths, existing_game_ids,
)
from scripts.platformkit.ingame.ingame_refresh_runner_io import (
    append_jsonl as _append_jsonl,
    call_feed as _call_feed,
    run_refresh_forever as _run_refresh_forever_loop,
)

_REPO = pathlib.Path(__file__).resolve().parents[3]
_STATE_DIR = _REPO / "data" / "cache" / "ingame"
_IMPROVE_DIR = _REPO / "data" / "cache" / "improve"
DEFAULT_PROPOSALS = _IMPROVE_DIR / "proposals.jsonl"
DEFAULT_STATUS = _IMPROVE_DIR / "status.jsonl"
DEFAULT_CKPT = _IMPROVE_DIR / "ingame_refresh_checkpoint.json"
# Verdicts under which the +PRIOR layer is honestly servable (mirror ingame_serve).
_PASS_VERDICTS = frozenset({"REPLICATED", "PARTIAL"})
NO_NEW = "NO_NEW_GAMES"
SWAPPED = "SWAPPED"
DOWNGRADED = "DOWNGRADED"
HELD = "HELD"          # re-fit but gate did not pass -> no swap (kept prior live)
ROLLED_BACK = "ROLLED_BACK"
ERROR = "ERROR"


@dataclass
class CycleResult:
    sport: str
    decision: str
    reasons: List[str] = field(default_factory=list)
    n_new_games: int = 0
    n_new_states: int = 0
    verdict: str = "UNKNOWN"
    prior_status: str = "none"
    prev_verdict: Optional[str] = None
    shipped_version: Optional[int] = None
    rolled_back_to: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sport": self.sport, "decision": self.decision, "reasons": self.reasons,
            "n_new_games": self.n_new_games, "n_new_states": self.n_new_states,
            "verdict": self.verdict, "prior_status": self.prior_status,
            "prev_verdict": self.prev_verdict, "shipped_version": self.shipped_version,
            "rolled_back_to": self.rolled_back_to,
        }


# Corpus I/O (A/B split, paths, dedup discovery, atomic append) is owned by
# ingame_refresh_corpora (imported above). These aliases keep the runner's private
# call sites + the offline tests (which probe R._corpus_paths / R._existing_game_ids)
# pointing at that ONE implementation -- no duplicated math, no second copy to drift.
_corpus_for = corpus_for
_corpus_paths = corpus_paths
_existing_game_ids = existing_game_ids
_append_states = append_states


# --------------------------------------------------------------- the cycle
def refresh_cycle(sport: str, *,
                  settled_games_fn: Callable[..., Sequence[Dict[str, Any]]],
                  ingest_fn: Callable[..., Sequence[Dict[str, Any]]],
                  gate_fn: Callable[[str], Any],
                  fit_fn: Callable[[str], Dict[str, Any]],
                  store_root: Optional[str] = None,
                  state_dir: Optional[pathlib.Path] = None,
                  ckpt_path: Optional[str] = None,
                  proposals_path: Optional[pathlib.Path] = None,
                  status_path: Optional[pathlib.Path] = None,
                  now: Optional[float] = None) -> CycleResult:
    """Run ONE idempotent refresh cycle for `sport`. Never raises out.

    All deps injectable for offline tests. settled_games_fn(sport, since=cursor) yields
    finals; ingest_fn(sport, game) yields frozen-schema state rows; gate_fn re-gates;
    fit_fn re-fits + persists the served artifact.
    """
    t = time.time() if now is None else float(now)
    sd = pathlib.Path(state_dir) if state_dir else _STATE_DIR
    proposals_path = proposals_path or DEFAULT_PROPOSALS
    status_path = status_path or DEFAULT_STATUS
    paths = _corpus_paths(sport, state_dir=sd)
    ck = load_checkpoint(ckpt_path or str(DEFAULT_CKPT))
    cur = ck.cursor(sport)
    # CURSOR = id/date HIGH-WATER key, NOT a count (cursor_util): a count desyncs from
    # dedup and can SKIP a game; a key only advances past FOLDED games.
    high_water = str(cur.get("high_water", "") or "")
    prev_verdict = cur.get("last_verdict")

    def _status(kind: str, **kw: Any) -> None:
        _append_jsonl(status_path, {"ts": t, "sport": sport, "status": kind, **kw})

    # PRIMARY fold guard = game_ids already ON DISK (seen), NOT the high-water key: an
    # out-of-order final (earlier commence, later final) has key < high-water but is
    # absent from disk -> still folded; `seen` is threaded to a seen_ids-aware feed.
    seen = _existing_game_ids(paths)

    # --- 1. fetch newly-settled finals (per-sport isolation) -----------------
    try:
        settled = list(_call_feed(settled_games_fn, sport, high_water, seen))
    except Exception as exc:  # noqa: BLE001 -- dead feed: isolate + continue
        _status("source_error", error=str(exc)[:200])
        return CycleResult(sport, ERROR, ["settled_games_fn raised: %s" % exc],
                           prev_verdict=prev_verdict)

    # --- 2. reconstruct + append (dedup by game_id) --------------------------
    rows_by_corpus: Dict[int, list] = {0: [], 1: []}
    n_new_games = 0
    folded_keys: List[str] = []   # games we FOLDED (high-water source)
    batch_keys: List[str] = []    # EVERY settled game this sweep saw
    try:
        for game in settled:
            gid = str(game.get("game_id", game) if isinstance(game, dict) else game)
            key = _game_key(game)
            batch_keys.append(key)
            if gid in seen:
                continue
            rows = list(ingest_fn(sport, game))
            if not rows:  # broken/empty PBP -> skip, never fabricate
                continue
            seen.add(gid)
            n_new_games += 1
            folded_keys.append(key)
            for r in rows:
                rows_by_corpus[_corpus_for(gid)].append(
                    {k: r[k] for k in FROZEN_COLS if k in r})
    except Exception as exc:  # noqa: BLE001
        _status("ingest_error", error=str(exc)[:200])
        return CycleResult(sport, ERROR, ["ingest_fn raised: %s" % exc],
                           prev_verdict=prev_verdict)

    # Advance past FOLDED games; on an all-deduped/empty batch advance past its max key
    # so a permanently-empty batch is not re-fetched forever (states are on disk).
    def _hw_after(keys: List[str]) -> str:
        return max([high_water] + keys) if keys else high_water

    if n_new_games == 0:
        cur["high_water"] = _hw_after(batch_keys)
        save_checkpoint(ck, ckpt_path or str(DEFAULT_CKPT))
        _status("no_new_games", n_settled=len(settled))
        return CycleResult(sport, NO_NEW, ["no new settled games to fold"],
                           verdict=str(prev_verdict or "UNKNOWN"),
                           prev_verdict=prev_verdict)

    n_new_states = _append_states(rows_by_corpus, paths)

    # --- 3. re-gate + re-fit (isolated) --------------------------------------
    try:
        verdict_obj = gate_fn(sport)
        verdict = str(getattr(verdict_obj, "verdict", verdict_obj))
        art = fit_fn(sport)
    except Exception as exc:  # noqa: BLE001 -- a raising gate/fit must not crash the loop
        _status("regate_error", error=str(exc)[:200])
        # states are on disk; advance high-water past the FOLDED games (never further).
        cur["high_water"] = _hw_after(folded_keys)
        save_checkpoint(ck, ckpt_path or str(DEFAULT_CKPT))
        return CycleResult(sport, ERROR, ["gate/fit raised: %s" % exc],
                           n_new_games=n_new_games, n_new_states=n_new_states,
                           prev_verdict=prev_verdict)

    prior_status = str(art.get("prior_status", "none"))
    # The GATE verdict decides whether to stage+swap; a broken re-fit (fit_ok False) is
    # then caught by the held-out check below and auto-rolled-back. Separating these two
    # concerns lets a passing-verdict-but-broken-fit roll back, not silently stay out.
    passes = verdict in _PASS_VERDICTS

    # --- 4. honesty-gated swap / downgrade / rollback ------------------------
    reasons: List[str] = []
    shipped_version: Optional[int] = None
    rolled_to: Optional[int] = None
    decision = HELD

    verdict_changed = prev_verdict is not None and prev_verdict != verdict
    downgraded = (prev_verdict in _PASS_VERDICTS and verdict not in _PASS_VERDICTS) or \
                 (prev_verdict == "REPLICATED" and verdict == "PARTIAL")

    if passes or downgraded:
        # Stage the freshly-fit artifact as a new version + atomic-swap current.
        # We swap on a downgrade too: the served model MUST reflect current truth
        # (a now-experimental / base-only artifact), never a stale 'proven'.
        shipped_version = _store.stage_version(sport, art, root=store_root)
        _store.swap_current(sport, shipped_version, root=store_root)
        decision = DOWNGRADED if downgraded else SWAPPED
        if downgraded:
            reasons.append("more data made %s stop replicating: %s -> %s "
                           "(prior_status now %s) -- DOWNGRADED served model"
                           % (sport, prev_verdict, verdict, prior_status))
            # BUG 3 FIX: NEVER auto-rollback on a downgrade -- the rollback target is the
            # stale 'proven' version we are retiring, so rolling back re-serves exactly
            # what the downgrade removed. A broken downgraded re-fit (fit_ok False) HOLDS
            # the base-only artifact we just swapped to (rolling FORWARD, never to proven).
            if not bool((art or {}).get("fit_ok")):
                reasons.append("downgraded re-fit fit_ok=False; HELD downgraded base-only "
                               "artifact -- did NOT roll back to retired proven")
        else:
            reasons.append("gate passes (%s); swapped served model to v%d (%s)"
                           % (verdict, shipped_version, prior_status))
            # auto-rollback ONLY on a non-downgrade swap (a regressed fresh fit restores
            # the prior good version -- it was NOT a retired-proven downgrade).
            res = _store.auto_rollback_if_regressed(
                sport, lambda rec: not bool(
                    ((rec or {}).get("payload") or {}).get("fit_ok")), root=store_root)
            if res.get("regressed"):
                rolled_to = res.get("rolled_to")
                decision = ROLLED_BACK
                reasons.append("auto-rollback: re-fit artifact failed held-out check "
                               "-> v%s" % rolled_to)
    else:
        reasons.append("gate did not pass (%s) and not a downgrade; kept prior live"
                       % verdict)

    if verdict_changed:
        reasons.append("verdict changed %s -> %s" % (prev_verdict, verdict))

    # --- 5. proposal (NEVER MEMORY.md / data/registry) + cursor advance ------
    _append_jsonl(proposals_path, {
        "ts": t, "sport": sport, "kind": "ingame_refresh", "decision": decision,
        "verdict": verdict, "prev_verdict": prev_verdict, "prior_status": prior_status,
        "n_new_games": n_new_games, "n_new_states": n_new_states,
        "shipped_version": shipped_version, "rolled_back_to": rolled_to,
        "reasons": reasons[:8],
        "note": "calibration (held-out Brier), not edge; PROPOSAL only -- never "
                "edits MEMORY.md / data/registry",
    })
    cur["high_water"] = _hw_after(folded_keys)
    cur["last_verdict"] = verdict
    cur["last_decision"] = decision
    cur["last_version"] = (shipped_version if shipped_version is not None
                           else cur.get("last_version"))
    save_checkpoint(ck, ckpt_path or str(DEFAULT_CKPT))
    _status("cycle_done", decision=decision, verdict=verdict,
            n_new_games=n_new_games)

    return CycleResult(sport, decision, reasons, n_new_games, n_new_states,
                       verdict, prior_status, prev_verdict, shipped_version, rolled_to)


# --------------------------------------------------------------- forever loop
def run_refresh_forever(*, sports: Sequence[str],
                        settled_games_fn: Callable[..., Sequence[Dict[str, Any]]],
                        ingest_fn: Callable[..., Sequence[Dict[str, Any]]],
                        gate_fn: Callable[[str], Any],
                        fit_fn: Callable[[str], Dict[str, Any]],
                        **kwargs: Any) -> List[CycleResult]:
    """Always-on, per-sport isolated refresh loop (loop body in the IO sibling).

    Thin wrapper over ingame_refresh_runner_io.run_refresh_forever; refresh_cycle + the
    error-result factory are injected to avoid a circular import. One sport's failure is
    ONE CycleResult(ERROR); the loop keeps going for the others and resumes from ckpt.
    """
    return _run_refresh_forever_loop(
        refresh_cycle, CycleResult, ERROR,
        sports=sports, settled_games_fn=settled_games_fn, ingest_fn=ingest_fn,
        gate_fn=gate_fn, fit_fn=fit_fn, **kwargs)


__all__ = [
    "CycleResult", "refresh_cycle", "run_refresh_forever", "NO_NEW", "SWAPPED",
    "DOWNGRADED", "HELD", "ROLLED_BACK", "ERROR",
    "DEFAULT_PROPOSALS", "DEFAULT_STATUS", "DEFAULT_CKPT",
]
