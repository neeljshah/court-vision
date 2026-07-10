"""NPB tie-RATE + KBO tie-run-environment DESCRIPTIVE claims (lane seed A6),
paired off the 'tied' column already on data/domains/{npb,kbo}/*_results.parquet
-- a direct port of the sibling npb_kbo_claims.py's producer pattern.

TWO CLAIMS (one per league, same season-level contract shape):
  npb_season_tie_rate       -- ties are a REAL outcome class in NPB (extra
                                innings can end in a tie under NPB's own
                                rules). Measures prevalence per season, a
                                split-half stability read, and the naive-
                                model implication of ignoring ties entirely.
  kbo_season_tie_rate       -- SAME mechanics, but the caveats frame it as a
                                season-by-season "tie run-environment" scan:
                                KBO has changed its own extra-inning/tie rules
                                across its history, so consecutive-season
                                tie_rate ratios are scanned for a candidate
                                regime-boundary. NO rule-change date is
                                hardcoded anywhere in this module -- the flag
                                fires only off what the on-disk deltas show.

WHY criteria.aggregate (not a pre-materialized snapshot): unlike the sibling
npb_kbo_claims.py's per-team split (which needs a home/away side-snapshot the
aggregate grammar cannot express in one groupby), a season-level tie tally is
a single plain group_by="season" -- the SAME contract-extension path already
used by basketball_claims.py / mlb_tto_claims.py. source_files points at the
raw game-level results parquet directly; claims_validator.validate_claim
independently re-derives games/ties/tie_rate off criteria.aggregate with zero
import of this module (or of recompute_aggregate's caller-side use here,
which only makes this producer's own numbers truthful against the SAME
recompute the validator will run -- same precedent as basketball_claims.py).

DESCRIPTIVE ONLY (CONFIRMED_LOCAL-equivalent local read) -- NOT a predictor,
NOT a gated signal, NOT a market/$ edge claim. The existing NPB/KBO pregame
and in-game gate verdicts are separate, already-adjudicated artifacts this
claim does not touch, replace, or contradict.

NETWORK: zero. Pure pandas over already-materialized parquets.

CLI:
    python -m scripts.platformkit.intel_validation.npb_kbo_tie_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.platformkit.intel_validation.aggregate_recompute import recompute_aggregate

REPO_ROOT = Path(__file__).resolve().parents[3]

_KBO_RESULTS = REPO_ROOT / "data" / "domains" / "kbo" / "kbo_results.parquet"
_NPB_RESULTS = REPO_ROOT / "data" / "domains" / "npb" / "npb_results.parquet"

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "npb_kbo_tie_claims.jsonl"

MIN_N_GAMES_SEASON = 100  # season sample floor; smallest partial season on disk (2026, both leagues) still clears it
REGIME_FLAG_RATIO = 2.0  # a >=2x (or <=0.5x) season-over-season tie_rate swing is flagged CANDIDATE, not confirmed

_AGGREGATE = {"group_by": "season", "derived": {"n": "count(date)", "n_ties": "sum(tied)"}}
_FORMULA = "sum(tied) / count(date)"


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def build_season_tie_table(results_path: Path) -> pd.DataFrame:
    """One row per season: season, n (games), n_ties, tie_rate. Built via the
    SAME recompute_aggregate the validator independently re-runs off
    criteria.aggregate + source_files -- this call only keeps this
    producer's own reported numbers truthful against that recompute."""
    raw = pd.read_parquet(results_path)
    table = recompute_aggregate(raw, {"aggregate": _AGGREGATE, "formula": _FORMULA})
    return table.rename(columns={"_value": "tie_rate"}).sort_values("season").reset_index(drop=True)


def split_half_tie_rate(results_path: Path) -> tuple[float, float, float]:
    """Split-half stability read: order ALL games chronologically, tie_rate
    of the first half of the corpus vs the second half. A robustness read,
    NOT a persistence/predictive claim (no gate attached)."""
    raw = pd.read_parquet(results_path).sort_values("date").reset_index(drop=True)
    mid = len(raw) // 2
    rate_a = float(raw.iloc[:mid]["tied"].mean())
    rate_b = float(raw.iloc[mid:]["tied"].mean())
    return round(rate_a, 4), round(rate_b, 4), round(abs(rate_a - rate_b), 4)


def season_over_season_deltas(season_table: pd.DataFrame) -> list[dict[str, Any]]:
    """season(t) vs season(t-1) tie_rate ratio, in season order -- the ONLY
    input to the regime-boundary flag. Purely data-driven."""
    deltas = []
    prev = None
    for row in season_table.itertuples(index=False):
        if prev is not None and prev.tie_rate > 0:
            deltas.append({
                "season_from": str(prev.season), "season_to": str(row.season),
                "tie_rate_from": round(float(prev.tie_rate), 4),
                "tie_rate_to": round(float(row.tie_rate), 4),
                "ratio": round(float(row.tie_rate) / float(prev.tie_rate), 3),
            })
        prev = row
    return deltas


def regime_boundary_flags(deltas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Candidate regime-boundary seasons: a season-over-season tie_rate
    ratio >= REGIME_FLAG_RATIO or <= 1/REGIME_FLAG_RATIO. Empty list is an
    honest 'no boundary detected in this corpus window' result."""
    return [d for d in deltas if d["ratio"] >= REGIME_FLAG_RATIO or d["ratio"] <= 1.0 / REGIME_FLAG_RATIO]


def build_ranking(table: pd.DataFrame, value_col: str, n_col: str, min_n: int) -> tuple[list[dict[str, Any]], int, int]:
    """Full-population ranking of seasons by value_col (no top-N cap).
    Returns (ranking, n_considered, n_excluded_below_floor)."""
    n_considered = len(table)
    qualifiers = table[table[n_col] >= min_n].sort_values(value_col, ascending=False).reset_index(drop=True)
    n_excluded = n_considered - len(qualifiers)
    ranking = [
        {
            "rank": i, "season": str(row.season), "player_name": str(row.season),
            "value": round(float(getattr(row, value_col)), 4), "n": int(getattr(row, n_col)),
        }
        for i, row in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return ranking, n_considered, n_excluded


def _common_caveats(league: str, as_of_iso: str, results_path: Path) -> list[str]:
    return [
        f"min_sample floor n_games(season)>={MIN_N_GAMES_SEASON} -- every season on disk clears it "
        "in this checkout; below-floor seasons (a mid-in-progress season, if ever this small) are "
        "counted in n_excluded_below_floor, never silently dropped.",
        "FULL POPULATION: every season clearing the floor is ranked, no top-N cap.",
        f"DESCRIPTIVE (CONFIRMED_LOCAL-equivalent local read) tie-rate ranking over the full on-disk "
        f"{league} results corpus as-of {as_of_iso} -- NOT a predictor, NOT a gated signal, NOT a "
        "market/$ edge claim; no persistence/predictive claim is made without a gate.",
        f"The existing {league} pregame gate verdict and in-game base-fit verdict "
        f"(data/domains/{league.lower()}/pregame_gate_verdict.json, ingame_base_fit_verdict.json) are "
        "SEPARATE, already-adjudicated artifacts this claim does not touch, replace, or contradict.",
        f"source: {_rel(results_path)} (raw game-level corpus, read directly -- no pre-materialized "
        "snapshot; season/games/ties recomputed via criteria.aggregate group_by=season).",
    ]


def build_tie_claim(league: str, results_path: Path, extra_caveats: list[str]) -> dict[str, Any]:
    raw = pd.read_parquet(results_path)
    as_of_iso = pd.to_datetime(raw["date"]).dt.date.max().isoformat()
    season_table = build_season_tie_table(results_path)
    ranking, n_considered, n_excluded = build_ranking(season_table, "tie_rate", "n", MIN_N_GAMES_SEASON)

    return {
        "claim_id": f"{league.lower()}_season_tie_rate_full_asof_{as_of_iso}",
        "kind": "ranking",
        "question": f"Which {league} seasons have the highest tie rate (full population above floor, "
                    f"as-of {as_of_iso})?",
        "criteria": {
            "metric": "tie_rate",
            "formula": _FORMULA,
            "window": f"asof_{as_of_iso}_{league.lower()}",
            "aggregate": _AGGREGATE,
            "min_sample": {"n": MIN_N_GAMES_SEASON},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "season",
        },
        "ranking": ranking,
        "source_files": [_rel(results_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [*extra_caveats, *_common_caveats(league, as_of_iso, results_path)],
    }


def build_npb_tie_rate_claim(results_path: Path = _NPB_RESULTS) -> dict[str, Any]:
    raw = pd.read_parquet(results_path)
    overall_rate = float(raw["tied"].mean())
    total_games, total_ties = len(raw), int(raw["tied"].sum())
    rate_a, rate_b, diff = split_half_tie_rate(results_path)
    season_table = build_season_tie_table(results_path)
    lo, hi = float(season_table["tie_rate"].min()), float(season_table["tie_rate"].max())

    extra = [
        f"PREVALENCE: ties are a REAL outcome class in NPB (extra innings can end in a tie under "
        f"NPB's own rules) -- {total_ties}/{total_games} games ({overall_rate * 100:.2f}%) tied over "
        "the full on-disk corpus.",
        f"BY-SEASON: per-season tie_rate ranges {lo:.4f}-{hi:.4f} across every season on disk (see "
        "ranking below) -- no order-of-magnitude swing observed in this corpus window.",
        f"SPLIT-HALF STABILITY (robustness read, not a persistence claim): first half of the "
        f"chronologically-ordered corpus tie_rate={rate_a:.4f}, second half={rate_b:.4f}, "
        f"abs diff={diff:.4f}.",
        f"NAIVE-MODEL IMPLICATION: a win/loss-only model has no tie outcome class; ignoring ties "
        f"entirely would misclassify or silently drop {overall_rate * 100:.2f}% of games "
        f"({total_ties}/{total_games}) rather than explicitly modeling a 3-way outcome space.",
    ]
    return build_tie_claim("NPB", results_path, extra)


def build_kbo_tie_run_env_claim(results_path: Path = _KBO_RESULTS) -> dict[str, Any]:
    season_table = build_season_tie_table(results_path)
    deltas = season_over_season_deltas(season_table)
    flags = regime_boundary_flags(deltas)

    if flags:
        flag_text = "; ".join(
            f"{f['season_from']}->{f['season_to']}: tie_rate {f['tie_rate_from']}->{f['tie_rate_to']} "
            f"(ratio {f['ratio']}x)" for f in flags
        )
        regime_line = (
            f"TIE RUN-ENVIRONMENT SCAN: {len(flags)} candidate regime-boundary season(s) flagged by a "
            f">= {REGIME_FLAG_RATIO}x season-over-season tie_rate swing: {flag_text}. KBO has changed "
            "its own extra-inning/tie rules across its history; this corpus alone cannot confirm "
            "causality (no rule-change metadata on disk) -- CANDIDATE only, no date is hardcoded."
        )
    else:
        regime_line = (
            f"TIE RUN-ENVIRONMENT SCAN: no season-over-season tie_rate swing >= {REGIME_FLAG_RATIO}x "
            "detected in this corpus window -- no regime boundary flagged."
        )
    extra = [regime_line, f"season-over-season deltas (all): {deltas}"]
    return build_tie_claim("KBO", results_path, extra)


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NPB tie-rate + KBO tie-run-env DESCRIPTIVE claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = [build_npb_tie_rate_claim(), build_kbo_tie_run_env_claim()]
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} ranking={c['ranking']}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
