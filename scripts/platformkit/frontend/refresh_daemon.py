"""scripts.platformkit.frontend.refresh_daemon -- keep board snapshots fresh.

A tiny background loop that periodically rebuilds the per-sport board snapshots
that serve.py READS. snapshot_writer.build_snapshot computes a sport's board ONCE
and writes it atomically; this daemon just calls write_all on a cadence so the
server's cheap reads always see a recent snapshot.

The contract is DEGRADE, NEVER DIE: if the writer raises on a tick we LOG and keep
going -- the last-good snapshots stay on disk (we never delete them), so a transient
failure (down odds feed, flaky network) just means the board is a little stale, not
dark. run_once and run_forever never raise.

HONEST: this only refreshes a local decision-support cache. Markets are efficient;
NO $ edge is claimed. No network at import time; snapshot_writer is injectable so
tests run offline.

Run:
  python -m scripts.platformkit.frontend.refresh_daemon                 # loop, 60s
  python -m scripts.platformkit.frontend.refresh_daemon --once          # one tick
  python -m scripts.platformkit.frontend.refresh_daemon --interval 30 \
      --sports soccer_intl nba

INVARIANTS: never edit src/ or kernel/; reuse the domain seams; <=300 LOC; no secrets.
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.frontend import snapshot_writer as _snapshot_writer

logger = logging.getLogger(__name__)

# Type of the writer seam: write_all(sports) -> {sport: path}. Injectable for tests.
Writer = Callable[..., Dict[str, str]]


def _utc_stamp() -> str:
    """Current UTC time as a short ISO stamp (seconds resolution), for logs/CLI."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_once(sports: Optional[List[str]] = None,
             writer: Optional[Writer] = None) -> Dict[str, str]:
    """Run ONE refresh tick: call the writer to rebuild every sport's snapshot.

    *writer* defaults to snapshot_writer.write_all and is injectable for tests.
    Returns the writer's {sport: path} map. On ANY error from the writer we LOG
    and return an empty dict -- the last-good snapshots already on disk are left
    untouched (never deleted), so the server keeps serving slightly-stale data
    rather than dark-screening. NEVER raises.
    """
    w = writer if writer is not None else _snapshot_writer.write_all
    try:
        paths = w(sports)
    except Exception as exc:  # noqa: BLE001 -- a bad tick must not kill the daemon
        logger.warning("refresh tick failed (keeping last-good snapshots): %s", exc)
        return {}
    return paths if isinstance(paths, dict) else {}


def run_forever(interval_s: float = 60.0,
                sports: Optional[List[str]] = None,
                writer: Optional[Writer] = None,
                sleep: Callable[[float], Any] = time.sleep,
                max_ticks: Optional[int] = None) -> int:
    """Refresh snapshots every *interval_s* seconds, forever (or *max_ticks* times).

    Each tick calls run_once (which already swallows writer errors); we ALSO wrap
    the whole tick in a guard so nothing -- not even an unexpected logging error --
    can kill the loop. *sleep* and *writer* are injectable so tests run a bounded,
    instant loop. *max_ticks* (None = unbounded) caps the number of ticks for tests
    and one-shot runs. Returns the number of ticks performed. NEVER raises.
    """
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        try:
            paths = run_once(sports, writer)
            logger.info("refresh tick %d @ %s -> %d snapshot(s)",
                        ticks + 1, _utc_stamp(), len(paths))
        except Exception as exc:  # noqa: BLE001 -- belt-and-suspenders: never die
            logger.warning("refresh loop guard caught: %s", exc)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            sleep(interval_s)
        except Exception as exc:  # noqa: BLE001 -- a bad sleep must not kill the loop
            logger.warning("refresh sleep interrupted: %s", exc)
            break
    return ticks


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: loop snapshot refresh (or a single --once tick) and print each tick."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(
        description="Periodically rebuild the board snapshots that serve.py reads.")
    ap.add_argument("--interval", type=float, default=60.0,
                    help="seconds between refresh ticks (default: 60)")
    ap.add_argument("--sports", nargs="+", default=None,
                    help="sports to refresh (default: snapshot_writer's all-sports)")
    ap.add_argument("--once", action="store_true",
                    help="run a single refresh tick and exit")
    a = ap.parse_args(argv)

    print(getattr(_snapshot_writer.slate_mod, "HONEST_NOTE",
                  "Decision-support cache refresh; markets efficient, no edge claimed."))

    def _tick_print(paths: Dict[str, str]) -> None:
        stamp = _utc_stamp()
        if not paths:
            print(f"[{stamp}] no snapshots written (kept last-good)")
            return
        for sport, p in paths.items():
            print(f"[{stamp}] {sport}: {p}")

    if a.once:
        _tick_print(run_once(a.sports))
        return 0

    print(f"[{_utc_stamp()}] refresh daemon: every {a.interval}s (Ctrl-C to stop)")
    try:
        while True:
            _tick_print(run_once(a.sports))
            time.sleep(a.interval)
    except KeyboardInterrupt:  # pragma: no cover -- operator stop
        print(f"[{_utc_stamp()}] refresh daemon stopped")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
