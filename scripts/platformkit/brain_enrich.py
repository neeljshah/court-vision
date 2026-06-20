"""
brain_enrich.py -- enrich the top-level brain indexes and connect every
top-level area to the master _Index (the last reachability gap).

Two idempotent, marker-delimited passes (re-run = byte-identical for a fixed
tree; never clobbers the curated body -- only its own managed block):

  enrich_master(vault):
      Appends/refreshes an "Atlas -- every brain area" block on vault/_Index.md
      that links the system map, EVERY top-level area dir (e.g. _Edge_Maps,
      _TrackRecord, Improvements) note-by-note with a one-line description, and
      a Journal section of root-level dated notes. Because it walks the
      filesystem, any future top-level area/note is linked automatically -- so
      the graph stays 100% reachable from the index without hand edits.

  enrich_hubs(vault):
      Appends/refreshes a navigation footer (Up + sibling hubs + See also) on
      each vault/_Organized/_Index/*.md cross-sport hub.

All links are vault-root-relative (no ../, no .md). No edge claims.

    python scripts/platformkit/brain_enrich.py vault [--dry-run]
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brain_folder_indexes import _summary, _label  # noqa: E402

DISCLAIMER = "Intelligence MAP -- markets efficient; calibration, not a $ edge."
_M0, _M1 = "<!-- BRAIN:ENRICH:START -->", "<!-- BRAIN:ENRICH:END -->"
_SKIP_DIRS = {"_Organized", "_System", ".obsidian"}


def _rel(p: Path, vault: Path) -> str:
    return p.relative_to(vault).as_posix()[:-3]


def _link(p: Path, vault: Path, label: str | None = None) -> str:
    return f"[[{_rel(p, vault)}|{label or _label(p.stem)}]]"


def _li(p: Path, vault: Path, label: str | None = None) -> str:
    d = _summary(p)
    return f"- {_link(p, vault, label)}" + (f" -- {d}" if d else "")


def _replace_block(text: str, block: str) -> str:
    """Insert or replace the managed marker block; idempotent."""
    new = f"{_M0}\n{block}\n{_M1}"
    if _M0 in text and _M1 in text:
        pre = text[: text.index(_M0)]
        post = text[text.index(_M1) + len(_M1):]
        return pre.rstrip() + "\n\n" + new + post
    return text.rstrip() + "\n\n" + new + "\n"


def _master_block(vault: Path) -> str:
    out = ["## Atlas -- every brain area", "",
           f"> Auto-maintained map of every top-level area, so the whole brain "
           f"is reachable from here. {DISCLAIMER}", ""]
    sysidx = vault / "_System/_System_Index.md"
    if sysidx.exists():
        out += ["### Pipeline & system", _li(sysidx, vault, "System Map"), ""]
    # every top-level area dir (durable: future dirs auto-link)
    for d in sorted(p for p in vault.iterdir()
                    if p.is_dir() and p.name not in _SKIP_DIRS):
        notes = sorted(d.rglob("*.md"))
        if not notes:
            continue
        out.append(f"### {_label(d.name)}")
        for n in notes:
            out.append(_li(n, vault))
        out.append("")
    # journal: every root-level note except the master index (dated notes + strays)
    journal = sorted(p for p in vault.glob("*.md") if p.stem != "_Index")
    if journal:
        out.append("### Journal & loose notes")
        for n in journal:
            out.append(_li(n, vault))
        out.append("")
    return "\n".join(out).rstrip()


def enrich_master(vault: Path, write: bool = True) -> bool:
    idx = vault / "_Index.md"
    if not idx.exists():
        return False
    text = idx.read_text(encoding="utf-8")
    new = _replace_block(text, _master_block(vault))
    changed = new != text
    if changed and write:
        idx.write_text(new, encoding="utf-8")
    return changed


def enrich_hubs(vault: Path, write: bool = True) -> int:
    hub_dir = vault / "_Organized/_Index"
    if not hub_dir.is_dir():
        return 0
    hubs = sorted(hub_dir.glob("*.md"))
    changed = 0
    for h in hubs:
        sibs = [x for x in hubs if x != h]
        foot = ["## Navigation", "",
                "Up: [[_Index|Master Index]] | [[_Organized/_Index/_Brain|Brain Map]]",
                "", "### Other cross-sport hubs"]
        for s in sibs:
            foot.append(f"- {_link(s, vault)}")
        foot += ["", "### See also",
                 "- [[_Index|Master Index]]",
                 "- [[_System/_System_Index|System Map]]",
                 "", f"> {DISCLAIMER}"]
        text = h.read_text(encoding="utf-8")
        new = _replace_block(text, "\n".join(foot).rstrip())
        if new != text:
            changed += 1
            if write:
                h.write_text(new, encoding="utf-8")
    return changed


def enrich_all(vault_root, write: bool = True) -> dict:
    vault = Path(vault_root)
    return {"master_changed": enrich_master(vault, write),
            "hubs_changed": enrich_hubs(vault, write),
            "mode": "WRITE" if write else "DRY"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Enrich top-level brain indexes.")
    ap.add_argument("vault", nargs="?", default="vault")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    import json
    print(json.dumps(enrich_all(a.vault, write=not a.dry_run), indent=2))


if __name__ == "__main__":
    main()
