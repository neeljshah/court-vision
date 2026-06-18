"""scripts.platformkit.frontend.snapshot_writer -- compute a sport's board ONCE per cycle.

Phase-0 snapshot keystone. Instead of the FastAPI server (serve.py) and the paper
bettor each recomputing a sport's slate + live board per request, this module builds
the board ONCE and writes it atomically to data/frontend/snapshots/<sport>.json. Both
readers then READ that snapshot -- one expensive compute, many cheap reads.

It does NOT reimplement any prediction math. It calls the REAL seams:
  * slate.build_slate(sport, odds_lookup=...)          -- the honest pregame slate
  * live_board.todays_live_games(sport)                -- today's real + live games
  * aggregate.to_odds_lookup(sport)                    -- the keyless multi-book odds

All three are GUARDED (imported behind try/except, mirroring serve.py) and INJECTABLE
so tests run network-free. Odds failure -> slate built without odds (never blocks).
Live failure -> live=None with a note. Any failure -> a written envelope with
status="unavailable" and a reason. The public functions NEVER raise.

The write is atomic (write .tmp then os.replace) so a concurrent reader never sees a
half-written file. data/ is gitignored -- correct; snapshots are a local cache.

HONEST: markets are efficient -- NO $ edge is claimed. Decision-support only.

INVARIANTS: never edit src/ or kernel/; reuse the domain predictors; <=300 LOC; no secrets.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.frontend import slate as slate_mod

logger = logging.getLogger(__name__)

# Guarded imports, mirroring serve.py: a refactor of any of these must never sink the
# snapshot writer. When absent the writer degrades (no odds / no live) but still writes.
try:  # live board: today's real games + in-game predictions
    from scripts.platformkit.frontend import live_board as _live_board
except Exception:  # pragma: no cover - optional dependency guard
    _live_board = None
try:  # our own keyless multi-book odds aggregator
    from scripts.platformkit.odds_provider.aggregate import to_odds_lookup as _to_odds_lookup
except Exception:  # pragma: no cover - provider optional
    _to_odds_lookup = None
try:  # ranked player-prop edge board (the COMPUTE step; belongs in the snapshot)
    from scripts.platformkit.prop_edge import build_prop_board as _build_prop_board
except Exception:  # pragma: no cover - props feature simply absent if unimportable
    _build_prop_board = None

# Snapshots live under the gitignored data/ tree (a local cache, never committed).
# __file__ = scripts/platformkit/frontend/snapshot_writer.py -> parents[3] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = _REPO_ROOT / "data" / "frontend" / "snapshots"


def _utc_iso(now: Optional[datetime] = None) -> str:
    """Current UTC time as an ISO string (injectable *now* for deterministic tests)."""
    dt = now if now is not None else datetime.now(timezone.utc)
    return dt.isoformat()


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    """Write *payload* as JSON to *path* atomically (tmp file + os.replace).

    A reader polling the snapshot therefore sees either the OLD file or the COMPLETE
    new file -- never a half-written one. Parent dirs are created as needed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, default=str, ensure_ascii=True)
    os.replace(tmp, path)  # atomic on the same filesystem


def _build_odds_lookup(sport: str,
                       odds_lookup_factory: Optional[Callable[[str], Any]]) -> Any:
    """Build the slate's odds_lookup from the factory, GUARDED. None on any failure."""
    if odds_lookup_factory is None:
        return None
    try:
        return odds_lookup_factory(sport)
    except Exception as exc:  # noqa: BLE001 -- odds must never block the snapshot
        logger.warning("snapshot odds_lookup factory failed for %s: %s", sport, exc)
        return None


def _build_slate(sport: str, slate_builder: Callable[..., Dict[str, Any]],
                 odds_lookup: Any) -> Dict[str, Any]:
    """Call the slate builder ONCE (with odds if available), GUARDED -> dict.

    First tries WITH odds; if that raises, retries WITHOUT odds (a slow/broken odds
    feed must not cost us the model-only slate). Returns an unavailable stub if even
    the bare slate raises. Never raises.
    """
    try:
        if odds_lookup is not None:
            return slate_builder(sport, odds_lookup=odds_lookup)
        return slate_builder(sport)
    except Exception as exc:  # noqa: BLE001
        logger.warning("snapshot slate(+odds) failed for %s: %s; retry bare", sport, exc)
    try:
        return slate_builder(sport)
    except Exception as exc:  # noqa: BLE001
        logger.warning("snapshot bare slate failed for %s: %s", sport, exc)
        return {"sport": sport, "status": "unavailable", "rows": [],
                "honest_note": slate_mod.HONEST_NOTE,
                "note": f"slate build error ({type(exc).__name__})"}


def _build_live(sport: str,
                live_builder: Optional[Callable[..., Dict[str, Any]]]) -> Dict[str, Any]:
    """Call the live builder ONCE, GUARDED. Returns the live payload or an unavailable
    stub (live=None upstream maps to a note). Never raises."""
    if live_builder is None:
        return {"sport": sport, "status": "unavailable", "games": [],
                "note": "live_board module not importable"}
    try:
        return live_builder(sport)
    except Exception as exc:  # noqa: BLE001 -- live must never sink the snapshot
        logger.warning("snapshot live board failed for %s: %s", sport, exc)
        return {"sport": sport, "status": "unavailable", "games": [],
                "note": f"live board error ({type(exc).__name__})"}


def _build_props(sport: str,
                 prop_builder: Optional[Callable[..., Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """Call the prop-edge builder ONCE, GUARDED. None when the feature is absent
    (no builder); on any failure returns {"status":"unavailable","reason":...} so a
    provider/parquet error degrades the props section WITHOUT blocking slate/live.
    Never raises."""
    if prop_builder is None:
        return None
    try:
        return prop_builder(sport)
    except Exception as exc:  # noqa: BLE001 -- props must never sink the snapshot
        logger.warning("snapshot prop board failed for %s: %s", sport, exc)
        return {"status": "unavailable", "edges": [],
                "reason": f"prop board error ({type(exc).__name__})"}


def build_snapshot(sport: str, *,
                   slate_builder: Optional[Callable[..., Dict[str, Any]]] = None,
                   live_builder: Optional[Callable[..., Dict[str, Any]]] = None,
                   odds_lookup_factory: Optional[Callable[[str], Any]] = None,
                   prop_builder: Optional[Callable[..., Dict[str, Any]]] = None,
                   out_dir: Optional[Path] = None,
                   now: Optional[datetime] = None) -> Dict[str, Any]:
    """Compute *sport*'s board ONCE and write it atomically to <out_dir>/<sport>.json.

    The seams default to the real ones (slate.build_slate, live_board.
    todays_live_games, aggregate.to_odds_lookup, prop_edge.build_prop_board) and are
    ALL injectable for tests. The props section is GUARDED + optional (None when no
    builder, "unavailable" on failure) and never blocks slate/live. Returns the
    written envelope. NEVER raises -- any failure yields an envelope with
    status="unavailable" and a reason, which is still written to disk.
    """
    sport = sport.lower()
    target_dir = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR
    path = target_dir / f"{sport}.json"
    generated_at = _utc_iso(now)
    sb = slate_builder if slate_builder is not None else slate_mod.build_slate
    lb = live_builder
    if lb is None and _live_board is not None:
        lb = _live_board.todays_live_games
    olf = odds_lookup_factory
    if olf is None and _to_odds_lookup is not None:
        olf = _to_odds_lookup
    pb = prop_builder if prop_builder is not None else _build_prop_board

    try:
        odds_lookup = _build_odds_lookup(sport, olf)
        slate_payload = _build_slate(sport, sb, odds_lookup)
        live_payload = _build_live(sport, lb)
        props_payload = _build_props(sport, pb)
        slate_ok = (slate_payload or {}).get("status") == "ok"
        envelope: Dict[str, Any] = {
            "sport": sport,
            "generated_at": generated_at,
            "status": "ok" if slate_ok else "unavailable",
            "slate": slate_payload,
            "live": live_payload,
            "props": props_payload,
            "freshness": {"as_of": generated_at, "source": "snapshot"},
            "honest_note": slate_mod.HONEST_NOTE,
        }
    except Exception as exc:  # noqa: BLE001 -- belt-and-suspenders: never raise
        logger.warning("snapshot build crashed for %s: %s", sport, exc)
        envelope = {
            "sport": sport,
            "generated_at": generated_at,
            "status": "unavailable",
            "slate": None,
            "live": None,
            "props": None,
            "freshness": {"as_of": generated_at, "source": "snapshot"},
            "honest_note": slate_mod.HONEST_NOTE,
            "note": f"snapshot build error ({type(exc).__name__})",
        }

    try:
        _atomic_write(path, envelope)
    except Exception as exc:  # noqa: BLE001 -- a write failure must not raise either
        logger.warning("snapshot write failed for %s -> %s: %s", sport, path, exc)
        envelope.setdefault("note", f"snapshot write error ({type(exc).__name__})")
    return envelope


def write_all(sports: Optional[List[str]] = None, **kw: Any) -> Dict[str, str]:
    """Build + write a snapshot for every sport in *sports* (default slate.SPORTS).

    Returns {sport: path-string}. One sport failing NEVER stops the others -- every
    sport is attempted; a per-sport crash is logged and that sport is skipped from
    the returned map (its envelope, if any, was still written by build_snapshot).
    """
    sport_list = list(sports) if sports is not None else list(slate_mod.SPORTS)
    out_dir = kw.get("out_dir")
    base = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR
    paths: Dict[str, str] = {}
    for sport in sport_list:
        s = sport.lower()
        try:
            build_snapshot(s, **kw)
            paths[s] = str(base / f"{s}.json")
        except Exception as exc:  # noqa: BLE001 -- one sport must not stop the rest
            logger.warning("write_all skipped %s: %s", s, exc)
    return paths


def read_snapshot(sport: str, out_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load <out_dir>/<sport>.json and return it, or None if missing/corrupt.

    The server and paper bettor call this instead of recomputing. A missing file
    (snapshot never written) or a corrupt/partial file both degrade to None -- the
    caller then falls back to a live compute or shows unavailable. Never raises.
    """
    sport = sport.lower()
    target_dir = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR
    path = target_dir / f"{sport}.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:  # noqa: BLE001 -- a corrupt file is just a cache miss
        logger.warning("snapshot read failed for %s -> %s: %s", sport, path, exc)
        return None
    return data if isinstance(data, dict) else None


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: write snapshots for the given sports (or all) and print the paths."""
    ap = argparse.ArgumentParser(
        description="Compute each sport's board ONCE and write data/frontend/snapshots/<sport>.json")
    ap.add_argument("--sports", nargs="+", default=None,
                    help=f"sports to snapshot (default: {' '.join(slate_mod.SPORTS)})")
    ap.add_argument("--out-dir", default=None,
                    help="output dir (default: data/frontend/snapshots)")
    a = ap.parse_args(argv)
    out_dir = Path(a.out_dir) if a.out_dir else None
    paths = write_all(a.sports, out_dir=out_dir)
    print(slate_mod.HONEST_NOTE)
    if not paths:
        print("no snapshots written")
        return 0
    for sport, p in paths.items():
        print(f"{sport}: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
