"""MLB batter CONTEXT-CONDITIONED split claims producer (family
mlb_batter_context) -- MLB mirror of player-level context-conditioned
intelligence. Mirrors platoon_split_claims.py: plain row-wise delta formula
(criteria.aggregate=None), zero code sharing with claims_validator.py.

SOURCE: globs data/cache/statcast/statcast_fuller__*.parquet -- every year
present (never hardcoded). Each year gets its own window, PLUS one pooled
window across all years found.

PA-ENDING DEF: events.notna() (PA-terminal pitch), THEN restricted to
estimated_woba_using_speedangle.notna() -- xwOBA is batted-ball-only, so
this drops walks/Ks/HBP/sac-bunts even though they end a PA. Declared in
every claim's caveats, never silently dropped.

THREE SPLITS, each delta = mean(hi/breaking/same) - mean(lo/fastball/opp):
  1. vs_velocity: fastball-family (FF/SI/FC) only, release_speed>=95 ("hi")
     minus <93 ("lo") -- 93-95 is a deliberate excluded gap. Floor n>=40 EACH.
  2. vs_pitch_type: breaking (SL/CU/KC/ST/SV) minus fastball-family, no
     velocity condition. Floor n>=40 EACH.
  3. platoon: same-hand (stand==p_throws) minus opposite-hand. Floor n>=75
     EACH. SIGN: positive = batter does BETTER same-hand -- the reverse of
     the typical platoon effect, so positive is the unusual case here.

ALL DESCRIPTIVE_ONLY, NOT causal: pitch selection (who gets thrown 95+, who
sees more breaking balls) is not random; pitchers attack known weaknesses.

LEAK: purely descriptive/retrospective aggregate -- no forecasting claim
(forward-looking test lives in predictive_validity/mlb_adapters.py's
batter_context_test, a SEPARATE walk-forward harness run). NETWORK: zero.
DESCRIPTIVE/SCOUTING ONLY -- NO MARKET/$ EDGE CLAIMED.

CLI:
    python -m scripts.platformkit.intel_validation.mlb_batter_context_claims
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[3]

_STATCAST_DIR = REPO_ROOT / "data" / "cache" / "statcast"
_GAMELOGS = REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "mlb_batter_context_claims.jsonl"

_FUELLER_RE = re.compile(r"statcast_fuller__(\d{4})\.parquet$")

FASTBALL_FAMILY = frozenset({"FF", "SI", "FC"})
BREAKING_FAMILY = frozenset({"SL", "CU", "KC", "ST", "SV"})
HI_VELO_MPH = 95.0
LO_VELO_MPH = 93.0
MIN_VELO_PA = 40
MIN_PITCH_TYPE_PA = 40
MIN_PLATOON_PA = 75

_PA_DEF_CAVEAT = (
    "PA-ending pitch = events.notna(), further restricted to "
    "estimated_woba_using_speedangle.notna() (statcast's xwOBA composite is "
    "batted-ball-only) -- this DROPS walks/strikeouts/HBP/sac-bunts from the "
    "xwOBA mean even though they end a PA; declared here, never silently."
)
_CAUSAL_CAVEAT = (
    "DESCRIPTIVE split only, NOT causal: pitch selection (who gets thrown "
    "95+, who sees more breaking balls) is not random -- pitchers attack a "
    "batter's known weaknesses. No forecasting/market/$ edge claimed."
)

_METRICS: dict[str, dict[str, Any]] = {
    "vs_velocity": {
        "hi_label": "hi", "lo_label": "lo",
        "question": "highest xwOBA gap vs high (95+ mph) minus low (<93 mph) "
                     "fastball-family velocity",
        "sign_note": "vs_velocity_delta = mean xwOBA vs release_speed>=95 minus "
                     "vs release_speed<93, fastball-family pitches only "
                     "(FF/SI/FC); 93-95 mph is a deliberate excluded gap band.",
        "floor": MIN_VELO_PA,
    },
    "vs_pitch_type": {
        "hi_label": "breaking", "lo_label": "fastball",
        "question": "highest xwOBA gap vs breaking balls minus vs fastballs",
        "sign_note": "vs_pitch_type_delta = mean xwOBA vs breaking "
                     "(SL/CU/KC/ST/SV) minus vs fastball-family (FF/SI/FC), no "
                     "velocity condition.",
        "floor": MIN_PITCH_TYPE_PA,
    },
    "platoon": {
        "hi_label": "same", "lo_label": "opp",
        # metric_name != "platoon_delta": that name is taken by platoon_split_claims.py's
        # mlb_platoon_split family (on-base rate, not xwOBA) -- avoids a metric-name collision.
        "metric_name": "context_platoon_delta",
        "question": "biggest same-hand-vs-opposite-hand xwOBA gap (stand vs "
                     "p_throws)",
        "sign_note": "context_platoon_delta = mean xwOBA same-hand "
                     "(stand==p_throws) minus opposite-hand -- POSITIVE means "
                     "the batter does BETTER same-hand, the reverse of the "
                     "typical platoon effect (most batters are worse "
                     "same-hand); a positive value here is the unusual case, "
                     "not the expected one.",
        "floor": MIN_PLATOON_PA,
    },
}


def discover_seasons(statcast_dir: Path = _STATCAST_DIR) -> dict[int, Path]:
    """Glob statcast_fuller__*.parquet -- never a hardcoded year list."""
    found = {}
    if statcast_dir.exists():
        for p in sorted(statcast_dir.glob("statcast_fuller__*.parquet")):
            m = _FUELLER_RE.search(p.name)
            if m:
                found[int(m.group(1))] = p
    return found


def load_batter_rows(paths: dict[int, Path]) -> pd.DataFrame:
    """Read raw columns for every year found, apply the PA-ending +
    xwOBA-populated filter, derive the three bucket columns. Returns a long
    frame (batter, season, xwoba, velo_bucket, pitch_class, platoon_match);
    each bucket column is None where a row doesn't qualify for that split
    (e.g. a changeup PA has no velo_bucket/pitch_class, only platoon_match)."""
    cols = ["batter", "events", "release_speed", "pitch_type", "stand",
            "p_throws", "estimated_woba_using_speedangle"]
    frames = []
    for season, path in sorted(paths.items()):
        df = pd.read_parquet(path, columns=cols)
        df["season"] = season
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=cols + ["season", "xwoba", "velo_bucket",
                                             "pitch_class", "platoon_match"])
    df = pd.concat(frames, ignore_index=True)

    pa_ending = df["events"].notna()
    has_xwoba = df["estimated_woba_using_speedangle"].notna()
    df = df[pa_ending & has_xwoba].copy()
    df["xwoba"] = df["estimated_woba_using_speedangle"].astype("float64")

    is_fastball = df["pitch_type"].isin(FASTBALL_FAMILY)
    is_breaking = df["pitch_type"].isin(BREAKING_FAMILY)
    velo = df["release_speed"].astype("float64")
    df["velo_bucket"] = np.select(
        [is_fastball & (velo >= HI_VELO_MPH), is_fastball & (velo < LO_VELO_MPH)],
        ["hi", "lo"], default=None,
    )
    df["pitch_class"] = np.select([is_breaking, is_fastball], ["breaking", "fastball"], default=None)
    df["platoon_match"] = np.where(df["stand"] == df["p_throws"], "same", "opp")

    return df[["batter", "season", "xwoba", "velo_bucket", "pitch_class", "platoon_match"]]


def _bucket_stats(df: pd.DataFrame, bucket_col: str, label: str) -> pd.DataFrame:
    sub = df[df[bucket_col] == label]
    g = sub.groupby("batter")["xwoba"].agg(n="size", mean="mean").reset_index()
    return g


def build_snapshot(df: pd.DataFrame, bucket_col: str, hi_label: str, lo_label: str,
                    out_path: Path) -> tuple[Path, dict]:
    """Wide per-batter snapshot (n_hi/mean_hi/n_lo/mean_lo) -- plain
    row-wise formula path (platoon_split_claims.py's pattern): the validator
    recomputes mean_hi - mean_lo directly, no group_by re-derivation."""
    hi = _bucket_stats(df, bucket_col, hi_label).rename(columns={"n": "n_hi", "mean": "mean_hi"})
    lo = _bucket_stats(df, bucket_col, lo_label).rename(columns={"n": "n_lo", "mean": "mean_lo"})
    joined = hi.merge(lo, on="batter", how="inner")
    n_considered = len(joined)

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(joined, preserve_index=False), out_path)
    return out_path, {"n_considered": n_considered}


def build_delta_claim(metric_key: str, window_label: str, snapshot_path: Path,
                       name_lookup: dict[int, str], seasons_declared: list[int]) -> dict[str, Any]:
    spec = _METRICS[metric_key]
    floor = spec["floor"]
    raw = pd.read_parquet(snapshot_path)
    n_considered = len(raw)
    qualifiers = raw[(raw["n_hi"] >= floor) & (raw["n_lo"] >= floor)].copy()
    n_excluded = n_considered - len(qualifiers)
    if len(qualifiers):
        qualifiers["delta"] = qualifiers["mean_hi"] - qualifiers["mean_lo"]
        qualifiers = qualifiers.sort_values("delta", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        bid = int(row.batter)
        ranking.append({
            "rank": i,
            "batter": bid,
            "batter_name": str(name_lookup.get(bid, "Unknown")),
            "value": round(float(row.delta), 4),
            "n": int(min(row.n_hi, row.n_lo)),
        })

    seasons_str = "/".join(str(s) for s in seasons_declared) if seasons_declared else "none"
    rel_source = str(snapshot_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"mlb_batter_context_{metric_key}_delta_{window_label}",
        "kind": "ranking",
        "question": f"Which MLB batters show the {spec['question']} "
                    f"(full qualifying population, window={window_label})?",
        "criteria": {
            "metric": spec.get("metric_name", f"{metric_key}_delta"),
            "formula": "mean_hi - mean_lo",
            "window": f"mlb_batter_context_{metric_key}_{window_label}",
            "window_spec": None,
            "aggregate": None,
            "min_sample": {"n_hi": floor, "n_lo": floor},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "batter",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            spec["sign_note"],
            _PA_DEF_CAVEAT,
            f"years present in this corpus at emit time: {seasons_str} -- window={window_label} "
            f"({'a single season' if window_label != 'pooled' else 'pooled across all years found'}).",
            f"min_sample floor: n >= {floor} in EACH bucket "
            f"({len(qualifiers)}/{n_considered} batters qualify).",
            f"FULL POPULATION: all {len(qualifiers)} batters clearing the floor are ranked "
            "here (no top-N truncation) -- below-floor batters honestly counted in "
            "n_excluded_below_floor, never silently dropped.",
            _CAUSAL_CAVEAT,
        ],
    }


def build_all_claims(statcast_dir: Path = _STATCAST_DIR) -> list[dict[str, Any]]:
    paths = discover_seasons(statcast_dir)
    seasons_declared = sorted(paths.keys())
    all_rows = load_batter_rows(paths)

    if _GAMELOGS.exists():
        names = pd.read_parquet(_GAMELOGS, columns=["player_id", "player"])
        name_lookup = dict(
            names.drop_duplicates(subset=["player_id"], keep="last").set_index("player_id")["player"]
        )
    else:
        name_lookup = {}

    windows: list[tuple[str, pd.DataFrame]] = [(str(s), all_rows[all_rows["season"] == s]) for s in seasons_declared]
    windows.append(("pooled", all_rows))

    bucket_cols = {"vs_velocity": "velo_bucket", "vs_pitch_type": "pitch_class", "platoon": "platoon_match"}
    claims = []
    for window_label, wdf in windows:
        for metric_key, spec in _METRICS.items():
            bucket_col = bucket_cols[metric_key]
            snap_path = _OUT_DIR / f"mlb_batter_context_{metric_key}_{window_label}.parquet"
            snap_path, _ = build_snapshot(wdf, bucket_col, spec["hi_label"], spec["lo_label"], snap_path)
            claims.append(build_delta_claim(metric_key, window_label, snap_path, name_lookup, seasons_declared))
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit MLB batter context-split descriptive ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = build_all_claims()
    if not claims:
        print("NO_DATA: no statcast_fuller__*.parquet found under data/cache/statcast/ -- "
              "no claims written.")
        return 0
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
