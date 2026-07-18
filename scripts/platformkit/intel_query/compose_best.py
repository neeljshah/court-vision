"""compose_best(aspect) -> ONE conclusion, all factors weighed, honestly.

Capstone composer: "who is the best <aspect>, all factors weighed, ONE
conclusion" -- built from VERIFIED claims only (via ask.load_verified_claims,
never ad-hoc jsonl parsing), following a DECLARED composition rule emitted
verbatim as composition_rule so the conclusion is auditable:

    1. PRIMARY AXIS: the pre-registered predictive-validity gate verdict
       (read from disk at runtime, never hardcoded) selects which VERIFIED
       ranking claim is primary/canonical; follows the gate if it flips.
    2. ATTRIBUTION AXES annotate the #1 primary-axis player with other
       VERIFIED claims' rank/value for that SAME player -- never override.
    3. HONEST DISAGREEMENT: an attribution axis's own #1 differing from the
       primary axis's #1 is surfaced explicitly, citing why primary wins.

Season awareness (compose_best_season.py): requested_season=None is
byte-identical to old behavior; a window mismatch substitutes a declared
season_fallback VERIFIED claim, or adds an honest mismatch caveat.

Fail-closed: if the primary claim (or the gate verdict file) is missing/not
VERIFIED, returns {"status": "UNANSWERABLE", "missing": [...]} -- never a
guessed name. An unavailable attribution axis does NOT block the conclusion.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.platformkit.intel_query import compose_best_season
from scripts.platformkit.intel_query.ask import (
    REPO_ROOT,
    _ascii_name,
    _claim_evidence,
    _find_by_key,
    load_verified_claims,
    pairs_for_claim_stores,
)

# The ONLY stores this composer reads (bare load_verified_claims() whole-
# loads GB-scale bulk rate stores). Last entry: season_fallback claim below.
_BEST_STORES: tuple[str, ...] = (
    "nba_canonical_shooter_claims.jsonl",
    "nba_quality_claims.jsonl",
    "nba_context_shooting_claims.jsonl",
    "shooter_composite_v2_claims.jsonl",
)

COMPOSITION_RULE = (
    "0. DOMAIN FILTER (if declared for this aspect): the primary ranking pool "
    "is first restricted to entities meeting a pre-declared domain-qualification "
    "minimum cited to an EXTERNAL convention (e.g. the NBA's own official 3P%-title "
    "statistical minimum, season fg3m>=82) -- a domain restriction, never a tuned "
    "threshold; the unfiltered #1 is still reported alongside for transparency. "
    "1. PRIMARY AXIS = the predictive-validity gate's verdict (read live from "
    "verdict_file) decides which VERIFIED ranking claim is canonical/primary; "
    "never hardcoded, follows the gate if it ever flips. "
    "2. ATTRIBUTION AXES annotate the primary axis's #1 player with other "
    "VERIFIED claims' rank/value for that player -- they never override the "
    "primary axis. "
    "3. HONEST DISAGREEMENT: if an attribution axis's own #1 differs from the "
    "primary axis's #1, that is surfaced explicitly with the gate citation "
    "explaining why the primary axis still wins."
)


@dataclass(frozen=True)
class _AttributionAxis:
    axis: str
    claim_id: str
    value_field: str = "value"


@dataclass(frozen=True)
class _DomainFilter:
    """Pre-declared domain restriction on the PRIMARY ranking pool -- e.g.
    an external league's qualification minimum, never a tuned threshold."""
    field: str
    min: float
    source: str


@dataclass(frozen=True)
class _AspectConfig:
    verdict_file: Path
    # gate verdict value -> claim_id of the ranking claim that becomes primary
    verdict_to_primary_claim: dict[str, str]
    attribution_axes: tuple[_AttributionAxis, ...]
    domain_filter: _DomainFilter | None = None
    # season -> VERIFIED claim_id on window mismatch; None -> caveat instead.
    season_fallback: dict[str, str] | None = None


# ponytail: only "shooter" wired v1 (task says no speculative aspects) --
# add a new _AspectConfig entry here when a second aspect is actually asked
# for, do not pre-build a registry for aspects nobody has requested yet.
_ASPECT_CONFIGS: dict[str, _AspectConfig] = {
    "shooter": _AspectConfig(
        verdict_file=REPO_ROOT / "data" / "domains" / "basketball_nba" / "quality_validity_gate_verdict.json",
        verdict_to_primary_claim={
            "REJECT_NAIVE_STAYS_CANONICAL": "nba_canonical_shooter_leaderboard_full_season_2024_25",
            "SHIP_RICHER_INDEX": "nba_shooter_quality_v1_full_season_2024_25",
        },
        attribution_axes=(
            _AttributionAxis("shooter_quality_v1_rank", "nba_shooter_quality_v1_full_season_2024_25"),
            _AttributionAxis("fg3_pct_vs_team_context", "nba_fg3_pct_vs_team_context"),
            _AttributionAxis("fg3a_share_of_team", "nba_fg3a_share_of_team_2024-25"),
            _AttributionAxis("fg3_pct_rest_split", "nba_fg3_pct_rest_split_2024-25"),
        ),
        domain_filter=_DomainFilter(
            field="fg3m", min=82, source="NBA official 3P% qualification minimum (82 3PM)"
        ),
        season_fallback={
            "2025-26": "shooter_composite_v2_asof_approx_full_season_2025_26",
        },
    ),
}


def _load_verdict(verdict_file: Path) -> dict[str, Any] | None:
    """Fail-open per-file, matching ask._load_json's contract: a missing or
    malformed verdict file is treated as unavailable, never crashes."""
    if not verdict_file.exists():
        return None
    try:
        with open(verdict_file, "r", encoding="ascii", errors="strict") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _unanswerable(aspect: str, missing: list[str]) -> dict[str, Any]:
    return {
        "status": "UNANSWERABLE",
        "aspect": aspect,
        "missing": missing,
        "edge_claimed": False,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _apply_domain_filter(
    ranking: list[dict[str, Any]], domain_filter: _DomainFilter
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    """Restrict `ranking` to rows meeting domain_filter before rank-1
    selection. None if the domain field is missing -- caller turns that
    into UNANSWERABLE rather than silently skipping the filter."""
    if not all(domain_filter.field in r for r in ranking):
        return None
    unfiltered_rank1 = min(ranking, key=lambda r: r.get("rank", float("inf")))
    unfiltered_block = {
        "name": _ascii_name(str(unfiltered_rank1.get("player_name", ""))),
        "value": unfiltered_rank1.get("value"),
        "fails_domain": (
            f"{domain_filter.field}={unfiltered_rank1.get(domain_filter.field)} < {domain_filter.min}"
        ),
    }
    filtered = [r for r in ranking if r.get(domain_filter.field, 0) >= domain_filter.min]
    return filtered, unfiltered_block


def compose_best(aspect: str = "shooter", requested_season: str | None = None) -> dict[str, Any]:
    """ONE conclusion for `aspect`, composed per COMPOSITION_RULE (module
    docstring). requested_season=None reproduces old behavior byte-for-byte;
    see compose_best_season.resolve for the substitution-vs-caveat contract."""
    config = _ASPECT_CONFIGS.get(aspect)
    if config is None:
        return _unanswerable(aspect, [f"aspect {aspect!r} has no declared composition config"])

    verdict = _load_verdict(config.verdict_file)
    if verdict is None:
        return _unanswerable(aspect, [f"gate verdict file unavailable: {_display_path(config.verdict_file)}"])

    verdict_value = verdict.get("verdict")
    primary_claim_id = config.verdict_to_primary_claim.get(verdict_value)
    if primary_claim_id is None:
        return _unanswerable(
            aspect,
            [f"gate verdict {verdict_value!r} has no declared primary-claim mapping in verdict_to_primary_claim"],
        )

    verified = load_verified_claims(pairs_for_claim_stores(_BEST_STORES))
    primary_claim = verified.get(primary_claim_id)
    if primary_claim is None:
        return _unanswerable(aspect, [f"primary claim not VERIFIED/available: {primary_claim_id}"])

    season = compose_best_season.resolve(config, verified, primary_claim, primary_claim_id, requested_season)
    primary_claim, primary_claim_id = season.claim, season.claim_id

    ranking = primary_claim.get("ranking", [])
    if not ranking:
        return _unanswerable(aspect, [f"primary claim {primary_claim_id} has an empty ranking"])

    unfiltered_rank1: dict[str, Any] | None = None
    if config.domain_filter is not None and not season.using_fallback:
        applied = _apply_domain_filter(ranking, config.domain_filter)
        if applied is None:
            return _unanswerable(
                aspect,
                [
                    f"domain_filter field {config.domain_filter.field!r} missing from "
                    f"primary claim {primary_claim_id}'s ranking rows"
                ],
            )
        ranking, unfiltered_rank1 = applied
        if not ranking:
            return _unanswerable(
                aspect,
                [f"no rows in {primary_claim_id} survive domain_filter {config.domain_filter.source!r}"],
            )

    rank1 = min(ranking, key=lambda r: r.get("rank", float("inf")))
    conclusion_name = _ascii_name(str(rank1.get("player_name", "")))

    attribution: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    caveats: list[str] = list(primary_claim.get("caveats", []))
    if season.caveat:
        caveats = [season.caveat] + caveats
    provenance: list[dict[str, Any]] = [_claim_evidence(primary_claim)]

    for ax in config.attribution_axes:
        axis_claim = verified.get(ax.claim_id)
        if axis_claim is None:
            attribution.append({"axis": ax.axis, "claim_id": ax.claim_id, "status": "not_verified"})
            continue
        ax_ranking = axis_claim.get("ranking", [])
        row_for_conclusion = _find_by_key(ax_ranking, "player_name", conclusion_name.strip().lower())
        ax_top = min(ax_ranking, key=lambda r: r.get("rank", float("inf"))) if ax_ranking else None
        ax_top_name = _ascii_name(str(ax_top.get("player_name", ""))) if ax_top else None
        entry: dict[str, Any] = {
            "axis": ax.axis,
            "claim_id": ax.claim_id,
            "value_for_conclusion": row_for_conclusion.get(ax.value_field) if row_for_conclusion else None,
            "rank_for_conclusion": row_for_conclusion.get("rank") if row_for_conclusion else None,
            "top_name_if_different": None,
        }
        if row_for_conclusion is None:
            entry["status"] = "not_qualifying"
        if ax_top_name and ax_top_name.strip().lower() != conclusion_name.strip().lower():
            entry["top_name_if_different"] = ax_top_name
            disagreements.append({
                "axis": ax.axis,
                "claim_id": ax.claim_id,
                "top_name": ax_top_name,
                "why_primary_wins": (
                    f"primary axis is selected by gate verdict {verdict_value!r} "
                    f"(see {_display_path(config.verdict_file)}), which this attribution axis "
                    "never overrides -- it is annotation only."
                ),
            })
        attribution.append(entry)
        provenance.append(_claim_evidence(axis_claim))
        caveats.extend(c for c in axis_claim.get("caveats", []) if c not in caveats)

    result: dict[str, Any] = {
        "aspect": aspect,
        "conclusion": conclusion_name,
        "composition_rule": COMPOSITION_RULE,
        "primary": compose_best_season.build_primary_block(
            primary_claim_id, conclusion_name, rank1, verdict_value,
            _display_path(config.verdict_file), requested_season, season.using_fallback,
        ),
        "attribution": attribution,
        "disagreements": disagreements,
        "caveats": caveats,
        "provenance": provenance,
        "edge_claimed": False,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    if unfiltered_rank1 is not None:
        result["unfiltered_rank1"] = unfiltered_rank1
    face_validity = primary_claim.get("face_validity_diagnostic")
    if face_validity is not None:
        result["face_validity_diagnostic"] = face_validity
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="compose ONE all-factors-weighed conclusion for an aspect")
    parser.add_argument("aspect", nargs="?", default="shooter")
    args = parser.parse_args(argv)
    result = compose_best(args.aspect)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") != "UNANSWERABLE" else 1


if __name__ == "__main__":
    sys.exit(main())
