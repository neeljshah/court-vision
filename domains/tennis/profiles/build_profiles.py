"""domains.tennis.profiles.build_profiles -- registry-driven tennis
ATTRIBUTE ENGINE. Reads attribute_registry.ATTRIBUTES for status/floor/
weight_ledger_family (the single source of truth for that metadata); the
actual per-attribute math is plain functions here + ingredients.py -- NOT a
generic formula executor (six attributes don't earn one).

Writes the SHARED CLAIMS CONTRACT snapshot at
data/cache/profiles/tennis_player_profiles.parquet (long format), plus
top-15-per-attribute ranking claims (career_to_2026 window only -- ranking a
2015 rate against a 2024 rate isn't meaningful) at
data/cache/intel_claims/tennis_profile_claims.jsonl, then runs the
independent claims_validator and prints VERIFIED/MISMATCH/UNVERIFIABLE.

edge_claimed hard-wired False everywhere. NETWORK: zero.
CLI: python -m domains.tennis.profiles.build_profiles
Per-file test: python -m pytest domains/tennis/profiles/test_build_profiles.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.tennis.profiles.attribute_registry import (
    ATTRIBUTES, SURFACES, blocked_attributes, concrete_attributes,
)
from domains.tennis.profiles.ingredients import (
    CAREER_WINDOW, REPO_ROOT, match_agg_ingredient, point_return_ingredient,
    point_serve_ingredient, pressure_ingredient, second_serve_ingredient, surface_ingredient,
)

_CHART_PATH = REPO_ROOT / "data/cache/sackmann_pbp/charting_points.parquet"
_OUT = REPO_ROOT / "data/cache/profiles/tennis_player_profiles.parquet"
_CLAIMS_PATH = REPO_ROOT / "data/cache/intel_claims/tennis_profile_claims.jsonl"
_CLAIMS_DIR = _CLAIMS_PATH.parent
_SCHEMA_COLS = ["entity_id", "entity_name", "window", "attribute", "raw_value",
                "percentile", "rating_2k", "n", "ingredients", "status", "sources"]
_POINT_SOURCES = "data/cache/sackmann_pbp/charting_points.parquet"
_MATCH_AGG_SOURCES = ("data/domains/tennis/match_stats.parquet;data/domains/tennis/matches.parquet;"
                      "data/domains/tennis/wta_matches.parquet")
_N_FLOOR_KEY = {"serve_dominance": "charting_svc_n", "return_strength": "charting_return_n",
                "pressure_serve": "n_bp_faced", "second_serve_reliability": "second_serve_n"}


def _rnd(x: Any) -> float | None:
    return None if pd.isna(x) else round(float(x), 4)


def build_serve_dominance(chart_raw: pd.DataFrame) -> pd.DataFrame:
    floor = ATTRIBUTES["serve_dominance"]["floor"]["charting_svc_n"]
    pt = point_serve_ingredient(chart_raw, floor)
    ma = match_agg_ingredient()[["entity_id", "window", "serve_strength", "n_matches"]]
    df = pt.merge(ma, on=["entity_id", "window"], how="left")
    df["raw_value"] = df[["rate", "serve_strength"]].mean(axis=1, skipna=True)
    df["ingredients"] = df.apply(lambda r: {
        "charting_svc_win_rate": _rnd(r["rate"]), "charting_svc_n": int(r["n"]),
        "match_agg_serve_strength": _rnd(r["serve_strength"]),
        "match_agg_n_matches": _rnd(r["n_matches"])}, axis=1)
    df["attribute"], df["sources"] = "serve_dominance", f"{_POINT_SOURCES};{_MATCH_AGG_SOURCES}"
    return df[["entity_id", "entity_name", "window", "attribute", "raw_value", "n", "ingredients", "sources"]]


def build_return_strength(chart_raw: pd.DataFrame) -> pd.DataFrame:
    floor = ATTRIBUTES["return_strength"]["floor"]["charting_return_n"]
    pt = point_return_ingredient(chart_raw, floor)
    ma = match_agg_ingredient()[["entity_id", "window", "return_strength", "n_matches"]]
    df = pt.merge(ma, on=["entity_id", "window"], how="left")
    df["raw_value"] = df[["rate", "return_strength"]].mean(axis=1, skipna=True)
    df["ingredients"] = df.apply(lambda r: {
        "charting_return_win_rate": _rnd(r["rate"]), "charting_return_n": int(r["n"]),
        "match_agg_return_strength": _rnd(r["return_strength"]),
        "match_agg_n_matches": _rnd(r["n_matches"])}, axis=1)
    df["attribute"], df["sources"] = "return_strength", f"{_POINT_SOURCES};{_MATCH_AGG_SOURCES}"
    return df[["entity_id", "entity_name", "window", "attribute", "raw_value", "n", "ingredients", "sources"]]


def build_pressure(chart_raw: pd.DataFrame) -> pd.DataFrame:
    floor = ATTRIBUTES["pressure_serve"]["floor"]["n_bp_faced"]
    snap = pressure_ingredient(chart_raw)
    df = snap[snap["n_bp_faced"] >= floor].copy()
    df["window"] = CAREER_WINDOW
    df["raw_value"], df["n"] = df["delta"], df["n_bp_faced"]
    df["ingredients"] = df.apply(lambda r: {
        "bp_save_rate": _rnd(r["bp_save_rate"]), "baseline": _rnd(r["baseline"]),
        "n_bp_faced": int(r["n_bp_faced"]), "years": f"{int(r['yr_min'])}-{int(r['yr_max'])}"}, axis=1)
    df["attribute"] = "pressure_serve"
    df["sources"] = "data/cache/intel_claims/tennis_pressure_claims__snapshot.parquet;" + _POINT_SOURCES
    return df[["entity_id", "entity_name", "window", "attribute", "raw_value", "n", "ingredients", "sources"]]


def build_second_serve(chart_raw: pd.DataFrame) -> pd.DataFrame:
    floor = ATTRIBUTES["second_serve_reliability"]["floor"]["second_serve_n"]  # first/second floors equal, declared
    df = second_serve_ingredient(chart_raw, floor)
    df["raw_value"], df["n"] = df["second_rate"], df["second_n"]
    df["ingredients"] = df.apply(lambda r: {
        "first_serve_win_rate": _rnd(r["first_rate"]), "first_serve_n": int(r["first_n"]),
        "second_serve_win_rate": _rnd(r["second_rate"]), "second_serve_n": int(r["second_n"])}, axis=1)
    df["attribute"], df["sources"] = "second_serve_reliability", _POINT_SOURCES
    return df[["entity_id", "entity_name", "window", "attribute", "raw_value", "n", "ingredients", "sources"]]


def build_surface(chart_raw: pd.DataFrame) -> pd.DataFrame:
    floor = ATTRIBUTES["surface_splits_serve_Hard"]["floor"]["n"]
    g = surface_ingredient(chart_raw, floor)
    src = f"{_POINT_SOURCES};data/domains/tennis/_raw/sackmann_pbp_repos/tennis_MatchChartingProject/charting-m-matches.csv;data/domains/tennis/_raw/sackmann_pbp_repos/tennis_MatchChartingProject/charting-w-matches.csv"
    rows = []
    for direction, rate_col, n_col in (("serve", "serve_rate", "serve_n"), ("return", "return_rate", "return_n")):
        for surface in SURFACES:
            sub = g[(g["surface"] == surface) & (g[n_col] >= floor)].copy()
            if sub.empty:
                continue
            sub["attribute"] = f"surface_splits_{direction}_{surface}"
            sub["window"], sub["raw_value"], sub["n"] = CAREER_WINDOW, sub[rate_col], sub[n_col]
            sub["ingredients"] = sub.apply(lambda r: {
                "serve_rate": _rnd(r["serve_rate"]), "serve_n": int(r["serve_n"]),
                "return_rate": _rnd(r["return_rate"]), "return_n": int(r["return_n"]),
                "surface": surface}, axis=1)
            sub["sources"] = src
            rows.append(sub[["entity_id", "entity_name", "window", "attribute", "raw_value", "n", "ingredients", "sources"]])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["entity_id", "entity_name", "window", "attribute", "raw_value", "n", "ingredients", "sources"])


def build_all(chart_raw: pd.DataFrame) -> pd.DataFrame:
    parts = [build_serve_dominance(chart_raw), build_return_strength(chart_raw), build_pressure(chart_raw),
             build_second_serve(chart_raw), build_surface(chart_raw)]
    raw = pd.concat(parts, ignore_index=True)
    raw["percentile"] = raw.groupby(["attribute", "window"])["raw_value"].rank(pct=True) * 100.0
    raw["rating_2k"] = 25.0 + raw["percentile"] * 0.74
    raw["status"] = raw["attribute"].map(lambda a: ATTRIBUTES[a]["status"])
    raw["ingredients"] = raw["ingredients"].map(json.dumps)
    return raw[_SCHEMA_COLS]


def write_profiles(df: pd.DataFrame, out_path: Path = _OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out_path)
    return out_path


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def build_claims(df: pd.DataFrame) -> list[dict[str, Any]]:
    career = df[df["window"] == CAREER_WINDOW]
    claims = []
    for attr in concrete_attributes():
        sub = career[career["attribute"] == attr]
        if sub.empty:
            continue
        floor = int(ATTRIBUTES[attr]["floor"].get(_N_FLOOR_KEY.get(attr, "n"), 0))
        snap = sub[["entity_id", "entity_name", "raw_value", "n"]].copy()
        snap["abs_value"] = snap["raw_value"].abs()
        snap_path = _CLAIMS_DIR / f"tennis_profile_claims__{attr}.parquet"
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pandas(snap, preserve_index=False), snap_path)

        top = snap.sort_values("abs_value", ascending=False).head(15)
        ranking = [{"rank": i, "entity_id": r.entity_id, "entity_name": r.entity_name,
                     "value": round(float(r.abs_value), 4), "n": float(r.n)}
                    for i, r in enumerate(top.itertuples(index=False), start=1)]
        claims.append({
            "claim_id": f"tennis_profile_claims__{attr}__career_to_2026", "kind": "ranking",
            "question": f"Which players rank highest by |{attr}| (career_to_2026, top 15)?",
            "criteria": {"metric": "abs_value", "formula": "abs_value", "window": CAREER_WINDOW,
                         "min_sample": {"n": floor}, "direction": "desc", "value_precision": 4,
                         "entity_key": "entity_id"},
            "ranking": ranking, "source_files": [_rel(snap_path)],
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "n_considered": len(snap), "n_excluded_below_floor": 0, "edge_claimed": False,
            "caveats": [
                f"{attr}: floor (n>={floor}) already baked into the source snapshot upstream (min_sample "
                "reapplied here so the validator's independent recompute is honest, not zero by vacuous "
                "construction).",
                "DESCRIPTIVE ranking only -- no forecasting/market/$ edge claimed.",
            ],
        })
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for c in claims:
            f.write(json.dumps(c) + "\n")
    return out_path


def main() -> int:
    chart_raw = pd.read_parquet(_CHART_PATH)
    df = build_all(chart_raw)
    out = write_profiles(df)
    print(f"wrote {len(df)} rows ({df['entity_id'].nunique()} distinct entities) -> {out}")

    cov = df.groupby("attribute").agg(n_rows=("entity_id", "size"), n_entities=("entity_id", "nunique"))
    print(cov.to_string())
    for attr, reason in blocked_attributes().items():
        print(f"BLOCKED {attr}: {reason}")

    claims = build_claims(df)
    claims_path = write_claims(claims)
    print(f"wrote {len(claims)} claims -> {claims_path}")

    from scripts.platformkit.intel_validation.claims_validator import validate_claims_file  # noqa: PLC0415
    summary = validate_claims_file(claims_path)
    print(f"validation: n_claims={summary.n_claims} verified={summary.n_verified} "
          f"mismatch={summary.n_mismatch} unverifiable={summary.n_unverifiable}")
    for d in summary.details:
        print(f"  {d['claim_id']}: {d['verdict']} -- {d['reason']}")
    return 0 if summary.n_mismatch == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
