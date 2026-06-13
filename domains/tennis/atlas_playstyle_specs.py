"""domains.tennis.atlas_playstyle_specs — Archetype definitions for tennis playstyle atlas.

Static catalogue of playstyle archetypes with names, slugs, descriptions, and
threshold documentation.  Imported by atlas_playstyles.py.

F5-clean: stdlib only.  No edge/betting language. No individual player names.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# ---------------------------------------------------------------------------
# Thresholds (kept here so notes and logic share the same source of truth)
# ---------------------------------------------------------------------------

MIN_MATCHES: int = 15
MIN_SURFACE_MATCHES: int = 5
HEIGHT_BIG_SERVER: float = 190.0
CLAY_SPECIALIST_DELTA: float = 0.07
GRASS_SPECIALIST_DELTA: float = 0.08
HARD_SPECIALIST_DELTA: float = 0.07
GS_DELTA: float = 0.08
GS_MIN_MATCHES: int = 5
ALL_COURT_MAX_SPREAD: float = 0.10
JOURNEYMAN_WIN_RATE_UPPER: float = 0.40


@dataclass
class ArchetypeSpec:
    """Definition of a single playstyle archetype."""
    name: str
    slug: str
    description: str
    stat_signature: str
    surface_tendency: str
    tags: List[str] = field(default_factory=list)


ARCHETYPES: List[ArchetypeSpec] = [
    ArchetypeSpec(
        name="Clay Court Specialist",
        slug="Clay_Court_Specialist",
        description=(
            "Excels on slow clay surfaces where heavy topspin, physicality, "
            "and baseline consistency are rewarded. Performance dips on faster "
            "hard and grass courts relative to clay."
        ),
        stat_signature=(
            f"clay_win_rate − overall_win_rate ≥ {CLAY_SPECIALIST_DELTA:.0%}; "
            f"≥{MIN_SURFACE_MATCHES} clay matches; "
            "clay_win_rate > hard_win_rate and clay_win_rate > grass_win_rate"
        ),
        surface_tendency="Clay >> Hard ≈ Grass",
        tags=["sport/tennis", "playstyle", "surface/clay"],
    ),
    ArchetypeSpec(
        name="Fast Court Big Server",
        slug="Fast_Court_Big_Server",
        description=(
            "Tall players (190 cm+) whose physical frame and natural serving leverage "
            "translate into outsized performance on faster hard and grass courts where "
            "a dominant first serve is most effective."
        ),
        stat_signature=(
            f"height ≥ {HEIGHT_BIG_SERVER:.0f} cm; "
            f"hard_win_rate − overall_win_rate ≥ {HARD_SPECIALIST_DELTA:.0%} "
            "OR grass_win_rate > clay_win_rate"
        ),
        surface_tendency="Hard ≈ Grass >> Clay",
        tags=["sport/tennis", "playstyle", "surface/hard", "surface/grass"],
    ),
    ArchetypeSpec(
        name="All Court Baseliner",
        slug="All_Court_Baseliner",
        description=(
            "Consistent performers across all three primary surfaces with no "
            "pronounced surface preference. Reliable baseline game translates "
            "regardless of court pace."
        ),
        stat_signature=(
            f"max(hard_wr, clay_wr, grass_wr) − min(hard_wr, clay_wr, grass_wr) "
            f"< {ALL_COURT_MAX_SPREAD:.0%}; ≥{MIN_SURFACE_MATCHES} matches on "
            "each surface; overall win-rate ≥ corpus median"
        ),
        surface_tendency="Hard ≈ Clay ≈ Grass (balanced)",
        tags=["sport/tennis", "playstyle"],
    ),
    ArchetypeSpec(
        name="Left Handed Specialist",
        slug="Left_Handed_Specialist",
        description=(
            "Left-handed players whose serve geometry, slice angles, and "
            "ad-court leverage create structural advantages that persist across "
            "surfaces and opposition types."
        ),
        stat_signature=(
            "hand = 'L'; "
            f"≥{MIN_MATCHES} matches in corpus"
        ),
        surface_tendency="Varies by individual; structural left-hand advantage applies universally",
        tags=["sport/tennis", "playstyle"],
    ),
    ArchetypeSpec(
        name="Grand Slam Performer",
        slug="Grand_Slam_Performer",
        description=(
            "Players whose win-rate in best-of-5 Grand Slam format is "
            "meaningfully higher than in best-of-3 tour events. "
            "Physical conditioning, mental durability, and tactical patience "
            "are decisive over five sets."
        ),
        stat_signature=(
            f"bo5_win_rate − bo3_win_rate ≥ {GS_DELTA:.0%}; "
            f"≥{GS_MIN_MATCHES} best-of-5 matches"
        ),
        surface_tendency="Best-of-5 format advantage transcends surface",
        tags=["sport/tennis", "playstyle", "format/bo5"],
    ),
    ArchetypeSpec(
        name="Hard Court Specialist",
        slug="Hard_Court_Specialist",
        description=(
            "Players who consistently outperform their baseline win-rate on "
            "hard courts. Hard-court dominance may reflect serve power, "
            "flat ball-striking, or tactical adaptability to medium-pace surfaces."
        ),
        stat_signature=(
            f"hard_win_rate − overall_win_rate ≥ {HARD_SPECIALIST_DELTA:.0%}; "
            f"≥{MIN_SURFACE_MATCHES} hard court matches; "
            "hard_win_rate > clay_win_rate"
        ),
        surface_tendency="Hard >> Clay; Grass variable",
        tags=["sport/tennis", "playstyle", "surface/hard"],
    ),
    ArchetypeSpec(
        name="Grass Court Specialist",
        slug="Grass_Court_Specialist",
        description=(
            "Players who thrive on fast grass surfaces where serve-and-volley "
            "tactics, low-bounce adaptation, and net approaches are most effective. "
            "Often underperforms on clay."
        ),
        stat_signature=(
            f"grass_win_rate − overall_win_rate ≥ {GRASS_SPECIALIST_DELTA:.0%}; "
            f"≥{MIN_SURFACE_MATCHES} grass matches; "
            "grass_win_rate > clay_win_rate"
        ),
        surface_tendency="Grass >> Hard ≈ Clay",
        tags=["sport/tennis", "playstyle", "surface/grass"],
    ),
    ArchetypeSpec(
        name="Journeyman",
        slug="Journeyman",
        description=(
            "Tour regulars who compete across all surfaces without a dominant "
            "win-rate. A vital part of the draw, they provide depth and "
            "occasionally produce upsets but rank below the median overall."
        ),
        stat_signature=(
            f"overall_win_rate < {JOURNEYMAN_WIN_RATE_UPPER:.0%}; "
            "active across multiple surfaces; "
            "does not satisfy any specialist threshold"
        ),
        surface_tendency="Broadly distributed; no dominant surface pattern identified",
        tags=["sport/tennis", "playstyle"],
    ),
]
