"""Soccer player-name RESOLVER: scraped prop name -> our roster player_id.

The CONVERGENCE step joins scraped sportsbook/DFS prop lines to our model's
per-player distributions. The join key is the player NAME -- and a WRONG match
fabricates a fake edge (we'd price book A's line against player B's history). So
this resolver BIASES TO FALSE-NEGATIVE: when a name is ambiguous it returns
status "unresolved" rather than guessing. A missed real edge is cheap; a fake one
is not.

Matching rules (in order of trust):
  1. Deaccent (Unicode NFKD + drop combining marks) and casefold BOTH sides, so
     "Luis Diaz" matches "Luis Diaz" / "Luis Diaz" regardless of diacritics.
  2. EXACT deaccented full-name match -> ok (if exactly one such df player).
  3. LAST-NAME + FIRST-INITIAL match -> ok ONLY when it is UNIQUE within the team
     (when a team is supplied) or unique overall. 2+ candidates -> unresolved.
  4. Anything else -> unresolved, with a human-readable reason.

Public functions NEVER raise -- they degrade to status "unresolved" and NEVER
fabricate a player_id or matched_name.

Run the per-file test (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_player_resolver.py -q
"""
from __future__ import annotations

import unicodedata
from typing import Any, Dict, List, Optional

import pandas as pd

_PLAYER_COL = "player"      # ESPN displayName
_ID_COL = "player_id"
_TEAM_COL = "team_abbr"


def _deaccent(text: str) -> str:
    """Strip diacritics (NFKD + drop combining marks) and casefold. ASCII-safe."""
    if text is None:
        return ""
    norm = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(c for c in norm if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())


def _last_initial_key(full: str) -> Optional[str]:
    """Deaccented 'lastname|firstinitial' key, or None if not derivable.

    Uses the FIRST token's initial + the LAST token as surname -- a coarse but
    deterministic key. Single-token names yield None (too little to disambiguate).
    """
    parts = _deaccent(full).split()
    if len(parts) < 2:
        return None
    return parts[-1] + "|" + parts[0][0]


def build_name_index(df: pd.DataFrame) -> Dict[str, Any]:
    """Build a reusable lookup index for one roster df (call once per df).

    Returns a dict with:
      exact:  {deaccented_full_name: [ {player_id, name, team}, ... ]}
      li:     {lastname|initial:      [ {player_id, name, team}, ... ]}
    Each candidate is de-duplicated on (player_id) so the same player across many
    match rows counts once. Degrades to empty maps on bad input (never raises).
    """
    exact: Dict[str, List[Dict[str, Any]]] = {}
    li: Dict[str, List[Dict[str, Any]]] = {}
    out = {"exact": exact, "li": li}
    if df is None or len(df) == 0 or _PLAYER_COL not in df.columns:
        return out

    seen_exact = set()
    seen_li = set()
    have_id = _ID_COL in df.columns
    have_team = _TEAM_COL in df.columns
    for _, row in df.iterrows():
        name = row.get(_PLAYER_COL)
        if name is None or (isinstance(name, float) and pd.isna(name)):
            continue
        name = str(name)
        pid = row.get(_ID_COL) if have_id else None
        pid = None if (pid is None or (isinstance(pid, float) and pd.isna(pid))) else str(pid)
        team = row.get(_TEAM_COL) if have_team else None
        team = None if (team is None or (isinstance(team, float) and pd.isna(team))) else str(team)
        cand = {"player_id": pid, "name": name, "team": team}

        ek = _deaccent(name)
        if ek:
            tag = (ek, pid)
            if tag not in seen_exact:
                seen_exact.add(tag)
                exact.setdefault(ek, []).append(cand)

        lk = _last_initial_key(name)
        if lk:
            tag = (lk, pid)
            if tag not in seen_li:
                seen_li.add(tag)
                li.setdefault(lk, []).append(cand)
    return out


def _filter_team(cands: List[Dict[str, Any]], team: Optional[str]) -> List[Dict[str, Any]]:
    """Narrow candidates to a team (deaccented compare). No team -> unchanged."""
    if not team:
        return cands
    tnorm = _deaccent(team)
    matched = [c for c in cands if c.get("team") and _deaccent(c["team"]) == tnorm]
    # Only narrow when the team actually matches something; otherwise the team
    # label simply doesn't line up with our roster abbreviations -> keep all and
    # let uniqueness decide (do NOT silently drop a real candidate).
    return matched if matched else cands


def _result(player_id, matched_name, status, reason) -> Dict[str, Any]:
    return {
        "player_id": player_id,
        "matched_name": matched_name,
        "status": status,
        "reason": reason,
    }


def resolve_player(
    df: pd.DataFrame,
    raw_name: str,
    *,
    team: Optional[str] = None,
    index: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve a scraped player name to a roster player_id (bias to false-negative).

    Returns {player_id, matched_name, status, reason}. status is "ok" only on a
    trustworthy unique match; otherwise "unresolved" with a reason. NEVER raises,
    NEVER guesses among 2+ candidates. Pass a prebuilt *index* for speed.
    """
    try:
        if raw_name is None or not str(raw_name).strip():
            return _result(None, None, "unresolved", "empty raw name")
        idx = index if index is not None else build_name_index(df)
        exact = idx.get("exact", {})
        li = idx.get("li", {})

        # 1. Exact deaccented full-name match.
        ek = _deaccent(raw_name)
        ex = _filter_team(exact.get(ek, []), team)
        ex_ids = {c["player_id"] for c in ex}
        if len(ex_ids) == 1:
            c = ex[0]
            return _result(c["player_id"], c["name"], "ok", "exact_deaccented")
        if len(ex_ids) > 1:
            return _result(None, None, "unresolved",
                           "ambiguous exact match (%d candidates)" % len(ex_ids))

        # 2. Last-name + first-initial, unique within team (or overall).
        lk = _last_initial_key(raw_name)
        if lk is None:
            return _result(None, None, "unresolved", "no match (single-token name)")
        cands = _filter_team(li.get(lk, []), team)
        ids = {c["player_id"] for c in cands}
        if len(ids) == 1:
            c = cands[0]
            scope = "team" if team else "overall"
            return _result(c["player_id"], c["name"], "ok",
                           "lastname_initial_unique_%s" % scope)
        if len(ids) > 1:
            return _result(None, None, "unresolved",
                           "ambiguous lastname+initial (%d candidates)" % len(ids))
        return _result(None, None, "unresolved", "no match")
    except Exception as exc:  # noqa: BLE001 -- public fn must never raise
        return _result(None, None, "unresolved",
                       "resolver error (%s)" % type(exc).__name__)


__all__ = ["resolve_player", "build_name_index"]
