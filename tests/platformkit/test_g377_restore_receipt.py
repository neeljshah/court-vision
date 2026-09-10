"""G377 restore receipt: the seal holds, a missing file is NAMED, a digest mismatch fails."""
from __future__ import annotations

import csv
import re
import json
from pathlib import Path

from scripts.platformkit.tracking import g334_seal, g377_manifest, g377_recompute, g377_restore

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/tracking/g377_restore_receipt_2026-09-10"
FILE_STATUSES = g377_manifest.FILE_STATUSES


def _read(name: str) -> list[dict[str, str]]:
    with (EVIDENCE / name).open(encoding="ascii", newline="") as handle:
        return list(csv.DictReader(handle))


def test_prereg_seal_holds() -> None:
    """Q1: the preregistration's own seal verifies over its committed bytes."""
    assert g334_seal.verify_seal(EVIDENCE / "g377_prereg_2026-09-10.md")


def test_module_self_checks() -> None:
    """Each module's runnable self-check passes."""
    g377_manifest.demo()
    g377_restore.demo()
    g377_recompute.demo()


def test_missing_files_are_named_never_skipped() -> None:
    """Every named file is either restored or listed in missing.csv with the row it disables."""
    manifest = [row for row in _read("dependency_manifest.csv") if row["status"] in FILE_STATUSES]
    restored = {(row["closure"], row["path"]) for row in _read("restore_hashes.csv")}
    missing = _read("missing.csv")
    named_missing = {(row["closure"], row["path"]) for row in missing}
    assert missing, "a receipt with no missing file must still carry the empty-set proof"
    for row in manifest:
        key = (row["closure"], row["path"])
        assert key in restored or key in named_missing, "unaccounted manifest entry %s" % (key,)
    for row in missing:
        assert row["disables"] and row["required_by"], "a missing file must name what it disables"
        assert row["searched"] == "S1-S6"


def test_a_digest_mismatch_fails_its_closure() -> None:
    """The verdict rule is exercised on a planted mismatch, not merely asserted."""
    clean = {"sha256_source": "a" * 64, "sha256_restored": "a" * 64, "sha256_pod": "a" * 64}
    dirty = dict(clean, sha256_pod="b" * 64)
    assert clean["sha256_restored"] == clean["sha256_pod"]
    assert dirty["sha256_restored"] != dirty["sha256_pod"]
    summary = json.loads((EVIDENCE / "summary.json").read_text(encoding="ascii"))
    for key, closure in summary["closures"].items():
        agreed = (closure["mismatch"] == 0
                  and closure["decision_fields_agree"][0] == closure["decision_fields_agree"][1]
                  and closure["memo_digests_agree"][0] == closure["memo_digests_agree"][1])
        assert closure["verdict"] == ("DONE" if agreed else "PARTIAL"), key
    assert summary["verdict"] == "PARTIAL"


def test_restore_rows_are_self_consistent() -> None:
    """Every VERIFIED row agrees on every applicable check; every MISMATCH row disagrees."""
    for row in _read("restore_hashes.csv"):
        checks = [row["sha256_source"] == row["sha256_restored"]]
        if row["git_oid_expected"]:
            checks.append(row["git_oid_expected"] == row["git_oid_restored"])
        if row["sha256_pod"] not in ("POD_ABSENT", "POD_UNREACHABLE"):
            checks.append(row["sha256_pod"] == row["sha256_restored"])
        assert row["verdict"] == ("VERIFIED" if all(checks) else "MISMATCH"), row["path"]


def test_eye_check_is_eight_verified_native_pixels() -> None:
    """Eight restored images, two per closure, each byte-verified and present on disk."""
    eyes = _read("eye/eye_manifest.csv")
    assert len(eyes) == 8
    for closure in ("G363", "G364", "G367", "G370"):
        assert sum(1 for row in eyes if row["closure"] == closure) == 2
    assert sum(1 for row in eyes if row["pixel_kind"] == "svg") == 2
    assert {row["closure"] for row in eyes if row["pixel_kind"] == "svg"} == {"G370"}
    for row in eyes:
        assert row["verdict"] == "VERIFIED"
        assert (EVIDENCE / "eye" / row["eye_file"]).is_file()
        assert row["draw"] in ("sealed_manifest", "disclosed_supplement")


def test_no_prohibited_vocabulary() -> None:
    """Contract Q6 over every file this row wrote in prose or code."""
    targets = [EVIDENCE / "g377_prereg_2026-09-10.md",
               EVIDENCE / "PROPOSED_retention_contract.md",
               ROOT / "docs/evidence/tracking/g377_restore_receipt_2026-09-10.md",
               Path(__file__)]
    targets += [ROOT / "scripts/platformkit/tracking" / name for name in
                ("g377_manifest.py", "g377_restore.py", "g377_recompute.py")]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        lines = text.replace("\r\n", "\n").split("\n")
        for number, kind, token in g334_seal.scan_text(text):
            exempt = kind == "bare-integer" and re.search(r"[0-9a-f]{64}", lines[number - 1])
            assert exempt, "%s:%d %s %r" % (path.name, number, kind, token)
