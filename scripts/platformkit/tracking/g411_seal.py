"""G411 sealing stage: input hashes, fresh reproductions, Q6 scan, SHA256SUMS."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.platformkit.tracking import g411_q6 as Q6  # noqa: E402
from scripts.platformkit.tracking.g411_extract import write_csv  # noqa: E402

EV = ROOT / "docs/evidence/tracking"
G401 = EV / "g401_fps_cap_duration_shadow_2026-09-11"
G408 = EV / "g408_pts_duration_stop_proposal_2026-09-11"
OUT = EV / "g411_integer_pts_extent_audit_2026-09-12"
CODE = ROOT / "scripts/platformkit/tracking"
MEMO = EV / "g411_integer_pts_extent_audit_2026-09-12.md"
TEST = ROOT / "tests/platformkit/test_g411_integer_pts_extent.py"
OWNED = ("g411_prepare.py", "g411_q6.py", "g411_rational.py", "g411_read.py",
         "g411_measure.py", "g411_extract.py", "g411_rows.py", "g411_run.py",
         "g411_seal.py")
REPRO_SKIP = {"reproductions", "integer_pts", "common_receipts",
               "runtime_receipts", "pre_fix1b", "pre_fix1c", "pre_fix1d",
               "pre_fix1e"}


def digest(path: Path) -> str:
    """SHA-256 over raw stored bytes."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def input_hashes() -> list:
    """Hash every inherited input, owned module and retained source."""
    rows = []
    for label, path in [("g401/draw.csv", G401 / "draw.csv"),
                        ("g401/pts.csv", G401 / "pts.csv"),
                        ("g401/paired_caps.csv", G401 / "paired_caps.csv"),
                        ("g408/paired_stops.csv", G408 / "paired_stops.csv"),
                        ("g408/g401_pts_rows.csv", G408 / "g401_pts_rows.csv"),
                        ("g408/pts_anomalies.csv", G408 / "pts_anomalies.csv"),
                        ("g408/summary.json", G408 / "summary.json"),
                        ("g411/prereg.md", OUT / "prereg.md"),
                        ("g411/test", TEST)]:
        rows.append({"role": "input", "label": label, "path": _rel(path),
                     "bytes": path.stat().st_size, "sha256": digest(path)})
    for name in sorted(p.name for p in (G408 / "g401_frame_pts").iterdir()):
        path = G408 / "g401_frame_pts" / name
        rows.append({"role": "archived_decimal_schedule", "label": name,
                     "path": _rel(path), "bytes": path.stat().st_size,
                     "sha256": digest(path)})
    for name in OWNED:
        path = CODE / name
        if path.exists():
            rows.append({"role": "regenerating_code", "label": name,
                         "path": _rel(path), "bytes": path.stat().st_size,
                         "sha256": digest(path)})
    return rows


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def delivered_tables(base: Path) -> dict:
    """Digest every regenerated table and card under one directory."""
    rows = {}
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(base).parts
        if parts[0] in REPRO_SKIP or path.name in {"SHA256SUMS", "prereg.md",
                                                   "PREPARE_ONLY.md",
                                                   "input_hashes.csv",
                                                   "repeats.json",
                                                   "q6_scan.json",
                                                   "extraction_receipts.json",
                                                   "source_receipts.csv",
                                                   "time_bases.csv",
                                                   "draw.csv",
                                                   "ledger_rows_g411.txt"}:
            continue
        rows[str(path.relative_to(base)).replace("\\", "/")] = digest(path)
    return rows


def reproduce(times: int = 2) -> dict:
    """Run the measurement stage in fresh processes from delivered bytes."""
    delivered = delivered_tables(OUT)
    runs = []
    for index in range(1, times + 1):
        target = OUT / "reproductions" / ("fresh_%d" % index)
        if target.exists():
            shutil.rmtree(target)
        argv = [sys.executable, "-m", "scripts.platformkit.tracking.g411_run",
                "--tag", "fresh_%d" % index, "--out", str(target)]
        done = subprocess.run(argv, capture_output=True, text=True, cwd=str(ROOT))
        tables = delivered_tables(target)
        same = {key: value for key, value in tables.items() if key != "summary.json"}
        base = {key: value for key, value in delivered.items()
                if key != "summary.json"}
        runs.append({"command": " ".join(argv), "returncode": done.returncode,
                     "identical": same == base,
                     "stdout_sha256": hashlib.sha256(
                         done.stdout.encode()).hexdigest(),
                     "stdout": done.stdout.strip()[:2000],
                     "stderr_head": done.stderr[:400],
                     "per_table_sha256": tables})
    return {"scope": "every delivered table and all 30 timeline cards, "
                     "regenerated from delivered bytes only "
                     "(summary.json carries a run tag and is compared apart)",
            "sealed_inputs": ["g411/integer_pts/", "g408/g401_frame_pts/",
                              "g408/paired_stops.csv", "g408/g401_pts_rows.csv",
                              "g401/draw.csv", "g411/source_receipts.csv"],
            "delivered_sha256": delivered, "runs": runs,
            "identical": all(run["identical"] and run["returncode"] == 0
                             for run in runs),
            "note": "table reproduction only; this does not prove inference "
                    "repeatability"}


def q6_scan() -> dict:
    """Scan every touched text path, the scanner and the memo included."""
    paths = [path for path in OUT.rglob("*") if path.is_file()
             and path.name != "ledger_rows_g411.txt"]
    paths += [CODE / name for name in OWNED if (CODE / name).exists()]
    paths += [TEST]
    if MEMO.exists():
        paths.append(MEMO)
    # fix 1b: the touched shared results log enters the manifest; G411's own
    # rows are scanned as a delivered receipt, the whole inherited log apart.
    ledger = EV / "RESULTS_LEDGER.md"
    own = [line for line in ledger.read_text(encoding="ascii").split(chr(10))
           if "| G411 |" in line]
    rows_path = OUT / "ledger_rows_g411.txt"
    rows_path.write_bytes((chr(10).join(own) + chr(10)).encode("ascii"))
    scan = Q6.scan_paths(paths, ROOT)
    shared = Q6.scan_paths([ledger], ROOT)
    own_scan = Q6.scan_paths([rows_path], ROOT)
    scan["shared_log_scan"] = {
        "path": "docs/evidence/tracking/RESULTS_LEDGER.md",
        "hits": shared["hits"],
        "non_opaque_hit_count": shared["non_opaque_hit_count"],
        "own_rows_receipt": "ledger_rows_g411.txt",
        "own_rows_opaque_hits": own_scan["hits"],
        "note": "whole inherited shared log scanned for the manifest; its hits "
                "are shared-log context, not G411 prose; the required ledger "
                "receipt is retained as an opaque artifact"}
    return scan


def write_sums() -> int:
    """Write SHA256SUMS with a byte-domain declaration on line 1."""
    lines = ["BYTE-DOMAIN: SHA-256 is computed over raw stored bytes; draw.csv "
             "is a byte-identical CRLF copy of the inherited G401 draw and "
             "every other artifact here is LF-terminated ASCII text."]
    count = 0
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            lines.append("%s  %s" % (digest(path),
                                     str(path.relative_to(OUT)).replace("\\", "/")))
            count += 1
    (OUT / "SHA256SUMS").write_bytes(
        (chr(10).join(lines) + chr(10)).encode("ascii"))
    return count


def _common_receipts() -> None:
    """Record the drawn names and the PC-only execution context."""
    base = OUT / "common_receipts"
    base.mkdir(parents=True, exist_ok=True)
    names = [row.split(",")[2] for row in
             (G401 / "draw.csv").read_text().splitlines()[1:]]
    (base / "draw_names.txt").write_bytes(
        (chr(10).join(names) + chr(10)).encode("ascii"))
    (base / "pc_receipt.json").write_bytes((json.dumps({
        "pod_stage": "none; G411 is a PC-only row",
        "gpu_used": False, "models_exercised": [],
        "retained_sources_root": "C:/Users/neelj/g401_receiver/sources",
        "scratch_root": "C:/Users/neelj/AppData/Local/Temp/g411_work",
        "sources_read_only": True}, indent=1, sort_keys=True) + chr(10)).encode("ascii"))


def _runtime_receipts() -> None:
    """Copy the scratch stage logs in as LF `.log.txt` receipts."""
    base = OUT / "runtime_receipts"
    base.mkdir(parents=True, exist_ok=True)
    scratch = Path("C:/Users/neelj/AppData/Local/Temp/g411_work")
    for name in ("extract.log", "run.log", "test.log"):
        source = scratch / name
        if source.exists():
            text = source.read_text(encoding="utf-8", errors="replace")
            content = text.replace("\r\n", chr(10)).encode("ascii", "replace")
            (base / (name.split(".")[0] + ".log.txt")).write_bytes(content)


def main() -> int:
    """Seal the directory: draw copy, hashes, reproductions, scan, sums."""
    shutil.copyfile(G401 / "draw.csv", OUT / "draw.csv")
    _common_receipts()
    write_csv(OUT / "input_hashes.csv",
              ("role", "label", "path", "bytes", "sha256"), input_hashes())
    repeats = reproduce()
    (OUT / "repeats.json").write_bytes(
        (json.dumps(repeats, indent=1, sort_keys=True) + chr(10)).encode("ascii"))
    _runtime_receipts()
    scan = q6_scan()
    (OUT / "q6_scan.json").write_bytes(
        (json.dumps(scan, indent=1, sort_keys=True) + chr(10)).encode("ascii"))
    count = write_sums()
    print(json.dumps({"reproductions_identical": repeats["identical"],
                      "runtime_receipts": len(list(
                          (OUT / "runtime_receipts").glob("*"))),
                      "q6_non_opaque_hits": scan["non_opaque_hit_count"],
                      "q6_scanned_paths": scan["scanned_count"],
                      "sha256sums_files": count}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
