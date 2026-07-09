"""domains.tennis.profiles.build_profiles_expanded -- builds the 39 EXPANDED
tennis attributes (court side, set-number, momentum, tiebreak, second-serve
aggression, game-point conversion, plus 28 match_agg x surface-bucket
attributes) registered in attribute_registry.py, and COMBINES them with the
original 10 from build_profiles.build_all() into ONE profiles parquet + ONE
claims file. REUSES build_profiles.write_profiles/build_claims/write_claims
verbatim (already registry-driven, generic over concrete_attributes()) --
zero changes to build_profiles.py needed.

edge_claimed hard-wired False everywhere. NETWORK: zero.
CLI: python -m domains.tennis.profiles.build_profiles_expanded
Per-file test: python -m pytest domains/tennis/profiles/test_build_profiles_expanded.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from domains.tennis.profiles import build_profiles as core
from domains.tennis.profiles.attribute_registry import ATTRIBUTES, MATCH_AGG_BUCKETS, MATCH_AGG_METRICS
from domains.tennis.profiles.ingredients import second_serve_ingredient
from domains.tennis.profiles.ingredients_expanded import (
    _event_vs_baseline, _won_rollup, courtside_points, game_point_points, match_agg_long,
    match_agg_windowed, point_sequence, service_games, set_bucket_points, tiebreak_points,
    tiebreak_serve_points,
)

_COLS = ["entity_id", "entity_name", "window", "attribute", "raw_value", "n", "ingredients", "sources"]
_MATCH_AGG_SOURCES = ("data/domains/tennis/match_stats.parquet;data/domains/tennis/matches.parquet;"
                      "data/domains/tennis/wta_matches.parquet")


def _shape(df: pd.DataFrame, attribute: str, value_col: str, n_col: str, sources: str, ing_fn) -> pd.DataFrame:
    """Common reshape into the shared [entity_id,entity_name,window,attribute,raw_value,n,ingredients,sources] contract."""
    out = df.copy()
    out["attribute"], out["sources"] = attribute, sources
    out["raw_value"], out["n"] = out[value_col], out[n_col]
    out["ingredients"] = out.apply(ing_fn, axis=1)
    return out[_COLS]


def build_courtside(chart_raw: pd.DataFrame) -> pd.DataFrame:
    pts = courtside_points(chart_raw)
    parts = []
    for side, attr in (("deuce", "courtside_serve_deuce"), ("ad", "courtside_serve_ad")):
        floor = ATTRIBUTES[attr]["floor"]["n"]
        g = _won_rollup(pts, floor, bucket_col="side", bucket_val=side)
        parts.append(_shape(g, attr, "rate", "n", core._POINT_SOURCES,
                             lambda r: {"won": int(r["won"]), "n": int(r["n"])}))
    return pd.concat(parts, ignore_index=True)


def build_set_bucket(chart_raw: pd.DataFrame) -> pd.DataFrame:
    pts = set_bucket_points(chart_raw)
    parts = []
    for bucket, attr in (("set1", "serve_by_set_set1"), ("set2", "serve_by_set_set2"),
                          ("set3plus", "serve_by_set_set3plus")):
        floor = ATTRIBUTES[attr]["floor"]["n"]
        g = _won_rollup(pts, floor, bucket_col="set_bucket", bucket_val=bucket)
        parts.append(_shape(g, attr, "rate", "n", core._POINT_SOURCES,
                             lambda r: {"won": int(r["won"]), "n": int(r["n"])}))
    return pd.concat(parts, ignore_index=True)


def build_momentum_bounceback(chart_raw: pd.DataFrame) -> pd.DataFrame:
    floor = ATTRIBUTES["momentum_bounceback"]["floor"]["n"]
    m = _event_vs_baseline(service_games(chart_raw), "prev_broken", floor, floor)
    return _shape(m, "momentum_bounceback", "delta", "n_event", core._POINT_SOURCES, lambda r: {
        "hold_rate_after_break": round(float(r["event_rate"]), 4), "baseline_hold_rate": round(float(r["baseline_rate"]), 4),
        "n_after_break": int(r["n_event"]), "n_baseline": int(r["n_baseline"])})


def build_momentum_streakiness(chart_raw: pd.DataFrame) -> pd.DataFrame:
    floor = ATTRIBUTES["momentum_streakiness"]["floor"]["n"]
    m = _event_vs_baseline(point_sequence(chart_raw), "event", floor, floor)
    return _shape(m, "momentum_streakiness", "delta", "n_event", core._POINT_SOURCES, lambda r: {
        "win_rate_after_win": round(float(r["event_rate"]), 4), "baseline_win_rate": round(float(r["baseline_rate"]), 4),
        "n_after_win": int(r["n_event"]), "n_baseline": int(r["n_baseline"])})


def build_tiebreak(chart_raw: pd.DataFrame) -> pd.DataFrame:
    floor_share = ATTRIBUTES["tiebreak_points_won_share"]["floor"]["n"]
    floor_serve = ATTRIBUTES["tiebreak_serve_win_rate"]["floor"]["n"]
    share = _won_rollup(tiebreak_points(chart_raw), floor_share)
    serve = _won_rollup(tiebreak_serve_points(chart_raw), floor_serve)
    ing = lambda r: {"won": int(r["won"]), "n": int(r["n"])}  # noqa: E731
    return pd.concat([
        _shape(share, "tiebreak_points_won_share", "rate", "n", core._POINT_SOURCES, ing),
        _shape(serve, "tiebreak_serve_win_rate", "rate", "n", core._POINT_SOURCES, ing),
    ], ignore_index=True)


def build_second_serve_aggression(chart_raw: pd.DataFrame) -> pd.DataFrame:
    floor = ATTRIBUTES["second_serve_reliability"]["floor"]["second_serve_n"]
    d = second_serve_ingredient(chart_raw, floor).copy()
    d["delta"] = d["second_rate"] - d["first_rate"]
    return _shape(d, "second_serve_aggression_delta", "delta", "second_n", core._POINT_SOURCES, lambda r: {
        "first_rate": round(float(r["first_rate"]), 4), "second_rate": round(float(r["second_rate"]), 4),
        "first_n": int(r["first_n"]), "second_n": int(r["second_n"])})


def build_game_point(chart_raw: pd.DataFrame) -> pd.DataFrame:
    floor = ATTRIBUTES["game_point_conversion"]["floor"]["n"]
    m = _event_vs_baseline(game_point_points(chart_raw), "game_point", floor, floor)
    return _shape(m, "game_point_conversion", "delta", "n_event", core._POINT_SOURCES, lambda r: {
        "game_point_win_rate": round(float(r["event_rate"]), 4), "baseline_win_rate": round(float(r["baseline_rate"]), 4),
        "n_game_points": int(r["n_event"]), "n_baseline": int(r["n_baseline"])})


def build_match_agg_windows() -> pd.DataFrame:
    long_df = match_agg_long()
    parts = []
    for metric in MATCH_AGG_METRICS:
        for bucket in MATCH_AGG_BUCKETS:
            attr = f"match_agg_{metric}_{bucket}"
            floor = ATTRIBUTES[attr]["floor"]["n"]
            g = match_agg_windowed(long_df, metric, bucket, floor)
            if g.empty:
                continue
            parts.append(_shape(g, attr, "value", "n", _MATCH_AGG_SOURCES,
                                 lambda r, m=metric, b=bucket: {"metric": m, "surface_bucket": b, "n_matches": int(r["n"])}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=_COLS)


def build_all_expanded(chart_raw: pd.DataFrame) -> pd.DataFrame:
    parts = [build_courtside(chart_raw), build_set_bucket(chart_raw), build_momentum_bounceback(chart_raw),
             build_momentum_streakiness(chart_raw), build_tiebreak(chart_raw),
             build_second_serve_aggression(chart_raw), build_game_point(chart_raw), build_match_agg_windows()]
    raw = pd.concat(parts, ignore_index=True)
    raw["percentile"] = raw.groupby(["attribute", "window"])["raw_value"].rank(pct=True) * 100.0
    raw["rating_2k"] = 25.0 + raw["percentile"] * 0.74
    raw["status"] = raw["attribute"].map(lambda a: ATTRIBUTES[a]["status"])
    raw["ingredients"] = raw["ingredients"].map(json.dumps)
    return raw[core._SCHEMA_COLS]


def main() -> int:
    chart_raw = pd.read_parquet(core._CHART_PATH)
    combined = pd.concat([core.build_all(chart_raw), build_all_expanded(chart_raw)], ignore_index=True)
    out = core.write_profiles(combined)
    print(f"wrote {len(combined)} rows ({combined['entity_id'].nunique()} distinct entities, "
          f"{combined['attribute'].nunique()} attributes) -> {out}")

    cov = combined.groupby("attribute").agg(n_rows=("entity_id", "size"), n_entities=("entity_id", "nunique"))
    print(cov.to_string())

    from domains.tennis.profiles.attribute_registry import blocked_attributes, concrete_attributes  # noqa: PLC0415
    print(f"concrete_attributes registered={len(concrete_attributes())}")
    for attr, reason in blocked_attributes().items():
        print(f"BLOCKED {attr}: {reason}")

    claims = core.build_claims(combined)
    claims_path = core.write_claims(claims)
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
