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
  - FULL POPULATION, no cap here: every VERIFIED ranking row above its own
    min_sample floor gets a line (a capped dossier traces to the upstream
    claim producer, e.g. basketball_claims.py's TOP_N, not this module).
  - CLAIM_ID_TO_FILE / EXTRA_VALIDATION_PATHS is a STATIC registry, not a
    glob -- a prefix that matches zero real claim_ids silently starves that
    source (fixed once: "nba_shooting_" matched none of
    nba_shooting_claims.jsonl's 20 per-dimension ids; see
    test_claim_id_to_file_prefixes_match_real_on_disk_claim_ids).
  - _slugify() strips Windows-illegal filename chars from fallback ids
    (e.g. "ATL|BIG" -> "atlbig") so a raw id never crashes the write.

Provenance line format (one per claim, per entity):
  claim_id | metric | value (precision) | source_files | validator=VERIFIED @ generated_at
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.vault_feed.dossier_registry import (
    CLAIM_ID_TO_FILE,
    ENTITY_KEY_NAME_FIELD,
    EXTRA_VALIDATION_PATHS,
    PAIR_ENTITY_KEY_NAME_FIELDS,
    REPO_ROOT,
)

VALIDATION_PATH = REPO_ROOT / "data/frontend/ops/intel_claims_validation.json"
CLAIMS_DIR = REPO_ROOT / "data/cache/intel_claims"
OUT_DIR = REPO_ROOT / "data/cache/vault_feed_staging/dossier_sections"


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


# Windows filename-illegal characters (also unwelcome in slugs generally).
# Seen in the wild: nba_fit_role_vacancy_by_team_posgroup_current's fallback
# id "ATL|BIG" (pipe) crashed write_text with OSError: Invalid argument.
_SLUG_ILLEGAL = str.maketrans("", "", '<>:"/\\|?*')


def _slugify(name: str) -> str:
    return (
        name.strip().lower()
        .replace(" ", "_").replace(".", "").replace("'", "")
        .translate(_SLUG_ILLEGAL)
    )


def _provenance_line(claim_id: str, metric: str, value, precision, source_files, generated_at: str) -> str:
    val_str = f"{value:.{precision}f}" if isinstance(value, (int, float)) and precision is not None else str(value)
    srcs = ", ".join(source_files) if source_files else ""
    return f"{claim_id} | {metric} | {val_str} ({precision}) | {srcs} | validator=VERIFIED @ {generated_at}"


_DEFAULT = object()


def build_dossier_sections(validation_path: Path = VALIDATION_PATH,
                            claims_dir: Path = CLAIMS_DIR,
                            out_dir: Path = OUT_DIR,
                            extra_validation_paths=_DEFAULT) -> dict:
    """Generate per-entity dossier section files. Returns {entity_slug: n_claim_lines} for verification.

    extra_validation_paths defaults to EXTRA_VALIDATION_PATHS only when the caller uses the
    default validation_path/claims_dir/out_dir (i.e. the real repo run); callers that pass
    their own tmp paths (tests) get an empty list unless they opt in explicitly, so isolated
    fail-open tests are not polluted by real repo artifacts.
    """
    if extra_validation_paths is _DEFAULT:
        extra_validation_paths = (
            EXTRA_VALIDATION_PATHS
            if validation_path == VALIDATION_PATH and claims_dir == CLAIMS_DIR and out_dir == OUT_DIR
            else []
        )
    verified = _load_verified_claim_ids(validation_path)
    for extra_path in extra_validation_paths:
        verified.update(_load_verified_claim_ids(extra_path))
    if not verified:
        return {}
    bodies = _load_claim_bodies(claims_dir)

    # entity -> list of (claim_id, line)
    entity_lines: dict = {}
    # entity -> set of claim_ids whose caveats must render in that entity's section
    entity_caveat_claims: dict = {}
    for claim_id, generated_at in sorted(verified.items()):
        claim = bodies.get(claim_id)
        if claim is None or claim.get("kind") != "ranking":
            continue
        entity_key = _entity_key_field(claim)
        metric = claim.get("criteria", {}).get("metric", claim_id)
        precision = claim.get("criteria", {}).get("value_precision", 4)
        source_files = claim.get("source_files", [])

        pair_fields = None
        if isinstance(entity_key, list) and len(entity_key) == 2:
            pair_fields = PAIR_ENTITY_KEY_NAME_FIELDS.get(tuple(entity_key))

        if pair_fields is not None:
            (id_a, id_b), (name_a, name_b) = (tuple(entity_key), pair_fields)
            for row in claim.get("ranking", []):
                n1, n2 = row.get(name_a), row.get(name_b)
                if not n1 or not n2:
                    continue
                s1 = _slugify(n1)
                s2 = _slugify(n2)
                # deterministic pair slug: lower id first
                if row.get(id_a, 0) <= row.get(id_b, 0):
                    slug, name = f"{s1}_vs_{s2}", f"{n1} vs {n2}"
                else:
                    slug, name = f"{s2}_vs_{s1}", f"{n2} vs {n1}"
                line = _provenance_line(claim_id, metric, row.get("value"), precision, source_files, generated_at)
                entity_lines.setdefault(slug, {"name": name, "lines": []})
                entity_lines[slug]["lines"].append((row.get("rank"), line))
                if claim.get("caveats"):
                    entity_caveat_claims.setdefault(slug, set()).add(claim_id)
            continue

        if not isinstance(entity_key, str):
            continue
        name_field = ENTITY_KEY_NAME_FIELD.get(entity_key)
        if entity_key not in ENTITY_KEY_NAME_FIELD:
            continue
        for row in claim.get("ranking", []):
            name = row.get(name_field) if name_field else None
            if not name:
                # fall back to the raw entity id as the display name
                raw_id = row.get(entity_key)
                if raw_id is None:
                    continue
                name = str(raw_id)
            slug = _slugify(str(name))
            line = _provenance_line(claim_id, metric, row.get("value"), precision, source_files, generated_at)
            entity_lines.setdefault(slug, {"name": name, "lines": []})
            entity_lines[slug]["lines"].append((row.get("rank"), line))
            if claim.get("caveats"):
                entity_caveat_claims.setdefault(slug, set()).add(claim_id)

    out_dir.mkdir(parents=True, exist_ok=True)
    # Clear stale dossiers from prior waves before writing the current VERIFIED set,
    # so re-runs never accrete orphan files backed by claims that are no longer
    # VERIFIED (e.g. a source flipping to UNVERIFIABLE between waves). Deterministic:
    # removes exactly the *.md files present, independent of OS iteration order.
    for stale in sorted(out_dir.glob("*.md")):
        stale.unlink()
    counts = {}
    for slug, payload in sorted(entity_lines.items()):
        lines = sorted(payload["lines"], key=lambda t: (t[1].split(" | ")[0], t[0]))
        body_lines = [f"## Validated Intelligence: {payload['name']}", ""]
        for _, line in lines:
            body_lines.append(f"- {line}")
        caveat_claim_ids = entity_caveat_claims.get(slug)
        if caveat_claim_ids:
            body_lines.append("")
            body_lines.append("**Caveats:**")
            for claim_id in sorted(caveat_claim_ids):
                claim = bodies.get(claim_id, {})
                for caveat in claim.get("caveats", []):
                    body_lines.append(f"- ({claim_id}) {caveat}")
        body_lines.append("")
        (out_dir / f"{slug}.md").write_text("\n".join(body_lines), encoding="utf-8", newline="\n")
        counts[slug] = len(lines)
    return counts


# build_gate_verdict_hub moved to gate_verdict_hub_gen.py (kept this module
# under the 300 LOC/file rail; it covers a different concern -- one whole-
# population verdict hub note, not per-entity dossiers). Re-exported here so
# any existing `from claims_dossier_gen import build_gate_verdict_hub` caller
# keeps working unchanged.
from scripts.platformkit.vault_feed.gate_verdict_hub_gen import (  # noqa: E402
    GATE_VERDICT_CLAIMS_PATH,
    GATE_VERDICT_HUB_OUT_DIR,
    GATE_VERDICT_VALIDATION_PATH,
    build_gate_verdict_hub,
)

if __name__ == "__main__":
    counts = build_dossier_sections()
    print(f"dossier_sections written: {len(counts)} entity files, "
          f"{sum(counts.values())} total claim lines")
    n_verdicts = build_gate_verdict_hub()
    print(f"honest_verdicts_hub written: {n_verdicts} verdict lines")
