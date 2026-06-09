"""Per-season minimum-sample floor — the keystone discipline change.

ROADMAP phase: ARCHITECTURE §2 (the keystone — do this FIRST, it retro-protects everything).
GATE to flip flag ON: this module contains PURE FUNCTIONS only; the caller (cross_season.gate_x
and D08 _intake_guard) must call passes_n_min before classing any deliverable beyond RESEARCH.

Design authority: ARCHITECTURE.md §2 + RED_A §A5 "statistical-power blindness in the gate stack."

Rule: below the floor a grain is ``single_season_effective`` → capped at RESEARCH, ineligible for
PROVEN-capable. This makes the honesty class a function of *statistical power*, not label presence.
It must be called by cross_season.gate_x and D08 _intake_guard (P0.1 executor work — NOT yet wired).

All functions are stdlib-only, fully unit-testable without any data files or heavy imports.
No torch / pandas / numpy imported at module load (discipline: import-safe).

Flag: DEFAULT-OFF. This module is additive scaffolding; it does NOT modify any live path.
Nothing is imported by an existing module until P0.1 executor wires it.
"""
from __future__ import annotations

__all__ = [
    "DEFAULT_FLOORS",
    "passes_n_min",
    "classify_power",
    "effective_season_count",
]

# ---------------------------------------------------------------------------
# Default per-season minimum-sample floors (ARCHITECTURE §2, tunable).
# Key = grain name, Value = minimum *per-season* labeled-row count.
#
# player_game: 3,000 labeled player-games/season (RED-A §A5 recommendation).
#   Basis: pregame_oof.parquet is 94% season-blank; the 2025-26 slice is only
#   7,630 rows *before* join shrinkage. Even the smaller half of a real 2-season
#   corpus needs ≥3,000 rows to run cluster_lab cross-season guard meaningfully.
#
# quarter: 5,000 quarter-rows/season (RED-A §A5 recommendation).
#   Basis: quarter_features.parquet is 16:1 imbalanced (26,186 vs 1,613 rows in
#   S1/S2). A 1,613-row second season cannot clear rel<−0.002 without noise help.
#
# sim_lever_games: 82 — one full regular season of graded games per season.
#   Basis: sim levers (foul-state, fatigue, play-type routing) were calibrated on
#   4 NYK/SAS Finals games (RED-A §A3). 82 games is one real regular-season corpus,
#   the smallest substrate where a slope sweep is not fitting noise.
#
# Grains not listed here (e.g. "possession", "prop") have corpora managed by
# cross_season.py and are not subject to this row-count floor gate directly,
# but callers may add entries to a custom floors dict at call time.
# ---------------------------------------------------------------------------
DEFAULT_FLOORS: dict[str, int] = {
    "player_game": 3_000,
    "quarter": 5_000,
    "sim_lever_games": 82,
}


def passes_n_min(
    season_counts: dict[str, int],
    grain: str,
    floors: dict[str, int] | None = None,
) -> tuple[bool, str]:
    """Return (passes, reason) — True iff every season meets the per-season floor.

    Parameters
    ----------
    season_counts:
        Mapping of season-label → labeled row count for that season.
        E.g. ``{"2024-25": 13643, "2025-26": 7630}``.
        Seasons with a blank/empty key are ignored (they represent season-unlabeled rows
        and convey no cross-season signal — consistent with RED-A §0 finding that 94% of
        pregame_oof.parquet carries no season label).
    grain:
        The grain name used to look up the floor, e.g. ``"player_game"``, ``"quarter"``,
        ``"sim_lever_games"``.  Unknown grains (not in floors) return
        ``(True, "no-floor-defined")`` — the caller is responsible for registering floors
        for new grains; defaulting to pass avoids false-blocking new grains before a floor
        is deliberated.
    floors:
        Override or extend DEFAULT_FLOORS. If None, DEFAULT_FLOORS is used.

    Returns
    -------
    tuple[bool, str]
        ``(True,  "passes: min_n=<k> >= floor=<f> across <n> seasons")``
        ``(False, "FAILS: season <s> has <k> rows < floor=<f> [grain=<g>]")``
        ``(True,  "no-floor-defined for grain <g>")``

    Notes
    -----
    - An empty ``season_counts`` dict (no labeled rows at all) is a hard failure when a
      floor is defined: there are zero seasons meeting the floor.
    - Season keys that are empty strings or None are silently skipped (they represent
      the 94%-unlabeled rows in pregame_oof; including them would defeat the guard).

    Example
    -------
    >>> passes_n_min({"2024-25": 13643, "2025-26": 7630}, "player_game")
    (False, 'FAILS: season 2025-26 has 7630 rows < floor=3000 ... wait, 7630 > 3000')
    # Actually 7630 >= 3000 so this passes — the real failure is the 4-game sim case.
    >>> passes_n_min({"2025-26": 4}, "sim_lever_games")
    (False, 'FAILS: season 2025-26 has 4 rows < floor=82 [grain=sim_lever_games]')
    """
    # TODO(P0.1): wire this call into cross_season.gate_x (before the gate_x verdict is
    #             returned) and into D08 _intake_guard (before honesty class is assigned).
    resolved_floors: dict[str, int] = DEFAULT_FLOORS if floors is None else floors

    if grain not in resolved_floors:
        return True, f"no-floor-defined for grain {grain!r}"

    floor = resolved_floors[grain]

    # Filter out blank / None season keys — they represent unlabeled rows and do not
    # constitute independent season evidence.
    labeled: dict[str, int] = {
        k: v for k, v in season_counts.items() if k and k.strip()
    }

    if not labeled:
        return (
            False,
            f"FAILS: no labeled seasons present; floor={floor} [grain={grain!r}]",
        )

    for season, count in sorted(labeled.items()):
        if count < floor:
            return (
                False,
                (
                    f"FAILS: season {season!r} has {count:,} rows "
                    f"< floor={floor:,} [grain={grain!r}]"
                ),
            )

    min_n = min(labeled.values())
    n_seasons = len(labeled)
    return (
        True,
        (
            f"passes: min_n={min_n:,} >= floor={floor:,} "
            f"across {n_seasons} season(s) [grain={grain!r}]"
        ),
    )


def classify_power(
    season_counts: dict[str, int],
    grain: str,
    floors: dict[str, int] | None = None,
) -> str:
    """Classify a grain/corpus as cross_season-eligible or single_season_effective.

    Returns
    -------
    str
        ``"cross_season"``           — passes_n_min AND effective_season_count >= 2.
        ``"single_season_effective"``— either fails the n_min floor OR has < 2 real seasons.

    This classification maps directly to the honesty-class cap in D08 §2.4:
      - ``"cross_season"``           → deliverable *may* reach PROVEN-capable (gated).
      - ``"single_season_effective"``→ deliverable is capped at RESEARCH; flag_allowed_on
                                       may still be True but honesty_class cannot exceed
                                       RESEARCH until a real second season exists.

    Notes
    -----
    Two conditions must BOTH hold to be ``"cross_season"``:
      1. passes_n_min is True (adequate per-season labeled rows).
      2. effective_season_count >= 2 (at least two distinct labeled seasons).
    Season-unlabeled rows (blank key) contribute to neither condition.
    """
    # TODO(P0.1): consumed by cross_season.gate_x dispatch logic and by
    #             D08 validation._intake_guard to gate the honesty ladder.
    ok, _reason = passes_n_min(season_counts, grain, floors)
    if not ok:
        return "single_season_effective"

    if effective_season_count(season_counts) < 2:
        return "single_season_effective"

    return "cross_season"


def effective_season_count(season_counts: dict[str, int]) -> int:
    """Return the number of *labeled* seasons present in the corpus.

    Season keys that are empty strings or whitespace-only are excluded — they represent
    the bulk of pregame_oof.parquet (94% season-blank, RED-A §0) and do NOT constitute
    independent seasons for cross-season validation purposes.

    Parameters
    ----------
    season_counts:
        Mapping of season-label → row count.  Any value is accepted (including 0 — a
        season present in the parquet with zero qualifying rows is still counted; the
        n_min floor in passes_n_min is what rejects inadequate seasons).

    Returns
    -------
    int
        Number of distinct non-blank season keys.

    Examples
    --------
    >>> effective_season_count({"": 335405, "2024-25": 13643, "2025-26": 7630})
    2
    >>> effective_season_count({"2024-25": 26186, "2025-26": 1613})
    2
    >>> effective_season_count({"": 100000, "  ": 50000})
    0
    """
    # TODO(P0.1): used by classify_power and may be called directly by corpus-builder
    #             scripts to PRINT per-season row counts before a cross-season search
    #             (RED-A §A1 recommended fix: "require the corpus builder to PRINT the
    #             per-season labeled-row count and refuse to run a cross-season search
    #             when min(per-season n) < a hard floor").
    return sum(1 for k in season_counts if k and k.strip())
