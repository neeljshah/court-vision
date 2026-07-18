"""Ranking / leaderboard resolver: top-N entities by ONE registered profile
attribute (e.g. "top 5 gravity", "shot_zone_three_efg leaders"). This is a
PLAIN attribute leaderboard, not a scouting CONCEPT superlative -- "best X" /
"who has the most X" questions still route to contracts.answer_superlative
per docs/analytics/ANSWER_RULES.md (raw single-attribute rankings are
small-sample-noisy; concept composites exist precisely to fix that). This
resolver is for the literal "rank entities by this one stat" shape.

Reuses the shared profiles parquet + per-sport attribute registry via
scripts.platformkit.profiles.ask -- no new data path, no re-implemented
fuzzy matcher (ask._norm / ask.load_profiles / ask.load_registry). Because
`sport` was always a plain parameter threaded into ask.load_profiles /
load_registry, this module needed ZERO sport-specific branching to cover
every sport that already has a built profiles parquet -- proven live in
test_leaderboard_resolver.py, one real top-N query per sport.

Per-sport coverage (honest, checked against data/cache/profiles/ + each
domain's attribute_registry.py on 2026-07-10):
  - nba:    data/cache/profiles/nba_{player,team,lineup}_profiles.parquet.
            `n` = minutes/possessions/shots depending on attribute family.
  - mlb:    data/cache/profiles/mlb_player_profiles.parquet (batters only).
            `n` = PA (plate appearances); e.g. K_avoidance floor=200 PA.
  - soccer: data/cache/profiles/soccer_team_profiles.parquet (teams only,
            no player kind built). `n` = matches (attribute's own
            `floor_basis`, e.g. counter_threat floor=30 team_matches).
  - tennis: data/cache/profiles/tennis_player_profiles.parquet.
            `n` = the attribute's own charting/match point count (e.g.
            serve_dominance floor={"charting_svc_n": 1000}).
  - wnba:   profiles exist (wnba_{player,lineup}_profiles.parquet) but is
            OUT OF SCOPE for this pass -- not requested, not proven here.
  min_n stays a raw comparison against the `n` column: it is already the
  sport-and-attribute-correct sample count because each domain's own
  build_profiles.py wrote it that way -- no per-sport min_n table needed
  here, and adding one would just duplicate what attribute_registry.py
  already declares per attribute (read it there, not here).

  EXCEPTION (2026-07-13 audit): a handful of `shot_zone_*` attributes were
  built with `n` = minutes played, not the zone's own attempt count --
  min_n=100 let 2-3 fg3a bigs (Jaxson Hayes, Mark Williams) rank #1 on
  shot_zone_three_efg because their MINUTES cleared the floor while their
  actual three-point attempts didn't. `_ZONE_DENOM_KEYS` below maps those
  attributes to the real ingredient(s) to floor on; every other attribute
  is unaffected (its own build-time n is already the right volume, per the
  per-sport coverage note above). The response always carries
  `denominator_used` so a caller can see which column bound the floor.

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
import json
import re

from scripts.platformkit.profiles import ask as _ask

TOP_N_RE = re.compile(r"^\s*top\s+(\d+)?\s*(.+?)\s*\??\s*$", re.I)
LEADERS_RE = re.compile(r"^\s*(.+?)\s+leaders?\s*\??\s*$", re.I)

# attribute -> ingredient key(s) that give the REAL volume denominator for
# this attribute (a leading "-" subtracts that key). See module docstring
# "EXCEPTION" note -- these are the attributes whose `n` column is minutes,
# not the zone's own attempt count.
_ZONE_DENOM_KEYS: dict[str, tuple[str, ...]] = {
    "shot_zone_three_efg": ("fg3a",),
    "shot_zone_two_fg_pct": ("fga", "-fg3a"),  # two-point attempts = fga - fg3a
}

# 'shooters' is a scouting word, not a registered attribute -- map it to a
# composite instead of falling through to the attribute menu (task 2).
_SHOOTER_STEMS = {"shooter", "shooting"}

# Filler words stripped from a free-text category before description-token
# matching -- without this, a filler word from the query (e.g. "a", "not")
# coincidentally appearing in an unrelated attribute's prose description
# scores a false match. Only bit for sports with big/verbose registries
# (mlb 121 attrs, tennis 73) -- caught by the multi-sport refuse test.
_CATEGORY_STOPWORDS = {"a", "an", "the", "is", "are", "of", "for", "to", "in", "on", "by",
                        "and", "or", "not", "this", "that", "it", "with", "per", "its"}


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
    tset = set(_ask._norm(category).replace("_", " ").split()) - _CATEGORY_STOPWORDS
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
    # a lone description-token hit (score 1) is not evidence -- with the
    # registry now actually loading (nba pkg fix 2026-07-18), garbage input
    # shares one word with SOME description; require a name-token match
    # (score>=2) or the difflib typo path (0.5). REFUSE beats guess.
    if 0.5 < best < 2:
        return []
    return tied


def _derive_denominator(ingredients_json: str, keys: tuple[str, ...]) -> float | None:
    """Sum/subtract ingredient keys (a leading '-' subtracts) -> None if any
    key is missing (row can't be floored, dropped rather than guessed)."""
    try:
        ing = json.loads(ingredients_json)
    except (TypeError, ValueError):
        return None
    total = 0.0
    for k in keys:
        sign, name = (-1.0, k[1:]) if k.startswith("-") else (1.0, k)
        if name not in ing:
            return None
        total += sign * ing[name]
    return total


def _denom_label(keys: tuple[str, ...]) -> str:
    return "".join(k if k.startswith("-") else ("+" + k if i else k) for i, k in enumerate(keys)).lstrip("+")


def _norm_stem(word: str) -> str:
    n = _ask._norm(word)
    return n[:-1] if n.endswith("s") and len(n) > 1 else n


def _shooters_composite(sport: str, df, top_n: int, min_n: float, window: str | None,
                         kind: str | None, ascending: bool) -> dict:
    """'shooters' = attempt-weighted blend of corner3 + above-break-3 eFG.
    Shot-quality naive v1 (no defender/shot-difficulty adjustment) -- stays
    DESCRIPTIVE, never upgraded. Floored on total 3PA (q40 of nonzero-3PA
    players, or the caller's min_n if stricter)."""
    parts = {}
    for efg_key, attr, fga_key in (
        ("corner3", "zone_efg_corner3", "corner3_fga"),
        ("above_break_3", "zone_efg_above_break_3", "above_break_3_fga"),
    ):
        sub = df[(df["sport"] == sport) & (df["attribute"] == attr)]
        if kind:
            sub = sub[sub["kind"] == kind]
        if sub.empty:
            return {"status": "not_supported", "category": "ranking", "sport": sport,
                    "note": f"'shooters' composite needs attribute '{attr}' for sport '{sport}' -- not built"}
        if window:
            w = sub[sub["window"].map(_ask._norm) == _ask._norm(window)]
            sub = w if not w.empty else sub.iloc[0:0]
        else:
            sub = sub.sort_values("window").groupby("entity_id", as_index=False).tail(1)
        if sub.empty:
            return {"status": "no_data", "category": "ranking", "sport": sport,
                    "note": f"no rows for '{attr}' (window={window!r})"}
        fga = sub["ingredients"].map(lambda s, k=fga_key: _derive_denominator(s, (k,)))
        parts[efg_key] = sub[["entity_id", "entity_name", "raw_value"]].assign(fga=fga.values)

    merged = parts["corner3"].merge(parts["above_break_3"], on=["entity_id", "entity_name"],
                                     suffixes=("_corner3", "_above_break_3"), how="outer")
    merged["fga_corner3"] = merged["fga_corner3"].fillna(0.0)
    merged["fga_above_break_3"] = merged["fga_above_break_3"].fillna(0.0)
    merged["raw_value_corner3"] = merged["raw_value_corner3"].fillna(0.0)
    merged["raw_value_above_break_3"] = merged["raw_value_above_break_3"].fillna(0.0)
    merged["attempts"] = merged["fga_corner3"] + merged["fga_above_break_3"]
    merged = merged[merged["attempts"] > 0]
    if merged.empty:
        return {"status": "no_data", "category": "ranking", "sport": sport,
                "note": "no players with nonzero corner3+above-break-3 attempts"}
    merged["blended_efg"] = (
        merged["raw_value_corner3"] * merged["fga_corner3"]
        + merged["raw_value_above_break_3"] * merged["fga_above_break_3"]
    ) / merged["attempts"]
    merged["percentile"] = merged["blended_efg"].rank(pct=True) * 100.0

    q40 = merged["attempts"].quantile(0.4)
    floor = max(min_n, q40) if min_n else q40
    merged = merged[merged["attempts"] >= floor]
    if merged.empty:
        return {"status": "no_data", "category": "ranking", "sport": sport,
                "note": f"zero rows meet attempts>={floor:.1f} floor for 'shooters'"}
    ranked = merged.sort_values(["blended_efg", "entity_id"], ascending=[ascending, True]).head(max(1, int(top_n)))
    return {
        "status": "ok", "category": "ranking", "sport": sport, "attribute": "shooters",
        "window": window or "latest per entity (mixed)", "min_n": round(float(floor), 1),
        "top_n": int(top_n), "ascending": ascending,
        "denominator_used": "corner3_fga+above_break_3_fga",
        "source_artifact": f"data/cache/profiles/{sport}_*_profiles.parquet",
        "note": "shot-quality naive v1 (no defender/shot-difficulty adjustment) -- DESCRIPTIVE only, not gate-validated",
        "rows": [
            {"rank": i + 1, "entity_name": r.entity_name, "entity_id": r.entity_id,
             "raw_value": round(float(r.blended_efg), 4), "attempts": round(float(r.attempts), 1),
             "percentile": round(float(r.percentile), 2), "status_label": "DESCRIPTIVE"}
            for i, r in enumerate(ranked.itertuples(index=False))
        ],
    }


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
    if _norm_stem(category) in _SHOOTER_STEMS:
        return _shooters_composite(sport, df, top_n, min_n, window, kind, ascending)
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
    denom_keys = _ZONE_DENOM_KEYS.get(attribute)
    if denom_keys:
        # bug fix: this attribute's `n` is minutes, not zone attempts -- floor
        # on the real ingredient volume instead, default q40-of-nonzero unless
        # the caller's min_n is stricter.
        sub = sub.assign(denom_attempts=sub["ingredients"].map(lambda s: _derive_denominator(s, denom_keys)))
        sub = sub[sub["denom_attempts"].notna()]
        nonzero = sub[sub["denom_attempts"] > 0]["denom_attempts"]
        q40 = nonzero.quantile(0.4) if not nonzero.empty else 0.0
        effective_min_n = max(min_n, q40) if min_n else q40
        sub = sub[sub["denom_attempts"] >= effective_min_n]
        denominator_used = _denom_label(denom_keys)
    else:
        effective_min_n = min_n
        if min_n:
            sub = sub[sub["n"] >= min_n]
        denominator_used = "n"
    if sub.empty:
        return {"status": "no_data", "category": "ranking", "sport": sport, "attribute": attribute,
                "note": f"zero rows meet window={window!r} and min_n={effective_min_n} "
                        f"(denominator={denominator_used}) for attribute '{attribute}'"}
    ranked = sub.sort_values(["raw_value", "entity_id"], ascending=[ascending, True]).head(max(1, int(top_n)))
    return {
        "status": "ok", "category": "ranking", "sport": sport, "attribute": attribute,
        "window": used_window, "min_n": round(float(effective_min_n), 1), "top_n": int(top_n),
        "ascending": ascending, "denominator_used": denominator_used,
        "source_artifact": f"data/cache/profiles/{sport}_*_profiles.parquet",
        "rows": [
            {"rank": i + 1, "entity_name": r.entity_name, "entity_id": r.entity_id,
             "raw_value": r.raw_value, "percentile": round(float(r.percentile), 2), "n": round(float(r.n), 1),
             **({"attempts": round(float(r.denom_attempts), 1)} if denom_keys else {}),
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
