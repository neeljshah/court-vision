"""build_injury_features.py — Build per-(player, asof_date) NBA injury feature parquet.

Local-only ingest (no API calls). Reads all three injury snapshots:
  1. data/external/nba_official_injury.json      — list[dict], 126 entries, status/game_date
  2. data/cache/injury_status_2026-MM-DD.json    — dict{date, source, players[...]}, last_updated
  3. data/cache/nba_injuries_2026-MM-DD.parquet  — DataFrame, report_date + player_id

The dated JSON has `last_updated` (the timestamp the injury was actually
listed). The external JSON has `game_date` which is the same value. The
parquet only carries `report_date` (snapshot date = today). We therefore
use the *listed_date* (last_updated / game_date) as the canonical "when was
this injury announced" timestamp.

All three sources are 100% overlapping (126/126 player rows match) as of
2026-05-26. We merge them: parquet supplies player_id; dated JSON +
external JSON both supply the original listed_date.

Output: data/cache/injury_features.parquet
Schema (one row per (player_name_lower, asof_date) seen in snapshots —
plus we also write the raw listed records so the loader at predict-time
can compute team_inj_count_* against any asof_date):

Columns:
  player_name_lower : str
  player_name       : str (display)
  team_abbrev       : str
  status            : str  (normalized: Out / Day-To-Day / Questionable / GTD / Probable)
  reason            : str
  listed_date       : pd.Timestamp (UTC-naive)
  source            : str
  player_id         : Int64 (nullable)

The runtime loader (src.features.feature_engineering.load_injury_features)
will, per asof_dt, filter rows where listed_date < asof_dt and aggregate
status counts per team. This gives walk-forward safety: a 2026-04-15 game
prediction never sees a 2026-05-02 injury listing.

Usage:
    python scripts/build_injury_features.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_DATA_DIR  = os.path.join(PROJECT_DIR, "data")
_EXT_JSON  = os.path.join(_DATA_DIR, "external", "nba_official_injury.json")
_CACHE_DIR = os.path.join(_DATA_DIR, "cache")
_OUT_PATH  = os.path.join(_CACHE_DIR, "injury_features.parquet")


# ── Status normalization ─────────────────────────────────────────────────
_STATUS_MAP = {
    "out":              "Out",
    "day-to-day":       "Day-To-Day",
    "day to day":       "Day-To-Day",
    "dtd":              "Day-To-Day",
    "questionable":     "Questionable",
    "gtd":              "GTD",
    "game-time decision": "GTD",
    "game time decision": "GTD",
    "probable":         "Probable",
    "available":        "Probable",
}


def _normalize_status(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    k = str(raw).strip().lower()
    return _STATUS_MAP.get(k, str(raw).strip().title())


def _parse_dt(s: Optional[str]) -> Optional[pd.Timestamp]:
    if not s:
        return None
    try:
        ts = pd.to_datetime(s, utc=True, errors="coerce")
        if pd.isna(ts):
            return None
        # Strip tz → naive UTC for parquet-safe comparison.
        return ts.tz_convert(None) if ts.tzinfo else ts
    except Exception:
        return None


# ── Source loaders ──────────────────────────────────────────────────────
def _load_external_json() -> List[dict]:
    if not os.path.exists(_EXT_JSON):
        return []
    with open(_EXT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for r in data:
        out.append({
            "player_name":  (r.get("player_name") or "").strip(),
            "team_abbrev":  (r.get("team_abbrev") or "").strip().upper(),
            "status":       _normalize_status(r.get("status")),
            "reason":       r.get("reason") or "",
            "listed_date":  _parse_dt(r.get("game_date")),
            "source":       r.get("source") or "external_json",
            "player_id":    None,
        })
    return out


def _load_dated_json_files() -> List[dict]:
    rows: List[dict] = []
    for path in sorted(glob.glob(os.path.join(_CACHE_DIR, "injury_status_*.json"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        for p in d.get("players", []) or []:
            rows.append({
                "player_name":  (p.get("player_name") or "").strip(),
                "team_abbrev":  (p.get("team") or p.get("team_abbrev") or "").strip().upper(),
                "status":       _normalize_status(p.get("status")),
                "reason":       p.get("reason") or "",
                "listed_date":  _parse_dt(p.get("last_updated")),
                "source":       p.get("source") or "espn_public_api",
                "player_id":    _safe_int(p.get("player_id")),
            })
    return rows


def _safe_int(v) -> Optional[int]:
    try:
        if v is None:
            return None
        if isinstance(v, float) and (v != v):  # NaN
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def _load_dated_parquet_files() -> List[dict]:
    rows: List[dict] = []
    for path in sorted(glob.glob(os.path.join(_CACHE_DIR, "nba_injuries_*.parquet"))):
        try:
            df = pd.read_parquet(path)
        except Exception:
            continue
        for r in df.to_dict(orient="records"):
            # Parquet only has report_date (today's snapshot), no listed_date.
            # Use fetched_at as a *upper bound* for when the listing existed.
            listed = _parse_dt(r.get("fetched_at")) or _parse_dt(r.get("report_date"))
            rows.append({
                "player_name":  str(r.get("player_name") or "").strip(),
                "team_abbrev":  str(r.get("team") or "").strip().upper(),
                "status":       _normalize_status(r.get("status")),
                "reason":       str(r.get("reason") or ""),
                "listed_date":  listed,
                "source":       str(r.get("source") or "parquet"),
                "player_id":    _safe_int(r.get("player_id")) if pd.notna(r.get("player_id")) else None,
            })
    return rows


def _merge_records(*record_sets: List[dict]) -> pd.DataFrame:
    """Merge sources; dedupe by (player_name_lower, listed_date).
    Source priority (highest first): external_json (game_date) > espn_public_api
    (last_updated) > parquet (fetched_at upper bound). Earliest listed_date
    wins on tie."""
    all_rows: List[dict] = []
    for rs in record_sets:
        all_rows.extend(rs)
    if not all_rows:
        return pd.DataFrame(columns=[
            "player_name_lower", "player_name", "team_abbrev", "status",
            "reason", "listed_date", "source", "player_id"
        ])

    df = pd.DataFrame(all_rows)
    df["player_name_lower"] = df["player_name"].fillna("").str.lower().str.strip()
    df = df[df["player_name_lower"] != ""]
    df = df[df["listed_date"].notna()]

    # Source priority — lower number = better
    _SRC_RANK = {"espn_fallback": 0, "external_json": 0,
                 "espn_public_api": 1, "parquet": 2, "espn": 2}
    df["_rank"] = df["source"].map(_SRC_RANK).fillna(3).astype(int)

    df = df.sort_values(["player_name_lower", "listed_date", "_rank"])
    df = df.drop_duplicates(subset=["player_name_lower", "listed_date"], keep="first")
    df = df.drop(columns=["_rank"])
    return df.reset_index(drop=True)


def build() -> pd.DataFrame:
    ext  = _load_external_json()
    jdat = _load_dated_json_files()
    pdat = _load_dated_parquet_files()
    print(f"[build_injury_features] external_json={len(ext)} dated_json={len(jdat)} "
          f"dated_parquet={len(pdat)}")
    df = _merge_records(ext, jdat, pdat)
    df = df[[
        "player_name_lower", "player_name", "team_abbrev", "status",
        "reason", "listed_date", "source", "player_id"
    ]]
    df["player_id"] = df["player_id"].astype("Int64")
    return df


def main() -> int:
    df = build()
    os.makedirs(os.path.dirname(_OUT_PATH), exist_ok=True)
    df.to_parquet(_OUT_PATH, index=False)
    print(f"[build_injury_features] wrote {_OUT_PATH}  rows={len(df)}  "
          f"unique_players={df['player_name_lower'].nunique()}")
    print("[build_injury_features] status counts:")
    print(df["status"].value_counts().to_string())
    print("[build_injury_features] team_abbrev counts (top 8):")
    print(df["team_abbrev"].value_counts().head(8).to_string())

    # ── 5 sample (player, asof) demos ──
    from src.features.feature_engineering import compute_injury_features  # noqa: E402
    samples = [
        ("Jayson Tatum",        "BOS", "2026-05-02T23:00Z"),  # listed earlier same day → Out
        ("Jayson Tatum",        "BOS", "2026-04-15T00:00Z"),  # before listing → null
        ("Nic Claxton",         "BKN", "2026-04-12T00:00Z"),
        ("Michael Porter Jr.",  "BKN", "2026-04-10T00:00Z"),
        ("Some Unknown Player", "LAL", "2026-05-15T00:00Z"),
    ]
    print("\n[build_injury_features] sample lookups (status, hours_since_listed, team_out, team_q):")
    for name, team, asof in samples:
        feats = compute_injury_features(name, team, pd.to_datetime(asof, utc=True).tz_convert(None))
        print(f"  {name:>22s} {team} @ {asof}  ->  {feats}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
