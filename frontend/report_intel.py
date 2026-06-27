"""frontend.report_intel -- READ-ONLY descriptive scouting blurbs for a matchup.

intel_blurbs(sport, home, away, *, base=None) -> dict assembles DESCRIPTIVE notes
(archetypes / tendencies / strengths-weaknesses) for both teams and the matchup
from the on-disk persistent-profile artifacts under
``data/cache/profiles/teams/<TRICODE>{,_dossier}.json``.

HONESTY (binding): every note here is DESCRIPTIVE scouting -- an archetype, a
ranked strength, a scheme tag. It is NEVER an edge / $ / ROI / "bet this" claim.
A miss (sport not NBA, no profile on disk, name unresolvable, malformed JSON)
nulls that piece -- this function NEVER raises.

Shape returned::

    {"home": {tricode, label, archetype, scheme, strengths[], weaknesses[],
              source} | None,
     "away": {...} | None,
     "matchup": {note, edge_claim:false} | None,
     "status": "ok" | "unavailable",
     "note": "<str>"}

Only NBA has profile artifacts today; other sports degrade to status
"unavailable" with all-null team blurbs (honest, never fabricated).

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; READ-ONLY; no $.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# __file__ = frontend/report_intel.py -> parents[1] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_PROFILES_DIR = _REPO_ROOT / "data" / "cache" / "profiles" / "teams"

# NBA full-name nickname token -> tricode. Mirrors team_resolver's authoritative
# 30-team table (re-used, not re-derived) so a full name resolves to the same
# tricode the profile files are keyed by. Best-effort, descriptive-only.
try:  # team_resolver lives in the safe platformkit tree (no gated src import).
    from scripts.platformkit.odds_provider.team_resolver import (
        _NBA_CODE_TO_NICK as _CODE_TO_NICK,
        _norm as _norm_name,
    )
    _NICK_TO_CODE: Dict[str, str] = {v: k for k, v in _CODE_TO_NICK.items()}
except Exception as exc:  # noqa: BLE001 -- resolver missing -> name match degrades
    logger.warning("report_intel: team_resolver unavailable: %s", exc)
    _NICK_TO_CODE = {}

    def _norm_name(name: str) -> str:  # minimal fallback normalizer
        return " ".join(str(name).lower().split())


def _resolve_tricode(name: Optional[str]) -> Optional[str]:
    """Best-effort full-name / tricode -> official tricode. None on a miss."""
    if not name:
        return None
    raw = str(name).strip()
    if not raw:
        return None
    if raw.upper() in _NICK_TO_CODE.values():        # already a tricode
        return raw.upper()
    norm = _norm_name(raw)
    if not norm:
        return None
    # Match the trailing nickname token of the normalized full name.
    tokens = norm.split()
    for tok in (norm.replace(" ", ""), tokens[-1] if tokens else ""):
        if tok in _NICK_TO_CODE:
            return _NICK_TO_CODE[tok]
    # "trail blazers" -> "trailblazers" style collapse already covered above; try
    # any nick that is a substring of the normalized name (e.g. "76ers").
    flat = norm.replace(" ", "")
    for nick, code in _NICK_TO_CODE.items():
        if nick in flat:
            return code
    return None


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Read+parse a profile JSON; None on any miss (never raises)."""
    try:
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001 -- a bad file is a null, not a crash
        logger.warning("report_intel: load %s failed: %s", path.name, exc)
        return None


def _rank_labels(items: Any, limit: int = 3) -> List[str]:
    """Pull up to *limit* descriptive labels from a strengths/weaknesses list."""
    out: List[str] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        label = it.get("label")
        if not label:
            continue
        tier = it.get("tier")
        out.append("%s (%s)" % (label, tier) if tier else str(label))
        if len(out) >= limit:
            break
    return out


def _team_blurb(tricode: str) -> Optional[Dict[str, Any]]:
    """Descriptive blurb for one team from its profile + dossier. None on miss."""
    profile = _load_json(_PROFILES_DIR / ("%s.json" % tricode))
    dossier = _load_json(_PROFILES_DIR / ("%s_dossier.json" % tricode))
    if profile is None and dossier is None:
        return None

    scheme: Optional[str] = None
    archetype: Optional[str] = None
    strengths: List[str] = []
    weaknesses: List[str] = []
    source_parts: List[str] = []

    if isinstance(profile, dict):
        sections = profile.get("sections", {}) or {}
        dscheme = sections.get("defense_scheme", {}) or {}
        scheme = dscheme.get("dominant_tag") or None
        if profile.get("as_of_game_date"):
            source_parts.append("profile@%s" % profile["as_of_game_date"])

    if isinstance(dossier, dict):
        blocks = dossier.get("blocks", {}) or {}
        off = (blocks.get("offensive_identity", {}) or {}).get("data", {}) or {}
        pace_id = off.get("pace_identity")
        if pace_id:
            archetype = "%s-paced offense" % str(pace_id).lower()
        sw = (blocks.get("strengths_weaknesses", {}) or {}).get("data", {}) or {}
        strengths = _rank_labels(sw.get("strengths"))
        weaknesses = _rank_labels(sw.get("weaknesses"))
        if dossier.get("last_built"):
            source_parts.append("dossier@%s" % dossier["last_built"])

    if not any((scheme, archetype, strengths, weaknesses)):
        return None
    return {
        "tricode": tricode,
        "label": tricode,
        "archetype": archetype,
        "scheme": scheme,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "source": " + ".join(source_parts) or "persistent_profiles",
    }


def _matchup_blurb(home: Optional[Dict[str, Any]],
                   away: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """One descriptive contrast sentence -- NEVER an edge / who-wins claim."""
    if not home and not away:
        return None
    bits: List[str] = []
    if home and home.get("scheme"):
        bits.append("%s defends with %s" % (home["label"], home["scheme"].lower()))
    if away and away.get("archetype"):
        bits.append("%s runs a %s" % (away["label"], away["archetype"]))
    if not bits:
        # Fall back to a neutral archetype/strength contrast if available.
        for side in (home, away):
            if side and side.get("strengths"):
                bits.append("%s: %s" % (side["label"], side["strengths"][0]))
    if not bits:
        return None
    return {"note": "; ".join(bits) + ".", "edge_claim": False}


def intel_blurbs(sport: str, home: Optional[str], away: Optional[str], *,
                 base: Optional[Any] = None) -> Dict[str, Any]:
    """Descriptive scouting blurbs for (sport, home, away). NEVER raises, NEVER $.

    *base* is accepted for forward-compatible call sites (e.g. a PredictionRecord
    or already-loaded context) but is purely advisory -- the blurbs are read fresh
    from the on-disk profiles so this stays a pure READ-ONLY scouting lookup.

    Returns {home, away, matchup, status, note}. Non-NBA or no-profile-on-disk
    degrades to status='unavailable' with null team blurbs (honest, never faked).
    """
    s = str(sport or "").strip().lower()
    null = {"home": None, "away": None, "matchup": None}
    if s != "nba":
        return {**null, "status": "unavailable",
                "note": "descriptive profiles available for nba only (got '%s')" % s}
    if not _PROFILES_DIR.exists():
        return {**null, "status": "unavailable",
                "note": "profiles dir missing on disk"}

    home_code = _resolve_tricode(home)
    away_code = _resolve_tricode(away)
    home_blurb = _team_blurb(home_code) if home_code else None
    away_blurb = _team_blurb(away_code) if away_code else None
    matchup = _matchup_blurb(home_blurb, away_blurb)

    have = any((home_blurb, away_blurb))
    return {
        "home": home_blurb,
        "away": away_blurb,
        "matchup": matchup,
        "status": "ok" if have else "unavailable",
        "note": ("descriptive scouting only; not an edge claim" if have
                 else "no on-disk profile resolved for either team"),
    }


__all__ = ["intel_blurbs"]
