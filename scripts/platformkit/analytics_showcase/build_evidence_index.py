"""Evidence-index builder for the website evidence spine.

Reads the committed evidence pages under docs/evidence/*.md and emits
out/evidence_index.json: one honest row per claim (slug, bucket, title, the
claim sentence, the single strongest receipt, and every cited artifact id).
The webapp (evidence.server.ts) parses the full markdown itself; this builder
owns only the editorial JOIN -- bucket assignment + the strongest-receipt pick.

Paths in the output are REPO-RELATIVE only (clone-safe; never a box-local
absolute like C:/Users/neelj/...). This repo never claims an edge, so every
row carries edge_claimed=false.

Run:   python -m scripts.platformkit.analytics_showcase.build_evidence_index
Check: python -m scripts.platformkit.analytics_showcase.build_evidence_index --check
Demo:  python -m scripts.platformkit.analytics_showcase.build_evidence_index --demo
"""
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_OUT = _REPO / "scripts" / "platformkit" / "analytics_showcase" / "out"
_EVID = _REPO / "docs" / "evidence"
_INDEX = _OUT / "evidence_index.json"

# The four editorial buckets, in display order (mirror SITE_PLAN_v2 1.3).
BUCKET_ORDER = [
    "Self-refutation & honesty",
    "Calibration & market",
    "Engineering depth",
    "Frontier measurements",
]

# slug -> bucket. Hand-curated: buckets are an editorial grouping, not derivable.
# demo() asserts every evidence page is mapped, so adding a page fails loud.
_BUCKET = {
    # Self-refutation & honesty -- the pages that publish where we are wrong.
    "cross-corpus-replication": "Self-refutation & honesty",
    "execution-honesty": "Self-refutation & honesty",
    "leak-instruments": "Self-refutation & honesty",
    "market-disagreement": "Self-refutation & honesty",
    "retraction-story": "Self-refutation & honesty",
    # Calibration & market -- Brier/devig/in-game calibration diagnostics.
    "calibration-decomposition": "Calibration & market",
    "devig-stack": "Calibration & market",
    "ingame-conditioning": "Calibration & market",
    "player-props": "Calibration & market",
    # Engineering depth -- the machinery behind the numbers.
    "agent-fleet-direction": "Engineering depth",
    "ai-engineering": "Engineering depth",
    "answer-engine": "Engineering depth",
    "cv-pipeline": "Engineering depth",
    "data-layer": "Engineering depth",
    "entity-atlas": "Engineering depth",
    "knowledge-engine": "Engineering depth",
    "mcp-live-demo": "Engineering depth",
    "operations-reliability": "Engineering depth",
    "possession-simulator": "Engineering depth",
    # Frontier measurements -- the uniquely-auditable analytics.
    "analytical-depth": "Frontier measurements",
    "industry-metrics": "Frontier measurements",
    "novel-analytics": "Frontier measurements",
    "true-intelligence": "Frontier measurements",
}

# Artifact fields, priority order, whose value is an honest one-line receipt.
_RECEIPT_KEYS = ("headline", "verdict", "label", "note", "honest_note", "summary")


def _rel(path):
    """Repo-relative POSIX string, or None. Never leaks an absolute box path."""
    if path is None:
        return None
    try:
        return str(Path(path).relative_to(_REPO)).replace("\\", "/")
    except ValueError:
        return None


def _pages():
    return [p for p in sorted(_EVID.glob("*.md")) if p.name != "README.md"]


def _clean(md):
    """Strip inline markdown to plain text: links, bold, italics, code, refs."""
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md)  # [text](url) -> text
    s = s.replace("**", "").replace("`", "")
    s = re.sub(r"(?<!\w)[*_](?=\w)|(?<=\w)[*_](?!\w)", "", s)  # stray * _
    return " ".join(s.split())


def _claim(text):
    """First paragraph under '## The claim', else under the first '## ' section."""
    lines = text.splitlines()
    # locate the heading to read from
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().lower() == "## the claim":
            start = i + 1
            break
    if start is None:
        for i, ln in enumerate(lines):
            if ln.startswith("## "):
                start = i + 1
                break
    if start is None:
        return ""
    para = []
    for ln in lines[start:]:
        if ln.startswith("#"):
            if para:
                break
            continue
        if not ln.strip():
            if para:
                break
            continue
        para.append(ln.strip())
    s = _clean(" ".join(para))
    return s if len(s) <= 400 else s[:397] + "..."


def _cited_artifacts(text):
    """Every out/<name>.json referenced -> canonical repo-rel path, deduped."""
    names = dict.fromkeys(re.findall(r"out/([A-Za-z0-9_]+)\.json", text))
    return [_rel(_OUT / f"{n}.json") for n in names]


def _receipt_label(artifact_rel):
    """One honest one-liner from the artifact's own metadata; '' if unreadable."""
    if not artifact_rel:
        return ""
    p = _REPO / artifact_rel
    if not p.exists():
        return ""  # fresh clone: webapp shows VALIDATION_PENDING
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    for k in _RECEIPT_KEYS:
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            s = " ".join(v.split())
            return s if len(s) <= 240 else s[:237] + "..."
    return ""


def _title(text, slug):
    for ln in text.splitlines():
        if ln.startswith("# "):
            return _clean(ln[2:])
    return slug.replace("-", " ").title()


def build():
    claims = []
    for page in _pages():
        slug = page.stem
        text = page.read_text(encoding="utf-8", errors="replace")
        cited = _cited_artifacts(text)
        primary = cited[0] if cited else None
        claim = _claim(text)
        label = _receipt_label(primary) or (claim.split(". ")[0] if claim else "")
        claims.append({
            "slug": slug,
            "bucket": _BUCKET.get(slug, "Engineering depth"),
            "title": _title(text, slug),
            "claim": claim,
            "strongest_receipt": {"source": primary, "label": label},
            "cited_artifacts": cited,
            "edge_claimed": False,
        })
    return {
        "generated_from": _rel(_EVID),
        "claim_count": len(claims),
        "bucket_order": BUCKET_ORDER,
        "edge_claimed": False,
        "claims": claims,
    }


def _validate(idx):
    assert isinstance(idx, dict), "index is not an object"
    for k in ("generated_from", "claim_count", "bucket_order", "claims"):
        assert k in idx, f"missing top-level key: {k}"
    assert idx["edge_claimed"] is False, "edge_claimed must be False"
    assert idx["bucket_order"] == BUCKET_ORDER, "bucket_order drifted"
    assert idx["claim_count"] == len(idx["claims"]), "claim_count mismatch"
    abs_pat = re.compile(r"^[A-Za-z]:[\\/]|^/")
    seen = set()
    for row in idx["claims"]:
        for k in ("slug", "bucket", "title", "claim", "strongest_receipt",
                  "cited_artifacts", "edge_claimed"):
            assert k in row, f"claim {row.get('slug')} missing field: {k}"
        assert row["edge_claimed"] is False, f"{row['slug']}: edge_claimed"
        assert row["slug"] not in seen, f"duplicate slug {row['slug']}"
        seen.add(row["slug"])
        assert row["bucket"] in BUCKET_ORDER, f"{row['slug']}: bad bucket"
        assert row["claim"], f"{row['slug']}: empty claim"
        src = row["strongest_receipt"]["source"]
        paths = [src] + list(row["cited_artifacts"])
        for v in paths:
            assert v is None or not abs_pat.match(v), \
                f"{row['slug']}: absolute path (not clone-safe): {v}"


def check():
    assert _INDEX.exists(), f"recorded index absent: {_rel(_INDEX)}"
    idx = json.loads(_INDEX.read_text(encoding="utf-8"))
    _validate(idx)
    buckets = {b: 0 for b in BUCKET_ORDER}
    for row in idx["claims"]:
        buckets[row["bucket"]] += 1
    print(f"PASS -- evidence_index.json: {idx['claim_count']} claims, "
          f"buckets={buckets}")


def demo():
    """Self-check: build in-memory, validate, and assert every page is mapped."""
    idx = build()
    _validate(idx)
    unmapped = [p.stem for p in _pages() if p.stem not in _BUCKET]
    assert not unmapped, f"pages missing from _BUCKET: {unmapped}"
    assert idx["claim_count"] == len(_pages()), "claim/page count mismatch"
    assert idx["claim_count"] >= 22, "fewer claims than expected"
    print(f"demo OK: {idx['claim_count']} claims across "
          f"{len(set(_BUCKET.values()))} buckets")


def main():
    if "--check" in sys.argv:
        check()
        return
    if "--demo" in sys.argv:
        demo()
        return
    idx = build()
    _validate(idx)
    _INDEX.write_text(json.dumps(idx, indent=2), encoding="utf-8")
    print(f"wrote {_rel(_INDEX)}: {idx['claim_count']} claims")


if __name__ == "__main__":
    main()
