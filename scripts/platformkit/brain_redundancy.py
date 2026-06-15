"""brain_redundancy.py — audit vault/_Organized/ for thin, duplicate, and orphan notes.

Measures brain DENSITY and REDUNDANCY over time.  Per top-level sport dir reports:
(a) THIN nodes: .md files < 450 B, excluding _-prefixed hub/index notes.
(b) near-DUPLICATE pairs: token-set Jaccard >= 0.85 within the same sport.
(c) ORPHAN nodes: notes with zero inbound AND zero outbound [[wikilinks]].
(d) totals: n_notes, total_bytes, avg_bytes per sport and overall.
(e) consolidation candidates: groups of >=5 near-identical notes in one (sport, category).

Writes ``vault/_Organized/_Index/_Redundancy_Report.md``.  Idempotent.  Pure stdlib.

CLI: ``python -m scripts.platformkit.brain_redundancy [<root>] [--json]``
"""
from __future__ import annotations
import json, re, sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BANNER = ("> **Intelligence map; markets efficient; calibration is not edge; "
           "no edge claimed.**  Redundancy audit — denser/less redundant over time is the goal.")
_THIN_BYTES = 450
_DUP_J = 0.85
_CONSOL_MIN = 5
_WL_RE = re.compile(r"\[\[([^\]|#\n]+)")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _tokens(text: str) -> frozenset:
    return frozenset(re.findall(r"[a-z0-9_]+", text.lower()))


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    u = len(a | b)
    return len(a & b) / u if u else 0.0


def _outlinks(text: str) -> List[str]:
    return _WL_RE.findall(text)


def _category(path: Path, sport_root: Path) -> str:
    parts = path.relative_to(sport_root).parts
    return parts[0] if len(parts) > 1 else "."


def _thin_nodes(notes: List[Dict]) -> List[Dict]:
    return sorted(
        [n for n in notes if n["size"] < _THIN_BYTES and not n["name"].startswith("_")],
        key=lambda n: n["size"],
    )


def _orphan_nodes(notes: List[Dict], inlinks: Dict[str, int]) -> List[Dict]:
    return [n for n in notes if not n["name"].startswith("_")
            and not inlinks.get(n["path"].stem, 0) and not n["outlinks"]]


def _dup_pairs(notes: List[Dict]) -> List[Tuple[Dict, Dict, float]]:
    pairs = []
    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            s = _jaccard(notes[i]["tokens"], notes[j]["tokens"])
            if s >= _DUP_J:
                pairs.append((notes[i], notes[j], round(s, 3)))
    return sorted(pairs, key=lambda t: t[2], reverse=True)


def _consolidation(notes: List[Dict]) -> List[Tuple[str, str, int, float]]:
    by_cat: Dict[str, List[Dict]] = defaultdict(list)
    for n in notes:
        by_cat[n["category"]].append(n)
    out = []
    for cat, grp in by_cat.items():
        if len(grp) < _CONSOL_MIN:
            continue
        sims = [_jaccard(grp[i]["tokens"], grp[j]["tokens"])
                for i in range(len(grp)) for j in range(i + 1, len(grp))]
        avg_j = sum(sims) / len(sims) if sims else 0.0
        if avg_j >= _DUP_J:
            out.append((cat, grp[0]["name"], len(grp), round(avg_j, 3)))
    return sorted(out, key=lambda t: t[3], reverse=True)


# ---------------------------------------------------------------------------
# Collect + analyse one sport
# ---------------------------------------------------------------------------

def _read_notes(sport_root: Path) -> List[Dict]:
    notes = []
    for fp in sorted(sport_root.rglob("*.md")):
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        notes.append({"path": fp, "name": fp.name, "size": fp.stat().st_size,
                      "tokens": _tokens(text), "outlinks": _outlinks(text),
                      "category": _category(fp, sport_root)})
    return notes


def _inlink_counts(all_notes: List[Dict]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for n in all_notes:
        for lk in n["outlinks"]:
            counts[Path(lk.strip()).stem] += 1
    return counts


def _analyse(sport_root: Path, all_flat: List[Dict]) -> Dict:
    notes = _read_notes(sport_root)
    if not notes:
        return {"n_notes": 0, "total_bytes": 0, "avg_bytes": 0,
                "thin": [], "dup_pairs": [], "orphans": [], "consolidation": [],
                "skipped": "no notes"}
    ink = _inlink_counts(all_flat)
    thin = _thin_nodes(notes)
    dups = _dup_pairs(notes)
    orphans = _orphan_nodes(notes, ink)
    consol = _consolidation(notes)
    tb = sum(n["size"] for n in notes)
    return {
        "n_notes": len(notes), "total_bytes": tb,
        "avg_bytes": round(tb / len(notes)),
        "thin":     [{"name": n["name"], "bytes": n["size"]} for n in thin],
        "dup_pairs":[{"a": a["name"], "b": b["name"], "jaccard": s} for a, b, s in dups],
        "orphans":  [{"name": n["name"]} for n in orphans],
        "consolidation": [{"category": c, "sample": s, "n": sz, "avg_j": j}
                          for c, s, sz, j in consol],
    }


# ---------------------------------------------------------------------------
# Report renderer
# ---------------------------------------------------------------------------

def _render(by_sport: Dict[str, Dict]) -> str:
    L = ["---", "tags: [organized, intelligence, redundancy-audit, person-free]", "---",
         "# Brain Redundancy Report\n", _BANNER + "\n",
         "A brain gets DENSER and LESS redundant over time.\n",
         "## Per-sport summary\n",
         "| Sport | Notes | Avg B | Thin | Dups | Orphans |",
         "|-------|------:|------:|-----:|-----:|--------:|"]
    tn = tb = tt = td = to = 0
    for sp, info in sorted(by_sport.items()):
        if "skipped" in info:
            L.append(f"| {sp} | — | — | — | — | — |")
            continue
        n, ab = info["n_notes"], info["avg_bytes"]
        th, dp, or_ = len(info["thin"]), len(info["dup_pairs"]), len(info["orphans"])
        L.append(f"| {sp} | {n} | {ab} | {th} | {dp} | {or_} |")
        tn += n; tb += info["total_bytes"]; tt += th; td += dp; to += or_
    avg = round(tb / tn) if tn else 0
    L.append(f"| **ALL** | **{tn}** | **{avg}** | **{tt}** | **{td}** | **{to}** |\n")
    for sp, info in sorted(by_sport.items()):
        if "skipped" in info:
            continue
        L.append(f"## {sp}\n")
        L.append(f"### Thin nodes (< {_THIN_BYTES} B) — {len(info['thin'])} total\n")
        L += ([f"- `{t['name']}` ({t['bytes']} B)" for t in info["thin"][:10]]
              or ["*None.*"])
        L.append(f"\n### Near-duplicate pairs (J≥{_DUP_J}) — {len(info['dup_pairs'])} total\n")
        L += ([f"- `{d['a']}` ↔ `{d['b']}` (J={d['jaccard']})" for d in info["dup_pairs"][:10]]
              or ["*None.*"])
        L.append(f"\n### Orphan nodes — {len(info['orphans'])} total\n")
        L += ([f"- `{o['name']}`" for o in info["orphans"][:10]] or ["*None.*"])
        if info["consolidation"]:
            L.append("\n### Consolidation candidates (≥5 near-identical in category)\n")
            L += [f"- **{c['category']}** — {c['n']} notes, avg J={c['avg_j']} "
                  f"(sample: `{c['sample']}`)" for c in info["consolidation"]]
        L.append("")
    L += ["## Reading this honestly",
          "- **Thin** notes: merge into a parent or expand with real content.",
          "- **Dup pairs**: keep the richer note; redirect the other.",
          "- **Orphans**: link them in or remove them.",
          "- Markets are efficient; no edge is claimed.",
          "", "## See also", "- [[_Brain|Platform Brain]]", "- [[_Index|Organized Index]]"]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_redundancy(organized_root: Optional[Path] = None,
                     write: bool = True) -> Dict:
    """Audit vault/_Organized/ for thin, dup, and orphan notes.

    Returns ``{by_sport, totals, _note}``.  Writes _Redundancy_Report.md when write=True.
    """
    root = Path(organized_root) if organized_root else (_REPO_ROOT / "vault" / "_Organized")
    if not root.exists():
        return {"by_sport": {}, "totals": {"n_notes": 0, "total_bytes": 0, "avg_bytes": 0,
                "n_thin": 0, "n_dup_pairs": 0, "n_orphans": 0},
                "_note": "intelligence map; markets efficient; calibration is not edge; no edge claimed"}

    # pre-scan all notes for cross-sport inlink counting
    all_flat: List[Dict] = []
    sport_dirs: List[Tuple[str, Path]] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and not child.name.startswith("_"):
            sport_dirs.append((child.name, child))
            for fp in child.rglob("*.md"):
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                    all_flat.append({"path": fp, "name": fp.name, "outlinks": _outlinks(text)})
                except OSError:
                    pass

    by_sport = {sp: _analyse(sdir, all_flat) for sp, sdir in sport_dirs}
    tn = sum(v.get("n_notes", 0) for v in by_sport.values())
    tb = sum(v.get("total_bytes", 0) for v in by_sport.values())
    totals = {"n_notes": tn, "total_bytes": tb,
              "avg_bytes": round(tb / tn) if tn else 0,
              "n_thin": sum(len(v.get("thin", [])) for v in by_sport.values()),
              "n_dup_pairs": sum(len(v.get("dup_pairs", [])) for v in by_sport.values()),
              "n_orphans": sum(len(v.get("orphans", [])) for v in by_sport.values())}
    if write:
        idx = root / "_Index"
        idx.mkdir(parents=True, exist_ok=True)
        (idx / "_Redundancy_Report.md").write_text(_render(by_sport), encoding="utf-8")
    return {"by_sport": by_sport, "totals": totals,
            "_note": "intelligence map; markets efficient; calibration is not edge; no edge claimed"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__); return 0
    root_arg = next((a for a in argv if not a.startswith("-")), None)
    rep = build_redundancy(organized_root=Path(root_arg) if root_arg else None, write=True)
    if "--json" in argv:
        print(json.dumps(rep, indent=2, default=str)); return 0
    t = rep["totals"]
    print(f"brain_redundancy: {t['n_notes']} notes | thin={t['n_thin']} "
          f"dup_pairs={t['n_dup_pairs']} orphans={t['n_orphans']}")
    for sp, info in sorted(rep["by_sport"].items()):
        if "skipped" in info:
            print(f"  [{sp:<7}] SKIPPED ({info['skipped']})")
        else:
            print(f"  [{sp:<7}] {info['n_notes']} notes | avg {info['avg_bytes']} B "
                  f"| thin={len(info['thin'])} dups={len(info['dup_pairs'])} "
                  f"orphans={len(info['orphans'])}")
    print(f"NOTE: {rep['_note']}"); return 0


if __name__ == "__main__":
    sys.exit(_main())
