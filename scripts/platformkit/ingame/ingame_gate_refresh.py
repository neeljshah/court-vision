"""scripts.platformkit.ingame.ingame_gate_refresh -- the LOOP-CONSISTENT in-game gate
(companion to ingame_gate_generic.py, kept <=300 LOC).

THE LOOP-CONSISTENCY BUG (BUG A, fixed here): the living refresh loop must RE-GATE the
EXACT data the server serves. The server (ingame_serve.fit_servable -> _load_pool ->
_corpora_for) pools ALL {sport}_states__*.parquet (the seed corpora -- mlb 2023/2024,
soccer league + combo files, tennis atp/wta -- PLUS any rolling refresh corpus the loop
appends to). The prior gate instead gated only a separate pair of
{sport}_states__refresh_a/_b.parquet files, which the server's pool then DWARFED -- so
the gate==serve parity assertion RAISED "gate/fit corpus mismatch" every cycle and the
loop turned every cycle into a CycleResult(ERROR) while the cursor still advanced.

THE FIX: gate the FULL server pool, split A<->B held-out-BY-CORPUS via
ingame_serve.pool_split_ab (the canonical corpus-file split -- MLB 2023<->2024, tennis
atp<->wta, soccer league groups -- leak-free + matching the verified per-sport verdicts).
A+B is EXACTLY the served pool, so gate(full pool) == serve(full pool) by construction.
The refresh runner APPENDS newly-settled games into a rolling {sport}_states__refresh
corpus that _corpora_for ALREADY globs, so a fresh game flows into BOTH the gate split
and the served fit -- the verdict reflects the appended data, and the gated corpora ==
the fit pool. The parity ASSERTION is KEPT but now PASSES.

  * generic sport -> gate_<sport>.json over pool_split_ab(sport)
  * NBA           -> finegrain_nba.json over the SAME pool_split_ab('nba')

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy/stdlib. No $;
verdict is CALIBRATION (held-out Brier), never a market edge.
"""
from __future__ import annotations

import os
import pathlib
from typing import List, Optional

from scripts.platformkit.ingame.ingame_gate_generic import (
    GenericVerdict, _OUT_DIR, _STATE_DIR, _MIN_GAMES_TO_OVERWRITE,
    _existing_verdict_games, gate_cross,
)
from scripts.platformkit.ingame.ingame_gate_generic_models import load_states
from scripts.platformkit.io_atomic import write_json_atomic


def gate_on_paths(sport: str, paths: List[str], *,
                  caveats: Optional[List[str]] = None) -> GenericVerdict:
    """Gate the EXACT corpus paths given (NOT a re-glob). Needs exactly two (A/B)."""
    cav = list(caveats or [])
    if len(paths) != 2:
        return GenericVerdict("INSUFFICIENT_DATA", sport, {}, {},
                              {"corpora_given": len(paths)},
                              cav + ["gate_on_paths needs exactly 2 corpora; got %d"
                                     % len(paths)])
    a, b = load_states(paths[0]), load_states(paths[1])
    return gate_cross(a, b, sport=sport, caveats=cav)


class GatePoolParityError(AssertionError):
    """Raised when the gated A/B split is NOT a disjoint, complete partition of the
    server's fit pool (the BUG A class)."""


def _assert_gate_pool_parity(sport: str, state_dir: Optional[str] = None) -> None:
    """Assert the gated A/B split == the server's fit pool (BUG A parity guard).

    The gate splits ingame_serve.pool_split_ab(sport); its A+B MUST be exactly the pool
    ingame_serve._load_pool(sport) serves -- same games, no double-count, no drop. This
    guard now actually CHECKS that (the prior version computed a value and returned
    without comparing -- a no-op that could never fire). It verifies, on the real pool:
      * every served game is covered by A|B and vice-versa (gate==serve game set), and
      * A and B share NO game (leak-free cross-corpus split, the soccer combos+singles
        double-count class), and
      * A+B state count == pool state count (no state dropped or duplicated).
    Restricted to the real cache (state_dir is None); offline tmp tests skip it. Raises
    GatePoolParityError on a genuine divergence so the loop surfaces it instead of
    silently gating the wrong data.
    """
    if state_dir is not None:
        return  # offline tmp dir: the real-cache glob is irrelevant
    try:
        from scripts.platformkit.ingame import ingame_serve as _serve
        pool = _serve._load_pool(sport)
        a, b = _serve.pool_split_ab(sport)
    except Exception:  # noqa: BLE001 -- parity probe must never crash the gate on I/O
        return
    if not pool:
        return  # nothing on disk yet -> gate_cross will return INSUFFICIENT_DATA honestly
    ga = {s["game_id"] for s in a}
    gb = {s["game_id"] for s in b}
    gp = {s["game_id"] for s in pool}
    overlap = ga & gb
    if overlap:
        raise GatePoolParityError(
            "%s: A/B split games overlap (cross-corpus double-count) -- e.g. %r"
            % (sport, sorted(overlap)[:3]))
    if (ga | gb) != gp:
        raise GatePoolParityError(
            "%s: gated A|B games != served pool games (gate!=serve): "
            "gate=%d pool=%d" % (sport, len(ga | gb), len(gp)))
    if len(a) + len(b) != len(pool):
        raise GatePoolParityError(
            "%s: A+B state count %d != pool state count %d (state dropped/duplicated)"
            % (sport, len(a) + len(b), len(pool)))


def _write(verdict: GenericVerdict, fname: str, out_dir: Optional[str] = None) -> str:
    """Write verdict JSON, with a write-guard when out_dir is None (production path).

    If out_dir is None (the production path) and the verdict is thin/INSUFFICIENT and an
    existing richer file is already present, the production file is NOT overwritten.
    Tests/offline callers must inject out_dir (a tmp path) so synthetic thin verdicts
    never touch the real data/frontend/ingame directory.
    """
    target_dir = out_dir if out_dir is not None else _OUT_DIR
    os.makedirs(target_dir, exist_ok=True)
    out = os.path.join(target_dir, fname)
    if out_dir is None:
        # WRITE-GUARD: skip clobbering a richer production verdict with a thin run.
        new_games = (verdict.coverage.get("a_games", 0) + verdict.coverage.get("b_games", 0))
        thin = verdict.verdict == "INSUFFICIENT_DATA" or new_games < _MIN_GAMES_TO_OVERWRITE
        if thin and os.path.exists(out) and _existing_verdict_games(out) > new_games:
            return out  # silently skip; production file is richer
    # Crash-safe: tmp+os.replace via the shared helper, not a bare open()+json.dump
    # (a kill mid-write on the always-on refresh loop used to leave torn JSON --
    # gap_ledger_ultra16.md row 1).
    write_json_atomic(out, verdict.to_dict(), encoding="ascii", indent=2)
    return out


def _gate_full_pool(sport: str, *, extra_caveats: List[str]) -> GenericVerdict:
    """Gate the FULL server pool split A<->B held-out-by-corpus (the BUG A fix core).

    pool_split_ab pools EXACTLY what ingame_serve.fit_servable serves, so the verdict is
    earned on the served model itself and the gated corpora == the fit pool.
    """
    from scripts.platformkit.ingame import ingame_serve as _serve
    a, b = _serve.pool_split_ab(sport)
    caveats = extra_caveats + [
        "LOOP-CONSISTENT gate: splits ingame_serve.pool_split_ab(sport) -- A+B is the "
        "EXACT pool fit_servable serves (incl. any rolling refresh corpus). gate==serve "
        "by construction (BUG A fix): a newly-folded game is in BOTH the split and the "
        "served fit, so the verdict reflects appended data.",
        "True cross-corpus A<->B held-out by canonical corpus; BASE slope + blend "
        "surface fit on TRAIN only; DM clustered by game_id. No $ -- CALIBRATION only.",
    ]
    return gate_cross(a, b, sport=sport, caveats=caveats)


def gate_refresh_generic(sport: str, state_dir: Optional[str] = None,
                         out_dir: Optional[str] = None) -> GenericVerdict:
    """Re-gate a GENERIC sport on the FULL server pool; write gate_<sport>.json.

    For an offline test that seeds a tmp state_dir, point the server's pool at it so the
    gate and the (test) server agree; otherwise gate the real cache pool.
    out_dir: inject a tmp path in tests so the verdict file never touches production.
    """
    if state_dir is not None:
        v = _gate_tmp_dir(sport, state_dir)
    else:
        _assert_gate_pool_parity(sport)
        v = _gate_full_pool(sport, extra_caveats=[])
    _write(v, "gate_%s.json" % sport, out_dir=out_dir)
    return v


def _gate_tmp_dir(sport: str, state_dir: str) -> GenericVerdict:
    """Gate every {sport}_states__*.parquet under a tmp state_dir, split by file parity.

    Mirrors pool_split_ab but rooted at an injected dir so an offline test that appends a
    new game sees it flow into the gate -- without touching the real cache.
    """
    import glob
    paths = sorted(glob.glob(os.path.join(str(state_dir),
                                          "%s_states__*.parquet" % sport)))
    if len(paths) < 1:
        return GenericVerdict("INSUFFICIENT_DATA", sport, {}, {},
                              {"corpora_present": 0},
                              ["no %s corpora under %s" % (sport, state_dir)])
    a: List[dict] = []
    b: List[dict] = []
    for i, p in enumerate(paths):
        (a if i % 2 == 0 else b).extend(load_states(p))
    if len(paths) == 1:  # a single rolling corpus -> split its games by hash for the test
        from scripts.platformkit.ingame.ingame_refresh_corpora import corpus_for
        allrows = a + b
        a = [s for s in allrows if corpus_for(s["game_id"]) == 0]
        b = [s for s in allrows if corpus_for(s["game_id"]) == 1]
    return gate_cross(a, b, sport=sport, caveats=[
        "LOOP-CONSISTENT gate (tmp state_dir): full pool of seeded corpora, split A<->B; "
        "a newly-appended game flows into the gate. CALIBRATION only, no $."])


def gate_refresh_nba(state_dir: Optional[str] = None,
                     out_dir: Optional[str] = None) -> GenericVerdict:
    """Re-gate NBA on the SAME pool the server fits; write finegrain_nba.json.

    Uses ingame_serve.pool_split_ab('nba') (frozen refresh corpora + native pbp_states),
    so the served verdict updates from the loop and is earned on the served model.
    out_dir: inject a tmp path in tests so the verdict file never touches production.
    """
    if state_dir is not None:
        v = _gate_tmp_dir("nba", state_dir)
        _write(v, "finegrain_nba.json", out_dir=out_dir)
        return v
    _assert_gate_pool_parity("nba")
    v = _gate_full_pool("nba", extra_caveats=[
        "NBA: pool includes the native pbp_states corpus via the NBA adapter."])
    _write(v, "finegrain_nba.json", out_dir=out_dir)
    return v


def gate_refresh(sport: str, state_dir: Optional[str] = None,
                 out_dir: Optional[str] = None) -> GenericVerdict:
    """Dispatch: NBA -> finegrain_nba.json pool gate; else -> generic refresh gate.

    The ONE entry point the refresh loop's gate_fn calls so the gate ALWAYS sees the
    same corpora the runner appends + the server fits, and writes the verdict file the
    server reads (unified per sport).
    out_dir: inject a tmp path in tests/offline runs so thin verdicts never clobber
    production data/frontend/ingame files.
    """
    if sport == "nba":
        return gate_refresh_nba(state_dir=state_dir, out_dir=out_dir)
    return gate_refresh_generic(sport, state_dir=state_dir, out_dir=out_dir)


__all__ = [
    "gate_on_paths", "gate_refresh", "gate_refresh_generic", "gate_refresh_nba",
]
