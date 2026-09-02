"""domains.soccer.ingest_espn_athlete -- ESPN keyless ATHLETE-OVERVIEW club priors.

EDGE-UNLOCK substrate. World Cup players carry ~1 WC match of history, so their
prop rates shrink almost entirely to a position baseline and the board produces 0
RELIABLE edges. This module ingests each athlete's CLUB-SEASON per-stat aggregates
from the ESPN athlete OVERVIEW endpoint (keyless) and writes them as a STRONG prior
so a player with a real club season gets a reliable rate baseline. This is real
data, not fabrication -- a club season is the player's true recent form.

Endpoint (confirmed keyless 2026-06-17; the /gamelog endpoint 500s -- use OVERVIEW):
  https://site.web.api.espn.com/apis/common/v3/sports/soccer/{league}/athletes/{id}/overview
Returns ``statistics`` with:
  statistics["names"]  -> stat-name order, aligned to each split's ``stats`` values.
  statistics["splits"] -> per-competition splits, each {displayName, leagueSlug,
                          leagueId, teamSlug, teamId, stats:[values aligned to names]}.
Each split is a CLUB/competition SEASON AGGREGATE with exactly our target stats.

per_start -> per90 APPROXIMATION (documented): ESPN gives season totals + ``starts``
but not minutes. A started match is ~90 minutes, so we treat ``starts`` as the
per-90 denominator (started-match count) and per_start = total/starts is read
downstream as a per90 rate. This slightly UNDER-counts the denominator (it ignores
sub appearances) so the per90 is a mild OVER-estimate; it is a PRIOR to be blended,
not a trusted probability. starts==0 -> per_start None.

Network isolation: http_get is INJECTABLE; no network at import time.
Public functions NEVER raise -- they degrade to {} / "unknown".
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd

from domains.soccer.player_rates import CANON_TO_COLS
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_TIMEOUT = 12
_OVERVIEW_URL = (
    "https://site.web.api.espn.com/apis/common/v3/sports/soccer/"
    "{league}/athletes/{athlete_id}/overview"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "soccer" / "espn_club_priors.parquet"
_PLAYERS_PARQUET = (
    _REPO_ROOT / "data" / "domains" / "soccer" / "espn_player_stats.parquet"
)

# Tokens that mark a split as a NATIONAL-TEAM / friendly / World-Cup competition.
# We EXCLUDE these so we measure CLUB form and never double-count WC data.
_INTL_TOKENS = (
    "world cup", "friendl", "national", "nations league", "qualif", "euro",
    "copa america", "international", "fifa", "concacaf", "conmebol", "afcon",
    "africa cup", "asian cup", "gold cup",
)


def _default_http_get(url: str) -> dict:
    """Fetch url via urllib; returns {} on any error."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        log.warning("ESPN overview fetch failed url=%s err=%s", url, exc)
        return {}


def fetch_athlete_overview(
    athlete_id, league: str = "esp.1", http_get: Optional[Callable] = None
) -> dict:
    """Raw athlete OVERVIEW payload for one athlete id; {} on any error."""
    getter = http_get or _default_http_get
    url = _OVERVIEW_URL.format(league=league, athlete_id=str(athlete_id))
    payload = getter(url)
    return payload if isinstance(payload, dict) else {}


def _is_intl_split(split: dict) -> bool:
    """True when a split looks like a national-team / friendly / WC competition."""
    blob = " ".join(
        str(split.get(k, "")) for k in ("displayName", "leagueSlug", "name")
    ).lower()
    return any(tok in blob for tok in _INTL_TOKENS)


def _num(value) -> Optional[float]:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_club_prior(overview: dict) -> Dict[str, Dict[str, Optional[float]]]:
    """Aggregate CLUB-season totals per canonical stat from an OVERVIEW payload.

    SUMS totals and SUMS starts across all CLUB/competition splits (excluding any
    international/friendly/WC split). Returns
      {stat_canonical: {"total": float, "starts": float, "per_start": float|None}}
    for every canonical stat the engine models. Cards = yellowCards + redCards.
    per_start = total/starts (starts==0 -> None). Empty/missing -> {}.
    """
    if not isinstance(overview, dict):
        return {}
    stats = overview.get("statistics")
    if not isinstance(stats, dict):
        return {}
    names = stats.get("names")
    splits = stats.get("splits")
    if not isinstance(names, list) or not isinstance(splits, list):
        return {}
    idx = {str(n): i for i, n in enumerate(names)}
    start_i = idx.get("starts")

    # Sum each raw ESPN column + starts across club splits.
    raw_totals: Dict[str, float] = {}
    starts_total = 0.0
    used_any = False
    for split in splits:
        if not isinstance(split, dict) or _is_intl_split(split):
            continue
        values = split.get("stats")
        if not isinstance(values, list):
            continue
        used_any = True
        if start_i is not None and start_i < len(values):
            s = _num(values[start_i])
            if s is not None:
                starts_total += s
        for col, i in idx.items():
            if i < len(values):
                v = _num(values[i])
                if v is not None:
                    raw_totals[col] = raw_totals.get(col, 0.0) + v

    if not used_any:
        return {}

    out: Dict[str, Dict[str, Optional[float]]] = {}
    for canon, cols in CANON_TO_COLS.items():
        total = 0.0
        have = False
        for col in cols:
            if col in raw_totals:
                total += raw_totals[col]
                have = True
        if not have:
            continue
        per_start = (total / starts_total) if starts_total > 0 else None
        out[canon] = {
            "total": float(total),
            "starts": float(starts_total),
            "per_start": (float(per_start) if per_start is not None else None),
        }
    return out


def build_club_priors(
    athlete_ids: Sequence,
    league: str = "esp.1",
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """Fetch+parse each athlete's club prior; write rows to the club-priors parquet.

    One row per (player_id, stat_canonical) with {total, starts, per_start, as_of};
    dedup on (player_id, stat_canonical) keeping last. Athletes that error / return
    empty are SKIPPED. Returns the output path. Never raises.
    """
    out = Path(out_path) if out_path else _DEFAULT_OUT
    getter = http_get or _default_http_get
    as_of = dt.date.today().isoformat()
    rows: List[dict] = []
    for aid in athlete_ids or []:
        try:
            overview = fetch_athlete_overview(aid, league=league, http_get=getter)
            priors = parse_club_prior(overview)
        except Exception as exc:  # noqa: BLE001 -- one bad athlete must not sink the run
            log.warning("club prior failed athlete=%s err=%s", aid, exc)
            continue
        for canon, vals in priors.items():
            rows.append({
                "player_id": str(aid),
                "stat_canonical": canon,
                "total": vals.get("total"),
                "starts": vals.get("starts"),
                "per_start": vals.get("per_start"),
                "as_of": as_of,
            })

    new_df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["player_id", "stat_canonical", "total", "starts", "per_start", "as_of"]
    )
    if out.exists() and not new_df.empty:
        try:
            existing = pd.read_parquet(out)
            new_df = (
                pd.concat([existing, new_df], ignore_index=True)
                .drop_duplicates(subset=["player_id", "stat_canonical"], keep="last")
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("S95: unreadable existing parquet %s" % out) from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(new_df, out)
    log.info("Wrote %d club-prior rows to %s", len(new_df), out)
    return out


def club_prior(
    player_id, stat_canonical: str, priors_path: Optional[Path] = None
) -> Dict[str, object]:
    """Look up one player's club prior. Returns
      {"per90": float|None, "starts": float, "status": "ok"|"unknown"}.
    per90 is the stored per_start (a started match ~ 90 min; see module docstring).
    Missing player/stat/parquet -> status "unknown". Never raises.
    """
    unknown = {"per90": None, "starts": 0.0, "status": "unknown"}
    path = Path(priors_path) if priors_path else _DEFAULT_OUT
    if not path.exists():
        return dict(unknown)
    try:
        df = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return dict(unknown)
    if df is None or len(df) == 0:
        return dict(unknown)
    pid = str(player_id)
    sub = df[
        (df["player_id"].astype(str) == pid)
        & (df["stat_canonical"].astype(str) == str(stat_canonical))
    ]
    if len(sub) == 0:
        return dict(unknown)
    row = sub.iloc[-1]
    per_start = row.get("per_start")
    starts = row.get("starts")
    try:
        starts_f = float(starts) if starts is not None and pd.notna(starts) else 0.0
    except (TypeError, ValueError):
        starts_f = 0.0
    if per_start is None or pd.isna(per_start):
        return {"per90": None, "starts": starts_f, "status": "unknown"}
    return {"per90": float(per_start), "starts": starts_f, "status": "ok"}


def _player_ids_from_parquet(path: Path, sample: Optional[int] = None) -> List[str]:
    try:
        df = pd.read_parquet(path, columns=["player_id"])
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read player ids from %s: %s", path, exc)
        return []
    ids = [str(x) for x in df["player_id"].dropna().drop_duplicates().tolist()]
    if sample is not None and sample > 0:
        ids = ids[:sample]
    return ids


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest ESPN athlete-overview club priors for soccer props."
    )
    parser.add_argument("--ids", nargs="+", default=None, help="explicit athlete ids")
    parser.add_argument("--league", default="esp.1")
    parser.add_argument("--out", default=None)
    parser.add_argument("--sample", type=int, default=None,
                        help="only the first N ids from the players parquet")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ids = args.ids or _player_ids_from_parquet(_PLAYERS_PARQUET, args.sample)
    path = build_club_priors(ids, league=args.league, out_path=args.out)
    print(f"Done: {path} ({len(ids)} ids)")


if __name__ == "__main__":
    _main()
