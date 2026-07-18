"""Two-entity comparison composer -- reuses resolver_registry's matchup
splitting (`_split_matchup`/`_BETWEEN_RE`) and profiles/ask's fuzzy
entity+attribute matcher (`_match_entities`/`_match_attribute`). Answers
"X vs Y -- who has more Z" and, when no metric is named, a side-by-side of
the shared attributes both entities actually have. Never invents a number:
one side unresolved, a cross-sport pairing, or a nonsense attribute all stay
no_data (see RESOLVERS["player_comparison"] in resolver_registry.py).
"""
from __future__ import annotations

import re

from scripts.platformkit.profiles import ask as _ask

_COMPARISON_RE = re.compile(
    r"\bvs\.?\b|\bversus\b|\bcompared to\b|\bstack(?:s|ed)?\s+up\b", re.I)
# "better/higher ... than" -- the two halves are often NOT adjacent in real
# phrasing ("shoot better from three THAN Grayson Allen"), so this checks
# both words appear with the comparative one before "than", not a literal
# contiguous phrase.
_COMPARATIVE_THAN_RE = re.compile(
    r"\b(?:better|higher|more|greater|worse|lower|fewer)\b.{0,60}?\bthan\b", re.I)
# "If A and B matched up head-to-head" / "A and B faced off" -- a comparison
# naming both entities via 'and' ahead of a matchup verb, rather than a vs/
# than/compared-to connector.
_AND_MATCHUP_RE = re.compile(
    r"\b([A-Z][\w.\'-]*(?:\s+[A-Z][\w.\'-]*){0,3})\s+and\s+([A-Z][\w.\'-]*(?:\s+[A-Z][\w.\'-]*){0,3})\s+"
    r"(?:matched up|played (?:each other|one another)|faced off|went head-to-head|squared off)\b")
DEFAULT_ATTR_CAP = 8


def is_comparison_query(query: str) -> bool:
    """A comparison SHAPE is present -- cheap keyword/pattern gate, no entity
    resolution yet (that happens in is_two_player_comparison)."""
    q = query or ""
    return bool(_COMPARISON_RE.search(q) or _COMPARATIVE_THAN_RE.search(q) or _AND_MATCHUP_RE.search(q))


def split_entities(query: str) -> tuple[str | None, str | None]:
    """Two raw entity-name candidates. Tries resolver_registry's own matchup
    splitter first (vs/versus/@/at/between-and -- lazy import to avoid a
    circular import, since resolver_registry imports this module), then the
    'A and B <matched up|...>' shape, then a plain split on 'compared to' /
    comparative-than -- each candidate string can carry extra words (a team
    qualifier, a verb phrase); _resolve_player's token-overlap matching is
    tolerant of that."""
    from scripts.platformkit.answers import resolver_registry as R
    a, b = R._split_matchup(query)
    if a and b:
        return a, b
    m = _AND_MATCHUP_RE.search(query)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.search(r"\bcompared to\b", query, re.I)
    if m:
        left, right = query[:m.start()].strip(" ?.!,"), query[m.end():].strip(" ?.!,")
        if left and right:
            return left, right
    m = re.search(r"\bthan\b", query, re.I)
    if m and _COMPARATIVE_THAN_RE.search(query):
        left, right = query[:m.start()].strip(" ?.!,"), query[m.end():].strip(" ?.!,")
        if left and right:
            return left, right
    return None, None


def _entity_kinds(df, name: str) -> set[str]:
    """{'player'}/{'team'}/{'player','team'} for the best-matching entity
    name, or {'ambiguous'} on a 2+-entity tie, or set() on zero matches."""
    tokens = _ask._norm(name).split()
    _, hits = _ask._match_entities(df, tokens)
    if not hits:
        return set()
    uniq = {(e, n) for e, n, _ in hits}
    if len(uniq) > 1:
        return {"ambiguous"}
    eid, _, esp = hits[0]
    sub = df[(df["entity_id"] == eid) & (df["sport"] == esp)]
    return set(sub["kind"].unique())


def is_two_player_comparison(query: str) -> bool:
    """True only when both sides resolve to a PLAYER entity (at least one
    'player' kind row each). Two pure-team names ('Lakers vs Celtics') return
    False so team-matchup routing (matchup_preview/prediction_winprob/
    concept_rating) is left untouched -- this composer must never steal
    those. Unresolved/ambiguous names also return False (honest fall-through,
    not a guess)."""
    if not is_comparison_query(query):
        return False
    a, b = split_entities(query)
    if not (a and b):
        return False
    df = _ask.load_profiles()
    if df.empty:
        return False
    ka, kb = _entity_kinds(df, a), _entity_kinds(df, b)
    if not ka or not kb or "ambiguous" in ka or "ambiguous" in kb:
        return False
    if ka == {"team"} and kb == {"team"}:
        return False
    return "player" in ka and "player" in kb


def _resolve_player(df, name: str):
    """One resolved player-kind entity, or None (no match / not a player /
    ambiguous)."""
    tokens = _ask._norm(name).split()
    _, hits = _ask._match_entities(df, tokens)
    if not hits:
        return None
    uniq = {(e, n) for e, n, _ in hits}
    if len(uniq) > 1:
        return None
    eid, ename, esp = hits[0]
    sub = df[(df["entity_id"] == eid) & (df["sport"] == esp)]
    sub = sub[sub["kind"] == "player"]
    if sub.empty:
        return None
    return {"entity_id": eid, "entity_name": ename, "sport": esp, "df": sub}


def _entity_payload(row) -> dict:
    return {"entity": row["entity_name"], "attribute": row["attribute"],
            "value": float(row["raw_value"]), "window": str(row["window"]),
            "receipt": str(row["sources"])}


def _metric_compare(left: dict, right: dict, attr: str, window: str | None) -> dict:
    lrows = left["df"][left["df"]["attribute"] == attr]
    rrows = right["df"][right["df"]["attribute"] == attr]
    if lrows.empty or rrows.empty:
        missing = left["entity_name"] if lrows.empty else right["entity_name"]
        return {"status": "no_data", "category": "player_comparison", "sport": left["sport"],
                "note": f"{missing} has no '{attr}' row -- refusing to guess a comparison"}
    a = _entity_payload(_ask._pick_row(lrows, window))
    b = _entity_payload(_ask._pick_row(rrows, window))
    higher = a["entity"] if a["value"] >= b["value"] else b["entity"]
    return {"status": "ok", "category": "player_comparison", "sport": left["sport"],
            "attribute": attr, "a": a, "b": b,
            "comparison": {"higher": higher, "delta": round(abs(a["value"] - b["value"]), 4)},
            "caveats": [f"raw_value comparison only -- rating_2k/percentile are presentation, not causal"]}


def _side_by_side(left: dict, right: dict, cap: int = DEFAULT_ATTR_CAP) -> dict:
    shared = sorted(set(left["df"]["attribute"].unique()) & set(right["df"]["attribute"].unique()))[:cap]
    if not shared:
        return {"status": "no_data", "category": "player_comparison", "sport": left["sport"],
                "note": f"no shared attributes between {left['entity_name']} and {right['entity_name']} "
                        "in this clone"}
    rows = [{"attribute": attr,
             "a": round(float(_ask._pick_row(left["df"][left["df"]["attribute"] == attr], None)["raw_value"]), 4),
             "b": round(float(_ask._pick_row(right["df"][right["df"]["attribute"] == attr], None)["raw_value"]), 4)}
            for attr in shared]
    return {"status": "ok", "category": "player_comparison", "sport": left["sport"],
            "a_entity": left["entity_name"], "b_entity": right["entity_name"], "rows": rows,
            "note": f"no single metric named in the question -- declared default shared-attribute "
                    f"set (cap {cap}), not inferred"}


def compare(query: str, sport: str = "nba", **kwargs) -> dict:
    """Entry point dispatched by resolver_registry.resolve() for category
    'player_comparison'. kwargs a=/b= override query-parsed entity names
    (same override convention as _matchup_teams)."""
    df = _ask.load_profiles()
    if df.empty:
        return {"status": "no_data", "category": "player_comparison", "note": "no profiles built in this clone"}
    a_name, b_name = kwargs.get("a"), kwargs.get("b")
    if not (a_name and b_name):
        a_name, b_name = split_entities(query)
    if not (a_name and b_name):
        return {"status": "no_data", "category": "player_comparison",
                "note": "could not parse two entities from the query -- pass a=/b= or 'X vs Y'"}
    left, right = _resolve_player(df, a_name), _resolve_player(df, b_name)
    if left is None or right is None:
        missing = a_name if left is None else b_name
        return {"status": "no_data", "category": "player_comparison",
                "note": f"'{missing}' did not resolve to a single player entity"}
    if left["sport"] != right["sport"]:
        return {"status": "no_data", "category": "player_comparison",
                "note": f"cross-sport comparison not supported ({left['entity_name']}: {left['sport']} vs "
                        f"{right['entity_name']}: {right['sport']})"}
    reg = _ask.load_registry(left["sport"])
    q_tokens = _ask._norm(query).split()
    ent_toks = set(_ask._norm(left["entity_name"]).split()) | set(_ask._norm(right["entity_name"]).split())
    leftover = [t for t in q_tokens if t not in ent_toks] or q_tokens
    attr = _ask._match_attribute(left["df"], leftover, reg)
    if attr:
        return _metric_compare(left, right, attr, kwargs.get("window"))
    return _side_by_side(left, right, cap=kwargs.get("cap", DEFAULT_ATTR_CAP))
