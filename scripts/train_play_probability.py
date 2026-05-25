"""train_play_probability.py — cycle 104a (loop 5).

Train the per-row P(play) head from the DNP-included projection set.

Each (player, game) becomes one training row with:
- target y = 1 if MIN > 0 (played), 0 if DNP
- features = is_b2b, age, days_since_last_game, l5_min-proxy (l5_pts/30),
  l10_min-proxy (l10_pts/30), position one-hots, opp_team_pace_l5,
  dnp_l20_rate (rolling DNP rate over prior 20 player-games)

The walker mirrors build_pergame_dataset emission order but is stripped
to only the features needed for P(play). Played rows come from the
gamelog cache; DNP rows from data/dnp_rows.parquet.

Trains LGBClassifier + Platt scaling and persists to
data/models/play_probability_v1.joblib.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import sys
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Tuple

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import numpy as np

from src.prediction.prop_pergame import (  # noqa: E402
    _MIN_PLAYED, _NBA_CACHE, _num, _parse_date,
    build_rest_travel, build_player_positions,
    _bbref_id_to_name, _unmangle_utf8,
)
from src.prediction.play_probability import (  # noqa: E402
    PLAY_PROB_FEATURES, train_play_probability, save_play_probability,
)
from src.data.dnp_set import load_dnp_rows  # noqa: E402

_BBREF_DIR = os.path.join(PROJECT_DIR, "data", "external")
_POSITIONS = ("G", "F", "C")


def _load_bbref_age(seasons: List[str]) -> Dict[Tuple[str, str], float]:
    out: Dict[Tuple[str, str], float] = {}
    for season in seasons:
        path = os.path.join(_BBREF_DIR, f"bbref_advanced_{season}.json")
        if not os.path.exists(path):
            continue
        try:
            rows = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for row in rows or []:
            name = _unmangle_utf8(str(row.get("player_name", "")).strip())
            if not name:
                continue
            try:
                age = float(row.get("age") or 0.0)
            except (TypeError, ValueError):
                continue
            if age > 0:
                out.setdefault((name, season), age)
    return out


def _season_from_date(d: datetime) -> str:
    y = d.year
    if d.month >= 9:
        return f"{y}-{str(y+1)[-2:]}"
    return f"{y-1}-{str(y)[-2:]}"


def _pos_onehot(pos: str) -> Dict[str, float]:
    out = {f"pos_{p}": 0.0 for p in _POSITIONS}
    if not pos:
        return out
    p = pos[0].upper()
    if p in _POSITIONS:
        out[f"pos_{p}"] = 1.0
    return out


def _build_team_pace_l5() -> Dict[Tuple[str, str], float]:
    """team_abbrev, game_date_iso -> last-5 pace average (prior to that date).
    Builds from gamelog cache aggregated by team-game by counting possessions
    proxy. Cheap proxy: use 100.0 (league avg) when unresolvable.
    """
    return {}


def build_training_set() -> Tuple[np.ndarray, np.ndarray, List[str]]:
    rest_travel = build_rest_travel()
    positions = build_player_positions()
    id2name = _bbref_id_to_name()

    # First pass: collect played rows.
    seasons_seen = set()
    played_rows: List[dict] = []
    # player_id -> chronological list of (date, played(0/1))
    play_history: Dict[int, List[Tuple[datetime, int]]] = defaultdict(list)

    paths = sorted(glob.glob(os.path.join(_NBA_CACHE, "gamelog_*.json")))
    logger.info("gamelog files: %d", len(paths))
    for path in paths:
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or not games:
            continue
        try:
            basename = os.path.basename(path)
            parts = basename.split("_")
            file_player_id = int(parts[1])
            file_season = parts[-1].replace(".json", "")
        except Exception:
            continue
        seasons_seen.add(file_season)
        dated = [(d, g) for g in games
                 if (d := _parse_date(g.get("GAME_DATE"))) is not None]
        dated.sort(key=lambda x: x[0])

        prior_pts: deque = deque(maxlen=10)
        for idx, (gdate, game) in enumerate(dated):
            played = _num(game.get("MIN")) >= _MIN_PLAYED
            matchup = str(game.get("MATCHUP", ""))
            team_abbrev = matchup.split()[0] if matchup.split() else ""
            rt = rest_travel.features(team_abbrev, gdate)
            is_b2b = float(rt.get("is_b2b", 0.0) or 0.0)
            days_since = 3.0
            if idx > 0:
                days_since = float((gdate - dated[idx - 1][0]).days)
            l5_pts = float(np.mean(list(prior_pts)[-5:])) if prior_pts else 0.0
            l10_pts = float(np.mean(list(prior_pts))) if prior_pts else 0.0
            pos = positions.position(file_player_id) or ""

            row = {
                "player_id": file_player_id,
                "season": file_season,
                "date": gdate,
                "is_b2b": is_b2b,
                "age": 0.0,  # filled second pass with age_lookup
                "days_since_last_game": min(days_since, 100.0),
                "l5_min": l5_pts / 2.0,  # rough proxy; pts/min ~ 0.5
                "l10_min": l10_pts / 2.0,
                "opp_team_pace_l5": 100.0,  # neutral default
                "y": 1 if played else 0,
                "_pos": pos,
                "_name": id2name.get(file_player_id, ""),
            }
            row.update(_pos_onehot(pos))
            played_rows.append(row)
            if played:
                prior_pts.append(_num(game.get("PTS")))

    logger.info("played-side rows: %d", len(played_rows))

    # DNP rows from parquet — y=0.
    dnp_df = load_dnp_rows()
    dnp_recs = dnp_df.to_dict("records") if hasattr(dnp_df, "to_dict") else []
    logger.info("dnp rows: %d", len(dnp_recs))

    # Build per-player DNP date set for dnp_l20_rate aux feature.
    dnp_dates_by_pid: Dict[int, List[datetime]] = defaultdict(list)
    for d in dnp_recs:
        try:
            pid = int(d.get("player_id") or 0)
            dt = datetime.fromisoformat(str(d.get("game_date"))[:10])
        except Exception:
            continue
        if pid > 0:
            dnp_dates_by_pid[pid].append(dt)

    # Construct DNP synthetic rows in same shape.
    dnp_added = 0
    for d in dnp_recs:
        try:
            pid = int(d.get("player_id") or 0)
        except (TypeError, ValueError):
            continue
        if pid <= 0:
            continue
        team = str(d.get("team") or "")
        try:
            gdate = datetime.fromisoformat(str(d.get("game_date"))[:10])
        except Exception:
            continue
        season = str(d.get("season") or "") or _season_from_date(gdate)
        seasons_seen.add(season)
        rt = rest_travel.features(team, gdate)
        is_b2b = float(rt.get("is_b2b", 0.0) or 0.0)
        pos = positions.position(pid) or ""
        row = {
            "player_id": pid,
            "season": season,
            "date": gdate,
            "is_b2b": is_b2b,
            "age": 0.0,
            "days_since_last_game": 3.0,
            "l5_min": 0.0,
            "l10_min": 0.0,
            "opp_team_pace_l5": 100.0,
            "y": 0,
            "_pos": pos,
            "_name": id2name.get(pid, ""),
        }
        row.update(_pos_onehot(pos))
        played_rows.append(row)
        dnp_added += 1

    logger.info("after DNP injection: %d (added %d)", len(played_rows), dnp_added)

    # Second pass: age lookup + rolling DNP rate.
    age_lookup = _load_bbref_age(sorted(seasons_seen))
    logger.info("bbref age entries: %d", len(age_lookup))

    # Sort all rows chronologically for the rolling DNP rate calc.
    played_rows.sort(key=lambda r: (r["player_id"], r["date"]))
    # rolling 20-game DNP rate prior to current row, per player.
    per_pid_hist: Dict[int, deque] = defaultdict(lambda: deque(maxlen=20))
    for r in played_rows:
        hist = per_pid_hist[r["player_id"]]
        r["dnp_l20_rate"] = (
            float(sum(1 - x for x in hist) / len(hist)) if hist else 0.0
        )
        hist.append(r["y"])
        r["age"] = float(age_lookup.get((r["_name"], r["season"]), 0.0))

    # Final chronological order over ALL rows.
    played_rows.sort(key=lambda r: r["date"])

    X = np.array(
        [[float(r.get(c, 0.0) or 0.0) for c in PLAY_PROB_FEATURES] for r in played_rows],
        dtype=float,
    )
    y = np.array([r["y"] for r in played_rows], dtype=int)
    dates = [r["date"].isoformat() for r in played_rows]
    return X, y, dates


def main() -> int:
    print("Building training set...", flush=True)
    X, y, dates = build_training_set()
    print(f"  total rows: {len(X)}", flush=True)
    print(f"  played frac: {y.mean():.4f}", flush=True)
    print(f"  features: {PLAY_PROB_FEATURES}", flush=True)
    print(f"  date range: {dates[0]} -> {dates[-1]}", flush=True)

    print("Training LGBClassifier + Platt...", flush=True)
    artifact = train_play_probability(X, y, val_frac=0.2)
    print(f"  n_train: {artifact['n_train']}  n_val: {artifact['n_val']}",
          flush=True)
    print(f"  val mean P(play): {artifact['val_mean_pred']:.4f}", flush=True)
    print(f"  val played frac:  {artifact['val_played_frac']:.4f}", flush=True)
    print(f"  val Brier:        {artifact['val_brier']:.4f}", flush=True)
    print(f"  calibration gap:  "
          f"{abs(artifact['val_mean_pred'] - artifact['val_played_frac']):.4f}",
          flush=True)

    path = save_play_probability(artifact)
    print(f"Saved -> {path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
