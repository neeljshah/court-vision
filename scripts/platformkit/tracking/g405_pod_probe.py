"""G405 pod-side discovery pass and read-only format probes (no download).

Subcommands:
  discover <outdir>            frozen-recipe search pass; writes population.jsonl
  probe    <outdir> <draw.csv> one -F listing plus one -J metadata per drawn id

Never writes the live feeder queue, never downloads media, never enqueues.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RECIPE = Path("/workspace/feeder/discover_sources.py")
LEDGER = Path("/workspace/data/tracking/track_daemon_ledger.jsonl")
SOURCES = Path("/workspace/feeder/sources.txt")
DISCOVER_LOG = Path("/workspace/feeder/discover.log")
DENY_PATH = Path("/workspace/feeder/deny.txt")
SEARCH_N = 15
MIN_DURATION_S = 2400
NL = chr(10)  # LF terminator for the jsonl writes
MAX_RUN_WIDE = 30  # discover_loop.sh passes 30; the live MAX is run-wide, not per query
LIST_TIMEOUT, META_TIMEOUT, SPACING_S = 120, 60, 7
REDACT = ("url", "fragments", "http_headers", "manifest_url", "fragment_base_url", "cookies")
GAME_ID_RE = re.compile(r"^(?:[A-Za-z0-9_-]+-)?([A-Za-z0-9_-]{11})_s\d+$")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def frozen_queries(recipe: Path = RECIPE) -> list[tuple[str, str, str]]:
    """Read the live QUERIES literal without executing the recipe module."""
    tree = ast.parse(recipe.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "QUERIES" for t in node.targets):
            return [tuple(str(x) for x in row) for row in ast.literal_eval(node.value)]
    raise ValueError("queries-not-found")


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []


def eligibility_sets() -> dict:
    """Reproduce the live discover_sources.py seen()/DENY inputs; nothing is written."""
    ledger = set()
    for line in _lines(LEDGER):
        try:
            game_id = json.loads(line).get("game_id", "")
        except ValueError:
            continue
        match = GAME_ID_RE.match(str(game_id))
        if match:
            ledger.add(match.group(1))
    queue = {parts[2] for parts in (l.split() for l in _lines(SOURCES) if not l.startswith("#"))
             if len(parts) >= 3}
    log = {parts[3] for parts in (l.split() for l in _lines(DISCOVER_LOG))
           if len(parts) >= 4 and parts[0] == "NEW"}
    deny = {l.split()[0] for l in _lines(DENY_PATH) if l.strip() and not l.startswith("#")}
    seen = ledger | queue
    return {"seen": set(seen), "deny": deny, "ledger": ledger, "queue": queue,
            "log_only_not_in_seen": log - seen, "max_run_wide": MAX_RUN_WIDE,
            "counts": {"ledger_ids": len(ledger), "sources_txt_ids": len(queue),
                       "live_seen_union_ledger_plus_sources_txt": len(seen),
                       "deny_ids": len(deny), "min_duration_s": MIN_DURATION_S,
                       "max_run_wide": MAX_RUN_WIDE,
                       "discover_log_ids_observed_but_NOT_gated": len(log),
                       "discover_log_only_ids_left_eligible": len(log - seen)},
            "inputs": {p.name: {"path": str(p), "exists": p.exists(),
                                "sha256": _sha(p) if p.exists() else "absent",
                                "bytes": p.stat().st_size if p.exists() else 0}
                       for p in (LEDGER, SOURCES, DISCOVER_LOG, DENY_PATH)}}


def gate_reason(source_id: str, duration_s: int, gate: dict) -> str | None:
    """Return the live per-row reject reason in discover_sources.py:53 order, else None."""
    if not source_id:
        return "no_id"
    if source_id in gate["seen"]:
        return "seen_in_ledger_or_queue"
    if source_id in gate["deny"]:
        return "deny_list"
    if duration_s < MIN_DURATION_S:
        return "duration_lt_%d" % MIN_DURATION_S
    return None


def write_seen_set(outdir: Path, gate: dict) -> None:
    """Archive the exact pre-run gate membership so the draw rebuilds from evidence."""
    rows = ([{"id": i, "member_of": "ledger"} for i in sorted(gate["ledger"])]
            + [{"id": i, "member_of": "sources_txt_queue"} for i in sorted(gate["queue"])]
            + [{"id": i, "member_of": "deny_list"} for i in sorted(gate["deny"])]
            + [{"id": i, "member_of": "discover_log_only_NOT_in_live_seen"}
               for i in sorted(gate["log_only_not_in_seen"])])
    (outdir / "seen_set.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + NL for r in rows), encoding="utf-8")


def _run(argv: list[str], timeout: int) -> dict[str, object]:
    start = utc()
    began = time.time()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        out, err, code, timed = proc.stdout, proc.stderr, proc.returncode, False
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        code, timed = -9, True
    return {"argv": argv, "start_utc": start, "end_utc": utc(),
            "elapsed_s": round(time.time() - began, 3), "returncode": code,
            "timed_out": timed, "stdout": out, "stderr": err}


def discover(outdir: Path) -> int:
    """Replay the live recipe's gate and run-wide cap over one bounded search pass."""
    outdir.mkdir(parents=True, exist_ok=True)
    queries = frozen_queries()
    gate = eligibility_sets()
    write_seen_set(outdir, gate)
    receipts, rows, everything, order, reasons, added, cap_at = [], [], [], 0, {}, 0, None
    for sport, tag, query in queries:
        res = _run(["yt-dlp", "--flat-playlist", "-j", "--no-warnings",
                    "ytsearch%d:%s" % (SEARCH_N, query)], LIST_TIMEOUT)
        stdout = str(res.pop("stdout"))
        kept = 0
        for line in stdout.splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            sid, dur = item.get("id") or "", int(item.get("duration") or 0)
            row = {"order": order, "competition": sport, "tag": tag, "query": query,
                   "source_id": sid, "ytid": sid, "duration_s": dur, "dur": dur,
                   "title": (item.get("title") or "")[:60],
                   "discovered_at": res["start_utc"]}
            reason = ("after_run_wide_cap_not_reached_by_live_run" if added >= MAX_RUN_WIDE
                      else gate_reason(sid, dur, gate))
            reasons[reason or "eligible"] = reasons.get(reason or "eligible", 0) + 1
            everything.append(dict(row, eligible=reason is None, gate_reason=reason or ""))
            order += 1
            if reason is None:
                gate["seen"].add(sid)  # live line 54: S.add(vid) dedupes within the run
                added, kept = added + 1, kept + 1
                rows.append(row)
                if added >= MAX_RUN_WIDE and cap_at is None:
                    cap_at = {"competition": sport, "query": query, "admitted": added,
                              "returned_row_order": row["order"]}
        res.update({"sport": sport, "tag": tag, "query": query,
                    "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
                    "stdout_lines": len(stdout.splitlines()), "eligible_rows": kept,
                    "stderr": str(res["stderr"])[-400:]})
        receipts.append(res)
        time.sleep(3)
    (outdir / "population.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + NL for r in rows), encoding="utf-8")
    (outdir / "population_all_returned.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + NL for r in everything), encoding="utf-8")
    (outdir / "discovery_receipts.json").write_text(
        json.dumps({"recipe": str(RECIPE), "recipe_sha256": _sha(RECIPE),
                    "search_n": SEARCH_N, "queries": queries, "runs": receipts,
                    "eligibility_gate": {
                        "applied_before_the_draw": True,
                        "matches_archived_live_recipe": True,
                        "criteria": ("discover_sources.py:53 order -- empty id, seen (ledger "
                                     "game_id | sources.txt), deny.txt, duration >= %d s; then "
                                     "line 54 S.add(vid) and the RUN-WIDE cap MAX=%d"
                                     % (MIN_DURATION_S, MAX_RUN_WIDE)),
                        "seen_is_ledger_plus_sources_txt_only": True,
                        "discover_log_is_recorded_but_never_gated": True,
                        "run_wide_cap": MAX_RUN_WIDE, "run_wide_cap_reached_at": cap_at,
                        "queries_after_the_cap_searched_for_archive_only": True,
                        "seen_set_file": "seen_set.jsonl",
                        "counts": gate["counts"], "inputs": gate["inputs"],
                        "reason_tally": reasons,
                        "returned_rows": len(everything), "eligible_rows": len(rows)}},
                   indent=1, sort_keys=True), encoding="utf-8")
    uniq = len({r["source_id"] for r in rows if r["source_id"]})
    print("discover returned=%d admitted=%d unique_admitted=%d queries=%d cap=%s"
          % (len(everything), len(rows), uniq, len(queries), added >= MAX_RUN_WIDE))
    return 0


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _redact(meta: dict) -> dict:
    """Drop signed access material while keeping every format record."""
    formats = []
    for fmt in meta.get("formats") or []:
        formats.append({k: v for k, v in fmt.items() if k not in REDACT})
    return {"id": meta.get("id"), "duration": meta.get("duration"),
            "extractor": meta.get("extractor"), "redacted_keys": list(REDACT),
            "format_count": len(formats), "formats": formats}


def _dump(outdir: Path, receipts: list) -> None:
    """Persist receipts after every probe so a later fault cannot orphan them."""
    (outdir / "probe_receipts.json").write_text(
        json.dumps(receipts, indent=1, sort_keys=True), encoding="utf-8")


def probe(outdir: Path, draw_csv: Path) -> int:
    """One -F listing and one -J metadata request per drawn source id."""
    raw, meta_dir = outdir / "raw_formats", outdir / "metadata"
    raw.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    with open(draw_csv, encoding="utf-8") as handle:
        drawn = list(csv.DictReader(handle))
    receipts = []
    for row in drawn:
        sid = row["source_id"]
        url = "https://www.youtube.com/watch?v=%s" % sid
        listing = _run(["yt-dlp", "-F", "--no-playlist", "--no-warnings", "--", url], LIST_TIMEOUT)
        text = str(listing.pop("stdout"))
        (raw / ("%s.txt" % sid)).write_text(text, encoding="utf-8")
        listing.update({"stage": "listing", "source_id": sid, "draw_j": row["draw_j"],
                        "stdout_bytes": len(text.encode()),
                        "stdout_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "stderr": str(listing["stderr"])[-600:]})
        receipts.append(listing)
        _dump(outdir, receipts)
        time.sleep(SPACING_S)
        md = _run(["yt-dlp", "-J", "--no-playlist", "--no-warnings", "--skip-download", "--", url],
                  META_TIMEOUT)
        blob = str(md.pop("stdout"))
        pre = hashlib.sha256(blob.encode()).hexdigest()
        try:
            parsed = json.loads(blob) if blob.strip() else None
        except ValueError:
            parsed = "unparsable"
        payload = _redact(parsed) if isinstance(parsed, dict) else {
            "formats": [], "error": "empty" if parsed is None else "non-object-json"}
        body = json.dumps(payload, indent=1, sort_keys=True)
        (meta_dir / ("%s.json" % sid)).write_text(body, encoding="utf-8")
        md.update({"stage": "metadata", "source_id": sid, "draw_j": row["draw_j"],
                   "stdout_bytes": len(blob.encode()), "pre_redaction_sha256": pre,
                   "post_redaction_sha256": hashlib.sha256(body.encode()).hexdigest(),
                   "format_count": len(payload.get("formats") or []),
                   "stderr": str(md["stderr"])[-600:]})
        receipts.append(md)
        _dump(outdir, receipts)
        time.sleep(SPACING_S)
        print("probed %s j=%s list_rc=%s meta_rc=%s formats=%d"
              % (sid, row["draw_j"], listing["returncode"], md["returncode"], md["format_count"]))
    _dump(outdir, receipts)
    print("probe done sources=%d receipts=%d" % (len(drawn), len(receipts)))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "discover":
        return discover(Path(argv[2]))
    if len(argv) >= 4 and argv[1] == "probe":
        return probe(Path(argv[2]), Path(argv[3]))
    print("usage: g405_pod_probe.py discover <outdir> | probe <outdir> <draw.csv>")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
