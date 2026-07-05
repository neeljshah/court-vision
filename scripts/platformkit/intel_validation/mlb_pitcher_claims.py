"""MLB starting/relief pitcher K-rate ranking claims producer (mission spine 5,
lane claims-breadth-2). Mirrors scripts/platformkit/intel_validation/
tennis_hold_claims.py's structure: emit a FULL-POPULATION ranking claim
(every pitcher clearing the min_sample floor, no top-N truncation -- see
mlb-fullpop lane) in the SAME claims contract shape, backed by a side parquet
the independent claims_validator.py re-derives the ranking from, zero code
sharing between producer and validator.

METRIC: k_rate = pitch_strikeOuts / battersFaced, aggregated over a single
season from data/domains/mlb/player_gamelogs.parquet's per-player-per-game
rows (is_pitcher==True rows only). This is a plain aggregate the validator's
criteria.aggregate grammar (sum()/sum() division) can recompute directly from
the raw per-game rows -- no pre-aggregation happens in this producer beyond
filtering to pitcher rows and stamping a season column (both mechanical,
inspectable in the side parquet itself).

WHY A SIDE PARQUET: player_gamelogs.parquet holds BOTH batting and pitching
columns for every roster player each game (batters have NaN pitching cols).
Writing a pitcher-only, season-stamped subset avoids the validator's
min_sample floor tripping over batter rows with NaN battersFaced, and keeps
the claim's source_files pointed at an artifact that is exactly the raw
input the aggregate grammar consumes (one row per pitcher per game).

WINDOW: season=2025 -- the last on-disk COMPLETE MLB season (2026 is
in-progress per data/domains/mlb/player_gamelogs.parquet's season counts).

MIN-SAMPLE FLOOR: battersFaced summed over the season >= 200 -- a plain,
stated, recomputable innings-floor proxy (roughly 45-50 IP), well above
single-relief-appearance noise, comfortably below a full qualifying-starter
threshold so the full-population ranking is dominated by real starters
without hand-picking a cutoff.

LEAK DISCIPLINE: purely descriptive/retrospective (a completed-season
box-score aggregate) -- no forecasting claim, no leak-risk window.

NETWORK: zero. Pure pandas over an already-materialized parquet.
ACCURACY ONLY -- NO MARKET EDGE CLAIMED.

CLI:
    python -m scripts.platformkit.intel_validation.mlb_pitcher_claims
"""
from __future__ import annotations

import argparse
import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[3]

_GAMELOGS = REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "mlb_pitcher_claims.jsonl"
_SNAPSHOT_OUT = _OUT_DIR / "mlb_pitcher_season_rows.parquet"

SEASON_WINDOW = "2025"  # last complete on-disk MLB season (verified: 2026 in-progress)
MIN_BATTERS_FACED = 200  # season-summed floor, ~45-50 IP proxy
# FULL-POPULATION FIX: every pitcher above the min_sample floor ships (no
# top-N truncation) -- below-floor pitchers are honestly counted in
# n_excluded_below_floor, never silently dropped. See mlb-fullpop lane.


def _ascii_fold(name: str) -> str:
    """Strip diacritics so player names survive ASCII-only JSON encoding
    (player_gamelogs.parquet carries genuine latin-1 mojibake, e.g. 'S�nchez')."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).encode(
        "ascii", "ignore"
    ).decode("ascii")


def build_pitcher_season_rows(season: str = SEASON_WINDOW) -> tuple[Path, pd.DataFrame]:
    """Filter player_gamelogs.parquet to pitcher rows, stamp a `season` column,
    write the raw per-pitcher-per-game rows the aggregate grammar consumes.
    Returns (parquet_path, name_lookup_df)."""
    df = pd.read_parquet(_GAMELOGS)
    df = df[df["is_pitcher"] == True].copy()  # noqa: E712 -- explicit bool compare, matches column dtype
    df["season"] = pd.to_datetime(df["date"]).dt.year.astype("int64")
    df = df[df["season"] == int(season)]
    df = df.dropna(subset=["battersFaced", "pitch_strikeOuts"])
    df["battersFaced"] = df["battersFaced"].astype("float64")
    df["pitch_strikeOuts"] = df["pitch_strikeOuts"].astype("float64")

    names = df[["player_id", "player"]].drop_duplicates(subset=["player_id"], keep="last")
    name_lookup = dict(zip(names["player_id"], names["player"]))

    write_cols = df[["player_id", "season", "battersFaced", "pitch_strikeOuts"]].copy()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), _SNAPSHOT_OUT)
    return _SNAPSHOT_OUT, pd.DataFrame({"player_id": list(name_lookup.keys()),
                                          "player_name": list(name_lookup.values())})


def build_ranking_claim() -> dict[str, Any]:
    out_path, name_df = build_pitcher_season_rows(SEASON_WINDOW)
    name_lookup = dict(zip(name_df["player_id"], name_df["player_name"]))

    raw = pd.read_parquet(out_path)
    grouped = raw.groupby("player_id").agg(
        bf=("battersFaced", "sum"), k=("pitch_strikeOuts", "sum")
    ).reset_index()
    n_considered = len(grouped)
    qualifiers = grouped[grouped["bf"] >= MIN_BATTERS_FACED].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers["k_rate"] = qualifiers["k"] / qualifiers["bf"]
    qualifiers = qualifiers.sort_values("k_rate", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        pid = int(row.player_id)
        ranking.append({
            "rank": i,
            "player_id": pid,
            "player_name": _ascii_fold(str(name_lookup.get(pid, "Unknown"))),
            "value": round(float(row.k_rate), 4),
            "n": int(row.bf),
        })

    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"mlb_pitcher_k_rate_top50_{SEASON_WINDOW}",  # claim_id kept stable (identifier, not a population statement)
        "kind": "ranking",
        "question": f"Which MLB pitchers have the best strikeout rate "
                    f"(full qualifying population, season={SEASON_WINDOW})?",
        "criteria": {
            "metric": "k_rate",
            "formula": "sum(pitch_strikeOuts) / sum(battersFaced)",
            "window": f"season_{SEASON_WINDOW}_mlb",
            "window_spec": {
                "kind": "season", "season_col": "season", "season": int(SEASON_WINDOW),
                "n": None, "order_by": None,
            },
            "aggregate": {
                "group_by": "player_id",
                "derived": {
                    "bf": "sum(battersFaced)",
                    "k": "sum(pitch_strikeOuts)",
                },
            },
            "min_sample": {"bf": MIN_BATTERS_FACED},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            f"k_rate = season-summed pitch_strikeOuts / season-summed battersFaced from "
            f"data/domains/mlb/player_gamelogs.parquet's per-pitcher-per-game rows, season="
            f"{SEASON_WINDOW} (the last on-disk COMPLETE MLB season).",
            f"min_sample floor: season batters-faced >= {MIN_BATTERS_FACED} (~45-50 IP proxy) "
            "-- a defensible floor against small-sample relief-appearance noise, not an "
            "official qualifying-starter (162-IP) threshold.",
            f"FULL POPULATION: all {len(qualifiers)} pitchers clearing the min_sample floor "
            "are ranked here (no top-N truncation) -- below-floor pitchers are honestly "
            "counted in n_excluded_below_floor, never silently dropped.",
            "DESCRIPTIVE season box-score aggregate only -- no forecasting/market/$ edge claimed.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit MLB pitcher K-rate ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = [build_ranking_claim()]
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} "
              f"top1={c['ranking'][0] if c['ranking'] else None}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
