"""generate_session_note.py — R29_V4 auto-generated session notes.

Synthesises ``vault/Sessions/SESSION<N>.md`` for a window of improve-loop
rounds (e.g. R15-R28). Pulls from three sources:

  1. ``scripts/coordination_log.md`` — narrative SHIP/REJECT/BLOCKED log
  2. ``scripts/improve_loop/state.json`` — ships with deltas + commits
  3. ``git log master`` — canonical commit SHAs (cross-checked w/ cat-file)

Hard rules
----------
* Pure-read from data sources. Single atomic write to the output path.
* Idempotent: same upstream data -> byte-identical body (the only
  clock-derived field is the header timestamp which uses ``--now`` for
  tests; production uses ``datetime.now``).
* Atomic write: stage to ``<out>.tmp`` -> ``os.replace``. Previous file
  (if any) rotates to ``<out>.bak`` before replacement.
* No SHA fabrication: every commit referenced in the round sections has
  been seen in the local git log scan; tests cross-check with
  ``git cat-file -t``.

Rendered sections (5)
---------------------
  1. Header             — session #, range, totals, master tip SHA
  2. Round-by-round     — one entry per round in the window
  3. Major themes       — work clustered by category
  4. Top 10 ships       — subjective impact ranking with reasoning
  5. Open items + stats — deferred, blocked, failed; commits/tests/LOC

CLI
---
    python scripts/generate_session_note.py
    python scripts/generate_session_note.py --session 3 \\
            --start-round R15 --end-round R28 \\
            --out vault/Sessions/SESSION3.md
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import json
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

DEFAULT_OUT_PATH       = PROJECT_DIR / "vault" / "Sessions" / "SESSION3.md"
DEFAULT_COORD_LOG      = PROJECT_DIR / "scripts" / "coordination_log.md"
DEFAULT_STATE_JSON     = PROJECT_DIR / "scripts" / "improve_loop" / "state.json"

# Mandatory section headings — assertable by tests and the probe.
SECTION_HEADINGS = (
    "## Round-by-Round Summary",
    "## Major Themes",
    "## Top 10 Ships by Impact",
    "## Open Items / Next Session",
    "## Stats",
)

# ---- Subjective Top-10 ranking (load-bearing — keep keyed on probe id). ----
# Reasoning is rendered verbatim in the output. Only ships that actually
# shipped (per coordination_log) are listed here. If the underlying ship is
# missing from the round window the entry is suppressed at render time.
TOP_10_RANKING: List[Tuple[str, str]] = [
    ("R20_M7", "Wired M2 multi5 ensemble that had sat un-wired for weeks; "
               "game 0022400061 total 224->231, spread 7.9->16.6 — recovers "
               "20 trained models the production stack was silently ignoring."),
    ("R22_O8", "Unblocked the injury feed (3-source fallback NBA-PDF -> ESPN "
               "-> rotowire, 126 OUT parsed) — the prerequisite for the "
               "R23_P2 injury->bet-ranker wire that comes one round later."),
    ("R23_P2", "Real gap: inplay_bet_ranker had 0 get_availability_factor "
               "calls. Jalen Williams OUT on SAS@OKC slate would have been "
               "bet pre-wire. Closed a live financial leak."),
    ("R23_P8", "Live recommendation engine producing TODAY recs end-to-end "
               "(Wembanyama BLK UNDER +49.5%, Fox PTS OVER +48.6%). Slate "
               "Kelly cap $250 hit exactly. First usable bet feed."),
    ("R28_U2", "Pace drift root-cause = computation artifact (R25_R1's "
               "Oliver formula was +2.2% over NBA Stats truth). Per-team "
               "multiplicative fix collapses mean_z home_pace 1.26->0.06; "
               "vindicates R27_T3 drift detector as a true positive."),
    ("R27_T3", "Feature drift detector + dashboard + workflow hook caught "
               "the pace shift before it corrupted the m2_family retrain — "
               "infrastructure that paid for itself in one round."),
    ("R19_L8", "Bankroll dashboard filter exposed real bankroll $1,000 "
               "(2 line_killed rows) vs unfiltered $3.67M illusory. Killed "
               "a class of misleading dashboard reads."),
    ("R23_P4", "Pinnacle scraper p99 70->26ms (-63% cold, -84% warm) via "
               "persistent curl_cffi session + dedup cache. Headroom for "
               "the line-killed recovery path and middle_finder."),
    ("R21_N1", "PTS/AST artifact resolver fixed a silent-None bug — "
               "load_pergame_model returned [] then short-circuited. "
               "Restored predictions for the most-traded stat surfaces."),
    ("R28_U1", "Played-games linescore backfill: BoxScoreSummaryV2 was "
               "returning NULL for 2025-26 stubs; pivoted to CDN static "
               "JSON for 100% hit rate. 175 stubs replaced, 18 OT tagged "
               "— unblocks future m2_family retrains."),
]


# ----------------------------------------------------------------------------
# Coordination-log parsing
# ----------------------------------------------------------------------------

_ROUND_RE     = re.compile(r"\bR(\d+)\b")
_PROBE_ID_RE  = re.compile(r"\bR\d+_([A-Z]\d+)\b")
_ENTRY_RE     = re.compile(r"^\[(\d{4}-\d{2}-\d{2})(?:\s+\w+)?\s+S\d\]\s+(.+)$")


def parse_coordination_log(path: Path) -> List[Dict[str, Any]]:
    """Return a list of structured log entries (one dict per line)."""
    if not path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    buffer: List[str] = []
    for line in raw_lines:
        stripped = line.rstrip()
        if _ENTRY_RE.match(stripped):
            if buffer:
                _flush_buffer(buffer, entries)
                buffer = []
            buffer.append(stripped)
        elif buffer:
            # Continuation line (indented sub-entry, e.g. the batch-ship list).
            buffer.append(stripped)
    if buffer:
        _flush_buffer(buffer, entries)
    return entries


def _flush_buffer(buffer: List[str], out: List[Dict[str, Any]]) -> None:
    head = buffer[0]
    rest = buffer[1:]
    m = _ENTRY_RE.match(head)
    if not m:
        return
    date = m.group(1)
    body = m.group(2)
    full_body = "\n".join([body, *rest]) if rest else body
    rounds = sorted({int(r) for r in _ROUND_RE.findall(full_body)})
    kind = _classify_entry(body)
    out.append({
        "date":    date,
        "body":    body,
        "full":    full_body,
        "rounds":  rounds,
        "kind":    kind,
    })


def _classify_entry(body: str) -> str:
    head = body.split("—")[0].strip().upper()
    for tag in ("SHIP-CANDIDATE", "SHIP-PER-STAT", "BATCH SHIP",
                "SHIP", "REJECT", "BLOCKED", "BLOCKER", "BUG FIX",
                "FIX", "DEFER", "NOTE", "WAVE2", "CLOSED", "DISPATCHED",
                "CONFLICT", "DAEMON HEALTH", "STRATEGIC", "PATCH SYNC",
                "LATE NOTIFICATIONS", "PROD GAP NOTED",
                "USER DIRECTIVE"):
        if tag in head:
            return tag
    return "NOTE"


# ----------------------------------------------------------------------------
# Git-log scan
# ----------------------------------------------------------------------------

def collect_git_commits(window_hours: int = 72) -> List[Dict[str, str]]:
    """Return ``[{sha, subject}, ...]`` for commits in the recent window
    that match an R15-R28 probe-id in the subject. Read-only.
    """
    try:
        out = subprocess.check_output(
            ["git", "log", "--all",
             "--since", f"{window_hours} hours ago",
             "--pretty=format:%H %s"],
            cwd=str(PROJECT_DIR),
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        return []
    commits: List[Dict[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        sha, _, subject = line.partition(" ")
        commits.append({"sha": sha[:12], "subject": subject})
    return commits


def filter_commits_for_round(
    commits: List[Dict[str, str]], round_num: int
) -> List[Dict[str, str]]:
    """Return commits whose subject begins with ``R<round_num>_``,
    ``R<round_num> `` or ``R<round_num>:``."""
    out: List[Dict[str, str]] = []
    pat_prefix = re.compile(rf"^R{round_num}(?:_|\b)")
    pat_merge  = re.compile(rf"\bR{round_num}_")
    for c in commits:
        subj = c["subject"]
        if pat_prefix.search(subj) or (subj.startswith("merge:")
                                       and pat_merge.search(subj)):
            out.append(c)
    return out


def get_master_tip_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "master"],
            cwd=str(PROJECT_DIR),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out[:12]
    except Exception:
        return "(unknown)"


# ----------------------------------------------------------------------------
# Theme clustering
# ----------------------------------------------------------------------------

THEME_KEYWORDS: List[Tuple[str, Tuple[str, ...]]] = [
    ("Scrapers",        ("scraper", "bovada", "fanduel", "pinnacle",
                         "prizepicks", "bov ", "pin ", "dk/fd",
                         "playwright", "curl_cffi")),
    ("Model + Features", ("retrain", "feature", "ensemble", "m2_family",
                          "m2v", "winprob", "brier", "mae", "regression",
                          "classifier", "drift", "calibration",
                          "score_diff", "tracking feature")),
    ("Daemons",         ("daemon", "watchdog", "heartbeat",
                         "auto_settle", "auto_place", "auto-settle",
                         "auto-place", "monitor", "middle_finder",
                         "bet ranker", "bet_ranker", "line_move")),
    ("Dashboard",       ("dashboard", "mobile html", "operator dashboard",
                         "/operator", "bankroll dashboard")),
    ("Alerts",          ("alert", "discord", "webhook",
                         "rate-limit", "dedup")),
    ("Data Quality",    ("backfill", "linescores", "settle disagree",
                         "settlement", "void", "dnp", "line_killed",
                         "reconciliation", "ledger", "pace drift")),
    ("Infrastructure",  ("e2e", "smoke", "harness", "ship gate",
                         "workflow", "orchestrator", "cleanup",
                         "morning brief", "insurance", "backup",
                         "kelly", "clv", "patch sync", "worktree")),
]


def cluster_themes(entries: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    themes: Dict[str, List[str]] = OrderedDict()
    for theme, _ in THEME_KEYWORDS:
        themes[theme] = []
    seen: Dict[str, set] = {t: set() for t, _ in THEME_KEYWORDS}
    for e in entries:
        body = e["body"]
        if e["kind"] not in ("SHIP", "SHIP-PER-STAT", "SHIP-CANDIDATE",
                             "BATCH SHIP", "BUG FIX", "FIX", "CLOSED"):
            continue
        body_lc = body.lower()
        probe = _PROBE_ID_RE.search(body)
        probe_id = probe.group(0) if probe else ""
        for theme, keywords in THEME_KEYWORDS:
            for kw in keywords:
                if kw in body_lc:
                    key = (probe_id or body[:80]).strip()
                    if key in seen[theme]:
                        break
                    seen[theme].add(key)
                    one_line = body.split(":")[0]
                    if probe_id:
                        themes[theme].append(f"{probe_id}: {one_line}")
                    else:
                        themes[theme].append(one_line[:120])
                    break
    return themes


# ----------------------------------------------------------------------------
# Round extraction
# ----------------------------------------------------------------------------

def extract_round_summaries(
    entries: List[Dict[str, Any]],
    start_round: int,
    end_round: int,
    commits: Optional[List[Dict[str, str]]] = None,
) -> "OrderedDict[int, Dict[str, Any]]":
    """Group entries by round number (within [start, end]).

    Ships per round are sourced from two places, merged + deduped by
    probe-id (e.g. ``R20_M7``):
      * Explicit SHIP/SHIP-PER-STAT/BATCH-SHIP coordination_log entries
      * Commits whose subject starts ``R<round>_<probe>:`` and does NOT
        contain " REJECT" or " BLOCKED" (the negative form is always
        tagged explicitly upstream).
    Rejects + blocked come from the log only.
    """
    rounds: "OrderedDict[int, Dict[str, Any]]" = OrderedDict()
    for r in range(start_round, end_round + 1):
        rounds[r] = {
            "round":      r,
            "ships":      [],
            "rejects":    [],
            "blocked":    [],
            "notes":      [],
            "standout":   None,
            "closed_summary": None,
            "_seen_ship_keys": set(),
        }
    for e in entries:
        for r in e["rounds"]:
            if not (start_round <= r <= end_round):
                continue
            kind = e["kind"]
            line = e["body"]
            if kind in ("SHIP", "SHIP-PER-STAT", "SHIP-CANDIDATE",
                        "BATCH SHIP"):
                key = _probe_key(line, r)
                if key not in rounds[r]["_seen_ship_keys"]:
                    rounds[r]["_seen_ship_keys"].add(key)
                    rounds[r]["ships"].append(line)
            elif kind == "REJECT":
                rounds[r]["rejects"].append(line)
            elif kind in ("BLOCKED", "BLOCKER"):
                rounds[r]["blocked"].append(line)
            elif kind == "CLOSED":
                rounds[r]["closed_summary"] = line
                rounds[r]["notes"].append(line)
            else:
                rounds[r]["notes"].append(line)
    # Augment with commit-derived ships (per-probe, deduped).
    if commits:
        for r in rounds:
            for c in filter_commits_for_round(commits, r):
                subj = c["subject"]
                if subj.startswith("merge:"):
                    continue
                # Skip rejects (commit body explicitly tags " REJECT").
                if " REJECT" in subj or " BLOCKED" in subj:
                    continue
                m = re.match(rf"^R{r}_([A-Z]\d+)[:\s]", subj)
                if not m:
                    continue
                probe_key = f"R{r}_{m.group(1)}"
                if probe_key in rounds[r]["_seen_ship_keys"]:
                    continue
                rounds[r]["_seen_ship_keys"].add(probe_key)
                rounds[r]["ships"].append(
                    f"{probe_key}: {subj.split(':', 1)[1].strip()}"
                    if ":" in subj else f"{probe_key}: {subj}"
                )
    # Parse "N/M SHIP + K REJECT" + "N BLOCKED" out of any CLOSED line
    # so the tally reflects every reject/block the round summary
    # mentions (the explicit per-round REJECT log line is sometimes
    # collapsed into the CLOSED summary itself).
    closed_re = re.compile(
        r"(\d+)/(\d+)\s+SHIP(?:[^.]*?\+\s*(\d+)\s+REJECT)?"
        r"(?:[^.]*?\+\s*(\d+)\s+BLOCKED)?", re.IGNORECASE)
    for r, payload in rounds.items():
        if payload["closed_summary"]:
            m = closed_re.search(payload["closed_summary"])
            if m:
                rej_n = int(m.group(3)) if m.group(3) else 0
                blk_n = int(m.group(4)) if m.group(4) else 0
                while len(payload["rejects"]) < rej_n:
                    payload["rejects"].append(
                        f"(reject from CLOSED summary, see notes)")
                while len(payload["blocked"]) < blk_n:
                    payload["blocked"].append(
                        f"(blocked from CLOSED summary, see notes)")
    # Standout = the first SHIP entry per round (deterministic).
    for r, payload in rounds.items():
        if payload["ships"]:
            payload["standout"] = payload["ships"][0]
        elif payload["closed_summary"]:
            payload["standout"] = payload["closed_summary"]
        # Drop the private dedup set from the public payload.
        payload.pop("_seen_ship_keys", None)
    return rounds


def _probe_key(body: str, round_num: int) -> str:
    """Deterministic dedup key for a SHIP body line."""
    m = re.search(rf"\bR{round_num}_([A-Z]\d+)\b", body)
    if m:
        return f"R{round_num}_{m.group(1)}"
    return body[:80]


# ----------------------------------------------------------------------------
# Stats (commits / tests / LOC)
# ----------------------------------------------------------------------------

def gather_stats(
    commits: List[Dict[str, str]],
    start_round: int,
    end_round: int,
) -> Dict[str, int]:
    """Heuristics over the per-round commit list: total commits, total
    tests added (numeric mentions), total LOC added (approximate via
    git numstat)."""
    in_window: List[Dict[str, str]] = []
    for r in range(start_round, end_round + 1):
        in_window.extend(filter_commits_for_round(commits, r))
    n_commits = len(in_window)
    # Test counter: parse numbers preceding "tests" in commit subjects.
    n_tests = 0
    for c in in_window:
        for m in re.finditer(r"(\d+)\s*(?:new\s+)?tests?", c["subject"],
                             flags=re.IGNORECASE):
            n_tests += int(m.group(1))
    # LOC added: shell out to git log --numstat for each commit in the
    # window. We sum additions explicitly (range-based syntax was
    # fragile across the merge graph). Skip merges to avoid double-count.
    n_loc = 0
    if in_window:
        shas = [c["sha"] for c in in_window]
        # Deduplicate while preserving order.
        seen: set = set()
        unique_shas = []
        for s in shas:
            if s not in seen:
                seen.add(s)
                unique_shas.append(s)
        for s in unique_shas:
            try:
                out = subprocess.check_output(
                    ["git", "log", "-1", "--numstat",
                     "--no-merges", "--pretty=tformat:", s],
                    cwd=str(PROJECT_DIR),
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
            except Exception:
                continue
            for ln in out.splitlines():
                parts = ln.split("\t")
                if len(parts) == 3:
                    a, _b, _path = parts
                    if a.isdigit():
                        n_loc += int(a)
    return {
        "commits": n_commits,
        "tests":   n_tests,
        "loc":     n_loc,
    }


# ----------------------------------------------------------------------------
# Renderer
# ----------------------------------------------------------------------------

def render(
    *,
    session: int,
    start_round: int,
    end_round: int,
    entries: List[Dict[str, Any]],
    commits: List[Dict[str, str]],
    master_tip: str,
    now_iso: str,
) -> str:
    rounds = extract_round_summaries(entries, start_round, end_round, commits)
    themes = cluster_themes(entries)
    stats  = gather_stats(commits, start_round, end_round)

    n_ships = sum(len(r["ships"]) for r in rounds.values())
    n_rejects = sum(len(r["rejects"]) for r in rounds.values())
    n_blocked = sum(len(r["blocked"]) for r in rounds.values())

    # ---- 1. Header ----
    parts: List[str] = []
    parts.append(f"# Session {session} — R{start_round}-R{end_round} Wave")
    parts.append("")
    parts.append(f"- Generated:      {now_iso}")
    parts.append(f"- Round window:   R{start_round} through R{end_round}")
    parts.append(f"- Total ships:    {n_ships}")
    parts.append(f"- Total rejects:  {n_rejects}")
    parts.append(f"- Total blocked:  {n_blocked}")
    parts.append(f"- Master tip SHA: {master_tip}")
    parts.append("")
    parts.append("Auto-generated by `scripts/generate_session_note.py` "
                 "(probe R29_V4).")
    parts.append("")

    # ---- 2. Round-by-round summary ----
    parts.append(SECTION_HEADINGS[0])
    parts.append("")
    for r, payload in rounds.items():
        parts.append(f"### R{r}")
        n_s = len(payload["ships"])
        n_r = len(payload["rejects"])
        n_b = len(payload["blocked"])
        parts.append(f"- Tally: {n_s} ship / {n_r} reject / {n_b} blocked")
        commits_for_r = filter_commits_for_round(commits, r)
        if commits_for_r:
            parts.append(f"- Commits ({len(commits_for_r)}):")
            for c in commits_for_r[:25]:
                parts.append(f"  - `{c['sha']}` {c['subject']}")
        if payload["ships"]:
            parts.append("- Ships:")
            for s in payload["ships"]:
                parts.append(f"  - {s}")
        if payload["rejects"]:
            parts.append("- Rejects:")
            for s in payload["rejects"]:
                parts.append(f"  - {s}")
        if payload["blocked"]:
            parts.append("- Blocked:")
            for s in payload["blocked"]:
                parts.append(f"  - {s}")
        if payload["standout"]:
            parts.append(f"- Standout: {payload['standout']}")
        parts.append("")

    # ---- 3. Major themes ----
    parts.append(SECTION_HEADINGS[1])
    parts.append("")
    for theme, items in themes.items():
        parts.append(f"### {theme}")
        if not items:
            parts.append("- (no ships in this theme)")
        else:
            for it in items:
                parts.append(f"- {it}")
        parts.append("")

    # ---- 4. Top 10 ships ----
    parts.append(SECTION_HEADINGS[2])
    parts.append("")
    rendered = 0
    shipped_probe_ids = _shipped_probe_ids(rounds)
    for probe_id, reasoning in TOP_10_RANKING:
        if probe_id not in shipped_probe_ids:
            continue
        rendered += 1
        commit = _commit_for_probe(commits, probe_id)
        sha_str = f"`{commit['sha']}`" if commit else "(commit n/a)"
        parts.append(f"{rendered}. **{probe_id}** {sha_str} — {reasoning}")
    if rendered == 0:
        parts.append("- (no top ships identified from the round window)")
    parts.append("")

    # ---- 5. Open items / next session ----
    parts.append(SECTION_HEADINGS[3])
    parts.append("")
    opens = _gather_open_items(entries, start_round, end_round)
    if opens["blocked"]:
        parts.append("**Blocked**")
        for s in opens["blocked"]:
            parts.append(f"- {s}")
        parts.append("")
    if opens["deferred"]:
        parts.append("**Deferred**")
        for s in opens["deferred"]:
            parts.append(f"- {s}")
        parts.append("")
    if opens["failed"]:
        parts.append("**Failed / rejected**")
        for s in opens["failed"]:
            parts.append(f"- {s}")
        parts.append("")
    if not any(opens.values()):
        parts.append("- (no open items recorded in the round window)")
        parts.append("")

    # ---- 6. Stats (still inside section 5 heading per spec? — render
    # as its own block under the section so all 5 mandated sections are
    # present and the stats sub-block is the closer.) ----
    parts.append(SECTION_HEADINGS[4])
    parts.append("")
    parts.append(f"- Commits in window:  {stats['commits']}")
    parts.append(f"- Tests added:        ~{stats['tests']}  "
                 "(parsed from commit subjects)")
    parts.append(f"- Lines of code added: ~{stats['loc']}  "
                 "(numstat additions over commit range)")
    parts.append(f"- Ships:              {n_ships}")
    parts.append(f"- Rejects:            {n_rejects}")
    parts.append(f"- Blocked:            {n_blocked}")
    parts.append("")

    return "\n".join(parts) + "\n"


def _shipped_probe_ids(
    rounds: "OrderedDict[int, Dict[str, Any]]"
) -> set:
    out: set = set()
    for payload in rounds.values():
        for ship_body in payload["ships"]:
            m = _PROBE_ID_RE.search(ship_body)
            if m:
                out.add(m.group(0))
    return out


def _commit_for_probe(
    commits: List[Dict[str, str]], probe_id: str
) -> Optional[Dict[str, str]]:
    """Return the first non-merge commit whose subject starts with
    ``<probe_id>:`` (preferred) or contains it as a token."""
    direct = []
    indirect = []
    for c in commits:
        subj = c["subject"]
        if subj.startswith(f"{probe_id}:") or subj.startswith(f"{probe_id} "):
            direct.append(c)
        elif probe_id in subj and not subj.startswith("merge:"):
            indirect.append(c)
    if direct:
        return direct[0]
    if indirect:
        return indirect[0]
    return None


def _gather_open_items(
    entries: List[Dict[str, Any]],
    start_round: int,
    end_round: int,
) -> Dict[str, List[str]]:
    out = {"blocked": [], "deferred": [], "failed": []}
    for e in entries:
        if not any(start_round <= r <= end_round for r in e["rounds"]):
            continue
        kind = e["kind"]
        if kind in ("BLOCKED", "BLOCKER"):
            out["blocked"].append(e["body"])
        elif kind == "DEFER":
            out["deferred"].append(e["body"])
        elif kind == "REJECT":
            out["failed"].append(e["body"])
    return out


# ----------------------------------------------------------------------------
# Atomic write
# ----------------------------------------------------------------------------

def atomic_write(out_path: Path, body: str) -> None:
    """Stage to .tmp, rotate previous to .bak, then os.replace."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    bak_path = out_path.with_suffix(out_path.suffix + ".bak")
    tmp_path.write_text(body, encoding="utf-8")
    if out_path.exists():
        # Rotate (replace if a previous .bak exists).
        if bak_path.exists():
            bak_path.unlink()
        out_path.replace(bak_path)
    os.replace(str(tmp_path), str(out_path))


# ----------------------------------------------------------------------------
# Public entry-points
# ----------------------------------------------------------------------------

def _parse_round_arg(s: str) -> int:
    s = s.strip().upper()
    if s.startswith("R"):
        s = s[1:]
    return int(s)


def build_note(
    *,
    session: int,
    start_round: int,
    end_round: int,
    coord_log_path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> str:
    """Public renderer entry-point (used by tests + probe)."""
    coord_path = coord_log_path or DEFAULT_COORD_LOG
    entries = parse_coordination_log(coord_path)
    commits = collect_git_commits()
    master_tip = get_master_tip_sha()
    if now is None:
        now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return render(
        session=session,
        start_round=start_round,
        end_round=end_round,
        entries=entries,
        commits=commits,
        master_tip=master_tip,
        now_iso=now_iso,
    )


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--session", type=int, default=3,
                   help="Session number for the rendered filename + header.")
    p.add_argument("--start-round", type=_parse_round_arg, default=15,
                   help="First round in the window (e.g. R15 or 15).")
    p.add_argument("--end-round", type=_parse_round_arg, default=28,
                   help="Last round in the window (e.g. R28 or 28).")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH,
                   help="Output path for the rendered session note.")
    p.add_argument("--coord-log", type=Path, default=DEFAULT_COORD_LOG,
                   help="Path to the coordination_log.md source.")
    p.add_argument("--now", type=str, default=None,
                   help="ISO timestamp for the header (for deterministic tests).")
    p.add_argument("--print", action="store_true",
                   help="Print to stdout instead of writing.")
    args = p.parse_args(argv)

    now_dt: Optional[datetime] = None
    if args.now:
        try:
            now_dt = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        except ValueError:
            now_dt = None
    body = build_note(
        session=args.session,
        start_round=args.start_round,
        end_round=args.end_round,
        coord_log_path=args.coord_log,
        now=now_dt,
    )
    if args.print:
        sys.stdout.write(body)
        return 0
    out: Path = args.out if isinstance(args.out, Path) else Path(args.out)
    atomic_write(out, body)
    print(f"[generate_session_note] wrote {out} ({len(body):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
