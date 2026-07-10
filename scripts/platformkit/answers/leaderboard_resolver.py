"""Ranking / leaderboard resolver: top-N entities by ONE registered profile
attribute (e.g. "top 5 gravity", "shot_zone_three_efg leaders"). This is a
PLAIN attribute leaderboard, not a scouting CONCEPT superlative -- "best X" /
"who has the most X" questions still route to contracts.answer_superlative
per docs/analytics/ANSWER_RULES.md (raw single-attribute rankings are
small-sample-noisy; concept composites exist precisely to fix that). This
resolver is for the literal "rank entities by this one stat" shape.

Reuses the shared profiles parquet + per-sport attribute registry via
scripts.platformkit.profiles.ask -- no new data path, no re-implemented
fuzzy matcher (ask._norm / ask.load_profiles / ask.load_registry).

Deterministic, refuse-unregistered, matching the rest of this stack:
  - a category word must resolve to exactly ONE known attribute name for the
    sport. Zero or 2+ candidates -> refuse (not_supported / ambiguous) with
    the candidate list returned, never guessed.
  - min_n is an OPT-IN extra volume floor on top of the floor already baked
    into the profiles builder (attribute_registry.py's own `floor` -- rows
    below it are already omitted at build time, never zero-filled). Pass
    min_n only to raise the bar further (e.g. a stricter "qualified
    leaders" cut). Default 0 = no additional filtering, no 1-attempt
    leaders survive regardless because the per-attribute floor already ran.
  - ties broken deterministically: raw_value (or percentile) desc, then
    entity_id asc.
  - ponytail: direction (higher-is-better vs lower-is-better) is NOT
    inferred per attribute -- that metadata is shaped differently across
    the 5 sports' registries. `ascending=True` is the caller's explicit
    knob for lower-is-better metrics (fouls, turnovers, concession rates).
    Upgrade path: consult each sport's own lower-is-better set if this
    resolver grows enough callers to need it.
"""
from __future__ import annotations

import difflib
import re

from scripts.platformkit.profiles import ask as _ask

TOP_N_RE = re.compile(r"^\s*top\s+(\d+)?\s*(.+?)\s*\??\s*$", re.I)
LEADERS_RE = re.compile(r"^\s*(.+?)\s+leaders?\s*\??\s*$", re.I)


def is_ranking_query(text: str) -> bool:
    return bool(TOP_N_RE.match(text) or LEADERS_RE.match(text))


def parse_query(text: str) -> tuple[str, int | None]:
    """Free-text -> (category_text, top_n_or_None). "top 10 shooters" ->
    ("shooters", 10); "gravity leaders" -> ("gravity", None)."""
    m = TOP_N_RE.match(text)
    if m:
        n = int(m.group(1)) if m.group(1) else None
        return m.group(2).strip(), n
    m = LEADERS_RE.match(text)
    if m:
        return m.group(1).strip(), None
    return text.strip(), None


def _candidate_attributes(sport: str, category: str, df=None) -> list[str]:
    """Fuzzy-match a free-text category word against this sport's known
    attribute names + registry descriptions. Returns the attribute(s) tied
    at the best match score (empty if nothing scores -- REFUSE, not guess)."""
    if df is None:
        df = _ask.load_profiles(sport)
    attrs = sorted(df[df["sport"] == sport]["attribute"].unique()) if not df.empty else []
    reg = _ask.load_registry(sport)
    attrs = sorted(set(attrs) | set(reg))
    if category in attrs:
        return [category]
    tset = set(_ask._norm(category).replace("_", " ").split())
    best, tied = 0.0, []
    for a in attrs:
        atoks = set(_ask._norm(a).replace("_", " ").split())
        desc_toks = set(_ask._norm(reg.get(a, {}).get("description", "")).split())
        score = len(atoks & tset) * 2 + len(desc_toks & tset)
        if score == 0:
            # last resort: fuzzy string similarity on the whole word (typos)
            near = difflib.get_close_matches(_ask._norm(category), [_ask._norm(a)], n=1, cutoff=0.75)
            score = 0.5 if near else 0
        if score > best:
            best, tied = score, [a]
        elif score == best and score > 0:
            tied.append(a)
    return tied


def leaderboard(sport: str, category: str, top_n: int = 10, min_n: float = 0.0,
                 window: str | None = None, kind: str | None = None,
                 ascending: bool = False) -> dict:
    """Top-N entities for `category` (an exact attribute name, or a fuzzy
    word resolved to exactly one candidate). status: not_supported (sport
    unwired, or zero attributes matched) | ambiguous (2+ candidates -- name
    one explicitly) | no_data | ok."""
    if sport not in _ask.SPORTS:
        return {"status": "not_supported", "category": "ranking", "sport": sport,
                "note": f"sport not wired for profile lookups. Available: {_ask.SPORTS}"}
    df = _ask.load_profiles(sport)
    candidates = _candidate_attributes(sport, category, df=df)
    if not candidates:
        all_attrs = sorted(df[df["sport"] == sport]["attribute"].unique()) if not df.empty else []
        return {"status": "not_supported", "category": "ranking", "sport": sport,
                "note": f"no registered attribute matched '{category}' for sport '{sport}' -- "
                        "name one explicitly rather than guessing", "available": all_attrs}
    if len(candidates) > 1:
        return {"status": "ambiguous", "category": "ranking", "sport": sport,
                "note": f"'{category}' matches multiple registered attributes -- name one explicitly",
                "candidates": candidates}
    attribute = candidates[0]
    if df.empty:
        return {"status": "no_data", "category": "ranking", "sport": sport, "attribute": attribute}
    sub = df[(df["sport"] == sport) & (df["attribute"] == attribute)]
    if kind:
        sub = sub[sub["kind"] == kind]
    if sub.empty:
        return {"status": "no_data", "category": "ranking", "sport": sport, "attribute": attribute,
                "note": f"no rows for attribute '{attribute}' (kind={kind!r})"}
    used_window = window
    if window:
        w = sub[sub["window"].map(_ask._norm) == _ask._norm(window)]
        sub = w if not w.empty else sub.iloc[0:0]
    else:
        # latest window per entity -- same convention as ask.py's _pick_row
        sub = sub.sort_values("window").groupby("entity_id", as_index=False).tail(1)
        used_window = "latest per entity (mixed)" if sub["window"].nunique() > 1 else str(sub["window"].iloc[0]) if not sub.empty else None
    if min_n:
        sub = sub[sub["n"] >= min_n]
    if sub.empty:
        return {"status": "no_data", "category": "ranking", "sport": sport, "attribute": attribute,
                "note": f"zero rows meet window={window!r} and min_n={min_n} for attribute '{attribute}'"}
    ranked = sub.sort_values(["raw_value", "entity_id"], ascending=[ascending, True]).head(max(1, int(top_n)))
    return {
        "status": "ok", "category": "ranking", "sport": sport, "attribute": attribute,
        "window": used_window, "min_n": min_n, "top_n": int(top_n), "ascending": ascending,
        "source_artifact": f"data/cache/profiles/{sport}_*_profiles.parquet",
        "rows": [
            {"rank": i + 1, "entity_name": r.entity_name, "entity_id": r.entity_id,
             "raw_value": r.raw_value, "percentile": round(float(r.percentile), 2), "n": round(float(r.n), 1),
             "status_label": r.status}
            for i, r in enumerate(ranked.itertuples(index=False))
        ],
    }


def resolve_query(sport: str, query: str, top_n: int | None = None, min_n: float = 0.0,
                   window: str | None = None, kind: str | None = None, ascending: bool = False,
                   category: str | None = None) -> dict:
    """Entry point for resolver_registry.resolve() -- parses "top N <cat>" /
    "<cat> leaders" free text when `category` isn't given explicitly."""
    cat_text, parsed_n = (category, None) if category else parse_query(query)
    return leaderboard(sport, cat_text, top_n=top_n or parsed_n or 10, min_n=min_n,
                        window=window, kind=kind, ascending=ascending)
