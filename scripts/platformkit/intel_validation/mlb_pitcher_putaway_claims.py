"""MLB pitcher PUTAWAY-SWINGING-SHARE ranking claims producer (matchup lane,
batter-vs-pitcher interaction build). Mirrors catcher_framing_claims.py's
structure: emit a FULL-POPULATION ranking claim (every pitcher clearing the
min_sample floor, no top-N truncation) in the SAME claims contract shape,
backed by domains/mlb/matchup/pitch_mix_profiles.py, zero code sharing with
the validator.

METRIC: putaway_swinging_rate = n_k_swinging / n_k -- of a pitcher's own
strikeouts (2022+2023 combined), what share end SWINGING vs LOOKING (from
statcast `des` free text on the PA-terminal pitch -- the only per-pitch
swing/take signal this corpus supports; see
domains/mlb/matchup/pitch_mix_profiles.py's CORPUS LIMIT docstring for the
full writeup: `type` S/B/X cannot separate called-from-swinging strikes, and
there is no per-pitch `description` column anywhere in this corpus). THIS IS
NOT A WHIFF RATE (whiff% = swings-and-misses / all swings, which needs
swing/take on every pitch, not just the PA-ender) -- it is a narrower,
CORPUS_ABSENT-safe proxy: among strikeouts a pitcher already recorded, how
many were the batter swinging through the pitch vs standing looking at a
called third strike. Real signal (a high-spin breaking-ball pitcher tends to
generate more swinging Ks than a control-fastball pitcher who catches the
corner), honestly scoped.

SOURCE: domains/mlb/matchup/pitch_mix_profiles.py's load_pitch_rows +
classify_terminal_k are re-invoked fresh here (not a stale read of that
module's own per-pitch-type parquet output) and re-aggregated to ONE row per
pitcher across ALL pitch types -- this producer's own aggregation, not an
import of build_pitcher_profile's per-pitch-type table.

WINDOW: seasons 2022+2023 (statcast_fuller__2022/2023.parquet, full seasons).
MIN-SAMPLE FLOOR: n_k (career strikeouts recorded in this window) >= 30 --
the metric's own denominator, damping small-sample noise on a binary
swinging/looking indicator while clearing a real population.

LEAK DISCIPLINE: purely descriptive/retrospective (a completed 2-season
statcast aggregate) -- no forecasting claim, no leak-risk window.
CLOSED-CLASS GUARD: descriptive putaway-style split only -- NOT a
predictor; the CLOSED sp_fatigue/velo-decline in-game class is untouched (no
pitch-count/fatigue feature here).

NETWORK: zero. Pure pandas over already-materialized parquets.
DESCRIPTIVE/SCOUTING ONLY -- NO MARKET/$ EDGE CLAIMED.

CLI:
    python -m scripts.platformkit.intel_validation.mlb_pitcher_putaway_claims
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

from domains.mlb.matchup.pitch_mix_profiles import SEASONS, classify_terminal_k, load_pitch_rows

REPO_ROOT = Path(__file__).resolve().parents[3]

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "mlb_pitcher_putaway_claims.jsonl"
_SNAPSHOT_OUT = _OUT_DIR / "mlb_pitcher_putaway_snapshot.parquet"

SEASON_WINDOW = "2022_2023"
MIN_N_K = 30  # floor on the metric's own denominator (career strikeouts, this window)


def build_snapshot() -> tuple[Path, dict]:
    rows = load_pitch_rows(seasons=SEASONS)
    rows = rows.copy()
    rows["k_class"] = classify_terminal_k(rows["des"], rows["events"])
    k_rows = rows[rows["k_class"].notna()]

    agg = k_rows.groupby("pitcher").agg(
        n_k=("k_class", "size"),
        n_k_swinging=("k_class", lambda s: (s == "swinging").sum()),
    ).reset_index().rename(columns={"pitcher": "pitcher_id"})

    n_considered = len(agg)
    n_qualifying = int((agg["n_k"] >= MIN_N_K).sum())
    report = {
        "component": "mlb_pitcher_putaway",
        "seasons": list(SEASONS),
        "n_pitchers_considered": n_considered,
        "n_pitchers_qualifying": n_qualifying,
        "min_n_k_floor": MIN_N_K,
    }

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_cols = agg[["pitcher_id", "n_k", "n_k_swinging"]].copy()
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), _SNAPSHOT_OUT)
    return _SNAPSHOT_OUT, report


def build_ranking_claim() -> dict[str, Any]:
    out_path, snap_report = build_snapshot()
    raw = pd.read_parquet(out_path)

    names = pd.read_parquet(
        REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet",
        columns=["player_id", "player"],
    )
    name_lookup = dict(
        names.drop_duplicates(subset=["player_id"], keep="last").set_index("player_id")["player"]
    )

    n_considered = len(raw)
    qualifiers = raw[raw["n_k"] >= MIN_N_K].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers["putaway_swinging_rate"] = qualifiers["n_k_swinging"] / qualifiers["n_k"]
    qualifiers = qualifiers.sort_values("putaway_swinging_rate", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        pid = int(row.pitcher_id)
        ranking.append({
            "rank": i,
            "pitcher_id": pid,
            "pitcher_name": str(name_lookup.get(pid, "Unknown")),
            "value": round(float(row.putaway_swinging_rate), 4),
            "n": int(row.n_k),
        })

    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"mlb_pitcher_putaway_swinging_rate_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": "Which MLB pitchers get the highest SWINGING share of "
                    f"their own strikeouts (vs looking, full qualifying "
                    f"population, seasons={SEASON_WINDOW})?",
        "criteria": {
            "metric": "putaway_swinging_rate",
            "formula": "sum(n_k_swinging) / sum(n_k)",
            "window": f"seasons_{SEASON_WINDOW}_mlb_pitcher_putaway",
            "window_spec": None,
            "aggregate": {
                "group_by": "pitcher_id",
                "derived": {
                    "n_k": "sum(n_k)",
                    "n_k_swinging": "sum(n_k_swinging)",
                },
            },
            "min_sample": {"n_k": MIN_N_K},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "pitcher_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "NOT A WHIFF RATE: this corpus has no per-pitch swing/take "
            "description column (see domains/mlb/matchup/pitch_mix_profiles.py "
            "CORPUS LIMIT docstring) -- putaway_swinging_rate is scoped to "
            "PA-terminal strikeouts only: of a pitcher's own strikeouts, what "
            "share end swinging (from `des` free text) vs looking.",
            f"putaway_swinging_rate = swinging strikeouts / all strikeouts, "
            f"seasons={SEASON_WINDOW} (data/cache/statcast/statcast_fuller__"
            "2022/2023.parquet).",
            f"min_sample floor: n_k >= {MIN_N_K} "
            f"({len(qualifiers)}/{n_considered} pitchers qualify).",
            f"FULL POPULATION: all {len(qualifiers)} pitchers clearing the "
            "floor are ranked here (no top-N truncation) -- below-floor "
            "pitchers honestly counted in n_excluded_below_floor.",
            "DESCRIPTIVE putaway-style split only -- NOT a validated predictor, "
            "no forecasting/market/$ edge claimed. CLOSED sp_fatigue/velo-"
            "decline in-game class untouched.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit MLB pitcher putaway-swinging-rate ranking claims")
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
