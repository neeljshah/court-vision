"""SOCCER_INTL (national-team) strength ranking claims producer (mission
spine 5, lane claims-breadth-2 -> widened to FULL population, lane
soccer-wnba-fullpop). Mirrors scripts/platformkit/intel_validation/
tennis_hold_claims.py's structure: emit a FULL-population as-of ranking
claim (every team above the soccer_intl_truth_spec floor, no top-N cap) in
the SAME claims contract shape, backed by a side parquet the independent
claims_validator.py re-derives the ranking from, zero code sharing between
producer and validator.

METRIC: strength = gf_ew - ga_ew, the leak-free walk-forward EW (exponentially
weighted) goals-for-rate minus goals-against-rate a national team carries
AS OF the snapshot date, from the walk-forward GoalsState the committed
domains/soccer_intl/ratings.py predictor replays over
data/domains/soccer_intl/results.parquet (see ratings.goals_state_asof).
This is a net-expected-goals-rate: a plain, defensible team-strength number,
NOT a market/edge claim.

WHY A SIDE PARQUET: GoalsState is a stateful dict-of-teams object built by a
chronological REPLAY (not a plain groupby aggregate a formula grammar could
recompute) -- exactly the tennis emitter's situation with asof_hold's wide
match-level table. This module runs the SAME committed replay
(domains.soccer_intl.ratings.goals_state_asof) as-of the day AFTER the corpus's
last match date (a full-corpus snapshot, still strictly leak-free per-team
since each team's own EW state only ever folds in matches before it), then
writes one row per team (team, gf_ew, ga_ew, n_matches) so the validator's
formula (row-wise arithmetic, no replay) independently reproduces the ranking
from that materialized snapshot -- it never re-imports or re-runs the replay.

MIN-SAMPLE FLOOR: n_matches (the team's total processed-match count feeding
its EW state) >= 200 -- excludes small non-FIFA/regional entities in the
corpus (Jersey, Guernsey, Isle of Man, Occitania, New Caledonia, ...) whose
tiny sample sizes produce noisy EW estimates.

FULL POPULATION: every team clearing the floor is ranked (no top-N cap) --
below-floor teams are counted honestly in n_excluded_below_floor, never
silently dropped.

LEAK DISCIPLINE: gf_ew/ga_ew are the SAME leak-free trailing EW state the
predictor uses pre-match (domains/soccer_intl/ratings.py's own strictly-prior
replay contract) -- this snapshot is simply "the final as-of state after
replaying the entire on-disk corpus", not a new leak.

NETWORK: zero. Pure pandas + the committed domains.soccer_intl.ratings replay
over an already-materialized parquet.
ACCURACY ONLY -- NO MARKET EDGE CLAIMED.

CLI:
    python -m scripts.platformkit.intel_validation.soccer_intl_strength_claims
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.soccer_intl.ratings import goals_state_asof

REPO_ROOT = Path(__file__).resolve().parents[3]

_RESULTS = REPO_ROOT / "data" / "domains" / "soccer_intl" / "results.parquet"

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "soccer_intl_strength_claims.jsonl"
_SNAPSHOT_OUT = _OUT_DIR / "soccer_intl_strength_snapshot.parquet"

MIN_N_MATCHES = 200


def build_strength_snapshot(results_path: Path | None = None) -> tuple[Path, str, int]:
    """Replay the full on-disk corpus (domains.soccer_intl.ratings.goals_state_asof),
    write one row per team (team, gf_ew, ga_ew, n_matches). Returns (parquet_path,
    as_of_date_iso, n_teams). results_path defaults to module-level _RESULTS,
    looked up at CALL time (not a stale def-time default) so tests can
    monkeypatch _RESULTS and call build_ranking_claim() with no args."""
    matches = pd.read_parquet(results_path if results_path is not None else _RESULTS)
    last_date = pd.to_datetime(matches["date"]).dt.date.max()
    as_of = last_date + dt.timedelta(days=1)  # strictly after the last match: full-corpus snapshot
    state = goals_state_asof(matches, as_of)

    rows = []
    for team, gf in state.gf_ew.items():
        rows.append({
            "team": team,
            "gf_ew": float(gf),
            "ga_ew": float(state.ga_ew.get(team, 0.0)),
            "n_matches": int(state.counts.get(team, 0)),
        })
    snapshot = pd.DataFrame(rows)

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(snapshot, preserve_index=False), _SNAPSHOT_OUT)
    return _SNAPSHOT_OUT, as_of.isoformat(), len(snapshot)


def build_ranking_claim() -> dict[str, Any]:
    out_path, as_of_iso, n_considered = build_strength_snapshot()
    snapshot = pd.read_parquet(out_path)

    qualifiers = snapshot[snapshot["n_matches"] >= MIN_N_MATCHES].copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers["strength"] = qualifiers["gf_ew"] - qualifiers["ga_ew"]
    qualifiers = qualifiers.sort_values("strength", ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "team": str(row.team),
            "player_name": str(row.team),  # ask()'s ranking-entry display-name key (cross-sport reuse)
            "value": round(float(row.strength), 4),
            "n": int(row.n_matches),
        })

    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"soccer_intl_strength_full_asof_{as_of_iso}",
        "kind": "ranking",
        "question": (
            f"Which international (national-team) sides rate strongest by net "
            f"expected goals (full population above floor, as-of {as_of_iso})?"
        ),
        "criteria": {
            "metric": "strength",
            "formula": "gf_ew - ga_ew",
            "window": f"asof_{as_of_iso}",
            "window_spec": {
                "kind": "season", "season": None, "n": None, "order_by": None,
            },
            "min_sample": {"n_matches": MIN_N_MATCHES},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "team",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            f"strength = gf_ew - ga_ew, the leak-free walk-forward EW goals-for minus "
            f"goals-against rate from domains/soccer_intl/ratings.py's replay over "
            f"data/domains/soccer_intl/results.parquet, as-of {as_of_iso} (the day after "
            "the corpus's last recorded match -- a full-corpus snapshot).",
            f"min_sample floor n_matches>={MIN_N_MATCHES} (total processed matches feeding "
            "the team's EW state) -- excludes small non-FIFA/regional entities in the corpus "
            "(e.g. Jersey, Guernsey, Isle of Man) whose tiny samples produce noisy EW estimates.",
            "FULL POPULATION: every team clearing the floor is ranked, no top-N cap -- "
            "below-floor teams are counted in n_excluded_below_floor, never silently dropped.",
            "CALIBRATION/descriptive team-strength ranking only -- no market/$ edge claimed.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit SOCCER_INTL team-strength ranking claims")
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
