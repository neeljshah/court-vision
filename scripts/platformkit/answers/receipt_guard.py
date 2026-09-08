"""S313 fix 2b -- receipt validation for `mechanism_effect` ledger rows.

A ledger row that names its receipt (`receipt=<path>` plus that file's SHA-256
inside the row note) may only reach `status="ok"` when every named artifact is
present, byte-intact, no newer than the ledger quoting it, and still carries the
row's own number. Anything else refuses with the contract's existing `no_data`
status and a note saying which artifact failed and why -- a refused envelope
never carries a number. Rows naming no receipt are legacy and pass through.
"""
from __future__ import annotations

import hashlib
import os
import re

# The two shapes on the ledger today: `receipt=<path>; receipt_sha256=<hex>`
# and `receipt=<path> sha256 <hex>` (`summary=` always uses the second).
_REF_RE = re.compile(
    r"\b(?:receipt|summary)=(?P<path>[^\s;,]+)"
    r"(?:;?\s*receipt_sha256=|\s+sha256\s+)(?P<sha>[0-9a-f]{64})")
_NUM_RE = re.compile(r"-?\d+\.\d+(?:[eE][-+]?\d+)?")
_TOL = 1e-9
# ponytail: a checkout writes the whole tree at once, so only an inversion
# larger than an hour is real staleness rather than file-write ordering.
_MTIME_SLACK_S = 3600.0


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def composed_n(row: dict) -> int | None:
    """The n an answer may print for `row`.

    A row that measured nothing has no n at all; a literal 0 would read as a
    real count of zero observations, which is a number this row never had.
    """
    if row.get("effect") is None and not row.get("n"):
        return None
    return row.get("n")


def _reason_to_refuse(row: dict, ledger_path: str) -> str | None:
    """None when the row may be answered, else the reason it must not be."""
    refs = list(_REF_RE.finditer(row.get("note") or ""))
    if not refs:
        return None  # legacy row: it claims no receipt, so there is none to check
    name = row.get("hypothesis")
    ledger_mtime = os.path.getmtime(ledger_path)
    texts = []
    for match in refs:
        path, sha = match.group("path"), match.group("sha")
        if not os.path.isfile(path):
            return f"the receipt {path} named by row '{name}' is absent"
        if _sha256(path) != sha:
            return f"the receipt {path} no longer hashes to the {sha} row '{name}' names"
        if ledger_mtime < os.path.getmtime(path) - _MTIME_SLACK_S:
            return (f"stale: the ledger {ledger_path} is older than its required input "
                    f"{path}, so the as-of of this answer would outrun the receipt it "
                    "derives from")
        texts.append(open(path, encoding="utf-8", errors="replace").read())
    effect = row.get("effect")
    if effect is None:
        return None
    if not any(abs(float(tok) - effect) <= _TOL
               for text in texts for tok in _NUM_RE.findall(text)):
        return (f"row '{name}' states {effect}, which nothing within {_TOL} reproduces in "
                f"{', '.join(m.group('path') for m in refs)}")
    return None


def check_rows(rows: list[dict], ledger_path: str) -> dict | None:
    """`{"status", "note"}` when any row must refuse, else None."""
    for row in rows:
        reason = _reason_to_refuse(row, ledger_path)
        if reason is not None:
            return {"status": "no_data",
                    "note": f"receipt validation refused this answer -- {reason}. "
                            "No number is composed from a receipt that did not verify."}
    return None


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
    print("receipt_guard self-check OK", file=sys.stderr)
