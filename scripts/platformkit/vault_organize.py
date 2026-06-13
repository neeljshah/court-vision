"""vault_organize.py — NON-DESTRUCTIVE clean/dedup re-organizer for the Obsidian vault.

Reads the EXISTING vault (read-only) and produces a fresh, deduped, large-category
tree under ``vault/_Organized/`` so the graph is clean WITHOUT touching the human's
live notes or pipeline.  Reversible: it only ever COPIES content out — never moves,
edits, or deletes a source file.  Each player is CANONICAL: exactly ONE note nested
under their SINGLE parsed team; duplicate player-ids collapse to the richest.

Output layout under *out_dir* (default ``vault/_Organized``):
  Teams/<TEAM>/<player_slug>.md   canonical player notes (one per player id)
  Teams/<TEAM>/_Team.md           team hub (links its players)
  Teams/_Unassigned/...           players with no parseable team
  Archetypes/ Schemes/ Trends/    person-free intelligence (copied)
  _Index/_Brain.md                top map-of-content

Team parse: a player note's body has ``**Team:** [[PHX]]`` -> team = wikilink target.
Player id = the digit prefix of the filename (``2544_lebron``).  Pure stdlib.
CLI: ``python -m scripts.platformkit.vault_organize`` -> writes out/ + before/after.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Reuse the W60 linter to MEASURE before/after (inventory + leaks) and its byte fmt.
from scripts.platformkit.vault_person_free_lint import (  # noqa: E402
    _fmt_bytes,
    lint_vault,
)

# player-id prefix: leading digits then "_", e.g. "2544_lebron_james".
_PLAYER_ID_RE = re.compile(r"^(\d{3,})_")
# the "**Team:** [[PHX]]" body line -> capture the wikilink target.
_TEAM_LINE_RE = re.compile(r"^\*\*Team:\*\*\s*\[\[([A-Za-z0-9_]+)\]\]")
# the "**Archetype:** ..." fragment (after the Team link, same line) for the hub.
_ARCH_RE = re.compile(r"\*\*Archetype:\*\*\s*([^·*\n]+)")

# Person-free intelligence subdirs (under Intelligence/) folded into large
# out categories of the same name.
_INTEL_CATEGORIES: List[str] = ["Archetypes", "Schemes", "Trends"]
_UNASSIGNED = "_Unassigned"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _read_safe(path: Path) -> Optional[str]:
    """Read text; return None on any OS/decoding failure (caller skips+counts)."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _player_id(stem: str) -> Optional[str]:
    """Player id = leading digit prefix of the filename stem, else None."""
    m = _PLAYER_ID_RE.match(stem)
    return m.group(1) if m else None


def _parse_team(text: str) -> Optional[str]:
    """Parse the team tricode from the ``**Team:** [[XXX]]`` body line, else None."""
    for raw in text.splitlines():
        m = _TEAM_LINE_RE.match(raw.strip())
        if m:
            return m.group(1)
    return None


def _parse_archetype(text: str) -> str:
    """Best-effort archetype label for the team-hub listing ('' if absent)."""
    m = _ARCH_RE.search(text)
    return m.group(1).strip() if m else ""


# --------------------------------------------------------------------------- #
# player dedup
# --------------------------------------------------------------------------- #

def _collect_players(players_dir: Path) -> Tuple[Dict[str, dict], int, int]:
    """Walk *players_dir*; return (canonical_by_id, n_dupes_collapsed, n_skipped).

    Canonical per player id = the RICHEST note (largest byte size).  Unreadable or
    no-id notes are skipped + counted; dedup tie-breaks on stem for determinism.
    """
    canonical: Dict[str, dict] = {}
    dupes = 0
    skipped = 0
    if not players_dir.is_dir():
        return canonical, dupes, skipped
    for path in sorted(players_dir.rglob("*.md")):
        if not path.is_file():
            continue
        pid = _player_id(path.stem)
        if pid is None:
            skipped += 1
            continue
        text = _read_safe(path)
        if text is None:
            skipped += 1
            continue
        # "richest" = largest content (byte length of the read text).
        rec = {
            "path": path, "stem": path.stem, "text": text,
            "size": len(text.encode("utf-8")),
            "team": _parse_team(text) or _UNASSIGNED,
            "archetype": _parse_archetype(text),
        }
        prev = canonical.get(pid)
        if prev is None:
            canonical[pid] = rec
        else:
            dupes += 1
            # keep the richest; tie-break on stem for determinism.
            if (rec["size"], rec["stem"]) > (prev["size"], prev["stem"]):
                canonical[pid] = rec
    return canonical, dupes, skipped


# --------------------------------------------------------------------------- #
# writers
# --------------------------------------------------------------------------- #

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_players(canonical: Dict[str, dict], teams_root: Path) -> Dict[str, List[str]]:
    """Write each canonical player under Teams/<team>/<stem>.md.  Return team->stems."""
    by_team: Dict[str, List[str]] = {}
    for pid in sorted(canonical):
        rec = canonical[pid]
        team = rec["team"]
        _write(teams_root / team / f"{rec['stem']}.md", rec["text"])
        by_team.setdefault(team, []).append(rec["stem"])
    for team in by_team:
        by_team[team].sort()
    return by_team


def _team_hub(team: str, recs: List[dict]) -> str:
    """Render a Teams/<team>/_Team.md hub linking its canonical players."""
    lines = [
        "---\ntags: [organized, team, hub]\n---",
        f"# {team} — Roster\n",
        f"> Canonical roster hub. {len(recs)} player(s), each appearing exactly once "
        "under this team. Auto-generated by `scripts/platformkit/vault_organize.py`.\n",
    ]
    for rec in sorted(recs, key=lambda r: r["stem"]):
        arch = f" — {rec['archetype']}" if rec["archetype"] else ""
        lines.append(f"- [[{rec['stem']}]]{arch}")
    return "\n".join(lines) + "\n"


def _write_team_hubs(canonical: Dict[str, dict], by_team: Dict[str, List[str]],
                     teams_root: Path) -> None:
    recs_by_team: Dict[str, List[dict]] = {}
    for rec in canonical.values():
        recs_by_team.setdefault(rec["team"], []).append(rec)
    for team in sorted(by_team):
        _write(teams_root / team / "_Team.md", _team_hub(team, recs_by_team.get(team, [])))


def _copy_intel(intel_root: Path, out_dir: Path) -> Dict[str, int]:
    """Copy person-free intelligence families into large out categories.  Counts."""
    counts: Dict[str, int] = {}
    for category in _INTEL_CATEGORIES:
        src = intel_root / category
        n = 0
        for path in sorted(src.rglob("*.md")) if src.is_dir() else []:
            text = _read_safe(path) if path.is_file() else None
            if text is None:
                continue
            _write(out_dir / category / path.relative_to(src), text)
            n += 1
        counts[category] = n
    return counts


def _write_brain(out_dir: Path, by_team: Dict[str, List[str]],
                 intel_counts: Dict[str, int]) -> None:
    """Top-level MOC: a few large categories + per-team roster links."""
    n_players = sum(len(v) for v in by_team.values())
    n_teams = sum(1 for t in by_team if t != _UNASSIGNED)
    cats = ", ".join(f"{c} ({n})" for c, n in sorted(intel_counts.items()))
    lines = [
        "---\ntags: [organized, brain, moc]\n---",
        "# Organized Vault — Brain\n",
        "> Clean, deduped, large-category view of the vault. Every player appears "
        "exactly once, nested under their single team. Non-destructive copy — the "
        "live `vault/` notes are untouched. Generated by "
        "`scripts/platformkit/vault_organize.py`.\n",
        f"**{n_players} canonical players across {n_teams} team(s)** "
        f"(+ Unassigned) · intelligence categories: {cats}\n",
        "## Teams\n",
    ]
    for team in sorted(by_team):
        lines.append(f"- [[_Team|{team}]] ({len(by_team[team])}) — `Teams/{team}/`")
    lines.append("\n## Intelligence categories\n")
    for category in sorted(intel_counts):
        lines.append(f"- `{category}/` ({intel_counts[category]} notes)")
    _write(out_dir / "_Index" / "_Brain.md", "\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #

def organize_vault(vault_dir: Optional[Path] = None, out_dir: Optional[Path] = None,
                   copy: bool = True) -> Dict:
    """Build a clean deduped large-category tree from *vault_dir* into *out_dir*.

    Non-destructive: reads source read-only, writes only under *out_dir* (a FRESH
    dir, wiped if it already exists — NEVER a live vault folder).  Returns a report
    with before/after inventory, duplicates_collapsed, players-per-team, and the
    person-leak count before vs after (via the W60 linter).  *copy* is accepted for
    API symmetry; content is always copied (we never move/delete the source).
    """
    vault_dir = Path(vault_dir) if vault_dir is not None else (_REPO_ROOT / "vault")
    out_dir = Path(out_dir) if out_dir is not None else (vault_dir / "_Organized")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    before = lint_vault(vault_dir)

    intel_root = vault_dir / "Intelligence"
    teams_root = out_dir / "Teams"
    canonical, dupes, skipped = _collect_players(intel_root / "Players")
    by_team = _write_players(canonical, teams_root)
    _write_team_hubs(canonical, by_team, teams_root)
    intel_counts = _copy_intel(intel_root, out_dir)
    _write_brain(out_dir, by_team, intel_counts)

    after = lint_vault(out_dir)
    players_per_team = {t: len(v) for t, v in sorted(by_team.items())}
    return {
        "vault_dir": str(vault_dir),
        "out_dir": str(out_dir),
        "duplicates_collapsed": dupes,
        "skipped_player_notes": skipped,
        "canonical_players": len(canonical),
        "n_teams": sum(1 for t in by_team if t != _UNASSIGNED),
        "players_per_team": players_per_team,
        "intel_counts": intel_counts,
        "before": {"n_files": before["n_files"], "total_bytes": before["total_bytes"],
                   "person_leaks": sum(before["leak_counts"].values())},
        "after": {"n_files": after["n_files"], "total_bytes": after["total_bytes"],
                  "person_leaks": sum(after["leak_counts"].values())},
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    vault_dir = Path(argv[0]) if argv and not argv[0].startswith("-") else None
    rep = organize_vault(vault_dir=vault_dir)
    if "--json" in argv:
        print(json.dumps(rep, indent=2))
        return 0
    b, a = rep["before"], rep["after"]
    print(f"source : {rep['vault_dir']}")
    print(f"out    : {rep['out_dir']}")
    print(f"\n{'':12}{'files':>10}{'size':>12}{'leaks':>10}")
    print(f"{'BEFORE':12}{b['n_files']:>10}{_fmt_bytes(b['total_bytes']):>12}{b['person_leaks']:>10}")
    print(f"{'AFTER':12}{a['n_files']:>10}{_fmt_bytes(a['total_bytes']):>12}{a['person_leaks']:>10}")
    print(f"\nduplicates collapsed : {rep['duplicates_collapsed']}")
    print(f"canonical players    : {rep['canonical_players']} (skipped {rep['skipped_player_notes']})")
    print(f"teams                : {rep['n_teams']} (+Unassigned)")
    cats = ", ".join(f"{c}={n}" for c, n in sorted(rep['intel_counts'].items()))
    print(f"intel categories     : {cats}\nplayers per team:")
    for team, n in sorted(rep["players_per_team"].items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {n:>4}  {team}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
