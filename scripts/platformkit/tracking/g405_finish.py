"""G405 fresh-process repeats, field-aware Q6 scan, and checksum manifest."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from scripts.platformkit.tracking.g405_prereg import FORBIDDEN, TEXT_SUFFIXES

TABLES = ("discovery_population.csv", "draw.csv", "probe_receipts.csv", "format_rows.csv",
          "availability.csv", "eye_index.csv", "discovery_queue.jsonl", "summary.json")
LEDGER_MD = Path("docs/evidence/tracking/RESULTS_LEDGER.md")
DATA_FIELDS = frozenset({"title", "query", "query_memberships", "stderr", "stdout", "error",
                         "resolution", "format_note", "extractor"})
SUMS_HEADER = ("# byte domain: sha256 over the LF-normalized bytes of each listed file (every CRLF "
               "collapsed to LF before hashing), path relative to this directory; that is the byte "
               "form git commits under core.autocrlf, so any checkout reproduces these digests")


def _sha(path: Path) -> str:
    """Hash the committed byte form: CRLF collapsed to LF, nothing else changed."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _rel(path: Path, evidence: Path) -> str:
    """Name a scanned file relative to the evidence dir, else to the repo root."""
    try:
        return str(path.relative_to(evidence)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _cards(evidence: Path) -> list[str]:
    return sorted("cards/%s" % p.name for p in (evidence / "cards").glob("*.txt"))


def repeats(evidence: Path) -> int:
    """Rebuild the tables and cards twice in fresh processes from saved bytes."""
    names = list(TABLES) + _cards(evidence)
    delivered = {n: _sha(evidence / n) for n in names}
    runs = []
    for index in (1, 2):
        proc = subprocess.run([sys.executable, "-m", "scripts.platformkit.tracking.g405_build",
                               "build", str(evidence)], capture_output=True, text=True)
        runs.append({"run": index, "returncode": proc.returncode,
                     "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()[-400:],
                     "matches": {n: _sha(evidence / n) == delivered[n] for n in names}})
    identical = all(all(r["matches"].values()) and r["returncode"] == 0 for r in runs)
    payload = {"identical": identical, "all_tables_and_cards_reproduced": identical,
               "delivered_sha256": delivered, "runs": runs,
               "scope": ("Fresh-process rebuilds of parsing, classification tables, sidecar and "
                         "cards from the archived raw listing/metadata bytes only. No network "
                         "probe was repeated; this proves parsing repeatability, not stable "
                         "future availability of any rendition.")}
    (evidence / "repeats.json").write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    print("repeats identical=%s runs=%d tables=%d" % (identical, len(runs), len(names)))
    return 0 if identical else 1


def _walk(node: object, field: str, pats: list[tuple[str, str]],
          counts: dict[str, dict[str, int]]) -> None:
    """Tally restricted patterns by OPAQUE index; the token text is never emitted."""
    if isinstance(node, dict):
        for key, value in node.items():
            _walk(value, str(key), pats, counts)
    elif isinstance(node, list):
        for value in node:
            _walk(value, field, pats, counts)
    elif isinstance(node, str):
        kind = "data_field" if field in DATA_FIELDS else "claim_field"
        low = node.lower()
        for index, word in pats:
            hits = _count(low, word)
            if hits:
                counts[index][kind] += hits


def _count(text: str, word: str) -> int:
    total, start = 0, 0
    while True:
        at = text.find(word, start)
        if at < 0:
            return total
        before = text[at - 1] if at else " "
        after = text[at + len(word)] if at + len(word) < len(text) else " "
        if not before.isalnum() and not after.isalnum():
            total += 1
        start = at + len(word)


def _patterns() -> list[tuple[str, str]]:
    """Pattern <i> is FORBIDDEN[i] rebuilt from character codes; text stays unnamed."""
    return [("pattern_%d" % i, "".join(chr(code) for code in item))
            for i, item in enumerate(FORBIDDEN)]


def q6(evidence: Path) -> int:
    """Count restricted vocabulary per artifact; emit indices, never the matched text."""
    pats = _patterns()
    keys = [index for index, _ in pats]
    per_file, totals = {}, {k: {"claim_field": 0, "data_field": 0} for k in keys}
    scanned = 0
    owned = sorted(Path("scripts/platformkit/tracking").glob("g405_*.py"))
    owned += [Path("tests/platformkit/test_g405_discovery_formats.py"), Path(str(evidence) + ".md"),
              LEDGER_MD]
    for path in sorted(evidence.rglob("*")) + owned:
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES | {".diff"}:
            continue
        scanned += 1
        counts = {k: {"claim_field": 0, "data_field": 0} for k in keys}
        raw = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() in (".json", ".jsonl"):
            for line in ([raw] if path.suffix.lower() == ".json" else raw.splitlines()):
                if line.strip():
                    try:
                        _walk(json.loads(line), "", pats, counts)
                    except ValueError:
                        _walk(line, "", pats, counts)
        elif path.suffix.lower() == ".csv":
            head = raw.splitlines()[0].split(",") if raw.strip() else []
            for line in raw.splitlines()[1:]:
                for column, cell in zip(head, line.split(",")):
                    _walk(cell, column, pats, counts)
        else:
            _walk(raw, "", pats, counts)
        for key in keys:
            for kind in ("claim_field", "data_field"):
                totals[key][kind] += counts[key][kind]
        if any(v["claim_field"] or v["data_field"] for v in counts.values()):
            per_file[_rel(path, evidence)] = counts
    payload = {"scanned_text_artifacts": scanned, "patterns_from_character_codes": len(pats),
               "counts_only": True, "totals": totals, "files_with_hits": per_file,
               "pattern_index_domain": (
                   "pattern_<i> is index i of FORBIDDEN in "
                   "scripts/platformkit/tracking/g405_prereg.py, built from character codes; "
                   "this receipt emits indices and counts only and never spells a pattern"),
               "field_aware_note": ("Hits inside inherited source description fields "
                                    "(%s) are data, not claims; claim_field hits are the gate."
                                    % ", ".join(sorted(DATA_FIELDS)))}
    out = evidence / "common_receipts" / "q6_scan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload["ledger_scope_note"] = (
        "%s is shared: its counts cover rows owned by other G rows, so the gate below "
        "is scoped to this row's added line only." % _rel(LEDGER_MD, evidence))
    payload["this_row_ledger_line"] = _ledger_line_counts(pats)
    out.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    owned_hits = sum(v["claim_field"] for name, counts in per_file.items()
                     for v in counts.values() if name != _rel(LEDGER_MD, evidence))
    claim_hits = owned_hits + sum(v["claim_field"] for v in payload["this_row_ledger_line"].values())
    print("q6 scanned=%d claim_field_hits=%d data_field_hits=%d"
          % (scanned, claim_hits, sum(v["data_field"] for v in totals.values())))
    return 0 if claim_hits == 0 else 1


def _ledger_line_counts(pats: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """Count the restricted patterns in this row's own ledger line only."""
    counts = {index: {"claim_field": 0, "data_field": 0} for index, _ in pats}
    if not LEDGER_MD.exists():
        return counts
    for line in LEDGER_MD.read_text(encoding="utf-8", errors="replace").splitlines():
        if "| G405 |" in line:
            _walk(line, "", pats, counts)
    return counts


def sums(evidence: Path) -> int:
    """Write SHA256SUMS with an explicit byte-domain declaration on line 1."""
    lines = [SUMS_HEADER]
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            lines.append("%s  %s" % (_sha(path), _rel(path, evidence)))
    (evidence / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("sums files=%d" % (len(lines) - 1))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: g405_finish.py repeats|q6|sums <evidence_dir>")
        return 2
    evidence = Path(argv[2])
    return {"repeats": repeats, "q6": q6, "sums": sums}[argv[1]](evidence)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
