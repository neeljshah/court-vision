"""atlas_card resolver -- fail-closed entity lookup across the built atlas
manifests (scripts/platformkit/analytics_showcase/out/atlas_*_manifest.json,
written by nba_player_atlas.py / nba_team_atlas.py / ... via atlas_factory.
write_manifest -- see that module for the shared {entity, card_path,
key_numbers, floors, as_of} entry shape every atlas builder writes).

Query shapes: "card for <entity>" / "show <entity> atlas". Matches the
`entity` field verbatim after name-normalization (accents/case/whitespace
stripped) -- ponytail: literal entity-field match only, never fuzzy-invents
against key_numbers or an aliased team name (e.g. "Hawks" -> "ATL" team-name
resolution is a possible upgrade, add if a real query needs it). An entity
absent from every manifest is an honest no_data; a normalized name shared by
2+ manifest entries is ambiguous (name the sport via sport_filter=, never
guessed).

This is ONE registered resolver (category "atlas_card") inside
scripts/platformkit/answers/resolver_registry.py -- route a category-agnostic
question through resolver_registry.resolve(), not here directly, unless you
already know it names an atlas card.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

CATEGORY = "atlas_card"
_REPO = Path(__file__).resolve().parents[3]
_OUT_DIR_REL = "scripts/platformkit/analytics_showcase/out"

CARD_FOR_RE = re.compile(
    r"^\s*(?:show\s+(?:me\s+)?(?:the\s+)?)?(?:atlas\s+)?card\s+(?:for|of)\s+(.+?)\s*\??\s*$", re.I)
SHOW_ATLAS_RE = re.compile(
    r"^\s*show\s+(?:me\s+)?(?:the\s+)?(.+?)\s+atlas(?:\s+card)?\s*\??\s*$", re.I)


def is_atlas_card_query(text: str) -> bool:
    return bool(CARD_FOR_RE.match(text) or SHOW_ATLAS_RE.match(text))


def parse_entity(text: str) -> str | None:
    """"card for Nikola Jokic" / "show Nikola Jokic atlas" -> "Nikola Jokic".
    None if `text` isn't either shape."""
    m = CARD_FOR_RE.match(text) or SHOW_ATLAS_RE.match(text)
    if not m:
        return None
    entity = m.group(1).strip().strip("?").strip()
    entity = re.sub(r"^the\s+", "", entity, flags=re.I)
    return entity or None


def _norm(s) -> str:
    s = str(s or "").lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _manifest_paths() -> list[Path]:
    out_dir = _REPO / _OUT_DIR_REL
    return sorted(out_dir.glob("atlas_*_manifest.json")) if out_dir.is_dir() else []


def _iter_entries():
    """(manifest_path_rel, manifest_sport, entry) for every entry in every
    built manifest -- fresh read every call (manifests are rebuilt
    out-of-process by each atlas_*.py builder), never cached here."""
    for path in _manifest_paths():
        try:
            manifest = json.loads(path.read_text(encoding="ascii"))
        except (json.JSONDecodeError, OSError):
            continue
        rel = str(path.relative_to(_REPO)).replace("\\", "/")
        for entry in manifest.get("entries", []):
            yield rel, manifest.get("sport"), entry


def resolve(entity: str, sport_filter: str | None = None) -> dict:
    """Name-normalized `entity` lookup across every built atlas manifest.
    sport_filter is opt-in only (never the caller's default sport, which
    would silently drop a real cross-sport match) -- narrows an ambiguous
    hit to one manifest's sport tag. status: no_data (no manifests built, or
    zero matches) | ambiguous (2+ distinct manifest entries share the
    normalized name) | ok."""
    if not _manifest_paths():
        return {"status": "no_data", "category": CATEGORY, "source_artifact": _OUT_DIR_REL,
                "note": "no atlas manifests built in this clone -- run an atlas_*.py builder first"}
    q = _norm(entity)
    if not q:
        return {"status": "no_data", "category": CATEGORY, "source_artifact": _OUT_DIR_REL,
                "note": "empty entity"}
    hits = [(rel, sp, e) for rel, sp, e in _iter_entries() if _norm(e.get("entity", "")) == q]
    if sport_filter:
        hits = [h for h in hits if h[1] == sport_filter]
    uniq = list({(rel, e.get("entity")): (rel, sp, e) for rel, sp, e in hits}.values())
    if not uniq:
        return {"status": "no_data", "category": CATEGORY, "source_artifact": _OUT_DIR_REL,
                "note": f"no atlas card matched entity '{entity}' -- refusing, not guessing"}
    if len(uniq) > 1:
        return {"status": "ambiguous", "category": CATEGORY, "source_artifact": _OUT_DIR_REL,
                "note": f"'{entity}' matched {len(uniq)} atlas cards -- narrow with sport_filter=",
                "candidates": [{"entity": e.get("entity"), "manifest": rel, "sport": sp} for rel, sp, e in uniq]}
    rel, sport, e = uniq[0]
    return {"status": "ok", "category": CATEGORY, "sport": sport, "source_artifact": rel,
            "as_of": e.get("as_of"), "entity": e.get("entity"), "card_path": e.get("card_path"),
            "key_numbers": e.get("key_numbers"), "floors": e.get("floors"),
            "descriptive_only": True, "edge_claimed": False}
