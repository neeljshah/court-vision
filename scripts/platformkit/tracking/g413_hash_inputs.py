"""Freeze G413 input identities before any measurement reads them."""
from __future__ import annotations

import csv
import hashlib
import io
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
G406 = ROOT / "docs/evidence/tracking/g406_masked_target_pixel_audit_2026-09-11"
G402 = ROOT / "docs/evidence/tracking/g402_mixed_provenance_target_mask_2026-09-11"
G412_ROOT = Path("C:/Users/neelj/nba-track-a3")
G412 = G412_ROOT / "docs/evidence/tracking/g412_box_frame_contract_2026-09-12"
MASTER_ROOT = Path("C:/Users/neelj/nba-ai-system")
MASTER_G412 = MASTER_ROOT / "docs/evidence/tracking/g412_box_frame_contract_2026-09-12"
G412_ACCEPTANCE = G412_ROOT / "docs/evidence/tracking/G412_VERIFY_att1_ACCEPT_WITH_CORRECTIONS_2026-09-11.md"
RECEIVER = Path("C:/Users/neelj/g402_receiver")
OUT = ROOT / "docs/evidence/tracking/g413_native_box_reaudit_2026-09-12"
DISPATCH_A3_TIP = "2fecca4e1"


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _row(role: str, path: Path, tip: str) -> dict[str, str]:
    body = path.read_bytes()
    return {
        "role": role,
        "path": path.resolve().as_posix(),
        "bytes": str(len(body)),
        "sha256_ondisk": _sha(body),
        "sha256_lf": _sha(body.replace(bytes((13, 10)), bytes((10,)))),
        "source_git_tip": tip,
        "dispatch_a3_tip": DISPATCH_A3_TIP if role == "g412" else "",
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator=chr(10))
    writer.writeheader()
    writer.writerows(rows)
    path.write_bytes(stream.getvalue().encode("utf-8"))


def freeze() -> dict[str, object]:
    """Hash every declared G413 input and copy the accepted transform verbatim."""
    OUT.mkdir(parents=True, exist_ok=True)
    tip = subprocess.check_output(["git", "-C", str(G412_ROOT), "rev-parse", "HEAD"], text=True).strip()
    routes = [ROOT / "scripts/platformkit/tracking/g413_contract.py",
              ROOT / "scripts/platformkit/tracking/g413_prepare.py",
              ROOT / "scripts/platformkit/tracking/g413_measure.py",
              ROOT / "scripts/platformkit/tracking/g413_finalize.py",
              ROOT / "scripts/platformkit/tracking/g406_audit.py",
              ROOT / "tests/platformkit/test_g413_native_box_reaudit.py"]
    g412_names = ("input_hashes.csv", "transforms.json", "route_chain.json", "construct_cases.csv",
                  "per_frame.csv", "summary.json", "SHA256SUMS")
    entries = [("g406", path, "") for path in sorted(G406.iterdir()) if path.is_file()]
    entries += [("g402", path, "") for path in sorted(G402.glob("*.csv"))]
    entries += [("g412", G412 / name, tip) for name in g412_names]
    entries += [("g412", G412_ROOT / "scripts/platformkit/tracking/g412_contract.py", tip)]
    entries += [("g412_acceptance_receipt", G412_ACCEPTANCE, "c53455110")]
    entries += [("g412_landed_memo", MASTER_G412.with_suffix(".md"), "5a0b84cba")]
    entries += [("g412_landed_transforms", MASTER_G412 / "transforms.json", "5a0b84cba")]
    entries += [("route", path, "") for path in routes]
    entries += [("receiver_candidate", path, "") for path in sorted(RECEIVER.glob("*.mp4"))]
    rows = [_row(role, path, source_tip) for role, path, source_tip in entries]
    _write_csv(OUT / "input_hashes.csv", rows)
    (OUT / "g412_transforms_handoff.json").write_bytes((G412 / "transforms.json").read_bytes())
    return {"input_rows": len(rows), "g412_tip": tip}


if __name__ == "__main__":
    result = freeze()
    print("input_rows=%d g412_tip=%s" % (result["input_rows"], result["g412_tip"]))
