"""
brain_folder_indexes.py -- join the brain's island clusters into one graph.

Every concept folder under _Organized/<sport>/ gets a MANAGED index note
(``_<Folder>_Index.md``) that links EVERY note in the folder -- including
underscore-prefixed notes and any foreign index notes (e.g. ``_Mechanisms.md``)
-- AND recurses into subfolders (e.g. ``Reference/Seasons/``), linking each
subfolder's managed index. Each note carries a one-line description; the index
links UP to the sport's _Index + _Digest and to its prev/next sibling folder.
A per-sport ``_Index`` home links every top-level folder index + the sport hubs.

Result: master _Index -> sport _Index -> folder index -> (subfolder index ->) note,
one fully connected, navigable component. Idempotent (re-run = byte-identical);
all links are vault-root-relative (no ``../``, no ``.md``); no edge claims; the
managed file never clobbers a foreign index (distinct ``_<Folder>_Index`` name).

    python scripts/platformkit/brain_folder_indexes.py vault [--dry-run]
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brain_concept_blurbs import blurb  # noqa: E402

SPORTS = ("NBA", "MLB", "Soccer", "Tennis")
DISCLAIMER = "Intelligence MAP -- markets efficient; calibration, not a $ edge."
_FM = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


def _rel(p: Path, vault: Path) -> str:
    return p.relative_to(vault).as_posix()[:-3]


def _label(name: str) -> str:
    return name.lstrip("_").replace("_", " ")


def _managed(folder: Path) -> str:
    return f"_{folder.name}_Index.md"


# Sections whose first prose line is the best one-line description of a note.
_SUMMARY_SECTIONS = ("summary", "overview", "purpose", "what wins", "what wins & why",
                     "the idea", "what", "definition")
# Boilerplate disclaimer phrases -- a line that is *only* these is not a description.
_DISCLAIMER_BITS = (
    "intelligence map", "intelligence / calibration", "markets efficient",
    "markets are efficient", "calibration is not edge", "calibration, not a $ edge",
    "no edge claimed", "not a market edge", "not a signal", "not a bet",
    "not a $ edge", "descriptive concept node", "person-free",
)


def _clean(line: str) -> str:
    line = re.sub(r"[*`_\[\]]", "", line.lstrip("> ").strip())
    line = re.sub(r"\s+", " ", line)
    return "".join(ch for ch in line if ord(ch) < 128).strip()


def _is_disclaimer(line: str) -> bool:
    low = line.lower()
    for bit in _DISCLAIMER_BITS:
        low = low.replace(bit, "")
    return sum(c.isalnum() for c in low) < 25


def _prose(line: str) -> bool:
    return bool(line) and not line.startswith(("#", "|", "- ", "* ", "[[", "!["))


def _summary(path: Path) -> str:
    """One-line description: prefer a Summary-like section, else first real prose."""
    try:
        text = _FM.sub("", path.read_text(encoding="utf-8"), count=1)
    except (OSError, UnicodeDecodeError):
        return ""
    lines = text.splitlines()
    # 1) first prose line inside a Summary-like section
    in_sect = False
    for raw in lines:
        s = raw.strip()
        if s.startswith("#"):
            in_sect = s.lstrip("# ").strip().lower() in _SUMMARY_SECTIONS
            continue
        if in_sect:
            c = _clean(s)
            if _prose(c) and len(c) >= 12:
                return c[:110]
    # 2) first non-disclaimer prose line anywhere
    for raw in lines:
        c = _clean(raw.strip())
        if _prose(c) and len(c) >= 12 and not _is_disclaimer(c):
            return c[:110]
    return ""


def _link(p: Path, vault: Path, label: str | None = None) -> str:
    return f"[[{_rel(p, vault)}|{label or _label(p.stem)}]]"


def _notes(folder: Path) -> list[Path]:
    mng = _managed(folder)
    return sorted(n for n in folder.glob("*.md") if n.name != mng)


def _subfolders(folder: Path) -> list[Path]:
    return sorted(d for d in folder.iterdir()
                  if d.is_dir() and not d.name.startswith("."))


def _has_notes(folder: Path) -> bool:
    return any(folder.rglob("*.md"))


def _xsport(folder: Path, sport: str, vault: Path) -> list[Path]:
    """Same-named concept folder's managed index in the OTHER sports (if populated)."""
    org = vault / "_Organized"
    out: list[Path] = []
    for other in SPORTS:
        if other == sport:
            continue
        cand = org / other / folder.name
        if cand.is_dir() and _has_notes(cand):
            out.append(cand / _managed(cand))
    return out


def _build_folder(folder: Path, sport: str, vault: Path, up: str,
                  write: bool, counter: dict,
                  xsport: list[Path] | None = None) -> Path | None:
    """Recursively build managed indexes; return this folder's index path or None."""
    self_idx = folder / _managed(folder)
    sub_idx: list[Path] = []
    for sub in _subfolders(folder):
        child_up = (f"Up: {_link(self_idx, vault, _label(folder.name) + ' Index')}")
        res = _build_folder(sub, sport, vault, child_up, write, counter)
        if res is not None:
            sub_idx.append(res)
    notes = _notes(folder)
    if not notes and not sub_idx:
        return None

    plain = [n for n in notes if not n.name.startswith("_")]
    foreign = [n for n in notes if n.name.startswith("_")]
    out = [f"---\ntags: [organized, index, {sport.lower()}]\n"
           f"aliases: [{_label(folder.name)} Index]\n---",
           f"# {sport} -- {_label(folder.name)}", "",
           f"> {blurb(folder.name)} {DISCLAIMER}", "", up, ""]
    if sub_idx:
        out.append("## Subsections")
        for s in sub_idx:
            out.append(f"- {_link(s, vault, _label(s.parent.name))}")
        out.append("")
    if foreign:
        out.append("## Section hubs")
        for f in foreign:
            d = _summary(f)
            out.append(f"- {_link(f, vault)}" + (f" -- {d}" if d else ""))
        out.append("")
    if plain:
        out.append("## Notes")
        for n in plain:
            d = _summary(n)
            out.append(f"- {_link(n, vault)}" + (f" -- {d}" if d else ""))
        out.append("")
    if xsport:
        out.append("## Same concept in other sports")
        for x in xsport:
            other = x.relative_to(vault / "_Organized").parts[0]
            out.append(f"- {_link(x, vault, f'{other} {_label(folder.name)}')}")
        out.append("")
    out.append(f"> {DISCLAIMER}")
    body = "\n".join(out) + "\n"
    if write and (not self_idx.exists()
                  or self_idx.read_text(encoding="utf-8") != body):
        self_idx.write_text(body, encoding="utf-8")
        counter["written"] += 1
    counter["indexes"] += 1
    return self_idx


def _sport_index(sdir: Path, sport: str, folder_idx: list[Path],
                 vault: Path) -> tuple[Path, str]:
    hubs = [h for h in sorted(sdir.glob("_*.md")) if h.name != "_Index.md"]
    out = [f"---\ntags: [organized, index, home, {sport.lower()}]\n"
           f"aliases: [{sport}, {sport} Index]\n---",
           f"# {sport} -- Index", "",
           f"> The {sport} intelligence brain: concept folders, hubs and "
           f"reference. {DISCLAIMER}", "",
           "Up: [[_Index|Master Index]] | [[_Organized/_Index/_Brain|Brain Map]]", ""]
    out.append("## Hubs")
    for h in hubs:
        d = _summary(h)
        out.append(f"- {_link(h, vault)}" + (f" -- {d}" if d else ""))
    if not hubs:
        out.append("_(none)_")
    out += ["", "## Concepts"]
    for fi in folder_idx:
        out.append(f"- {_link(fi, vault, _label(fi.parent.name))}"
                   f" -- {blurb(fi.parent.name)}")
    out += ["", "## See also",
            "- [[_Organized/_Index/_Cross_Sport_Digest|Cross-sport Digest]]",
            "- [[_Organized/_Index/_Brain|Brain Map]]",
            "", f"> {DISCLAIMER}"]
    return sdir / "_Index.md", "\n".join(out) + "\n"


def build_folder_indexes(vault_root, write: bool = True) -> dict:
    vault = Path(vault_root)
    org = vault / "_Organized"
    counter = {"written": 0, "indexes": 0}
    by_sport: dict[str, dict] = {}
    sport_idx = 0
    for sport in SPORTS:
        sdir = org / sport
        if not sdir.is_dir():
            continue
        top_idx: list[Path] = []
        folders = sorted(d for d in sdir.iterdir() if d.is_dir()
                         and not d.name.startswith("."))
        for i, folder in enumerate(folders):
            sibs = []
            if i > 0:
                sibs.append("Prev: " + _link(folders[i - 1] / _managed(folders[i - 1]),
                                              vault, _label(folders[i - 1].name)))
            if i < len(folders) - 1:
                sibs.append("Next: " + _link(folders[i + 1] / _managed(folders[i + 1]),
                                             vault, _label(folders[i + 1].name)))
            up = (f"Up: [[_Organized/{sport}/_Index|{sport} Index]] | "
                  f"[[_Organized/{sport}/_Digest|{sport} Digest]]"
                  + ((" | " + " | ".join(sibs)) if sibs else ""))
            res = _build_folder(folder, sport, vault, up, write, counter,
                                xsport=_xsport(folder, sport, vault))
            if res is not None:
                top_idx.append(res)
        sp_path, sp_body = _sport_index(sdir, sport, top_idx, vault)
        if write and (not sp_path.exists()
                      or sp_path.read_text(encoding="utf-8") != sp_body):
            sp_path.write_text(sp_body, encoding="utf-8")
        sport_idx += 1
        by_sport[sport] = {"top_folders": len(top_idx)}
    return {"indexes": counter["indexes"], "written": counter["written"],
            "sport_indexes": sport_idx, "by_sport": by_sport,
            "mode": "WRITE" if write else "DRY"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Join brain folder islands into one graph.")
    ap.add_argument("vault", nargs="?", default="vault")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    import json
    print(json.dumps(build_folder_indexes(a.vault, write=not a.dry_run), indent=2))


if __name__ == "__main__":
    main()
