"""MLB batter home/away + rest-day split claims producer (family
mlb_batter_splits, spec_mlb.md Family 3). Mirrors platoon_split_claims.py's
PLAIN row-wise formula path (criteria.aggregate=None): the snapshot carries
raw per-cell SUMS (never a pre-divided rate), and criteria.formula is a
ratio-of-sums subtraction the validator re-derives directly -- zero code
sharing with claims_validator.py.

HOME/AWAY: player_gamelogs.parquet has no home/away flag -- derived by
joining game_pk -> home_team/away_team from the UNION of
savant_full__{2023,2024,2025,2026}.parquet + statcast_fuller__2022.parquet
(verified: 11,141 unique game_pk across the union, 99.78% of gamelog rows
match). team_norm applies ONE alias (OAK->ATH, the Athletics' relocation/
rename mid-corpus) before matching -- verified this alias resolves every
remaining team-code mismatch (7,210/321,012 rows recovered, 0 unresolved
after). Unmatched game_pk rows (missing game, ~0.22%) are honestly excluded,
never guessed.

REST BUCKET: rest_days = (calendar days since this player's own prior game)
- 1, clipped at 0 (a player who played on back-to-back calendar days has
rest_days=0; standard MLB "days rest" convention). b2b = rest_days==0,
rested = rest_days>=2 -- rest_days==1 is a DELIBERATE excluded middle gap
(matching mlb_batter_context_claims.py's velocity-gap precedent), not a
data omission.

5 metrics x 2 split axes = 10 delta claims, ALL ratio-of-sums (never a mean
of per-game rates, to avoid distorting games with 0 AB): hr_rate=HR/games,
rbi_rate=RBI/games, avg=hits/AB, k_rate=K/PA_approx, tb_per_pa=TB/PA_approx.
PA_approx = AB+BB+HBP (this box-score gamelog has no sac-fly/sac-bunt
columns, so it under-counts true PA slightly -- declared in every caveat).

min_sample floors: n_games >= 20 in EACH cell (a self-declared descriptive
floor, no spec number given -- verified 1,519/2,530 batters clear it on the
home/away axis, 649/2,447 on the rest axis on the real corpus), PLUS a
>= 1 zero-denominator guard on the metric's AB/PA denominator columns for
the avg/k_rate/tb_per_pa variants (real-corpus finding 2026-07-18: pitchers
clear the 20-games floor with zero AB/PA in a cell -- without the declared
guard the validator's row-wise recompute dies on float division by zero and
the producer would rank them as inf/NaN).

LEAK: purely descriptive/retrospective full-window splits -- rest_days uses
only each player's PRIOR game date, so it is inherently as-of, but no
forecasting claim is made here (that would need a walk-forward harness).
NETWORK: zero. DESCRIPTIVE ONLY -- NO MARKET/$ EDGE CLAIMED.

CLI:
    python -m scripts.platformkit.intel_validation.mlb_batter_splits_claims
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

REPO_ROOT = Path(__file__).resolve().parents[3]

_GAMELOGS = REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"
_STATCAST_DIR = REPO_ROOT / "data" / "cache" / "statcast"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "mlb_batter_splits.jsonl"

MIN_GAMES_FLOOR = 20
_TEAM_ALIAS = {"OAK": "ATH"}  # Athletics relocation/rename mid-corpus

# metric_key -> (numerator sum column, denominator sum/count column)
_METRICS: dict[str, tuple[str, str]] = {
    "hr_rate": ("sum_hr", "n_games"),
    "rbi_rate": ("sum_rbi", "n_games"),
    "avg": ("sum_hits", "sum_ab"),
    "k_rate": ("sum_k", "sum_pa"),
    "tb_per_pa": ("sum_tb", "sum_pa"),
}
# axis -> (bucket column, hi label, lo label, metric-name prefix)
_AXES: dict[str, tuple[str, str, str, str]] = {
    "home_away": ("loc", "home", "away", "home_minus_away"),
    "rest": ("rest_bucket", "rested", "b2b", "rest_minus_b2b"),
}


def _game_home_away_map(statcast_dir: Path = _STATCAST_DIR) -> pd.DataFrame:
    """Union of every savant_full__*.parquet + statcast_fuller__2022.parquet
    -- game_pk -> (home_team, away_team), de-duplicated. Never hardcodes a
    year list (globs savant_full__*; 2022 is the one fuller-named exception)."""
    frames = []
    if statcast_dir.exists():
        for p in sorted(statcast_dir.glob("savant_full__*.parquet")):
            frames.append(pd.read_parquet(p, columns=["game_pk", "home_team", "away_team"]))
        fuller_2022 = statcast_dir / "statcast_fuller__2022.parquet"
        if fuller_2022.exists():
            frames.append(pd.read_parquet(fuller_2022, columns=["game_pk", "home_team", "away_team"]))
    if not frames:
        return pd.DataFrame(columns=["game_pk", "home_team", "away_team"])
    return pd.concat(frames, ignore_index=True).drop_duplicates("game_pk")


def _prep_gamelogs(gamelogs_path: Path, game_map: pd.DataFrame) -> pd.DataFrame:
    cols = ["player_id", "player", "date", "team", "game_pk", "homeRuns", "rbi", "hits",
            "atBats", "strikeOuts", "totalBases", "baseOnBalls", "hitByPitch"]
    df = pd.read_parquet(gamelogs_path, columns=cols).sort_values(["player_id", "date"])
    df["team_norm"] = df["team"].replace(_TEAM_ALIAS)
    df["pa_approx"] = df["atBats"] + df["baseOnBalls"] + df["hitByPitch"]

    merged = df.merge(game_map, on="game_pk", how="left")
    merged["loc"] = None
    merged.loc[merged["team_norm"] == merged["home_team"], "loc"] = "home"
    merged.loc[merged["team_norm"] == merged["away_team"], "loc"] = "away"

    diff_days = merged.groupby("player_id")["date"].diff().dt.days
    rest_days = (diff_days - 1).clip(lower=0)
    merged["rest_bucket"] = None
    merged.loc[rest_days == 0, "rest_bucket"] = "b2b"
    merged.loc[rest_days >= 2, "rest_bucket"] = "rested"
    return merged


def _cell_sums(df: pd.DataFrame, bucket_col: str, label: str, suffix: str) -> pd.DataFrame:
    sub = df[df[bucket_col] == label]
    g = sub.groupby("player_id").agg(**{
        f"n_games{suffix}": ("game_pk", "nunique"), f"sum_hr{suffix}": ("homeRuns", "sum"),
        f"sum_rbi{suffix}": ("rbi", "sum"), f"sum_hits{suffix}": ("hits", "sum"),
        f"sum_ab{suffix}": ("atBats", "sum"), f"sum_k{suffix}": ("strikeOuts", "sum"),
        f"sum_tb{suffix}": ("totalBases", "sum"), f"sum_pa{suffix}": ("pa_approx", "sum"),
    }).reset_index()
    return g


def build_axis_snapshot(prepped: pd.DataFrame, axis: str, out_path: Path) -> tuple[Path, int]:
    bucket_col, hi_label, lo_label, _ = _AXES[axis]
    hi = _cell_sums(prepped, bucket_col, hi_label, "_hi")
    lo = _cell_sums(prepped, bucket_col, lo_label, "_lo")
    joined = hi.merge(lo, on="player_id", how="inner")
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(joined, preserve_index=False), out_path)
    return out_path, len(joined)


def build_delta_claim(metric_key: str, axis: str, snapshot_path: Path,
                       name_lookup: dict[int, str]) -> dict[str, Any]:
    num, den = _METRICS[metric_key]
    _, hi_label, lo_label, prefix = _AXES[axis]
    floor = MIN_GAMES_FLOOR
    # ONE min_sample dict drives BOTH the producer mask below and the declared
    # criteria -- claims_validator applies exactly these floors
    # (_apply_min_sample_floors) BEFORE evaluating the row-wise formula, so a
    # zero-denominator entity (e.g. a pitcher with 20+ games but 0 AB/PA in a
    # cell) must be excluded HERE or the validator's scalar division crashes
    # (real-corpus finding 2026-07-18: 6/10 claims UNVERIFIABLE 'float
    # division by zero'). n_games denominators are already floored at 20;
    # AB/PA denominators get an explicit >= 1 zero-guard (not a quality
    # floor -- the games floor is the family's declared quality cut).
    min_sample: dict[str, Any] = {"n_games_hi": floor, "n_games_lo": floor}
    if den != "n_games":
        min_sample[f"{den}_hi"] = 1
        min_sample[f"{den}_lo"] = 1
    raw = pd.read_parquet(snapshot_path)
    n_considered = len(raw)
    mask = pd.Series(True, index=raw.index)
    for col, f in min_sample.items():
        mask &= raw[col] >= f
    qualifiers = raw[mask].copy()
    n_excluded = n_considered - len(qualifiers)
    if len(qualifiers):
        rate_hi = qualifiers[f"{num}_hi"] / qualifiers[f"{den}_hi"]
        rate_lo = qualifiers[f"{num}_lo"] / qualifiers[f"{den}_lo"]
        qualifiers["delta"] = rate_hi - rate_lo
        qualifiers = qualifiers.sort_values("delta", ascending=False).reset_index(drop=True)

    ranking = [
        {"rank": i, "player_id": int(row.player_id), "player_name": str(name_lookup.get(row.player_id, "Unknown")),
         "value": round(float(row.delta), 4), "n": int(min(row.n_games_hi, row.n_games_lo))}
        for i, row in enumerate(qualifiers.itertuples(index=False), start=1)
    ]

    metric_name = f"{prefix}_{metric_key}"
    formula = f"({num}_hi/{den}_hi) - ({num}_lo/{den}_lo)"
    try:
        rel_source = str(snapshot_path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        rel_source = str(snapshot_path)  # out-of-repo path (e.g. a tmp test snapshot)
    return {
        "claim_id": f"mlb_batter_splits_{metric_name}",
        "kind": "ranking",
        "question": f"Which MLB batters show the biggest {metric_key} gap, "
                    f"{hi_label} minus {lo_label} ({axis} split)?",
        "criteria": {
            "metric": metric_name,
            "formula": formula,
            "window": f"mlb_batter_splits_{axis}",
            "window_spec": None,
            "aggregate": None,
            "min_sample": min_sample,
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            f"{metric_name}_delta = {hi_label} rate minus {lo_label} rate ({num}/{den}, "
            "ratio-of-sums, never a mean of per-game rates).",
            "home/away derived via game_pk join to the savant union (OAK->ATH alias applied); "
            "rest_days = calendar days since this player's prior game minus 1, clipped at 0 -- "
            "rest_days==1 is a deliberate excluded middle gap between the b2b and rested cells."
            if axis == "rest" else
            "home/away derived via game_pk join to the savant union (OAK->ATH alias applied); "
            "unmatched game_pk rows (~0.22% of gamelog rows) are excluded, never guessed.",
            f"min_sample floors: {min_sample} "
            f"({len(qualifiers)}/{n_considered} batters qualify). The n_games floors are "
            "the family's quality cut; any AB/PA denominator floor (>= 1) is a "
            "zero-denominator guard so entities with zero denominator in a cell (e.g. "
            "pitchers batting) are excluded, never ranked as inf/NaN.",
            f"FULL POPULATION: all {len(qualifiers)} batters clearing the floor are ranked here "
            "(no top-N truncation) -- below-floor batters honestly counted in "
            "n_excluded_below_floor, never silently dropped.",
            "DESCRIPTIVE split only -- no forecasting/market/$ edge claimed.",
        ],
    }


def build_all_claims() -> list[dict[str, Any]]:
    game_map = _game_home_away_map()
    prepped = _prep_gamelogs(_GAMELOGS, game_map)
    if _GAMELOGS.exists():
        names = pd.read_parquet(_GAMELOGS, columns=["player_id", "player"])
        name_lookup = dict(names.drop_duplicates(subset=["player_id"], keep="last").set_index("player_id")["player"])
    else:
        name_lookup = {}

    claims = []
    for axis in _AXES:
        snap_path = _OUT_DIR / f"mlb_batter_splits_{axis}_snapshot.parquet"
        snap_path, _ = build_axis_snapshot(prepped, axis, snap_path)
        for metric_key in _METRICS:
            claims.append(build_delta_claim(metric_key, axis, snap_path, name_lookup))
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit MLB batter home/away + rest split claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    if not _GAMELOGS.exists():
        print(f"NO_DATA: {_GAMELOGS} not found -- no claims written.")
        return 0
    claims = build_all_claims()
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
