"""compose_scout(sport, player) -> a multi-axis descriptive scouting VECTOR.

A scouting report is a VECTOR of independent axes, never one collapsed score
(the platform's one-conclusion rule). This composer assembles, for one player:

  * concept_axes  -- one entry per concept DECLARED in the sport's
    domains/<sport>/concepts/concept_registry.py, each carrying the player's
    composite rating, a league percentile derived from that concept's own
    ranking, the confidence tier, and a source citation. Ratings come from
    contracts.answer_superlative (the ONE weight formula lives there); this
    module never re-derives weights.
  * shooting_facet -- the multi-axis shooter trait vector from
    compose_profile (NBA claim-based; not_applicable for other sports).
  * raw_attributes -- the player's top-N raw attribute percentiles straight
    off the profiles parquet (descriptive, per-attribute).

Fail-closed (mirrors analytics_verify/answers.py's envelope + ask.py's
UNANSWERABLE): a sport with no wired concept registry -> no_data; a player
who resolves on NO axis (no concept, no shooting facet, no raw attribute) ->
no_data with answerable:false naming the miss. Every number is read from a
source artifact (profiles parquet / VERIFIED claims), never fabricated.

Output shape is a standard resolver envelope (category "scouting_report") so
the future matchup composer and the Lane G resolver registry can consume it.

CLI:
    python -m scripts.platformkit.intel_query.compose_scout "LeBron James" --sport nba
    python -m scripts.platformkit.intel_query.compose_scout "Aaron Judge" --sport mlb
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from scripts.platformkit.answers import contracts
from scripts.platformkit.answers.registry_loader import (
    CONCEPT_REGISTRY_MODULE,
    get_registry,
)
from scripts.platformkit.intel_query.compose_profile import (
    compose_profile,
    percentile_from_rank,
)
from scripts.platformkit.profiles import ask as _profiles

CATEGORY = "scouting_report"
# ponytail: answer_superlative reloads the profiles parquet once per concept
# (~8 loads of a 100k-row frame); fine for a per-player CLI dossier. Upgrade
# to a shared-df API only if this ever runs in a hot serving path.
_SUPERLATIVE_TOP_N = 100_000  # effectively "the whole ranked league"


def _profiles_path(sport: str, kind: str) -> str:
    return os.path.join(_profiles.PROFILES_DIR, f"{sport}_{kind}_profiles.parquet")


def _as_of(path: str) -> str | None:
    """Parquet mtime as a TZ-aware UTC ISO string -- the honest freshness of
    the descriptive snapshot. None if the file is absent."""
    if not os.path.exists(path):
        return None
    return datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat()


def _resolve_entity(df, player: str) -> tuple[str, Any]:
    """(status, payload) -- reuses profiles.ask's fuzzy resolver, never
    guesses. status is one of:
      "no_entity"  -> payload None (zero hits)
      "ambiguous"  -> payload [candidate entity_name, ...] (2+ DISTINCT ids)
      "ok"         -> payload (entity_id, entity_name)
    Candidates are grouped by entity_id, not raw entity_name: the profiles
    parquet can carry two different entity_name spellings for the SAME id
    (e.g. nba_player_profiles.parquet has both "Luka Doncic" and an accented
    spelling for entity_id 1629029 -- an upstream builder data bug, see
    docs/research/resolver_coverage_2026_07_17.md gap 2). Grouping by id is
    the resolver-side fix so a dup-spelling row never inflates a real 2-way
    tie into a false 3-way one."""
    if df.empty:
        return "no_entity", None
    _best, hits = _profiles._match_entities(df, _profiles._norm(player).split())
    if not hits:
        return "no_entity", None
    by_eid: dict[Any, str] = {}
    for eid, ename, _sp in hits:
        by_eid.setdefault(eid, ename)
    if len(by_eid) != 1:
        return "ambiguous", list(by_eid.values())
    (eid, ename), = by_eid.items()
    return "ok", (eid, ename)


def _concept_axis(sport: str, kind: str, concept: str, entity_id: Any,
                  reg_module: str, source_artifact: str) -> dict[str, Any]:
    """One concept axis for the player: rating + league percentile + citation,
    all from that concept's own answer_superlative ranking. A player below the
    concept's min-n floor is honestly reported not_in_pool (never guessed)."""
    result = contracts.answer_superlative(concept, sport, kind=kind, top_n=_SUPERLATIVE_TOP_N)
    ordered = list(result.get("top", [])) + list(result.get("runners_up", []))
    pool_n = len(ordered)
    hit_idx = next((i for i, e in enumerate(ordered, start=1)
                    if e.get("entity_id") == entity_id), None)
    citation = {"concept_registry": reg_module, "signals": [s.get("attribute") for s in
                                                            get_registry(sport).get_concept(concept)["signals"]],
                "source_artifact": source_artifact}
    if hit_idx is None:
        return {"axis": concept, "status": "not_in_pool", "pool_n": pool_n,
                "note": "player absent from this concept's ranking (below its min-n floor or no signals)",
                "citation": citation}
    entry = ordered[hit_idx - 1]
    return {
        "axis": concept, "status": "ok",
        "rating": entry.get("composite"),
        "rating_scale": "weighted-percentile composite in [0,100] (higher = stronger on this concept)",
        "percentile": percentile_from_rank(hit_idx, pool_n),
        "rank": hit_idx, "pool_n": pool_n, "n": entry.get("n"),
        "confidence": entry.get("confidence"), "status_mix": entry.get("status_mix"),
        "citation": citation,
    }


_MLB_INJURY_RECENCY_CLAIM_ID = "mlb_injury_recency_days_since_latest"
_MLB_INJURY_RECENCY_STORE = ("mlb_injury_recency_claims.jsonl",)


def _injury_facts_block(sport: str, player: str) -> dict[str, Any]:
    """Latest injury-status rows for this player via edge_facts_resolver's
    fail-closed, 7d-staleness-gated injury_report. Lazy-imported + exception-
    wrapped: a missing/broken injury store (soccer/tennis have none) must
    never break the rest of the dossier."""
    try:
        from scripts.platformkit.answers.edge_facts_resolver import injury_report
        return injury_report(sport, player=player)
    except Exception as exc:  # noqa: BLE001 -- fail-closed, never kill the dossier
        return {"status": "no_data", "category": "edge_facts_injury_report", "sport": sport,
                "note": f"injury_report lookup raised {exc.__class__.__name__}: {exc}"}


def _mlb_injury_recency_block(entity_id: Any) -> dict[str, Any]:
    """MLB-only: this player's rank/value in the VERIFIED
    mlb_injury_recency_claims ranking (days_since_latest), read via the same
    load_verified_claims/pairs_for_claim_stores path compose_matchup uses --
    never a bare load_verified_claims() (whole-store loads OOM on GB stores).
    subject_id in that claim keys on ESPN athlete id while profiles.entity_id
    is MLBAM id (no crosswalk wired) -- a player is honestly reported
    not_in_ranking rather than guessed when the ids don't line up."""
    category = "mlb_injury_recency_claim"
    try:
        from scripts.platformkit.intel_query.ask import load_verified_claims, pairs_for_claim_stores
        verified = load_verified_claims(pairs_for_claim_stores(_MLB_INJURY_RECENCY_STORE))
    except Exception as exc:  # noqa: BLE001 -- fail-closed, never kill the dossier
        return {"status": "no_data", "category": category,
                "note": f"claims lookup raised {exc.__class__.__name__}: {exc}"}
    row = verified.get(_MLB_INJURY_RECENCY_CLAIM_ID)
    if row is None:
        return {"status": "no_data", "category": category,
                "note": f"no VERIFIED claim {_MLB_INJURY_RECENCY_CLAIM_ID!r} currently available"}
    citation = {"claim_id": row["claim_id"], "as_of": row.get("computed_at"),
                "source_artifact": row.get("_producer_source")}
    hit = next((r for r in row.get("ranking", []) if r.get("subject_id") == str(entity_id)), None)
    if hit is None:
        return {"status": "not_in_ranking", "category": category, "citation": citation,
                "note": "player's profile entity_id not found in this claim's subject_id ranking "
                        "(id-space mismatch or genuinely absent from the injury-fact corpus)"}
    return {"status": "ok", "category": category, "citation": citation,
            "rank": hit["rank"], "days_since_latest": hit["value"], "n_facts": hit["n"]}


def _injury_context(sport: str, player: str, entity_id: Any | None) -> dict[str, Any]:
    """Optional injury block: per-sub-block fail-closed, mirrors
    compose_matchup's pattern -- absent data marks that sub-block absent
    with a reason, never kills the dossier."""
    block: dict[str, Any] = {"injury_facts": _injury_facts_block(sport, player)}
    if sport != "mlb":
        block["mlb_injury_recency"] = {
            "status": "not_applicable", "category": "mlb_injury_recency_claim",
            "note": "recency-claim ranking is MLB-only"}
    elif entity_id is None:
        block["mlb_injury_recency"] = {
            "status": "no_data", "category": "mlb_injury_recency_claim",
            "note": "player not resolved to a profiles entity_id"}
    else:
        block["mlb_injury_recency"] = _mlb_injury_recency_block(entity_id)
    return block


def _top_raw_attrs(df, entity_id: Any, top_n: int, source_artifact: str) -> dict[str, Any]:
    """Player's top-N raw attribute percentiles (latest window per attribute),
    read verbatim off the profiles parquet -- descriptive, never combined."""
    sub = df[df["entity_id"] == entity_id]
    if sub.empty:
        return {"status": "no_data", "note": "no profile rows for this entity"}
    latest = sub.sort_values("window").groupby("attribute", as_index=False).tail(1)
    top = latest.sort_values("percentile", ascending=False).head(top_n)
    attrs = [
        {"attribute": r["attribute"], "percentile": round(float(r["percentile"]), 1),
         "raw_value": r["raw_value"], "n": r.get("n"), "status": r["status"]}
        for _, r in top.iterrows()
    ]
    return {"status": "ok", "top_n": top_n, "attributes": attrs, "source_artifact": source_artifact}


def compose_scout(sport: str, player: str, kind: str = "player", top_n: int = 8) -> dict[str, Any]:
    """Multi-axis descriptive scouting dossier vector for `player` -- see the
    module docstring for the contract. Standard resolver envelope."""
    player = _profiles._ascii(player)
    # Sport must have a wired concept registry (fail-closed: else no_data).
    if sport not in CONCEPT_REGISTRY_MODULE:
        return {"status": "no_data", "category": CATEGORY, "sport": sport, "player": player,
                "answerable": False,
                "note": f"no concept registry wired for sport '{sport}'. "
                        f"Available: {sorted(CONCEPT_REGISTRY_MODULE)}"}
    reg_module = CONCEPT_REGISTRY_MODULE[sport]
    reg = get_registry(sport)
    source_artifact = _profiles_path(sport, kind)
    as_of = _as_of(source_artifact)

    df = _profiles.load_profiles(sport)
    if not df.empty:
        df = df[df["kind"] == kind].reset_index(drop=True)
    resolve_status, resolved = _resolve_entity(df, player)

    if resolve_status == "ambiguous":
        return {"status": "ambiguous", "category": CATEGORY, "sport": sport, "player": player,
                "source_artifact": source_artifact, "as_of": as_of, "answerable": False,
                "candidates": resolved,
                "note": f"{len(resolved)} distinct players match this name -- narrow your query",
                "edge_claimed": False}

    concept_axes: list[dict[str, Any]] = []
    raw_attributes: dict[str, Any] = {"status": "no_data", "note": "player not resolved in profiles"}
    entity_name = player
    entity_id: Any | None = None
    if resolve_status == "ok":
        entity_id, entity_name = resolved
        for concept in reg.list_concepts():
            concept_axes.append(_concept_axis(sport, kind, concept, entity_id, reg_module, source_artifact))
        raw_attributes = _top_raw_attrs(df, entity_id, top_n, source_artifact)

    # Shooting facet is NBA claim-based (compose_profile); not_applicable else.
    shooting = compose_profile(player)
    shooting_ok = shooting.get("status") == "OK"
    shooting_facet: dict[str, Any] = shooting if shooting_ok else {
        "status": "not_applicable" if sport != "nba" else shooting.get("status", "UNANSWERABLE"),
        "note": ("shooter trait facet is NBA claim-based; not applicable to this sport"
                 if sport != "nba" else "no VERIFIED shooter-profile axis for this player"),
        "detail": shooting.get("missing") or shooting.get("status"),
    }

    concept_hits = [a for a in concept_axes if a.get("status") == "ok"]
    raw_hit = raw_attributes.get("status") == "ok"
    # UNANSWERABLE: resolved on NO axis at all (mirror ask.py's pattern) ->
    # fail-closed no_data naming exactly what was checked and missed.
    if not concept_hits and not shooting_ok and not raw_hit:
        return {"status": "no_data", "category": CATEGORY, "sport": sport, "player": entity_name,
                "source_artifact": source_artifact, "as_of": as_of, "answerable": False,
                "missing": [
                    f"player found on NO scouting axis: 0/{len(reg.list_concepts())} concept ratings, "
                    "no VERIFIED shooter-profile facet, no raw attribute rows "
                    "(name mismatch, or below every floor)"],
                "edge_claimed": False}

    return {
        "status": "ok", "category": CATEGORY, "sport": sport, "kind": kind,
        "player": entity_name, "source_artifact": source_artifact, "as_of": as_of,
        "answerable": True,
        "concept_axes": concept_axes,
        "shooting_facet": shooting_facet,
        "raw_attributes": raw_attributes,
        "injury_context": _injury_context(sport, entity_name, entity_id),
        "axes_hit": {"concepts": len(concept_hits), "concepts_total": len(reg.list_concepts()),
                     "shooting_facet": shooting_ok, "raw_attributes": raw_hit},
        "note": ("DESCRIPTIVE multi-axis scouting vector -- each axis reported with its own rating, "
                 "percentile, and citation; axes are NEVER combined into one score. No forecast/$ claim. "
                 "source_artifact is a season-snapshot profile (no live-freshness SLA); as_of is its mtime."),
        "edge_claimed": False,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="multi-axis descriptive scouting dossier vector")
    parser.add_argument("player")
    parser.add_argument("--sport", default="nba")
    parser.add_argument("--kind", default="player")
    parser.add_argument("--top-n", type=int, default=8, help="top-N raw attribute percentiles")
    args = parser.parse_args(argv)
    result = compose_scout(args.sport, args.player, kind=args.kind, top_n=args.top_n)
    print(_profiles._ascii(json.dumps(result, indent=2, default=str)))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
