"""Paper-desk host uptime from committed receipts (operations, not edge).

Run: python -m scripts.platformkit.eval_gate.desk_uptime_report [--check]
Writes the table between marker comments in docs/evidence/DESK_UPTIME_2026-10-20.md
and a JSON sidecar beside it. Stdlib only, read-only on docs/evidence/forward; reads only git-tracked files.
"""
import argparse
import json
import re
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

START, END = "2026-09-24", "2026-10-18"
CAP = "2026-10-19T00:00:00Z"  # END + 1 day midnight (exclusive upper bound)
TS_KEYS = ("started_at", "completed_at", "fill_ts", "record_ts", "selected_at", "started_utc", "settlement_ts", "close_ts")
SUBDIRS = ("schedules", "nights", "live_shadow", "paper_result")
# Self-reported by the owner/desk sessions in .planning/NOW.md (gitignored, read 2026-10-20).
OWNER_SLEEPS = [
    ("2026-10-08T01:57:00Z", "2026-10-08T14:24:00Z"),
    ("2026-10-10T01:56:00Z", "2026-10-12T13:26:00Z"),
    ("2026-10-13T00:56:00Z", "2026-10-13T20:01:00Z"),
    ("2026-10-14T03:26:00Z", "2026-10-14T15:30:00Z"),
    ("2026-10-17T00:26:00Z", "2026-10-19T14:40:00Z"),
]
BEGIN, FIN = "<!-- DESK_UPTIME:BEGIN -->", "<!-- DESK_UPTIME:END -->"
_TS = re.compile(r'"(%s)":\s*"(20\d\d-\d\d-\d\dT[0-9:.]+(?:Z|\+00:00))"' % "|".join(TS_KEYS))


def _t(s):
    s = re.sub(r"\.(\d+)", lambda m: "." + m.group(1)[:6].ljust(6, "0"), s.replace("Z", "+00:00"))
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def _days():
    d, e = date.fromisoformat(START), date.fromisoformat(END)
    while d <= e:
        yield d.isoformat()
        d += timedelta(days=1)


def _tracked(fwd):
    """Set of git-tracked files under fwd, so a clean clone reproduces the table; None if no git."""
    try:
        out = subprocess.run(["git", "ls-files", "-z", "."], cwd=fwd, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {(fwd / x).resolve() for x in out.decode("utf-8").split("\0") if x} or None


def collect(fwd):
    fwd = Path(fwd)
    tr = _tracked(fwd)

    def ok(f):
        return tr is None or f.resolve() in tr

    stamps = []
    for sub in SUBDIRS:
        for f in sorted((fwd / sub).glob("*.json")):
            if ".superseded" in f.name or not ok(f):
                continue
            stamps += [_t(m.group(2)) for m in _TS.finditer(f.read_text(encoding="utf-8"))]
    lo, hi = _t(START + "T00:00:00Z"), _t(CAP)
    ignored = sorted({s for s in stamps if not lo <= s < hi})
    stamps = sorted({s for s in stamps if lo <= s < hi})
    gaps = sorted(((b - a).total_seconds() / 3600, a, b) for a, b in zip(stamps, stamps[1:]))[::-1]
    rows = []
    for d in _days():
        sched = fwd / "schedules" / f"{d}_maker_forward.json"
        games = set()
        has = sched.exists() and ok(sched)
        if has:
            games = {r.get("game_id") for r in json.loads(sched.read_text(encoding="utf-8"))}
        night = fwd / "nights" / f"{d}.json"
        n = json.loads(night.read_text(encoding="utf-8")) if night.exists() and ok(night) else None
        rows.append({"date": d, "scheduled": has, "served": len(games),
                     "night": n["status"] if n else None,
                     "reasons": list(n.get("reasons") or []) if n else [],
                     "attempt_file": ok(fwd / "night_attempts" / f"{d}.json") and (fwd / "night_attempts" / f"{d}.json").exists()})
    sleeps = [{"start": a, "end": b, "hours": round((_t(b) - _t(a)).total_seconds() / 3600, 1)}
              for a, b in OWNER_SLEEPS]
    reasons = {}
    for r in rows:
        for x in r["reasons"]:
            reasons[x] = reasons.get(x, 0) + 1
    sc = [r for r in rows if r["scheduled"]]
    sv = [r for r in rows if r["served"] > 0]
    nt = [r for r in rows if r["night"]]
    spells = [{"start": _iso(a), "end": _iso(b), "hours": round(h, 1)} for h, a, b in gaps[:2]]
    return {"window": [START, END], "days": len(rows), "scheduled": len(sc), "served": len(sv),
            "scored": len(nt), "scored_share": round(len(nt) / len(rows), 3),
            "scored_complete": sum(r["night"] == "COMPLETE" for r in rows),
            "scored_partial": sum(r["night"] == "PARTIAL" for r in rows),
            "dark_spells": spells, "partial_reasons": dict(sorted(reasons.items())),
            "no_receipt_days": len(rows) - len(nt), "stamps": len(stamps),
            "ignored_out_of_window": sorted({_iso(x) for x in ignored}),
            "owner_sleeps_self_reported": sleeps, "table": rows}


def render(r):
    L = ["| date | scheduled | games served | night receipt | partial reasons | attempt file |",
         "|---|---|---|---|---|---|"]
    for x in r["table"]:
        L.append("| %s | %s | %d | %s | %s | %s |" % (
            x["date"], "yes" if x["scheduled"] else "no", x["served"], x["night"] or "none",
            ", ".join(x["reasons"]) or "-", "yes" if x["attempt_file"] else "no"))
    L += ["", "Summary (%s to %s, %d days):" % (r["window"][0], r["window"][1], r["days"]), "",
          "- days scheduled: %d" % r["scheduled"], "- days served (>= 1 game): %d" % r["served"],
          "- scored nights: %d (COMPLETE %d, PARTIAL %d)" % (r["scored"], r["scored_complete"], r["scored_partial"]),
          "- scored-night share: %.1f%% (%d of %d days)" % (100 * r["scored_share"], r["scored"], r["days"]),
          "- days with no night receipt: %d" % r["no_receipt_days"]]
    for i, s in enumerate(r["dark_spells"]):
        L.append("- dark spell %d: %s to %s = %.1f h" % (i + 1, s["start"], s["end"], s["hours"]))
    L.append("- partial reasons on scored nights: " + (", ".join(
        "%s %d" % kv for kv in r["partial_reasons"].items()) or "none"))
    L.append("- ignored out-of-window timestamps (outside %sT00:00Z to %s): %s" % (
        r["window"][0], CAP[:16] + "Z", ", ".join(r["ignored_out_of_window"]) or "none"))
    L += ["", "Owner-reported sleep windows (self-reported, from .planning/NOW.md; not receipt-derived):", ""]
    L += ["- %s to %s = %.1f h" % (s["start"], s["end"], s["hours"]) for s in r["owner_sleeps_self_reported"]]
    return "\n".join(L)


def write(root):
    root = Path(root)
    r = collect(root / "docs/evidence/forward")
    md = root / "docs/evidence/DESK_UPTIME_2026-10-20.md"
    block = BEGIN + "\n" + render(r) + "\n" + FIN
    txt = md.read_text(encoding="utf-8") if md.exists() else block + "\n"
    if BEGIN in txt:
        txt = re.sub(re.escape(BEGIN) + r".*?" + re.escape(FIN), lambda m: block, txt, flags=re.S)
    else:
        txt += "\n" + block + "\n"
    md.write_text(txt, encoding="utf-8", newline="\n")
    md.with_suffix(".json").write_text(json.dumps(r, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return r


def check(root):
    """Recompute from the (git-tracked) receipts and compare to the written md block + JSON."""
    root = Path(root)
    md = root / "docs/evidence/DESK_UPTIME_2026-10-20.md"
    if not md.is_file() or not md.with_suffix(".json").is_file():
        return False
    r = collect(root / "docs/evidence/forward")
    want_json = json.dumps(r, indent=1, sort_keys=True) + "\n"
    m = re.search(re.escape(BEGIN) + r"\n(.*?)\n" + re.escape(FIN), md.read_text(encoding="utf-8"), re.S)
    return bool(m) and m.group(1) == render(r) and md.with_suffix(".json").read_text(encoding="utf-8") == want_json


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        ok = check(a.repo_root)
        print("MATCH" if ok else "MISMATCH")
        raise SystemExit(0 if ok else 1)
    r = write(a.repo_root)
    print(render(r))
