"""S221 construct probe for foundry queue lease and sport-binding behavior.

Runs only against fresh temporary SQLite databases.  It does not open a pod,
the repository cache, the register, or the ledger.
"""
from __future__ import annotations

import json
import signal
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from scripts.platformkit.foundry.grammar import Hypothesis
from scripts.platformkit.foundry.results_db import ResultsDB
from scripts.platformkit.foundry.runner_leases import claim_lifecycle


TIER = "T0"
SPORT = "nba"
HORIZONS = (901, 1801)
LIFECYCLES = ("heartbeat_running", "heartbeat_stopped", "sigterm_restart")
BINDINGS = (("bound", SPORT), ("unbound", None))


def _stamp(base: datetime, seconds: int) -> str:
    return (base + timedelta(seconds=seconds)).isoformat()


def _seed(db: ResultsDB) -> list[str]:
    """Seed exactly three valid, sport-bound construct hypotheses."""
    hashes = []
    for half_life in (3, 5, 10):
        hypothesis = Hypothesis(
            SPORT,
            "pace_diff_asof",
            "ew",
            (("halflife", half_life),),
            frozenset(),
            "pregame",
            "ml",
            family="s221_construct",
        )
        hashes.append(db.upsert_hypothesis(hypothesis))
    db.enqueue(hashes, TIER)
    return hashes


def _assert_no_sport_null_at_startup(db: ResultsDB) -> int:
    """Exercise the seed guard and return the queued sport-NULL count."""
    hypothesis = Hypothesis(
        SPORT,
        "pace_null",
        "ew",
        (("halflife", 20),),
        frozenset(),
        "pregame",
        "ml",
        family="s221_construct",
    )
    digest = db.upsert_hypothesis(hypothesis)
    db._c.execute("UPDATE hypothesis SET sport=NULL WHERE hash=?", (digest,))
    try:
        db.enqueue([digest], TIER)
    except ValueError:
        pass
    else:
        raise AssertionError("sport-NULL seed was not refused")
    return len(db.undrainable_queued())


def _invoke_sigterm_handler(db: ResultsDB, hashes: list[str]) -> None:
    """Exercise claim_lifecycle's installed SIGTERM handler without a pod process."""
    with claim_lifecycle(db) as owner:
        if len(db.claim(3, tier=TIER, owner=owner)) != 3:
            raise AssertionError("initial SIGTERM lifecycle claim did not hold three rows")
        handler = signal.getsignal(signal.SIGTERM)
        if not callable(handler):
            raise AssertionError("SIGTERM lifecycle handler was not installed")
        try:
            handler(signal.SIGTERM, None)
        except SystemExit:
            pass
    if db._c.execute("SELECT COUNT(*) FROM queue WHERE claimed_at IS NULL").fetchone()[0] != 3:
        raise AssertionError("SIGTERM lifecycle did not release unfinished rows")
    if len(db.claim(3, tier=TIER, owner="runner-a-restarted")) != 3:
        raise AssertionError("restarted runner did not reclaim its released rows")


def _apply_lifecycle(db: ResultsDB, hashes: list[str], lifecycle: str,
                     horizon: int, base: datetime) -> bool:
    """Make runner A hold the construct rows through the checked horizon."""
    if lifecycle == "heartbeat_running":
        if len(db.claim(3, tier=TIER, owner="runner-a-heartbeat")) != 3:
            raise AssertionError("heartbeat runner did not claim its construct rows")
        for offset in range(800, horizon, 800):
            if db.renew(hashes, lease_seconds=900, now=_stamp(base, offset)) != 3:
                raise AssertionError("heartbeat did not renew every claimed row")
        return False
    if lifecycle == "heartbeat_stopped":
        if len(db.claim(3, tier=TIER, owner="runner-a-stopped")) != 3:
            raise AssertionError("stopped runner did not claim its construct rows")
        return False
    if lifecycle == "sigterm_restart":
        _invoke_sigterm_handler(db, hashes)
        return True
    raise ValueError("unknown lifecycle: {0}".format(lifecycle))


def _run_case(temp_root: Path, lifecycle: str, binding_name: str,
              sport: Optional[str], horizon: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="s221_", dir=str(temp_root)) as temp_dir:
        db = ResultsDB(Path(temp_dir) / "construct.sqlite")
        try:
            hashes = _seed(db)
            sport_null_queued = _assert_no_sport_null_at_startup(db)
            base = datetime.now(timezone.utc)
            sigterm_handler_exercised = _apply_lifecycle(db, hashes, lifecycle, horizon, base)
            db.reap_expired(_stamp(base, horizon))
            claimed_by_b = db.claim(3, tier=TIER, sport=sport, owner="runner-b")
            return {
                "horizon_seconds": horizon,
                "lifecycle": lifecycle,
                "runner_b_double_claimed": len(claimed_by_b),
                "sigterm_handler_exercised": sigterm_handler_exercised,
                "sport_binding": binding_name,
                "sport_null_queued_startup": sport_null_queued,
            }
        finally:
            db.close()


def run_probe(temp_root: Path | None = None) -> dict[str, Any]:
    """Enumerate all S221 construct cases against isolated temporary stores."""
    root = Path.cwd() if temp_root is None else Path(temp_root)
    cases = []
    for horizon in HORIZONS:
        for lifecycle in LIFECYCLES:
            for binding_name, sport in BINDINGS:
                cases.append(_run_case(root, lifecycle, binding_name, sport, horizon))
    if len(cases) != 12:
        raise AssertionError("S221 requires exactly 12 enumerated cases")
    return {
        "cases": cases,
        "differential": [],
        "metric": "runner_b_double_claimed and sport_null_queued_startup per case",
        "n": len(cases),
        "q9": "not applicable: construct queue probe has no scored model comparison",
    }


def render_table(summary: dict[str, Any]) -> str:
    """Render the exhaustive case grid with ASCII-only cells."""
    lines = [
        "lifecycle | sport_binding | horizon_seconds | runner_b_double_claimed | sport_null_queued_startup",
        "--- | --- | ---: | ---: | ---:",
    ]
    for case in summary["cases"]:
        lines.append(
            "{0} | {1} | {2} | {3} | {4}".format(
                case["lifecycle"],
                case["sport_binding"],
                case["horizon_seconds"],
                case["runner_b_double_claimed"],
                case["sport_null_queued_startup"],
            )
        )
    return "\n".join(lines)


def main() -> None:
    """Print the S221 case grid and machine-readable construct summary."""
    summary = run_probe()
    print("S221 isolated temporary SQLite construct probe")
    print(render_table(summary))
    print("summary_json={0}".format(json.dumps(summary, sort_keys=True)))


if __name__ == "__main__":
    main()
