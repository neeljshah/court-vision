"""incremental_oof_refresh.py — keep ``data/cache/pregame_oof.parquet`` current.

After each finished NBA game the daemon appends new
``(player, stat, oof_pred, actual)`` rows to the parquet so it stays the live
data foundation for cross-stat heads, prediction caches, and synthetic CLV.

Detection rule
--------------
A game is "finished" when ``data/cache/quarter_box/<gid>_q4.json`` exists. We
scan the cache dir, drop any game_id already present in ``pregame_oof.parquet``,
and for the remaining ids build a per-(player,stat) row pair (oof_pred + actual)
using the live ``predict_pergame`` path and the summed quarter boxscores.

Fold rule
---------
All newly appended rows for this refresh batch go into a single new fold
``last_fold + 1`` so walk-forward integrity (each fold = strictly future
games relative to all prior folds) is preserved.

Atomic write
------------
We write the merged dataframe to ``pregame_oof.parquet.tmp`` and ``os.replace``
it onto ``pregame_oof.parquet``. The replace is atomic on POSIX and on
Windows-NTFS, so concurrent readers never see a half-written file.

Prediction cache refresh
------------------------
After a successful append we shell out to
``scripts/build_prediction_cache.py`` to rebuild today's
``data/cache/predictions_cache_<isodate>.parquet`` (R16_E3) — the serving
layer reads the freshest one off disk.

Usage
-----
    # one-shot
    python scripts/incremental_oof_refresh.py --once

    # daemon (5-min poll)
    python scripts/incremental_oof_refresh.py --check-interval-sec 300

Idempotent: running twice in a row with no new q4.json finds zero new games.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Bypass live ESPN scraping during the OOF refresh — we want raw model preds.
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

_OOF_PATH = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
_OOF_TMP_PATH = _OOF_PATH + ".tmp"
_QUARTER_BOX_DIR = os.path.join(PROJECT_DIR, "data", "cache", "quarter_box")
_NBA_DIR = os.path.join(PROJECT_DIR, "data", "nba")
_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
_PROBE_RESULT_PATH = os.path.join(
    _CACHE_DIR, "probe_R18_K5_oof_refresh_results.json"
)

_STATS: Tuple[str, ...] = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_FNAME_RE = re.compile(r"^(\d{10})_q([1-4])\.json$")

# ── light helpers ─────────────────────────────────────────────────────────────


def _load_game_index() -> Dict[str, Dict[str, str]]:
    """Walk every season_games_<season>.json and build game_id -> {season,
    game_date, home_team, away_team}. Cached at module level via lru_cache
    on caller; we keep this plain so callers can reload between polls."""
    idx: Dict[str, Dict[str, str]] = {}
    if not os.path.isdir(_NBA_DIR):
        return idx
    for fname in sorted(os.listdir(_NBA_DIR)):
        if not (fname.startswith("season_games_") and fname.endswith(".json")):
            continue
        path = os.path.join(_NBA_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue
        rows = payload.get("rows") if isinstance(payload, dict) else None
        if not rows:
            continue
        for r in rows:
            gid = str(r.get("game_id") or "")
            if not gid:
                continue
            idx[gid] = {
                "season": str(r.get("season") or ""),
                "game_date": str(r.get("game_date") or ""),
                "home_team": str(r.get("home_team") or ""),
                "away_team": str(r.get("away_team") or ""),
            }
    return idx


def _list_finished_game_ids(quarter_dir: str = _QUARTER_BOX_DIR) -> Set[str]:
    """Game ids whose <gid>_q4.json exists on disk."""
    if not os.path.isdir(quarter_dir):
        return set()
    finished: Set[str] = set()
    for fname in os.listdir(quarter_dir):
        m = _FNAME_RE.match(fname)
        if m is None or m.group(2) != "4":
            continue
        finished.add(m.group(1))
    return finished


def _existing_game_ids(oof_path: str = _OOF_PATH) -> Set[str]:
    if not os.path.exists(oof_path):
        return set()
    import pandas as pd
    df = pd.read_parquet(oof_path, columns=["game_id"])
    return set(df["game_id"].astype(str).unique())


def _last_fold(oof_path: str = _OOF_PATH) -> int:
    if not os.path.exists(oof_path):
        return 0
    import pandas as pd
    df = pd.read_parquet(oof_path, columns=["fold"])
    if df.empty:
        return 0
    return int(df["fold"].max())


# ── boxscore aggregation (sum the 4 quarters for full-game totals) ────────────


def _read_quarter(game_id: str, period: int,
                  quarter_dir: str = _QUARTER_BOX_DIR) -> Optional[dict]:
    path = os.path.join(quarter_dir, f"{game_id}_q{period}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _sum_player_totals(game_id: str,
                       quarter_dir: str = _QUARTER_BOX_DIR
                       ) -> Dict[int, Dict[str, float]]:
    """Sum every player's per-quarter line into a full-game total.

    Returns ``{player_id: {pts, reb, ast, fg3m, stl, blk, tov, min}}``.
    Players who DNP across all 4 quarters (or only sat the recorded ones)
    are skipped — they have zero total minutes.

    Note: q4.json uses the field ``to`` for turnovers; we surface it as
    ``tov`` in the totals to match prop_pergame's STATS naming.
    """
    totals: Dict[int, Dict[str, float]] = {}
    for q in (1, 2, 3, 4):
        payload = _read_quarter(game_id, q, quarter_dir)
        if payload is None:
            continue
        for prow in payload.get("players", []) or []:
            try:
                pid = int(prow.get("player_id") or prow.get("personId") or 0)
            except (TypeError, ValueError):
                pid = 0
            if pid <= 0:
                continue
            rec = totals.setdefault(pid, {
                "pts": 0.0, "reb": 0.0, "ast": 0.0, "fg3m": 0.0,
                "stl": 0.0, "blk": 0.0, "tov": 0.0, "min": 0.0,
            })
            # Minutes — handle "MM:SS" or numeric.
            m_raw = prow.get("min")
            if isinstance(m_raw, str) and ":" in m_raw:
                try:
                    mm, ss = m_raw.split(":", 1)
                    rec["min"] += float(mm) + float(ss) / 60.0
                except (TypeError, ValueError):
                    pass
            elif m_raw not in (None, ""):
                try:
                    rec["min"] += float(m_raw)
                except (TypeError, ValueError):
                    pass
            for k in ("pts", "reb", "ast", "fg3m", "stl", "blk"):
                v = prow.get(k)
                try:
                    rec[k] += float(v) if v not in (None, "") else 0.0
                except (TypeError, ValueError):
                    pass
            # Turnovers — accept either "to" (v2) or "tov" (v3) shape.
            tv = prow.get("to") if "to" in prow else prow.get("tov")
            try:
                rec["tov"] += float(tv) if tv not in (None, "") else 0.0
            except (TypeError, ValueError):
                pass
    return totals


# ── oof_pred path (one row per (player, stat)) ────────────────────────────────


def _predict_for_player(player_id: int, opp_team: str, season: str,
                        is_home: bool) -> Optional[Dict[str, float]]:
    """Live raw-blend pregame prediction for one player. Returns
    ``{stat: oof_pred}`` or ``None`` when the player has no usable gamelog."""
    from src.prediction.prop_pergame import (  # noqa: PLC0415
        build_prediction_row, predict_pergame,
    )
    row = build_prediction_row(player_id, opp_team, season, is_home=is_home)
    if row is None:
        return None
    out: Dict[str, float] = {}
    for stat in _STATS:
        val = predict_pergame(stat, row)
        if val is None:
            return None
        out[stat] = float(val)
    return out


def _build_rows_for_game(game_id: str, game_info: Dict[str, str],
                         fold: int,
                         quarter_dir: str = _QUARTER_BOX_DIR) -> List[dict]:
    """For each player who actually played in <game_id>, emit one row per
    stat: ``oof_pred`` (live model) + ``actual`` (summed quarter total)."""
    totals = _sum_player_totals(game_id, quarter_dir=quarter_dir)
    if not totals:
        return []

    home = game_info.get("home_team", "")
    away = game_info.get("away_team", "")
    season = game_info.get("season", "")
    game_date = game_info.get("game_date", "")

    # Identify each player's team from the q1 cache (or any quarter that has them).
    player_team: Dict[int, str] = {}
    for q in (1, 2, 3, 4):
        payload = _read_quarter(game_id, q, quarter_dir=quarter_dir)
        if payload is None:
            continue
        for prow in payload.get("players", []) or []:
            try:
                pid = int(prow.get("player_id") or 0)
            except (TypeError, ValueError):
                continue
            if pid <= 0 or pid in player_team:
                continue
            player_team[pid] = str(prow.get("team_abbreviation") or "")

    rows: List[dict] = []
    for pid, tot in totals.items():
        if tot.get("min", 0.0) <= 0:
            continue
        team = player_team.get(pid, "")
        if team == home:
            is_home, opp = True, away
        elif team == away:
            is_home, opp = False, home
        else:
            # Unknown team / pre-season / All-Star — best effort: assume home.
            is_home, opp = True, away or home

        try:
            oof = _predict_for_player(pid, opp, season, is_home)
        except Exception as exc:  # never let one bad player kill the batch
            print(f"  [warn] predict {pid} for {game_id} failed: {exc}",
                  flush=True)
            oof = None
        if oof is None:
            continue
        for stat in _STATS:
            rows.append({
                "game_id":   game_id,
                "player_id": int(pid),
                "stat":      stat,
                "oof_pred":  float(oof[stat]),
                "actual":    float(tot.get(stat, 0.0)),
                "game_date": game_date,
                "fold":      int(fold),
                "season":    season,
            })
    return rows


# ── append (atomic) ───────────────────────────────────────────────────────────


def _atomic_append_rows(new_rows: List[dict],
                        oof_path: str = _OOF_PATH) -> int:
    """Append rows to the parquet via tmp + replace. Returns rows written."""
    if not new_rows:
        return 0
    import pandas as pd

    cols = ["game_id", "player_id", "stat", "oof_pred", "actual",
            "game_date", "fold", "season"]
    new_df = pd.DataFrame(new_rows)[cols]

    if os.path.exists(oof_path):
        existing = pd.read_parquet(oof_path)
        merged = pd.concat([existing, new_df], ignore_index=True)
    else:
        merged = new_df

    os.makedirs(os.path.dirname(oof_path), exist_ok=True)
    tmp = oof_path + ".tmp"
    merged.to_parquet(tmp, index=False)
    os.replace(tmp, oof_path)
    return len(new_df)


# ── prediction cache refresh trigger ──────────────────────────────────────────


def _refresh_prediction_cache(python_exe: str = sys.executable) -> bool:
    """Rebuild ``data/cache/predictions_cache_<isodate>.parquet`` (R16_E3).
    Returns True on a clean exit. Best-effort: failures are logged not raised
    so the OOF append still ships."""
    script = os.path.join(PROJECT_DIR, "scripts", "build_prediction_cache.py")
    if not os.path.exists(script):
        print(f"  [skip] prediction cache rebuild — {script} not found",
              flush=True)
        return False
    try:
        proc = subprocess.run(
            [python_exe, script],
            cwd=PROJECT_DIR, capture_output=True, text=True, timeout=1800,
        )
        if proc.returncode == 0:
            print("  prediction cache refreshed OK", flush=True)
            return True
        print(f"  [warn] prediction cache rebuild rc={proc.returncode}; "
              f"stderr tail: {(proc.stderr or '')[-400:]}", flush=True)
        return False
    except Exception as exc:
        print(f"  [warn] prediction cache rebuild exception: {exc}",
              flush=True)
        return False


# ── one refresh pass ──────────────────────────────────────────────────────────


def refresh_once(*, oof_path: str = _OOF_PATH,
                 quarter_dir: str = _QUARTER_BOX_DIR,
                 trigger_prediction_cache: bool = True,
                 probe_path: str = _PROBE_RESULT_PATH) -> Dict[str, object]:
    """Detect finished games not yet in the parquet, predict, append, refresh
    the prediction cache. Returns a result dict (also written to probe JSON)."""
    t0 = time.time()
    print(f"[oof-refresh] starting at {datetime.now(timezone.utc).isoformat()}",
          flush=True)

    finished = _list_finished_game_ids(quarter_dir)
    existing = _existing_game_ids(oof_path)
    candidates = sorted(finished - existing)

    print(f"  finished_q4_games={len(finished)}  in_oof={len(existing)}  "
          f"new_candidates={len(candidates)}", flush=True)

    game_idx = _load_game_index()
    last_fold = _last_fold(oof_path)
    new_fold = last_fold + 1

    new_rows: List[dict] = []
    n_games_kept = 0
    for gid in candidates:
        info = game_idx.get(gid)
        if info is None:
            print(f"  [skip] {gid}: no schedule entry", flush=True)
            continue
        rows = _build_rows_for_game(gid, info, new_fold,
                                    quarter_dir=quarter_dir)
        if not rows:
            print(f"  [skip] {gid}: no usable players", flush=True)
            continue
        new_rows.extend(rows)
        n_games_kept += 1
        print(f"  {gid}: +{len(rows)} rows  date={info.get('game_date')}",
              flush=True)

    n_rows_added = _atomic_append_rows(new_rows, oof_path)

    pred_cache_refreshed = False
    if n_rows_added > 0 and trigger_prediction_cache:
        pred_cache_refreshed = _refresh_prediction_cache()

    result: Dict[str, object] = {
        "n_new_games_detected": int(n_games_kept),
        "n_rows_added": int(n_rows_added),
        "last_fold": int(new_fold if n_rows_added > 0 else last_fold),
        "prediction_cache_refreshed": bool(pred_cache_refreshed),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "wall_sec": round(time.time() - t0, 1),
    }

    try:
        os.makedirs(os.path.dirname(probe_path), exist_ok=True)
        with open(probe_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    except Exception as exc:
        print(f"  [warn] failed to write {probe_path}: {exc}", flush=True)

    print(f"[oof-refresh] done: {result}", flush=True)
    return result


# ── daemon loop ───────────────────────────────────────────────────────────────


def loop(check_interval_sec: int) -> None:
    print(f"[oof-refresh] daemon poll every {check_interval_sec}s "
          f"(pid={os.getpid()})", flush=True)
    while True:
        try:
            refresh_once()
        except Exception as exc:
            print(f"[oof-refresh] iteration crashed: {exc}", flush=True)
        time.sleep(check_interval_sec)


# ── entry point ───────────────────────────────────────────────────────────────


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Append newly-finished NBA games to pregame_oof.parquet "
                    "and refresh the R16_E3 prediction cache."
    )
    ap.add_argument(
        "--check-interval-sec", type=int, default=300,
        help="Poll interval in seconds when run as a daemon (default 300).",
    )
    ap.add_argument(
        "--once", action="store_true",
        help="Run a single refresh pass and exit (no daemon loop).",
    )
    ap.add_argument(
        "--no-prediction-cache", action="store_true",
        help="Skip the R16_E3 prediction cache rebuild after appending.",
    )
    return ap.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    if args.once:
        refresh_once(trigger_prediction_cache=not args.no_prediction_cache)
        return 0
    loop(args.check_interval_sec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
