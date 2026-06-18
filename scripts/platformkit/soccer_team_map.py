"""Light, leak-free OPPONENT-NAME -> team_abbr resolver for the soccer prop board.

The scraped prop lines carry full team names ("France", "South Africa") in the
``match`` / ``team`` fields, but our player-stats parquet carries only FIFA-style
3-letter ``team_abbr`` codes ("FRA", "RSA"). To pass an opponent multiplier we
must map the OPPONENT full name (the OTHER team in ``match``) to that abbr space.

HONESTY (binding): a WRONG opponent mapping silently distorts a player's lambda,
so this BIASES TO A SAFE NO-OP -- when the name cannot be confidently mapped to an
abbr that actually appears in our df, we return None and the caller falls back to
opp_mult=1.0 (the prior, opponent-blind behaviour). We NEVER guess an abbr that is
not present in the df. No edge is claimed; this only feeds a calibration lever.

Resolution order (each restricted to abbrs PRESENT in the df):
  1. Explicit FIFA name table (the non-prefix codes: RSA, GER, NED, ...).
  2. Deaccented 3-letter prefix of the single-token compacted name (FRA/BRA/...),
     accepted ONLY when exactly one df abbr matches.
Anything ambiguous or unseen -> None.

Public functions NEVER raise. ASCII only.

Per-file test (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_soccer_team_map.py -q
"""
from __future__ import annotations

import unicodedata
from typing import Iterable, Optional, Set

# FIFA-ish full country name (deaccented, casefolded) -> team_abbr. Only the codes
# whose abbr is NOT a clean 3-letter prefix of the name need to live here; the rest
# fall through to the prefix rule. Kept small and explicit on purpose.
_NAME_TO_ABBR = {
    "south africa": "RSA", "germany": "GER", "netherlands": "NED",
    "holland": "NED", "south korea": "KOR", "korea republic": "KOR",
    "spain": "ESP", "croatia": "CRO", "switzerland": "SUI", "japan": "JPN",
    "saudi arabia": "KSA", "ivory coast": "CIV", "cote d'ivoire": "CIV",
    "iran": "IRN", "ir iran": "IRN", "uruguay": "URU", "mexico": "MEX",
    "morocco": "MAR", "england": "ENG", "scotland": "SCO", "denmark": "DEN",
    "cape verde": "CPV", "cabo verde": "CPV", "curacao": "CUW",
    "dr congo": "COD", "congo dr": "COD", "haiti": "HAI", "new zealand": "NZL",
    "panama": "PAN", "uzbekistan": "UZB", "jordan": "JOR", "iraq": "IRQ",
    "qatar": "QAT", "turkey": "TUR", "turkiye": "TUR", "norway": "NOR",
    "sweden": "SWE", "austria": "AUT", "australia": "AUS", "belgium": "BEL",
    "bosnia and herzegovina": "BIH", "bosnia herzegovina": "BIH",
    "tunisia": "TUN", "egypt": "EGY", "algeria": "ALG", "ghana": "GHA",
    "senegal": "SEN", "portugal": "POR", "brazil": "BRA", "argentina": "ARG",
    "colombia": "COL", "ecuador": "ECU", "paraguay": "PAR", "france": "FRA",
    "canada": "CAN", "czechia": "CZE", "czech republic": "CZE",
    "united states": "USA", "usa": "USA",
}


def _deaccent(text) -> str:
    """Strip diacritics (NFKD + drop combining marks), casefold, collapse spaces."""
    if text is None:
        return ""
    norm = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(c for c in norm if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())


def opponent_in_match(match, team) -> Optional[str]:
    """Return the OTHER team's display name in ``match`` (the one != ``team``).

    ``match`` is a 'A vs B' / 'A @ B' / 'A v B' style title. Splits on common
    separators, returns the side that does NOT deaccent-equal ``team``. None when
    it cannot be determined (one side, no clean split). Never raises.
    """
    try:
        s = str(match or "")
        for sep in (" vs ", " v ", " @ ", " - ", " x "):
            if sep in s:
                a, b = s.split(sep, 1)
                ta, tb, tt = _deaccent(a), _deaccent(b), _deaccent(team)
                if tt and tt == ta:
                    return b.strip()
                if tt and tt == tb:
                    return a.strip()
                # team not matched to either side -> ambiguous, no guess.
                return None
        return None
    except Exception:  # noqa: BLE001 -- never raise
        return None


def opponent_for_team(teams, team_abbr) -> Optional[str]:
    """Given a 2-element list of team_abbrs and one side, return the OTHER. None
    when not a clean two-team split or the side is absent. Never raises. Used by
    the backtest, where each event has exactly two team_abbrs in the parquet."""
    try:
        uniq = [str(t) for t in (teams or [])]
        if len(uniq) != 2:
            return None
        a, b = uniq
        ta = str(team_abbr)
        if ta == a:
            return b
        if ta == b:
            return a
        return None
    except Exception:  # noqa: BLE001 -- never raise
        return None


def resolve_team_abbr(name, present: Iterable[str]) -> Optional[str]:
    """Map a full team NAME to a team_abbr that is PRESENT in the df. None if not
    confidently mappable. ``present`` = the df's team_abbr universe. Never raises.
    """
    try:
        avail: Set[str] = {str(a).upper() for a in (present or []) if a is not None}
        if not avail:
            return None
        key = _deaccent(name)
        if not key:
            return None
        abbr = _NAME_TO_ABBR.get(key)
        if abbr and abbr in avail:
            return abbr
        # Prefix rule: 3-letter prefix of the compacted (spaceless) name.
        compact = key.replace(" ", "")
        if len(compact) >= 3:
            cand = compact[:3].upper()
            if cand in avail:
                return cand
        return None
    except Exception:  # noqa: BLE001 -- never raise
        return None


def opp_mult_for_line(match, team, df, as_of, stat_c, team_abbrs, opp_cache):
    """Leak-free opponent multiplier for one scraped line's stat. Maps the OTHER
    team in ``match`` to a df team_abbr (light name match), returns 1.0 when the
    opponent is unmappable (NEVER guesses a wrong abbr). Caches all_multipliers per
    (opponent_abbr, as_of) in the caller-owned ``opp_cache``. Never raises.

    ``team_defense.all_multipliers`` is imported lazily so this module stays a thin
    name-mapping utility with no hard soccer-domain dependency at import time.
    """
    try:
        opp_name = opponent_in_match(match, team)
        if not opp_name:
            return 1.0
        opp_abbr = resolve_team_abbr(opp_name, team_abbrs)
        if not opp_abbr:
            return 1.0
        key = (opp_abbr, as_of)
        mults = opp_cache.get(key) if opp_cache is not None else None
        if mults is None:
            from domains.soccer.team_defense import all_multipliers
            mults = all_multipliers(df, opp_abbr, as_of)
            if opp_cache is not None:
                opp_cache[key] = mults
        m = (mults or {}).get(stat_c, 1.0)
        return float(m) if isinstance(m, (int, float)) else 1.0
    except Exception:  # noqa: BLE001 -- never raise; degrade to opponent-blind
        return 1.0


__all__ = ["opponent_in_match", "opponent_for_team", "resolve_team_abbr",
           "opp_mult_for_line"]
