"""verified_claims resolver -- the BRIDGE that makes every auto-discovered
VERIFIED claim family reachable through resolver_registry.resolve() (and thus
the MCP server + qa_runner, both resolve()-based), not only through
intel_query.ask.ask() directly.

This is a THIN adapter. It does NOT re-implement the answer engine: it
lazy-imports scripts.platformkit.intel_query.ask.ask() -- the already
fail-closed, index-fast-path, auto-discovering (filename-pairing) engine over
data/cache/intel_claims/*.jsonl -- and reshapes its response into the ONE
standard envelope every other resolver returns:

    {status, category, sport, source_artifact, as_of, ...}

Two capabilities, same category:
  * evidence/provenance ("show the evidence for <claim_id>", "how do you
    know") -> wrap ask(), surface claim_id + ranking excerpt (top 5 + the
    asked entity if named) + caveats + validator verdict as receipts.
  * discovery ("what claim families exist for <sport>?") -> list_claim_families
    reads each store's cheap validation summary (n_claims / n_verified) so a
    cold AI can see what families exist without a full claim load.

Key-mismatch note: WNBA claim families key ranking rows by `entity_name`; ask's
entity_lookup keys them `player_name`. _norm_row accepts BOTH here at the
adapter layer -- never patched into ask.py (behavior-preserving for every
existing caller).
"""
from __future__ import annotations

from typing import Any

CATEGORY = "verified_claims"
_CLAIMS_DIR_REL = "data/cache/intel_claims/"
# wnba MUST precede nba so "wnba" isn't swallowed by the "nba" substring test.
_SPORT_TOKENS = ("wnba", "tennis", "soccer", "mlb", "nba")


def _sport_in_query(low: str) -> str | None:
    for s in _SPORT_TOKENS:
        if s in low:
            return s
    return None


def _norm_row(r: dict[str, Any]) -> dict[str, Any]:
    """One ranking row -> compact excerpt row. Accepts any of the name keys
    used across families (player_name from ask's entity_lookup, entity_name
    from the WNBA/zone families, team from the venue-split families) -- the
    ONLY place this normalization lives."""
    name = r.get("player_name") or r.get("entity_name") or r.get("team")
    return {"rank": r.get("rank"), "name": name, "value": r.get("value"), "n": r.get("n")}


def _excerpt(answer: dict[str, Any], query: str, top: int = 5) -> list[dict[str, Any]]:
    """Top-`top` ranking rows if ask's answer carries a ranking (top_n family),
    plus the asked entity's row if the query names one that fell below `top`.
    Provenance answers carry no ranking -> honestly empty."""
    rows = answer.get("ranking")
    if not rows:
        return []
    out = [_norm_row(r) for r in rows[:top]]
    low = query.lower()
    seen = {r["name"] for r in out}
    for r in rows[top:]:
        name = r.get("player_name") or r.get("entity_name") or ""
        if name and name.lower() in low and name not in seen:
            out.append(_norm_row(r))
            break
    return out


def _wrap_ask(query: str, sport: str) -> dict[str, Any]:
    """Call ask() (lazy import) and reshape its response into the standard
    envelope. answerable:False -> fail-closed no_data (never a guess)."""
    from scripts.platformkit.intel_query.ask import ask  # lazy: keeps resolver import light

    resp = ask(query)
    if not resp.get("answerable"):
        return {
            "status": "no_data", "category": CATEGORY, "sport": sport,
            "source_artifact": _CLAIMS_DIR_REL,
            "note": resp.get("reason", "no VERIFIED claim covers this question"),
            "nearest_supported_families": resp.get("nearest_supported_families", []),
        }
    answer = resp.get("answer") or {}
    evidence = resp.get("evidence") or []
    ev0 = evidence[0] if evidence else {}
    claim_id = answer.get("claim_id") or ev0.get("claim_id")
    return {
        "status": "ok", "category": CATEGORY, "sport": sport,
        "source_artifact": ev0.get("producer_source", _CLAIMS_DIR_REL),
        "as_of": ev0.get("as_of"),
        "family": resp.get("family"),
        "claim_id": claim_id,
        "validator_verdict": ev0.get("validator_verdict", "VERIFIED"),
        "validator_source": ev0.get("validator_source"),
        "ranking_excerpt": _excerpt(answer, query),
        "caveats": answer.get("caveats", []),
        "evidence": evidence,
    }


def list_claim_families(sport: str | None = None) -> dict[str, Any]:
    """Discovery: every (validation, claims) pair ask() auto-discovered, with
    each store's cheap validation summary (n_claims / n_verified). Reads only
    the small *_validation.json per store, never the (GB-scale) claims JSONL.
    `sport` (substring) filters the family name; None -> all families."""
    from scripts.platformkit.intel_query import ask as _ask_mod  # lazy: CLAIM_SOURCE_PAIRS + _load_json

    fams: list[dict[str, Any]] = []
    newest: str | None = None
    for validation_path, claims_path in _ask_mod.CLAIM_SOURCE_PAIRS:
        stem = claims_path.stem
        if sport and sport.lower() not in stem.lower():
            continue
        summary = _ask_mod._load_json(validation_path) or {}
        fams.append({
            "family": stem,
            "n_claims": summary.get("n_claims"),
            "n_verified": summary.get("n_verified"),
            "edge_claimed": summary.get("edge_claimed", False),
        })
        gen = summary.get("generated_at")
        if gen and (newest is None or gen > newest):
            newest = gen
    if not fams:
        return {"status": "no_data", "category": CATEGORY, "sport": sport or "all",
                "source_artifact": _CLAIMS_DIR_REL,
                "note": f"no claim families found for sport filter {sport!r}"}
    fams.sort(key=lambda f: f["family"])
    return {"status": "ok", "category": CATEGORY, "sport": sport or "all",
            "source_artifact": _CLAIMS_DIR_REL, "as_of": newest,
            "n_families": len(fams), "families": fams}


def resolve(query: str, sport: str = "nba", **kwargs) -> dict[str, Any]:
    """Single entrypoint for the verified_claims category. A family-discovery
    question routes to list_claim_families (sport parsed from the query, else
    all); everything else wraps ask()."""
    low = (query or "").lower()
    if kwargs.get("list_families") or "famil" in low or ("list" in low and "claim" in low):
        return list_claim_families(_sport_in_query(low))
    return _wrap_ask(query, sport)
