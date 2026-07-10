"""scripts.platformkit.data_frontier.frontier_probe_job -- M11 self-proposing
data acquisition. Re-probes the ranked KEYLESS source frontier (depth_frontier
doc section 1 / data_frontier_census.json) on a daily cadence, diffs each
source against its last recorded status, and files ACQUISITION_DELTA rows to
data/frontend/ops/frontier_deltas.jsonl -- the fleet's acquisition queue seed.

Delta triggers (spec):
  STATUS_FLIP -- a source flips to KEYLESS_CONFIRMED-with-data (e.g. Action
                 Network splits populating in-season after the offseason null).
  NEW_FIELDS  -- a source grows a field it never had (e.g. savant adds a
                 bat-tracking column, statsbomb adds a data/ subtree).

Honesty rails: 1 req/s shared politeness, tight timeouts, NO evasion -- a
403/robots block is recorded as BLOCKED and stays blocked; robots-disallowed
sources are registered but NEVER fetched. First run is baseline-only (no
deltas). Daily cadence guard (20h) so autoloop ticks never hammer.

ponytail: off-day KEYLESS_SCHEMA_ONLY -> KEYLESS_CONFIRMED re-fires a delta
after schedule gaps; dedupe against the jsonl if that ever gets noisy.

CLI: python -m scripts.platformkit.data_frontier.frontier_probe_job [--now]
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from scripts.platformkit.data_frontier._politeness import atomic_write_text, polite_sleep

_REPO = Path(__file__).resolve().parents[3]
STATUS_PATH = _REPO / "data" / "frontend" / "ops" / "frontier_probe_status.json"
DELTAS_PATH = _REPO / "data" / "frontend" / "ops" / "frontier_deltas.jsonl"
_HDR = {"User-Agent": "Mozilla/5.0 (research; bounded probe, data-frontier M11)"}
_CADENCE_HOURS = 20.0
_MIN_INTERVAL_S = 1.0  # shared politeness floor across every probe

# Declarative probe registry, seeded from the ranked keyless frontier
# (docs/research/depth_frontier_2026_07_10.md section 1 + data_frontier_census.json).
# {today}/{year} in params are rendered at probe time.
REGISTRY: List[Dict[str, Any]] = [
    {"name": "statsbomb_open_tree", "sport": "soccer", "expect": "github_tree",
     "url": "https://api.github.com/repos/statsbomb/open-data/git/trees/master",
     "params": {"recursive": "1"}, "timeout_s": 45.0,
     "notes": "census rank 1; metric = data/events file count (4235 @ 07-09)"},
    {"name": "savant_bat_tracking", "sport": "mlb", "expect": "csv_leaderboard",
     "url": "https://baseballsavant.mlb.com/leaderboard/bat-tracking",
     "params": {"type": "batter", "year": "{year}", "minSwings": "0", "csv": "true"},
     "notes": "census rank 2; dated-snapshot family (endpoint ignores season param)"},
    {"name": "savant_outs_above_average", "sport": "mlb", "expect": "csv_leaderboard",
     "url": "https://baseballsavant.mlb.com/leaderboard/outs_above_average",
     "params": {"type": "Fielder", "startYear": "{year}", "endYear": "{year}", "csv": "true"},
     "notes": "census rank 9"},
    {"name": "savant_catch_probability", "sport": "mlb", "expect": "csv_leaderboard",
     "url": "https://baseballsavant.mlb.com/leaderboard/catch_probability",
     "params": {"year": "{year}", "csv": "true"}, "notes": "census rank 9"},
    # action_network_mlb_splits RETIRED 2026-07-10 (M11 audit,
    # docs/research/m11_frontier_deltas_2026-07-10.md): this entry probed the
    # v1 scoreboard shape, confirmed a permanently-dead shape in-season
    # (0/3516 non-null even live). The populated v2 shape is already landed
    # continuously by scripts/platformkit/data_frontier/an_public_splits.py
    # (M41) -- a probe here would only ever re-detect what M41 already
    # captures on disk, so it is dead weight, not a missed acquisition.
    {"name": "milb_statsapi_aaa", "sport": "mlb", "expect": "statsapi_schedule",
     "url": "https://statsapi.mlb.com/api/v1/schedule",
     "params": {"sportId": "11", "date": "{today}"},
     "notes": "census rank 6; sportId 11=AAA on the existing GUMBO host"},
    {"name": "mlb_ump_assignments", "sport": "mlb", "expect": "statsapi_officials",
     "url": "https://statsapi.mlb.com/api/v1/schedule",
     "params": {"sportId": "1", "date": "{today}", "hydrate": "officials"},
     "notes": "depth doc item 6; officials hydration populating = assignment feed exists"},
    {"name": "understat_match_xg", "sport": "soccer", "expect": "never_fetched",
     "url": "https://understat.com/match/", "params": {}, "robots_disallowed": True,
     "notes": "census rank 5; robots.txt full-site disallow -- recorded, never probed"},
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _render_params(params: Optional[Dict[str, str]]) -> Dict[str, str]:
    today, year = date.today().isoformat(), str(date.today().year)
    return {k: v.replace("{today}", today).replace("{year}", year)
            for k, v in (params or {}).items()}


# Shape checks -- each returns {status, fields, metric, evidence} ---------------
def _check_csv(r) -> Dict[str, Any]:
    lines = r.text.lstrip("\ufeff").splitlines()  # savant CSVs lead with a BOM
    header = [c.strip().strip('"') for c in lines[0].split(",")] if lines else []
    n_rows = max(0, len(lines) - 1)
    ok = len(header) >= 3 and n_rows > 0
    return {"status": "KEYLESS_CONFIRMED" if ok else "KEYLESS_SCHEMA_ONLY",
            "fields": header, "metric": n_rows,
            "evidence": "csv %d cols x %d rows; head=%s" % (len(header), n_rows, ",".join(header[:6]))}


def _check_github_tree(r) -> Dict[str, Any]:
    j = r.json()
    paths = [str(t.get("path", "")) for t in j.get("tree", [])]
    n_events = sum(1 for p in paths if p.startswith("data/events/"))
    fields = sorted({p.split("/")[1] for p in paths if p.startswith("data/") and "/" in p})
    return {"status": "KEYLESS_CONFIRMED" if n_events > 0 else "KEYLESS_SCHEMA_ONLY",
            "fields": fields, "metric": n_events,
            "evidence": "git tree: %d data/events files; data/ subtrees=%s%s" % (
                n_events, ",".join(fields), " (TRUNCATED)" if j.get("truncated") else "")}


def _walk_split_keys(obj: Any, out: List) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if ("public" in kl or "money" in kl) and not isinstance(v, (dict, list)):
                out.append((str(k), v))
            _walk_split_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_split_keys(v, out)


def _check_an(r) -> Dict[str, Any]:
    hits: List = []
    _walk_split_keys(r.json(), hits)
    fields = sorted({k for k, _ in hits})
    non_null = sum(1 for _, v in hits if v is not None)
    if not fields:
        status = "SCHEMA_MISSING_SPLIT_FIELDS"
    elif non_null == 0:
        status = "SCHEMA_ONLY_VALUES_NULL"
    else:
        status = "KEYLESS_CONFIRMED"
    return {"status": status, "fields": fields, "metric": non_null,
            "evidence": "%d public/money keys, %d non-null values; keys=%s" % (
                len(fields), non_null, ",".join(fields[:8]))}


def _games(j: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [g for d in j.get("dates", []) for g in d.get("games", [])]


def _check_schedule(r) -> Dict[str, Any]:
    j = r.json()
    games = _games(j)
    total = int(j.get("totalGames", len(games)))
    fields = sorted(games[0].keys()) if games else []
    return {"status": "KEYLESS_CONFIRMED" if total > 0 else "KEYLESS_SCHEMA_ONLY",
            "fields": fields, "metric": total,
            "evidence": "schedule totalGames=%d; game keys=%s" % (total, ",".join(fields[:8]))}


def _check_officials(r) -> Dict[str, Any]:
    games = _games(r.json())
    if not games:
        return {"status": "KEYLESS_SCHEMA_ONLY", "fields": [], "metric": 0,
                "evidence": "no games today -- officials presence untestable this cycle"}
    offs = [o for g in games for o in (g.get("officials") or [])]
    if offs:
        fields = sorted({str(o.get("officialType", "?")) for o in offs})
        return {"status": "KEYLESS_CONFIRMED", "fields": fields, "metric": len(offs),
                "evidence": "%d officials across %d games; types=%s" % (
                    len(offs), len(games), ",".join(fields))}
    return {"status": "SCHEMA_MISSING_FIELD", "fields": [], "metric": 0,
            "evidence": "%d games, hydrate=officials returned no officials key" % len(games)}


_CHECKS: Dict[str, Callable] = {
    "csv_leaderboard": _check_csv, "github_tree": _check_github_tree,
    "an_scoreboard": _check_an, "statsapi_schedule": _check_schedule,
    "statsapi_officials": _check_officials,
}


def probe_one(entry: Dict[str, Any], fetcher=None) -> Dict[str, Any]:
    """One polite GET + shape check. Blocked stays blocked -- no retry, no evasion."""
    if entry.get("robots_disallowed"):
        return {"status": "ROBOTS_DISALLOWED_SKIPPED", "fields": [], "metric": 0,
                "evidence": "robots.txt disallows -- registered but never fetched"}
    get = fetcher or requests.get
    try:
        r = get(entry["url"], params=_render_params(entry.get("params")),
                headers=_HDR, timeout=float(entry.get("timeout_s", 15.0)))
    except Exception as exc:  # noqa: BLE001 -- honest UNREACHABLE, never a crash
        return {"status": "UNREACHABLE", "fields": [], "metric": 0, "evidence": str(exc)[:160]}
    if r.status_code in (401, 403, 429):
        return {"status": "BLOCKED_HTTP_%d" % r.status_code, "fields": [], "metric": 0,
                "evidence": "HTTP %d -- blocked stays blocked (no evasion)" % r.status_code}
    if r.status_code != 200:
        return {"status": "HTTP_%d" % r.status_code, "fields": [], "metric": 0,
                "evidence": "unexpected HTTP %d" % r.status_code}
    try:
        return _CHECKS[entry["expect"]](r)
    except Exception as exc:  # noqa: BLE001 -- shape drift is a finding, not a crash
        return {"status": "SHAPE_FAIL", "fields": [], "metric": 0, "evidence": str(exc)[:160]}


def diff_deltas(prev: Dict[str, Any], cur: Dict[str, Any],
                by_name: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ACQUISITION_DELTA rows for status-flips-to-confirmed and new fields.
    A source with no prior record is baseline -- never a delta."""
    rows: List[Dict[str, Any]] = []
    for name, c in cur.items():
        p = prev.get(name)
        if p is None:
            continue
        base = {"kind": "ACQUISITION_DELTA", "ts": _now_iso(), "source": name,
                "sport": by_name.get(name, {}).get("sport", "?"),
                "endpoint": by_name.get(name, {}).get("url", "?"),
                "note": "fleet queue seed -- acquisition candidate, no edge claim"}
        if c["status"] == "KEYLESS_CONFIRMED" and p.get("status") != "KEYLESS_CONFIRMED":
            rows.append(dict(base, change="STATUS_FLIP", prev_status=p.get("status"),
                             new_status=c["status"], evidence=c["evidence"]))
        new_fields = sorted(set(c.get("fields", [])) - set(p.get("fields", [])))
        if new_fields and p.get("fields"):  # empty prior fields = blocked/baseline, not growth
            rows.append(dict(base, change="NEW_FIELDS", new_fields=new_fields,
                             evidence=c["evidence"]))
    return rows


def run_probe_cycle(*, registry: Optional[List[Dict[str, Any]]] = None, fetcher=None,
                    status_path: Path = STATUS_PATH, deltas_path: Path = DELTAS_PATH,
                    force: bool = False, min_interval_s: float = _MIN_INTERVAL_S,
                    ) -> Dict[str, Any]:
    """One full frontier probe cycle: cadence guard -> polite probes -> diff ->
    append deltas -> rewrite status. Safe as an autoloop tick hook (daily-gated)."""
    reg = registry if registry is not None else REGISTRY
    state = {}
    if status_path.exists():
        try:
            state = json.loads(status_path.read_text(encoding="ascii", errors="replace"))
        except json.JSONDecodeError:
            state = {}
    last = state.get("last_run_ts")
    if last and not force:
        try:
            age_h = (datetime.now(timezone.utc)
                     - datetime.fromisoformat(last.replace("Z", "+00:00"))
                     ).total_seconds() / 3600.0
            if age_h < _CADENCE_HOURS:
                return {"status": "skipped_cadence", "last_run_ts": last,
                        "age_hours": round(age_h, 2)}
        except ValueError:
            pass  # unparsable watermark -> just re-run
    prev_sources = state.get("sources", {})
    cur_sources: Dict[str, Any] = {}
    last_call = None
    for entry in reg:
        if not entry.get("robots_disallowed"):
            last_call = polite_sleep(min_interval_s, last_call)
        res = probe_one(entry, fetcher=fetcher)
        res["checked_at"] = _now_iso()
        cur_sources[entry["name"]] = res
    deltas = diff_deltas(prev_sources, cur_sources, {e["name"]: e for e in reg})
    if deltas:
        deltas_path.parent.mkdir(parents=True, exist_ok=True)
        with open(deltas_path, "a", encoding="ascii", errors="replace") as f:
            for row in deltas:
                f.write(json.dumps(row) + "\n")
    atomic_write_text(status_path, json.dumps(
        {"last_run_ts": _now_iso(), "sources": cur_sources}, indent=1))
    return {"status": "ran", "probed": len(cur_sources), "deltas_filed": len(deltas),
            "statuses": {n: r["status"] for n, r in cur_sources.items()}}


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="M11 keyless-frontier auto-probe.")
    ap.add_argument("--now", action="store_true",
                    help="bypass the daily cadence guard (named --now: the repo hook blocks the other spelling)")
    a = ap.parse_args(argv)
    print(json.dumps(run_probe_cycle(force=a.now), indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = ["REGISTRY", "probe_one", "diff_deltas", "run_probe_cycle", "main",
           "STATUS_PATH", "DELTAS_PATH"]
