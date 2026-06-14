"""vault_sources.py — Per-sport source descriptors + small parsers for the multi-sport
Obsidian vault organizer.

Defines a frozen SportSpec dataclass describing WHERE each sport's notes live inside
``vault/`` and what categories to include vs drop.  The ``source_specs`` factory returns
one SportSpec per supported sport.  Pure stdlib; NO pandas/pyarrow imports at module top.

SportSpec fields
----------------
name          : canonical sport key used as the output sub-folder name (e.g. "NBA").
is_solo       : True for solo sports (Tennis); team sports keep players nested in teams.
teams_dir     : Path to per-team note files (team sports only; None for solo).
players_dir   : Path to individual player note files (NBA: Intelligence/Players; solo:
                sport-specific Players/ if present; None if absent).
team_note_dir : Same as teams_dir for most sports — the dir with one .md per team that
                supplies the DENSE content folded into each _Team.md hub.
archetype_dirs: List of Paths whose .md files become the Archetypes/ output category.
scheme_dirs   : List of Paths whose .md files become the Schemes/ output category.
trend_dirs    : List of Paths whose .md files become the Trends/ output category.
reference_dirs: List of Paths whose .md files become the Reference/ output category.
drop_dirs     : List of Paths to silently ignore (Matchups/, StyleMatchups/, etc.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# --------------------------------------------------------------------------- #
# helpers used by vault_organize_multi (tiny, sport-generic parsers)
# --------------------------------------------------------------------------- #

_PLAYER_ID_RE = re.compile(r"^(\d{3,})_")
_TEAM_LINE_RE = re.compile(r"^\*\*Team:\*\*\s*\[\[([A-Za-z0-9_]+)\]\]")
_ARCH_RE = re.compile(r"\*\*Archetype:\*\*\s*([^·*\n]+)")
_POS_RE = re.compile(r"\*\*Position:?\*\*\s*([A-Za-z/ -]+)")
_USAGE_RE = re.compile(r"\*\*Usage rate:?\*\*\s*([\d.]+%?)")


def parse_player_id(stem: str) -> Optional[str]:
    """Leading digit prefix of a filename stem, else None (e.g. '2544' from '2544_lebron')."""
    m = _PLAYER_ID_RE.match(stem)
    return m.group(1) if m else None


def parse_team_from_body(text: str) -> Optional[str]:
    """Extract team tricode from ``**Team:** [[XXX]]`` body line."""
    for raw in text.splitlines():
        m = _TEAM_LINE_RE.match(raw.strip())
        if m:
            return m.group(1)
    return None


def parse_archetype_from_body(text: str) -> str:
    """Best-effort archetype label ('' if absent) — used for team-hub roster histograms."""
    m = _ARCH_RE.search(text)
    return m.group(1).strip() if m else ""


def parse_position(text: str) -> str:
    """Player position from ``- **Position:** Guard`` body line ('' if absent)."""
    m = _POS_RE.search(text)
    return m.group(1).strip() if m else ""


def parse_usage(text: str) -> str:
    """Player usage rate from ``- **Usage rate:** 15.9%`` ('' if absent)."""
    m = _USAGE_RE.search(text)
    return m.group(1).strip() if m else ""


def roster_aggregate(recs: List[dict]) -> Dict:
    """Aggregate a team's player records (each with archetype + full text) into
    archetype/position distributions, roster rows, and a top-3 style signature.
    """
    arch_hist: Dict[str, int] = {}
    pos_hist: Dict[str, int] = {}
    rows: List[Dict[str, str]] = []
    for r in recs:
        arch = r.get("archetype", "") or "Unknown"
        arch_hist[arch] = arch_hist.get(arch, 0) + 1
        txt = r.get("text", "")
        pos = parse_position(txt) or "—"
        pos_hist[pos] = pos_hist.get(pos, 0) + 1
        rows.append({"stem": r.get("stem", ""), "archetype": arch,
                     "position": pos, "usage": parse_usage(txt) or "—"})
    n = max(len(recs), 1)
    top = sorted(arch_hist.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    sig = ", ".join(f"{a} ({c * 100 // n}%)" for a, c in top)
    return {"n": len(recs), "arch_hist": arch_hist, "pos_hist": pos_hist,
            "rows": rows, "style_signature": sig}


# --------------------------------------------------------------------------- #
# SportSpec
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SportSpec:
    """Immutable descriptor of a sport's source layout inside vault/."""

    name: str                               # output folder key, e.g. "NBA"
    is_solo: bool                           # True -> no team nesting; Players/ allowed
    teams_dir: Optional[Path]               # dir of <TRI>.md team files (team sports)
    players_dir: Optional[Path]             # dir of player .md files (may be None)
    team_note_dir: Optional[Path]           # dir whose .md content folds into _Team hubs
    archetype_dirs: List[Path] = field(default_factory=list)
    scheme_dirs: List[Path] = field(default_factory=list)
    trend_dirs: List[Path] = field(default_factory=list)
    reference_dirs: List[Path] = field(default_factory=list)
    drop_dirs: List[Path] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# factory
# --------------------------------------------------------------------------- #

def source_specs(vault_dir: Path) -> List[SportSpec]:
    """Return one SportSpec per supported sport rooted at *vault_dir*."""
    v = vault_dir

    # ------------------------------------------------------------------ NBA --
    nba_root = v / "Sports" / "Basketball_NBA"
    nba_intel = v / "Intelligence"
    nba = SportSpec(
        name="NBA",
        is_solo=False,
        teams_dir=nba_intel / "Teams",          # Intelligence/Teams/<TRI>.md
        players_dir=nba_intel / "Players",      # Intelligence/Players/<id>_first_last.md
        team_note_dir=nba_intel / "Teams",      # same as teams_dir for NBA
        archetype_dirs=[
            nba_intel / "Archetypes",           # Intelligence/Archetypes/
            nba_root / "Archetypes" / "Archetypes",  # Sports/Basketball_NBA/Archetypes/Archetypes/
        ],
        scheme_dirs=[nba_intel / "Schemes"],
        trend_dirs=[
            nba_intel / "Trends",
            nba_root / "Trends" / "Trends",
        ],
        reference_dirs=[
            nba_root / "Scouting",
            nba_root / "Seasons",
            nba_root / "Seasons" / "Seasons",
        ],
        drop_dirs=[
            nba_intel / "Matchups",
            v / "Intelligence" / "Pairs",
        ],
    )

    # ------------------------------------------------------------------ MLB --
    mlb_root = v / "Sports" / "MLB"
    mlb = SportSpec(
        name="MLB",
        is_solo=False,
        teams_dir=mlb_root / "Teams",
        players_dir=None,                        # no individual player notes
        team_note_dir=mlb_root / "Teams",
        archetype_dirs=[mlb_root / "Playstyles"],
        scheme_dirs=[],
        trend_dirs=[mlb_root / "StyleTrends"],
        reference_dirs=[
            mlb_root / "HomeEnvironment",
            mlb_root / "Leagues",
            mlb_root / "Seasons",
            mlb_root / "Signals",
            mlb_root / "Scouting",
        ],
        drop_dirs=[
            mlb_root / "Matchups",
            mlb_root / "StyleMatchups",
        ],
    )

    # --------------------------------------------------------------- Soccer --
    soccer_root = v / "Sports" / "Soccer"
    soccer = SportSpec(
        name="Soccer",
        is_solo=False,
        teams_dir=soccer_root / "Teams",
        players_dir=None,
        team_note_dir=soccer_root / "Teams",
        archetype_dirs=[soccer_root / "Playstyles"],
        scheme_dirs=[soccer_root / "SchemeTransitions"],
        trend_dirs=[soccer_root / "StyleTrends"],
        reference_dirs=[
            soccer_root / "Leagues",
            soccer_root / "Seasons",
            soccer_root / "Signals",
            soccer_root / "Scouting",
        ],
        drop_dirs=[
            soccer_root / "Matchups",
            soccer_root / "StyleMatchups",
        ],
    )

    # --------------------------------------------------------------- Tennis --
    tennis_root = v / "Sports" / "Tennis"
    tennis = SportSpec(
        name="Tennis",
        is_solo=True,
        teams_dir=None,
        players_dir=tennis_root / "Players" if (tennis_root / "Players").is_dir() else None,
        team_note_dir=None,
        archetype_dirs=[tennis_root / "Playstyles"],
        scheme_dirs=[],
        trend_dirs=[tennis_root / "StyleTrends"],
        reference_dirs=[
            tennis_root / "Surfaces",
            tennis_root / "Tournaments",
            tennis_root / "Leagues",
            tennis_root / "Seasons",
            tennis_root / "Signals",
            tennis_root / "Scouting",
        ],
        drop_dirs=[
            tennis_root / "Matchups",
            tennis_root / "StyleMatchups",
        ],
    )

    return [nba, mlb, soccer, tennis]
