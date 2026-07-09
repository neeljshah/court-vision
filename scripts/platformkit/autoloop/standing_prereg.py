"""scripts.platformkit.autoloop.standing_prereg -- the sha-pinned template
registry.

AUTOLOOP_SPEC_2026-07-06.md sec 1 + R-D erratum: canonical template JSONs are
TRACKED at scripts/platformkit/autoloop/templates/ (survive a data/ wipe);
data/cache/autoloop/ holds only runtime state (K ledger, watermarks).

Each template declares its own `prereg_sha` over the CANONICAL json (sorted
keys, minus `prereg_sha` itself) -- same canonicalization `prereg_sha_stamp`
already uses (`_canonical_bytes`), mirrored here (field name differs:
`prereg_sha` not `sha256`, and this module never WRITES the pin -- it only
verifies). A mismatch is fail-closed: PREREG_TAMPER, the family is refused.

The daemon reads pins; it never writes them. A NEW template class is a human/
Fable action (author the JSON, compute+embed prereg_sha via `compute_sha`).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit import reject_ledger
from scripts.platformkit.io_atomic import append_jsonl_atomic, write_json_atomic

_REPO = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = _REPO / "scripts" / "platformkit" / "autoloop" / "templates"
_CACHE_DIR = _REPO / "data" / "cache" / "autoloop"
K_LEDGER_DIR = _CACHE_DIR / "k_ledger"
WATERMARK_PATH = _CACHE_DIR / "checkpoint.json"

VALID_KINDS = {"claims_regen", "reclaim_fit", "calib_refit", "interaction_batch"}


def _canonical_bytes(obj: Dict[str, Any]) -> bytes:
    """Canonical JSON (sorted keys, minus prereg_sha) as ASCII bytes -- mirrors
    prereg_sha_stamp._canonical_bytes exactly, field name adapted."""
    minus_sha = {k: v for k, v in obj.items() if k != "prereg_sha"}
    return json.dumps(minus_sha, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":")).encode("ascii")


def compute_sha(obj: Dict[str, Any]) -> str:
    """sha256 hex digest over the canonical JSON (sorted keys, minus prereg_sha)."""
    return hashlib.sha256(_canonical_bytes(obj)).hexdigest()


_REQUIRED_FIELDS = ("template_id", "sport", "kind", "prereg_sha", "universe",
                    "corpus", "bars", "k_ledger", "planted_null",
                    "max_candidates_per_cycle")


class Template:
    """One verified, sha-pinned standing prereg template."""

    def __init__(self, path: Path, body: Dict[str, Any], ok: bool, reason: Optional[str]):
        self.path = path
        self.body = body
        self.ok = ok
        self.reason = reason  # None if ok; else e.g. "PREREG_TAMPER" / "MALFORMED"

    @property
    def template_id(self) -> str:
        return str(self.body.get("template_id") or self.path.stem)

    @property
    def sport(self) -> str:
        return str(self.body.get("sport", ""))

    @property
    def kind(self) -> str:
        return str(self.body.get("kind", ""))

    @property
    def universe(self) -> List[str]:
        return list(self.body.get("universe") or [])

    @property
    def excluded_signals(self) -> List[str]:
        return list(self.body.get("excluded_signals") or [])

    @property
    def max_candidates_per_cycle(self) -> int:
        return int(self.body.get("max_candidates_per_cycle", 0) or 0)


def load_template(path: Path) -> Template:
    """Load + sha-verify one template JSON. Never raises -- a missing/malformed
    field or a sha mismatch produces an ok=False Template with a `reason`.
    """
    path = Path(path)
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 -- unreadable/garbage template, fail-closed
        return Template(path, {}, False, "UNREADABLE:%s" % str(exc)[:80])
    if not isinstance(body, dict):
        return Template(path, {}, False, "MALFORMED_NOT_OBJECT")
    missing = [f for f in _REQUIRED_FIELDS if f not in body]
    if missing:
        return Template(path, body, False, "MALFORMED_MISSING:%s" % ",".join(missing))
    if body.get("kind") not in VALID_KINDS:
        return Template(path, body, False, "MALFORMED_KIND:%s" % body.get("kind"))
    pinned = str(body.get("prereg_sha", ""))
    live = compute_sha(body)
    if pinned != live:
        return Template(path, body, False, "PREREG_TAMPER")
    return Template(path, body, True, None)


def load_all_templates(templates_dir: Optional[Path] = None) -> List[Template]:
    """Every *.json template under templates_dir, each independently verified.
    One malformed/tampered template never blocks the others (per-template isolation)."""
    d = Path(templates_dir) if templates_dir is not None else TEMPLATES_DIR
    if not d.is_dir():
        return []
    return [load_template(p) for p in sorted(d.glob("*.json"))]


def derive_blocklist(template: Template, *, stale_after_days: Optional[float] = None,
                     ledger_path: Optional[Path] = None) -> List[str]:
    """Universe members whose LATEST reject_ledger verdict is a live (non-stale)
    REJECT/CLOSED -- DERIVED at run time, never hand-copied (spec sec 1)."""
    stale = template.body.get("stale_after_days", stale_after_days)
    blocked: List[str] = []
    for member in template.universe:
        if member in template.excluded_signals:
            blocked.append(member)
            continue
        if reject_ledger.is_known_reject(template.sport, member,
                                         stale_after_days=stale,
                                         ledger_path=ledger_path):
            blocked.append(member)
    return blocked


# K ledger: append-only, per (sport, template_id); NEVER reset (R13).
def k_ledger_path(sport: str, template_id: str, *, base_dir: Optional[Path] = None) -> Path:
    d = Path(base_dir) if base_dir is not None else K_LEDGER_DIR
    return d / ("%s__%s.jsonl" % (sport, template_id))


def k_ledger_load(sport: str, template_id: str, *, base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """All rows for this (sport, template); [] if never written. Tolerates a
    torn trailing line (best-effort skip) rather than raising."""
    p = k_ledger_path(sport, template_id, base_dir=base_dir)
    if not p.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in p.read_text(encoding="ascii", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def k_ledger_cum_k(sport: str, template_id: str, *, base_dir: Optional[Path] = None) -> int:
    """Latest cum_k on record; 0 if the ledger is empty (fresh template)."""
    rows = k_ledger_load(sport, template_id, base_dir=base_dir)
    return int(rows[-1].get("cum_k", 0)) if rows else 0


def k_ledger_append(sport: str, template_id: str, ts: str, new_deduped_k: int,
                    cum_k: int, *, base_dir: Optional[Path] = None) -> None:
    """Append one {ts, new_deduped_k, cum_k} row -- append-only, atomic write.
    Claims-regen templates append new_deduped_k=0 (spends no K)."""
    p = k_ledger_path(sport, template_id, base_dir=base_dir)
    append_jsonl_atomic(p, {
        "ts": ts, "new_deduped_k": int(max(0, new_deduped_k)), "cum_k": int(max(0, cum_k)),
    })


# Watermark store: per-template content-sha last processed.
def load_watermarks(*, path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """{template_id: {corpus_sha, last_run_ts}}; {} if never written or torn."""
    p = Path(path) if path is not None else WATERMARK_PATH
    if not p.exists():
        return {}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        return dict(doc.get("templates") or {}) if isinstance(doc, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_watermarks(watermarks: Dict[str, Dict[str, Any]], *, path: Optional[Path] = None) -> None:
    """Atomic write (tmp + os.replace via io_atomic) -- a crash resumes on the
    last consistent sha, never a torn watermark (spec self-critique C)."""
    p = Path(path) if path is not None else WATERMARK_PATH
    write_json_atomic(p, {"templates": watermarks})


def is_due(template_id: str, corpus_sha: str, watermarks: Dict[str, Dict[str, Any]]) -> bool:
    """DUE iff the corpus's current content sha differs from the last processed
    sha for this template (a CONTENT sha, never a timestamp/row count -- spec
    2b + self-critique C). A template never seen before is always due."""
    prior = watermarks.get(template_id)
    if prior is None:
        return True
    return str(prior.get("corpus_sha", "")) != str(corpus_sha)


def _gate_corpus_sha(sport: str) -> Optional[str]:
    """sha256 of corpus_cache's OWN sha-sidecar {source: sha256} manifest --
    reads it, never reimplements its staleness bar (reclaim_fit/calib_refit)."""
    from scripts.platformkit.combo import corpus_cache as CC
    sidecar = CC._sidecar_path(sport)  # noqa: SLF001 -- same-package reuse, read-only
    if not sidecar.exists():
        try:
            CC.build_gate_corpus(sport)  # first-ever build for this sport
        except Exception:
            return None
    try:
        manifest = json.loads(sidecar.read_text(encoding="utf-8"))
        fp = json.dumps(manifest.get("sources") or {}, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(fp.encode("ascii", errors="replace")).hexdigest()
    except Exception:
        return None


def _claims_grid(sport: str) -> Dict[str, Any]:
    return __import__("domains.%s.claims_grid" % sport, fromlist=["GRID"]).GRID


def _claims_grid_source_sha(sport: str, universe: List[str]) -> Optional[str]:
    """sha256 over the pinned grid families' own source parquet bytes
    (claims_regen has no gate corpus_cache watermark -- the factory's own
    per-family source file IS the content that changes)."""
    try:
        fam_cfg = {f["family"]: f for f in _claims_grid(sport)["families"]}
        sources = sorted({fam_cfg[f]["source"] for f in universe if f in fam_cfg})
        if not sources:
            return None
        h = hashlib.sha256()
        for rel in sources:
            p = _REPO / rel if not Path(rel).is_absolute() else Path(rel)
            h.update(p.read_bytes())
        return h.hexdigest()
    except Exception:
        return None


def _interaction_content_sha(template: Template) -> Optional[str]:
    """interaction_batch is PROGRESS-triggered, not only corpus-triggered: the
    factory walks NEW untested candidates each cycle, so DUE must stay True while
    candidates remain. Token = sha(source freshness + tested-candidate count):
      - source freshness = declared `source_globs` file (name,size,mtime) digest,
      - count = ledger rows for THIS template (each batch grows it).
    So the token advances after every batch (still due next cycle) and STABILIZES
    once the factory is exhausted (no new rows) -> is_due False -> halts, and a
    corpus change flips the freshness digest -> re-triggers. None if no source."""
    globs = template.body.get("source_globs") or []
    parts: List[str] = []
    for g in sorted(globs):
        for p in sorted(_REPO.glob(g)):
            if p.is_file():
                st = p.stat()
                parts.append("%s:%d:%d" % (p.name, st.st_size, int(st.st_mtime)))
    if not parts:
        return None
    ledger_rel = template.body.get("interaction_ledger") or \
        "data/cache/intel_claims/interaction_factory_ledger.jsonl"
    lp = _REPO / ledger_rel
    n_rows = 0
    if lp.exists():
        needle = '"template_id": "%s"' % template.template_id
        needle2 = '"template_id":"%s"' % template.template_id
        for line in lp.read_text(encoding="ascii", errors="replace").splitlines():
            if needle in line or needle2 in line:
                n_rows += 1
    src = "|".join(parts)
    return hashlib.sha256(("%s::%d" % (src, n_rows)).encode("ascii")).hexdigest()


def template_content_sha(template: Template) -> Optional[str]:
    """Kind-dispatched content-sha watermark: reclaim_fit/calib_refit use the
    corpus_cache gate-corpus sidecar; claims_regen uses its own grid source
    parquet(s) (no gate corpus_cache entry exists for a claims sport name);
    interaction_batch uses source freshness + factory progress (see above)."""
    if template.kind == "claims_regen":
        return _claims_grid_source_sha(template.sport, template.universe)
    if template.kind == "interaction_batch":
        return _interaction_content_sha(template)
    return _gate_corpus_sha(template.sport)


def run_claims_regen(template: Template) -> Dict[str, Any]:
    """Regenerate+batch-validate+index each due claims family via the factory
    CLI's own generate_family. Import-guarded: absent/failing factory -> honest
    SKIPPED_FAMILY, fail-closed, cycle continues (spec sec 2d)."""
    regenerated = verified = n_excluded = 0
    skipped: List[str] = []
    max_n = template.max_candidates_per_cycle
    for family in (template.universe[:max_n] if max_n else template.universe):
        try:
            from scripts.platformkit.intel_validation.claims_factory import generate_family
            summary = generate_family(template.sport, family, _claims_grid(template.sport))
            regenerated += 1
            verified += int(summary.get("n_claims", 0) or 0)
            n_excluded += int(summary.get("n_excluded_below_floor", 0) or 0)
        except Exception:  # noqa: BLE001 -- ImportError (factory absent) or any factory failure -> SKIP
            skipped.append(family)
    return {"claims_regenerated": regenerated, "claims_verified": verified,
           "claims_mismatch": 0, "n_excluded_below_floor": n_excluded,
           "skipped_family": skipped, "new_deduped_k": 0}


__all__ = [
    "TEMPLATES_DIR", "K_LEDGER_DIR", "WATERMARK_PATH", "VALID_KINDS",
    "Template", "compute_sha", "load_template", "load_all_templates",
    "derive_blocklist", "k_ledger_path", "k_ledger_load", "k_ledger_cum_k",
    "k_ledger_append", "load_watermarks", "save_watermarks", "is_due",
    "template_content_sha", "run_claims_regen",
]
