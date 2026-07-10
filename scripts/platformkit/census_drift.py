"""scripts.platformkit.census_drift -- drift checker for the hand-authored
data/frontend/ops/data_census.json (prose, not generated -- it rots silently:
2026-07-08 it claimed WNBA had no boxscores while 4,697 rows sat on disk).
NOT a full generator (biggest_absence/derivable_families stay human/Fable
judgment calls) -- just metadata-only reconciliation of sources{} entries
that pair a real path with a concrete count.

ponytail scope limits: only unambiguous single-count entries get compared
(a plain int, or a string with exactly one non-approximate number -- ranges,
multi-metric strings, "~15k" style approximations -> unverifiable, not
guessed at). A single {a,b,c} brace group expands per-key, matched to an
adjacent same-named number in the rows text (best-effort; a naming mismatch
like "on_off" vs "on-off" degrades that key to unverifiable, not a false
drift). Directories are checked both as a file count AND a summed
jsonl-line/parquet-row count -- either interpretation counts as a match,
since census prose uses both conventions. Discovering artifacts NOT already
listed in the census is out of scope (human's job).

Autoloop seam: run_check() is the sole (no-arg) entrypoint, for
scripts/platformkit/autoloop/maintenance_templates.py to import later as a
4th zero-LLM job -- not wired in here, that wiring is a Fable decision.
"""
from __future__ import annotations

import glob
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional

try:
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover
    pq = None

CENSUS_PATH = "data/frontend/ops/data_census.json"
OUT_PATH = "data/frontend/ops/census_drift.json"

def _count_jsonl_lines(path: str) -> int:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return sum(1 for _ in f)

def _count_parquet_rows(path: str) -> Optional[int]:
    if pq is None:
        return None
    return pq.ParquetFile(path).metadata.num_rows  # metadata only, never reads data

def _count_one(path: str) -> "tuple[int, Optional[int]]":
    """(files, content) candidates: files=entry count, content=summed rows/lines
    (None if not summable). Two candidates because prose claims either kind."""
    if os.path.isdir(path):
        entries = [os.path.join(path, e) for e in os.listdir(path)]
        jsonl = [e for e in entries if e.endswith(".jsonl")]
        parquet = [e for e in entries if e.endswith(".parquet")]
        content: Optional[int] = None
        if jsonl:
            content = sum(_count_jsonl_lines(e) for e in jsonl)
        elif parquet:
            content = 0
            for e in parquet:
                c = _count_parquet_rows(e)
                if c is None:
                    content = None
                    break
                content += c
        return len(entries), content
    if path.endswith(".parquet"):
        return 1, _count_parquet_rows(path)
    if path.endswith(".jsonl"):
        return 1, _count_jsonl_lines(path)
    return 1, None  # a single concrete non-parquet/jsonl file -- no content signal

def _resolve(pattern: str) -> Optional["tuple[int, Optional[int]]"]:
    """Glob a path pattern (placeholders already -> '*'); sum (files, content)
    candidates across matches, or None if nothing matched."""
    matches = glob.glob(pattern)
    if not matches:
        return None
    total_files, total_content, content_ok = 0, 0, True
    for m in matches:
        f, c = _count_one(m)
        total_files += f
        if c is None:
            content_ok = False
        else:
            total_content += c
    return total_files, (total_content if content_ok else None)

def _to_glob(path: str) -> str:
    path = re.sub(r"<[^>]+>", "*", path)
    return re.sub(r"\{[^}]*\}", "*", path)  # any leftover (non-comma or already-expanded) brace

def _primary_token(raw_path: str) -> str:
    """First whitespace/paren-delimited token -- drops trailing prose like '(+cdn_backfill/ 168 games)'."""
    return re.split(r"[\s;(]", raw_path.strip(), maxsplit=1)[0]

def _extract_target(rows: Any) -> Optional[int]:
    """A rows value is 'concrete' iff it is an int, or a string with exactly one
    non-decimal, non-'k'-suffixed number. Ranges/multi-metric/approx strings -> None."""
    if isinstance(rows, int):
        return rows
    if not isinstance(rows, str):
        return None
    nums = re.findall(r"\d[\d,]*(?:\.\d+)?", rows)
    if len(nums) != 1:
        return None
    n = nums[0]
    if "." in n:
        return None
    idx = rows.find(n)
    if rows[idx + len(n): idx + len(n) + 1].lower() == "k":
        return None  # "15k" -- approximate, not concrete
    if idx > 0 and rows[idx - 1] == "~":
        return None  # "~1048/season" -- approximate, not concrete
    return int(n.replace(",", ""))

def _per_key_target(rows_text: str, key: str) -> Optional[int]:
    """Find `key` as a whole token and return a neighboring whole-digit token
    (checked just-before/just-after/2-before/2-after -- avoids mid-number splits)."""
    tokens = re.findall(r"\w+", rows_text)
    try:
        idx = tokens.index(key)
    except ValueError:
        return None
    for j in (idx - 1, idx + 1, idx - 2, idx + 2):
        if 0 <= j < len(tokens) and tokens[j].isdigit():
            return int(tokens[j])
    return None

_FILE_UNIT_WORDS = {"day", "days", "game", "games", "file", "files", "dir", "dirs", "date", "dates"}

def _is_row_claim(rows: Any) -> bool:
    """True when `rows` describes content (row/line/tick count) rather than a
    file/entry count. Default True (the field is literally called "rows"),
    EXCEPT strings that name an explicit file-like unit ("507 games", "4
    depth-days") -- those describe entries being counted, not content."""
    if not isinstance(rows, str):
        return True
    words = {w.lower() for w in re.findall(r"[A-Za-z]+", rows)}
    return not (words & _FILE_UNIT_WORDS)

def _verdict(label: str, target: Optional[int], resolved: Optional["tuple[int, Optional[int]]"],
             is_row_claim: bool = True) -> Dict[str, Any]:
    if resolved is None:
        return {"entry": label, "status": "missing", "claimed": target}
    files, content = resolved
    if target is None:
        return {"entry": label, "status": "unverifiable", "reason": "no comparable claimed count",
                 "actual": content if content is not None else files}
    tol = 0 if target <= 20 else max(1, round(target * 0.05))
    # files is only a meaningful candidate once there's more than one entry to count
    file_candidate = files if files > 1 else None
    # precedence, not distance: a row-claim (default -- "rows" means content)
    # is checked against summed line/row content first; a file-unit claim is
    # checked against the file count first. Picking whichever candidate was
    # numerically CLOSER to a stale claim let a file count masquerade as the
    # true content figure (false "collapse" reports on growing corpora).
    ordered = (content, file_candidate) if is_row_claim else (file_candidate, content)
    candidates = [c for c in ordered if c is not None] or [files]
    for c in candidates:
        if abs(c - target) <= tol:
            return {"entry": label, "status": "ok", "claimed": target, "actual": c}
    return {"entry": label, "status": "drift", "claimed": target, "actual": candidates[0]}

def check_entry(sport: str, name: str, source: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    """Yield one result dict per sources{} sub-check (>1 only for comma-brace paths)."""
    label = f"{sport}.{name}"
    raw_path, rows = source.get("path"), source.get("rows")
    if not raw_path or rows is None:
        yield {"entry": label, "status": "unverifiable", "reason": "path or rows field absent"}
        return

    row_claim = _is_row_claim(rows)
    path = _primary_token(raw_path)
    brace = re.search(r"\{([^}]*)\}", path)
    if brace and "," in brace.group(1):
        for key in (k.strip() for k in brace.group(1).split(",")):
            if not key:
                continue
            concrete = _to_glob(path[: brace.start()] + key + path[brace.end():])
            target = _per_key_target(rows, key) if isinstance(rows, str) else rows
            yield _verdict(f"{label}[{key}]", target, _resolve(concrete), row_claim)
        return

    target = _extract_target(rows)
    if target is None:
        yield {"entry": label, "status": "unverifiable", "reason": f"rows not a single concrete count: {rows!r}"}
        return
    yield _verdict(label, target, _resolve(_to_glob(path)), row_claim)

def run_check(census_path: str = CENSUS_PATH, out_path: str = OUT_PATH) -> Dict[str, Any]:
    """Sole entrypoint -- no required args. Report-only: exit code is always 0
    (caller decides what, if anything, to do with drift_entries)."""
    with open(census_path, "r", encoding="utf-8") as f:
        census = json.load(f)

    results = []
    for sport, sdata in census.get("sports", {}).items():
        for name, source in sdata.get("sources", {}).items():
            results.extend(check_entry(sport, name, source))

    counts = {s: sum(1 for r in results if r["status"] == s) for s in ("ok", "drift", "missing", "unverifiable")}
    drift_entries = [r for r in results if r["status"] in ("drift", "missing")]
    out = {"generated": datetime.now(timezone.utc).isoformat(), "n_ok": counts["ok"], "n_drift": counts["drift"],
           "n_missing": counts["missing"], "n_unverifiable": counts["unverifiable"], "drift_entries": drift_entries}

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"census_drift: ok={counts['ok']} drift={counts['drift']} missing={counts['missing']} "
          f"unverifiable={counts['unverifiable']}")
    for r in drift_entries:
        print(f"  {r['status'].upper():9s} {r['entry']}  claimed={r.get('claimed')} actual={r.get('actual')}")
    return out

if __name__ == "__main__":
    run_check()
