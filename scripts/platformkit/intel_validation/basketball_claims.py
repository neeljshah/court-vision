"""NBA full-population descriptive claims producer (LANE nba-fullpop).

The NBA had NO claims module before this build. Emits one ranking claim per
buildable dimension in docs/research/intel-layer/basketball_truth_spec.json,
SAME contract shape as tennis_hold_claims.py / platoon_split_claims.py, so
claims_validator.py can VERIFY every row independently.

GOAL: full population, not top-N sampling. The FLOOR applies to the WHOLE
qualifying population -- "where does LeBron rank on X" is answerable for
every one of the 329 (2024-25 n_games>=20 AND fga_sum>=200) qualifying
players who ALSO clear that dimension's own per-source floor; EVERY
qualifying player above that floor is RANKED (no top-N cap -- lane
nba-uncap-settle removed a prior TOP_N=50 truncation at two head(TOP_N)
call sites, mirroring the mlb_tto_claims.py full-population precedent).
n_considered/n_excluded_below_floor cover the full population; below-floor
players are counted honestly, never silently dropped. claim_id strings
retain their historical `_top50_` token unchanged -- stable identifiers
consumed verbatim by dossier_registry.py's CLAIM_ID_TO_FILE registry; only
the ranked population changed, not the id.

TWO CLAIM SHAPES: (1) boxscore aggregate dims (ts_pct/efg_pct/fga_per_game/
fg3a_per_game) via the validator's criteria.aggregate group-by path off
player_boxscores.parquet (like catcher_framing_claims.py); (2) atlas
per-player dims (usage_rate, gravity_score, ...), already one row per
player, via the plain formula path over a FLATTENED snapshot (like
tennis_hold_claims.py's wide->long reshape) -- basketball_claims_dims.py
extracts every nested struct leaf the spec names into its own column.
DIMENSIONS WITH NO CORPUS ON DISK: none -- all 12 atlas_player_*.parquet +
player_boxscores confirmed present. Absent: DEFER-stub LEAF fields inside
an otherwise-present source (shot_clock early/mid, gravity_radius, ft
streak/pressure/home-road), reported via counts.dims_corpus_absent.
CONCURRENCY: atlas dims build via ThreadPoolExecutor; every snapshot write
goes through basketball_claims_io.atomic_write_parquet (temp file +
os.replace) so a reader can never observe a truncated parquet footer.

LEAK DISCIPLINE: purely descriptive/retrospective -- no forecasting claim.
NETWORK: zero. DESCRIPTIVE/SCOUTING ONLY -- NO MARKET/$ EDGE CLAIMED.

CLI:
    python -m scripts.platformkit.intel_validation.basketball_claims
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa

from scripts.platformkit.intel_validation import basketball_claims_dims as dims
from scripts.platformkit.intel_validation.aggregate_recompute import recompute_aggregate
from scripts.platformkit.intel_validation.basketball_claims_io import atomic_write_parquet
from scripts.platformkit.intel_validation.claims_validator import validate_claim

REPO_ROOT = Path(__file__).resolve().parents[3]

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "nba_shooting_claims.jsonl"
_BOXSCORE_SNAPSHOT_OUT = _OUT_DIR / "nba_boxscore_agg_snapshot.parquet"

SEASON_WINDOW = dims.SEASON


def build_boxscore_snapshot() -> tuple[Path, pd.DataFrame]:
    """Raw per-player-per-game boxscore rows for the qualifying population;
    the validator's criteria.aggregate path recomputes ts_pct/efg_pct/
    fga_per_game/fg3a_per_game from THESE rows via sum()/count() (same
    mechanics as catcher_framing_claims.py's aggregate path)."""
    pop = dims.qualifying_population()
    box = pd.read_parquet(
        dims._BOXSCORES,
        columns=["player_id", "game_id", "season", "pts", "fga", "fgm", "fg3m", "fg3a", "fta"],
    )
    season_rows = box[box["season"] == SEASON_WINDOW]
    restricted = season_rows[season_rows["player_id"].isin(set(pop["player_id"]))].copy()
    write_cols = restricted[["player_id", "game_id", "pts", "fga", "fgm", "fg3m", "fg3a", "fta"]]
    atomic_write_parquet(pa.Table.from_pandas(write_cols, preserve_index=False), _BOXSCORE_SNAPSHOT_OUT)
    return _BOXSCORE_SNAPSHOT_OUT, pop


# metric -> (formula, question, caveat). Row-wise sum() then divide (not an
# average of per-game ratios) -- matches the spec's derived formula exactly.
_BOXSCORE_AGG_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ("ts_pct", "sum(pts) / (2 * (sum(fga) + 0.44 * sum(fta)))",
     "Which qualifying NBA players have the highest true shooting % (2024-25)?",
     "ts_pct = pts / (2*(fga + 0.44*fta)), summed over the season then divided."),
    ("efg_pct", "(sum(fgm) + 0.5 * sum(fg3m)) / sum(fga)",
     "Which qualifying NBA players have the highest effective FG% (2024-25)?",
     "efg_pct = (fgm + 0.5*fg3m) / fga, summed over the season then divided."),
    ("fga_per_game", "sum(fga) / count(game_id)",
     "Which qualifying NBA players attempt the most field goals per game (2024-25)?",
     "fga_per_game = season fga_sum / n_games played."),
    ("fg3a_per_game", "sum(fg3a) / count(game_id)",
     "Which qualifying NBA players attempt the most 3-pointers per game (2024-25)?",
     "fg3a_per_game = season fg3a_sum / n_games played."),
)
_BOXSCORE_AGG_DEFS: dict[str, dict[str, str]] = {
    metric: {"formula": formula, "question": question, "caveat": caveat}
    for metric, formula, question, caveat in _BOXSCORE_AGG_ROWS
}


def build_boxscore_aggregate_claim(metric: str) -> dict[str, Any]:
    out_path, pop = build_boxscore_snapshot()
    raw = pd.read_parquet(out_path)
    names = dims.name_lookup()

    defn = _BOXSCORE_AGG_DEFS[metric]
    agg_spec = {
        "group_by": "player_id",
        "derived": {
            "n_games": "count(game_id)",
            "fga_sum": "sum(fga)",
            "fta_sum": "sum(fta)",
        },
    }
    criteria = {
        "metric": metric,
        "formula": defn["formula"],
        "window": f"season_{SEASON_WINDOW}_nba",
        "window_spec": None,
        "aggregate": agg_spec,
        "min_sample": {"n_games": dims.POP_MIN_GAMES, "fga_sum": dims.POP_MIN_FGA},
        "direction": "desc",
        "value_precision": 4,
        "entity_key": "player_id",
    }
    # recompute here so this producer's own ranking/n_considered/n_excluded
    # are truthful against the SAME snapshot the validator will re-derive.
    table = recompute_aggregate(raw, criteria)
    n_considered = len(table)
    qualifiers = table[
        (table["n_games"] >= dims.POP_MIN_GAMES) & (table["fga_sum"] >= dims.POP_MIN_FGA)
    ].copy()
    n_excluded = n_considered - len(qualifiers)
    ascending = criteria["direction"] == "asc"
    qualifiers = qualifiers.sort_values("_value", ascending=ascending).reset_index(drop=True)
    # itertuples mangles "_value" -> "_1" positionally; rename first.
    qualifiers = qualifiers.rename(columns={"_value": "metric_value"})

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        pid = int(row.player_id)
        ranking.append({
            "rank": i,
            "player_id": pid,
            "player_name": names.get(pid, "Unknown"),
            "value": round(float(row.metric_value), 4),
            "n": int(row.n_games),
        })

    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"nba_{metric}_top50_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": defn["question"],
        "criteria": criteria,
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            defn["caveat"],
            f"min_sample floor: n_games>={dims.POP_MIN_GAMES} AND fga_sum>={dims.POP_MIN_FGA} "
            f"({len(qualifiers)}/{n_considered} players qualify) -- the frozen "
            "qualifying_population gate from basketball_truth_spec.json.",
            f"FULL POPULATION: all {len(qualifiers)} qualifying players clearing the floor "
            "are ranked here (no top-N truncation) -- below-floor players honestly counted "
            "in n_excluded_below_floor, never silently dropped.",
            "DESCRIPTIVE ranking only -- no forecasting/market/$ edge claimed.",
        ],
    }


def build_atlas_dim_claim(spec: dims.DimSpec) -> dict[str, Any] | None:
    """Build one ranking claim for an atlas per-player dimension. Returns
    None if the source parquet has zero rows for the qualifying population
    (an honest empty corpus, reported via dims_corpus_absent by the caller,
    never silently fabricated)."""
    pop = dims.qualifying_population()
    pop_ids = set(pop["player_id"])
    extracted = spec.extractor(pop_ids)
    if extracted.empty:
        return None
    names = dims.name_lookup()

    snapshot_path = _OUT_DIR / f"nba_{spec.name}_snapshot.parquet"
    cols = ["player_id", spec.metric_col, spec.floor_col]
    write_cols = extracted[cols].dropna(subset=[spec.metric_col])
    atomic_write_parquet(pa.Table.from_pandas(write_cols, preserve_index=False), snapshot_path)

    n_considered = len(write_cols)
    qualifiers = write_cols[write_cols[spec.floor_col] >= spec.floor_value].copy()
    n_excluded = n_considered - len(qualifiers)
    ascending = spec.direction == "asc"
    qualifiers = qualifiers.sort_values(spec.metric_col, ascending=ascending).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        pid = int(row.player_id)
        ranking.append({
            "rank": i,
            "player_id": pid,
            "player_name": names.get(pid, "Unknown"),
            "value": round(float(getattr(row, spec.metric_col)), 4),
            "n": int(getattr(row, spec.floor_col)),
        })

    rel_source = str(snapshot_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"nba_{spec.name}_top50_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": spec.question,
        "criteria": {
            "metric": spec.metric_col,
            "formula": spec.metric_col,
            "window": f"season_{SEASON_WINDOW}_nba",
            "window_spec": None,
            "aggregate": None,
            "min_sample": {spec.floor_col: spec.floor_value},
            "direction": spec.direction,
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            spec.caveat,
            f"population gate: 2024-25 n_games>=20 AND fga_sum>=200 (329 qualifying per "
            f"basketball_truth_spec.json), further restricted by min_sample floor "
            f"{spec.floor_col}>={spec.floor_value} ({len(qualifiers)}/{n_considered} qualify).",
            f"FULL POPULATION: all {len(qualifiers)} qualifying players clearing the floor "
            "are ranked here (no top-N truncation) -- below-floor players honestly counted "
            "in n_excluded_below_floor, never silently dropped.",
            "DESCRIPTIVE ranking only -- no forecasting/market/$ edge claimed.",
        ],
    }


def build_all_claims() -> tuple[list[dict[str, Any]], list[str]]:
    """Build every buildable dimension's claim. Boxscore dims run
    sequentially (share one snapshot build); atlas dims run concurrently
    via ThreadPoolExecutor since each does its own parquet read +
    json.loads flatten pass (IO-bound, safe to parallelize)."""
    claims: list[dict[str, Any]] = [
        build_boxscore_aggregate_claim(m) for m in dims.BOXSCORE_AGGREGATE_DIMS
    ]
    dims_corpus_absent: list[str] = list(dims.DIMS_DEFER_IN_SOURCE)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(build_atlas_dim_claim, spec): spec for spec in dims.DIM_SPECS}
        for fut in as_completed(futures):
            spec = futures[fut]
            result = fut.result()
            if result is None:
                dims_corpus_absent.append(f"{spec.name} (zero rows for qualifying population)")
            else:
                claims.append(result)

    # deterministic order -- ThreadPoolExecutor completion is not.
    claims.sort(key=lambda c: c["claim_id"])
    return claims, dims_corpus_absent


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA full-population descriptive ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims, dims_corpus_absent = build_all_claims()
    out_path = write_claims(claims, Path(args.output))

    n_validator_pass = 0
    n_validator_fail = 0
    for c in claims:
        verdict = validate_claim(c)
        status = "PASS" if verdict.verdict == "VERIFIED" else "FAIL"
        if status == "PASS":
            n_validator_pass += 1
        else:
            n_validator_fail += 1
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} "
              f"validator={status} ({verdict.reason})")
    print(f"dims_corpus_absent ({len(dims_corpus_absent)}): {dims_corpus_absent}")
    print(f"wrote {len(claims)} claims -> {out_path} "
          f"(validator_pass={n_validator_pass} validator_fail={n_validator_fail})")
    return 0 if n_validator_fail == 0 else 2


if __name__ == "__main__":
    import sys
    sys.exit(main())
