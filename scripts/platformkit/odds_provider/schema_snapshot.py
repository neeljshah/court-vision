"""scripts.platformkit.odds_provider.schema_snapshot -- payload shape drift detector.

THE GAP: a provider silently renaming/dropping a JSON field ("odds" -> "price",
or "devigged_prob" vanishing) is indistinguishable today from "no data" --
feed_health.py only checks reachability, never the SHAPE of what came back.

WHAT THIS DOES: derive an expected-shape SNAPSHOT (key paths + value types,
depth-bounded) from a sample payload, store it dated per-provider under
data/cache/schema_snapshots/, and compare() a fresh payload against it ->
missing_keys / new_keys / type_changes. Read-only over the JSONL the platform
ALREADY writes (data/cache/line_history/<sport>/<date>.jsonl, one flat quote
record per line -- see snapshot.py's row shape); no network calls of its own.

HONEST RAILS: pure functions (shape/compare) never raise; only I/O is a local
atomic (tmp+os.replace) read/write under data/cache/schema_snapshots/; no
data/registry/ write, no flag flip, no $ field, no edge claim.

Run: python -m scripts.platformkit.odds_provider.schema_snapshot snapshot --sport nba
     python -m scripts.platformkit.odds_provider.schema_snapshot check --sport nba
Per-file test: scripts/platformkit/odds_provider/test_schema_snapshot.py
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_REPO = Path(__file__).resolve().parents[3]
_SNAPSHOT_DIR = _REPO / "data" / "cache" / "schema_snapshots"
_LINE_HISTORY_DIR = _REPO / "data" / "cache" / "line_history"

MAX_DEPTH = 4

# A baseline this old is itself the fossil -- a field that was null/absent when
# the snapshot was taken (e.g. devigged_prob before it was wired up) drifts
# EVERY scan forever once the real payload fills in, never because the live
# feed broke. 'stale_baseline' self-identifies that case instead of counting
# as persistent drift (see feed_health._schema_drift_notes, which only feeds
# status=="drift" rows into the soft_red promotion counter).
_STALE_BASELINE_DAYS = 14


def _type_name(value: Any) -> str:
    """Python value -> small JSON-ish type vocabulary (int/float collapse to
    "number"; None -> "null") so e.g. devigged_prob 0 vs 0.5 never diffs."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def shape_of(payload: Any, *, max_depth: int = MAX_DEPTH) -> Dict[str, str]:
    """Flatten *payload* into {dotted.key.path: type_name}, bounded to max_depth.
    Arrays are sampled at index 0 only (a "[]" path segment) -- profiles the
    ELEMENT shape of a list-of-records payload without exploding per-index.
    Beyond max_depth a container is recorded by its own type and not descended
    into (bounded, never a runaway walk). Never raises."""
    out: Dict[str, str] = {}

    def _walk(node: Any, path: str, depth: int) -> None:
        t = _type_name(node)
        if depth >= max_depth or t not in ("object", "array"):
            out[path or "$"] = t
            return
        if t == "object":
            out[path or "$"] = t
            for key in sorted(node.keys()):
                child = "%s.%s" % (path, key) if path else str(key)
                _walk(node[key], child, depth + 1)
        elif t == "array":
            out[path or "$"] = t
            if node:
                _walk(node[0], "%s[]" % path if path else "[]", depth + 1)

    try:
        _walk(payload, "", 0)
    except Exception:  # noqa: BLE001 -- shape derivation must never raise
        return {"$": "unknown"}
    return out


def shape_of_records(records: Sequence[Any], *, max_depth: int = MAX_DEPTH) -> Dict[str, str]:
    """Union the shape of every record in *records* (a list of JSONL rows). A key
    present in only SOME records still shows up -- union, not intersection
    (JSONL rows legally vary row-to-row, e.g. a missing "line" on a moneyline
    row). Never raises; empty/None input -> empty shape."""
    union: Dict[str, str] = {}
    try:
        for rec in records or []:
            for path, t in shape_of(rec, max_depth=max_depth).items():
                if path not in union:
                    union[path] = t
                elif union[path] != t and t != "null" and union[path] != "null" \
                        and "mixed(" not in union[path]:
                    # two genuinely different non-null types at the same path --
                    # a synthetic marker so compare() still flags drift.
                    union[path] = "mixed(%s|%s)" % (union[path], t)
    except Exception:  # noqa: BLE001
        return union
    return union


def compare(payload_shape: Dict[str, str], snapshot_shape: Dict[str, str]) -> Dict[str, Any]:
    """Diff a fresh shape against a stored snapshot shape. Never raises.
    missing_keys: in the snapshot but absent fresh (a provider DROPPED a field
    -- the silent-degrade this module exists to catch). new_keys: additive,
    benign, does not flip ok. type_changes: same path, different type_name (a
    rename/restructure masquerading as "still there"). ok is True iff
    missing_keys and type_changes are both empty."""
    try:
        snap_keys = set(snapshot_shape or {})
        fresh_keys = set(payload_shape or {})
        missing = sorted(snap_keys - fresh_keys)
        added = sorted(fresh_keys - snap_keys)
        changed = sorted(p for p in (snap_keys & fresh_keys)
                          if snapshot_shape[p] != payload_shape[p])
    except Exception:  # noqa: BLE001 -- compare must never raise
        return {"ok": False, "missing_keys": [], "new_keys": [], "type_changes": [],
                "error": "compare failed"}
    return {
        "ok": not missing and not changed,
        "missing_keys": missing,
        "new_keys": added,
        "type_changes": changed,
    }


def _snapshot_path(provider: str, sport: str) -> Path:
    safe_provider = str(provider).replace("/", "_").replace(":", "_")
    safe_sport = str(sport).replace("/", "_")
    return _SNAPSHOT_DIR / safe_sport / ("%s.json" % safe_provider)


def save_snapshot(provider: str, sport: str, shape: Dict[str, str], *,
                   sample_size: int, dated: str, path: Optional[Path] = None) -> bool:
    """Atomically write a snapshot doc (tmp + os.replace). Never raises."""
    try:
        out_path = Path(path) if path is not None else _snapshot_path(provider, sport)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"provider": provider, "sport": sport, "dated": dated,
               "sample_size": sample_size, "shape": shape}
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True),
                        encoding="ascii")
        os.replace(str(tmp), str(out_path))
        return True
    except Exception:  # noqa: BLE001 -- write must never crash the caller
        return False


def load_snapshot(provider: str, sport: str, *, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Best-effort read of a stored snapshot doc. None on any failure/missing file."""
    try:
        p = Path(path) if path is not None else _snapshot_path(provider, sport)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="ascii"))
    except Exception:  # noqa: BLE001
        return None


def discover_capture_files(sport: str, *, base_dir: Optional[Path] = None) -> List[Path]:
    """Sport's real JSONL captures under data/cache/line_history/<sport>/, sorted
    ascending (YYYY-MM-DD -> also chronological, newest last -> take [-1]).
    Missing dir -> empty list, never raises."""
    base = Path(base_dir) if base_dir is not None else _LINE_HISTORY_DIR
    sport_dir = base / sport
    try:
        return sorted(sport_dir.glob("*.jsonl"))
    except Exception:  # noqa: BLE001
        return []


def _provider_of(book: str) -> str:
    """Provider id from a row's "book": "espn:DraftKings" -> "espn"; a bare
    "pinnacle"/"kalshi" -> itself unchanged."""
    try:
        return str(book).split(":", 1)[0] or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def load_records_by_provider(jsonl_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Read one JSONL capture file, bucket rows by provider (from "book").
    Malformed lines are skipped -- a single bad line must not sink the read."""
    by_provider: Dict[str, List[Dict[str, Any]]] = {}
    try:
        with open(jsonl_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001 -- one bad row must not sink the file
                    continue
                provider = _provider_of(rec.get("book", "unknown"))
                by_provider.setdefault(provider, []).append(rec)
    except Exception:  # noqa: BLE001
        return {}
    return by_provider


def _latest_by_provider(sport: str, base_dir: Optional[Path]) -> Optional[Any]:
    """(latest_file, {provider: records}) for *sport*'s newest capture, or None."""
    files = discover_capture_files(sport, base_dir=base_dir)
    if not files:
        return None
    latest = files[-1]
    return latest, load_records_by_provider(latest)


def snapshot_sport(sport: str, *, base_dir: Optional[Path] = None,
                    snapshot_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Derive + save a snapshot per provider found in the LATEST capture for
    *sport*. Never raises; an empty/missing capture -> providers: {}."""
    result: Dict[str, Any] = {"sport": sport, "capture_file": None, "providers": {}}
    found = _latest_by_provider(sport, base_dir)
    if found is None:
        return result
    latest, by_provider = found
    result["capture_file"] = str(latest)
    dated = latest.stem
    for provider, records in by_provider.items():
        shape = shape_of_records(records)
        path = Path(snapshot_dir) / sport / ("%s.json" % provider) if snapshot_dir else None
        ok = save_snapshot(provider, sport, shape, sample_size=len(records),
                            dated=dated, path=path)
        result["providers"][provider] = {"sample_size": len(records), "n_keys": len(shape),
                                          "saved": ok}
    return result


def _baseline_age_days(dated: Optional[str], *, today: Optional[datetime.date] = None) -> Optional[int]:
    """Days between a snapshot's "dated" stem (YYYY-MM-DD) and *today*. None on
    missing/malformed input -- never raises. *today* is injectable for tests."""
    if not dated:
        return None
    try:
        d = datetime.date.fromisoformat(str(dated))
        return ((today or datetime.date.today()) - d).days
    except Exception:  # noqa: BLE001
        return None


def check_sport(sport: str, *, base_dir: Optional[Path] = None,
                 snapshot_dir: Optional[Path] = None,
                 today: Optional[datetime.date] = None) -> Dict[str, Any]:
    """Compare the LATEST capture for *sport* against each provider's stored
    snapshot. No stored snapshot yet -> reported, not failed (run `snapshot` first).
    A drifted provider whose baseline is >= _STALE_BASELINE_DAYS old is reported
    as "stale_baseline" instead of "drift" -- a fossil re-baseline problem, not
    live feed breakage (see _STALE_BASELINE_DAYS docstring)."""
    result: Dict[str, Any] = {"sport": sport, "capture_file": None, "providers": {}}
    found = _latest_by_provider(sport, base_dir)
    if found is None:
        return result
    latest, by_provider = found
    result["capture_file"] = str(latest)
    for provider, records in by_provider.items():
        fresh_shape = shape_of_records(records)
        snap_path = Path(snapshot_dir) / sport / ("%s.json" % provider) if snapshot_dir else None
        snap_doc = load_snapshot(provider, sport, path=snap_path)
        if snap_doc is None:
            result["providers"][provider] = {"status": "no_snapshot",
                                              "sample_size": len(records)}
            continue
        diff = compare(fresh_shape, snap_doc.get("shape", {}))
        diff["status"] = "ok" if diff["ok"] else "drift"
        diff["sample_size"] = len(records)
        diff["snapshot_dated"] = snap_doc.get("dated")
        if diff["status"] == "drift":
            age = _baseline_age_days(snap_doc.get("dated"), today=today)
            if age is not None and age >= _STALE_BASELINE_DAYS:
                diff["status"] = "stale_baseline"
                diff["baseline_age_days"] = age
        result["providers"][provider] = diff
    return result


def render(doc: Dict[str, Any]) -> str:
    header = "SCHEMA SNAPSHOT -- %s (%s)" % (doc.get("sport"), doc.get("capture_file"))
    lines = ["=" * 78, header, "=" * 78]
    for provider, info in sorted(doc.get("providers", {}).items()):
        status = info.get("status", "?")
        if status == "no_snapshot":
            lines.append("%-14s NO_SNAPSHOT  n=%d" % (provider, info.get("sample_size", 0)))
        elif "saved" in info:
            lines.append("%-14s SAVED  n=%d  keys=%d" % (provider, info.get("sample_size", 0),
                                                          info.get("n_keys", 0)))
        else:
            lines.append("%-14s %-5s  missing=%s new=%s type_changes=%s" % (
                provider, status.upper(), info.get("missing_keys"), info.get("new_keys"),
                info.get("type_changes")))
    lines.append("-" * 78)
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="schema_snapshot")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("snapshot", "check"):
        sub.add_parser(name).add_argument("--sport", required=True)
    args = parser.parse_args(argv)
    doc = snapshot_sport(args.sport) if args.cmd == "snapshot" else check_sport(args.sport)
    print(render(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "MAX_DEPTH", "shape_of", "shape_of_records", "compare", "save_snapshot",
    "load_snapshot", "discover_capture_files", "load_records_by_provider",
    "snapshot_sport", "check_sport", "render",
]
