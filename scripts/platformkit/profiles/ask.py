"""ASK layer: ask about a specific entity+attribute, get a real answer with
ingredients and provenance -- never a bare number. No LLM; deterministic
fuzzy resolution over the shared long-format profile parquets.

Schema (data/cache/profiles/<sport>_{player,team,lineup}_profiles.parquet):
  entity_id, entity_name, window, attribute, raw_value, percentile, rating_2k,
  n, ingredients (json str name->value), status, sources
"""
from __future__ import annotations

import argparse
import difflib
import glob
import importlib
import json
import os
import unicodedata

import pandas as pd

PROFILES_DIR = os.path.join("data", "cache", "profiles")
SPORTS = ["nba", "mlb", "tennis", "soccer", "wnba"]
STATUS_MEANING = {
    "VALIDATED_MECHANISM": "built on a mechanism replicated on independent corpora",
    "VALIDATED_CLAIM": "claims re-verified against source data",
    "DESCRIPTIVE": "computed fact, predictive value not established",
    "PROVISIONAL": "single-fold / not yet replicated -- treat as tentative",
}


def _norm(s) -> str:
    s = str(s or "").lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def load_profiles(sport: str | None = None) -> pd.DataFrame:
    """Concat every <sport>_<kind>_profiles.parquet into one long frame,
    tagging sport + kind from the filename."""
    frames = []
    pat = os.path.join(PROFILES_DIR, f"{sport or '*'}_*_profiles.parquet")
    for path in sorted(glob.glob(pat)):
        base = os.path.basename(path)[: -len("_profiles.parquet")]
        parts = base.split("_")
        sp, kind = parts[0], parts[-1]
        if sp not in SPORTS:
            continue
        try:
            df = pd.read_parquet(path)
        except Exception:
            continue
        df["sport"], df["kind"] = sp, kind
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_registry(sport: str) -> dict:
    """Defensive read of domains/<sport>/profiles/attribute_registry.py.
    Returns {attribute: {description, weight_ledger_family}}. Skips if absent."""
    try:
        mod = importlib.import_module(f"domains.{sport}.profiles.attribute_registry")
    except Exception:
        return {}
    reg: dict = {}
    for cand in ("ATTRIBUTES", "REGISTRY", "ATTRIBUTE_REGISTRY", "attributes"):
        obj = getattr(mod, cand, None)
        if obj is None:
            continue
        items = obj.items() if isinstance(obj, dict) else enumerate(obj)
        for k, v in items:
            if not isinstance(v, dict):
                continue
            name = v.get("name") or v.get("attribute") or (k if isinstance(k, str) else None)
            if name:
                reg[name] = {"description": v.get("description", ""),
                             "weight_ledger_family": v.get("weight_ledger_family")}
        if reg:
            break
    if not reg and hasattr(mod, "get_attributes"):
        try:
            for v in mod.get_attributes():
                if isinstance(v, dict) and v.get("name"):
                    reg[v["name"]] = {"description": v.get("description", ""),
                                      "weight_ledger_family": v.get("weight_ledger_family")}
        except Exception:
            pass
    return reg


def _match_entities(df: pd.DataFrame, q_tokens: list[str]):
    """Score each distinct entity by name-token overlap with the query.
    Returns (best_score, [(entity_id, entity_name, sport), ...] at best score)."""
    ents = df[["entity_id", "entity_name", "sport"]].drop_duplicates()
    best, hits = 0, []
    for eid, name, sp in ents.itertuples(index=False):
        etoks = _norm(name).split()
        if not etoks:
            continue
        score = sum(1 for t in etoks if t in q_tokens)
        if _norm(name) in " ".join(q_tokens):  # full-name substring bonus
            score = max(score, len(etoks))
        if score > best:
            best, hits = score, [(eid, name, sp)]
        elif score == best and score > 0:
            hits.append((eid, name, sp))
    if best == 0:  # difflib fallback: per-token typo tolerance against name tokens
        tok2ent: dict[str, list] = {}
        for eid, name, sp in ents.itertuples(index=False):
            for t in _norm(name).split():
                tok2ent.setdefault(t, []).append((eid, name, sp))
        seen = set()
        for qt in q_tokens:
            for nt in difflib.get_close_matches(qt, list(tok2ent), n=3, cutoff=0.8):
                for e in tok2ent[nt]:
                    if e not in seen:
                        seen.add(e)
                        hits.append(e)
        best = 1 if hits else 0
    return best, hits


def _match_attribute(sub: pd.DataFrame, tokens: list[str], reg: dict) -> str | None:
    """Fuzzy-match an attribute for one entity from leftover query tokens,
    also matching registry descriptions."""
    attrs = list(sub["attribute"].unique())
    tset = set(tokens)
    # substring / token overlap on attribute names
    best, chosen = 0, None
    for a in attrs:
        atoks = set(_norm(a).replace("_", " ").split())
        score = len(atoks & tset)
        if score > best:
            best, chosen = score, a
    if chosen:
        return chosen
    # registry-description match
    for a in attrs:
        desc = _norm(reg.get(a, {}).get("description", ""))
        if desc and tset & set(desc.split()):
            return a
    # difflib on names
    near = difflib.get_close_matches(" ".join(tokens), [_norm(a) for a in attrs], n=1, cutoff=0.5)
    if near:
        for a in attrs:
            if _norm(a) == near[0]:
                return a
    return None


def _pick_row(rows: pd.DataFrame, window: str | None):
    if window:
        w = rows[rows["window"].map(_norm) == _norm(window)]
        if not w.empty:
            rows = w
    # ponytail: "latest" == lexically-max window label; upgrade to a real
    # recency key if windows stop sorting chronologically.
    return rows.sort_values("window").iloc[-1]


def _fmt_row(row) -> str:
    L = [
        f"Entity:     {row['entity_name']}  ({row['sport']} {row.get('kind','')})".rstrip(),
        f"Attribute:  {row['attribute']}",
        f"Window:     {row['window']}",
        f"Raw value:  {row['raw_value']}",
        f"Percentile: {row['percentile']}",
        f"Rating(2K): {row['rating_2k']}",
        f"n:          {row['n']}",
        "Ingredients:",
    ]
    try:
        ing = json.loads(row["ingredients"]) if isinstance(row["ingredients"], str) else (row["ingredients"] or {})
    except Exception:
        ing = {}
    if ing:
        for k, v in ing.items():
            L.append(f"  {k} = {v}")
    else:
        L.append("  (none recorded)")
    st = str(row["status"])
    L.append(f"Status:     {st} -- {STATUS_MEANING.get(st, 'unspecified')}")
    L.append(f"Sources:    {row['sources']}")
    return "\n".join(L)


def answer_lookup(query: str, sport: str | None = None, window: str | None = None) -> dict:
    """Structured single-attribute lookup -- the same resolution `answer()`
    renders to a string, returned instead as {status, ...} so a caller (e.g.
    the resolver registry) gets the real pd.Series row, not a formatted
    string to re-parse. status is one of:
    no_data / no_entity / ambiguous / no_attribute / ok."""
    df = load_profiles(sport)
    if df.empty:
        return {"status": "no_data"}
    q_tokens = _norm(query).split()
    best, hits = _match_entities(df, q_tokens)
    if not hits:
        return {"status": "no_entity"}
    uniq = {(e, n): sp for e, n, sp in hits}
    if len(uniq) > 1:
        return {"status": "ambiguous", "candidates": [f"{n} ({sp})" for (e, n), sp in uniq.items()]}
    eid, ename, esp = hits[0]
    sub = df[(df["entity_id"] == eid) & (df["sport"] == esp)]
    ent_toks = set(_norm(ename).split())
    leftover = [t for t in q_tokens if t not in ent_toks] or q_tokens
    reg = load_registry(esp)
    attr = _match_attribute(sub, leftover, reg)
    if attr is None:
        return {"status": "no_attribute", "entity_name": ename, "sport": esp,
                "available": sorted(sub["attribute"].unique())}
    rows = sub[sub["attribute"] == attr]
    return {"status": "ok", "row": _pick_row(rows, window)}


def answer(query: str, sport: str | None = None, window: str | None = None) -> str:
    r = answer_lookup(query, sport, window)
    if r["status"] == "no_data":
        return ("No profiles built yet -- run domains/<sport>/profiles/build_profiles.py "
                "to populate data/cache/profiles/.")
    if r["status"] == "no_entity":
        return "No entity matched. Try --list to see what is available."
    if r["status"] == "ambiguous":
        return "\n".join(["Multiple entities match -- narrow your query:"]
                          + [f"  - {n}" for n in r["candidates"]])
    if r["status"] == "no_attribute":
        return (f"Attribute not recognized for {r['entity_name']}. Available {r['sport']} attributes:\n  "
                + "\n  ".join(r["available"]))
    return _fmt_row(r["row"])


def list_attributes(sport: str | None = None) -> str:
    df = load_profiles(sport)
    out = []
    for sp in ([sport] if sport else SPORTS):
        attrs = set()
        if not df.empty:
            attrs |= set(df[df["sport"] == sp]["attribute"].unique())
        attrs |= set(load_registry(sp).keys())
        if attrs:
            out.append(f"[{sp}] ({len(attrs)} attributes)")
            out += [f"  - {a}" for a in sorted(attrs)]
    return "\n".join(out) if out else "No attributes found (no profiles built and no registries importable)."


def _ascii(s: str) -> str:
    """cp1252 console: diacritics in entity names (e.g. Jokic's c-acute) crash
    print -- NFKD-fold to plain ASCII at the render boundary only."""
    import unicodedata
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def main(argv=None):
    p = argparse.ArgumentParser(description="Ask about an entity+attribute; get ingredients + provenance.")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--sport")
    p.add_argument("--window")
    p.add_argument("--list", action="store_true")
    p.add_argument("--concept", action="store_true",
                    help="route through the concept answer engine (superlative/comparison/"
                         "explanation composites) instead of a single-attribute lookup -- "
                         "see docs/analytics/ANSWER_RULES.md")
    a = p.parse_args(argv)
    if a.list:
        print(_ascii(list_attributes(a.sport)))
    elif a.concept and a.query:
        from scripts.platformkit.answers import contracts
        print(_ascii(contracts.render(contracts.answer_question(a.query, a.sport or "nba", a.window))))
    elif a.query:
        print(_ascii(answer(a.query, a.sport, a.window)))
    else:
        p.error("provide a query, or use --list")


if __name__ == "__main__":
    main()
