"""sbs_shadow_logger.py -- SHADOW-log BASE vs v2-player-line in-game projections.

Strictly read-only / append-only SHADOW logger for the v2 second-by-second (SBS)
player-line head (``src/ingame/continuous_projection.UnifiedPlayerLineProjector``,
validated walk-forward in ``.planning/ingame/eval_curve_v2.json``). For a game it
reads the live box snapshots the poller already wrote to
``data/live/<game_id>_<epoch_ms>.json`` and, for each snapshot, computes per
(player, stat, game-time-bucket):

  * BASE  -- ``scripts/predict_in_game.project_snapshot(snap)``  (exactly the value
             the live page / poller returns today; the production default).
  * V2    -- ``UnifiedPlayerLineProjector.project(v2_row)`` where v2_row is built
             from the snapshot's box-so-far + the player's leak-free L5 prior
             (gamelog games STRICTLY before the game date). This is the validated
             v2 CORE head.
  * GATED -- the value a *server* WOULD use under the validated game-time gate:
             v2 only in the endQ1->midQ3 window; pregame-L5 in Q1; BASE in Q4
             (see src/ingame/sbs_shadow.grid_bucket_for). Logged for reference;
             never served.

It appends one JSON object per snapshot to its OWN log at
``data/cache/ingame/sbs_shadow_<game_id>.jsonl``.

HARD SAFETY (this logger lives entirely in the shadow lane):
  * NEVER writes to ``data/live/`` or any live artifact -- only READS snapshots and
    APPENDS to its own ``data/cache/ingame/`` log.
  * Does NOT change the live default. The NEW ``CV_INGAME_SBS`` gate (default OFF)
    is forced ON only in THIS process so the shadow head always computes; the live
    api/poller process is untouched, and the BASE column is the unmodified live
    projection. When the flag is OFF nothing serves the v2 head anywhere.
  * Imports + post-processes the existing projector / v2 head; it edits no
    production module.

Run -- one-shot over all existing snapshots for a game:
    set NBA_OFFLINE=1
    python scripts/ingame/sbs_shadow_logger.py --game-id 0042500317

Run -- watch mode (poll data/live for new snapshots until FINAL / max-iters):
    python scripts/ingame/sbs_shadow_logger.py --game-id 0042500317 --watch
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

# Force the v2 SBS gate ON for THIS process only, BEFORE importing the shadow
# helpers, so the shadow path always computes the v2 projection regardless of the
# ambient env. Does NOT affect the live api/poller process.
os.environ["CV_INGAME_SBS"] = "1"
os.environ.setdefault("NBA_OFFLINE", "1")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import predict_in_game as pig  # noqa: E402  (base projector; never modified)
from src.ingame import sbs_shadow  # noqa: E402
from src.ingame.continuous_projection import (  # noqa: E402
    UnifiedPlayerLineProjector, SBS_V2_DIR,
)

STATS = sbs_shadow.PLAYER_STATS

LIVE_DIR = os.path.join(PROJECT_DIR, "data", "live")
SHADOW_DIR = os.path.join(PROJECT_DIR, "data", "cache", "ingame")
NBA_DIR = os.path.join(PROJECT_DIR, "data", "nba")


# ── snapshot discovery (read-only over data/live) ──────────────────────────────
def snapshot_paths_for_game(game_id: str, live_dir: str = LIVE_DIR) -> List[str]:
    """All snapshot paths for ``game_id``, chronologically by epoch in the name."""
    paths = glob.glob(os.path.join(live_dir, f"{game_id}_*.json"))
    return sorted(paths, key=_epoch_from_path)


def _epoch_from_path(path: str) -> int:
    base = os.path.basename(path)
    stem = base[:-5] if base.endswith(".json") else base
    tail = stem.rsplit("_", 1)[-1]
    try:
        return int(tail)
    except (TypeError, ValueError):
        return 0


def _game_date_for(game_id: str, snap: Dict[str, Any]):
    """Leak-free game date (datetime.date) for the L5 cutoff.

    Priority: season_games row -> snapshot captured_at/date -> None. Used only as
    the STRICTLY-BEFORE cutoff for the L5 prior, so it can never pull future data.
    """
    # season_games (authoritative)
    for path in glob.glob(os.path.join(NBA_DIR, "season_games_*.json")):
        try:
            data = json.load(open(path, "r", encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for r in data.get("rows", []):
            if str(r.get("game_id", "")) == str(game_id):
                d = _parse_iso((r.get("game_date") or "")[:10])
                if d is not None:
                    return d
    # snapshot
    cap = snap.get("captured_at") or snap.get("date") or snap.get("game_date")
    if isinstance(cap, str) and len(cap) >= 10:
        return _parse_iso(cap[:10])
    return None


def _parse_iso(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# ── projector (load once) ───────────────────────────────────────────────────────
def _load_v2(model_dir=SBS_V2_DIR) -> Optional[UnifiedPlayerLineProjector]:
    try:
        return UnifiedPlayerLineProjector.load(model_dir)
    except Exception as exc:  # untrained -> log BASE only
        print(f"  [warn] v2 model not loadable ({exc}); logging BASE only")
        return None


def _gamelog_store():
    """Lazily build a GamelogStore for L5 priors (reused across snapshots)."""
    try:
        from scripts.ingame.eval_second_by_second import GamelogStore
        return GamelogStore()
    except Exception as exc:
        print(f"  [warn] GamelogStore unavailable ({exc}); v2 prior cols -> 0")
        return None


# ── one shadow record per snapshot ───────────────────────────────────────────────
def _index_base(rows: List[Dict[str, Any]]) -> Dict[Tuple[Any, str], float]:
    out: Dict[Tuple[Any, str], float] = {}
    for r in rows:
        out[(r.get("player_id"), r.get("stat"))] = float(r.get("projected_final", 0.0) or 0.0)
    return out


def shadow_record_for_snapshot(
    path: str, *, projector: Optional[UnifiedPlayerLineProjector],
    store, game_date,
) -> Optional[Dict[str, Any]]:
    """Build one shadow-log record for a single snapshot file (or None)."""
    try:
        snap = pig.load_snapshot(path)
    except Exception as exc:
        print(f"  [warn] could not load {path}: {exc}")
        return None

    epoch_ms = _epoch_from_path(path)

    # BASE: the exact live projection (untouched), indexed by (pid, stat).
    base_idx = _index_base(pig.project_snapshot(snap))

    # V2 rows (clock + box + L5 prior) per player; bucket + gate decision attached.
    v2_rows = sbs_shadow.snapshot_to_v2_rows(snap, store=store, game_date=game_date)

    projections: List[Dict[str, Any]] = []
    n_v2_changed = 0
    for vr in v2_rows:
        pid = vr["player_id"]
        bucket = vr.get("_bucket")
        decision = vr.get("_gate_decision", "pregame")
        l5 = vr.get("_l5") or {}
        v2_out = projector.project(vr) if projector is not None else {}
        for stat in STATS:
            base_val = base_idx.get((pid, stat))
            if base_val is None:
                continue
            cur = float(vr.get(f"p_{stat}_so_far", 0.0) or 0.0)
            v2_val = float(v2_out.get(stat, base_val)) if v2_out else base_val
            # GATED served-equivalent under the validated game-time gate.
            if decision == "v2" and v2_out:
                gated = v2_val
            elif decision == "pregame" and stat in l5:
                gated = max(cur, float(l5[stat]))
            else:  # "snapshot" (Q4) or no v2 available
                gated = base_val
            if abs(v2_val - base_val) > 1e-9:
                n_v2_changed += 1
            projections.append({
                "player_id": pid,
                "name": vr.get("name"),
                "team": vr.get("team"),
                "stat": stat,
                "current": round(cur, 4),
                "base_proj": round(base_val, 6),
                "v2_proj": round(v2_val, 6),
                "gated_proj": round(gated, 6),
                "gate_decision": decision,
            })

    return {
        "game_id": snap.get("game_id"),
        "snapshot_file": os.path.basename(path),
        "snapshot_epoch_ms": epoch_ms,
        "captured_at": snap.get("captured_at"),
        "game_date": str(game_date) if game_date else None,
        "game_status": snap.get("game_status"),
        "period": snap.get("period"),
        "clock": snap.get("clock"),
        "grid_bucket": v2_rows[0].get("_bucket") if v2_rows else None,
        "gate_decision": v2_rows[0].get("_gate_decision") if v2_rows else "pregame",
        "home_team": snap.get("home_team"),
        "away_team": snap.get("away_team"),
        "home_score": snap.get("home_score"),
        "away_score": snap.get("away_score"),
        "n_rows": len(projections),
        "n_v2_changed": n_v2_changed,
        "logged_at": datetime.now(tz=timezone.utc).isoformat(),
        "projections": projections,
    }


# ── shadow-log append (writes ONLY under data/cache/ingame) ──────────────────────
def shadow_log_path(game_id: str, out_dir: str = SHADOW_DIR) -> str:
    return os.path.join(out_dir, f"sbs_shadow_{game_id}.jsonl")


def _already_logged(log_path: str) -> set:
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
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


# ── drivers ──────────────────────────────────────────────────────────────────────
def log_existing(
    game_id: str, *, out_dir: str = SHADOW_DIR, skip_logged: bool = True,
) -> int:
    """Log every existing snapshot for ``game_id`` not already in the shadow log."""
    log_path = shadow_log_path(game_id, out_dir)
    done = _already_logged(log_path) if skip_logged else set()
    paths = snapshot_paths_for_game(game_id)
    if not paths:
        print(f"  [info] no snapshots for game_id={game_id} in {LIVE_DIR}")
        return 0
    projector = _load_v2()
    store = _gamelog_store()
    # game_date from the first loadable snapshot (constant per game)
    game_date = None
    for p in paths:
        try:
            game_date = _game_date_for(game_id, pig.load_snapshot(p))
        except Exception:
            game_date = None
        if game_date is not None:
            break
    print(f"  [info] game_date={game_date}  v2_loaded={projector is not None}  "
          f"snapshots={len(paths)}")
    n = 0
    for p in paths:
        if os.path.basename(p) in done:
            continue
        rec = shadow_record_for_snapshot(
            p, projector=projector, store=store, game_date=game_date)
        if rec is None:
            continue
        append_record(log_path, rec)
        done.add(rec["snapshot_file"])
        n += 1
        if n % 200 == 0 or n == 1:
            print(f"  logged {rec['snapshot_file']} status={rec['game_status']} "
                  f"period={rec['period']} clock={rec['clock']} "
                  f"bucket={rec['grid_bucket']} gate={rec['gate_decision']} "
                  f"v2_changed={rec['n_v2_changed']}")
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
    game_id: str, *, out_dir: str = SHADOW_DIR, poll_interval: float = 20.0,
    max_iters: Optional[int] = None, stop_on_final: bool = True,
) -> int:
    """Poll ``data/live`` for new snapshots of ``game_id`` and shadow-log each."""
    log_path = shadow_log_path(game_id, out_dir)
    done = _already_logged(log_path)
    projector = _load_v2()
    store = _gamelog_store()
    total = 0
    it = 0
    print(f"  [watch] game_id={game_id} poll={poll_interval}s log={log_path}")
    game_date = None
    try:
        while True:
            it += 1
            paths = snapshot_paths_for_game(game_id)
            if game_date is None and paths:
                try:
                    game_date = _game_date_for(game_id, pig.load_snapshot(paths[0]))
                except Exception:
                    game_date = None
            new_paths = [p for p in paths if os.path.basename(p) not in done]
            for p in new_paths:
                rec = shadow_record_for_snapshot(
                    p, projector=projector, store=store, game_date=game_date)
                if rec is None:
                    done.add(os.path.basename(p))
                    continue
                append_record(log_path, rec)
                done.add(rec["snapshot_file"])
                total += 1
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] "
                      f"logged {rec['snapshot_file']} period={rec['period']} "
                      f"clock={rec['clock']} bucket={rec['grid_bucket']} "
                      f"gate={rec['gate_decision']}")
            if stop_on_final and paths and _snap_is_final(paths[-1]) and not new_paths:
                print("  [watch] latest snapshot FINAL and nothing new -> stopping.")
                break
            if max_iters is not None and it >= max_iters:
                print(f"  [watch] reached max_iters={max_iters} -> stopping.")
                break
            time.sleep(max(1.0, float(poll_interval)))
    except KeyboardInterrupt:
        print("\n  [watch] interrupted -> stopping.")
    print(f"  -> appended {total} shadow record(s) this session to {log_path}")
    return total


# ── CLI ────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-id", required=True, help="NBA game_id to shadow-log.")
    ap.add_argument("--watch", action="store_true",
                    help="Poll data/live for new snapshots until FINAL / max-iters.")
    ap.add_argument("--poll-interval", type=float, default=20.0,
                    help="Seconds between polls in --watch mode (default 20).")
    ap.add_argument("--max-iters", type=int, default=None,
                    help="Stop --watch after this many polls (default: until FINAL).")
    ap.add_argument("--out-dir", default=SHADOW_DIR,
                    help="Directory for the shadow log (default data/cache/ingame).")
    ap.add_argument("--no-skip-logged", action="store_true",
                    help="Re-log snapshots already present in the log (one-shot).")
    args = ap.parse_args()

    print(f"  sbs_shadow_logger: {sbs_shadow.SBS_FLAG}="
          f"{os.environ.get(sbs_shadow.SBS_FLAG)} "
          f"NBA_OFFLINE={os.environ.get('NBA_OFFLINE')}")
    print(f"  sbs_shadow.is_enabled() -> {sbs_shadow.is_enabled()}")

    if args.watch:
        watch(args.game_id, out_dir=args.out_dir,
              poll_interval=args.poll_interval, max_iters=args.max_iters)
    else:
        log_existing(args.game_id, out_dir=args.out_dir,
                     skip_logged=not args.no_skip_logged)
    return 0


if __name__ == "__main__":
    sys.exit(main())
