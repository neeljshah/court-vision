"""Cross-season stability of the player-interaction effect sizes (the
"record how much" payoff): for pairwise gravity (efg_delta) and lineup
synergy (synergy_residual), joins the SAME entity (directed pair / 5-man
lineup) across every pair of the 3 seasons on disk and reports the plain
Pearson correlation of the effect between seasons.

WHY THIS MATTERS: a HIGH cross-season correlation means the effect is a
persistent trait of the entity (a real candidate prediction input); a
near-zero correlation means it is season-to-season noise -- report either
outcome honestly, a null is a finding, not a failure (see repo-wide
no-edge-claims rule: an honest null is a SUCCESS).

Same floor + negative-placeholder-id exclusion as
nba_player_interaction_claims.py (independent re-derivation here, not
imported, to keep this module's only import surface pandas -- same
precedent as the claims producers in this lane), applied to the FULL
qualifying population per season (NOT the top-50 claims subset -- a top-50
intersection across seasons is too small to correlate meaningfully; the
full floor-passing population is the right basis for this measurement).

Usage redistribution is NOT included here (task scope: pairwise gravity +
lineup synergy only) -- its "high-usage player" identity churns fastest of
the three (injuries/trades/role changes each season), so a cross-season
match on (player_id, team_id, teammate_id) would already be thin by
construction; left for a future pass if usage stability specifically is
asked for.

OUTPUT: data/cache/team_system/interaction_stability.json
  {metric: [{season_a, season_b, n_overlap, pearson_r}, ...]}

NETWORK: zero. CLI: python -m scripts.platformkit.intel_validation.nba_interaction_stability
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.platformkit.intel_validation.claims_validator import _json_numpy_default

REPO_ROOT = Path(__file__).resolve().parents[3]
_INTERACTIONS_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "interactions"
_OUT_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "interaction_stability.json"

SEASONS = ["2025_26", "2024_25", "2023_24"]
MIN_OVERLAP_FOR_CORR = 30  # below this, a pearson r estimate itself has too much variance to trust


def load_pairwise_qualifiers(season: str) -> pd.DataFrame:
    df = pd.read_parquet(_INTERACTIONS_DIR / f"pairwise_onoff_{season}.parquet")
    # min_together/min_x_without_y floor already baked in by the producer;
    # the negative-placeholder-id exclusion is the one still needed here.
    return df[(df["player_x"] >= 0) & (df["player_y"] >= 0) & df["efg_delta"].notna()]


def load_synergy_qualifiers(season: str) -> pd.DataFrame:
    df = pd.read_parquet(_INTERACTIONS_DIR / f"lineup_synergy_{season}.parquet")
    return df[(df["min"] >= 100.0) & df["synergy_residual"].notna() & (df["min_member_id"] >= 0)]


def stability_for_metric(
    frames: dict[str, pd.DataFrame], join_cols: list[str], metric: str,
) -> list[dict[str, Any]]:
    rows = []
    for a, b in itertools.combinations(SEASONS, 2):
        merged = frames[a].merge(frames[b], on=join_cols, suffixes=("_a", "_b"))
        n = len(merged)
        r = None
        if n >= MIN_OVERLAP_FOR_CORR:
            corr = merged[f"{metric}_a"].corr(merged[f"{metric}_b"])
            r = round(float(corr), 4) if corr == corr else None  # NaN -> None (e.g. zero variance)
        rows.append({
            "season_a": a, "season_b": b, "n_overlap": n,
            "pearson_r": r,
            "interpretable": n >= MIN_OVERLAP_FOR_CORR,
        })
    return rows


def build_summary() -> dict[str, Any]:
    pairwise_frames = {s: load_pairwise_qualifiers(s) for s in SEASONS}
    synergy_frames = {s: load_synergy_qualifiers(s) for s in SEASONS}
    return {
        "pairwise_gravity_efg_delta": stability_for_metric(
            pairwise_frames, ["team_id", "player_x", "player_y"], "efg_delta",
        ),
        "lineup_synergy_residual": stability_for_metric(
            synergy_frames, ["team_id", "lineup_key"], "synergy_residual",
        ),
        "min_overlap_for_corr": MIN_OVERLAP_FOR_CORR,
        "note": (
            "pearson_r=None with interpretable=false means n_overlap fell below "
            f"MIN_OVERLAP_FOR_CORR={MIN_OVERLAP_FOR_CORR} -- too few repeated entities "
            "across those two seasons to say anything, not a claim of zero correlation."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cross-season stability of NBA interaction effect sizes")
    parser.add_argument("--out", type=str, default=str(_OUT_PATH))
    args = parser.parse_args(argv)

    summary = build_summary()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=1, default=_json_numpy_default), encoding="ascii")

    for metric, rows in summary.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            print(
                f"{metric}: {row['season_a']} vs {row['season_b']} "
                f"n_overlap={row['n_overlap']} pearson_r={row['pearson_r']}"
            )
    print(f"-> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
