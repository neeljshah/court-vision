"""Room builder: claims_index.json -- TWO separate corpora (SPEC v1.1).

preregistered: data/cache/claims/cards.jsonl + card_ledger.jsonl (~21k cards,
pre-registered before grading, joined to verdicts).
verified_facts: data/cache/intel_claims/*_claims_validation.json sidecars,
paired with each family's *_claims.jsonl.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.platformkit.showcase import common

CARDS = common.REPO / "data" / "cache" / "claims" / "cards.jsonl"
LEDGER = common.REPO / "data" / "cache" / "claims" / "card_ledger.jsonl"
INTEL_DIR = common.REPO / "data" / "cache" / "intel_claims"

SAMPLE_CAP = 2000
_SPORT_TOKENS = ("nba", "wnba", "mlb", "npb", "kbo", "soccer", "tennis", "atp", "wta")


def _derive_sport(text: str) -> str | None:
    low = text.lower()
    for tok in _SPORT_TOKENS:
        if tok in low:
            return tok
    return None


def _count_lines(path: Path) -> int:
    n = 0
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    n += 1
    except OSError:
        return 0
    return n


def _build_preregistered(asof: str) -> dict:
    if not CARDS.exists() or not LEDGER.exists():
        return common.unavailable("data/cache/claims/cards.jsonl or card_ledger.jsonl missing")

    ledger_rows = common.read_jsonl(LEDGER)
    ledger_by_id = {r["card_id"]: r for r in ledger_rows if "card_id" in r}
    verdict_counts: dict[str, int] = {}
    for r in ledger_by_id.values():
        v = r.get("verdict", "OPEN")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1

    total = _count_lines(CARDS)
    graded_ids = set(ledger_by_id)
    stride = max(1, total // SAMPLE_CAP) if total else 1

    graded_sample: list[dict] = []
    ungraded_pool: list[dict] = []
    idx = 0
    try:
        with CARDS.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                idx += 1
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                cid = row.get("card_id")
                claim_text = str(row.get("claim", ""))[:240]
                entry = {
                    "card_id": cid,
                    "claim": claim_text,
                    "sport": _derive_sport(claim_text + " " + str(row.get("source", ""))),
                    "verdict": ledger_by_id.get(cid, {}).get("verdict", "PENDING"),
                    "asof": row.get("registered_ts", asof),
                }
                if cid in graded_ids:
                    graded_sample.append(entry)
                elif idx % stride == 0 and len(ungraded_pool) < SAMPLE_CAP:
                    ungraded_pool.append(entry)
    except OSError:
        return common.unavailable("cards.jsonl unreadable mid-stream")

    remaining = max(0, SAMPLE_CAP - len(graded_sample))
    sample = graded_sample + ungraded_pool[:remaining]

    return {
        "total": total,
        "graded": len(ledger_by_id),
        "verdict_counts": verdict_counts,
        "sample": sample[:SAMPLE_CAP],
        "receipt": common.receipt(
            "Pre-registered prediction cards, graded against realized outcomes as data accrues.",
            total, "PROVISIONAL", CARDS, asof,
            reproduce="cat data/cache/claims/card_ledger.jsonl",
        ),
    }


def _build_verified_facts(asof: str) -> dict:
    if not INTEL_DIR.is_dir():
        return common.unavailable("data/cache/intel_claims/ missing")

    validation_files = sorted(INTEL_DIR.glob("*_claims_validation.json"))
    if not validation_files:
        return common.unavailable("no *_claims_validation.json sidecars found")

    n_families = len(validation_files)
    per_family_cap = max(1, SAMPLE_CAP // n_families)

    # raw corpus size: every generated claim row, not just the validated sample
    corpus_total = 0
    for jpath in INTEL_DIR.glob("*.jsonl"):
        if jpath.name.endswith(".index.jsonl"):
            continue
        try:
            with jpath.open(encoding="utf-8") as fh:
                corpus_total += sum(1 for line in fh if line.strip())
        except OSError:
            continue

    total = 0
    verified = 0
    mismatch = 0
    families: list[dict] = []
    sample: list[dict] = []

    for vpath in validation_files:
        family = vpath.name[: -len("_claims_validation.json")]
        vdata = common.read_json(vpath) or {}
        n_claims = int(vdata.get("n_claims", 0) or 0)
        n_verified = int(vdata.get("n_verified", 0) or 0)
        n_mismatch = int(vdata.get("n_mismatch", 0) or 0)
        total += n_claims
        verified += n_verified
        mismatch += n_mismatch
        families.append({"family": family, "n_claims": n_claims,
                          "n_verified": n_verified, "n_mismatch": n_mismatch})

        verdict_by_claim_id = {
            d.get("claim_id"): d.get("verdict")
            for d in vdata.get("details", []) if isinstance(d, dict)
        }

        claims_path = INTEL_DIR / f"{family}_claims.jsonl"
        rows = common.read_jsonl(claims_path, limit=per_family_cap)
        for row in rows:
            cid = row.get("claim_id")
            statement = row.get("question") or row.get("statement") or str(cid)
            sample.append({
                "claim_id": cid,
                "statement": str(statement)[:240],
                "family": family,
                "verdict": verdict_by_claim_id.get(cid, "NOT_IN_VALIDATION_SAMPLE"),
                "asof": row.get("computed_at", asof),
            })

    return {
        "total": corpus_total,
        "validated_sample": total,
        "verified": verified,
        "mismatch": mismatch,
        "families": families,
        "sample": sample[:SAMPLE_CAP],
        "receipt": common.receipt(
            f"Intelligence-layer claims generated from raw data; a {total}-claim "
            f"sample re-validated against source ({verified} verified).",
            {"corpus_rows": corpus_total, "validated_sample": total,
             "verified": verified},
            "VALIDATED (sampled)", INTEL_DIR, asof,
            reproduce="ls data/cache/intel_claims/*_claims_validation.json",
        ),
    }


def build() -> dict:
    asof = datetime.now(timezone.utc).date().isoformat()
    return {
        "preregistered": _build_preregistered(asof),
        "verified_facts": _build_verified_facts(asof),
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=1, default=str)[:2000])
