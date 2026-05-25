"""scripts/probe_R4_D_form_only_heads.py -- R4-D form-only residual heads probe.

For each (pid, stat) at endQ3, if data/models/residual_heads_form_only/{stat}.lgb
exists, predicts a residual correction using ONLY rolling-form features (no
in-game state) and adds it to the BASELINE projection.

Features (~40):
  l5_<stat>_mean, l5_<stat>_std  (14)
  l20_<stat>_mean, l20_<stat>_std (14)
  l5_min_mean, l20_min_mean       (2)
  b2b, rest_days, is_home         (3)
  season_<stat>_mean              (7)

Clip: residual prediction is clipped to [-cur_stat, 2 * BASELINE_proj].

Usage:
    from scripts.probe_R4_D_form_only_heads import treatment
    from scripts.improve_loop.scaffold import run_endq3_probe
    run_endq3_probe("R4_D_form_only_heads", treatment)

CLI:
    python scripts/probe_R4_D_form_only_heads.py
    python scripts/probe_R4_D_form_only_heads.py --max-games 200
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from scripts.improve_loop.scaffold import run_endq3_probe, BASELINE  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
HEAD_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_form_only")

FEATURE_NAMES = (
    [f"l5_{s}_mean" for s in STATS]
    + [f"l5_{s}_std" for s in STATS]
    + [f"l20_{s}_mean" for s in STATS]
    + [f"l20_{s}_std" for s in STATS]
    + ["l5_min_mean", "l20_min_mean"]
    + ["b2b", "rest_days", "is_home"]
    + [f"season_{s}_mean" for s in STATS]
)

# Module-level caches (lazy-loaded on first treatment() call)
_head_cache: Optional[Dict[str, object]] = None
_gamelog_cache: Optional[Dict[int, List[Dict]]] = None
_rest_cache: Optional[Dict[Tuple[str, str], Dict]] = None
_game_date_cache: Optional[Dict[str, str]] = None


# ---------------------------------------------------------------------------
# Gamelog helpers (mirrored from train_residual_heads_form_only.py)
# ---------------------------------------------------------------------------

def _parse_gamelog_date(s) -> Optional[str]:
    if not s:
        return None
    try:
        return datetime.strptime(str(s), "%b %d, %Y").date().isoformat()
    except (ValueError, TypeError):
        return None


def _load_gamelogs() -> Dict[int, List[Dict]]:
    out: Dict[int, List[Dict]] = {}
    pattern = os.path.join(PROJECT_DIR, "data", "nba", "gamelog_*.json")
    for fp in glob.glob(pattern):
        base = os.path.basename(fp)
        parts = base.split("_")
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                games = json.load(fh) or []
        except Exception:
            continue
        for row in games:
            d = _parse_gamelog_date(row.get("GAME_DATE"))
            if d is None:
                continue
            try:
                m = float(row.get("MIN") or 0)
            except (TypeError, ValueError):
                m = 0.0
            if m < 1.0:
                continue
            entry: Dict = {"date": d, "min": m}
            for stat in STATS:
                try:
                    entry[stat] = float(row.get(stat.upper()) or 0)
                except (TypeError, ValueError):
                    entry[stat] = 0.0
            out.setdefault(pid, []).append(entry)
    for pid in out:
        out[pid].sort(key=lambda x: x["date"])
    return out


def _load_rest() -> Dict[Tuple[str, str], Dict]:
    import pandas as pd
    path = os.path.join(PROJECT_DIR, "data", "rest_travel.parquet")
    if not os.path.exists(path):
        return {}
    df = pd.read_parquet(path)
    out: Dict[Tuple[str, str], Dict] = {}
    for _, r in df.iterrows():
        gid = str(r["game_id"])
        team = str(r["team_abbreviation"])
        b2b = float(r.get("is_b2b") or 0)
        out[(gid, team)] = {"b2b": b2b, "rest_days": 1.0 if b2b else 2.0}
    return out


def _load_heads() -> Dict[str, object]:
    import lightgbm as lgb
    heads: Dict[str, object] = {}
    for stat in STATS:
        path = os.path.join(HEAD_DIR, f"{stat}.lgb")
        if os.path.exists(path):
            try:
                heads[stat] = lgb.Booster(model_file=path)
            except Exception as exc:
                print(f"  WARN: could not load {path}: {exc}")
    return heads


def _build_game_date_cache(gamelog: Dict[int, List[Dict]]) -> Dict[str, str]:
    """Build game_id -> date mapping from snap player data.

    This is called lazily during the first game in treatment(). We populate
    it on the fly per-game using the snap's game_id (stored in a side dict).
    """
    return {}


# ---------------------------------------------------------------------------
# Rolling form feature computation
# ---------------------------------------------------------------------------

def _rolling(
    pid: int,
    target_date: str,
    window: int,
    gamelog: Dict[int, List[Dict]],
) -> Optional[Dict[str, float]]:
    """Rolling mean+std for last `window` games strictly BEFORE target_date."""
    log = gamelog.get(pid, [])
    prior = [e for e in log if e["date"] < target_date]
    if not prior:
        return None
    entries = prior[-window:]
    result: Dict[str, float] = {}
    for stat in STATS:
        vals = [e[stat] for e in entries]
        n = len(vals)
        mean = sum(vals) / n
        if n > 1:
            var = sum((v - mean) ** 2 for v in vals) / (n - 1)
            std = var ** 0.5
        else:
            std = 0.0
        result[f"l{window}_{stat}_mean"] = mean
        result[f"l{window}_{stat}_std"] = std
    min_vals = [e["min"] for e in entries]
    result[f"l{window}_min_mean"] = sum(min_vals) / len(min_vals)
    return result


def _season_means(
    pid: int,
    target_date: str,
    gamelog: Dict[int, List[Dict]],
) -> Dict[str, float]:
    """Walk-forward expanding season mean (same calendar year, before target_date)."""
    log = gamelog.get(pid, [])
    year = target_date[:4]
    prior = [e for e in log if e["date"] < target_date and e["date"][:4] == year]
    if not prior:
        return {f"season_{s}_mean": 0.0 for s in STATS}
    return {f"season_{s}_mean": sum(e[s] for e in prior) / len(prior) for s in STATS}


def _resolve_game_date(
    game_id: str,
    snap: dict,
    gamelog: Dict[int, List[Dict]],
    date_cache: Dict[str, str],
) -> Optional[str]:
    """Resolve game_id -> ISO date by matching a snap player's MIN against gamelog."""
    if game_id in date_cache:
        return date_cache[game_id]

    # Sort players by minutes played (descending) and probe their gamelogs
    players = snap.get("players", [])
    sorted_players = sorted(
        players,
        key=lambda p: float(p.get("min", 0)),
        reverse=True,
    )
    for player in sorted_players[:5]:
        try:
            pid = int(player["player_id"])
        except (TypeError, ValueError):
            continue
        min_total = float(player.get("min", 0))
        log = gamelog.get(pid, [])
        for entry in log:
            if abs(entry["min"] - min_total) <= 1.0:
                date_cache[game_id] = entry["date"]
                return entry["date"]
    return None


# ---------------------------------------------------------------------------
# Feature row builder
# ---------------------------------------------------------------------------

def _build_feature_row(
    pid: int,
    game_id: str,
    game_date: str,
    player_team: str,
    home_team: str,
    gamelog: Dict[int, List[Dict]],
    rest_index: Dict[Tuple[str, str], Dict],
) -> Optional[List[float]]:
    """Build the ~40-feature form-only row. Returns None on cold-start."""
    import numpy as np

    l5 = _rolling(pid, game_date, 5, gamelog)
    if l5 is None:
        return None  # cold-start: drop

    l20 = _rolling(pid, game_date, 20, gamelog)
    season = _season_means(pid, game_date, gamelog)

    row: List[float] = []
    # l5 mean + std (14)
    for stat in STATS:
        row.append(l5.get(f"l5_{stat}_mean", 0.0))
    for stat in STATS:
        row.append(l5.get(f"l5_{stat}_std", 0.0))
    # l20 mean + std (14)
    for stat in STATS:
        row.append(l20.get(f"l20_{stat}_mean", 0.0) if l20 else 0.0)
    for stat in STATS:
        row.append(l20.get(f"l20_{stat}_std", 0.0) if l20 else 0.0)
    # l5_min_mean, l20_min_mean (2)
    row.append(l5.get("l5_min_mean", 0.0))
    row.append(l20.get("l20_min_mean", 0.0) if l20 else 0.0)
    # b2b, rest_days, is_home (3)
    rest = rest_index.get((game_id, player_team), {})
    row.append(rest.get("b2b", 0.0))
    row.append(rest.get("rest_days", 2.0))
    row.append(float(player_team == home_team))
    # season_<stat>_mean (7)
    for stat in STATS:
        row.append(season.get(f"season_{stat}_mean", 0.0))

    return row


# ---------------------------------------------------------------------------
# Treatment function
# ---------------------------------------------------------------------------

def treatment(snap: dict) -> Dict[Tuple[int, str], float]:
    """Apply form-only residual head corrections on top of BASELINE projections.

    For each (pid, stat): if a trained head exists, compute the ~40-feature
    form-only row, predict the residual, clip to [-cur_stat, 2*BASELINE_proj],
    and add to BASELINE. Falls back to BASELINE when head missing or cold-start.
    """
    global _head_cache, _gamelog_cache, _rest_cache, _game_date_cache

    # Lazy-load on first call
    if _head_cache is None:
        _head_cache = _load_heads()
    if _gamelog_cache is None:
        print("  [R4_D] loading gamelogs ...", flush=True)
        _gamelog_cache = _load_gamelogs()
    if _rest_cache is None:
        _rest_cache = _load_rest()
    if _game_date_cache is None:
        _game_date_cache = {}

    import numpy as np

    base = BASELINE(snap)
    out: Dict[Tuple[int, str], float] = dict(base)

    if not _head_cache:
        return out  # no heads trained yet

    game_id = str(snap.get("game_id", ""))
    home_team = str(snap.get("home_team", ""))

    # Resolve game date (needed for all gamelog lookups)
    game_date = _resolve_game_date(game_id, snap, _gamelog_cache, _game_date_cache)
    if game_date is None:
        return out  # can't resolve date -> fall back to BASELINE

    for player in snap.get("players", []):
        try:
            pid = int(player["player_id"])
        except (TypeError, ValueError):
            continue

        player_team = str(player.get("team", ""))

        feat_list = _build_feature_row(
            pid=pid,
            game_id=game_id,
            game_date=game_date,
            player_team=player_team,
            home_team=home_team,
            gamelog=_gamelog_cache,
            rest_index=_rest_cache,
        )
        if feat_list is None:
            continue  # cold-start: keep BASELINE

        feat = np.array([feat_list], dtype=np.float32)

        for stat in STATS:
            head = _head_cache.get(stat)
            if head is None:
                continue

            key = (pid, stat)
            projected = base.get(key)
            if projected is None:
                continue

            residual_pred = float(head.predict(feat)[0])
            cur_stat = float(player.get(stat, 0))

            # Clip: can't push below current in-game total; cap at 2x baseline
            adjusted = float(projected) + residual_pred
            adjusted = max(float(projected) - cur_stat, adjusted)  # lo: -cur_stat
            adjusted = min(float(projected) + max(0.0, 2.0 * float(projected)), adjusted)  # hi: 2x
            adjusted = max(0.0, adjusted)

            out[key] = adjusted

    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="R4-D form-only residual heads probe (endQ3)."
    )
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    n_heads = sum(
        1 for s in STATS
        if os.path.exists(os.path.join(HEAD_DIR, f"{s}.lgb"))
    )
    if n_heads == 0:
        print("  No form-only heads found. Run train_residual_heads_form_only.py first.")
        return 1

    print(f"  {n_heads} head(s) found in {HEAD_DIR}")
    print("  Running R4_D_form_only_heads probe ...")
    run_endq3_probe(
        "R4_D_form_only_heads",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
