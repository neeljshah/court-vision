"""domains.mlb.ingest_injuries -- ESPN free-API MLB injury-report snapshot ingest.

KNOWLEDGE/SUBSTRATE ONLY -- NOT a model-feed signal by itself.
Adds data depth (injury status + beat-writer text), not edge. Markets already
price public injury news; this module makes that news available to the SAME
deterministic edge-fact extractor every other source feeds (edge_engine), it
does not create a new advantage on its own.

Endpoint (free, no auth, keyless with a browser UA):
  https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/injuries

LEAK CONTRACT: captured_at is WHEN WE OBSERVED the row (ISO UTC, set at fetch
time) -- NOT when the injury happened. injury_date is ESPN's own 'date' field
on the injury entry and can lag or lead our capture. As-of joins MUST key on
snapshot_date (the day WE captured this row), never on injury_date alone --
injury_date is unverified provenance metadata, not a vintage guarantee.

Network isolation: http_get is INJECTABLE; no network call happens at import.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_TIMEOUT = 12
_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/injuries"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "mlb" / "injuries.parquet"
_DEFAULT_FACTS_OUT = _REPO_ROOT / "data" / "domains" / "mlb" / "edge_facts_injuries.parquet"

_SNAPSHOT_COLUMNS = [
    "snapshot_date", "captured_at", "team", "athlete_id", "athlete_name",
    "position", "status", "injury_date", "injury_type", "detail", "side",
    "return_date", "short_comment", "long_comment",
]

_PLAYER_ID_RE = re.compile(r"/mlb/player/(?:[a-z]+/)?_/id/(\d+)")


# ---------------------------------------------------------------------------
# Network layer
# ---------------------------------------------------------------------------

def _default_http_get(url: str) -> dict:
    """Fetch url via urllib; returns {} on any error."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        log.warning("ESPN fetch failed url=%s err=%s", url, exc)
        return {}


# ---------------------------------------------------------------------------
# Pure parsing helpers (no I/O)
# ---------------------------------------------------------------------------

def _athlete_id(athlete: dict) -> Optional[int]:
    """Pull the numeric ESPN athlete id out of a playercard/overview link href.

    The injury payload never carries athlete.id directly -- only link hrefs
    like '.../mlb/player/_/id/32046/james-mccann'. Returns None if no link
    parses (handled gracefully downstream -- nullable Int64 column).
    """
    for link in athlete.get("links") or []:
        href = link.get("href", "")
        m = _PLAYER_ID_RE.search(href)
        if m:
            return int(m.group(1))
    return None


def _parse_injury_row(team_name: str, entry: dict, snapshot_date: str, captured_at: str) -> Optional[dict]:
    """Parse one injuries[].injuries[] entry into a flat snapshot row.

    Returns None only if there is no usable athlete name at all. Every other
    field is optional and defaults to None/''. PURE -- no I/O.
    """
    athlete = entry.get("athlete") or {}
    name = athlete.get("displayName") or athlete.get("shortName")
    if not name:
        return None

    details = entry.get("details") or {}
    position = (athlete.get("position") or {}).get("abbreviation")

    return {
        "snapshot_date": snapshot_date,
        "captured_at": captured_at,
        "team": team_name,
        "athlete_id": _athlete_id(athlete),
        "athlete_name": name,
        "position": position,
        "status": entry.get("status"),
        "injury_date": entry.get("date"),
        "injury_type": details.get("type"),
        "detail": details.get("detail"),
        "side": details.get("side"),
        "return_date": details.get("returnDate"),
        "short_comment": entry.get("shortComment") or "",
        "long_comment": entry.get("longComment") or "",
    }


def parse_injuries_payload(payload: dict, snapshot_date: str, captured_at: str) -> List[dict]:
    """Flatten an ESPN injuries payload into a list of snapshot rows. PURE -- no I/O."""
    rows: List[dict] = []
    for team_block in payload.get("injuries") or []:
        team_name = team_block.get("displayName", "")
        for entry in team_block.get("injuries") or []:
            row = _parse_injury_row(team_name, entry, snapshot_date, captured_at)
            if row is not None:
                rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Fetch + snapshot-append layer
# ---------------------------------------------------------------------------

def fetch_injuries(http_get: Optional[Callable] = None) -> dict:
    """Fetch the raw ESPN injuries payload; returns {} on error."""
    getter = http_get or _default_http_get
    return getter(_INJURIES_URL)


def _now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ingest_snapshot(
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
    snapshot_date: Optional[str] = None,
    captured_at: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch one injuries snapshot and merge it into the append-only parquet.

    Dedup key is (snapshot_date, athlete_id) keep-last -- a same-day re-run is
    idempotent (row count does not grow), but prior snapshot_dates are NEVER
    dropped, so history across days is preserved for as-of joins. Rows with a
    null athlete_id fall back to (snapshot_date, team, athlete_name) for dedup
    since Int64 NaN cannot be a reliable subset key.
    Returns the full (existing + new) DataFrame that was written.
    """
    out = Path(out_path) if out_path else _DEFAULT_OUT
    snap_date = snapshot_date or dt.date.today().strftime("%Y-%m-%d")
    cap_at = captured_at or _now_utc_iso()

    payload = fetch_injuries(http_get=http_get)
    rows = parse_injuries_payload(payload, snap_date, cap_at)
    new_df = pd.DataFrame(rows, columns=_SNAPSHOT_COLUMNS)
    if not new_df.empty:
        new_df["athlete_id"] = new_df["athlete_id"].astype("Int64")

    if out.exists():
        try:
            existing = pd.read_parquet(out)
            new_df = pd.concat([existing, new_df], ignore_index=True)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("S95: unreadable existing parquet %s" % out) from exc
    if not new_df.empty:
        has_id = new_df["athlete_id"].notna()
        keyed = new_df[has_id].drop_duplicates(subset=["snapshot_date", "athlete_id"], keep="last")
        unkeyed = new_df[~has_id].drop_duplicates(
            subset=["snapshot_date", "team", "athlete_name"], keep="last"
        )
        new_df = pd.concat([keyed, unkeyed], ignore_index=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    if not new_df.empty:
        write_parquet_atomic(new_df, out)
    log.info("injuries snapshot: %d rows -> %s", len(new_df), out)
    return new_df


# ---------------------------------------------------------------------------
# Edge-facts bridge -- feeds beat-writer text through the deterministic extractor
# ---------------------------------------------------------------------------

def _load_edge_engine():
    """Import the edge_engine schema/extractor. Isolated so import errors are legible."""
    try:  # package import
        from scripts.platformkit.edge_engine.schema_source import SourceDoc  # type: ignore
        from scripts.platformkit.edge_engine.extract import extract_rule  # type: ignore
    except ImportError:  # direct-script fallback
        import sys
        sys.path.insert(0, str(_REPO_ROOT))
        from scripts.platformkit.edge_engine.schema_source import SourceDoc  # type: ignore
        from scripts.platformkit.edge_engine.extract import extract_rule  # type: ignore
    return SourceDoc, extract_rule


_FACT_COLUMNS = [
    "fact_kind", "sport", "subject_id", "game_date", "value_text",
    "source", "availability_ts", "confidence",
]


def build_edge_facts(snapshot_rows: List[dict]) -> List[dict]:
    """Run each injury row's beat text through edge_engine.extract_rule.

    Only rows with non-empty long_comment/short_comment text produce a
    SourceDoc (there is nothing to extract from bare status codes). Uses the
    RULE fallback only -- extract_llm is a human-gated stub and is never
    called here. Each row is wrapped in try/except so one malformed row never
    kills the run; failures are logged and skipped.
    """
    SourceDoc, extract_rule = _load_edge_engine()
    facts: List[dict] = []
    for row in snapshot_rows:
        text = row.get("long_comment") or row.get("short_comment") or ""
        if not text:
            continue
        athlete_id = row.get("athlete_id")
        subject_id = str(athlete_id) if athlete_id is not None else row.get("athlete_name", "")
        if not subject_id:
            continue
        try:
            doc = SourceDoc(
                doc_id=f"espn-injury-{row.get('snapshot_date')}-{subject_id}",
                sport="mlb",
                published_ts=row.get("captured_at"),
                text=text,
                source="https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/injuries",
                doc_date=row.get("snapshot_date"),
            )
            for f in extract_rule(doc, subject_id=subject_id, game_date=row.get("snapshot_date")):
                facts.append(f.as_dict())
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "edge-fact extraction failed subject_id=%s snapshot_date=%s err=%s",
                subject_id, row.get("snapshot_date"), exc,
            )
            continue
    return facts


def write_edge_facts(facts: List[dict], out_path: Optional[Path] = None) -> pd.DataFrame:
    """Append+dedup facts into the edge-facts parquet on (game_date, subject_id, fact_kind)."""
    out = Path(out_path) if out_path else _DEFAULT_FACTS_OUT
    new_df = pd.DataFrame(facts, columns=_FACT_COLUMNS)

    if out.exists():
        try:
            existing = pd.read_parquet(out)
            new_df = pd.concat([existing, new_df], ignore_index=True)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("S95: unreadable existing parquet %s" % out) from exc

    if not new_df.empty:
        new_df = new_df.drop_duplicates(subset=["game_date", "subject_id", "fact_kind"], keep="last")

    out.parent.mkdir(parents=True, exist_ok=True)
    if not new_df.empty:
        write_parquet_atomic(new_df, out)
    log.info("edge facts: %d rows -> %s", len(new_df), out)
    return new_df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    snap_df = ingest_snapshot()
    today_rows: List[dict] = []
    if not snap_df.empty:
        snap_date = snap_df["snapshot_date"].iloc[-1]
        today_rows = snap_df[snap_df["snapshot_date"] == snap_date].to_dict("records")

    facts = build_edge_facts(today_rows)
    facts_df = write_edge_facts(facts)

    teams = snap_df["team"].nunique() if not snap_df.empty else 0
    print(f"snapshot rows: {len(snap_df)}")
    print(f"teams: {teams}")
    if not facts_df.empty:
        counts = facts_df["fact_kind"].value_counts().to_dict()
        print(f"facts emitted by fact_kind: {counts}")
    else:
        print("facts emitted by fact_kind: {}")


if __name__ == "__main__":
    _main()
