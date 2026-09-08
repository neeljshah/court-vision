"""S313 attempt 3 -- replay the harness-receipt -> answer round trip.

Replays the label-survival check from the COMMITTED envelopes, recomputes one
landed loss from its archived per-tick rows, and proves the resolver withholds
a number on a corrupted receipt, a missing ledger, a stale ledger, a flipped
basis and a runtime-tracking request, and dates every answer by its OLDEST
named input rather than by the newer ledger quoting it.

Run this file alone, with confcutdir pointed at the platformkit test package.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ART = ROOT / "docs/evidence/harness/S313_attempt3_artifact"
LEDGER = ROOT / "domains/basketball_nba/knowledge/validation_ledger.jsonl"
S293_ROWS = ROOT / ("docs/evidence/harness/"
                    "S293_tail_metric_rail_attempt2_2026-09-07_paired_losses.csv.gz")

EXPECTED = {"R1": "NULL", "R2": "CLOSED AT LIMIT", "R3": "NOT_TESTABLE", "R4": "BEHIND"}

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def routes() -> dict:
    data = json.loads((ART / "envelopes_pass1.json").read_text(encoding="utf-8"))
    return {r["id"]: r for r in data["routes"]}


@pytest.fixture()
def registry(monkeypatch):
    """`_LEDGER_PATHS` values are repo-relative, so every call must run from ROOT."""
    from scripts.platformkit.answers import resolver_registry as R
    monkeypatch.chdir(ROOT)
    return R


def _numeric(env: dict) -> bool:
    """True when the envelope actually asserts a number."""
    if env.get("status") != "ok":
        return False
    return any(f.get("effect_local") is not None for f in env.get("findings", []))


# --- label survival ---------------------------------------------------------

def test_committed_envelopes_carry_each_label_verbatim(routes):
    for rid, label in EXPECTED.items():
        env = routes[rid]["envelope"]
        assert env["status"] == "ok", rid
        assert env["findings"][0]["verdict"] == label, (rid, env["findings"][0]["verdict"])
        assert label in routes[rid]["composed_answer"], rid


def test_every_answer_cites_artifact_and_as_of(routes):
    for rid in EXPECTED:
        env = routes[rid]["envelope"]
        assert env.get("source_artifact"), rid
        assert env.get("as_of"), rid


def test_out_of_domain_route_withholds_the_numeric_claim(routes):
    env = routes["R5"]["envelope"]
    assert env["status"] != "ok"
    assert not _numeric(env)
    assert "NOT_SUPPORTED" in routes["R5"]["composed_answer"]


# --- live re-resolution (real landed receipt -> answer) ---------------------

def test_live_resolve_reproduces_every_committed_finding(routes, registry):
    for rid in EXPECTED:
        got = registry.resolve(routes[rid]["question"], "nba")
        want = routes[rid]["envelope"]
        assert got["status"] == "ok", rid
        assert got["findings"] == want["findings"], rid
        assert got["source_artifact"] == want["source_artifact"], rid
        assert got["as_of"], rid  # mtime moves with the checkout; presence is the contract


def test_as_of_is_the_oldest_named_input_when_the_ledger_is_newer(routes, registry):
    """Derived freshness may never outrun its oldest required input (S313 spec bar)."""
    from datetime import datetime, timezone

    from scripts.platformkit.answers import receipt_guard as G
    rows = [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]
    ledger_mtime = os.path.getmtime(LEDGER)
    for rid in EXPECTED:
        env = registry.resolve(routes[rid]["question"], "nba")
        named = [ROOT / m.group("path")
                 for r in rows if r["hypothesis"] == env["hypothesis"]
                 for m in G._REF_RE.finditer(r["note"])]
        assert named, f"{rid} names no artifact, so it has no freshness floor"
        oldest = min(os.path.getmtime(p) for p in named)
        assert oldest < ledger_mtime, f"{rid}: premise -- the ledger must be the newer file"
        assert env["as_of"] == datetime.fromtimestamp(oldest, tz=timezone.utc).isoformat(), rid


def test_landed_s293_loss_recomputes_from_its_archived_rows(routes):
    """Recompute from the archived per-tick rows themselves, not from the summary."""
    candidate, recal_null = [], []
    with gzip.open(S293_ROWS, "rt", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["tail_log_loss"]:
                candidate.append(float(row["tail_log_loss"]))
                recal_null.append(float(row["tail_recal_null_log_loss"]))
    answered = routes["R4"]["envelope"]["findings"][0]
    recomputed = (math.fsum(recal_null) - math.fsum(candidate)) / len(candidate)
    assert len(candidate) == answered["n"] == 308756
    assert abs(recomputed - answered["effect_local"]) < 1e-9
    assert str(answered["effect_local"]) in routes["R4"]["composed_answer"]


# --- fail-closed surfaces ---------------------------------------------------

def _point_ledger(monkeypatch, registry, path) -> None:
    monkeypatch.setitem(registry._LEDGER_PATHS, "nba", str(path))


def test_a_corrupted_receipt_never_yields_a_number(monkeypatch, registry, tmp_path, routes):
    """Corrupt the RECEIPT, not the ledger syntax: flip one hex digit of the
    sha256 the row quotes. The ledger still parses and the row still carries its
    number, so it is the receipt hash check -- not a parse error -- that refuses.
    """
    from scripts.platformkit.answers import receipt_guard as G
    corrupt = tmp_path / "corrupt_receipt.jsonl"
    rows = [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]
    row = next(r for r in rows if r["hypothesis"] == "s310_ingame_tail_beta_offset")
    ref = G._REF_RE.search(row["note"])
    assert ref, "premise -- the S310 row must quote a receipt hash to corrupt"
    sha = ref.group("sha")
    row["note"] = row["note"].replace(sha, sha[:-1] + ("0" if sha[-1] != "0" else "1"))
    corrupt.write_text(json.dumps(row) + "\n", encoding="utf-8")
    _point_ledger(monkeypatch, registry, corrupt)
    env = registry.resolve(routes["R2"]["question"], "nba")
    assert env["status"] == "no_data", env["status"]
    assert not _numeric(env)
    assert "findings" not in env
    assert "no longer hashes" in env["note"] and ref.group("path") in env["note"]


def test_missing_ledger_refuses_with_no_data(monkeypatch, registry, tmp_path, routes):
    _point_ledger(monkeypatch, registry, tmp_path / "absent.jsonl")
    env = registry.resolve(routes["R2"]["question"], "nba")
    assert env["status"] == "no_data"
    assert not _numeric(env)


def test_a_stale_ledger_refuses_instead_of_answering(monkeypatch, registry, tmp_path, routes):
    """Derived freshness may never outrun its oldest required input (S313 spec bar).

    S319 re-expressed this SETUP only. The staleness used to be built by back-dating
    the ledger FILE's mtime, and mtime is exactly what git does not preserve, so that
    construct made every route refuse on a fresh checkout. The staleness is now built
    where the guard reads it: the row's own recorded date. The test's name and every
    assertion below are unchanged.
    """
    stale = tmp_path / "stale.jsonl"
    rows = [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]
    keep = [r for r in rows if r["hypothesis"] == "s310_ingame_tail_beta_offset"]
    assert keep, "the S310 receipt row must be on the ledger"
    row = dict(keep[0])
    row["run_ts"] = "2017-07-14T00:00:00Z"  # older than every receipt the row names
    stale.write_text(json.dumps(row) + "\n", encoding="utf-8")
    _point_ledger(monkeypatch, registry, stale)
    env = registry.resolve(routes["R2"]["question"], "nba")
    assert env["status"] == "no_data", env["status"]
    assert not _numeric(env)
    assert "findings" not in env
    assert "stale" in env["note"] and "S310_tail_beta_offset_2026-09-07.md" in env["note"]


def test_a_flipped_basis_refuses_instead_of_returning_the_flipped_number(
        monkeypatch, registry, tmp_path, routes):
    """A sign-flipped effect no longer reproduces its receipt, so the route refuses."""
    flipped = tmp_path / "flipped.jsonl"
    rows = [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]
    row = next(r for r in rows if r["hypothesis"] == "s293_tail_log_loss_rail")
    row["effect"] = -row["effect"]
    flipped.write_text(json.dumps(row) + "\n", encoding="utf-8")
    _point_ledger(monkeypatch, registry, flipped)
    env = registry.resolve(routes["R4"]["question"], "nba")
    assert env["status"] == "no_data", env["status"]
    assert not _numeric(env)
    assert "findings" not in env
    assert "S293_tail_metric_rail_attempt2_2026-09-07.md" in env["note"]


def test_teacher_route_emits_no_number_and_no_runtime_tracking_read(routes):
    f = routes["R3"]["envelope"]["findings"][0]
    assert f["verdict"] == "NOT_TESTABLE"
    assert f["effect_local"] is None and f["n"] is None
    note = f["note"]
    assert "prerequisite=S312" in note and "blocking_row=S314" in note
    assert "never a runtime tracking read" in note
    src = (ROOT / "scripts/platformkit/answers/resolver_registry.py").read_text(encoding="utf-8")
    assert "src.tracking" not in src and "src/tracking" not in src
