"""S313 -- receipt validation and envelope build for `mechanism_effect` rows.

A ledger row that names an artifact (a path plus that file's SHA-256 inside the
row note) may only reach `status="ok"` when every named artifact is present,
byte-intact, no newer than the ledger quoting it, and still carries the row's
own number. Anything else refuses with the contract's existing `no_data` status
and a note saying which artifact failed and why -- a refused envelope never
carries a number. Rows naming no artifact are legacy and pass through.

Attempt 3 also puts the answer's `as_of` floor here: derived freshness may never
outrun the oldest input the answer is derived from (S313 spec bar), so the whole
envelope is composed in one place, `mechanism_envelope`.

S319 makes both checks a function of CONTENT rather than of the checkout. A text
receipt is hashed over LF-normalised bytes through the shared `sha256_lf` helper,
and freshness compares the dates the row and the receipt themselves RECORD, since
git preserves neither line endings nor mtimes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from scripts.platformkit.hash_lf import sha256_lf

# Any `<path> sha256 <hex>` / `<path>; receipt_sha256=<hex>` pair in the note,
# whatever labels it: `receipt=`, `summary=`, `spec `, `blocking_row=<row>, `.
# The path is captured without a `<label>=` prefix because `=` is not in the
# class, so the four shapes on the ledger today all yield the bare path.
_REF_RE = re.compile(
    r"(?P<path>[A-Za-z0-9_./-]+\.[A-Za-z0-9]{2,5})"
    r"(?:;?\s*receipt_sha256=|\s+sha256\s+)(?P<sha>[0-9a-f]{64})")
_NUM_RE = re.compile(r"-?\d+\.\d+(?:[eE][-+]?\d+)?")
_TOL = 1e-9
# ponytail: a checkout writes the whole tree at once, so only an inversion
# larger than an hour is real staleness rather than file-write ordering. Used
# only where one side records no date of its own (S319 rule 2 fallback).
_MTIME_SLACK_S = 3600.0
# git stores these verbatim, so normalising their bytes would be wrong: they are
# hashed raw and verify only against a raw digest.
_BINARY_EXT = frozenset({".gz", ".zip", ".parquet", ".png", ".jpg", ".jpeg",
                         ".mp4", ".npy", ".pkl", ".pt", ".bin"})
# Recorded (CRLF-sealed) digest -> LF digest of the same content. Committed, so
# it is resolved against the module, not against the caller's cwd.
_SIDECAR = (Path(__file__).resolve().parents[3]
            / "docs/evidence/harness/S319_receipt_hashes_2026-09-08.json")
_ISO_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
_DATE_FIELD_RE = re.compile(
    r"\"?\b(?:run_utc|generated_at|as_of)\"?\s*[:=]\s*\"?(\d{4}-\d{2}-\d{2})")
_ROW_DATE_KEYS = ("as_of", "date", "run_ts")


def _sha256_raw(path: str) -> str:
    """SHA-256 of the file's bytes as they sit on this checkout."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@lru_cache(maxsize=1)
def _sidecar_map() -> dict:
    try:
        return json.loads(_SIDECAR.read_text(encoding="utf-8"))["recorded_to_lf"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}  # absent sidecar simply offers no alternative digest


def hash_match(path: str, recorded: str) -> str | None:
    """Which rule verifies `path` against the digest a row `recorded`, or None.

    Keyed by the RECORDED digest rather than by path, so a row quoting an altered
    digest finds no sidecar entry and still refuses.
    """
    if os.path.splitext(path)[1].lower() in _BINARY_EXT:
        return "raw" if _sha256_raw(path) == recorded else None
    lf = sha256_lf(path)
    if lf == recorded:
        return "lf"
    if _sidecar_map().get(recorded) == lf:
        return "sidecar_lf"
    if _sha256_raw(path) == recorded:
        return "raw"  # legacy: sealed raw on a CRLF machine, read on one too
    return None


def receipt_date(path: str, text: str) -> str | None:
    """The date the receipt itself records, or None if it records none.

    Its own `run_utc`/`generated_at`/`as_of` field wins. Otherwise the LATEST
    ISO-8601 date in its text: an artifact cannot have been produced before the
    newest date it names, so the fallback errs toward refusing, not accepting.
    """
    if os.path.splitext(path)[1].lower() in _BINARY_EXT:
        return None
    field = _DATE_FIELD_RE.search(text)
    if field:
        return field.group(1)
    dates = _ISO_RE.findall(text)
    return max(dates) if dates else None


def row_date(row: dict) -> str | None:
    """The date the ledger row itself records, or None."""
    for key in _ROW_DATE_KEYS:
        value = row.get(key)
        if isinstance(value, str) and _ISO_RE.match(value):
            return value[:10]
    return None


def composed_n(row: dict) -> int | None:
    """The n an answer may print for `row`.

    A row that measured nothing has no n at all; a literal 0 would read as a
    real count of zero observations, which is a number this row never had.
    """
    if row.get("effect") is None and not row.get("n"):
        return None
    return row.get("n")


def _reason_to_refuse(row: dict, ledger_path: str,
                      matched: dict | None = None) -> str | None:
    """None when the row may be answered, else the reason it must not be.

    `matched` collects `path -> which hash rule verified it` for the envelope note.
    """
    refs = list(_REF_RE.finditer(row.get("note") or ""))
    if not refs:
        return None  # legacy row: it claims no receipt, so there is none to check
    name = row.get("hypothesis")
    ledger_mtime = os.path.getmtime(ledger_path)
    quoted = row_date(row)
    texts = []
    for match in refs:
        path, sha = match.group("path"), match.group("sha")
        if not os.path.isfile(path):
            return f"the receipt {path} named by row '{name}' is absent"
        how = hash_match(path, sha)
        if how is None:
            return f"the receipt {path} no longer hashes to the {sha} row '{name}' names"
        if matched is not None:
            matched[path] = how
        text = open(path, encoding="utf-8", errors="replace").read()
        recorded = receipt_date(path, text)
        if recorded is not None and quoted is not None:
            if recorded > quoted:
                return (f"stale: the receipt {path} records {recorded}, later than the "
                        f"{quoted} that row '{name}' records, so the as-of of this answer "
                        "would outrun the receipt it derives from")
        elif ledger_mtime < os.path.getmtime(path) - _MTIME_SLACK_S:
            return (f"stale: no recorded date on both sides, so mtimes were compared -- "
                    f"the ledger {ledger_path} is older than its required input "
                    f"{path}, so the as-of of this answer would outrun the receipt it "
                    "derives from")
        texts.append(text)
    effect = row.get("effect")
    if effect is None:
        return None
    if not any(abs(float(tok) - effect) <= _TOL
               for text in texts for tok in _NUM_RE.findall(text)):
        return (f"row '{name}' states {effect}, which nothing within {_TOL} reproduces in "
                f"{', '.join(m.group('path') for m in refs)}")
    return None


def check_rows(rows: list[dict], ledger_path: str,
               matched: dict | None = None) -> dict | None:
    """`{"status", "note"}` when any row must refuse, else None."""
    for row in rows:
        reason = _reason_to_refuse(row, ledger_path, matched)
        if reason is not None:
            return {"status": "no_data",
                    "note": f"receipt validation refused this answer -- {reason}. "
                            "No number is composed from a receipt that did not verify."}
    return None


def as_of(rows: list[dict], ledger_path: str) -> str:
    """The oldest of the ledger and every artifact these rows name, ISO-8601 UTC.

    Derived freshness may never outrun its oldest required input (S313 spec bar),
    so the answer is dated by that input, not by the ledger that quotes it.
    """
    named = (m.group("path") for row in rows
             for m in _REF_RE.finditer(row.get("note") or ""))
    oldest = min([os.path.getmtime(ledger_path)]
                 + [os.path.getmtime(p) for p in named if os.path.isfile(p)])
    return datetime.fromtimestamp(oldest, tz=timezone.utc).isoformat()


def mechanism_envelope(rows: list[dict], ledger_path: str, sport: str, name: str) -> dict:
    """The `mechanism_effect` answer for one hypothesis -- or its refusal.

    Every receipt-bearing row verifies before any number is composed from it.
    """
    matched: dict[str, str] = {}
    refusal = check_rows(rows, ledger_path, matched)
    if refusal is not None:
        return {"status": refusal["status"], "category": "mechanism_effect", "sport": sport,
                "source_artifact": ledger_path, "note": refusal["note"]}
    return {"status": "ok", "category": "mechanism_effect", "sport": sport,
            "source_artifact": ledger_path, "as_of": as_of(rows, ledger_path),
            "hypothesis": name,
            "note": ("receipts verified: " + ", ".join(
                f"{p} [{how}]" for p, how in sorted(matched.items()))
                if matched else "this row names no receipt (legacy pass-through)"),
            "findings": [{"verdict": r["verdict"], "effect_local": r["effect"],
                          "n": composed_n(r), "p": r.get("p"), "corpus": r["corpus"],
                          "note": r["note"]} for r in rows],
            "framing": "LOCAL single-corpus finding(s) -- not a market-beating or causal claim"}


if __name__ == "__main__":  # pragma: no cover - runnable self-check
    import json
    import sys
    LEDGER = "domains/basketball_nba/knowledge/validation_ledger.jsonl"
    good = [json.loads(line) for line in open(LEDGER, encoding="utf-8") if line.strip()]
    assert check_rows(good, LEDGER) is None, "the landed ledger must verify"
    bad = dict(next(r for r in good if r["hypothesis"] == "s293_tail_log_loss_rail"))
    bad["effect"] = -bad["effect"]
    assert check_rows([bad], LEDGER) is not None, "a flipped row must refuse"
    assert composed_n({"effect": None, "n": 0}) is None
    assert composed_n({"effect": 0.5, "n": 12}) == 12
    rows = [r for r in good if r["hypothesis"] == "s293_tail_log_loss_rail"]
    env = mechanism_envelope(rows, LEDGER, "nba", "s293_tail_log_loss_rail")
    ledger_at = datetime.fromtimestamp(os.path.getmtime(LEDGER), tz=timezone.utc).isoformat()
    assert env["as_of"] < ledger_at, "the answer must be dated by its oldest input"
    print("receipt_guard self-check OK", file=sys.stderr)
