"""domains.tennis.profiles.build_profiles_windows -- builds the WINDOW +
OPPONENT-TIER + FORM tennis attributes (49 -> 72 registry keys; see
attribute_registry.py's WINDOWS block) and COMBINES them with build_profiles
+ build_profiles_expanded's existing output into ONE profiles parquet + ONE
claims file. REUSES build_profiles.write_profiles/build_claims/write_claims
verbatim -- zero changes to build_profiles.py needed.

CLAIMS SCOPE: build_profiles.build_claims already restricts to rows whose
window == CAREER_WINDOW ("career_to_2026"). The opp_tier_* attributes are
written with that exact window, so they get ranking claims automatically by
running the SAME unmodified build_claims over the combined frame -- zero new
claims code. window_<metric> (year_YYYY) and form_* (last10) rows do NOT
match CAREER_WINDOW and are therefore excluded from claims by construction
(documented here, not special-cased): per-year claims would explode the
store (7 metrics x 11 years), so year_YYYY rows live ONLY in the profiles
parquet for the leak-free prior-window gate to read directly.

edge_claimed hard-wired False everywhere. NETWORK: zero.
CLI: python -m domains.tennis.profiles.build_profiles_windows
Per-file test: python -m pytest domains/tennis/profiles/test_build_profiles_windows.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from domains.tennis.profiles import build_profiles as core
from domains.tennis.profiles import build_profiles_expanded as expanded
from domains.tennis.profiles.attribute_registry import (
    ATTRIBUTES, FORM_FLOOR, MATCH_AGG_METRICS, OPPONENT_TIERS, TIER_FLOOR, WINDOW_YEAR_FLOOR,
)
from domains.tennis.profiles.ingredients import CAREER_WINDOW
from domains.tennis.profiles.ingredients_windows import (
    form_last10, match_agg_long_with_rank, opponent_tier_rollup, year_window_rollup,
)

_COLS = ["entity_id", "entity_name", "window", "attribute", "raw_value", "n", "ingredients", "sources"]
_SOURCES = ("data/domains/tennis/match_stats.parquet;data/domains/tennis/matches.parquet;"
            "data/domains/tennis/wta_matches.parquet")


def _shape(df: pd.DataFrame, attribute: str, value_col: str, n_col: str, ing_fn) -> pd.DataFrame:
    out = df.copy()
    out["attribute"], out["sources"] = attribute, _SOURCES
    out["raw_value"], out["n"] = out[value_col], out[n_col]
    out["ingredients"] = out.apply(ing_fn, axis=1)
    return out[_COLS]


def build_windows(long_df: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for metric in MATCH_AGG_METRICS:
        g = year_window_rollup(long_df, metric, WINDOW_YEAR_FLOOR)
        if g.empty:
            continue
        parts.append(_shape(g, f"window_{metric}", "value", "n",
                             lambda r, m=metric: {"metric": m, "n_matches": int(r["n"])}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=_COLS)


def build_opponent_tiers(long_df: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for metric in MATCH_AGG_METRICS:
        g = opponent_tier_rollup(long_df, metric, TIER_FLOOR)
        for tier in OPPONENT_TIERS:
            sub = g[g["tier"] == tier] if not g.empty else g
            if sub.empty:
                continue
            sub = sub.assign(window=CAREER_WINDOW)
            parts.append(_shape(sub, f"opp_tier_{metric}_{tier}", "value", "n",
                                 lambda r, m=metric, t=tier: {"metric": m, "tier": t, "n_matches": int(r["n"])}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=_COLS)


def build_form(long_df: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for metric, attr in (("serve_pts_won", "form_serve_dominance"), ("return_pts_won", "form_return_strength")):
        g = form_last10(long_df, metric, FORM_FLOOR)
        if g.empty:
            continue
        g = g.assign(window="last10")
        parts.append(_shape(g, attr, "value", "n", lambda r, m=metric: {"metric": m, "n_matches": int(r["n"])}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=_COLS)


def build_all_windows() -> pd.DataFrame:
    long_df = match_agg_long_with_rank()
    parts = [build_windows(long_df), build_opponent_tiers(long_df), build_form(long_df)]
    raw = pd.concat(parts, ignore_index=True)
    raw["percentile"] = raw.groupby(["attribute", "window"])["raw_value"].rank(pct=True) * 100.0
    raw["rating_2k"] = 25.0 + raw["percentile"] * 0.74
    raw["status"] = raw["attribute"].map(lambda a: ATTRIBUTES[a]["status"])
    raw["ingredients"] = raw["ingredients"].map(json.dumps)
    return raw[core._SCHEMA_COLS]


def main() -> int:
    chart_raw = pd.read_parquet(core._CHART_PATH)
    combined = pd.concat([core.build_all(chart_raw), expanded.build_all_expanded(chart_raw),
                           build_all_windows()], ignore_index=True)
    out = core.write_profiles(combined)
    print(f"wrote {len(combined)} rows ({combined['entity_id'].nunique()} distinct entities, "
          f"{combined['attribute'].nunique()} attributes) -> {out}")

    cov = combined.groupby("attribute").agg(n_rows=("entity_id", "size"), n_entities=("entity_id", "nunique"))
    print(cov.to_string())

    from domains.tennis.profiles.attribute_registry import blocked_attributes, concrete_attributes  # noqa: PLC0415
    n_pairs = combined[["attribute", "window"]].drop_duplicates().shape[0]
    print(f"registry-key attributes={len(concrete_attributes())} distinct (attribute,window) pairs={n_pairs}")
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
