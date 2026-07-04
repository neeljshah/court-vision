"""claims_dossier_gen -- STAGING ONLY generator for per-entity 'Validated Intelligence'
markdown sections.

Reads:
  - data/frontend/ops/intel_claims_validation.json (verdict rows: claim_id -> VERIFIED/MISMATCH/UNVERIFIABLE)
  - data/cache/intel_claims/*.jsonl (the claim bodies: ranking entries with source_files, criteria)

Writes:
  - data/cache/vault_feed_staging/dossier_sections/<entity>.md  (one file per ranked entity)

Rules (binding, see LANE spec):
  - NEVER include a MISMATCH or UNVERIFIABLE claim -- VERIFIED only.
  - NEVER include a claim whose kind is not 'ranking' with a resolvable entity_key
    (e.g. gate_verdict rows describe a whole-population verdict, not one entity --
    they are skipped here by design; they belong in an aggregate summary, not a dossier).
  - Fail-open: if the validation file or a referenced claims JSONL is absent, skip
    silently (never fabricate a claim).
  - Deterministic + idempotent: same inputs -> byte-identical outputs. No wall-clock
    timestamps in file bodies except the claim's own `generated_at` (from the
    validation record) quoted verbatim.
  - No edge/ROI phrasing anywhere in generated text.

Provenance line format (one per claim, per entity):
  claim_id | metric | value (precision) | source_files | validator=VERIFIED @ generated_at
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATION_PATH = REPO_ROOT / "data/frontend/ops/intel_claims_validation.json"
CLAIMS_DIR = REPO_ROOT / "data/cache/intel_claims"
OUT_DIR = REPO_ROOT / "data/cache/vault_feed_staging/dossier_sections"

# claim_id prefix -> claims jsonl filename (only ranking claims from these files are eligible)
CLAIM_ID_TO_FILE = {
    "nba_shooting_": "nba_shooting_claims.jsonl",
    "nba_quality_": "nba_quality_claims.jsonl",
}


def _load_verified_claim_ids(validation_path: Path) -> dict:
    """Return {claim_id: generated_at} for claims marked VERIFIED. Fail-open to {}."""
    if not validation_path.exists():
        return {}
    try:
        doc = json.loads(validation_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    generated_at = doc.get("generated_at", "")
    out = {}
    for row in doc.get("details", []):
        if row.get("verdict") == "VERIFIED":
            out[row["claim_id"]] = generated_at
    return out


def _claims_file_for(claim_id: str) -> str | None:
    for prefix, fname in CLAIM_ID_TO_FILE.items():
        if claim_id.startswith(prefix):
            return fname
    return None


def _load_claim_bodies(claims_dir: Path) -> dict:
    """Return {claim_id: claim_dict} across all known jsonl files. Fail-open per file."""
    bodies = {}
    for fname in sorted(set(CLAIM_ID_TO_FILE.values())):
        fpath = claims_dir / fname
        if not fpath.exists():
            continue
        try:
            for line in fpath.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                bodies[d["claim_id"]] = d
        except (json.JSONDecodeError, OSError):
            continue
    return bodies


def _entity_key_field(claim: dict) -> str | None:
    return claim.get("criteria", {}).get("entity_key")


def _provenance_line(claim_id: str, metric: str, value, precision, source_files, generated_at: str) -> str:
    val_str = f"{value:.{precision}f}" if isinstance(value, (int, float)) and precision is not None else str(value)
    srcs = ", ".join(source_files) if source_files else ""
    return f"{claim_id} | {metric} | {val_str} ({precision}) | {srcs} | validator=VERIFIED @ {generated_at}"


def build_dossier_sections(validation_path: Path = VALIDATION_PATH,
                            claims_dir: Path = CLAIMS_DIR,
                            out_dir: Path = OUT_DIR) -> dict:
    """Generate per-entity dossier section files. Returns {entity_slug: n_claim_lines} for verification."""
    verified = _load_verified_claim_ids(validation_path)
    if not verified:
        return {}
    bodies = _load_claim_bodies(claims_dir)

    # entity -> list of (claim_id, line)
    entity_lines: dict = {}
    for claim_id, generated_at in sorted(verified.items()):
        claim = bodies.get(claim_id)
        if claim is None or claim.get("kind") != "ranking":
            continue
        entity_key = _entity_key_field(claim)
        if entity_key != "player_id":
            continue
        metric = claim.get("criteria", {}).get("metric", claim_id)
        precision = claim.get("criteria", {}).get("value_precision", 4)
        source_files = claim.get("source_files", [])
        for row in claim.get("ranking", []):
            name = row.get("player_name")
            if not name:
                continue
            slug = name.strip().lower().replace(" ", "_").replace(".", "").replace("'", "")
            line = _provenance_line(claim_id, metric, row.get("value"), precision, source_files, generated_at)
            entity_lines.setdefault(slug, {"name": name, "lines": []})
            entity_lines[slug]["lines"].append((row.get("rank"), line))

    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for slug, payload in sorted(entity_lines.items()):
        lines = sorted(payload["lines"], key=lambda t: (t[1].split(" | ")[0], t[0]))
        body_lines = [f"## Validated Intelligence: {payload['name']}", ""]
        for _, line in lines:
            body_lines.append(f"- {line}")
        body_lines.append("")
        (out_dir / f"{slug}.md").write_text("\n".join(body_lines), encoding="utf-8", newline="\n")
        counts[slug] = len(lines)
    return counts


if __name__ == "__main__":
    counts = build_dossier_sections()
    print(f"dossier_sections written: {len(counts)} entity files, "
          f"{sum(counts.values())} total claim lines")
