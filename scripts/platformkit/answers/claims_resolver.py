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

import json
from pathlib import Path
from typing import Any

CATEGORY = "verified_claims"
_CLAIMS_DIR_REL = "data/cache/intel_claims/"
# wnba MUST precede nba so "wnba" isn't swallowed by the "nba" substring test.
_SPORT_TOKENS = ("wnba", "tennis", "soccer", "mlb", "nba")
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_predictive_validity(validator_source: str | None) -> dict[str, Any]:
    """Read the SAME on-disk validation JSON validator_verdict was sourced
    from (validator_source is that file's repo-relative display path) and
    pull out its top-level "predictive_validity" key -- the compact summary
    scripts.platformkit.predictive_validity.artifacts.stamp_validation()
    merges in. Fail-open: missing/malformed file or absent key -> {} (never
    breaks the ok envelope; a family with no predictive-validity run yet is
    simply silent on this field)."""
    if not validator_source:
        return {}
    path = Path(validator_source)
    if not path.is_absolute():
        path = _REPO_ROOT / path
    try:
        doc = json.loads(path.read_text(encoding="ascii"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return doc.get("predictive_validity", {}) if isinstance(doc, dict) else {}


def _sport_in_query(low: str) -> str | None:
    for s in _SPORT_TOKENS:
        if s in low:
            return s
    return None


def _norm_row(r: dict[str, Any]) -> dict[str, Any]:
    """One ranking row -> compact excerpt row. Accepts any of the name keys
    used across families (player_name from ask's entity_lookup, entity_name
    from the WNBA/zone families, team from the venue-split families,
    entity_id from NAME-KEYED families like nba_referee_crew_ft where the
    entity_id VALUE is the official's name, not a numeric id) -- the ONLY
    place this normalization lives."""
    name = r.get("player_name") or r.get("entity_name") or r.get("team") or r.get("entity_id")
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
    if resp.get("aspect") and resp.get("conclusion"):
        # Composer shape (one-conclusion answers: aspect/conclusion/
        # provenance) has no 'answerable' key -- without this branch a
        # composed answer was silently dropped to no_data (found live
        # 2026-07-18: 'best shooters this season'). Pass it through with
        # its own receipts; never re-rank it here.
        prov = (resp.get("provenance") or [{}])[0]
        return {
            "status": "ok", "category": CATEGORY, "sport": sport,
            "source_artifact": (prov.get("source_files") or [_CLAIMS_DIR_REL])[0],
            "as_of": prov.get("as_of"),
            "family": resp.get("family"),
            "claim_id": (resp.get("primary") or {}).get("claim_id"),
            "validator_verdict": prov.get("validator_verdict", "VERIFIED"),
            "conclusion": resp.get("conclusion"),
            "composition_rule": resp.get("composition_rule"),
            "attribution": resp.get("attribution"),
            "caveats": resp.get("caveats", []),
            "edge_claimed": False,
        }
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
        "predictive_validity": _load_predictive_validity(ev0.get("validator_source")),
        "ranking_excerpt": _excerpt(answer, query),
        "caveats": answer.get("caveats", []),
        "evidence": evidence,
    }


# FAMILY-LEVEL fallback (2026-07-19): a question that names a known family's
# vocabulary (today: referee/official) but whose NL phrasing ask() can't map
# to one specific metric ("which referee crews inflate free throws", "top
# officials by fta per game officiated") must not just fall to no_data --
# it should list that ONE family's VERIFIED ranking claims directly. Keyed
# off resolver_registry's OWN referee regex (imported lazily below to avoid
# the claims_resolver<->resolver_registry import cycle -- resolver_registry
# imports this module at top level) so the two never drift on what counts
# as a "referee question". Generalizes only as far as today's name-keyed
# stores go (referees); a new name-keyed family needs one more entry here,
# not a new mechanism.
def _referee_route() -> tuple[Any, str]:
    from scripts.platformkit.answers.resolver_registry import _REFEREE_RE
    return _REFEREE_RE, "nba_referee_crew_ft_claims"


_FAMILY_ROUTES = (_referee_route,)


def _family_top_claims(family_stem: str, query: str, sport: str, top: int = 5) -> dict[str, Any]:
    """ONE named family's VERIFIED ranking claims (top rows per metric), for
    when a family-level question can't be narrowed to one metric/entity.
    Scoped load via pairs_for_claim_stores -- never a corpus-wide scan, same
    discipline every other composer in this module already follows."""
    from scripts.platformkit.intel_query.ask import (
        CLAIM_SOURCE_PAIRS, load_verified_claims, pairs_for_claim_stores)

    pairs = pairs_for_claim_stores((f"{family_stem}.jsonl",), CLAIM_SOURCE_PAIRS)
    if not pairs:
        return {"status": "no_data", "category": CATEGORY, "sport": sport,
                "source_artifact": _CLAIMS_DIR_REL,
                "note": f"no claim store found for family {family_stem!r}"}
    verified = load_verified_claims(pairs)
    ranking_claims = [r for r in verified.values() if r.get("kind") == "ranking"]
    if not ranking_claims:
        return {"status": "no_data", "category": CATEGORY, "sport": sport,
                "source_artifact": _CLAIMS_DIR_REL,
                "note": f"no VERIFIED ranking claims in family {family_stem!r}"}
    ranking_claims.sort(key=lambda r: str(r.get("claim_id", "")))
    claims_out = [
        {
            "claim_id": row["claim_id"],
            "metric": row.get("criteria", {}).get("metric"),
            "window": row.get("criteria", {}).get("window"),
            "top": [_norm_row(r) for r in row.get("ranking", [])[:top]],
        }
        for row in ranking_claims
    ]
    return {
        "status": "ok", "category": CATEGORY, "sport": sport,
        "source_artifact": ranking_claims[0].get("_producer_source", _CLAIMS_DIR_REL),
        "family": family_stem,
        "note": "family-level answer: the question named this family but no single "
                "metric/entity was resolved, so every VERIFIED ranking claim in it "
                "is returned",
        "claims": claims_out,
        "evidence": [_claim_evidence(r) for r in ranking_claims],
    }


def _claim_evidence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": row["claim_id"], "validator_verdict": "VERIFIED",
        "validator_source": row.get("_validator_source"),
        "producer_source": row.get("_producer_source"), "as_of": row.get("computed_at"),
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
            "predictive_validity": summary.get("predictive_validity", {}),
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


_SPORT_PREFIXES = {"nba", "mlb", "wnba", "tennis", "soccer", "npb", "kbo",
                   "baseball", "basketball"}
_SPORT_SYNONYMS = {"nba": {"nba", "basketball"}, "mlb": {"mlb", "baseball"},
                   "wnba": {"wnba"}}


def _env_matches_sport(env: dict[str, Any], sport: str) -> bool:
    """True when the answering store's name prefix matches the requested
    sport, or the store is cross-sport (no sport prefix at all)."""
    src = str(env.get("source_artifact") or env.get("family") or "")
    base = src.replace("\\", "/").rsplit("/", 1)[-1]
    prefix = base.split("_", 1)[0].lower()
    if prefix not in _SPORT_PREFIXES:
        return True  # cross-sport family (kalshi_, market_, line_, ...)
    return prefix in _SPORT_SYNONYMS.get(sport, {sport})


def resolve(query: str, sport: str = "nba", **kwargs) -> dict[str, Any]:
    """Single entrypoint for the verified_claims category. A family-discovery
    question routes to list_claim_families (sport parsed from the query, else
    all); everything else wraps ask()."""
    low = (query or "").lower()
    if kwargs.get("list_families") or "famil" in low or ("list" in low and "claim" in low):
        return list_claim_families(_sport_in_query(low))
    wrapped = _wrap_ask(query, sport)
    if wrapped.get("status") == "ok" and not _env_matches_sport(wrapped, sport):
        # sport guard (2026-07-18): ask() scans every family, so
        # sport='mlb' + 'top 5 assist leaders' answered with the NBA
        # store. A wrong-sport answer is worse than an honest miss.
        wrapped = {"status": "no_data", "category": CATEGORY, "sport": sport,
                   "source_artifact": _CLAIMS_DIR_REL,
                   "note": f"only a different sport's claim store matches this "
                           f"question (asked sport={sport!r})"}
    if wrapped.get("status") == "no_data":
        for route in _FAMILY_ROUTES:
            pattern, family_stem = route()
            if pattern.search(low):
                fallback = _family_top_claims(family_stem, query, sport)
                if fallback.get("status") == "ok":
                    return fallback
                break  # a matched route with nothing to show stays no_data (honest)
    return wrapped
