"""ingame_shadow_logger.py -- SHADOW-log BASE vs ATLAS in-game projections.

This is a strictly read-only/append-only SHADOW logger for the live in-game prop
projection. For a given game it reads the live snapshots that the poller has already
written to ``data/live/<game_id>_<epoch>.json`` and, for each snapshot, computes TWO
projections:

  * BASE  -- ``scripts/predict_in_game.project_snapshot(snap)``  (exactly the value the
             live page / poller returns today; the production default).
  * ATLAS -- ``src.loop.ingame_atlas_corrector.apply_atlas_correction(snap, base, ...)``
             with the ``CV_INGAME_ATLAS`` gate FORCED ON *inside this process only*.

It appends BOTH (snapshot epoch, period, clock, and per-(player,stat) base-vs-atlas
``projected_final``) to its OWN log at
``data/cache/loop/ingame_shadow_<game_id>.jsonl`` -- one JSON object per snapshot.

HARD SAFETY (this logger lives entirely in the shadow lane):
  * It NEVER writes to ``data/live/`` or any live artifact. It only READS snapshots and
    APPENDS to its own ``data/cache/loop/`` log.
  * It does NOT change the live default. The ``CV_INGAME_ATLAS`` flag is forced ON only
    in THIS process's environment; the live api/poller process is untouched, and the
    BASE column it logs is the unmodified live projection.
  * It imports + post-processes the existing projector / corrector; it does not edit
    ``scripts/predict_in_game.py`` or ``src/prediction/live_engine.py``.

Snapshot epoch source: the live filename is ``<game_id>_<epoch_ms>.json``. We parse the
trailing integer as the snapshot epoch (ms). The leak-safe atlas as-of date is taken
from the snapshot's ``captured_at`` (ISO) when present, else derived from that epoch,
else today -- so the atlas join can never see future intelligence.

Run -- one-shot over all existing snapshots for a game:
    set NBA_OFFLINE=1
    python scripts/loop/ingame_shadow_logger.py --game-id 0042500317

Run -- watch mode (poll data/live for new snapshots as they land, until the game is
final or the process is stopped):
    python scripts/loop/ingame_shadow_logger.py --game-id 0042500317 --watch
    python scripts/loop/ingame_shadow_logger.py --game-id 0042500317 --watch \
        --poll-interval 20 --device cpu
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Force the atlas gate ON for THIS process only, BEFORE importing the corrector, so the
# shadow path always computes the atlas projection regardless of the ambient env. This
# does not affect the live api/poller process.
os.environ["CV_INGAME_ATLAS"] = "1"
os.environ.setdefault("NBA_OFFLINE", "1")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import predict_in_game as pig  # noqa: E402  (base projector; never modified)
from src.loop import ingame_atlas_corrector as corrector  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

LIVE_DIR = os.path.join(PROJECT_DIR, "data", "live")
SHADOW_DIR = os.path.join(PROJECT_DIR, "data", "cache", "loop")


# ── snapshot discovery (read-only over data/live) ──────────────────────────────
def snapshot_paths_for_game(game_id: str, live_dir: str = LIVE_DIR) -> List[str]:
    """All snapshot paths for ``game_id``, chronologically by epoch in the filename."""
    pat = os.path.join(live_dir, f"{game_id}_*.json")
    paths = glob.glob(pat)
    return sorted(paths, key=lambda p: _epoch_from_path(p))


def _epoch_from_path(path: str) -> int:
    """Parse the trailing ``_<epoch>.json`` integer from a snapshot filename.

    Returns 0 when the filename has no parseable trailing integer (so such files sort
    first and still log, just with epoch 0).
    """
    base = os.path.basename(path)
    stem = base[:-5] if base.endswith(".json") else base
    tail = stem.rsplit("_", 1)[-1]
    try:
        return int(tail)
    except (TypeError, ValueError):
        return 0


def _asof_iso(snap: Dict[str, Any], epoch_ms: int) -> Optional[str]:
    """Leak-safe atlas as-of date (ISO ``YYYY-MM-DD``) for this snapshot.

    Priority: snapshot ``captured_at`` (ISO) -> the filename epoch (ms) -> today.
    """
    cap = snap.get("captured_at") or snap.get("date")
    if isinstance(cap, str) and len(cap) >= 10:
        return cap[:10]
    if epoch_ms and epoch_ms > 0:
        try:
            return datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc) \
                .date().isoformat()
        except (OverflowError, OSError, ValueError):
            pass
    return datetime.now(tz=timezone.utc).date().isoformat()


# ── projection (base + atlas) for one snapshot ──────────────────────────────────
def _index_by_key(rows: List[Dict[str, Any]]) -> Dict[Tuple[Any, str], Dict[str, Any]]:
    out: Dict[Tuple[Any, str], Dict[str, Any]] = {}
    for r in rows:
        out[(r.get("player_id"), r.get("stat"))] = r
    return out


def shadow_record_for_snapshot(
    path: str, *, device: str = "auto",
) -> Optional[Dict[str, Any]]:
    """Build one shadow-log record for a single snapshot file.

    Returns a JSON-serialisable dict with the snapshot epoch / period / clock and a
    per-(player,stat) list of base-vs-atlas ``projected_final`` values, or ``None`` if
    the snapshot can't be loaded.
    """
    try:
        snap = pig.load_snapshot(path)
    except Exception as exc:
        print(f"  [warn] could not load {path}: {exc}")
        return None

    epoch_ms = _epoch_from_path(path)
    as_of_iso = _asof_iso(snap, epoch_ms)

    # BASE: the exact live projection (untouched).
    base_rows = pig.project_snapshot(snap)
    # ATLAS: forced-on corrector (flag set at import); pass explicit leak-safe as_of so
    # the join never sees the future. apply_atlas_correction rewrites projected_final
    # and records projected_final_base on corrected rows.
    atlas_rows = corrector.apply_atlas_correction(
        snap, [dict(r) for r in base_rows], as_of=as_of_iso, device=device)
    atlas_idx = _index_by_key(atlas_rows)

    projections: List[Dict[str, Any]] = []
    n_changed = 0
    for br in base_rows:
        key = (br.get("player_id"), br.get("stat"))
        base_val = float(br.get("projected_final", 0.0))
        ar = atlas_idx.get(key)
        if ar is not None:
            # projected_final_base is the base value the corrector saw; projected_final
            # is the atlas-corrected value. Fall back to base when not corrected.
            atlas_val = float(ar.get("projected_final", base_val))
        else:
            atlas_val = base_val
        if abs(atlas_val - base_val) > 1e-9:
            n_changed += 1
        projections.append({
            "player_id": br.get("player_id"),
            "name": br.get("name"),
            "team": br.get("team"),
            "stat": br.get("stat"),
            "current": float(br.get("current", 0.0)),
            "base_projected_final": round(base_val, 6),
            "atlas_projected_final": round(atlas_val, 6),
        })

    return {
        "game_id": snap.get("game_id"),
        "snapshot_file": os.path.basename(path),
        "snapshot_epoch_ms": epoch_ms,
        "captured_at": snap.get("captured_at"),
        "atlas_as_of": as_of_iso,
        "game_status": snap.get("game_status"),
        "period": snap.get("period"),
        "clock": snap.get("clock"),
        "home_team": snap.get("home_team"),
        "away_team": snap.get("away_team"),
        "home_score": snap.get("home_score"),
        "away_score": snap.get("away_score"),
        "n_rows": len(projections),
        "n_atlas_changed": n_changed,
        "logged_at": datetime.now(tz=timezone.utc).isoformat(),
        "projections": projections,
    }


# ── shadow-log append (writes ONLY under data/cache/loop) ───────────────────────
def shadow_log_path(game_id: str, out_dir: str = SHADOW_DIR) -> str:
    return os.path.join(out_dir, f"ingame_shadow_{game_id}.jsonl")


def _already_logged(log_path: str) -> set:
    """Snapshot filenames already present in the shadow log (for idempotent re-runs)."""
    done: set = set()
    if not os.path.exists(log_path):
        return done
    try:
        with open(log_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sf = rec.get("snapshot_file")
                if sf:
                    done.add(sf)
    except Exception:
        pass
    return done


def append_record(log_path: str, record: Dict[str, Any]) -> None:
    """Append one record as a JSON line to the shadow log (creates dir/file as needed)."""
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


# ── one-shot + watch drivers ────────────────────────────────────────────────────
def log_existing(
    game_id: str, *, device: str = "auto", out_dir: str = SHADOW_DIR,
    skip_logged: bool = True,
) -> int:
    """Log every existing snapshot for ``game_id`` not already in the shadow log.

    Returns the number of NEW records appended.
    """
    log_path = shadow_log_path(game_id, out_dir)
    done = _already_logged(log_path) if skip_logged else set()
    paths = snapshot_paths_for_game(game_id)
    if not paths:
        print(f"  [info] no snapshots for game_id={game_id} in {LIVE_DIR}")
        return 0
    n = 0
    for p in paths:
        if os.path.basename(p) in done:
            continue
        rec = shadow_record_for_snapshot(p, device=device)
        if rec is None:
            continue
        append_record(log_path, rec)
        done.add(rec["snapshot_file"])
        n += 1
        print(f"  logged {rec['snapshot_file']}  "
              f"period={rec['period']} clock={rec['clock']} "
              f"rows={rec['n_rows']} atlas_changed={rec['n_atlas_changed']}")
    print(f"  -> appended {n} new shadow record(s) to {log_path}")
    return n


def _snap_is_final(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            snap = json.load(fh)
        return str(snap.get("game_status") or "").upper() == "FINAL"
    except Exception:
        return False


def watch(
    game_id: str, *, device: str = "auto", out_dir: str = SHADOW_DIR,
    poll_interval: float = 20.0, max_iters: Optional[int] = None,
    stop_on_final: bool = True,
) -> int:
    """Poll ``data/live`` for new snapshots of ``game_id`` and shadow-log each as it
    lands. Reads only; appends only to the shadow log.

    Stops when (a) ``max_iters`` polls have elapsed, or (b) ``stop_on_final`` and the
    most recent snapshot is FINAL and there is nothing new left to log. Ctrl-C exits
    cleanly. Returns the total number of records appended across the session.
    """
    log_path = shadow_log_path(game_id, out_dir)
    done = _already_logged(log_path)
    total = 0
    it = 0
    print(f"  [watch] game_id={game_id}  poll={poll_interval}s  log={log_path}")
    try:
        while True:
            it += 1
            paths = snapshot_paths_for_game(game_id)
            new_paths = [p for p in paths if os.path.basename(p) not in done]
            for p in new_paths:
                rec = shadow_record_for_snapshot(p, device=device)
                if rec is None:
                    done.add(os.path.basename(p))  # don't retry an unloadable file
                    continue
                append_record(log_path, rec)
                done.add(rec["snapshot_file"])
                total += 1
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] "
                      f"logged {rec['snapshot_file']} period={rec['period']} "
                      f"clock={rec['clock']} atlas_changed={rec['n_atlas_changed']}")
            # Termination checks.
            if stop_on_final and paths and _snap_is_final(paths[-1]) and not new_paths:
                print("  [watch] latest snapshot is FINAL and nothing new -> stopping.")
                break
            if max_iters is not None and it >= max_iters:
                print(f"  [watch] reached max_iters={max_iters} -> stopping.")
                break
            time.sleep(max(1.0, float(poll_interval)))
    except KeyboardInterrupt:
        print("\n  [watch] interrupted -> stopping.")
    print(f"  -> appended {total} shadow record(s) this session to {log_path}")
    return total


# ── CLI ──────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-id", required=True, help="NBA game_id to shadow-log.")
    ap.add_argument("--watch", action="store_true",
                    help="Poll data/live for new snapshots until FINAL / max-iters.")
    ap.add_argument("--poll-interval", type=float, default=20.0,
                    help="Seconds between polls in --watch mode (default 20).")
    ap.add_argument("--max-iters", type=int, default=None,
                    help="Stop --watch after this many polls (default: until FINAL).")
    ap.add_argument("--device", default="auto",
                    help="'auto' (default) / 'cuda' / 'cpu' for the atlas corrector.")
    ap.add_argument("--out-dir", default=SHADOW_DIR,
                    help="Directory for the shadow log (default data/cache/loop).")
    ap.add_argument("--no-skip-logged", action="store_true",
                    help="Re-log snapshots already present in the shadow log (one-shot).")
    args = ap.parse_args()

    print(f"  ingame_shadow_logger: CV_INGAME_ATLAS={os.environ.get('CV_INGAME_ATLAS')} "
          f"NBA_OFFLINE={os.environ.get('NBA_OFFLINE')} device={args.device}")
    print(f"  corrector gate is_enabled() -> {corrector.is_enabled()}")

    if args.watch:
        watch(args.game_id, device=args.device, out_dir=args.out_dir,
              poll_interval=args.poll_interval, max_iters=args.max_iters)
    else:
        log_existing(args.game_id, device=args.device, out_dir=args.out_dir,
                     skip_logged=not args.no_skip_logged)
    return 0


if __name__ == "__main__":
    sys.exit(main())
