"""scripts.platformkit.knowledge.backfill_knowledge -- one-time, re-runnable
backfill of domains/<sport>/knowledge/knowledge.jsonl: a machine-readable
knowledge store built from two READ-ONLY sources per sport:

1. domains/<sport>/knowledge/mechanisms.md -- numbered mechanism entries
   ("### N. Title" / "- **claim**: ..." / "- **status**: LABEL ...").
2. data/cache/intel_claims/interaction_factory_ledger.jsonl -- the
   interaction-factory validation ledger (all sports mixed in one file).

Row schema (exact keys): claim, mechanism, sport, effect, ci, n, corpora,
label, lineage, last_validated, source. Missing numerics -> null, never
invented. `label` is copied VERBATIM from the source text -- never
upgraded or paraphrased (mechanisms.md's own binding invariant: labels are
the product).

Dedup rule: a mechanisms.md row and a factory-ledger row describing the same
mechanism are BOTH kept (different `source`) -- this store is append-only
lineage; consumers dedupe, the builder never merges.

Idempotent: re-run overwrites deterministically -- rows are stable-sorted
by (sport, source, last_validated) before being written one-JSON-per-line
with sort_keys=True, so identical inputs always produce identical bytes.

CLI: python -m scripts.platformkit.knowledge.backfill_knowledge
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[3]
SPORTS = ["basketball_nba", "mlb", "soccer", "tennis"]
LEDGER_PATH = REPO / "data" / "cache" / "intel_claims" / "interaction_factory_ledger.jsonl"

_HEADING_RE = re.compile(r"^### (\d+)\.\s*(.+?)\s*$")
_SECTION_RE = re.compile(r"^## (.+?)\s*$")
_SECTION_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_CLAIM_RE = re.compile(r"^\s*-\s*\*\*claim[^*]*\*\*:\s*(.+?)\s*$")
_STATUS_RE = re.compile(r"^\s*-\s*\*\*status\*\*:\s*(.+?)\s*$")
# ponytail: free-text figures, not a structured field -- first match wins,
# never invented if absent. Covers "eff=0.0057", "effect -1.73", "effect +3.40".
_EFFECT_RE = re.compile(r"\beff(?:ect)?\s*[:=]?\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)")
# fallback when the entry reports a correlation instead of an effect size
# (e.g. split-half persistence rows: "r=0.604, p=4.1e-4").
_R_RE = re.compile(r"(?<![A-Za-z])r\s*=\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)")
_N_RE = re.compile(r"\bn\s*=\s*([\d,]+)")
_CI_RE = re.compile(r"\bCI\s*\[([^\]]+)\]")
_COMMIT_RE = re.compile(r"\bcommits?\s+([0-9a-f]{6,10}(?:/[0-9a-f]{6,10})*)")
# fallback when the label lives in the HEADING, not a status line, e.g.
# "### 42. Team staff-wide ... -- CONFIRMED_LOCAL (2026-07-11 update, ...)".
# Uppercase label token(s) only; "(" is outside the class so parentheticals
# stay out of the label field.
_HEADING_LABEL_RE = re.compile(r"--\s*([A-Z][A-Z_]*(?:[ ,/]+[A-Z][A-Z_]*)*)")


def _mechanism_row(sport: str, mech_id: str, title: str, lines: List[str],
                    section_date: Optional[str]) -> Dict[str, Any]:
    text = "\n".join(lines)
    claim = title
    for line in lines:
        cm = _CLAIM_RE.match(line)
        if cm:
            claim = cm.group(1)
            break
    label = None
    for line in lines:
        sm = _STATUS_RE.match(line)
        if sm:
            label = sm.group(1)
            break
    if label is None:
        hm = _HEADING_LABEL_RE.search(title)
        if hm:
            label = hm.group(1).strip()
    eff_m = _EFFECT_RE.search(text) or _R_RE.search(text)
    n_m = _N_RE.search(text)
    ci_m = _CI_RE.search(text)
    commit_m = _COMMIT_RE.search(text)
    # ponytail: "REPLICATED" appearing in the entry's own status/body text is
    # the only local signal of a 2nd corpus -- coarse (local/local+2nd) by
    # design; upgrade to a real corpus-name list if a consumer needs more.
    corpora = ["local", "2nd"] if "REPLICATED" in text else ["local"]
    return {
        "claim": claim,
        "mechanism": title,
        "sport": sport,
        "effect": float(eff_m.group(1)) if eff_m else None,
        "ci": ci_m.group(1) if ci_m else None,
        "n": int(n_m.group(1).replace(",", "")) if n_m else None,
        "corpora": corpora,
        "label": label,
        "lineage": commit_m.group(1).split("/") if commit_m else [],
        "last_validated": section_date,
        "source": "mechanisms.md#%s" % mech_id,
    }


def parse_mechanisms(path: Path, sport: str) -> List[Dict[str, Any]]:
    """Parse one mechanisms.md into knowledge rows. Missing file -> []."""
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    section_date: Optional[str] = None
    block_id: Optional[str] = None
    block_title = ""
    block_lines: List[str] = []

    def flush() -> None:
        if block_id is not None:
            rows.append(_mechanism_row(sport, block_id, block_title, block_lines, section_date))

    for raw in path.read_text(encoding="ascii", errors="replace").splitlines():
        m_head = _HEADING_RE.match(raw)
        if m_head:
            flush()
            block_id, block_title, block_lines = m_head.group(1), m_head.group(2), []
            continue
        m_section = _SECTION_RE.match(raw)
        if m_section:
            flush()
            block_id, block_lines = None, []
            date_m = _SECTION_DATE_RE.search(m_section.group(1))
            section_date = date_m.group(1) if date_m else None
            continue
        if block_id is not None:
            block_lines.append(raw)
    flush()
    return rows


def _load_ledger(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def ledger_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map one interaction_factory_ledger.jsonl row -> a knowledge row."""
    attr_a, attr_b = row.get("attr_a"), row.get("attr_b")
    outcome, template_id = row.get("outcome"), row.get("template_id")
    corpus = row.get("corpus")
    return {
        "claim": "%s x %s -> %s (%s)" % (attr_a, attr_b, outcome, template_id),
        "mechanism": template_id,
        "sport": row.get("sport"),
        "effect": row.get("effect"),
        "ci": None,
        "n": row.get("n"),
        "corpora": [corpus] if corpus else [],
        "label": row.get("verdict"),
        "lineage": [],
        "last_validated": row.get("computed_at"),
        "source": "factory_ledger:%s/%s" % (template_id, row.get("candidate_id")),
    }


def build_sport(sport: str, ledger_path: Path = LEDGER_PATH) -> List[Dict[str, Any]]:
    mech_path = REPO / "domains" / sport / "knowledge" / "mechanisms.md"
    rows = parse_mechanisms(mech_path, sport)
    rows.extend(ledger_row(r) for r in _load_ledger(ledger_path) if r.get("sport") == sport)
    rows.sort(key=lambda r: (r["sport"] or "", r["source"], r.get("last_validated") or ""))
    return rows


def write_sport(sport: str, ledger_path: Path = LEDGER_PATH) -> List[Dict[str, Any]]:
    rows = build_sport(sport, ledger_path)
    out_path = REPO / "domains" / sport / "knowledge" / "knowledge.jsonl"
    lines = [json.dumps(r, sort_keys=True) for r in rows]
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="ascii")
    return rows


def main() -> int:
    total = 0
    for sport in SPORTS:
        rows = write_sport(sport)
        print("%s: %d rows -> domains/%s/knowledge/knowledge.jsonl" % (sport, len(rows), sport))
        total += len(rows)
    print("total: %d rows" % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["parse_mechanisms", "ledger_row", "build_sport", "write_sport", "main"]
