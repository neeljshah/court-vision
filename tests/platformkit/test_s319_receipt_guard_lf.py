"""S319 -- the receipt guard must judge CONTENT, not the checkout.

Git preserves neither line endings nor mtimes, so a byte-exact hash and an mtime
comparison both make a landed receipt verify or refuse depending on which machine
checked the tree out. Every case here builds a scratch tree from the real landed
receipts and runs the real guard against it; no tracked file is touched.

Run this file alone, with confcutdir pointed at the platformkit test package.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER_REL = "domains/basketball_nba/knowledge/validation_ledger.jsonl"
SIDECAR = ROOT / "docs/evidence/harness/S319_receipt_hashes_2026-09-08.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.platformkit.answers import receipt_guard as G  # noqa: E402
from scripts.platformkit.hash_lf import sha256_lf  # noqa: E402


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    text = (ROOT / LEDGER_REL).read_text(encoding="utf-8")
    all_rows = [json.loads(l) for l in text.splitlines() if l.strip()]
    keep = [r for r in all_rows if G._REF_RE.search(r.get("note") or "")]
    assert keep, "premise -- the ledger must carry at least one receipt-bearing row"
    return keep


def _refs(rows: list[dict]) -> list[tuple[str, str]]:
    """Every `(relative path, recorded digest)` the rows name, in order."""
    return [(m.group("path"), m.group("sha"))
            for r in rows for m in G._REF_RE.finditer(r["note"])]


def _build(root: pathlib.Path, rows: list[dict], eol: bytes = b"\n",
           ledger_rows: list[dict] | None = None) -> None:
    """A scratch copy of the ledger and every receipt it names, in one line ending."""
    for rel, _ in _refs(rows):
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        raw = (ROOT / rel).read_bytes()
        if pathlib.Path(rel).suffix.lower() in G._BINARY_EXT:
            dst.write_bytes(raw)
        else:
            dst.write_bytes(raw.replace(b"\r\n", b"\n").replace(b"\n", eol))
    ledger = root / LEDGER_REL
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("".join(json.dumps(r) + "\n" for r in (ledger_rows or rows)),
                      encoding="utf-8")
    base = 1_757_000_000.0  # every receipt older than the ledger, by default
    for rel, _ in _refs(rows):
        os.utime(root / rel, (base, base))
    os.utime(ledger, (base + 7200, base + 7200))


def _run(monkeypatch, root: pathlib.Path, rows: list[dict]) -> tuple[dict | None, dict]:
    monkeypatch.chdir(root)
    matched: dict[str, str] = {}
    return G.check_rows(rows, LEDGER_REL, matched), matched


# --- T1: line endings must not decide the verdict ---------------------------

def test_crlf_and_lf_copies_yield_the_same_outcome(monkeypatch, tmp_path, rows):
    outcomes = {}
    for label, eol in (("lf", b"\n"), ("crlf", b"\r\n")):
        root = tmp_path / label
        _build(root, rows, eol)
        outcomes[label] = _run(monkeypatch, root, rows)
    (lf_refusal, lf_matched), (crlf_refusal, crlf_matched) = outcomes["lf"], outcomes["crlf"]
    assert lf_refusal is None, lf_refusal          # both must verify, not both refuse
    assert crlf_refusal is None, crlf_refusal
    assert lf_matched == crlf_matched, (lf_matched, crlf_matched)
    assert len(lf_matched) == len(_refs(rows)) > 0
    # and the two trees really did differ in bytes
    first = _refs(rows)[0][0]
    assert (tmp_path / "lf" / first).read_bytes() != (tmp_path / "crlf" / first).read_bytes()


# --- T2 / T3: freshness comes from the recorded dates ------------------------

def test_a_receipt_newer_by_mtime_but_older_by_recorded_date_is_accepted(
        monkeypatch, tmp_path, rows):
    root = tmp_path / "mtime"
    _build(root, rows, b"\n")
    ledger_mtime = os.path.getmtime(root / LEDGER_REL)
    late = ledger_mtime + 30 * 86400
    for rel, _ in _refs(rows):
        os.utime(root / rel, (late, late))
    for rel, _ in _refs(rows):
        assert os.path.getmtime(root / rel) > ledger_mtime, "premise -- receipt is newer"
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        assert G.receipt_date(rel, text) is not None, rel
    refusal, matched = _run(monkeypatch, root, rows)
    assert refusal is None, refusal
    assert len(matched) == len(_refs(rows))


def test_a_receipt_recorded_later_than_its_row_refuses_as_stale(monkeypatch, tmp_path, rows):
    row = dict(rows[0])
    row["run_ts"] = "2017-07-14T00:00:00Z"  # older than every receipt it names
    root = tmp_path / "stale"
    _build(root, rows, b"\n", ledger_rows=[row])
    refusal, _ = _run(monkeypatch, root, [row])
    assert refusal is not None and refusal["status"] == "no_data"
    assert "stale" in refusal["note"]
    assert G.row_date(row) == "2017-07-14"
    named = _refs([row])[0][0]
    assert named in refusal["note"], refusal["note"]


# --- T4: an altered digest still refuses ------------------------------------

def test_a_flipped_hex_digit_still_refuses(monkeypatch, tmp_path, rows):
    row = dict(rows[0])
    rel, sha = _refs([row])[0]
    row["note"] = row["note"].replace(sha, sha[:-1] + ("0" if sha[-1] != "0" else "1"))
    root = tmp_path / "flipped"
    _build(root, rows, b"\n", ledger_rows=[row])
    refusal, _ = _run(monkeypatch, root, [row])
    assert refusal is not None and refusal["status"] == "no_data"
    assert "no longer hashes" in refusal["note"] and rel in refusal["note"]


# --- T5: the sidecar says what it claims to say -----------------------------

def test_every_sidecar_entry_maps_a_named_receipt_to_its_normalised_digest(rows):
    payload = json.loads(SIDECAR.read_text(encoding="utf-8"))
    mapping, provenance = payload["recorded_to_lf"], payload["provenance"]
    named = {sha: rel for rel, sha in _refs(rows)}
    assert set(mapping) == set(provenance), "every entry must name the artifact it came from"
    for recorded, lf in mapping.items():
        assert recorded in named, "sidecar entry for a digest no ledger row records"
        rel = provenance[recorded]
        assert rel == named[recorded], (rel, named[recorded])
        assert lf == sha256_lf(ROOT / rel), rel
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == recorded, rel
    needed = {sha for rel, sha in _refs(rows)
              if pathlib.Path(rel).suffix.lower() not in G._BINARY_EXT
              and sha256_lf(ROOT / rel) != sha}
    assert needed <= set(mapping), needed - set(mapping)


def test_the_sidecar_alone_verifies_a_receipt_no_raw_digest_could(tmp_path):
    """The sidecar, not the raw fallback, is what an LF checkout verifies through."""
    payload = json.loads(SIDECAR.read_text(encoding="utf-8"))
    recorded, rel = next(iter(payload["provenance"].items()))
    dst = tmp_path / pathlib.Path(rel).name
    shutil.copyfile(ROOT / rel, dst)
    dst.write_bytes(dst.read_bytes().replace(b"\r\n", b"\n"))
    assert hashlib.sha256(dst.read_bytes()).hexdigest() != recorded, "premise -- raw differs"
    assert G.hash_match(str(dst), recorded) == "sidecar_lf"
