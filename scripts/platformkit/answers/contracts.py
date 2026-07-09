"""Answer contracts -- turns a concept (per-sport registry via
registry_loader.get_registry) into one of four question shapes. Every answer
carries window + n + status + provenance (ingredients); NEVER a bare number.
Reuses each registry's derive_weights for the one weight formula, and
ask.load_profiles/_norm/_match_entities for profile loading + entity resolution.

Question shapes:
    superlative  -- answer_superlative(concept, ...)          "best X"
    comparison   -- answer_comparison(concept, a, b, ...)     "A vs B on X"
    explanation  -- answer_explanation(concept, entity, ...)  "why is A good at X"
    fit          -- answer_fit(concept, entity, roster, ...)  "does A fit team T need X"
        (fit's "team need" = the roster's own composite average, a documented
        proxy -- no on-disk team-need dataset exists.)
Never routes a forecast/prediction question here (docs/analytics/ANSWER_RULES.md):
this answers "what is true about X", not "what will happen" -- predict-matchup owns that.
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from typing import Any

import pandas as pd

from domains.basketball_nba.concepts.concept_registry import STATUS_RANK  # sport-generic status ladder
from scripts.platformkit.answers.registry_loader import get_registry as _registry
from scripts.platformkit.profiles import ask as _ask


def _load_df(sport: str, kind: str = "player") -> pd.DataFrame:
    df = _ask.load_profiles(sport)
    return df[df["kind"] == kind].reset_index(drop=True) if not df.empty else df

def _resolve_entity(df: pd.DataFrame, query: str) -> tuple[Any, str]:
    tokens = _ask._norm(query).split()
    _best, hits = _ask._match_entities(df, tokens)
    if not hits:
        raise ValueError(f"no entity matched '{query}'")
    uniq = {(e, n) for e, n, _sp in hits}
    if len(uniq) > 1:
        raise ValueError(f"ambiguous entity '{query}': {sorted(n for _, n in uniq)}")
    eid, ename, _sp = hits[0]
    return eid, ename


def _entity_composite(weights_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(per-entity composite, per-signal contribution). Groups by entity_id
    ONLY -- some attributes (e.g. spacing_contribution) carry an empty
    entity_name on their own rows (registry's documented '' convention), so
    grouping by (entity_id, entity_name) would split one entity in two."""
    df = weights_df.copy()
    eff_pct = df["percentile"].where(df["direction"] == "higher_is_better", 100 - df["percentile"])
    df["contribution"] = df["norm_weight"] * eff_pct
    names = df[df["entity_name"] != ""].groupby("entity_id")["entity_name"].first()
    comp = df.groupby("entity_id", as_index=False)["contribution"].sum().rename(columns={"contribution": "composite"})
    comp["entity_name"] = comp["entity_id"].map(names).fillna("")
    return comp, df


def _apply_min_n(weights_df: pd.DataFrame, concept: dict, min_n: float | None) -> pd.DataFrame:
    floor = concept["min_n"] if min_n is None else min_n
    primary = weights_df[weights_df["attribute"] == concept["signals"][0]["attribute"]]
    ok_ids = set(primary.loc[primary["n"] >= floor, "entity_id"])
    return weights_df[weights_df["entity_id"].isin(ok_ids)]

def _primary_n(entity_rows: pd.DataFrame, concept: dict) -> float | None:
    row = entity_rows[entity_rows["attribute"] == concept["signals"][0]["attribute"]]
    return float(row["n"].iloc[0]) if not row.empty else None


def _confidence_tier(entity_rows: pd.DataFrame, concept: dict) -> str:
    # HIGH: no PROVISIONAL + primary n>=2x floor + mean status>=VALIDATED_CLAIM. LOW: any
    # PROVISIONAL, or primary n below its own floor. Else MEDIUM.
    if entity_rows.empty or (entity_rows["status"] == "PROVISIONAL").any():
        return "LOW"
    n, floor = _primary_n(entity_rows, concept), concept["min_n"]
    if n is None or n < floor:
        return "LOW"
    avg_rank = entity_rows["status"].map(STATUS_RANK).fillna(1).mean()
    if avg_rank >= STATUS_RANK["VALIDATED_CLAIM"] and n >= 2 * floor:
        return "HIGH"
    return "MEDIUM"


def _sig_summary(r) -> dict:
    return {"raw_value": round(float(r["raw_value"]), 4), "percentile": round(float(r["percentile"]), 2),
            "n": round(float(r["n"]), 1), "status": r["status"]}

def _ingredients(entity_rows: pd.DataFrame) -> dict:
    out = {}
    for _, r in entity_rows.sort_values("norm_weight", ascending=False).iterrows():
        out[r["attribute"]] = {**_sig_summary(r), "weight": round(float(r["norm_weight"]), 4),
                                "contribution": round(float(r["contribution"]), 3)}
    return out


def answer_superlative(concept_name: str, sport: str = "nba", kind: str = "player",
                        window: str | None = None, top_n: int = 3,
                        min_n: float | None = None) -> dict:
    reg = _registry(sport)
    concept = reg.get_concept(concept_name)
    df = _load_df(sport, kind)
    weights = _apply_min_n(reg.derive_weights(concept, df, window), concept, min_n)
    if weights.empty:
        return {"question_type": "superlative", "concept": concept_name, "sport": sport,
                "window": window or "latest", "top": [], "runners_up": [],
                "note": "no entities met the min-n floor"}
    comp_df, contrib_df = _entity_composite(weights)
    comp_df = comp_df.sort_values("composite", ascending=False).reset_index(drop=True)

    def _entry(row) -> dict:
        erows = contrib_df[contrib_df["entity_id"] == row["entity_id"]]
        return {"entity_name": row["entity_name"], "entity_id": row["entity_id"],
                "composite": round(float(row["composite"]), 2), "n": _primary_n(erows, concept),
                "status_mix": sorted(erows["status"].unique().tolist()),
                "confidence": _confidence_tier(erows, concept), "ingredients": _ingredients(erows)}

    top = [_entry(r) for _, r in comp_df.head(top_n).iterrows()]
    runners_up = [_entry(r) for _, r in comp_df.iloc[top_n:top_n + 2].iterrows()]
    return {"question_type": "superlative", "concept": concept_name, "sport": sport,
            "window": window or "latest", "min_n": concept["min_n"] if min_n is None else min_n,
            "top": top, "runners_up": runners_up}


def answer_comparison(concept_name: str, entity_a: str, entity_b: str, sport: str = "nba",
                       kind: str = "player", window: str | None = None) -> dict:
    reg = _registry(sport)
    concept = reg.get_concept(concept_name)
    df = _load_df(sport, kind)
    eid_a, ename_a = _resolve_entity(df, entity_a)
    eid_b, ename_b = _resolve_entity(df, entity_b)
    weights = reg.derive_weights(concept, df, window)
    comp_df, contrib_df = _entity_composite(weights[weights["entity_id"].isin([eid_a, eid_b])])

    def _composite_of(eid):
        row = comp_df[comp_df["entity_id"] == eid]
        return float(row["composite"].iloc[0]) if not row.empty else None

    ca, cb = _composite_of(eid_a), _composite_of(eid_b)
    rows_a = contrib_df[contrib_df["entity_id"] == eid_a].set_index("attribute")
    rows_b = contrib_df[contrib_df["entity_id"] == eid_b].set_index("attribute")
    ingredient_table = [
        {"attribute": attr,
         "a": _sig_summary(rows_a.loc[attr]) if attr in rows_a.index else None,
         "b": _sig_summary(rows_b.loc[attr]) if attr in rows_b.index else None}
        for attr in sorted(set(rows_a.index) | set(rows_b.index))
    ]

    what_would_flip = None
    if ca is not None and cb is not None and ca != cb:
        behind_eid, behind_rows, gap = (eid_a, rows_a, abs(ca - cb)) if ca < cb else (eid_b, rows_b, abs(ca - cb))
        candidates = [(attr, gap / r["norm_weight"]) for attr, r in behind_rows.iterrows() if r["norm_weight"] > 0]
        if candidates:
            attr, pts_needed = min(candidates, key=lambda t: t[1])
            what_would_flip = {
                "trailing_entity": ename_a if behind_eid == eid_a else ename_b, "signal": attr,
                "percentile_points_needed": round(float(pts_needed), 2),
                "note": "smallest single-signal percentile move (others fixed) that flips the ranking"}

    return {"question_type": "comparison", "concept": concept_name, "sport": sport,
            "window": window or "latest",
            "entity_a": {"name": ename_a, "composite": None if ca is None else round(ca, 2)},
            "entity_b": {"name": ename_b, "composite": None if cb is None else round(cb, 2)},
            "favored": (ename_a if (ca or 0) >= (cb or 0) else ename_b) if ca is not None and cb is not None else None,
            "ingredient_table": ingredient_table, "what_would_flip_it": what_would_flip}


def answer_explanation(concept_name: str, entity: str, sport: str = "nba",
                        kind: str = "player", window: str | None = None) -> dict:
    reg = _registry(sport)
    concept = reg.get_concept(concept_name)
    df = _load_df(sport, kind)
    eid, ename = _resolve_entity(df, entity)
    rows = reg.derive_weights(concept, df, window)
    rows = rows[rows["entity_id"] == eid]
    if rows.empty:
        return {"question_type": "explanation", "concept": concept_name, "entity_name": ename,
                "note": "no signals present for this entity/window -- likely below every signal's own floor"}
    comp_df, contrib_df = _entity_composite(rows)
    decomposition = [
        {"attribute": r["attribute"], "contribution": round(float(r["contribution"]), 3),
         "percentile": round(float(r["percentile"]), 2), "weight": round(float(r["norm_weight"]), 4),
         "status": r["status"], "n": round(float(r["n"]), 1)}
        for _, r in contrib_df.sort_values("contribution", ascending=False).iterrows()
    ]
    return {"question_type": "explanation", "concept": concept_name, "sport": sport,
            "window": window or "latest", "entity_name": ename,
            "composite": round(float(comp_df["composite"].iloc[0]), 2),
            "confidence": _confidence_tier(rows, concept), "decomposition": decomposition}


def answer_fit(concept_name: str, entity: str, team_roster: list[str], sport: str = "nba",
               kind: str = "player", window: str | None = None) -> dict:
    reg = _registry(sport)
    concept = reg.get_concept(concept_name)
    df = _load_df(sport, kind)
    eid, ename = _resolve_entity(df, entity)
    comp_df, _ = _entity_composite(reg.derive_weights(concept, df, window))
    ent_row = comp_df[comp_df["entity_id"] == eid]
    if ent_row.empty:
        return {"question_type": "fit", "concept": concept_name, "entity_name": ename,
                "note": "entity has no signals for this concept/window"}

    resolved, unresolved, roster_ids = [], [], []
    for name in team_roster:
        try:
            rid, rname = _resolve_entity(df, name)
        except ValueError:
            unresolved.append(name)
            continue
        if rid != eid:
            roster_ids.append(rid)
            resolved.append(rname)

    roster_rows = comp_df[comp_df["entity_id"].isin(roster_ids)]
    baseline = float(roster_rows["composite"].mean()) if not roster_rows.empty else None
    entity_composite = float(ent_row["composite"].iloc[0])
    return {"question_type": "fit", "concept": concept_name, "sport": sport,
            "window": window or "latest", "entity_name": ename,
            "entity_composite": round(entity_composite, 2),
            "team_need_baseline": None if baseline is None else round(baseline, 2),
            "team_roster_resolved": resolved, "team_roster_unresolved": unresolved,
            "delta": None if baseline is None else round(entity_composite - baseline, 2),
            "note": ("team_need_baseline is the given roster's own current composite average for "
                     "this concept -- a proxy for team need, not a modeled need score.")}


# ---------------------------------------------------------------------------
# CLI / free-text dispatch (thin -- structured flags for anything ambiguous)
# ---------------------------------------------------------------------------
def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")


def render(result: dict) -> str:
    return _ascii(str(result))


def _detect_concept(query: str, sport: str = "nba") -> str | None:
    q = _ask._norm(query)
    for name in _registry(sport).list_concepts():
        if re.search(rf"\b{re.escape(name)}\b", q) or name.replace("_", " ") in q:
            return name
    return None


def answer_question(query: str, sport: str = "nba", window: str | None = None,
                     concept: str | None = None) -> dict:
    """Free-text dispatch for superlative/comparison/explanation questions.
    fit needs a roster -- use answer_fit() directly, or the CLI's --fit/--team."""
    cname = concept or _detect_concept(query, sport)
    if cname is None:
        return {"error": f"no concept recognized in '{query}'. "
                          f"Available: {_registry(sport).list_concepts()}"}
    q = _ask._norm(query)
    if " vs " in q or " versus " in q:
        parts = re.split(r"\s+vs\.?\s+|\s+versus\s+", query, maxsplit=1)
        if len(parts) == 2:
            return answer_comparison(cname, parts[0].strip(), re.split(r"\bon\b", parts[1])[0].strip(),
                                      sport, window=window)
    if q.startswith("why"):
        m = re.search(r"why\s+is\s+(.+?)\s+(good|great|elite)\s+at", query, re.I)
        entity = m.group(1) if m else re.sub(r"why\s+is\s+", "", query, flags=re.I)
        return answer_explanation(cname, entity.strip(), sport, window=window)
    return answer_superlative(cname, sport, window=window)


def main(argv=None):
    p = argparse.ArgumentParser(description="Answer contracts: superlative/comparison/explanation/fit over a concept.")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--sport", default="nba")
    p.add_argument("--window")
    p.add_argument("--concept")
    p.add_argument("--entity", help="for --fit, or comparison's first entity with --vs")
    p.add_argument("--vs", help="second entity, for comparison")
    p.add_argument("--fit", action="store_true")
    p.add_argument("--team", help="comma-separated roster names, for --fit")
    p.add_argument("--top-n", type=int, default=3)
    p.add_argument("--list-concepts", action="store_true")
    a = p.parse_args(argv)
    if a.list_concepts:
        print("\n".join(_registry(a.sport).list_concepts()))
    elif a.fit:
        roster = [s.strip() for s in (a.team or "").split(",") if s.strip()]
        print(render(answer_fit(a.concept, a.entity, roster, a.sport, window=a.window)))
    elif a.vs:
        print(render(answer_comparison(a.concept, a.entity or a.query, a.vs, a.sport, window=a.window)))
    elif a.entity and not a.query:
        print(render(answer_explanation(a.concept, a.entity, a.sport, window=a.window)))
    elif a.concept and not a.query:
        print(render(answer_superlative(a.concept, a.sport, window=a.window, top_n=a.top_n)))
    elif a.query:
        print(render(answer_question(a.query, a.sport, a.window, a.concept)))
    else:
        p.error("provide a query, or --concept with --entity/--vs/--fit, or --list-concepts")


if __name__ == "__main__":
    main()
