"""NBA canonical shooter leaderboard claims producer (one-conclusion-composer wave).

Materializes the naive-composite shooter ranking as a validated CLAIM. Today
this ranking exists only inside the predictive-validity gate verdict
(data/domains/basketball_nba/quality_validity_gate_verdict.json,
verdict=REJECT_NAIVE_STAYS_CANONICAL, mean_rho_naive=0.4044 vs
mean_rho_shooter_quality_v1=0.2680) -- the gate never emits a ranking claim
for the WINNING side, only the verdict comparing the two. This module closes
that gap: the naive composite is the canonical prediction-grade leaderboard
per the gate's binding honest-null clause, so it deserves its own
independently-recomputable ranking claim, not just a verdict citation.

NAIVE_WEIGHTS (0.55*TS%+0.30*eFG%+0.15*FT%) is imported from
domains.basketball_nba.quality_indices -- the single source of truth also
used by quality_validity_gate.py's _agg_pre_t(). Never re-typed here.

Same qualifying population as every other quality-index claim in this lane:
season 2024-25, games>=20 AND fga>=200 (domains.basketball_nba.quality_indices
QUALIFY_MIN_GAMES/QUALIFY_MIN_FGA/QUALIFY_SEASON), same source parquets
(player_boxscores.parquet -- naive_comp needs no atlas join at all).

CONTRACT: kind="ranking", entity_key="player_id", ROW-WISE (non-aggregate)
formula path -- naive_comp is a per-player linear combination of columns
already on load_qualifying_factor_table()'s output, so claims_validator.py's
plain evaluate_formula() (safe_formula.py: + - * / () only) recomputes it
directly with zero groupby/aggregate machinery, unlike the fit_sweep sibling.

NETWORK: zero. Pure pandas over player_boxscores.parquet.

CLI:
    python -m scripts.platformkit.intel_validation.nba_canonical_shooter_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.basketball_nba.quality_claim_builders import rank_of
from domains.basketball_nba.quality_indices import (
    NAIVE_WEIGHTS,
    QUALIFY_MIN_FGA,
    QUALIFY_MIN_GAMES,
    QUALIFY_SEASON,
    aggregate_season,
    load_boxscores,
    load_qualifying_factor_table,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_SNAPSHOT_PATH = _OUT_DIR / "nba_canonical_shooter_snapshot.parquet"
_CLAIMS_OUT = _OUT_DIR / "nba_canonical_shooter_claims.jsonl"

_VERDICT_FILE = "data/domains/basketball_nba/quality_validity_gate_verdict.json"
_SNAPSHOT_COLS = ["player_id", "player_name", "games", "fga", "fg3m", "fg3a", "ts_pct", "efg_pct", "ft_pct"]


def _build_formula() -> str:
    """Row-wise algebraic formula string, identical to
    quality_indices.aggregate_season()'s naive_comp computation and to
    quality_validity_gate._agg_pre_t()'s per-cutoff naive_comp -- same
    NAIVE_WEIGHTS import, never fresh literals."""
    return (
        f"{NAIVE_WEIGHTS['ts_pct']}*ts_pct + {NAIVE_WEIGHTS['efg_pct']}*efg_pct "
        f"+ {NAIVE_WEIGHTS['ft_pct']}*ft_pct"
    )


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)


def _attach_fg3m(t: pd.DataFrame, season: str) -> pd.DataFrame:
    """load_qualifying_factor_table()'s output already carries fg3a but drops
    fg3m at its build_factor_table() column-select (quality_indices.py is
    domains/** and out of this task's edit rails) -- so fg3m is joined back in
    here from the SAME season boxscore aggregate (load_boxscores +
    aggregate_season, both already the single source of truth this module
    imports for everything else), keyed on player_id. Additive column only:
    ranking order/values/floors are untouched.

    aggregate_season groups by (player_id, player_name): a handful of 2025-26
    box rows carry a mojibake-corrupted name variant for the same player_id
    (e.g. "Luka Doncic" vs "Luka Don?i?"), which would otherwise split one
    player into two agg rows and break the player_id->fg3m map (duplicate
    index). Group by player_id alone here so every variant's fg3m is summed
    under the one real player -- ponytail: the name-corruption itself is an
    ESPN-ingest encoding bug in domains/basketball_nba/ (human-gated, out of
    this file's edit rails), not fixed here; this local sum only prevents this
    additive fg3m join from undercounting or crashing on it."""
    agg = aggregate_season(load_boxscores(), season=season)
    fg3m_by_player = agg.groupby("player_id")["fg3m"].sum()
    out = t.copy()
    out["fg3m"] = out["player_id"].map(fg3m_by_player).fillna(0).astype(int)
    return out


def build_canonical_shooter_claim(season: str = QUALIFY_SEASON) -> dict[str, Any]:
    """Build the snapshot parquet + the single full-ordered-ranking claim.

    Full ranking (not top-10 only, per task spec) over the same 329-qualifier
    (games>=20, fga>=200) pool every sibling quality claim in this lane uses.
    """
    t = load_qualifying_factor_table(season=season)
    t = _attach_fg3m(t, season)
    # season-scoped snapshot filename: two seasons of this claim (e.g. the
    # 2024-25 default store + the 2025-26 sibling) must NOT share one on-disk
    # snapshot, or running the second season silently clobbers the first
    # season's re-validation source (claims_validator recomputes from
    # source_files, so a stale/wrong-season snapshot breaks it).
    season_id = season.replace("-", "_")
    snapshot_path = _SNAPSHOT_PATH.with_name(f"nba_canonical_shooter_snapshot_{season_id}.parquet")
    _write_parquet(t[_SNAPSHOT_COLS].copy(), snapshot_path)

    ranked = t.sort_values("naive_comp", ascending=False, na_position="last").reset_index(drop=True)
    n_considered = int(len(t))
    n_valid = int(ranked["naive_comp"].notna().sum())
    n_excluded_below_floor = n_considered - n_valid  # naive_comp NaN -> failed a floor upstream, never ranked

    ranking = [
        {
            "rank": i + 1,
            "player_id": int(row["player_id"]),
            "player_name": row["player_name"],
            "value": round(float(row["naive_comp"]), 4),
            "n": int(row["games"]),
            "fg3m": int(row["fg3m"]),
            "fg3a": int(row["fg3a"]),
        }
        for i, row in ranked.iterrows()
        if pd.notna(row["naive_comp"])
    ]
    top_name = ranking[0]["player_name"] if ranking else None

    curry_rank = rank_of(t, "naive_comp", "Stephen Curry")
    ellis_rank = rank_of(t, "naive_comp", "Keon Ellis")

    rel_source = str(snapshot_path.relative_to(REPO_ROOT)).replace("\\", "/")
    claim = {
        "claim_id": f"nba_canonical_shooter_leaderboard_full_season_{season_id}",
        "kind": "ranking",
        "question": (
            f"Who is the canonical NBA shooter leaderboard (naive composite, "
            f"full season {season}) -- top name explicit?"
        ),
        "criteria": {
            "metric": "naive_comp",
            "formula": _build_formula(),
            "weights": dict(NAIVE_WEIGHTS),
            "floors": {"min_games": QUALIFY_MIN_GAMES, "min_fga": QUALIFY_MIN_FGA},
            "min_sample": {"games": QUALIFY_MIN_GAMES, "fga": QUALIFY_MIN_FGA},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
            # window: real single-season vintage this claim was aggregated
            # over (season arg, e.g. "2024-25") -- resolves via
            # intel_weighting.claim_features.window_to_season(style="split")
            # so the relevance gate can use this as a prior-season feature
            # instead of being permanently UNTESTABLE on an unlabeled window.
            "window": season,
        },
        "ranking": ranking,
        "top_name": top_name,
        "face_validity_diagnostic": {
            "type": "reported_never_a_fitting_target",
            "stephen_curry_rank": curry_rank,
            "keon_ellis_rank": ellis_rank,
            "n_qualifying": n_considered,
            "top_decile_cutoff_rank": max(1, n_considered // 10),
        },
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded_below_floor,
        "edge_claimed": False,
        "caveats": [
            "DESCRIPTIVE-CANONICAL-BY-GATE-VERDICT: this ranking is canonical for "
            "prediction-grade purposes ONLY because the pre-registered walk-forward "
            f"gate returned REJECT_NAIVE_STAYS_CANONICAL (cite {_VERDICT_FILE}: "
            "mean_rho_naive=0.4044 beat mean_rho_shooter_quality_v1=0.2680 "
            "out-of-sample, bootstrap delta CI=[-0.2198,-0.0566], sign held 0/3 folds "
            "in the richer index's favor). REJECT is a recorded SUCCESS, not a "
            "failure -- the naive composite wins by not losing, it is not itself "
            "validated as predictive; see that verdict file for the full comparison.",
            "NAIVE-METRICS-DO-NOT-CAPTURE-DIFFICULTY/GRAVITY: TS%/eFG%/FT% carry no "
            "shot-difficulty or gravity signal, so this leaderboard systematically "
            "favors low-difficulty, high-efficiency finishers over high-difficulty, "
            "high-gravity shot creators. Concretely on this pool: Stephen Curry ranks "
            f"#{curry_rank}/{n_considered} while Keon Ellis (a low-usage catch-and-shoot "
            f"role player) ranks #{ellis_rank}/{n_considered} -- naive TS%/eFG%/FT% "
            "cannot see that Curry's shots are vastly harder to create/defend than "
            "Ellis's, because difficulty/gravity are not in the formula at all. This "
            "is the exact known limitation, not an incidental artifact.",
            "FACE-VALIDITY NOTE (from the sibling quality claims, nba_quality_claims.jsonl): "
            "the same Curry/Ellis diagnostic is reported there as "
            "'reported_never_a_fitting_target' for shooter_quality_v1/scorer_quality_v1 "
            "too -- neither index was tuned to place Curry or Ellis at any particular "
            "rank; the diagnostic is descriptive evidence, never an optimization target.",
            "SCOPE: naive_comp needs no atlas join (TS%/eFG%/FT% are boxscore-only "
            "rate stats), so this claim's qualifying population and source parquet "
            "are built the same way as every sibling quality-index claim in this "
            f"lane (load_qualifying_factor_table, season {season}, games>="
            f"{QUALIFY_MIN_GAMES} AND fga>={QUALIFY_MIN_FGA}, {n_considered} "
            f"qualifiers, {n_excluded_below_floor} with a NaN naive_comp).",
        ],
    }
    return claim


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


# Emitted seasons when --season is not given: 2024-25 (unchanged/byte-stable,
# no atlas ingredient used here -- naive_comp is boxscore-only) + 2025-26
# (boxscores.parquet now covers the full season, additive row in the SAME
# store, 2024-25 row untouched).
DEFAULT_SEASONS = (QUALIFY_SEASON, "2025-26")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA canonical shooter leaderboard ranking claim(s)")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    parser.add_argument("--season", type=str, default=None, help="single season override; default emits both DEFAULT_SEASONS")
    args = parser.parse_args(argv)

    seasons = [args.season] if args.season else list(DEFAULT_SEASONS)
    claims = [build_canonical_shooter_claim(s) for s in seasons]
    out_path = write_claims(claims, Path(args.output))

    for claim in claims:
        print(
            f"{claim['claim_id']}: top_name={claim['top_name']!r} "
            f"n_considered={claim['n_considered']} n_excluded_below_floor={claim['n_excluded_below_floor']}"
        )
        for r in claim["ranking"][:5]:
            print(f"  #{r['rank']} {r['player_name']} value={r['value']}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
