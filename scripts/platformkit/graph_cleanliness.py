"""graph_cleanliness.py — Graph-view cleanliness checker for vault/_Organized/.

Scans vault/_Organized/ for .md files and checks two classes of violations:
  1. SPECIFIC-PLAYER nodes  — filenames or wikilinks naming a real person
  2. SPECIFIC-MATCH nodes   — filenames or wikilinks naming a date-specific game

ALLOWED: tactical concept links ([[Drop vs Switch]], [[_WhatWins]], team _Identity
hubs, archetype/scheme concept nodes).

Exit code 0 = clean; exit code 1 = violations found.

CLI: ``python -m scripts.platformkit.graph_cleanliness [vault_organized_dir]``
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple

# ── repo bootstrap ──────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ── constants ────────────────────────────────────────────────────────────────
# Tactical/concept tokens: a two-word combo where EITHER word appears here is
# considered a concept, not a person name.
_CONCEPT_TOKENS = frozenset((
    "drop switch zone man help base balanced paint perimeter pace iso transition "
    "halfcourt closeout coverage scheme defense offense run scoring prevention "
    "power grinder speed contact stars initiator runner shooter scorer defender "
    "creator handler anchor protector stopper spacer cutter slasher aggressor "
    "connector pusher buster archetype playstyle matchups catalog trends env "
    "schemes index overview summary report health model big guard forward wing "
    "center roll usage two off ball identity stretch bench contributor dominant "
    "versatile picks pick three and rim floor high low primary lead contender "
    "movement combo profile cross sport digest read validated drivers risk "
    "mechanisms coverage archetypes brain moc what wins variance attacking "
    "prone leaky home strong defensive entertaining entertainment "
    "specialist interior playmaking rebounding scoring pitching sp hand inning "
    "total runs game mode style season seasons role player "
    "open masters finals cup tennis atp wta grand slam tournament circuit "
    "australian french british american canadian miami miami indian shanghai "
    "buenos laver sao paris madrid rome queen delray toronto monte "
    "active closeouts drop switch matrix effects scheme effects "
    "winton winston salem beach carolina paris roland garros queens queen new york "
    "los cabos york club "
    # generated Driver/Mechanism concept slugs (two-lowercase-word combos)
    "free throws swing bullpen late comeback red card ht collapse territorial "
    "control broke bp conversion edge margin structure tiebreak weight lead "
    "result stability finishing surface serve hold "
).split())

# Known team tricodes / full-names that appear in team vs team matchup lines.
# We do NOT want "Lakers vs Warriors" as a specific match node.
# We detect TEAM vs TEAM by checking if both sides look like proper team names.
_KNOWN_TEAM_TRICODES = frozenset((
    "nba mlb nfl nhl mls epl bundesliga laliga seriea ligue1 "
    "atl bkn bos cha chi cle dal den det gsw hou ind lac lal mem mia mil "
    "min nop nyk okc orl phi phx por sac sas tor uta was "
    "ari bal chc cin cle col cws det hou kan laa lad mia mil min nym nyy "
    "oak phi pit sea sfg stl tex tor was "
    "arsenal chelsea liverpool mancity manutd tottenham everton "
    "barca realmadrid atletico juventus milan inter "
    "bayernmunich dortmund leverkusen"
).split())

# Generated concept directories: files here are person-free CONCEPT notes by
# construction (Driver/Mechanism/Archetype/Scheme slugs, _Index hubs, Trends/
# Reference). Their two-lowercase-word stems must NOT be read as player filenames.
# Generated concept dirs (single source of truth in concept_dirs.py). Files here are
# person-free CONCEPT notes by construction; the id-prefixed player guard below still
# ALWAYS flags real player nodes regardless of directory.
from scripts.platformkit.concept_dirs import under_concept_dir as _under_concept_dir  # noqa: E402


# Date-like patterns in filenames: YYYY-MM-DD or YYYYMMDD
_DATE_FILENAME_RE = re.compile(r"\d{4}[-_]\d{2}[-_]\d{2}")
# Game-id-like patterns: YYYYMMDD + team codes
_GAME_ID_RE = re.compile(r"\b\d{8}[A-Z]{2,4}\b")
# Wikilink extractor
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
# Player-id filename prefix: 3+ leading digits then underscore (e.g. 2544_lebron)
_PLAYER_ID_FILENAME_RE = re.compile(r"^\d{3,}_[a-z]", re.IGNORECASE)
# Lowercase first_last or first-last-suffix: two or more lowercase words (letters/hyphens)
# e.g. "aaron_holiday", "shai_gilgeous-alexander"
_FIRSTLAST_LOWER_RE = re.compile(r"^[a-z]{2,}(?:[_-][a-z]{2,})+$")
# Two-word name: first word starts uppercase (any case after), second word Title-Case
# e.g. "LeBron James", "Aaron Holiday"
_TITLE_NAME_RE = re.compile(r"^([A-Z][A-Za-z']{1,})\s+([A-Z][a-z]{1,}(?:['-][A-Za-z]+)?)$")


# ── helpers ──────────────────────────────────────────────────────────────────

def _is_concept_token(word: str) -> bool:
    return word.lower() in _CONCEPT_TOKENS


def _is_player_filename(stem: str) -> bool:
    """True if the stem looks like a player name: id_first_last or first_last[-suffix]."""
    if _PLAYER_ID_FILENAME_RE.match(stem):
        return True
    # Only match purely-lowercase stems (team hubs like NYK_Identity are uppercase)
    clean = stem.lower()
    if clean != stem:
        return False   # mixed/upper-case = archetype/team/concept node, not a player
    if _FIRSTLAST_LOWER_RE.match(clean) and not any(c.isdigit() for c in clean):
        parts = re.split(r"[_-]", clean)
        # If ANY part is a concept token, treat as concept node not a player name
        if any(_is_concept_token(p) for p in parts):
            return False
        return True
    return False


def _is_match_filename(stem: str) -> bool:
    """True if the stem looks like a specific game/match file."""
    if _DATE_FILENAME_RE.search(stem):
        return True
    if _GAME_ID_RE.search(stem):
        return True
    return False


def _wikilink_is_player(link_target: str) -> bool:
    """True if a wikilink target looks like a specific player name."""
    # strip path prefix
    target = link_target.split("/")[-1].strip()
    if _PLAYER_ID_FILENAME_RE.match(target):
        return True
    # Two-word Title/Mixed-case name (e.g. "LeBron James", "Aaron Holiday")
    m = _TITLE_NAME_RE.match(target)
    if m:
        w1, w2 = m.group(1), m.group(2)
        # Skip if either part is a known concept token (e.g. "Drop Coverage")
        return not (_is_concept_token(w1) or _is_concept_token(w2))
    # lowercase first_last as wikilink target
    if _is_player_filename(target):
        return True
    return False


def _wikilink_is_match(link_target: str) -> bool:
    """True if a wikilink target looks like a specific game/match."""
    target = link_target.split("/")[-1].strip()
    return bool(_DATE_FILENAME_RE.search(target) or _GAME_ID_RE.search(target))


# ── scanning ─────────────────────────────────────────────────────────────────

class Violation(NamedTuple):
    file: str
    kind: str   # "player_node" | "match_node" | "player_link" | "match_link"
    detail: str


def scan_file(path: Path, root: Path) -> List[Violation]:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()

    violations: List[Violation] = []
    stem = path.stem
    in_concept_dir = _under_concept_dir(rel)

    # --- filename checks ---
    # The id-prefix form (2544_lebron) is unambiguous and always flags. The
    # two-lowercase-word heuristic is exempted under generated concept dirs, whose
    # slugs (free_throws, tiebreak_swing, ...) are Driver/Mechanism notes, not names.
    if _PLAYER_ID_FILENAME_RE.match(stem):
        violations.append(Violation(rel, "player_node", stem))
    elif not in_concept_dir and _is_player_filename(stem):
        violations.append(Violation(rel, "player_node", stem))
    if _is_match_filename(stem):
        violations.append(Violation(rel, "match_node", stem))

    # --- wikilink checks ---
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return violations

    for m in _WIKILINK_RE.finditer(text):
        target = m.group(1).strip()
        if _wikilink_is_player(target):
            violations.append(Violation(rel, "player_link", f"[[{target}]]"))
        elif _wikilink_is_match(target):
            violations.append(Violation(rel, "match_link", f"[[{target}]]"))

    return violations


def scan_vault(organized_dir: Path) -> Dict:
    """Scan all .md files under organized_dir. Return a structured report."""
    if not organized_dir.is_dir():
        return {"error": f"not a directory: {organized_dir}", "clean": False}

    all_files: List[Path] = sorted(organized_dir.rglob("*.md"))
    n_total = len(all_files)
    violations: List[Violation] = []
    for path in all_files:
        violations.extend(scan_file(path, organized_dir))

    by_kind: Dict[str, int] = {}
    for v in violations:
        by_kind[v.kind] = by_kind.get(v.kind, 0) + 1

    player_nodes = by_kind.get("player_node", 0)
    match_nodes = by_kind.get("match_node", 0)
    player_links = by_kind.get("player_link", 0)
    match_links = by_kind.get("match_link", 0)
    clean = (player_nodes == 0 and match_nodes == 0)

    # Hub-link coverage: count files that link to a known hub
    hub_patterns = re.compile(
        r"\[\[(?:[^\]|#]*/)?"
        r"(_WhatWins|_Brain|_Brain_MOC|_Drivers|_Mechanisms|_Archetypes|_Schemes"
        r"|_Archetypes_Index|_Scheme_Effects_Matrix|_Trends_Overview|_Index|_Brain\.md)"
    )
    n_hub_linked = 0
    for path in all_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if hub_patterns.search(text):
            n_hub_linked += 1

    pct_hub_linked = round(100 * n_hub_linked / max(n_total, 1), 1)
    return {
        "n_files": n_total,
        "n_hub_linked": n_hub_linked,
        "pct_hub_linked": pct_hub_linked,
        "player_nodes": player_nodes,
        "match_nodes": match_nodes,
        "player_links": player_links,
        "match_links": match_links,
        "by_kind": by_kind,
        "violations": [v._asdict() for v in violations[:100]],
        "clean": clean,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    vault_arg = next((a for a in argv if not a.startswith("-")), None)
    if vault_arg:
        organized_dir = Path(vault_arg)
    else:
        organized_dir = _REPO_ROOT / "vault" / "_Organized"

    rep = scan_vault(organized_dir)

    if "--json" in argv:
        print(json.dumps(rep, indent=2))
        return 0 if rep.get("clean") else 1

    print(f"vault/_Organized : {organized_dir}")
    if "error" in rep:
        print(f"ERROR: {rep['error']}")
        return 1

    print(f"total .md files  : {rep['n_files']}")
    print(f"hub-linked files : {rep['n_hub_linked']}  ({rep['pct_hub_linked']}%)")
    print(f"player nodes     : {rep['player_nodes']}  (must be 0)")
    print(f"match nodes      : {rep['match_nodes']}  (must be 0)")
    print(f"player links     : {rep['player_links']}  (advisory)")
    print(f"match links      : {rep['match_links']}  (advisory)")
    print(f"CLEAN            : {rep['clean']}")

    if rep["violations"]:
        print("\nFirst 20 violations:")
        for v in rep["violations"][:20]:
            print(f"  [{v['kind']}] {v['file']} — {v['detail']}")

    if not rep["clean"]:
        print("\nFAIL: specific-player or specific-match NODES found.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
