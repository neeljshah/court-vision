"""brain_concept_nodes — generic CONCEPT-NODE generator for the person-free brain.

Turns every person-free spec module in ``scripts.platformkit.specs`` (the contract is
documented in that package's ``__init__``) into MANY dense Obsidian graph nodes under
``vault/_Organized/<SPORT>/<FAMILY>/<slug>.md``, plus a per-family ``_Index.md`` hub.
Adding a spec module multiplies the brain's node count — all organized, all person-free.

Each node carries YAML frontmatter, the honest banner, and the six dense sections
(Summary / Stat Signature / Mechanism / Conditions / Magnitude / Related). The Related
section resolves each declared link slug against a GLOBAL map of every emitted node and
renders a POSIX-relative ``[[path|title]]`` wikilink, preferring a same-SPORT target;
links that do not resolve to a real emitted node are DROPPED (the graph stays clean —
no dangling links, BY CONSTRUCTION, because the map only contains nodes we write).

HONEST: a descriptive intelligence map; markets are efficient; calibration is not edge;
no edge / ROI / pick is ever claimed. Idempotent (re-run overwrites identically),
deterministic, pure stdlib at module top.

CLI: ``python -m scripts.platformkit.brain_concept_nodes [<organized_root>] [--json]``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from posixpath import relpath as _posix_relpath
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BANNER = (
    "> **Intelligence map; markets efficient; calibration is not edge; no edge "
    "claimed.** Descriptive concept node — NOT a signal and NOT a bet."
)
# (sport, family, relpath-from-organized-root, title) for one emitted node.
_Entry = Tuple[str, str, str, str]


def _norm_specs(injected_specs) -> List[Tuple[str, str, list]]:
    """Coerce injected (SPORT, FAMILY, CONCEPTS) tuples to a clean triple list."""
    out: List[Tuple[str, str, list]] = []
    for item in injected_specs or []:
        sport, family, concepts = item
        out.append((str(sport), str(family), list(concepts or [])))
    return out


def _discover_specs() -> Tuple[List[Tuple[str, str, list]], List[str]]:
    """Import every real spec module; return (triples, skipped-notes).

    A module that fails to import, lacks SPORT/FAMILY/CONCEPTS, or has an invalid
    SPORT is SKIPPED HONESTLY (never crashes the rebuild). Modules whose name starts
    with ``_`` (and ``__init__``) are ignored.
    """
    import importlib
    import pkgutil

    from scripts.platformkit import specs as _specs_pkg
    from scripts.platformkit.specs import SPEC_MODULE_VARS, VALID_SPORTS

    triples: List[Tuple[str, str, list]] = []
    skipped: List[str] = []
    for mod_info in sorted(
        pkgutil.iter_modules(_specs_pkg.__path__), key=lambda m: m.name
    ):
        name = mod_info.name
        if name.startswith("_"):
            continue
        full = f"{_specs_pkg.__name__}.{name}"
        try:
            mod = importlib.import_module(full)
        except Exception as exc:  # noqa: BLE001 — honest skip, never crash
            skipped.append(f"{name}: import failed ({type(exc).__name__}: {exc})")
            continue
        if not all(hasattr(mod, v) for v in SPEC_MODULE_VARS):
            skipped.append(f"{name}: missing one of {SPEC_MODULE_VARS}")
            continue
        sport = str(getattr(mod, "SPORT"))
        if sport not in VALID_SPORTS:
            skipped.append(f"{name}: invalid SPORT {sport!r}")
            continue
        triples.append((sport, str(getattr(mod, "FAMILY")), list(getattr(mod, "CONCEPTS"))))
    return triples, skipped


def _collect(
    triples,
) -> Tuple[Dict[str, _Entry], List[Tuple[str, str, dict]], List[str], Dict[str, List[_Entry]]]:
    """Validate concepts; build the GLOBAL slug map + the ordered emit list.

    Returns (global_map, emit, skipped, by_slug). ``global_map`` maps each unique slug
    to ONE canonical entry; ``by_slug`` is the full per-slug index that link resolution
    consults for same-SPORT preference. ``by_slug`` is RETURNED (not stashed on the
    function object) so concurrent calls never clobber each other's state.
    """
    from scripts.platformkit.specs import validate_concept

    by_slug: Dict[str, List[_Entry]] = {}
    emit: List[Tuple[str, str, dict]] = []          # (sport, family, concept)
    skipped: List[str] = []
    seen: set = set()                                # (sport, family, slug) dedup
    for sport, family, concepts in triples:
        for c in concepts:
            problems = validate_concept(c)
            if problems:
                skipped.append(f"{sport}/{family}/{c.get('slug','?')}: {'; '.join(problems)}")
                continue
            slug = str(c["slug"])
            key = (sport, family, slug)
            if key in seen:
                skipped.append(f"{sport}/{family}/{slug}: duplicate slug in family")
                continue
            seen.add(key)
            relpath = f"{sport}/{family}/{slug}.md"
            by_slug.setdefault(slug, []).append((sport, family, relpath, str(c["title"])))
            emit.append((sport, family, c))
    # Flatten to a deterministic canonical map (first-seen wins) for the public report.
    global_map = {s: entries[0] for s, entries in by_slug.items()}
    return global_map, emit, skipped, by_slug


def _resolve(link_slug: str, from_rel: str, from_sport: str, by_slug) -> Optional[str]:
    """Return a POSIX-relative wikilink to a REAL emitted node, or None to DROP it.

    Prefers a same-SPORT target; else the first declared target. Because ``by_slug``
    only holds slugs we actually write, a non-None result always points at a real node.
    """
    entries = by_slug.get(str(link_slug))
    if not entries:
        return None
    chosen = next((e for e in entries if e[0] == from_sport), entries[0])
    _sport, _family, target_rel, title = chosen
    from_dir = from_rel.rsplit("/", 1)[0] if "/" in from_rel else ""
    rel = _posix_relpath(target_rel, from_dir or ".")
    target = rel[:-3] if rel.endswith(".md") else rel          # drop .md for the link
    return f"- [[{target}|{title}]]"


def _frontmatter(sport: str, family: str) -> str:
    tags = f"[organized, {sport.lower()}, {family.lower()}, concept, person-free]"
    return f"---\ntags: {tags}\n---\n"


def _section(heading: str, body) -> str:
    text = str(body).strip() or "_(none)_"
    return f"## {heading}\n{text}\n"


def _render_node(sport: str, family: str, c: dict, by_slug) -> str:
    rel = f"{sport}/{family}/{c['slug']}.md"
    related = [r for r in (_resolve(s, rel, sport, by_slug) for s in c.get("links", [])) if r]
    related_body = "\n".join(related) if related else "_(no resolved related concepts)_"
    parts = [
        _frontmatter(sport, family),
        f"# {c['title']}\n",
        _BANNER + "\n",
        _section("Summary", c.get("summary", "")),
        _section("Stat Signature", c.get("stat_signature", "")),
        _section("Mechanism", c.get("mechanism", "")),
        _section("Conditions", c.get("conditions", "")),
        _section("Magnitude", c.get("magnitude", "")),
        f"## Related\n{related_body}\n",
    ]
    return "\n".join(parts).rstrip() + "\n"


def _render_index(sport: str, family: str, members: List[Tuple[str, str]]) -> str:
    """members: ordered (slug, title) for this (sport, family)."""
    lines = "\n".join(f"- [[{slug}|{title}]]" for slug, title in members) or "_(empty)_"
    return (
        f"{_frontmatter(sport, family)}"
        f"# {sport} · {family} — Concept Index\n\n"
        f"{_BANNER}\n\n"
        f"{len(members)} concept node(s) in this family.\n\n"
        f"{lines}\n"
    )


def build_concept_nodes(
    organized_root=None,
    write: bool = True,
    injected_specs=None,
) -> dict:
    """Generate concept nodes from spec modules (or ``injected_specs``).

    Production: discovers every spec module. Test seam: pass ``injected_specs`` as a
    list of ``(SPORT, FAMILY, CONCEPTS_list)`` tuples to bypass disk discovery.
    Returns a report dict (see module docstring / task contract).
    """
    if organized_root is None:
        organized_root = _REPO_ROOT / "vault" / "_Organized"
    organized_root = Path(organized_root)

    if injected_specs is not None:
        triples = _norm_specs(injected_specs)
        skipped = []
    else:
        triples, skipped = _discover_specs()
    n_modules = len(triples)

    _global_map, emit, collect_skips, by_slug = _collect(triples)
    skipped = skipped + collect_skips

    # Group emitted concepts by (sport, family), preserving first-seen order.
    families: "Dict[Tuple[str, str], List[dict]]" = {}
    order: List[Tuple[str, str]] = []
    for sport, family, c in emit:
        key = (sport, family)
        if key not in families:
            families[key] = []
            order.append(key)
        families[key].append(c)

    by_sport_family: Dict[str, int] = {}
    n_nodes = 0
    for (sport, family) in order:
        members = families[(sport, family)]
        fam_dir = organized_root / sport / family
        if write:
            fam_dir.mkdir(parents=True, exist_ok=True)
        for c in members:
            n_nodes += 1
            if write:
                (fam_dir / f"{c['slug']}.md").write_text(
                    _render_node(sport, family, c, by_slug), encoding="utf-8"
                )
        if write:
            (fam_dir / "_Index.md").write_text(
                _render_index(sport, family, [(c["slug"], str(c["title"])) for c in members]),
                encoding="utf-8",
            )
        by_sport_family[f"{sport}/{family}"] = len(members)

    return {
        "n_modules": n_modules,
        "n_nodes": n_nodes,
        "n_skipped": len(skipped),
        "by_sport_family": by_sport_family,
        "skipped": skipped,
        "_note": (
            "Descriptive person-free concept nodes; markets efficient; calibration is "
            "not edge; no edge claimed. Every emitted [[link]] resolves to a real node; "
            "unresolved links are dropped."
        ),
    }


def _main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    positional = [a for a in argv if not a.startswith("--")]
    root = Path(positional[0]) if positional else None
    rep = build_concept_nodes(organized_root=root, write=True)
    if as_json:
        print(json.dumps(rep, indent=2))
    else:
        print(
            f"concept nodes: {rep['n_nodes']} node(s) from {rep['n_modules']} module(s), "
            f"{rep['n_skipped']} skipped"
        )
        for sf, n in sorted(rep["by_sport_family"].items()):
            print(f"  {sf}: {n}")
        for s in rep["skipped"]:
            print(f"  SKIP {s}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["build_concept_nodes"]
