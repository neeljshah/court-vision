"""scripts.platformkit.ingame.ingame_refresh_runner_svc -- supervised entry for the
LIVING in-game refresh loop (the self-improving in-game calibration engine).

A thin, runnable wrapper around ``ingame_refresh_runner.run_refresh_forever`` so the
M9 supervisor can spawn it as ``python -u -m
scripts.platformkit.ingame.ingame_refresh_runner_svc`` and keep it alive,
checkpoint-resumable across restarts.

WHY a wrapper (mirrors selfimprove_runner / inplay_runner):
  * ``run_refresh_forever`` is pure glue requiring injected feeds; it is intentionally
    not runnable on its own. This svc supplies the REAL wiring: the keyless-ESPN
    settled-finals feed, the per-sport state ingest, the generic gate, and the servable
    re-fit -- plus a liveness heartbeat and a clean CLI.
  * It resumes LOSSLESSLY from the per-sport checkpoint cursor (a restart never
    reprocesses an already-folded game).

SAFETY: the DEFAULT settled feed returns an EMPTY list unless a real keyless-ESPN
finals provider is present, so with no in-season finals nothing is folded, no artifact
is swapped, no flag is flipped, no registry is written -- the loop just beats its
heartbeat. The gate + re-fit reuse the proven ingame_gate_generic / ingame_serve.

Heartbeat component: ``m7_ingame_refresh`` ->
data/cache/daemon_heartbeats/m7_ingame_refresh.txt (consumed by ops.liveness via
service_registry, so it lands in the single status.json).

INVARIANTS: never edits MEMORY.md, never writes data/registry/, never flips a flag,
calibration not edge. Stdlib + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.ingame.ingame_refresh_runner import run_refresh_forever

logger = logging.getLogger("ingame_refresh_runner_svc")

HEARTBEAT_COMPONENT = "m7_ingame_refresh"
DEFAULT_SPORTS = ("mlb", "soccer", "tennis", "nba")
# In-season sports settle new games daily; NBA is off-season most of the year so its
# feed simply returns [] -> NO_NEW (still honest + harmless).


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the liveness heartbeat for this service. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001 -- liveness write must never sink loop
        logger.debug("ingame_refresh heartbeat skipped: %s", exc)


def _default_settled_games_fn(sport: str, *, since: Any = "",
                              seen_ids: Optional[Sequence[str]] = None,
                              **_kw) -> List[Dict[str, Any]]:
    """Newly-settled in-season finals for ``sport`` not yet folded.

    Wired to the keyless-ESPN provider settled_finals.settled_since with DEDUP by
    game_id via ``seen_ids`` (the runner threads the on-disk seen set), so an
    out-of-order late final is surfaced rather than key-skipped. Absent provider /
    dead feed -> [] (the cycle then logs NO_NEW and just advances). NEVER raises.
    """
    try:  # the real keyless-ESPN finals provider
        from scripts.platformkit.ingame import settled_finals as _sf  # type: ignore
    except Exception:  # noqa: BLE001
        return []
    try:
        return list(_sf.settled_since(sport, since=since, seen_ids=seen_ids))
    except Exception as exc:  # noqa: BLE001
        logger.debug("settled_games_fn(%s) unavailable: %s", sport, exc)
        return []


def _default_ingest_fn(sport: str, game: Dict[str, Any],
                       **_kw) -> List[Dict[str, Any]]:
    """Reconstruct one settled game's frozen-schema in-game states.

    Delegates to the sport's own ingest adapter via an optional dispatcher; absent ->
    [] (the game is skipped, never fabricated). NEVER raises.
    """
    try:
        from scripts.platformkit.ingame import settled_finals as _sf  # type: ignore
    except Exception:  # noqa: BLE001
        return []
    try:
        return list(_sf.states_for_game(sport, game))  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingest_fn(%s) unavailable: %s", sport, exc)
        return []


def _default_gate_fn(sport: str):
    """Re-gate the SAME corpora the runner appends + the server fits (C1/C2 fix).

    Routes through ingame_gate_refresh.gate_refresh: a generic sport gates its
    refresh_a/_b corpora (with a parity assertion vs the server's fit pool) and writes
    gate_<sport>.json; NBA gates the EXACT served pool and writes finegrain_nba.json --
    the ONE verdict file ingame_serve reads. (The old run('nba') wrote gate_nba.json,
    which the server ignored, and re-globbed the wrong/stale corpora.)
    """
    from scripts.platformkit.ingame.ingame_gate_refresh import gate_refresh
    return gate_refresh(sport)


def _default_fit_fn(sport: str) -> Dict[str, Any]:
    """Re-fit + persist the servable in-game model for ``sport``."""
    from scripts.platformkit.ingame.ingame_serve import fit_servable
    return fit_servable(sport)


def _beating_sleep(base_sleep: Callable[[float], None],
                   clock: Optional[Callable[[], float]]) -> Callable[[float], None]:
    """Wrap sleep so a heartbeat lands on every cycle boundary. Never raises."""
    def _sleep(seconds: float) -> None:
        now = None
        if clock is not None:
            try:
                now = float(clock())
            except Exception:  # noqa: BLE001
                now = None
        _beat(now)
        base_sleep(seconds)
    return _sleep


def run(*, sports: Sequence[str] = DEFAULT_SPORTS,
        settled_games_fn: Optional[Callable[..., Sequence[Dict[str, Any]]]] = None,
        ingest_fn: Optional[Callable[..., Sequence[Dict[str, Any]]]] = None,
        gate_fn: Optional[Callable[[str], Any]] = None,
        fit_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
        cadence_sec: float = 3600.0,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_cycles: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None,
        **kwargs) -> List[Any]:
    """Run the checkpoint-resumable in-game refresh loop + a liveness heartbeat.

    Defaults are honest no-op when no in-season finals are available. Everything is
    injectable so an offline test drives it with a fake clock/sleep, seeded feeds, a
    bounded ``max_cycles`` and an isolated checkpoint/store. NEVER raises out.
    """
    import time as _time
    base_sleep = sleep if sleep is not None else _time.sleep
    _beat()  # live before the first cycle completes
    return run_refresh_forever(
        sports=tuple(sports),
        settled_games_fn=settled_games_fn or _default_settled_games_fn,
        ingest_fn=ingest_fn or _default_ingest_fn,
        gate_fn=gate_fn or _default_gate_fn,
        fit_fn=fit_fn or _default_fit_fn,
        clock=clock, sleep=_beating_sleep(base_sleep, clock),
        cadence_sec=float(cadence_sec), max_cycles=max_cycles,
        should_stop=should_stop, on_tick=lambda: _beat(clock() if clock else None),
        **kwargs)


def _main() -> int:  # pragma: no cover -- thin CLI shim
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Supervised in-game REFRESH runner (the living in-game loop): "
                    "folds newly-settled finals into the corpora, re-gates, re-fits "
                    "+ honesty-gated-swaps the served model. Calibration, not edge.")
    p.add_argument("--sports", default=",".join(DEFAULT_SPORTS),
                   help="Comma-separated sport ids (default: %s)."
                        % ",".join(DEFAULT_SPORTS))
    p.add_argument("--cadence", type=float, default=3600.0,
                   help="Seconds between refresh sweeps (default hourly).")
    a = p.parse_args()
    sport_list = tuple(s.strip() for s in a.sports.split(",") if s.strip())
    print("ingame_refresh_runner_svc | started sports=%s cadence=%ss component=%s"
          % (",".join(sport_list), a.cadence, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(sports=sport_list, cadence_sec=a.cadence)
    except KeyboardInterrupt:
        print("ingame_refresh_runner_svc | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["HEARTBEAT_COMPONENT", "DEFAULT_SPORTS", "run"]
