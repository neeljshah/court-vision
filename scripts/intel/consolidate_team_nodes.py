"""One node per team. Fold Matchups/<TEAM>.md (2025-26 identity + scouting) and
GamePlans/<TEAM>.md (opposing-GM tactical report) INTO the canonical
Teams/<TEAM>.md, then delete the duplicate team files and repoint links.

Why Teams/ is canonical: scripts/intel/render_schemes_to_vault.py (the SessionStart
hook) owns Teams/<TEAM>.md but only replaces its <!-- SCHEME-AUTO --> block and
SKIPS missing notes — so it preserves our folded content and never recreates the
deleted Matchups/GamePlans team files. Folded content is wrapped in TEAMFOLD
markers placed BEFORE the SCHEME-AUTO block.

Player notes link bare [[<TEAM>]] -> after deleting the dupes, only Teams/<TEAM>.md
has that basename, so they resolve cleanly. Idempotent.
"""
from __future__ import annotations
import os, re, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTEL = ROOT / "vault" / "Intelligence"
TEAMS_D = INTEL / "Teams"
MATCH_D = INTEL / "Matchups"
GP_D = INTEL / "GamePlans"
TEAMS = ['ATL','BKN','BOS','CHA','CHI','CLE','DAL','DEN','DET','GSW','HOU','IND','LAC','LAL','MEM','MIA','MIL','MIN','NOP','NYK','OKC','ORL','PHI','PHX','POR','SAC','SAS','TOR','UTA','WAS']
FS, FE = "<!-- TEAMFOLD-START -->", "<!-- TEAMFOLD-END -->"
SCHEME_START = "<!-- SCHEME-AUTO START -->"


def _strip_h1(body: str) -> str:
    lines = body.split("\n")
    out = [ln for ln in lines if not re.match(r"^#\s", ln)]
    return "\n".join(out).strip()


def _gameplan_body(txt: str) -> str:
    m = re.search(r"<!-- GAMEPLAN START -->(.*?)<!-- GAMEPLAN END -->", txt, re.S)
    if m:
        return m.group(1).strip()
    # fallback: drop frontmatter + nav lines
    txt = re.sub(r"^---.*?---", "", txt, flags=re.S)
    txt = "\n".join(l for l in txt.split("\n") if not l.strip().startswith("←") and not l.startswith("> "))
    return _strip_h1(txt).strip()


def fold_team(tri: str) -> bool:
    tnote = TEAMS_D / f"{tri}.md"
    if not tnote.exists():
        print(f"  [skip] Teams/{tri}.md missing"); return False
    parts = []
    mnote = MATCH_D / f"{tri}.md"
    if mnote.exists():
        parts.append(_strip_h1(mnote.read_text(encoding="utf-8")))
    gnote = GP_D / f"{tri}.md"
    if gnote.exists():
        gp = _gameplan_body(gnote.read_text(encoding="utf-8"))
        if gp:
            parts.append("## Game Plan — How to Attack / Defend Them\n\n" + gp)
    if not parts:
        return False
    block = FS + "\n\n" + "\n\n---\n\n".join(parts) + "\n\n" + FE
    txt = tnote.read_text(encoding="utf-8")
    # remove old fold
    if FS in txt and FE in txt:
        txt = re.sub(re.escape(FS) + r".*?" + re.escape(FE) + r"\n?", "", txt, flags=re.S)
    # insert before SCHEME-AUTO (so hook preserves), else append
    if SCHEME_START in txt:
        i = txt.index(SCHEME_START)
        txt = txt[:i].rstrip() + "\n\n" + block + "\n\n" + txt[i:]
    else:
        txt = txt.rstrip() + "\n\n" + block + "\n"
    tnote.write_text(txt, encoding="utf-8")
    # delete dupes
    if mnote.exists():
        mnote.unlink()
    if gnote.exists():
        gnote.unlink()
    return True


def fix_links():
    """Repoint [[GamePlans/<TRI>...]] and [[Matchups/<TRI>...]] -> [[Teams/<TRI>]] across the vault."""
    changed = 0
    for fp in glob.glob(str(INTEL / "**" / "*.md"), recursive=True):
        try:
            txt = open(fp, encoding="utf-8").read()
        except Exception:
            continue
        orig = txt
        for tri in TEAMS:
            # [[GamePlans/ATL]] or [[GamePlans/ATL|label]] -> [[Teams/ATL]]
            txt = re.sub(r"\[\[GamePlans/" + tri + r"(\|[^\]]*)?\]\]", f"[[Teams/{tri}]]", txt)
            txt = re.sub(r"\[\[Matchups/" + tri + r"(\|[^\]]*)?\]\]", f"[[Teams/{tri}]]", txt)
        # generic GamePlans_Index link -> drop to Teams index / scheme matrix
        txt = txt.replace("[[GamePlans_Index|All Game Plans]]", "[[_Scheme_Matrix|All Teams]]")
        txt = txt.replace("[[GamePlans_Index]]", "[[_Scheme_Matrix]]")
        if txt != orig:
            open(fp, "w", encoding="utf-8").write(txt)
            changed += 1
    print(f"  repointed links in {changed} notes")


def cleanup_orphans():
    for orphan in ["GamePlans_Index.md"]:
        p = INTEL / orphan
        if p.exists():
            p.unlink(); print(f"  removed {orphan}")
    # remove now-empty GamePlans dir
    try:
        if GP_D.exists() and not any(GP_D.iterdir()):
            GP_D.rmdir(); print("  removed empty GamePlans/ dir")
    except Exception:
        pass


if __name__ == "__main__":
    folded = sum(fold_team(t) for t in TEAMS)
    print(f"folded {folded} teams into Teams/<TEAM>.md (deleted Matchups/<TEAM> + GamePlans/<TEAM>)")
    fix_links()
    cleanup_orphans()
    # report remaining per-team node count
    leftover = [d for d in ["Teams", "Matchups", "GamePlans"]
                for f in glob.glob(str(INTEL / d / "*.md"))
                if Path(f).stem in TEAMS]
    from collections import Counter
    print("per-team .md files remaining by dir:", dict(Counter(
        Path(f).parent.name for d in ["Teams", "Matchups", "GamePlans"]
        for f in glob.glob(str(INTEL / d / "*.md")) if Path(f).stem in TEAMS)))
