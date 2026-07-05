"""gate_verdict_hub_gen -- STAGING ONLY generator for the whole-population
'Honest Verdicts' hub note.

Extracted from claims_dossier_gen.py (which now stays scoped to per-entity
dossiers) to keep both files under the 300 LOC/file rail. Gate-verdict claims
describe a whole population's verdict (e.g. a gate SHIP/REJECT), not one
entity -- they never get a per-entity dossier section; they get exactly one
hub note here instead.

Reads:
  - data/frontend/ops/intel_verdict_claims_validation.json (verdict rows)
  - data/cache/intel_claims/gate_verdict_claims.jsonl (claim bodies)

Writes:
  - data/cache/vault_feed_staging/atlas_hubs/honest_verdicts_hub.md

Rules (binding, see LANE spec):
  - VERIFIED-only: MISMATCH/UNVERIFIABLE rows excluded.
  - Fail-open: missing inputs -> no file written, returns 0.
  - No edge/ROI phrasing anywhere in generated text.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

GATE_VERDICT_VALIDATION_PATH = REPO_ROOT / "data/frontend/ops/intel_verdict_claims_validation.json"
GATE_VERDICT_CLAIMS_PATH = REPO_ROOT / "data/cache/intel_claims/gate_verdict_claims.jsonl"
GATE_VERDICT_HUB_OUT_DIR = REPO_ROOT / "data/cache/vault_feed_staging/atlas_hubs"


def build_gate_verdict_hub(validation_path: Path = GATE_VERDICT_VALIDATION_PATH,
                            claims_path: Path = GATE_VERDICT_CLAIMS_PATH,
                            out_dir: Path = GATE_VERDICT_HUB_OUT_DIR) -> int:
    """Write a single whole-population 'Honest Verdicts' hub note.

    Gate-verdict claims describe a whole population, not one entity -- they never
    get per-entity dossiers. VERIFIED-only: MISMATCH/UNVERIFIABLE rows are excluded.
    Fail-open: missing inputs -> no file written, returns 0.
    """
    if not validation_path.exists() or not claims_path.exists():
        return 0
    try:
        val_doc = json.loads(validation_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    verified_ids = {
        row["claim_id"] for row in val_doc.get("details", [])
        if row.get("verdict") == "VERIFIED"
    }
    if not verified_ids:
        return 0

    bodies = {}
    try:
        for line in claims_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            bodies[d["claim_id"]] = d
    except (json.JSONDecodeError, OSError):
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    lines = ["## Honest Verdicts Hub", ""]
    for claim_id in sorted(verified_ids):
        claim = bodies.get(claim_id)
        if claim is None:
            continue
        verdict = claim.get("verdict", "")
        primary = claim.get("primary_number", "")
        gate_module = claim.get("gate_module", "")
        lines.append(f"- {claim_id} | verdict={verdict} | primary={primary} | gate={gate_module}")
    lines.append("")
    n = len(lines) - 2
    (out_dir / "honest_verdicts_hub.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return n


if __name__ == "__main__":
    n_verdicts = build_gate_verdict_hub()
    print(f"honest_verdicts_hub written: {n_verdicts} verdict lines")
