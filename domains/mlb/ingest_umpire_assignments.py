"""domains.mlb.ingest_umpire_assignments -- FORWARD umpire crew assignment store.

KNOWLEDGE/SUBSTRATE ONLY -- NOT a model-feed signal, no edge claimed.

PREMISE (verified 2026-07-09): no new scraping is needed. The statsapi
schedule endpoint ALREADY carries the full officials crew via
hydrate=officials -- the SAME endpoint/payload ingest_probables.py fetches
every ~6h under the M31 daemon (scripts/platformkit/mlb_context_runner.py).
ingest_probables keeps ONLY the Home Plate umpire; this module parses the
FULL crew (Home Plate / First Base / Second Base / Third Base, plus LF/RF in
postseason) into a long-format as-of store keyed by game_pk. gumbo_live
ticks do NOT carry officials (flattened count/base-state dicts only), so
the schedule hydrate is the right source.

STORE: data/domains/mlb/umpire_assignments.parquet -- one row per
(game_pk, official_type, snapshot_date), dedup keep-last, snapshot-append.
Games whose officials block is absent/empty (usual until near first pitch)
contribute NO rows -- absence of a (game_pk, snapshot_date) row means "crew
not yet posted as of that snapshot".

LEAK CONTRACT (same as ingest_probables): captured_at records when WE knew
it. Officials usually post near/at game time; a crew scraped on game day is
not known information at any earlier as-of point. Downstream joins MUST be
as-of on snapshot_date/captured_at, never game_date alone.

JOIN TARGET: umpire_id here is the MLB person id -- the SAME namespace as
data/cache/intel_claims/umpire_zone_claims.jsonl ranking entity_key
umpire_id (via probables.parquet hp_umpire_id). See
test_ingest_umpire_assignments.py::test_live_join_to_umpire_zone_claims.

Network isolation: http_get is INJECTABLE; no network at import time.

CLI:
    python -m domains.mlb.ingest_umpire_assignments            # today+tomorrow
    python -m domains.mlb.ingest_umpire_assignments --date 2026-07-09
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import time
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import pandas as pd

# ponytail: reuse the probables fetch layer -- same endpoint, same UA/timeout.
from domains.mlb.ingest_probables import _SCHEDULE_URL, _default_http_get
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "mlb" / "umpire_assignments.parquet"

_DEDUP_KEYS = ["game_pk", "official_type", "snapshot_date"]

_COLUMNS = [
    "game_pk", "game_date", "snapshot_date", "captured_at",
    "home_team", "away_team", "official_type", "umpire_id", "umpire_name",
]


# ---------------------------------------------------------------------------
# Pure parsing (no I/O)
# ---------------------------------------------------------------------------

def parse_game_officials(game: dict, snapshot_date: str, captured_at: str) -> List[dict]:
    """Parse one schedule game entry into 0..N crew rows (one per official).

    Returns [] when the game entry lacks gamePk/teams or its officials block
    is absent/empty (normal far from first pitch). PURE -- no I/O.
    """
    if not game:
        return []
    game_pk = game.get("gamePk")
    teams = game.get("teams") or {}
    home = (teams.get("home") or {}).get("team") or {}
    away = (teams.get("away") or {}).get("team") or {}
    if game_pk is None or not home.get("name") or not away.get("name"):
        return []
    rows: List[dict] = []
    for off in game.get("officials") or []:
        person = off.get("official") or {}
        if person.get("id") is None:
            continue
        rows.append({
            "game_pk": int(game_pk),
            "game_date": game.get("officialDate"),
            "snapshot_date": snapshot_date,
            "captured_at": captured_at,
            "home_team": home.get("name"),
            "away_team": away.get("name"),
            "official_type": off.get("officialType") or "Unknown",
            "umpire_id": int(person["id"]),
            "umpire_name": person.get("fullName"),
        })
    return rows


def parse_schedule_officials(payload: dict, snapshot_date: str, captured_at: str) -> List[dict]:
    """Parse a full schedule payload into crew rows across all games. PURE."""
    if not payload:
        return []
    rows: List[dict] = []
    for date_block in payload.get("dates") or []:
        for game in date_block.get("games") or []:
            rows.extend(parse_game_officials(game, snapshot_date, captured_at))
    return rows


# ---------------------------------------------------------------------------
# Fetch + parquet merge
# ---------------------------------------------------------------------------

def fetch_date(date: str, http_get: Optional[Callable] = None) -> List[dict]:
    """Fetch + parse the officials crew for one YYYY-MM-DD schedule date."""
    getter = http_get or _default_http_get
    payload = getter(_SCHEDULE_URL.format(date=date))
    snapshot_date = dt.date.today().isoformat()
    captured_at = dt.datetime.utcnow().isoformat() + "Z"
    return parse_schedule_officials(payload, snapshot_date, captured_at)


def _rows_to_frame(rows: Sequence[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=_COLUMNS)
    df = pd.DataFrame(rows)[_COLUMNS]
    df["game_pk"] = df["game_pk"].astype("int64")
    df["umpire_id"] = df["umpire_id"].astype("int64")
    return df


def ingest_range(
    dates: Sequence[str],
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
    sleep_s: float = 1.0,
) -> Path:
    """Fetch officials crews for *dates* and merge into the as-of parquet.

    Idempotent: dedup keep-last on (game_pk, official_type, snapshot_date).
    sleep_s=1.0 between dates honors the 1 req/s politeness rail.
    """
    out = Path(out_path) if out_path else _DEFAULT_OUT
    getter = http_get or _default_http_get
    rows: List[dict] = []
    for i, date in enumerate(dates):
        rows.extend(fetch_date(date, http_get=getter))
        if sleep_s and i < len(dates) - 1:
            time.sleep(sleep_s)

    new_df = _rows_to_frame(rows)
    if not new_df.empty:
        new_df = new_df.drop_duplicates(subset=_DEDUP_KEYS, keep="last")

    if out.exists():
        try:
            existing = pd.read_parquet(out)
            combined = pd.concat([existing, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=_DEDUP_KEYS, keep="last")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("S95: unreadable existing parquet %s" % out) from exc
    else:
        combined = new_df

    out.parent.mkdir(parents=True, exist_ok=True)
    if not combined.empty:
        write_parquet_atomic(combined, out)
    log.info("Wrote %d rows to %s", len(combined), out)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest MLB umpire crew assignments (keyless statsapi schedule)."
    )
    parser.add_argument("--date", default=None, help="Single date YYYY-MM-DD.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.date:
        dates = [args.date]
    else:
        today = dt.date.today()
        dates = [today.isoformat(), (today + dt.timedelta(days=1)).isoformat()]

    result = ingest_range(dates)
    df = pd.read_parquet(result)
    print("rows_total=%d games=%d out=%s" % (len(df), df["game_pk"].nunique(), result))


if __name__ == "__main__":
    _main()
