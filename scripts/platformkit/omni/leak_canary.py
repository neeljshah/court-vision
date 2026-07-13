"""scripts.platformkit.omni.leak_canary -- P1 acceptance canary for the leak guard.

Proves two things about scripts.platformkit.omni.feature_store:
  1. A HONEST future-knowable feature (knowable_at stamped after the game) is
     correctly excluded by get_asof() at a pregame asof_ts -- the as-of guard
     works structurally.
  2. A DISHONEST feature (same future-derived value, but knowable_at LIED to
     be pregame) is NOT caught by get_asof() -- as-of filtering trusts the
     stamp, it cannot detect a lie in the input. It IS caught by a separate
     suspicion audit: flag any feature whose pregame-visible value correlates
     too perfectly with the realized outcome across games.

# ponytail: the suspicion audit is a heuristic tripwire (perfect-correlation
# detector on a handful of games), not a proof of general leak-freedom -- a
# noisy leak or a leak on one game in fifty would slip past it. Upgrade path:
# a routine per-feature mutual-information screen against realized outcomes
# as a Stage-A gate in the funnel, run on every candidate feature at scale.

PURE pandas + stdlib + feature_store. ASCII only. No $/edge claims.
"""
from __future__ import annotations

import pathlib
from typing import Sequence

import pandas as pd

from scripts.platformkit.omni import feature_store as fs

HONEST_KEY = "canary_leak_honest"
DISHONEST_KEY = "canary_leak_dishonest"


def plant_canary(sport: str, games: Sequence[dict]) -> dict:
    """Plant honest + dishonest canary rows for each game.

    games: [{"entity": str, "game_ts": ISO str, "realized": float}, ...]
    Both rows carry the SAME future-derived value (the realized outcome).
    Honest row's knowable_at is 1 day AFTER game_ts (truthful -> excluded
    pregame). Dishonest row's knowable_at is 1 day BEFORE game_ts (a lie --
    the value is only knowable after the game, but the stamp claims pregame).
    """
    rows = []
    for g in games:
        ts = pd.Timestamp(g["game_ts"])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        rows.append(_row(g["entity"], HONEST_KEY, g["realized"], ts + pd.Timedelta(days=1)))
        rows.append(_row(g["entity"], DISHONEST_KEY, g["realized"], ts - pd.Timedelta(days=1)))
    fs.put_features(sport, pd.DataFrame(rows))
    return {"honest_key": HONEST_KEY, "dishonest_key": DISHONEST_KEY}


def _row(entity: str, key: str, value: float, knowable_at) -> dict:
    return {
        "entity": entity,
        "key": key,
        "value": value,
        "knowable_at": knowable_at,
        "computed_at": knowable_at,
        "pipeline_version": "leak-canary-v0",
    }


def fetch_pregame(sport: str, games: Sequence[dict], key: str) -> pd.DataFrame:
    """What get_asof() returns for *key* when queried exactly at each game's own game_ts."""
    rows = []
    for g in games:
        out = fs.get_asof(sport, [g["entity"]], [key], g["game_ts"])
        if not out.empty:
            rows.append({"entity": g["entity"], "value": float(out.iloc[0]["value"])})
    return pd.DataFrame(rows, columns=["entity", "value"])


def audit_canary(sport: str, games: Sequence[dict], key: str, corr_threshold: float = 0.999) -> dict:
    """Suspicion audit: flag *key* CAUGHT if its pregame-visible values correlate
    near-perfectly with realized outcomes across games (the tripwire the as-of
    filter itself cannot apply, since it only trusts the claimed timestamp).
    """
    visible = fetch_pregame(sport, games, key)
    if visible.empty:
        return {"feature_key": key, "verdict": "NOT_FOUND", "reason": "no pregame-visible rows for this key"}
    realized = {g["entity"]: g["realized"] for g in games}
    merged = visible.assign(realized=visible["entity"].map(realized))
    corr = merged["value"].corr(merged["realized"])
    if pd.notna(corr) and abs(corr) >= corr_threshold:
        return {
            "feature_key": key,
            "verdict": "CAUGHT",
            "reason": f"perfect-correlation tripwire: |r|={corr:.4f} >= {corr_threshold} "
            f"across {len(merged)} games despite claimed pregame knowable_at",
        }
    return {"feature_key": key, "verdict": "CLEAN", "reason": f"|r|={corr:.4f} below threshold {corr_threshold}"}


def realized_from_replay(sport: str, date: str) -> pd.DataFrame:
    """Best-effort: load (game_id, realized) from a P1-B replay parquet if present."""
    path = pathlib.Path("data/omni/replay") / sport / f"{date}.parquet"
    if not path.is_file():
        return pd.DataFrame(columns=["game_id", "realized"])
    df = pd.read_parquet(path)
    return df[["game_id", "realized"]].drop_duplicates("game_id").reset_index(drop=True)


__all__ = ["plant_canary", "fetch_pregame", "audit_canary", "realized_from_replay", "HONEST_KEY", "DISHONEST_KEY"]
