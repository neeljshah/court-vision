"""brain_query — read-only retrieval seam over the Obsidian brain.

Closes the "memory written but not consulted at inference time" gap
(06_INTELLIGENCE.md §2.3 / §4.4).  Returns UNDERSTANDING + provenance chips;
NEVER a betting number / probability / edge.  Wiring into scout/synthesizer is
human-gated (those live under scripts/team_system/ which this module must not edit).

CLI:
    python -m scripts.platformkit.brain_query "drop coverage rim-runner" [--sport nba] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# ── Contract constant ─────────────────────────────────────────────────────────
_NO_NUMBER_CONTRACT: str = (
    "BrainHit MUST NOT carry a probability, odds, ROI, edge, Kelly fraction, or any "
    "number that could drive a bet.  Retrieval returns understanding, never a bettable "
    "number.  Enforced by is_number_free() in tests and by design."
)

# Checked on structured fields (title, stat_signature keys/values) — not raw prose.
# Prose excerpts are excluded so honest denial notes (_World_Model) are not false-flagged.
_NUM_PAT = re.compile(
    r"\b(?:probability|prob(?:ability)?|odds|roi|edge|kelly|win_prob|brier|clv|vig|juice|"
    r"expected[_\s]value)\b",
    re.IGNORECASE,
)

_KIND_MAP = {"archetypes": "archetype", "schemes": "scheme", "trends": "trend",
             "teams": "team", "_index": "reference", "intelligence": "reference",
             "sports": "reference"}
VALID_KINDS = frozenset({"team", "archetype", "scheme", "trend", "reference",
                         "player", "concept"})
# Concept-family dirs make the 2k+ node concept graph first-class (else -> "reference").
try:
    from scripts.platformkit.concept_dirs import CONCEPT_DIRS as _CONCEPT_DIRS
except Exception:  _CONCEPT_DIRS = frozenset()  # noqa: BLE001,E701
_FALLBACK_SUBDIRS = ("Intelligence", "Sports")
_STAT_SKIP = re.compile(
    r"^(?:metric|feature|stat|name|team|rank|player|verdict|sport|position|-+)$",
    re.IGNORECASE,
)
_STAT_PAT = re.compile(
    r"\*{1,2}([^*|]{1,50}?)\*{1,2}\s*:\s*(.{1,80})"
    r"|\|\s*([^|]{1,50}?)\s*\|\s*([^|]{1,80}?)\s*\|"
)
_SEP_ROW = re.compile(r"^\|[\s\-|:]+\|")


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BrainHit:
    """A single brain-retrieval result.  All fields are provenance-chipped understanding;
    none carry a bettable number (enforced by is_number_free)."""
    sport: str
    kind: str          # team | archetype | scheme | trend | reference | player
    title: str
    path: str
    stat_signature: Dict[str, str] = field(default_factory=dict)
    prevalence: float = 0.0
    excerpt: str = ""
    provenance: str = ""  # "brain:<relative-path>" chip


def is_number_free(hit: BrainHit) -> bool:
    """True iff structured fields (title + stat_signature) carry no forbidden keywords."""
    texts = [hit.sport, hit.kind, hit.title] + list(hit.stat_signature.keys()) + list(hit.stat_signature.values())
    return not bool(_NUM_PAT.search(" ".join(texts)))


# ── Internal helpers ──────────────────────────────────────────────────────────

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _resolve_root(root: Optional[Path]) -> Optional[Path]:
    """If root is explicit, use it as-is (no fallback).  If None, try _Organized then fallbacks."""
    if root is not None:
        return root if root.is_dir() else None
    candidate = _repo_root() / "vault" / "_Organized"
    if candidate.is_dir():
        return candidate
    vault = _repo_root() / "vault"
    for sub in _FALLBACK_SUBDIRS:
        fb = vault / sub
        if fb.is_dir():
            return fb
    return None


def _infer_sport(path: Path, text: str) -> str:
    for p in [x.lower() for x in path.parts]:
        if "nba" in p or "basketball" in p: return "nba"
        if "tennis" in p: return "tennis"
        if "soccer" in p or "football" in p: return "soccer"
        if "mlb" in p or "baseball" in p: return "mlb"
    m = re.search(r"^sport\s*:\s*[\"']?(\w+)", text, re.MULTILINE | re.IGNORECASE)
    return m.group(1).lower() if m else ""


def _infer_kind(path: Path, text: str) -> str:
    for p in [x.lower() for x in path.parts]:
        if p in _KIND_MAP:
            return _KIND_MAP[p]
        if p in _CONCEPT_DIRS:
            return "concept"
    if re.search(r"^archetype\s*:", text, re.MULTILINE | re.IGNORECASE): return "archetype"
    if re.search(r"^scheme\s*:", text, re.MULTILINE | re.IGNORECASE): return "scheme"
    if re.match(r"^\d+_", path.name): return "player"
    return "reference"


def _parse_stat_sig(text: str) -> Dict[str, str]:
    sig: Dict[str, str] = {}
    for line in text.splitlines():
        if _SEP_ROW.match(line):
            continue
        for m in _STAT_PAT.finditer(line):
            key = (m.group(1) or m.group(3) or "").strip()
            val = re.sub(r"\*{1,2}|`", "", (m.group(2) or m.group(4) or "")).strip()
            if key and val and not _STAT_SKIP.match(key):
                sig[key[:50]] = val[:80]
            if len(sig) >= 20:
                return sig
    return sig


def _parse_excerpt(text: str) -> str:
    body = re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL)
    body = re.sub(r"^#\s+[^\n]+\n", "", body.lstrip(), count=1)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body[:300]


def _build_hit(path: Path, root: Path) -> Optional[BrainHit]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if len(text.strip()) < 20:
        return None
    title_m = re.search(r"^#\s+(.+)", text, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else path.stem.replace("_", " ").title()
    byte_len = len(text.encode("utf-8"))
    n_sec = len(re.findall(r"^##\s+", text, re.MULTILINE))
    prev = round(min(min(byte_len / 10_000, 1.0) * 0.7 + min(n_sec / 10, 1.0) * 0.3, 1.0), 4)
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)
    # Infer sport/kind from the ROOT-RELATIVE path only: an absolute root under a
    # repo dir like "nba-ai-system" would otherwise leak "nba" into every note.
    return BrainHit(
        sport=_infer_sport(rel, text),
        kind=_infer_kind(rel, text),
        title=title,
        path=str(path),
        stat_signature=_parse_stat_sig(text),
        prevalence=prev,
        excerpt=_parse_excerpt(text),
        provenance=f"brain:{rel}",
    )


def _score(query_toks: List[str], note_toks: List[str]) -> float:
    if not query_toks:
        return 0.0
    q = set(query_toks)
    return len(q & set(note_toks)) / len(q)


def _tok(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _note_toks(h: BrainHit) -> List[str]:
    return _tok(h.title + " " + " ".join(h.stat_signature.keys()) + " " + h.excerpt)


# ── Public API ────────────────────────────────────────────────────────────────

def brain_query(
    query: str,
    sport: Optional[str] = None,
    kind: Optional[str] = None,
    root: Optional[Path] = None,
    top_k: int = 8,
) -> List[BrainHit]:
    """Retrieve top-k brain notes matching *query*.

    Returns understanding + provenance chips; NEVER a bettable number.
    Every returned hit satisfies is_number_free(hit) == True.
    """
    eff_root = _resolve_root(root)
    if eff_root is None:
        return []
    q_toks = _tok(query)
    hits = []
    for p in sorted(eff_root.rglob("*.md")):
        if p.name.startswith("_") and p.stem in ("_Brain", "_Team", "_Index"):
            continue
        h = _build_hit(p, eff_root)
        if h is None:
            continue
        if sport and h.sport and h.sport != sport.lower():
            continue
        if kind and h.kind != kind.lower():
            continue
        sc = _score(q_toks, _note_toks(h))
        hits.append((sc, str(p), h))
    hits.sort(key=lambda t: (-t[0], t[1]))
    return [h for _, _, h in hits[:top_k]]


def prior_verdicts(sport: Optional[str] = None, root: Optional[Path] = None) -> Dict:
    """Return honest empirical priors from the brain's _World_Model note.

    Always returns edge_claimed: False and the conservative defaults if no note found.
    NEVER carries a probability or edge claim — only qualitative honest verdicts.
    """
    defaults = {"edge_claimed": False, "market_efficiency": "efficient",
                "tested_signals": "REJECT", "note": "markets efficient; calibration not edge"}
    eff_root = _resolve_root(root)
    candidates: List[Path] = []
    if eff_root:
        for p in eff_root.rglob("*.md"):
            if any(kw in p.stem.lower() for kw in ("world_model", "signals_hub", "_brain")):
                candidates.append(p)
    if not candidates:
        intel = _repo_root() / "vault" / "Intelligence"
        if intel.is_dir():
            candidates += [p for p in intel.glob("*.md")
                           if any(kw in p.stem.lower() for kw in ("world_model", "signals_hub"))]
    if not candidates:
        return dict(defaults)
    try:
        text = candidates[0].read_text(encoding="utf-8", errors="replace")
    except OSError:
        return dict(defaults)
    out = dict(defaults)
    if re.search(r"market.*efficient", text, re.IGNORECASE):
        out["market_efficiency"] = "efficient"
    if re.search(r"\bREJECT\b", text):
        out["tested_signals"] = "REJECT"
    if re.search(r"(?:no edge|edge.*not claimed|never.*edge|edge_claimed.*[Ff]alse)", text, re.IGNORECASE):
        out["edge_claimed"] = False
    if sport:
        m = re.search(rf"{re.escape(sport.lower())}.*?(REJECT|SHIP|efficient|inefficient)",
                      text, re.IGNORECASE)
        if m:
            out[f"{sport.lower()}_verdict"] = m.group(1).upper()
    try:
        out["source_path"] = str(candidates[0].relative_to(eff_root)) if eff_root else candidates[0].name
    except ValueError:
        out["source_path"] = candidates[0].name
    return out


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli() -> None:  # pragma: no cover
    ap = argparse.ArgumentParser(description="brain_query: understanding + provenance; never a number.")
    ap.add_argument("query")
    ap.add_argument("--sport", default=None)
    ap.add_argument("--kind", default=None)
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    hits = brain_query(a.query, sport=a.sport, kind=a.kind, top_k=a.top_k)
    if a.json:
        print(json.dumps([asdict(h) for h in hits], indent=2))
        return
    if not hits:
        print("No brain hits found.")
        return
    for i, h in enumerate(hits, 1):
        print(f"\n[{i}] {h.title}  ({h.kind}{' / ' + h.sport if h.sport else ''})")
        print(f"    provenance : {h.provenance}")
        print(f"    prevalence : {h.prevalence:.3f}")
        if h.stat_signature:
            print(f"    stat-sig   : {dict(list(h.stat_signature.items())[:4])}")
        if h.excerpt:
            print(f"    excerpt    : {h.excerpt[:100]} ...")
    bad = [h.title for h in hits if not is_number_free(h)]
    if bad:
        print(f"WARNING: number-contract violation: {bad}", file=sys.stderr)


if __name__ == "__main__":
    _cli()
