"""brain_consolidate.py — merge near-identical stub notes into dense consolidated notes.

CLI: ``python -m scripts.platformkit.brain_consolidate [<organized_root>] [--json]``
Returns: {n_families, n_notes_merged, n_files_removed, n_links_repaired, by_sport, _note}
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BANNER = ("> **Intelligence map; markets efficient; calibration is not edge; "
           "no edge claimed.** Consolidated corpus-derived reference — "
           "descriptive only; NOT a signal and NOT a bet.")
MIN_FAMILY = 8
MIN_SEASON = 4   # min year-stubs per prefix to trigger season merge
JACCARD_THRESH = 0.80
MAX_TOKENS = 400
_SEASON_RE = re.compile(r"^(.+)\s+(\d{4})$")  # "La_Liga 2019" → prefix, year

_EXPLICIT: List[Tuple] = [
    ("Tennis", "Reference", "*.md",  ("_","Clay","Grass","Hard"), "Tournaments",
     "ATP/Grand Slam tournament reference stubs", MIN_FAMILY),
    ("Tennis", "Reference", None,    ("_",), "Surfaces", "Tennis surface stubs", 2),
    ("Tennis", "Trends",    "2*.md", ("_",), "YearTrends", "Tennis style-trends year stubs", 3),
]
_SURFACE_EXACT = ("Clay.md", "Grass.md", "Hard.md")
_FM_RE  = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
_HIST   = re.compile(r"[░▒▓█]+")
_BOLD_K = re.compile(r"\*\*([^*]+)\*\*")
_BULLET = re.compile(r"^-\s+")


def _tokenize(text: str) -> frozenset:
    return frozenset(re.findall(r"[a-z0-9]+", text.lower())[:MAX_TOKENS])

def _jaccard(a: frozenset, b: frozenset) -> float:
    u = len(a | b); return len(a & b) / u if u else 1.0

def _title(text: str, stem: str) -> str:
    m = re.search(r"^# (.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else stem

def _clean_fact(raw: str) -> Optional[str]:
    s = raw.strip().rstrip(";").strip()
    if _HIST.search(s): return None
    if not re.sub(r"[/|%\s0-9]", "", s) or re.fullmatch(r"[\s/|%0-9]+", s): return None
    s = _BOLD_K.sub(r"\1", _BULLET.sub("", s).strip())
    s = re.sub(r"\s+\([A-Z]\)$", "", s).strip()
    return re.sub(r"\s{2,}", " ", s) or None

_KEY_SYNONYMS = {"best_of": "format", "rounds": "format", "best of": "format",
                 "total_matches": "matches", "corpus_matches": "matches"}

def _norm_key(k: str) -> str:
    k = k.lower().strip()
    for pat, repl in [(r"_(label|count|total)$",""), (r"^total_",""),
                      (r"\s+in\s+corpus$",""), (r"^(typical\s+)?","")]:
        k = re.sub(pat, repl, k)
    k = k.strip()
    return _KEY_SYNONYMS.get(k, k)

def _facts(text: str, stem: str) -> List[str]:
    raw: List[str] = []
    fm = re.match(r"---\n(.*?)\n---", text, re.DOTALL)
    if fm:
        for ln in fm.group(1).splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("tags") or ln.startswith("-"): continue
            if "name:" in ln and stem.lower().replace(" ", "_") in ln.lower(): continue
            raw.append(ln)
    for ln in _FM_RE.sub("", text).splitlines():
        s = ln.strip()
        if not s or s.startswith(("#", "[[", ">")): continue
        if s.startswith("|") and ("---" in s or _HIST.search(s)): continue
        if (re.search(r"\d", s) and len(s) > 6) or "%" in s:
            raw.append(s)
    seen_keys: Set[str] = set(); out: List[str] = []
    for fragment in raw:
        c = _clean_fact(fragment)
        if not c: continue
        ci = c.find(":"); raw_key = c[:ci].strip() if ci != -1 else c
        key = _norm_key(raw_key)
        if key in seen_keys: continue
        seen_keys.add(key); out.append(c)
    return out

def _render(family_name: str, sport: str, category: str,
            stubs: List[Tuple[str, str, List[str]]], desc: str) -> str:
    slug = sport.lower()
    rows = "\n".join(
        f"| {title or stem} | {('; '.join(fs) or '(none)').replace('|','/')} |"
        for stem, title, fs in stubs)
    return (f"---\ntags:\n  - sport/{slug}\n  - organized\n  - consolidated"
            f"\n  - {category.lower()}\n---\n\n"
            f"# {sport} / {category} — {family_name} Consolidated\n\n{_BANNER}\n\n"
            f"*{desc}. One row per merged stub — every distinguishing fact preserved.*\n"
            f"*Merged {len(stubs)} stub notes into this single dense reference.*\n\n"
            f"[[_Index|{sport} Index]]\n\n## Fact Table\n\n"
            f"| Entry | Distinguishing Facts |\n|-------|---------------------|\n{rows}\n\n"
            f"## Notes\n- All {len(stubs)} stubs shared the same structural template.\n"
            f"- Intelligence map only; markets efficient; no edge claimed.\n\n"
            f"## See also\n- [[_Index|{sport} Index]]\n")

def _link_pattern(stem: str) -> re.Pattern:
    e = re.escape(stem)
    return re.compile(r"\[\[(?:[^|\]]*/)?" + e + r"(?:\.md)?(?:\|[^\]]+)?\]\]", re.IGNORECASE)

def _repair_file(fp: Path, stems: Set[str], cons_rel: str, cons_name: str) -> int:
    try: text = fp.read_text(encoding="utf-8", errors="replace")
    except OSError: return 0
    pats = {s: _link_pattern(s) for s in stems}
    cons_link = f"[[{cons_rel}|{cons_name}]]"
    changed = False; new_lines: List[str] = []; seen_cons = False
    for line in text.splitlines(keepends=True):
        nl = line
        for pat in pats.values():
            if pat.search(nl): nl = pat.sub(cons_link, nl)
        if nl != line: changed = True
        # drop all but the FIRST occurrence of a cons-only line (any position)
        stripped = nl.strip().lstrip("- ").strip()
        if stripped == cons_link:
            if seen_cons: changed = True; continue
            seen_cons = True
        new_lines.append(nl)
    if not changed: return 0
    fp.write_text("".join(new_lines), encoding="utf-8")
    return sum(1 for o, n in zip(text.splitlines(), "".join(new_lines).splitlines()) if o != n)

def _repair_sport(sport_dir: Path, stems: Set[str], cons_path: Path) -> int:
    if not stems: return 0
    total = 0
    for md in sport_dir.rglob("*.md"):
        if md == cons_path: continue
        try: rel = cons_path.relative_to(md.parent).as_posix().replace(".md", "")
        except ValueError:
            try: rel = cons_path.relative_to(sport_dir.parent).as_posix().replace(".md", "")
            except ValueError: rel = cons_path.stem
        total += _repair_file(md, stems, rel, cons_path.stem.lstrip("_").replace("_", " "))
    return total

def _consolidate_family(cat_dir: Path, name: str, members: List[Path],
                        sport: str, category: str, desc: str, write: bool,
                        sport_dir: Optional[Path] = None) -> Dict:
    out_path = cat_dir / f"_{name}_Consolidated.md"
    stubs = []
    for p in sorted(members, key=lambda x: x.stem):
        try: txt = p.read_bytes().decode("utf-8", errors="replace")
        except OSError: continue
        stubs.append((p.stem, _title(txt, p.stem), _facts(txt, p.stem)))
    md = _render(name, sport, category, stubs, desc)
    stems = {p.stem for p in members}; removed = n_links = 0
    if write:
        out_path.write_text(md, encoding="utf-8")
        for p in members:
            if p.exists() and p != out_path: p.unlink(); removed += 1
        n_links = _repair_sport(sport_dir or cat_dir.parent, stems, out_path)
    return {"family": name, "n_merged": len(stubs), "n_removed": removed,
            "n_links_repaired": n_links, "output": str(out_path)}

def _resolve_explicit(sport_dir: Path, spec: Tuple) -> Optional[Tuple]:
    sport, category, glob_pat, excl_pfx, name, desc, min_f = spec
    cat_dir = sport_dir / category
    if not cat_dir.is_dir(): return None
    if name == "Surfaces":
        members = [cat_dir / n for n in _SURFACE_EXACT if (cat_dir / n).exists()]
    else:
        members = [f for f in cat_dir.glob(glob_pat or "*.md")
                   if not any(f.name.startswith(p) for p in excl_pfx)
                   and "_Consolidated" not in f.name]
    return (name, sorted(members), desc) if len(members) >= min_f else None

def _detect_season_stubs(sport_dir: Path, category: str,
                         skip: Set[str]) -> List[Tuple]:
    """Group <Prefix YYYY>.md files by prefix; return one family per prefix with >= MIN_SEASON."""
    cat_dir = sport_dir / category
    if not cat_dir.is_dir(): return []
    groups: Dict[str, List[Path]] = {}
    for f in cat_dir.glob("*.md"):
        if f.name.startswith("_") or "_Consolidated" in f.name or f.stem in skip: continue
        m = _SEASON_RE.match(f.stem)
        if m: groups.setdefault(m.group(1), []).append(f)
    return [(f"{pfx.replace(' ','_')}_Seasons", sorted(fs),
             f"{pfx} season-by-season reference stubs")
            for pfx, fs in groups.items() if len(fs) >= MIN_SEASON]

def _detect_generic(sport_dir: Path, category: str,
                    skip: Set[str] = frozenset()) -> Optional[Tuple]:
    cat_dir = sport_dir / category
    if not cat_dir.is_dir(): return None
    cands = [f for f in cat_dir.glob("*.md")
             if not f.name.startswith("_") and "_Consolidated" not in f.name
             and f.stem not in skip]
    if len(cands) < MIN_FAMILY: return None
    tok = {}
    for f in cands:
        try: tok[f.name] = _tokenize(f.read_bytes().decode("utf-8", errors="replace"))
        except OSError: pass
    seen: set = set()
    for seed in cands:
        if seed.name in seen: continue
        st = tok.get(seed.name, frozenset())
        grp = [seed] + [o for o in cands if o.name != seed.name and o.name not in seen
                        and _jaccard(st, tok.get(o.name, frozenset())) >= JACCARD_THRESH]
        if len(grp) >= MIN_FAMILY:
            for p in grp: seen.add(p.name)
            return f"{category}_Generic", sorted(grp), f"{sport_dir.name} {category} stubs"
    return None

def consolidate(organized_root: Optional[Path] = None, write: bool = True,
                injected_families: Optional[List[Dict]] = None) -> Dict:
    """Detect stub families, merge each to one dense note, repair wikilinks. Idempotent."""
    root = Path(organized_root) if organized_root else (_REPO_ROOT / "vault" / "_Organized")
    by_sport: Dict[str, List[Dict]] = {}
    n_fam = n_merged = n_removed = n_links = 0

    if injected_families is not None:
        for spec in injected_families:
            sport, cat = spec["sport"], spec["category"]
            cat_dir = root / sport / cat; cat_dir.mkdir(parents=True, exist_ok=True)
            members = [Path(m) for m in spec["members"]]; sport_dir = root / sport
            if not members:
                by_sport.setdefault(sport, []).append(
                    {"family": spec["name"], "n_merged": 0, "n_removed": 0,
                     "n_links_repaired": 0,
                     "output": str(cat_dir / f"_{spec['name']}_Consolidated.md")}); continue
            info = _consolidate_family(cat_dir, spec["name"], members, sport, cat,
                                       spec.get("description", f"{sport} {cat}"), write,
                                       sport_dir=sport_dir)
            by_sport.setdefault(sport, []).append(info)
            n_fam += 1; n_merged += info["n_merged"]
            n_removed += info["n_removed"]; n_links += info.get("n_links_repaired", 0)
    else:
        skip_dirs = {".obsidian", "_Index"}
        for sport_dir in sorted(d for d in root.iterdir()
                                if d.is_dir() and d.name not in skip_dirs):
            sport = sport_dir.name; explicit_cats: set = set(); found: List[Tuple] = []
            for spec in _EXPLICIT:
                if spec[0] != sport: continue
                r = _resolve_explicit(sport_dir, spec)
                if r: found.append(r); explicit_cats.add(spec[1])
            season_claimed: Set[str] = set()
            for cd in sorted(sport_dir.iterdir()):
                if not cd.is_dir() or cd.name in explicit_cats: continue
                for tup in _detect_season_stubs(sport_dir, cd.name, set()):
                    found.append(tup); season_claimed.update(p.stem for p in tup[1])
            for cd in sorted(sport_dir.iterdir()):
                if not cd.is_dir() or cd.name in explicit_cats: continue
                r2 = _detect_generic(sport_dir, cd.name, season_claimed)
                if r2: found.append(r2)
            for name, members, desc in found:
                if not members: continue
                cat = members[0].parent.name
                info = _consolidate_family(sport_dir / cat, name, members, sport, cat,
                                           desc, write, sport_dir=sport_dir)
                by_sport.setdefault(sport, []).append(info)
                n_fam += 1; n_merged += info["n_merged"]
                n_removed += info["n_removed"]; n_links += info.get("n_links_repaired", 0)

    return {"n_families": n_fam, "n_notes_merged": n_merged, "n_files_removed": n_removed,
            "n_links_repaired": n_links, "by_sport": by_sport,
            "_note": ("intelligence map; markets efficient; calibration is not edge; "
                      "no edge claimed; merged stub notes into dense consolidated notes")}

def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv: print(__doc__); return 0
    root_arg = next((a for a in argv if not a.startswith("-")), None)
    rep = consolidate(organized_root=Path(root_arg) if root_arg else None, write=True)
    if "--json" in argv:
        print(json.dumps(rep, indent=2, default=str)); return 0
    print(f"brain_consolidate: {rep['n_families']} families merged "
          f"({rep['n_notes_merged']} stubs -> {rep['n_files_removed']} removed, "
          f"{rep['n_links_repaired']} links repaired)")
    for sport, infos in rep["by_sport"].items():
        for info in infos:
            print(f"  [{sport}/{info['family']}] {info['n_merged']} stubs -> {info['output']}")
    print(f"NOTE: {rep['_note']}")
    return 0

if __name__ == "__main__":
    sys.exit(_main())
