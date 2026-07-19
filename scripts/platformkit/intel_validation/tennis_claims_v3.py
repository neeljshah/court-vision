"""Tennis truth-spec breadth: return-quality + hold/break-dynamics ranking
claims (program v3, lane tennis-fullpop). Adds the tennis_truth_spec.json
dimensions whose corpus already exists on disk as a plain per-entity leak-free
parquet -- companion to tennis_hold_claims.py (which already covers
hold_pct_asof) and tennis_h2h_index_claims.py (already covers head-to-head).
Kept in a SEPARATE file (not appended to tennis_hold_claims.py) purely on the
<=300 LOC-per-file rail: tennis_hold_claims.py is already at its own budget
before adding a second corpus family.

Reuses the EXACT wide->long reshape + season-snapshot pattern
tennis_hold_claims.py established (see that module's docstring for the WHY):
each on-disk asof_*.parquet is one row per MATCH with p1_/p2_-prefixed
columns and no player_id column; this module melts p1_/p2_ into one row per
player per match, then keeps each player's LAST as-of snapshot within the
declared season window.

NEW DIMENSIONS (both FULL POPULATION -- every qualifier above the floor gets
a ranked row, no top-N slice, per the same discipline as the uncapped
tennis_hold_claims.py):
  - return_pts_won_asof, break_pct_asof   (data/domains/tennis/asof_return.parquet)
      ATP ONLY: confirmed by event_id-intersection against wta_matches.parquet
      (zero overlap) -- there is no on-disk WTA return-quality corpus, matching
      tennis_truth_spec.json (asof_return.parquet lists no _wta companion,
      unlike asof_hold/asof_setdetail which both do).
  - tiebreak_win_pct_asof, sets_dropped_rate_asof, close_set_rate_asof
      (data/domains/tennis/asof_setdetail.parquet + asof_setdetail_wta.parquet)
      ATP + WTA: both files confirmed to fully intersect their tour's match
      spine (30616/30616 ATP, 11270/11270 WTA).

MIN-SAMPLE FLOOR: n_prior >= 50, matching tennis_hold_claims.py's floor and
rationale exactly (a defensible floor against small-sample noise on a running
trailing-average feature, not a tour-standard threshold). The two
asof_return.parquet metrics carry per-metric n_prior columns
(p{1,2}_return_won_n_prior / p{1,2}_break_pct_n_prior) that are numerically
identical (same underlying return-points sample) -- return_won_n_prior is
used as the single floor column for both metrics, avoiding a spurious
duplicate. asof_setdetail.parquet/_wta share one n_prior column across all
three of its metrics.

LEAK DISCIPLINE: every source column is already a leak-free trailing feature
(each row is a snapshot BEFORE that match is played; see
domains/tennis/asof_return.py / asof_setdetail.py's own future-leak
assertions). Taking a player's LAST snapshot in-window adds no new leak.

NETWORK: zero. Pure pandas over already-materialized parquets.
DESCRIPTIVE/CALIBRATION ONLY -- NO MARKET/$ EDGE CLAIMED.

CLI:
    python -m scripts.platformkit.intel_validation.tennis_claims_v3
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[3]

_ATP_MATCHES = REPO_ROOT / "data" / "domains" / "tennis" / "matches.parquet"
_WTA_MATCHES = REPO_ROOT / "data" / "domains" / "tennis" / "wta_matches.parquet"
_ATP_RETURN = REPO_ROOT / "data" / "domains" / "tennis" / "asof_return.parquet"
_ATP_SETDETAIL = REPO_ROOT / "data" / "domains" / "tennis" / "asof_setdetail.parquet"
_WTA_SETDETAIL = REPO_ROOT / "data" / "domains" / "tennis" / "asof_setdetail_wta.parquet"

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "tennis_claims_v3.jsonl"

SEASON_WINDOW = "2025"  # same last-complete-season window as tennis_hold_claims.py
MIN_N_PRIOR = 50


@dataclass(frozen=True)
class MetricSpec:
    """One rankable metric within a source corpus.
    metric: the plain (non-prefixed) column name, e.g. "return_won_asof".
    n_prior_metric: which p{1,2}_<x>_n_prior column names the floor (may
        differ from `metric` when several metrics share one floor column,
        e.g. break_pct_asof floors on return_won_n_prior)."""
    metric: str
    n_prior_metric: str
    label: str  # human-readable, used in the claim's `question` text


@dataclass(frozen=True)
class SourceSpec:
    """One source parquet + the tours it covers + the metrics it exposes."""
    key: str  # short slug used in claim_id / snapshot filename
    metrics: tuple[MetricSpec, ...]
    atp_path: Path | None
    wta_path: Path | None


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        key="return",
        metrics=(
            MetricSpec("return_won_asof", "return_won_n_prior", "return points won"),
            MetricSpec("break_pct_asof", "return_won_n_prior", "break percentage"),
        ),
        atp_path=_ATP_RETURN,
        wta_path=None,  # confirmed absent on disk -- zero event_id overlap with wta_matches.parquet
    ),
    SourceSpec(
        key="setdetail",
        metrics=(
            MetricSpec("tiebreak_win_pct_asof", "n_prior", "tiebreak win percentage"),
            MetricSpec("sets_dropped_rate_asof", "n_prior", "sets-dropped rate"),
            MetricSpec("close_set_rate_asof", "n_prior", "close-set rate"),
        ),
        atp_path=_ATP_SETDETAIL,
        wta_path=_WTA_SETDETAIL,
    ),
)


def _reshape_long(matches: pd.DataFrame, source: pd.DataFrame, metric: str, n_prior_metric: str) -> pd.DataFrame:
    """Join the match spine (p1_id/p2_id/date) against the wide source table
    for ONE metric, then melt p1_/p2_ into one row per player per match:
    columns = player_id, date, value, n_prior."""
    spine = matches[["event_id", "date", "p1_id", "p2_id"]].copy()
    val_cols = [f"p1_{metric}", f"p2_{metric}"]
    n_cols = [f"p1_{n_prior_metric}", f"p2_{n_prior_metric}"]
    joined = spine.merge(source[["event_id"] + val_cols + n_cols], on="event_id", how="inner")
    p1 = joined.rename(columns={
        "p1_id": "player_id", f"p1_{metric}": "value", f"p1_{n_prior_metric}": "n_prior",
    })[["player_id", "date", "value", "n_prior"]]
    p2 = joined.rename(columns={
        "p2_id": "player_id", f"p2_{metric}": "value", f"p2_{n_prior_metric}": "n_prior",
    })[["player_id", "date", "value", "n_prior"]]
    long_df = pd.concat([p1, p2], ignore_index=True)
    long_df["player_id"] = pd.to_numeric(long_df["player_id"], errors="coerce")
    long_df = long_df.dropna(subset=["player_id"])
    long_df["player_id"] = long_df["player_id"].astype("int64")
    return long_df


def _season_snapshot(long_df: pd.DataFrame, season: str) -> pd.DataFrame:
    """Restrict to the season window, then keep each player's LAST (most
    recent-dated) as-of row within that window -- one row per player.
    Identical rule to tennis_hold_claims.py's _season_snapshot."""
    season_year = int(season)
    in_season = long_df[long_df["date"].map(lambda d: d.year) == season_year].copy()
    in_season = in_season.sort_values("date", kind="mergesort")
    latest = in_season.groupby("player_id", as_index=False).tail(1).reset_index(drop=True)
    return latest


def _name_lookup(matches: pd.DataFrame) -> dict[int, str]:
    names: dict[int, str] = {}
    for id_col, name_col in (("p1_id", "p1_name"), ("p2_id", "p2_name")):
        sub = matches[[id_col, name_col]].dropna()
        for pid, name in zip(sub[id_col], sub[name_col]):
            names[int(pid)] = str(name)
    return names


def build_metric_snapshot(
    source_key: str, metric: MetricSpec, tour: str,
) -> tuple[Path, pd.DataFrame, int, int]:
    """Build + write the long-format season snapshot parquet for one
    (source, metric, tour) combination. Returns (parquet_path, snapshot_df,
    n_considered, n_excluded_below_floor)."""
    src = next(s for s in SOURCES if s.key == source_key)
    tour_path = src.atp_path if tour == "atp" else src.wta_path
    matches_path = _ATP_MATCHES if tour == "atp" else _WTA_MATCHES
    if tour_path is None:
        raise ValueError(f"no on-disk {tour.upper()} corpus for source={source_key!r}")

    matches = pd.read_parquet(matches_path)
    source = pd.read_parquet(tour_path)
    long_df = _reshape_long(matches, source, metric.metric, metric.n_prior_metric)
    snapshot = _season_snapshot(long_df, SEASON_WINDOW)
    n_considered = len(snapshot)
    n_excluded = int((snapshot["n_prior"] < MIN_N_PRIOR).sum())

    out_path = _OUT_DIR / f"tennis_v3_snapshot_{source_key}_{metric.metric}_{tour}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_cols = snapshot[["player_id", "value", "n_prior"]].copy()
    pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), out_path)

    names = _name_lookup(matches)
    snapshot = snapshot.copy()
    snapshot["player_name"] = snapshot["player_id"].map(lambda pid: names.get(int(pid), "Unknown"))
    return out_path, snapshot, n_considered, n_excluded


def build_ranking_claim(source_key: str, metric: MetricSpec, tour: str) -> dict[str, Any]:
    out_path, snapshot, n_considered, n_excluded = build_metric_snapshot(source_key, metric, tour)
    qualifiers = snapshot[snapshot["n_prior"] >= MIN_N_PRIOR].copy()
    qualifiers = qualifiers.dropna(subset=["value"])
    # tie-break: value DESC, THEN player_id ASC -- matches claims_validator.py's
    # generic recompute tie-break, see tennis_ranking_claims.py docstring.
    qualifiers = qualifiers.sort_values(["value", "player_id"], ascending=[False, True]).reset_index(drop=True)
    # FULL POPULATION: every qualifier above the floor is ranked, no head(N).
    top = qualifiers

    ranking = []
    for i, row in enumerate(top.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "player_id": int(row.player_id),
            "player_name": row.player_name,
            "value": round(float(row.value), 4),
            "n": int(row.n_prior),
        })

    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    tour_label = "ATP" if tour == "atp" else "WTA"
    claim_id = f"tennis_{source_key}_{metric.metric}_{tour}_{SEASON_WINDOW}"
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": f"Who leads the {tour_label} tour in {metric.label} (full population, season={SEASON_WINDOW})?",
        "criteria": {
            "metric": metric.metric,
            "formula": "value",
            "window": f"season_{SEASON_WINDOW}_{tour}",
            "window_spec": {
                "kind": "season", "season": SEASON_WINDOW, "n": None, "order_by": None,
            },
            "min_sample": {"n_prior": MIN_N_PRIOR},
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
            f"{metric.metric} is a leak-free TRAILING as-of prior (domains/tennis/asof_return.py / "
            f"asof_setdetail.py); each player's row is their LAST as-of snapshot within season="
            f"{SEASON_WINDOW} (their most recent trailing value, not a season-average recompute).",
            f"min_sample floor n_prior>={MIN_N_PRIOR} (running matches-in-history feeding the "
            "trailing average) -- same floor and rationale as tennis_hold_claims.py, a defensible "
            "guard against small-sample noise, not a tour-standard threshold.",
            "FULL POPULATION: every qualifying player above the floor is ranked (no top-N slice); "
            "below-floor players are counted in n_excluded_below_floor, never dropped.",
            "CALIBRATION/descriptive ranking only -- no market/$ edge claimed.",
        ],
    }


def build_all_claims() -> tuple[list[dict[str, Any]], list[str]]:
    """Build every (source, metric, tour) claim where the tour's on-disk
    corpus exists. Returns (claims, dims_corpus_absent) -- the latter names
    the (source, metric, tour) combinations skipped because no on-disk
    parquet exists for that tour (honest gap, not a silent drop)."""
    claims: list[dict[str, Any]] = []
    absent: list[str] = []
    for src in SOURCES:
        for metric in src.metrics:
            for tour, path in (("atp", src.atp_path), ("wta", src.wta_path)):
                dim_label = f"{src.key}.{metric.metric}.{tour}"
                if path is None:
                    absent.append(dim_label)
                    continue
                claims.append(build_ranking_claim(src.key, metric, tour))
    return claims, absent


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit tennis v3 breadth ranking claims (return + setdetail)")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims, absent = build_all_claims()
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} "
              f"top1={c['ranking'][0] if c['ranking'] else None}")
    if absent:
        print(f"dims_corpus_absent (honest gap, no on-disk corpus): {absent}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
