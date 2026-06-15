"""vault_person_free_lint.py — Person-free linter + size inventory for the vault.

The vault is a graph of PLAYSTYLES / ARCHETYPES — never people. Measures SIZE/SHAPE
(file/byte counts per subdir) + PERSON LEAKS: ``named_title`` (``# First Last`` heading,
archetype-allowlisted + concept-dir-exempt), ``named_filename`` (``<digits>_<word>_<word>``
or filename matchup), ``matchup_vs`` (``<Word> vs <Word>`` / ``<TEAM>@<TEAM>``, concept
pairs OK). Pure stdlib. CLI: ``python -m scripts.platformkit.vault_person_free_lint [dir]``.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

# concept dirs (person-free by construction) -> named_title exempt; see concept_dirs.py
from scripts.platformkit.concept_dirs import under_concept_dir as _under_concept_dir

# === Configuration ===
# Cap on the reported leaks list (inventory totals are always exact).
_MAX_LEAKS = 200

# Allowlist of capitalized two-word NON-NAME concepts (archetypes/schemes/section
# titles). Compared case-insensitively as the joined two words. Tunable.
_ALLOWLIST_PHRASES = frozenset(p.lower() for p in (
    "Primary Initiator", "Rim Runner", "Pick And", "And Roll", "Pick Roll",
    "Stretch Big", "Three Level", "Catch Shoot", "Spot Up", "Roll Man",
    "Lob Threat", "Floor Spacer", "Two Way", "High Usage", "Low Usage",
    "Off Ball", "On Ball", "Ball Handler", "Shot Creator", "Defensive Anchor",
    "Rim Protector", "Perimeter Defender", "Wing Stopper", "Point Forward",
    "Combo Guard", "Stretch Four", "Stretch Five", "Pace Pusher", "Half Court",
    "Fast Break", "Iso Heavy", "Post Up", "Zone Buster", "Switch Heavy",
    "Drop Coverage", "Man Coverage", "Transition Heavy", "Closeout Defender",
    "Volume Scorer", "Efficient Scorer", "Connector Wing", "Defensive Grinder",
    "Baseline Aggressor", "Slasher Cutter", "Movement Shooter", "Signal Catalog",
    "Style Trends", "Style Matchups", "Home Environment", "Scheme Transitions",
    "Graph Health", "World Model",
))

# Single archetype/scheme words — a two-word title containing ANY of these is a
# concept, not a person.
_ALLOWLIST_TOKENS = frozenset(t.lower() for t in (
    "Initiator Runner Shooter Scorer Defender Creator Handler Anchor Protector "
    "Stopper Spacer Cutter Slasher Aggressor Grinder Connector Pusher Buster "
    "Coverage Archetype Playstyle Matchup Matchups Catalog Trends Environment "
    "Transitions Scheme Schemes Profile Index Overview Summary Report Health "
    "Model Big Guard Forward Wing Center Roll Iso Post Heavy Court Break Level "
    "Usage Two Off Ball "
    # archetype/scheme concept words in generated titles + comparisons
    "Bench Contributor Specialist Role Player Defensive Offensive Attacking "
    "Spacing Scoring Block Low High Floor Drop Switch Zone Man Help Run "
    "Prevention Poisson Dominant Versatile Balanced Contender Routine Variance "
    "Finishing Territorial Control Late Comeback Tiebreak Surface Serve Hold "
    "Bullpen Inning Pace Rebounding Turnovers Shooting Margin Structure"
).split())

# Team tricodes for "TEAM @ TEAM" / "TEAM vs TEAM" matchup detection.
_TEAM_RE = r"[A-Z]{2,4}"
_TEAM_RE_FULL = re.compile(r"^[A-Z]{2,4}$")  # full team-code token guard

# === Compiled patterns ===
# "# First Last" heading: exactly two Title-Case words (allow apostrophes/hyphens).
_NAMED_TITLE_RE = re.compile(
    r"^#\s+([A-Z][a-z]+(?:['’-][A-Za-z]+)?)\s+([A-Z][a-z]+(?:['’-][A-Za-z]+)?)\s*$"
)

# player-id_first_last.md filename, e.g. 1626164_devin_booker.md
_NAMED_FILENAME_RE = re.compile(r"^\d{3,}_[a-z]+_[a-z]+", re.IGNORECASE)

# "Word vs Word" matchup (content or filename). Word may be a TEAM code or a name.
_MATCHUP_VS_RE = re.compile(r"\b([A-Za-z][\w'.-]+)\s+vs\.?\s+([A-Za-z][\w'.-]+)", re.IGNORECASE)

# "TEAM @ TEAM" matchup, e.g. LAL@BOS
_MATCHUP_AT_RE = re.compile(rf"\b{_TEAM_RE}\s*@\s*{_TEAM_RE}\b")


# === Data type ===
@dataclass(frozen=True)
class Leak:
    """A single person-free violation."""

    file: str   # vault-relative path (forward slashes)
    kind: str
    sample: str

    def as_dict(self) -> Dict[str, str]:
        return {"file": self.file, "kind": self.kind, "sample": self.sample}


# === Helpers ===
def _read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _relposix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _top_dir(rel: str) -> str:
    """Top-level subdir of a vault-relative path; '.' for root-level files."""
    parts = rel.split("/")
    return parts[0] if len(parts) > 1 else "."


def _word_is_concept(word: str) -> bool:
    """True if a word (or any hyphen/apostrophe sub-token) is an allowlist concept,
    e.g. 'Floor-Spacing' -> ['floor','spacing']."""
    if word.lower() in _ALLOWLIST_TOKENS:
        return True
    return any(p in _ALLOWLIST_TOKENS
               for p in re.split(r"[-’'.]", word.lower()) if p)


def _is_allowlisted_title(w1: str, w2: str) -> bool:
    """True if a two-word Title-Case heading is a known archetype/scheme concept."""
    joined = f"{w1} {w2}".lower()
    if joined in _ALLOWLIST_PHRASES:
        return True
    return _word_is_concept(w1) or _word_is_concept(w2)


def _vs_pair_is_allowlisted(a: str, b: str) -> bool:
    """Suppress benign 'X vs Y' concept comparisons (e.g. 'accuracy vs edge',
    'Drop vs Switch', 'over-dispersed vs Poisson') while still flagging real
    proper-noun team/person matchups ('Lakers vs Celtics', 'LAL vs BOS').
    """
    # Lowercase/hyphenated common-noun comparisons are not person/team matchups.
    if a[:1].islower() and b[:1].islower():
        return True
    # A hyphenated side (e.g. 'over-dispersed', 'Run-scoring') is a concept phrase.
    if ("-" in a or "-" in b) and not (_TEAM_RE_FULL.match(a) and _TEAM_RE_FULL.match(b)):
        return True
    # Either side a known archetype/scheme/comparison concept word.
    if _word_is_concept(a) or _word_is_concept(b):
        return True
    return False


# === Inventory ===
def inventory_only(vault_dir) -> Dict:
    """Size/count inventory of every .md file under *vault_dir*.

    Returns keys: n_files, total_bytes, by_dir, biggest_dirs.
    """
    root = Path(vault_dir)
    by_dir: Dict[str, Dict[str, int]] = {}
    n_files = 0
    total_bytes = 0

    if root.is_dir():
        for path in sorted(root.rglob("*.md")):
            if not path.is_file():
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            rel = _relposix(path, root)
            top = _top_dir(rel)
            n_files += 1
            total_bytes += size
            slot = by_dir.setdefault(top, {"n_files": 0, "bytes": 0})
            slot["n_files"] += 1
            slot["bytes"] += size

    biggest: List[Tuple[str, int]] = sorted(
        ((d, v["bytes"]) for d, v in by_dir.items()),
        key=lambda kv: (-kv[1], kv[0]),
    )[:10]

    return {
        "n_files": n_files,
        "total_bytes": total_bytes,
        "by_dir": by_dir,
        "biggest_dirs": biggest,
    }


# === Leak detection ===
def _scan_filename(rel: str, stem: str) -> List[Leak]:
    leaks: List[Leak] = []
    if _NAMED_FILENAME_RE.search(stem):
        leaks.append(Leak(rel, "named_filename", stem))
    m = _MATCHUP_VS_RE.search(stem.replace("_", " "))
    if m and not _vs_pair_is_allowlisted(m.group(1), m.group(2)):
        leaks.append(Leak(rel, "matchup_vs", m.group(0)))
    if _MATCHUP_AT_RE.search(stem):
        leaks.append(Leak(rel, "matchup_vs", stem))
    return leaks


def _scan_content(rel: str, text: str) -> List[Leak]:
    leaks: List[Leak] = []
    for raw in text.splitlines():
        line = raw.strip()
        mt = _NAMED_TITLE_RE.match(line)
        if (mt and not _is_allowlisted_title(mt.group(1), mt.group(2))
                and not _under_concept_dir(rel)):
            leaks.append(Leak(rel, "named_title", line))
        mv = _MATCHUP_VS_RE.search(line)
        if mv and not _vs_pair_is_allowlisted(mv.group(1), mv.group(2)):
            leaks.append(Leak(rel, "matchup_vs", mv.group(0)))
        elif _MATCHUP_AT_RE.search(line):
            leaks.append(Leak(rel, "matchup_vs", _MATCHUP_AT_RE.search(line).group(0)))
    return leaks


def _scan_file(path: Path, rel: str) -> List[Leak]:
    leaks = _scan_filename(rel, path.stem)
    leaks.extend(_scan_content(rel, _read_safe(path)))
    return leaks


# === Top-level report ===
def lint_vault(vault_dir) -> Dict:
    """Inventory + person-free lint of *vault_dir*. Returns the full report dict."""
    root = Path(vault_dir)
    inv = inventory_only(root)

    all_leaks: List[Leak] = []
    leak_counts: Dict[str, int] = {}
    if root.is_dir():
        for path in sorted(root.rglob("*.md")):
            if not path.is_file():
                continue
            rel = _relposix(path, root)
            for leak in _scan_file(path, rel):
                leak_counts[leak.kind] = leak_counts.get(leak.kind, 0) + 1
                if len(all_leaks) < _MAX_LEAKS:
                    all_leaks.append(leak)

    total_leaks = sum(leak_counts.values())
    return {
        "n_files": inv["n_files"],
        "total_bytes": inv["total_bytes"],
        "by_dir": inv["by_dir"],
        "leaks": [l.as_dict() for l in all_leaks],
        "leak_counts": leak_counts,
        "person_free": total_leaks == 0,
        "biggest_dirs": inv["biggest_dirs"],
    }


# === CLI ===
def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024.0
    return f"{n:.1f}GB"


def main(argv: List[str] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    if argv:
        vault_dir = Path(argv[0])
    else:
        vault_dir = Path(__file__).resolve().parents[2] / "vault"

    if "--json" in argv:
        print(json.dumps(lint_vault(vault_dir), indent=2))
        return 0

    report = lint_vault(vault_dir)
    print(f"vault: {vault_dir}")
    print(f"files: {report['n_files']}   total: {_fmt_bytes(report['total_bytes'])}")
    print("\nbiggest dirs:")
    for d, b in report["biggest_dirs"][:10]:
        print(f"  {_fmt_bytes(b):>10}  {d}")
    print("\nleak_counts:")
    if report["leak_counts"]:
        for kind, n in sorted(report["leak_counts"].items()):
            print(f"  {n:>6}  {kind}")
    else:
        print("  (none)")
    print(f"\nperson_free: {report['person_free']}")
    if report["leaks"]:
        print("\nsample leaks:")
        for leak in report["leaks"][:10]:
            print(f"  [{leak['kind']}] {leak['file']}: {leak['sample'][:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
