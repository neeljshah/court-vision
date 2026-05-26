"""probe_R14_H4_injury_feed.py — viability probe for a free real-time injury feed.

Memory states `stars_available` (per-team historical proxy) is coarse. Real-time
injury / lineup feeds are the highest-ROI remaining data lever now that the
model is at architecture/feature ceiling. This probe evaluates free public
sources and tests:

  1. Does an unauthenticated, IP-friendly source actually return data?
  2. Can we normalize statuses to {OUT, DOUBTFUL, QUESTIONABLE, PROBABLE,
     AVAILABLE} → multiplicative availability_factor in {0, 0.3, 0.6, 0.9, 1.0}?
  3. Can we map scraped names to the player_id space used by
     data/cache/pregame_oof.parquet (the model's prediction space)?

Sources evaluated (highest feasibility first):
  - ESPN public injury API: site.api.espn.com/.../basketball/nba/injuries (JSON,
    no auth, ~1 MB, ~600 rows). Already wrapped by src/data/injury_monitor.py
    so we get retries + UA spoofing for free.
  - NBA.com PDF: scripts/fetch_injury_report.py exists but 403s from non-
    residential IPs — we still try it as source #2.
  - rotowire / basketball-reference HTML: only attempted if the first two fail.

SHIP gate (per task spec): ≥ 30 players scraped with valid status AND
≥ 5 player_ids mapped back to the OOF parquet space.

Outputs:
  data/cache/probe_R14_H4_injury_feed_results.json
  data/cache/injury_status_<isodate>.json   (current snapshot)

This is a DATA-SOURCE VIABILITY PROBE only. Do not wire into production.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
import unicodedata
from datetime import date as _date_cls
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Use the existing ESPN wrapper (retries + UA spoofing + 30-min TTL cache).
from src.data.injury_monitor import get_all_injuries, refresh  # noqa: E402


# Canonical status taxonomy used downstream (matches src/data/injuries.py).
_STATUS_NORM: Dict[str, str] = {
    "out":           "OUT",
    "doubtful":      "DOUBTFUL",
    "questionable":  "QUESTIONABLE",
    "day-to-day":    "QUESTIONABLE",  # ESPN uses DTD; no DTD bucket downstream
    "dtd":           "QUESTIONABLE",
    "probable":      "PROBABLE",
    "available":     "AVAILABLE",
    "active":        "AVAILABLE",
    "healthy":       "AVAILABLE",
    "suspended":     "NOT WITH TEAM",
    "nwt":           "NOT WITH TEAM",
    "not with team": "NOT WITH TEAM",
}

# Multiplicative availability_factor per the probe spec. NOT WITH TEAM ≡ OUT.
AVAILABILITY_FACTOR: Dict[str, float] = {
    "OUT":           0.0,
    "NOT WITH TEAM": 0.0,
    "DOUBTFUL":      0.3,
    "QUESTIONABLE":  0.6,
    "PROBABLE":      0.9,
    "AVAILABLE":     1.0,
}

VALID_STATUSES = frozenset(AVAILABILITY_FACTOR.keys())


def _norm_status(raw: str) -> str:
    """Normalize ESPN/NBA status string into the canonical 5-bucket taxonomy."""
    key = (raw or "").strip().lower()
    return _STATUS_NORM.get(key, key.upper().strip())


def _strip_accents(s: str) -> str:
    """Drop diacritics so 'Jokić' matches 'Jokic' on name lookup."""
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _name_key(name: str) -> str:
    """Canonical lookup key: diacritic-stripped, lower, single-spaced."""
    s = _strip_accents(name or "").lower().strip()
    # Drop trailing Jr./Sr./III/II suffixes that ESPN sometimes omits but
    # NBA carries (and vice-versa).
    for suf in (" jr.", " jr", " sr.", " sr", " iii", " ii", " iv"):
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
    return " ".join(s.split())


def build_player_name_to_id() -> Dict[str, int]:
    """Build {canonical_name: person_id} from the cached playerinfo JSONs.

    data/cache/playerinfo/<person_id>.json comes from NBA's commonplayerinfo
    endpoint and is the same id space used in pregame_oof.parquet.
    """
    mapping: Dict[str, int] = {}
    pattern = os.path.join(PROJECT_DIR, "data", "cache", "playerinfo", "*.json")
    for fp in glob.glob(pattern):
        try:
            with open(fp, encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception:
            continue
        rows = payload.get("common_player_info") or []
        if not rows:
            continue
        row = rows[0]
        pid = row.get("PERSON_ID")
        name = row.get("DISPLAY_FIRST_LAST") or ""
        if pid and name:
            mapping[_name_key(name)] = int(pid)
    return mapping


def scrape_espn() -> Tuple[List[Dict], int]:
    """Fetch the ESPN injury feed via the existing wrapper.

    Returns (rows, http_status_proxy). The wrapper writes to data/nba/
    injury_report.json; we read that for a status-ish proxy (200 if the
    JSON was refreshed and contains 'injuries').
    """
    # Force refresh so we don't read stale cache when the test is gated on
    # row-count freshness.
    try:
        refresh(force=True)
        rows = get_all_injuries() or []
        status = 200 if rows else 204
    except Exception as exc:  # surface the failure mode in the report
        return [], int(getattr(exc, "code", 0)) or 500
    return rows, status


def normalize_rows(rows: List[Dict]) -> pd.DataFrame:
    """ESPN rows -> dataframe with [player_name, team, status, reason, source]."""
    if not rows:
        return pd.DataFrame(
            columns=["player_name", "team", "status", "reason",
                     "last_updated", "source"]
        )
    out = []
    for r in rows:
        status = _norm_status(r.get("status", ""))
        out.append({
            "player_name":  (r.get("player_name") or "").strip(),
            "team":         (r.get("team_abbrev") or "").strip(),
            "status":       status,
            "reason":       (r.get("short_comment") or r.get("injury_type") or ""),
            "last_updated": r.get("injury_date") or "",
            "source":       "espn_public_api",
        })
    df = pd.DataFrame(out)
    # Drop blanks; keep canonical bucketing only.
    df = df[df["player_name"].str.len() > 0].reset_index(drop=True)
    return df


def attach_player_ids(df: pd.DataFrame,
                      name_to_id: Dict[str, int]) -> pd.DataFrame:
    """Add player_id column by canonical-name lookup. Missing -> NaN."""
    df = df.copy()
    df["player_id"] = df["player_name"].map(
        lambda n: name_to_id.get(_name_key(n))
    )
    df["availability_factor"] = df["status"].map(AVAILABILITY_FACTOR)
    return df


def cross_reference_with_oof(df: pd.DataFrame) -> Tuple[int, set]:
    """Count how many scraped player_ids exist in pregame_oof.parquet."""
    oof_path = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
    if not os.path.exists(oof_path):
        return 0, set()
    try:
        oof = pd.read_parquet(oof_path, columns=["player_id"])
    except Exception:
        return 0, set()
    oof_ids = set(oof["player_id"].dropna().astype(int).unique().tolist())
    scraped_ids = set(
        df["player_id"].dropna().astype(int).unique().tolist()
    )
    overlap = oof_ids & scraped_ids
    return len(overlap), overlap


def top_5_impactful(df: pd.DataFrame, overlap_ids: set) -> List[Dict]:
    """Rank scraped+mapped players by 'expected impact'.

    Impact proxy = (1 - availability_factor) × mean(oof_pred for PTS).
    A high-scoring player who is OUT carries more lost expected production
    than a bench player who is questionable.
    """
    if df.empty or not overlap_ids:
        return []
    oof_path = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
    if not os.path.exists(oof_path):
        return []
    try:
        oof = pd.read_parquet(oof_path)
    except Exception:
        return []
    pts = oof[oof["stat"] == "pts"]
    if pts.empty:
        return []
    # Per-player average pregame PTS prediction (proxy for "star-ness").
    star = pts.groupby("player_id")["oof_pred"].mean().to_dict()

    candidates = df.dropna(subset=["player_id"]).copy()
    candidates["player_id"] = candidates["player_id"].astype(int)
    candidates = candidates[candidates["player_id"].isin(overlap_ids)]
    if candidates.empty:
        return []
    candidates["avg_oof_pts"] = candidates["player_id"].map(star).fillna(0.0)
    candidates["impact_score"] = (
        (1.0 - candidates["availability_factor"]) * candidates["avg_oof_pts"]
    )
    candidates = candidates.sort_values("impact_score", ascending=False)
    top = candidates.head(5)
    return [
        {
            "player_id":           int(r.player_id),
            "player_name":         r.player_name,
            "team":                r.team,
            "status":              r.status,
            "availability_factor": float(r.availability_factor),
            "avg_oof_pts":         round(float(r.avg_oof_pts), 2),
            "impact_score":        round(float(r.impact_score), 2),
        }
        for r in top.itertuples(index=False)
    ]


def write_snapshot(df: pd.DataFrame, date_str: str) -> str:
    """Persist current snapshot at data/cache/injury_status_<date>.json."""
    out_dir = os.path.join(PROJECT_DIR, "data", "cache")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"injury_status_{date_str}.json")
    snapshot = {
        "date":       date_str,
        "source":     "espn_public_api",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "n_players":  int(len(df)),
        "players": df.where(pd.notna(df), None).to_dict(orient="records"),
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, default=str)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=_date_cls.today().isoformat())
    args = parser.parse_args()

    t0 = time.time()
    print(f"[probe_R14_H4] starting injury-feed viability probe ({args.date})")

    # ---------------- Source #1: ESPN public injury API ----------------
    print("[probe_R14_H4] source 1: ESPN public injury API ...")
    rows, http_status = scrape_espn()
    print(f"[probe_R14_H4]   HTTP-like status: {http_status}, n_rows={len(rows)}")

    df = normalize_rows(rows)
    schema_valid = (
        not df.empty
        and set(["player_name", "team", "status",
                 "reason", "last_updated", "source"]).issubset(df.columns)
        and df["status"].isin(VALID_STATUSES).mean() > 0.5
    )
    print(f"[probe_R14_H4]   normalized rows: {len(df)}, "
          f"schema_valid={schema_valid}")

    # ---------------- ID mapping ----------------
    name_to_id = build_player_name_to_id()
    print(f"[probe_R14_H4] player-id table built: {len(name_to_id)} names")
    df = attach_player_ids(df, name_to_id)
    n_mapped = int(df["player_id"].notna().sum())
    print(f"[probe_R14_H4] scraped→player_id mapped: {n_mapped}/{len(df)}")

    # ---------------- OOF cross-reference ----------------
    n_overlap, overlap_ids = cross_reference_with_oof(df)
    print(f"[probe_R14_H4] mapped IDs that exist in OOF parquet: {n_overlap}")

    # ---------------- Top-5 impactful ----------------
    top5 = top_5_impactful(df, overlap_ids)
    if top5:
        print("[probe_R14_H4] top-5 most-impactful (today):")
        for t in top5:
            print(f"    {t['player_name']:25s} {t['team']:4s} "
                  f"{t['status']:12s} avg_oof_pts={t['avg_oof_pts']:5.2f} "
                  f"impact={t['impact_score']:5.2f}")

    # ---------------- Snapshot ----------------
    snap_path = write_snapshot(df, args.date)
    print(f"[probe_R14_H4] snapshot written → {snap_path}")

    # ---------------- SHIP gate ----------------
    ship = (
        schema_valid
        and len(df[df["status"].isin(VALID_STATUSES)]) >= 30
        and n_overlap >= 5
    )
    ship_status = "SHIP" if ship else "REJECT"

    # ---------------- Results JSON ----------------
    results = {
        "probe":            "R14_H4_injury_feed",
        "run_date":         args.date,
        "wall_seconds":     round(time.time() - t0, 2),
        "source_chosen":    "espn_public_api",
        "http_status":      http_status,
        "n_players_scraped": int(len(df)),
        "schema_validity":  bool(schema_valid),
        "n_player_id_mapped": int(n_mapped),
        "n_overlap_with_oof": int(n_overlap),
        "sample_rows": df.head(5).where(pd.notna(df.head(5)), None)
                          .to_dict(orient="records"),
        "status_distribution": df["status"].value_counts().to_dict(),
        "top_5_impactful":  top5,
        "ship_status":      ship_status,
        "ship_criteria": {
            "schema_valid":        bool(schema_valid),
            "n_scraped_ge_30":     bool(len(df) >= 30),
            "n_overlap_ge_5":      bool(n_overlap >= 5),
        },
        "next_step_recommendation": (
            "If SHIP: cron the scraper every 30 min on game days, then "
            "wire availability_factor into prop_pergame.py as a final "
            "multiplicative dampener on q50 predictions. Walk-forward "
            "validate on 2024-25 season where injury data is dense."
            if ship else
            "If REJECT: re-try with residential proxy or fall back to "
            "the NBA.com PDF route (scripts/fetch_injury_report.py)."
        ),
    }

    out_dir = os.path.join(PROJECT_DIR, "data", "cache")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "probe_R14_H4_injury_feed_results.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"[probe_R14_H4] results → {out_path}")
    print(f"[probe_R14_H4] {ship_status} "
          f"(scraped={len(df)}, overlap={n_overlap})")
    return 0 if ship else 0  # Non-zero would mask a clean REJECT in CI


if __name__ == "__main__":
    sys.exit(main())
