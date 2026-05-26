"""Probe R14_H2: defender_distance CV signal feature-engineering audit.

Context
-------
ISSUE-022 notes that CV-extracted ``defender_distance`` in
``data/tracking/<game_id>/shot_log.csv`` carries a sentinel ``200.0`` that
the production tracking writer never converts to NULL. Memory also flagged
that only ~19 games were Phase-G processed. The hypothesis was: if enough
games have non-sentinel defender_distance values AND the player resolver
correctly identifies the shooter, we can engineer
``avg_defender_distance_l5_shots`` per NBA player_id and wire it into the
pergame feature stack (or the endQ3 residual head) as a CV-derived prior on
shot-quality difficulty.

What this probe does
--------------------
1. Audits every non-backup ``data/tracking/*/shot_log.csv``: counts games,
   shots, NULLs, and the historical sentinel-200 fraction.
2. Force-coerces ``defender_distance`` to numeric (the column is written as
   string in some games), then computes the broader >=199.5 sentinel cluster
   we observed in addition to strict ==200.0.
3. Audits player linkage: ``player_id`` in the shot_log is per-game local
   track ID (1-10), not NBA player_id, so the join key has to come from
   ``player_name``. We measure how many shots have a *real* first-last name
   vs the ``TEAM#?`` / ``#N`` jersey placeholders that the resolver falls
   back to when re-ID fails.
4. Computes the usable cell count: shots with a non-sentinel defender_distance
   AND a real player_name AND a real game_id. Reports n_games, n_players,
   n_player_game_cells.
5. Applies the ship gate from the task spec: if usable n_games < 100 OR
   sentinel_fraction > 0.5, declare data-blocked and STOP without touching
   any production code. The probe does NOT silently patch the sentinel; that
   change belongs in ISSUE-022 fix-up to the tracking writer.

Output
------
``data/cache/probe_R14_H2_defender_distance_results.json`` with the audit
numbers, the decision, and the reasoning. No production training run is
launched because we stop at the audit gate.
"""
from __future__ import annotations

import glob
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_DIR / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
RESULT_PATH = CACHE_DIR / "probe_R14_H2_defender_distance_results.json"

# Audit gate constants (from task spec)
MIN_USABLE_GAMES = 100
MAX_SENTINEL_FRACTION = 0.50

# Sentinel definitions
STRICT_SENTINEL = 200.0
# Anything >=199.5 pixels also clusters with the sentinel (observed during audit)
SENTINEL_BAND_LO = 199.5

REAL_NAME_RE = re.compile(r"^[A-Z][\w'-]+ [A-Z]")


def _collect_shot_logs() -> List[Path]:
    base = PROJECT_DIR / "data" / "tracking"
    return sorted(p for p in base.glob("*/shot_log.csv") if ".bak" not in str(p))


def _load_concat(files: List[Path]) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for f in files:
        try:
            d = pd.read_csv(f)
        except Exception:
            continue
        if "defender_distance" not in d.columns:
            continue
        frames.append(d)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _audit(df: pd.DataFrame) -> Dict:
    dd = pd.to_numeric(df["defender_distance"], errors="coerce")
    name = df.get("player_name", pd.Series([None] * len(df))).astype(str)

    is_real_name = name.str.match(REAL_NAME_RE).fillna(False)
    is_strict_sentinel = dd.eq(STRICT_SENTINEL)
    is_band_sentinel = dd.ge(SENTINEL_BAND_LO) & dd.notna()
    is_usable_value = dd.notna() & ~is_band_sentinel
    usable_row = is_usable_value & is_real_name

    n_shots = int(len(df))
    n_games_total = int(df["game_id"].nunique()) if "game_id" in df.columns else 0
    n_games_usable = int(df.loc[usable_row, "game_id"].nunique()) if "game_id" in df.columns else 0
    n_players_usable = int(df.loc[usable_row, "player_name"].nunique()) if "player_name" in df.columns else 0

    player_game_cells = 0
    if "game_id" in df.columns and "player_name" in df.columns:
        player_game_cells = int(
            df.loc[usable_row].groupby(["game_id", "player_name"]).ngroups
        )

    sentinel_strict_frac = float(is_strict_sentinel.sum()) / max(n_shots, 1)
    sentinel_band_frac = float(is_band_sentinel.sum()) / max(n_shots, 1)
    null_frac = float(dd.isna().sum()) / max(n_shots, 1)

    return {
        "n_shots": n_shots,
        "n_games_total": n_games_total,
        "n_games_usable": n_games_usable,
        "n_players_usable": n_players_usable,
        "n_player_game_cells_usable": player_game_cells,
        "null_fraction": round(null_frac, 4),
        "sentinel_strict_200_fraction": round(sentinel_strict_frac, 4),
        "sentinel_band_ge199p5_fraction": round(sentinel_band_frac, 4),
        "n_usable_rows": int(usable_row.sum()),
        "n_real_name_rows": int(is_real_name.sum()),
    }


def _decision(audit: Dict) -> Dict:
    sentinel_frac = audit["sentinel_band_ge199p5_fraction"]
    n_games = audit["n_games_usable"]
    blocked_reasons: List[str] = []

    if n_games < MIN_USABLE_GAMES:
        blocked_reasons.append(
            f"n_games_usable={n_games} < {MIN_USABLE_GAMES} required"
        )
    if sentinel_frac > MAX_SENTINEL_FRACTION:
        blocked_reasons.append(
            f"sentinel_band_fraction={sentinel_frac} > {MAX_SENTINEL_FRACTION} threshold"
        )

    # Additional reality check: even with the formal gate, you need enough
    # player-game cells to support an L5 rolling average per player.
    if audit["n_player_game_cells_usable"] < 500:
        blocked_reasons.append(
            f"player_game_cells={audit['n_player_game_cells_usable']} too few to support L5 rolling avg"
        )

    if blocked_reasons:
        return {
            "ship_status": "DATA_BLOCKED_STOP",
            "proceeded_to_feature_engineering": False,
            "reasons": blocked_reasons,
            "by_stat_mae_delta": None,
        }

    # Not reachable in current data state; left for forward compatibility.
    return {
        "ship_status": "PROCEED_TO_FE",
        "proceeded_to_feature_engineering": True,
        "reasons": [],
        "by_stat_mae_delta": None,
    }


def main() -> None:
    files = _collect_shot_logs()
    n_files = len(files)
    if not files:
        result = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "n_shot_log_files": 0,
            "audit": {},
            "decision": {
                "ship_status": "DATA_BLOCKED_STOP",
                "proceeded_to_feature_engineering": False,
                "reasons": ["No shot_log.csv files found under data/tracking/"],
                "by_stat_mae_delta": None,
            },
            "notes": [
                "ISSUE-022 sentinel-200 fix should be applied in the tracking writer,",
                "not silently patched in the probe.",
            ],
        }
        RESULT_PATH.write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        return

    df = _load_concat(files)
    audit = _audit(df)
    decision = _decision(audit)

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "n_shot_log_files": n_files,
        # Convenience top-level keys (matches the task-spec contract)
        "n_games": audit["n_games_usable"],
        "sentinel_fraction": audit["sentinel_band_ge199p5_fraction"],
        "ship_status": decision["ship_status"],
        "by_stat_mae_delta": decision["by_stat_mae_delta"],
        # Detail
        "audit": audit,
        "decision": decision,
        "gate_thresholds": {
            "min_usable_games": MIN_USABLE_GAMES,
            "max_sentinel_fraction": MAX_SENTINEL_FRACTION,
        },
        "notes": [
            "shot_log player_id is per-game local track id (1-10), not NBA player_id;",
            "shooter identity must come from player_name. Most resolver outputs are",
            "'TEAM#?' or '#N' jersey placeholders, blocking cross-game aggregation.",
            "ISSUE-022 sentinel-200 fix belongs in the tracking writer; no",
            "production code paths were modified by this probe.",
        ],
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
