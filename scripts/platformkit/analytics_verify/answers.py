"""LANE E -- fail-closed resolvers over the analytics-verification layer
(attribution rollup, claim survival, sentinel verification, contradiction
scan). Mirrors resolver_registry.py's envelope contract exactly:
    {status: "ok"|"refused"|"not_supported"|"no_data", category, sport,
     source_artifact, as_of, ...category-specific fields}

Every number returned is read verbatim off the pinned JSON artifact -- never
recomputed here (recomputation is each producer's own job:
scripts/platformkit/analytics_verify/{attribution,regrader,sentinel,
contradiction}.py). Fails closed three ways, in order:
  1. artifact file absent (sibling lane hasn't built it in this clone / a
     fresh clone where data/ is gitignored)               -> status "no_data"
  2. artifact present but not stamped edge_claimed: false, or that field is
     missing entirely                                      -> status "refused"
  3. artifact's as_of/generated_at is unparseable or older than the
     staleness bound (default 48h)                         -> status "refused"

Run: python -m scripts.platformkit.analytics_verify.answers attribution --family player_prop
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

STALENESS_HOURS = 48.0

ARTIFACTS = {
    "attribution": "data/cache/analytics_verify/attribution_rollup.json",
    "claim_survival": "data/cache/analytics_verify/claim_survival.json",
    "verification": "data/cache/analytics_verify/sentinel_report.json",
    "contradictions": "data/cache/analytics_verify/contradiction_report.json",
}


def _parse_dt(raw) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _load(kind: str, category: str, sport: str) -> tuple[dict | None, tuple[dict, str, str] | None]:
    """Returns (failure_envelope, None) if any fail-closed gate trips, else
    (None, (data, as_of_iso, path)) for the caller to build an "ok" envelope
    from."""
    path = ARTIFACTS[kind]
    if not os.path.exists(path):
        return {"status": "no_data", "category": category, "sport": sport, "source_artifact": path,
                "note": "analytics-verify artifact not built in this clone"}, None
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "no_data", "category": category, "sport": sport, "source_artifact": path,
                "note": f"artifact unreadable: {exc}"}, None
    if data.get("edge_claimed", True) is not False:
        return {"status": "refused", "category": category, "sport": sport, "source_artifact": path,
                "note": "artifact missing explicit edge_claimed:false -- refusing per no-edge-claims rule"}, None
    as_of_dt = _parse_dt(data.get("generated_at") or data.get("as_of"))
    if as_of_dt is None:
        return {"status": "refused", "category": category, "sport": sport, "source_artifact": path,
                "note": "artifact missing a parseable as_of/generated_at timestamp"}, None
    age_hours = (datetime.now(timezone.utc) - as_of_dt).total_seconds() / 3600.0
    if age_hours > STALENESS_HOURS:
        return {"status": "refused", "category": category, "sport": sport, "source_artifact": path,
                "as_of": as_of_dt.isoformat(),
                "note": f"artifact is {age_hours:.1f}h old, exceeds the {STALENESS_HOURS:.0f}h staleness bound"}, None
    return None, (data, as_of_dt.isoformat(), path)


def attribution(sport: str = "all", family: str | None = None, card_id: str | None = None) -> dict:
    """analytics.attribution -- per-family/per-card CLV attribution receipt
    from the pinned rollup. Verbatim by_family[family] / by_card[card_id]
    row, never recomputed."""
    fail, ctx = _load("attribution", "analytics_attribution", sport)
    if fail:
        return fail
    data, as_of, path = ctx
    base = {"status": "ok", "category": "analytics_attribution", "sport": sport, "source_artifact": path,
            "as_of": as_of, "honest_note": data.get("honest_note"),
            "link_method_mix": data.get("link_method_mix"), "join_rates": data.get("join_rates")}
    if card_id:
        row = (data.get("by_card") or {}).get(card_id)
        if row is None:
            return {"status": "no_data", "category": "analytics_attribution", "sport": sport,
                    "source_artifact": path, "as_of": as_of, "note": f"no attribution row for card_id={card_id!r}"}
        return {**base, "card_id": card_id, "receipt": row}
    if family:
        row = (data.get("by_family") or {}).get(family)
        if row is None:
            return {"status": "no_data", "category": "analytics_attribution", "sport": sport,
                    "source_artifact": path, "as_of": as_of,
                    "note": f"no attribution row for family={family!r}. "
                            f"Available: {sorted((data.get('by_family') or {}))}"}
        return {**base, "family": family, "receipt": row}
    return {**base, "families": sorted((data.get("by_family") or {})), "cards": sorted((data.get("by_card") or {}))}


def claim_survival(sport: str = "all") -> dict:
    """analytics.claim_survival -- verbatim card-decay scoreboard (DECAYED
    means stop trusting that card)."""
    fail, ctx = _load("claim_survival", "analytics_claim_survival", sport)
    if fail:
        return fail
    data, as_of, path = ctx
    return {"status": "ok", "category": "analytics_claim_survival", "sport": sport, "source_artifact": path,
            "as_of": as_of, "honest_note": data.get("honest_note"),
            "n_cards_total": data.get("n_cards_total"), "n_eligible": data.get("n_eligible"),
            "verdict_counts": data.get("verdict_counts"), "survival": data.get("survival"),
            "decayed_cards": data.get("decayed_cards"), "insufficient_cards": data.get("insufficient_cards")}


def verification(sport: str = "all", stat: str | None = None) -> dict:
    """analytics.verification -- sentinel re-derivation check(s). A
    DISCREPANT verdict means the served stat must not be displayed as-is."""
    fail, ctx = _load("verification", "analytics_verification", sport)
    if fail:
        return fail
    data, as_of, path = ctx
    base = {"status": "ok", "category": "analytics_verification", "sport": sport, "source_artifact": path,
            "as_of": as_of, "honest_note": data.get("honest_note"), "overall": data.get("overall"),
            "n_verified": data.get("n_verified"), "n_discrepant": data.get("n_discrepant"),
            "n_stale": data.get("n_stale"), "n_uncheckable": data.get("n_uncheckable")}
    checks = data.get("checks") or []
    if stat:
        matched = [c for c in checks if c.get("stat") == stat]
        if not matched:
            return {"status": "no_data", "category": "analytics_verification", "sport": sport,
                    "source_artifact": path, "as_of": as_of, "note": f"no sentinel check found for stat={stat!r}"}
        return {**base, "stat": stat, "checks": matched}
    return {**base, "checks": checks}


def contradictions(sport: str = "all", family: str | None = None) -> dict:
    """analytics.contradictions -- verbatim conflict rows from the
    cross-claim consistency scan."""
    fail, ctx = _load("contradictions", "analytics_contradictions", sport)
    if fail:
        return fail
    data, as_of, path = ctx
    base = {"status": "ok", "category": "analytics_contradictions", "sport": sport, "source_artifact": path,
            "as_of": as_of, "honest_note": data.get("honest_note"),
            "families_scanned": data.get("families_scanned"), "n_claims": data.get("n_claims"),
            "by_family_consistency": data.get("by_family_consistency"),
            "n_conflicts_by_kind": data.get("n_conflicts_by_kind")}
    conflicts = data.get("conflicts") or []
    if family:
        return {**base, "family": family, "conflicts": [c for c in conflicts if c.get("family") == family]}
    return {**base, "conflicts": conflicts}


def main(argv=None):
    p = argparse.ArgumentParser(description="Query the analytics-verification resolvers directly.")
    p.add_argument("kind", choices=["attribution", "claim_survival", "verification", "contradictions"])
    p.add_argument("--sport", default="all")
    p.add_argument("--family")
    p.add_argument("--card-id")
    p.add_argument("--stat")
    a = p.parse_args(argv)
    fn = {"attribution": lambda: attribution(a.sport, a.family, a.card_id),
          "claim_survival": lambda: claim_survival(a.sport),
          "verification": lambda: verification(a.sport, a.stat),
          "contradictions": lambda: contradictions(a.sport, a.family)}[a.kind]
    print(json.dumps(fn(), indent=2, default=str))


if __name__ == "__main__":
    main()
