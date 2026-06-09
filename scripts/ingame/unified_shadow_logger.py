"""unified_shadow_logger.py -- SHADOW-log PRODUCTION vs UNIFIED in-game projections.

Strictly read-only / append-only SHADOW logger for the UNIFIED in-game projector
(``src/ingame/unified_projector.project_unified``), which assembles the TWO
validated in-game heads for a single live snapshot:

  * SBS v2 player-line head  (validated walk-forward, half PTS MAE 4.11 -> 3.43)
  * possession rest-of-game sim  (final score beats snapshot_pace 7/7 game-times;
    win-prob beats the sigmoid on Brier/LogLoss from mid-game on)

For a game it reads the live box snapshots the poller already wrote to
``data/live/<game_id>_<epoch_ms>.json`` and, for each snapshot, records BOTH:

  * PRODUCTION -- ``scripts/predict_in_game.project_snapshot(snap)`` (exactly the
    value the live page / poller returns today; the production default), AND
  * UNIFIED    -- ``project_unified(snap, as_of=game_date, ...)`` with the SBS gate
    forced ON *in this process only*, yielding the assembled player-lines +
    possession-sim team-score + win-prob.

It logs THREE comparable components side-by-side per snapshot:

  * player lines : per-(player, stat) PRODUCTION ``projected_final`` vs UNIFIED
    SBS-v2 ``projected_final`` (+ the snapshot's current accumulation), AND
  * team score   : PRODUCTION's home/away final (if the production payload carries
    one; usually it does NOT -- the production in-game default is player-lines
    only) vs the UNIFIED possession-sim ``home_final_mean`` / ``away_final_mean``,
    AND
  * win prob     : PRODUCTION home win prob (if carried) vs UNIFIED
    ``home_win_prob``.

It appends one JSON object per snapshot to its OWN log at
``data/cache/ingame/unified_shadow_<game_id>.jsonl``.

HARD SAFETY (this logger lives entirely in the shadow lane):
  * NEVER writes to ``data/live/`` or any live artifact -- only READS snapshots and
    APPENDS to its own ``data/cache/ingame/`` log.
  * Does NOT change the live default. The ``CV_INGAME_SBS`` gate (default OFF) is
    forced ON only in THIS process so the unified head always computes; the live
    api/poller process is untouched, and the PRODUCTION column is the unmodified
    ``project_snapshot`` output. When the flag is OFF nothing serves the unified
    head anywhere (``project_unified`` is a byte-identical pass-through).
  * Imports + post-processes the existing projectors; it edits no production module.

Granularity honesty: this logs PER SNAPSHOT / PER EVENT (the unit the poller
captures), NOT per-second. The per-second display layer rides the same v2 head
but accuracy is graded per-event by ``grade_unified_shadow.py``.

Run -- one-shot over all existing snapshots for a game:
    set NBA_OFFLINE=1
    python scripts/ingame/unified_shadow_logger.py --game-id 0042500317

Run -- watch mode (poll data/live for new snapshots until FINAL / max-iters):
    python scripts/ingame/unified_shadow_logger.py --game-id 0042500317 --watch
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

# Force the SBS/unified gate ON for THIS process only, BEFORE importing the
# projector helpers, so the shadow path always computes the unified projection
# regardless of the ambient env. Does NOT affect the live api/poller process.
os.environ["CV_INGAME_SBS"] = "1"
os.environ.setdefault("NBA_OFFLINE", "1")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import predict_in_game as pig  # noqa: E402  (production projector; never modified)
from src.ingame import sbs_shadow  # noqa: E402
from src.ingame import unified_projector as up  # noqa: E402

STATS = sbs_shadow.PLAYER_STATS

LIVE_DIR = os.path.join(PROJECT_DIR, "data", "live")
SHADOW_DIR = os.path.join(PROJECT_DIR, "data", "cache", "ingame")
NBA_DIR = os.path.join(PROJECT_DIR, "data", "nba")

# Keys a PRODUCTION payload MIGHT carry for team score / win prob. The production
# in-game default returns a list of player-line rows and usually carries NO team
# score or win prob -- in that case those production columns are logged as None
# (the grader marks the production team/winprob components "n/a, production has no
# such head"). We never invent a production value.
_PROD_HOME_WP_KEYS = ("home_win_prob", "home_wp", "win_prob_home", "p_home_win")
_PROD_HOME_SCORE_KEYS = ("home_final", "home_final_mean", "proj_home_score",
                         "home_score_proj")
_PROD_AWAY_SCORE_KEYS = ("away_final", "away_final_mean", "proj_away_score",
                         "away_score_proj")


# -- snapshot discovery (read-only over data/live) ---------------------------- #
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


def _parse_iso(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _game_date_for(game_id: str, snap: Dict[str, Any]):
    """Leak-free game date (datetime.date) for the L5 cutoff.

    Priority: season_games row -> snapshot captured_at/date -> None. Used only as
    the STRICTLY-BEFORE cutoff for the L5 prior, so it can never pull future data.
    """
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
    cap = snap.get("captured_at") or snap.get("date") or snap.get("game_date")
    if isinstance(cap, str) and len(cap) >= 10:
        return _parse_iso(cap[:10])
    return None


# -- gamelog store for the L5 prior (load once, reused) ----------------------- #
def _gamelog_store():
    try:
        from scripts.ingame.eval_second_by_second import GamelogStore
        return GamelogStore()
    except Exception as exc:
        print(f"  [warn] GamelogStore unavailable ({exc}); v2 prior cols -> 0")
        return None


def _load_player_projector():
    """Pre-load the SBS v2 player head once (skip the per-snapshot disk load)."""
    try:
        from src.ingame.continuous_projection import (
            UnifiedPlayerLineProjector, SBS_V2_DIR,
        )
        return UnifiedPlayerLineProjector.load(SBS_V2_DIR)
    except Exception as exc:
        print(f"  [warn] v2 player head not loadable ({exc}); "
              f"unified player lines will fall back to current accumulation")
        return None


# -- production payload helpers ----------------------------------------------- #
def _index_production_lines(prod_out: Any) -> Dict[Tuple[Any, str], Dict[str, Any]]:
    """Index the PRODUCTION ``project_snapshot`` list by (player_id, stat).

    The production in-game default returns a list of per-(player, stat) row dicts
    each carrying ``projected_final``. Tolerant of missing keys.
    """
    out: Dict[Tuple[Any, str], Dict[str, Any]] = {}
    if not isinstance(prod_out, list):
        return out
    for r in prod_out:
        if not isinstance(r, dict):
            continue
        key = (r.get("player_id"), r.get("stat"))
        out[key] = r
    return out


def _first_present(d: Any, keys: Tuple[str, ...]) -> Optional[float]:
    """Return the first present numeric value among ``keys`` in dict ``d``, else None."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return float(d[k])
            except (TypeError, ValueError):
                continue
    return None


def _production_team_winprob(prod_out: Any) -> Tuple[Optional[float], Optional[float],
                                                     Optional[float]]:
    """Extract production (home_score, away_score, home_win_prob) IF carried.

    The default production in-game projector is player-lines only and carries no
    team score / win prob -> returns (None, None, None). If a future production
    payload is a dict (or carries a meta dict) with such fields, they are surfaced
    so the grader can compare honestly. We never fabricate a production value.
    """
    container = prod_out if isinstance(prod_out, dict) else None
    if container is None:
        return None, None, None
    # accept either top-level or a nested "team"/"meta" block
    for sub in (container, container.get("team"), container.get("meta")):
        h = _first_present(sub, _PROD_HOME_SCORE_KEYS)
        a = _first_present(sub, _PROD_AWAY_SCORE_KEYS)
        wp = _first_present(sub, _PROD_HOME_WP_KEYS)
        if h is not None or a is not None or wp is not None:
            return h, a, wp
    return None, None, None


# -- one shadow record per snapshot ------------------------------------------- #
def shadow_record_for_snapshot(
    path: str, *, store, game_date, player_projector,
    n_sims: int, seed: int, device: str,
) -> Optional[Dict[str, Any]]:
    """Build one shadow-log record for a single snapshot file (or None)."""
    try:
        snap = pig.load_snapshot(path)
    except Exception as exc:
        print(f"  [warn] could not load {path}: {exc}")
        return None

    epoch_ms = _epoch_from_path(path)

    # PRODUCTION: the exact live projection (untouched).
    prod_out = pig.project_snapshot(snap)
    prod_lines = _index_production_lines(prod_out)
    prod_home, prod_away, prod_wp = _production_team_winprob(prod_out)

    # UNIFIED: the assembled two-head projection (flag forced ON in this process).
    # project_unified returns a dict {player_lines, team, production_baseline, ...}.
    try:
        unified = up.project_unified(
            snap, as_of=game_date, device=device, store=store,
            n_sims=n_sims, seed=seed, player_projector=player_projector,
        )
    except Exception as exc:
        print(f"  [warn] unified projection failed for {os.path.basename(path)}: {exc}")
        return None
    if not isinstance(unified, dict) or not unified.get("enabled"):
        # Flag somehow off -> nothing to shadow (should not happen here).
        print(f"  [warn] unified disabled for {os.path.basename(path)}; skip")
        return None

    uni_player_lines = unified.get("player_lines") or []
    uni_team = unified.get("team") or {}

    grid_bucket = uni_player_lines[0].get("grid_bucket") if uni_player_lines else None
    gate_decision = (uni_player_lines[0].get("gate_decision")
                     if uni_player_lines else "pregame")

    # --- player-line component: PRODUCTION vs UNIFIED (SBS v2) per (pid, stat) ---
    projections: List[Dict[str, Any]] = []
    n_changed = 0
    for ul in uni_player_lines:
        pid = ul.get("player_id")
        stat = ul.get("stat")
        if stat not in STATS:
            continue
        prod_row = prod_lines.get((pid, stat))
        prod_val = None
        if prod_row is not None:
            try:
                prod_val = float(prod_row.get("projected_final"))
            except (TypeError, ValueError):
                prod_val = None
        try:
            uni_val = float(ul.get("projected_final"))
        except (TypeError, ValueError):
            continue
        cur = float(ul.get("current", 0.0) or 0.0)
        if prod_val is not None and abs(uni_val - prod_val) > 1e-9:
            n_changed += 1
        projections.append({
            "player_id": pid,
            "name": ul.get("name"),
            "team": ul.get("team"),
            "stat": stat,
            "current": round(cur, 4),
            "prod_proj": (round(prod_val, 6) if prod_val is not None else None),
            "unified_proj": round(uni_val, 6),
            "grid_bucket": ul.get("grid_bucket"),
            "gate_decision": ul.get("gate_decision"),
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
        "grid_bucket": grid_bucket,
        "gate_decision": gate_decision,
        "home_team": snap.get("home_team"),
        "away_team": snap.get("away_team"),
        "home_score": snap.get("home_score"),
        "away_score": snap.get("away_score"),
        # team-score + win-prob component (production columns are None when the
        # production default carries no team/winprob head).
        "team": {
            "prod_home_final": prod_home,
            "prod_away_final": prod_away,
            "prod_home_win_prob": prod_wp,
            "unified_home_final": uni_team.get("home_final_mean"),
            "unified_away_final": uni_team.get("away_final_mean"),
            "unified_home_win_prob": uni_team.get("home_win_prob"),
            "unified_margin_mean": uni_team.get("margin_mean"),
            "unified_total_mean": uni_team.get("total_mean"),
            "unified_poss_remaining_mean": uni_team.get("poss_remaining_mean"),
            "unified_n_sims": uni_team.get("n_sims"),
        },
        "n_player_rows": len(projections),
        "n_player_changed": n_changed,
        "device": unified.get("device"),
        "logged_at": datetime.now(tz=timezone.utc).isoformat(),
        "projections": projections,
    }


# -- shadow-log append (writes ONLY under data/cache/ingame) ------------------ #
def shadow_log_path(game_id: str, out_dir: str = SHADOW_DIR) -> str:
    return os.path.join(out_dir, f"unified_shadow_{game_id}.jsonl")


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


# -- drivers ------------------------------------------------------------------ #
def _resolve_game_date(game_id: str, paths: List[str]):
    for p in paths:
        try:
            return _game_date_for(game_id, pig.load_snapshot(p))
        except Exception:
            continue
    return None


def log_existing(
    game_id: str, *, out_dir: str = SHADOW_DIR, skip_logged: bool = True,
    n_sims: int = up.DEFAULT_N_SIMS, seed: int = up.DEFAULT_SEED,
    device: str = "auto",
) -> int:
    """Log every existing snapshot for ``game_id`` not already in the shadow log."""
    log_path = shadow_log_path(game_id, out_dir)
    done = _already_logged(log_path) if skip_logged else set()
    paths = snapshot_paths_for_game(game_id)
    if not paths:
        print(f"  [info] no snapshots for game_id={game_id} in {LIVE_DIR}")
        return 0
    store = _gamelog_store()
    projector = _load_player_projector()
    game_date = _resolve_game_date(game_id, paths)
    print(f"  [info] game_date={game_date}  player_head={projector is not None}  "
          f"snapshots={len(paths)}  n_sims={n_sims}  device={device}")
    n = 0
    for p in paths:
        if os.path.basename(p) in done:
            continue
        rec = shadow_record_for_snapshot(
            p, store=store, game_date=game_date, player_projector=projector,
            n_sims=n_sims, seed=seed, device=device)
        if rec is None:
            continue
        append_record(log_path, rec)
        done.add(rec["snapshot_file"])
        n += 1
        if n % 200 == 0 or n == 1:
            t = rec["team"]
            print(f"  logged {rec['snapshot_file']} status={rec['game_status']} "
                  f"period={rec['period']} clock={rec['clock']} "
                  f"bucket={rec['grid_bucket']} gate={rec['gate_decision']} "
                  f"changed={rec['n_player_changed']} "
                  f"uni_wp={t.get('unified_home_win_prob')}")
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
    n_sims: int = up.DEFAULT_N_SIMS, seed: int = up.DEFAULT_SEED,
    device: str = "auto",
) -> int:
    """Poll ``data/live`` for new snapshots of ``game_id`` and shadow-log each."""
    log_path = shadow_log_path(game_id, out_dir)
    done = _already_logged(log_path)
    store = _gamelog_store()
    projector = _load_player_projector()
    total = 0
    it = 0
    print(f"  [watch] game_id={game_id} poll={poll_interval}s log={log_path}")
    game_date = None
    try:
        while True:
            it += 1
            paths = snapshot_paths_for_game(game_id)
            if game_date is None and paths:
                game_date = _resolve_game_date(game_id, paths)
            new_paths = [p for p in paths if os.path.basename(p) not in done]
            for p in new_paths:
                rec = shadow_record_for_snapshot(
                    p, store=store, game_date=game_date, player_projector=projector,
                    n_sims=n_sims, seed=seed, device=device)
                if rec is None:
                    done.add(os.path.basename(p))
                    continue
                append_record(log_path, rec)
                done.add(rec["snapshot_file"])
                total += 1
                t = rec["team"]
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] "
                      f"logged {rec['snapshot_file']} period={rec['period']} "
                      f"clock={rec['clock']} bucket={rec['grid_bucket']} "
                      f"gate={rec['gate_decision']} "
                      f"uni_wp={t.get('unified_home_win_prob')}")
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


# -- CLI ---------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
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
    ap.add_argument("--n-sims", type=int, default=up.DEFAULT_N_SIMS,
                    help=f"Possession-sim rollouts (default {up.DEFAULT_N_SIMS}).")
    ap.add_argument("--seed", type=int, default=up.DEFAULT_SEED,
                    help=f"Possession-sim RNG seed (default {up.DEFAULT_SEED}).")
    ap.add_argument("--device", default="auto", choices=("auto", "cpu", "cuda"),
                    help="Device for the v2 head (default auto: cuda w/ CPU fallback).")
    ap.add_argument("--no-skip-logged", action="store_true",
                    help="Re-log snapshots already present in the log (one-shot).")
    args = ap.parse_args(argv)

    print(f"  unified_shadow_logger: {sbs_shadow.SBS_FLAG}="
          f"{os.environ.get(sbs_shadow.SBS_FLAG)} "
          f"NBA_OFFLINE={os.environ.get('NBA_OFFLINE')}")
    print(f"  unified_projector.is_enabled() -> {up.is_enabled()}")

    if args.watch:
        watch(args.game_id, out_dir=args.out_dir,
              poll_interval=args.poll_interval, max_iters=args.max_iters,
              n_sims=args.n_sims, seed=args.seed, device=args.device)
    else:
        log_existing(args.game_id, out_dir=args.out_dir,
                     skip_logged=not args.no_skip_logged,
                     n_sims=args.n_sims, seed=args.seed, device=args.device)
    return 0


if __name__ == "__main__":
    sys.exit(main())
