"""
brain_system_map.py -- emit a navigable Obsidian "system map" under vault/_System/.

Turns the curated funnel spec (brain_system_spec) into connected notes:
  Platform . Data -> Signals -> Models -> Engines -> Predictions -> Execution
  -> Intelligence (bridges into the existing _Organized/ sports brain).

Each stage hub links prev/next stage + its components + bridge targets; each
component links to its stage and flows to its downstream components. All links
are vault-root-relative (the form Obsidian resolves). Idempotent. No edge claims.

    python scripts/platformkit/brain_system_map.py vault [--dry-run]
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brain_system_spec import STAGES, COMPONENTS, BRIDGES, DISCLAIMER  # noqa: E402

SYS_DIR = "_System"


def _comp_paths() -> dict[str, str]:
    """component key -> vault-relative note path (no extension)."""
    m: dict[str, str] = {}
    for skey, comps in COMPONENTS.items():
        for ckey, *_ in comps:
            m[ckey] = f"{SYS_DIR}/{skey}/{ckey}"
    return m


def _comp_title() -> dict[str, str]:
    return {ckey: title for comps in COMPONENTS.values() for (ckey, title, *_) in comps}


def _link(rel: str, label: str) -> str:
    return f"[[{rel}|{label}]]"


def _stage_note(i: int, paths: dict, titles: dict) -> tuple[str, str]:
    skey, title, role = STAGES[i]
    out = [f"---\ntags: [system, {title.lower()}]\naliases: [{title} (system)]\n---",
           f"# {title} -- system stage", "", f"> {role}", ""]
    # funnel neighbours
    nav = []
    if i > 0:
        pk, pt, _ = STAGES[i - 1]
        nav.append("Prev: " + _link(f"{SYS_DIR}/{pk}", pt))
    if i < len(STAGES) - 1:
        nk, nt, _ = STAGES[i + 1]
        nav.append("Next: " + _link(f"{SYS_DIR}/{nk}", nt))
    nav.append(_link(f"{SYS_DIR}/_System_Index", "System Index"))
    if nav:
        out += [" | ".join(nav), ""]
    # components
    comps = COMPONENTS.get(skey, [])
    if comps:
        out.append("## Components")
        for ckey, ctitle, *_ in comps:
            out.append(f"- {_link(paths[ckey], ctitle)}")
        out.append("")
    # bridges into the existing sports brain
    br = BRIDGES.get(skey, [])
    if br:
        out.append("## Bridges into the brain")
        for t in br:
            out.append(f"- {_link(t, t.split('/')[-1].lstrip('_').replace('_', ' '))}")
        out.append("")
    out.append(f"> {DISCLAIMER}")
    return f"{SYS_DIR}/{skey}.md", "\n".join(out) + "\n"


def _component_note(skey: str, comp: tuple, paths: dict, titles: dict) -> tuple[str, str]:
    ckey, ctitle, blurb, files, flows = comp
    stage_title = next(t for k, t, _ in STAGES if k == skey)
    out = [f"---\ntags: [system, {stage_title.lower()}, component]\naliases: [{ctitle}]\n---",
           f"# {ctitle}", "", blurb, "",
           "Part of: " + _link(f"{SYS_DIR}/{skey}", stage_title), ""]
    if files:
        out.append("## Key files")
        for f in files:
            out.append(f"- `{f}`")
        out.append("")
    flows_real = [f for f in flows if f in paths]
    if flows_real:
        out.append("## Flows to")
        for f in flows_real:
            out.append(f"- {_link(paths[f], titles[f])}")
        out.append("")
    out.append(f"> {DISCLAIMER}")
    return f"{SYS_DIR}/{skey}/{ckey}.md", "\n".join(out) + "\n"


def _index_note(paths: dict) -> tuple[str, str]:
    out = ["---\ntags: [system, moc, index]\naliases: [System Map, Pipeline]\n---",
           "# System Map -- the whole pipeline", "",
           "> One graph from raw data to a calibrated prediction. " + DISCLAIMER, "",
           "## Funnel"]
    chain = " -> ".join(_link(f"{SYS_DIR}/{k}", t) for k, t, _ in STAGES)
    out += [chain, "", "## Stages"]
    for k, t, role in STAGES:
        out.append(f"- {_link(f'{SYS_DIR}/{k}', t)} -- {role}")
    out += ["", "## Back to the brain",
            f"- {_link('_Index', 'Master Index')}",
            f"- {_link('_Organized/_Index/_Brain', 'Brain Map')}", ""]
    return f"{SYS_DIR}/_System_Index.md", "\n".join(out) + "\n"


def build_system_map(vault_root, write: bool = True) -> dict:
    vault = Path(vault_root)
    paths, titles = _comp_paths(), _comp_title()
    notes: list[tuple[str, str]] = [_index_note(paths)]
    for i, (skey, _t, _r) in enumerate(STAGES):
        notes.append(_stage_note(i, paths, titles))
        for comp in COMPONENTS.get(skey, []):
            notes.append(_component_note(skey, comp, paths, titles))
    written = 0
    for rel, body in notes:
        p = vault / rel
        if write:
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists() or p.read_text(encoding="utf-8") != body:
                p.write_text(body, encoding="utf-8")
                written += 1
    return {"notes": len(notes), "written": written,
            "stages": len(STAGES), "components": sum(len(v) for v in COMPONENTS.values()),
            "mode": "WRITE" if write else "DRY"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Emit the Obsidian system map.")
    ap.add_argument("vault", nargs="?", default="vault")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    r = build_system_map(a.vault, write=not a.dry_run)
    for k, v in r.items():
        print(f"{k:11}: {v}")


if __name__ == "__main__":
    main()
