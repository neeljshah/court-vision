"""scripts.platformkit.omni.news_knowability -- P5 knowability-stamped news/injury layer.

Ingests EXISTING injury-capture snapshots (does not scrape) and normalizes
them into report-stamped rows so injury state becomes queryable as-of any
decision time through the P1-A feature_store leak guard.

Source found in STEP 0 discovery: data/cache/nba_injuries_*.parquet -- daily
ESPN injury snapshots written by the m39 injury daemon (armed 2026-07-09),
columns: player_name, team, status, reason, source, fetched_at, report_date.
``fetched_at`` is the KNOWABILITY stamp (when we captured the item), never
the game date -- this is the whole point of the leak-guard framing.

Row shape (news_events.jsonl):
    sport, player_or_entity, status, minutes_implication (ordinal),
    report_ts, source, raw_ref, content_hash

INVARIANTS: pandas + stdlib only. <=300 LOC. ASCII stdout. data/registry/
read-only (never written). No $/edge claims -- this is availability state,
not a bet signal.
"""
from __future__ import annotations

import glob
import hashlib
import json
import pathlib
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from scripts.platformkit.io_atomic import append_jsonl_atomic
from scripts.platformkit.omni import feature_store

_NEWS_DIR = pathlib.Path("data/omni/news")
_EVENTS_NAME = "news_events.jsonl"
_FRESHNESS_NAME = "freshness.json"
_PIPELINE_VERSION = "p5_news_v1"

# Ordinal = likelihood of playing (higher = more likely). Unknown -> skipped.
_STATUS_ORDINAL = {
    "OUT": 0,
    "DOUBTFUL": 1,
    "QUESTIONABLE": 2,
    "DAY_TO_DAY": 2,
    "DTD": 2,
    "PROBABLE": 3,
    "AVAILABLE": 4,
    "ACTIVE": 4,
}


def _events_path(base_dir=None) -> pathlib.Path:
    return (pathlib.Path(base_dir) if base_dir is not None else _NEWS_DIR) / _EVENTS_NAME


def _freshness_path(base_dir=None) -> pathlib.Path:
    return (pathlib.Path(base_dir) if base_dir is not None else _NEWS_DIR) / _FRESHNESS_NAME


def _content_hash(row: dict) -> str:
    """Stable hash over the fields that make a captured item unique -- idempotency key."""
    basis = f"{row['sport']}|{row['player_or_entity']}|{row['status']}|{row['report_ts']}|{row['source']}|{row['raw_ref']}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _normalize_status(raw_status: Any) -> int | None:
    if raw_status is None:
        return None
    key = str(raw_status).strip().upper().replace("-", "_").replace(" ", "_")
    return _STATUS_ORDINAL.get(key)


def ingest_news(source_glob: str, *, sport: str = "nba", base_dir=None) -> dict:
    """Read parquet/jsonl files matching *source_glob*, normalize, append idempotently.

    Returns {n_read, n_written, n_skipped_unknown_status, n_duplicate, new_events}.
    ``new_events`` holds only the rows actually appended THIS call -- callers
    that push to feature_store on every run (e.g. this module's __main__)
    should push only these, not load_events()'s full history, or a rerun
    would double every row in the feature store.
    """
    files = sorted(glob.glob(source_glob))
    existing_hashes: set[str] = set()
    events_path = _events_path(base_dir)
    if events_path.is_file():
        with open(events_path, "r", encoding="ascii") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    existing_hashes.add(json.loads(line)["content_hash"])

    n_read = 0
    n_written = 0
    n_skipped = 0
    n_dup = 0
    new_events: list[dict] = []
    for fpath in files:
        if fpath.endswith(".parquet"):
            df = pd.read_parquet(fpath)
        elif fpath.endswith(".jsonl"):
            df = pd.read_json(fpath, lines=True)
        else:
            continue
        for _, r in df.iterrows():
            n_read += 1
            player = r.get("player_name")
            status_raw = r.get("status")
            report_ts = r.get("fetched_at")
            if player is None or status_raw is None or report_ts is None or pd.isna(report_ts):
                n_skipped += 1
                continue
            ordinal = _normalize_status(status_raw)
            if ordinal is None:
                n_skipped += 1
                continue
            row = {
                "sport": sport,
                "player_or_entity": str(player),
                "status": str(status_raw).strip().upper(),
                "minutes_implication": ordinal,
                "report_ts": pd.Timestamp(report_ts).tz_localize("UTC").isoformat()
                if pd.Timestamp(report_ts).tzinfo is None
                else pd.Timestamp(report_ts).tz_convert("UTC").isoformat(),
                "source": str(r.get("source", "unknown")),
                "raw_ref": fpath,
            }
            row["content_hash"] = _content_hash(row)
            if row["content_hash"] in existing_hashes:
                n_dup += 1
                continue
            append_jsonl_atomic(events_path, row)
            existing_hashes.add(row["content_hash"])
            new_events.append(row)
            n_written += 1

    return {
        "n_read": n_read,
        "n_written": n_written,
        "n_skipped_unknown_status": n_skipped,
        "n_duplicate": n_dup,
        "new_events": new_events,
    }


def to_feature_rows(events: list[dict]) -> pd.DataFrame:
    """Map normalized news events -> feature_store row schema (entity=player)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "entity": e["player_or_entity"],
            "key": "injury_status",
            "value": float(e["minutes_implication"]),
            "knowable_at": e["report_ts"],
            "computed_at": now_iso,
            "pipeline_version": _PIPELINE_VERSION,
        }
        for e in events
    ]
    cols = ["entity", "key", "value", "knowable_at", "computed_at", "pipeline_version"]
    return pd.DataFrame(rows, columns=cols)


def load_events(base_dir=None) -> list[dict]:
    events_path = _events_path(base_dir)
    if not events_path.is_file():
        return []
    with open(events_path, "r", encoding="ascii") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def push_to_feature_store(sport: str, events: list[dict]) -> int:
    """Convert events for *sport* into as-of feature rows and persist via P1-A store."""
    sport_events = [e for e in events if e["sport"] == sport]
    if not sport_events:
        return 0
    df = to_feature_rows(sport_events)
    return feature_store.put_features(sport, df)


def freshness_report(base_dir=None) -> dict:
    """{n_items, median_capture_lag (None if not computable), latest_ts} -> freshness.json."""
    events = load_events(base_dir)
    n_items = len(events)
    latest_ts = max((e["report_ts"] for e in events), default=None)
    # ponytail: no distinct publish-vs-capture timestamp in the source snapshots
    # (only fetched_at survives), so capture lag is not computable from this
    # source. Wire in a real "published_at" field (e.g. edge_engine news_facts
    # has one) if/when a lag number is actually needed.
    report = {
        "n_items": n_items,
        "median_capture_lag": None,
        "latest_ts": latest_ts,
    }
    out_path = _freshness_path(base_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii") as fh:
        json.dump(report, fh, indent=2)
    return report


if __name__ == "__main__":
    stats = ingest_news("data/cache/nba_injuries_*.parquet", sport="nba")
    new_events = stats.pop("new_events")
    print(json.dumps(stats))
    n_total = push_to_feature_store("nba", new_events)  # only THIS run's new rows
    print(json.dumps({"n_new_rows_pushed": len(new_events), "feature_store_total_rows": n_total}))
    print(json.dumps(freshness_report()))
