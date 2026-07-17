"""compose_comparables(sport, player, k=5) -> K nearest players by Euclidean
distance over registered attribute PERCENTILES (numpy only, no sklearn).

Loads through the SAME memoized scripts.platformkit.profiles.ask.load_profiles
(sport) compose_scout.py uses -- no second parquet reader here, and a repeat
call in the same process hits the shared single-slot memo instead of
re-reading data/cache/profiles/<sport>_*_profiles.parquet (long format:
entity_id, entity_name, window, attribute, raw_value, percentile, kind, ...).
Filtered to kind=='player' before pivoting (load_profiles concats every
player/team/lineup parquet for the sport; only player rows belong in a
player-comparables KNN). Attribute descriptions are
enriched from domains/<domain>/profiles/attribute_registry.py when available
(the parquet's own `attribute` column is the ground truth for which
attributes are "player"-entity for a sport -- the builder only ever writes
rows for attributes its own registry declares, so no per-sport entity-
taxonomy mapping is needed here; NBA's registry splits player/team/lineup,
MLB's splits batter/pitcher/catcher/fielder, tennis has no split at all).

Distance: per-neighbor Euclidean, NORMALIZED by shared dimension count
(sqrt(mean(delta**2)), i.e. RMS percentile-point gap) over attributes present
(non-null percentile) for BOTH the target and the candidate ("shared
attributes"). Unnormalized (raw-sum) Euclidean would favor thin-sample
candidates purely because they share FEWER dimensions with the target, not
because they are actually similar -- RMS keeps the comparison fair across
varying intersection sizes. A candidate whose shared-attribute count is below
MIN_SHARED_ATTRS is dropped, never distance-padded with a guessed value.
Descriptive only: "statistically similar profile", never a projection.

Envelope: {status: ok|refused|not_supported|no_data, category, sport,
source_artifact, as_of, ...} -- category-specific fields are player,
entity_id, k, floor, neighbors.

CLI: python -m scripts.platformkit.intel_query.compose_comparables --sport nba --player "Nikola Jokic"
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import unicodedata
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from scripts.platformkit.profiles import ask as _profiles

MIN_SHARED_ATTRS = 5
CATEGORY = "player_comparables"
# ask.load_registry's domains.<sport> import is wrong for nba/wnba (the
# domain folder is basketball_<sport>) -- same fix attribute_gate.py applies.
_DOMAIN = {"nba": "basketball_nba", "wnba": "basketball_wnba"}


def _norm(s) -> str:
    s = str(s or "").lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(status: str, sport: str, source_artifact: str, **extra) -> dict:
    return {"status": status, "category": CATEGORY, "sport": sport,
            "source_artifact": source_artifact, "as_of": _now(), **extra}


def _load_attribute_descriptions(sport: str) -> dict:
    """{attribute_name: description}, best-effort. Registry absent, or
    lacking an ATTRIBUTES/PLAYER_ATTRIBUTES dict -> {} (descriptions are
    presentation-only, never load-bearing for the KNN itself)."""
    domain = _DOMAIN.get(sport, sport)
    try:
        mod = importlib.import_module(f"domains.{domain}.profiles.attribute_registry")
    except Exception:
        return {}
    for cand in ("ATTRIBUTES", "PLAYER_ATTRIBUTES", "REGISTRY"):
        obj = getattr(mod, cand, None)
        if isinstance(obj, dict):
            return {k: v.get("description", "") for k, v in obj.items() if isinstance(v, dict)}
    return {}


def _player_profiles_path(sport: str) -> str:
    # same naming compose_scout.py's _profiles_path(sport, "player") reports
    return os.path.join(_profiles.PROFILES_DIR, f"{sport}_player_profiles.parquet")


def _pivot_percentiles(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """entity_id x attribute -> percentile (latest window per entity+attribute).
    ponytail: "latest" = lexically-max window label, same tie-break
    profiles/ask.py's _pick_row uses -- upgrade both together if windows
    stop sorting chronologically."""
    d = df.sort_values("window").drop_duplicates(subset=["entity_id", "attribute"], keep="last")
    wide = d.pivot(index="entity_id", columns="attribute", values="percentile")
    names = d.drop_duplicates("entity_id").set_index("entity_id")["entity_name"]
    return wide, names


def _match_entity(names: pd.Series, player: str) -> int | None:
    """Normalized-exact match preferred; else a UNIQUE substring hit. Zero or
    ambiguous (>1) matches both return None -> caller reports no_data."""
    key = _norm(player)
    exact = [eid for eid, nm in names.items() if _norm(nm) == key]
    if len(exact) == 1:
        return exact[0]
    sub = [eid for eid, nm in names.items() if key and key in _norm(nm)]
    if len(sub) == 1:
        return sub[0]
    return None


def compose_comparables(sport: str, player: str, k: int = 5,
                         floor: int = MIN_SHARED_ATTRS) -> dict:
    path = _player_profiles_path(sport)
    df = _profiles.load_profiles(sport)
    if not df.empty:
        df = df[df["kind"] == "player"].reset_index(drop=True)
    if df.empty:
        return _envelope("no_data", sport, path,
                          note=f"no player profile parquet built for sport={sport!r} in this clone")

    wide, names = _pivot_percentiles(df)
    eid = _match_entity(names, player)
    if eid is None:
        return _envelope("no_data", sport, path,
                          player=player,
                          note="no unique entity matched this player name in the profile parquet")

    target = wide.loc[eid]
    target_attrs = set(target.dropna().index)
    if len(target_attrs) < floor:
        return _envelope("refused", sport, path, player=player, entity_id=int(eid), floor=floor,
                          note=f"target player has only {len(target_attrs)} registered attributes "
                               f"on file, below the floor of {floor}")

    descriptions = _load_attribute_descriptions(sport)
    neighbors = []
    for other_eid in wide.index:
        if other_eid == eid:
            continue
        other = wide.loc[other_eid]
        shared = sorted(target_attrs & set(other.dropna().index))
        if len(shared) < floor:
            continue
        tv = target[shared].to_numpy(dtype=float)
        ov = other[shared].to_numpy(dtype=float)
        dist = float(np.sqrt(np.mean((tv - ov) ** 2)))  # RMS, not raw sum -- see module docstring
        neighbors.append({
            "entity_id": int(other_eid), "entity_name": names.loc[other_eid],
            "distance": round(dist, 4), "n_attrs": len(shared),
            "attributes_used": [{"attribute": a, "description": descriptions.get(a, "")} for a in shared],
        })

    if not neighbors:
        return _envelope("refused", sport, path, player=player, entity_id=int(eid), floor=floor,
                          note=f"no candidate cleared the >={floor} shared-attribute intersection floor")

    neighbors.sort(key=lambda n: (n["distance"], n["entity_id"]))
    return _envelope("ok", sport, path, player=names.loc[eid], entity_id=int(eid), k=k, floor=floor,
                      neighbors=neighbors[:k],
                      note="statistically similar profile (Euclidean over shared percentile attributes) "
                           "-- descriptive only, never a projection")


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="K nearest players by Euclidean distance over registered "
                                             "attribute percentiles.")
    p.add_argument("--sport", default="nba")
    p.add_argument("--player", required=True)
    p.add_argument("--k", type=int, default=5)
    args = p.parse_args(argv)
    result = compose_comparables(args.sport, args.player, args.k)
    print(_ascii(json.dumps(result, indent=2, ensure_ascii=True)))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
