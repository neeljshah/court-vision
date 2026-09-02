"""Read-only manifest of every eval-gate artifact on disk.

Walks (never writes into, except the --out manifest itself):
  (a) data/cache/eval_gate/*.json + *.jsonl  -- ledgers (fwer cumulative K, backtest charges)
  (b) docs/evidence/**/*.json                -- harness sweeps / packets (absence tolerated)
  (c) data/cache/**/*_lock*.json, null_ship*.json -- lock + null-ship-calibration artifacts

For each artifact this records: name, verdict (if the file exposes one), an as_of
timestamp (from the file's own fields, else mtime), explicit measurement-time
provenance, staleness in days vs a reference "today", and the source path.

FAIL-CLOSED CONTRACT: nothing an audit cannot read is allowed to vanish silently.
An artifact that cannot be parsed OR stat-ed is emitted as a row with status
UNREADABLE; a DIRECTORY that cannot be traversed is emitted as a scan_error row
(pathlib.rglob swallows PermissionError and would drop a whole subtree without a
trace, so this walks with os.walk + onerror instead). The CLI exits 1 if any row
is UNREADABLE, or (under --max-age-days) if any row is stale.

Staleness is a SEPARATE `stale` flag, never a status value: overwriting status
with "STALE" erased UNREADABLE/EMPTY and hid unparseable artifacts from every
reader that filters on status (S45a). A measurement time in the FUTURE beyond
_FUTURE_TOLERANCE_DAYS is invalid evidence, not fresh evidence, and the row says
so in `measured_at_invalid` (RT-7).

This is an audit/calibration tool. It reports verdicts already present in gate
artifacts; it computes and claims no $ edge / ROI of its own. ASCII + stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

_VERDICT_KEYS = ("verdict", "gate_verdict", "result")
_ASOF_KEYS = ("as_of", "frozen_at", "at", "extracted_at", "ts", "generated_at")

# Freshness is SELF-DECLARED, so an artifact can claim a measurement time in the
# future and read as fresh forever (RT-7 measured as_of=2031-01-01 -> staleness
# -1581.0 days, status OK). A measurement time beyond `as_of` by more than this
# clock-skew tolerance is INVALID evidence, never fresh evidence. Knob, not a
# bar: widen it for a fleet with looser clocks, never to admit a claim.
_FUTURE_TOLERANCE_DAYS = 1.0


def _as_utc(dt: datetime) -> datetime:
    """Naive datetimes are read as UTC. Without this, a caller passing a plain
    datetime(2026, 9, 1) crashed the whole build with 'can't subtract
    offset-naive and offset-aware datetimes'."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_dt(s: Optional[str]):
    if not isinstance(s, str) or not s:
        return None
    s2 = s[:-1] + "+00:00" if s.endswith("Z") else s
    try:
        return _as_utc(datetime.fromisoformat(s2))
    except ValueError:
        return None


def _extract(obj) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not isinstance(obj, dict):
        return None, None, None
    verdict = next((obj[k] for k in _VERDICT_KEYS if k in obj), None)
    as_of_key = next((k for k in _ASOF_KEYS if k in obj), None)
    as_of = obj.get(as_of_key) if as_of_key is not None else None
    return (str(verdict) if verdict is not None else None,
            str(as_of) if as_of is not None else None, as_of_key)


def _load(path: Path):
    """Return parsed content, or None for an empty file. Raises on corrupt content."""
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return None
    if path.suffix == ".jsonl":
        obj = None
        for line in text.splitlines():
            if line.strip():
                obj = json.loads(line)  # any bad line -> raises -> whole file UNREADABLE
        return obj
    return json.loads(text)


def _walk(root: Path, bad_dirs: List[str]) -> Iterator[Path]:
    """Yield every file under root. Unlike Path.rglob (which returns silently on
    PermissionError and drops the entire subtree), an untraversable directory is
    RECORDED in bad_dirs so the audit can fail closed on it."""
    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(
        root, onerror=lambda e: bad_dirs.append(f"{e.filename}: {type(e).__name__}: {e}")
    ):
        dirnames.sort()
        for name in sorted(filenames):
            yield Path(dirpath) / name


def _scan(repo_root: Path, bad_dirs: List[str],
          exclude: Optional[Path] = None) -> List[Tuple[Path, str]]:
    seen: Dict[Path, Tuple[Path, str]] = {}
    skip = exclude.resolve() if exclude else None

    def claim(p: Path, category: str) -> None:
        rp = p.resolve()
        if rp != skip:
            seen.setdefault(rp, (p, category))

    ledger_dir = repo_root / "data" / "cache" / "eval_gate"
    for p in _walk(ledger_dir, bad_dirs):
        if p.parent == ledger_dir and p.suffix in (".json", ".jsonl"):
            claim(p, "ledger")

    for p in _walk(repo_root / "docs" / "evidence", bad_dirs):
        if p.suffix == ".json":
            claim(p, "evidence")

    for p in _walk(repo_root / "data" / "cache", bad_dirs):
        if p.suffix == ".json" and ("_lock" in p.name or p.name.startswith("null_ship")):
            claim(p, "lock_or_null_ship")

    return list(seen.values())


def _dir_error_row(msg: str) -> dict:
    return {"name": "<unreadable dir>", "source_path": msg, "category": "scan_error",
            "status": "UNREADABLE", "verdict": None, "as_of_field": None,
            "mtime": None, "measured_at": None, "measured_at_source": None,
            "measured_at_invalid": None, "stale": False,
            "staleness_days": None, "error": msg}


def _row_for(path: Path, category: str, repo_root: Path, as_of: datetime) -> dict:
    try:
        rel = str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        rel = str(path)

    status, verdict, as_of_field, as_of_key, error, mtime = "OK", None, None, None, None, None
    try:
        # stat() lives INSIDE the guard: a file that vanishes between the scan and
        # this row (or that cannot be stat-ed) must become an UNREADABLE row, not a
        # FileNotFoundError that kills every other row in the manifest.
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        obj = _load(path)
        if obj is None:
            status = "EMPTY"
        else:
            verdict, as_of_field, as_of_key = _extract(obj)
    except Exception as e:  # fail-closed: never skip, never raise past this row
        status, error = "UNREADABLE", f"{type(e).__name__}: {e}"

    effective = _parse_dt(as_of_field)
    measured_at_source = f"field:{as_of_key}" if effective else ("mtime" if mtime else None)
    effective = effective or mtime
    staleness = (round((as_of - effective).total_seconds() / 86400.0, 2)
                 if effective is not None else None)
    # RT-7: a measurement time AFTER the reference "today" is not fresh evidence,
    # it is a broken clock or a self-serving stamp. Keep the declared value in the
    # row (that is the honest record) and name why it cannot be trusted.
    invalid = ("future" if staleness is not None and staleness < -_FUTURE_TOLERANCE_DAYS
               else None)
    return {"name": path.name, "source_path": rel, "category": category, "status": status,
            "verdict": verdict, "as_of_field": as_of_field,
            "mtime": mtime.isoformat() if mtime else None,
            "measured_at": effective.isoformat() if effective else None,
            "measured_at_source": measured_at_source,
            "measured_at_invalid": invalid, "stale": False,
            "staleness_days": staleness, "error": error}


class StaleEvidence(Exception):
    """Raised when a freshness claim lacks usable, timely evidence."""


def _stale_rows(manifest: dict, max_age_days: float,
                categories: tuple[str, ...] | None = None) -> List[dict]:
    offenders = []
    for row in manifest.get("rows", []):
        if categories is not None and row.get("category") not in categories:
            continue
        if (row.get("measured_at_source") in (None, "mtime")
                or row.get("measured_at") is None
                or row.get("measured_at_invalid") is not None
                or row.get("status") in ("UNREADABLE", "EMPTY")
                or row.get("staleness_days") is None
                or row["staleness_days"] > max_age_days):
            offenders.append(row)
    return offenders


def assert_fresh(manifest: dict, max_age_days: float,
                 categories: tuple[str, ...] | None = None) -> None:
    """Raise StaleEvidence when a requested claim lacks fresh measurement evidence."""
    offenders = _stale_rows(manifest, max_age_days, categories)
    if offenders:
        names = ", ".join(f"{row['name']} ({row['source_path']})" for row in offenders)
        raise StaleEvidence("stale evidence: " + names)


def build_manifest(repo_root: Path, as_of: Optional[datetime] = None,
                   exclude: Optional[Path] = None) -> dict:
    as_of = _as_utc(as_of) if as_of else datetime.now(timezone.utc)
    bad_dirs: List[str] = []
    found = _scan(repo_root, bad_dirs, exclude=exclude)
    rows = [_row_for(p, cat, repo_root, as_of) for p, cat in found]
    rows.extend(_dir_error_row(m) for m in bad_dirs)
    summary = {"total": len(rows)}
    for s in ("OK", "EMPTY", "UNREADABLE"):
        summary[s.lower()] = sum(1 for r in rows if r["status"] == s)
    return {"as_of": as_of.isoformat(), "repo_root": str(repo_root),
            "rows": rows, "summary": summary}


def render_table(manifest: dict) -> str:
    headers = ["NAME", "CATEGORY", "STATUS", "STALE", "VERDICT", "STALE_D", "PATH"]
    widths = [28, 20, 11, 5, 16, 8, 48]

    def fmt(vals):
        # PATH is last and is never truncated: clipping it to a fixed width made two
        # different artifacts under one long directory render as identical rows.
        cells = [str(v)[:w].ljust(w) for v, w in zip(vals[:-1], widths[:-1])]
        return " | ".join(cells + [str(vals[-1])])

    lines = [fmt(headers), "-+-".join("-" * w for w in widths)]
    for r in manifest["rows"]:
        stale = "-" if r["staleness_days"] is None else r["staleness_days"]
        invalid = r.get("measured_at_invalid")
        lines.append(fmt([r["name"], r["category"], r["status"],
                          (invalid or "YES").upper() if r.get("stale") else "-",
                          r["verdict"] or "-", stale, r["source_path"]]))
    s = manifest["summary"]
    # S45(b): the STALE count a human reads. It is a SEPARATE column from the
    # status counts now, so OK+EMPTY+UNREADABLE still sums to TOTAL.
    lines.append(f"TOTAL={s['total']} OK={s['ok']} EMPTY={s['empty']} "
                 f"UNREADABLE={s['unreadable']} STALE={s.get('stale', 0)}  "
                 f"as_of={manifest['as_of']}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Read-only eval-gate artifact manifest.")
    ap.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    ap.add_argument("--out", type=Path, default=None,
                    help="default: <repo-root>/data/cache/eval_gate/gate_manifest.json")
    ap.add_argument("--as-of", type=str, default=None, help="ISO datetime; default now (UTC)")
    ap.add_argument("--max-age-days", type=float, default=None,
                    help="opt-in claim gate; mark stale rows and exit 1")
    args = ap.parse_args(argv)

    as_of = None
    if args.as_of is not None:
        as_of = _parse_dt(args.as_of)
        if as_of is None:  # never silently fall back to now: every staleness would be wrong
            ap.error("--as-of is not an ISO datetime: " + repr(args.as_of))

    out = args.out or (args.repo_root / "data" / "cache" / "eval_gate" / "gate_manifest.json")
    # exclude our own output: otherwise run N+1 audits run N's manifest as a "ledger".
    manifest = build_manifest(args.repo_root, as_of=as_of, exclude=out)
    stale_rows = _stale_rows(manifest, args.max_age_days) if args.max_age_days is not None else []
    # S45(a): staleness is its own flag. Overwriting status with "STALE" ERASED
    # UNREADABLE and EMPTY -- an artifact nobody can parse then reported as merely
    # old, and gate_manifest_tool / harness_health_report counted zero unreadables.
    for row in stale_rows:
        row["stale"] = True
    if stale_rows:
        manifest["summary"]["stale"] = len(stale_rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
                   encoding="ascii")

    print(render_table(manifest))
    print("manifest written: " + str(out))
    return 1 if stale_rows or manifest["summary"]["unreadable"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
