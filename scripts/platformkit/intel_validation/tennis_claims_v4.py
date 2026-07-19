"""Tennis surface-split DESCRIPTIVE ranking claims (lane tennis-persist,
program v3). Emits FULL-population ranking claims (every player above the
stated per-surface floor, no top-N cap) from the NEW
data/cache/tennis_atlas/surface_splits.parquet layer (domains/tennis/
atlas_persist_layers.persist_surface_splits) -- per-player, per-surface,
career-descriptive serve aggregates: ace rate, first-serve-in %,
double-fault rate on hard/clay/grass.

CLOSED-CLASS GUARD (program v2 ratified verdict): tennis playstyle/surface
PREDICTIVE gates are CLOSED -- no in-game or pregame conditioning hypothesis
on playstyle/surface priors is being re-opened here. This module emits
PLAIN DESCRIPTIVE RANKINGS ONLY: no hypothesis test, no predictive gate, no
calibration/Brier claim, no market/$ edge claim. Every ranking is a
descriptive box-score/serve aggregate with a stated provenance + floor,
identical in kind to tennis_claims_v3.py / tennis_hold_claims.py / the
basketball and WNBA descriptive-ranking producers -- it does not re-open,
extend, or bear on the closed predictive-gate verdict in any way.

NINE DIMENSIONS (3 metrics x 3 surfaces), each FULL POPULATION (every
qualifier above the floor is ranked, no head(N) slice; below-floor players
are counted in n_excluded_below_floor, never silently dropped):
  ace_rate            -- per-player mean ace rate on {Hard,Clay,Grass}
  first_serve_in_pct  -- per-player mean first-serve-in %% on {Hard,Clay,Grass}
  double_fault_rate   -- per-player mean double-fault rate on {Hard,Clay,Grass}

MIN-SAMPLE FLOOR: n_matches >= 30 on THAT surface (stricter than the
persistence layer's own MIN_SURFACE_SPLIT_MATCHES=10 floor -- this module
applies an additional, stated floor on top so the claims themselves rank
only players with a defensibly large per-surface sample; the persistence
layer's floor is a storage-noise guard, this floor is the claim's own
stated sample-size contract). Players clearing the persistence floor but
below THIS claim's n_matches>=30 floor are counted in
n_excluded_below_floor, never dropped without a trace.

LEAK DISCIPLINE: not applicable -- this is a full-career, non-trailing,
purely descriptive corpus aggregate (see atlas_persist_layers.
persist_surface_splits' own docstring); no forecasting claim, no as-of
ordering claim, no leak-risk window.

NETWORK: zero. Pure pandas over an already-materialized parquet.
DESCRIPTIVE ONLY -- NO MARKET/$ EDGE CLAIMED, NO GATE, NO CALIBRATION CLAIM.

CLI:
    python -m scripts.platformkit.intel_validation.tennis_claims_v4
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]

_SURFACE_SPLITS_SRC = REPO_ROOT / "data" / "cache" / "tennis_atlas" / "surface_splits.parquet"
# surface_splits.parquet's player_id is ATP-only (confirmed: 423/423 ids
# intersect matches.parquet, 0/423 intersect wta_matches.parquet), so the
# SAME name-lookup source tennis_hold_claims.py / tennis_claims_v3.py already
# use (matches.parquet's p1_name/p2_name) resolves every id here too --
# reused verbatim, not a new mapping.
_ATP_MATCHES_FOR_NAMES = REPO_ROOT / "data" / "domains" / "tennis" / "matches.parquet"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "tennis_claims_v4.jsonl"

MIN_N_MATCHES_ON_SURFACE = 30
PRIMARY_SURFACES: tuple[str, ...] = ("Hard", "Clay", "Grass")

_CLOSED_CLASS_CAVEAT = (
    "CLOSED-CLASS GUARD: tennis playstyle/surface PREDICTIVE gates are CLOSED "
    "(program v2 ratified verdict) -- this is a plain DESCRIPTIVE ranking only, "
    "NOT a hypothesis test, NOT a predictive/in-game gate, NOT a calibration or "
    "Brier claim, and does NOT re-open or bear on the closed predictive-gate "
    "verdict in any way."
)


@dataclass(frozen=True)
class MetricSpec:
    """One rankable per-surface metric. column: the plain column name in
    surface_splits.parquet. label: human-readable text for the claim's
    `question` field."""
    column: str
    label: str


METRICS: tuple[MetricSpec, ...] = (
    MetricSpec("ace_rate", "ace rate"),
    MetricSpec("first_serve_in_pct", "first-serve-in percentage"),
    MetricSpec("double_fault_rate", "double-fault rate"),
)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _load_surface_splits() -> pd.DataFrame:
    return pd.read_parquet(_SURFACE_SPLITS_SRC)


def _name_lookup() -> dict[int, str]:
    """IDENTICAL pattern to tennis_hold_claims.py / tennis_claims_v3.py's
    _name_lookup: read matches.parquet's p1_id/p1_name + p2_id/p2_name pairs
    into one {player_id: name} dict. surface_splits.parquet has no name
    column of its own (see module docstring's ATP-only overlap check)."""
    names: dict[int, str] = {}
    if not _ATP_MATCHES_FOR_NAMES.exists():
        return names
    matches = pd.read_parquet(_ATP_MATCHES_FOR_NAMES, columns=["p1_id", "p1_name", "p2_id", "p2_name"])
    for id_col, name_col in (("p1_id", "p1_name"), ("p2_id", "p2_name")):
        sub = matches[[id_col, name_col]].dropna()
        for pid, name in zip(sub[id_col], sub[name_col]):
            names[int(pid)] = str(name)
    return names


def build_surface_snapshot(
    df: pd.DataFrame, metric: MetricSpec, surface: str, out_dir: Path = _OUT_DIR
) -> tuple[Path, pd.DataFrame]:
    """Write a PRE-FILTERED, single-(metric,surface) snapshot parquet and
    return (path, sub_df). The shared surface_splits.parquet stacks all 3
    surfaces in one file with no categorical-filter primitive in
    claims_validator's formula grammar -- so each claim's source_files must
    point at an ALREADY-SLICED single-surface file (same pattern
    tennis_claims_v3.py's build_metric_snapshot uses for per-tour slices),
    not the shared multi-surface parquet directly.

    out_dir defaults to the real _OUT_DIR; tests MUST pass a tmp_path here so
    fixture rows never overwrite the committed production snapshot parquets
    that claims_validator re-reads from disk on every validation run."""
    sub = df[df["surface"] == surface][["player_id", "n_matches", metric.column, "as_of"]].copy()
    out_path = out_dir / f"tennis_v4_snapshot_{metric.column}_{surface.lower()}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sub.to_parquet(out_path, index=False)
    return out_path, sub


def build_ranking_claim(
    df: pd.DataFrame, metric: MetricSpec, surface: str, out_dir: Path = _OUT_DIR
) -> dict[str, Any]:
    """Full-population ranking for one (metric, surface) pair: every player
    with n_matches>=MIN_N_MATCHES_ON_SURFACE on `surface`, ranked desc by
    `metric.column`, no top-N cap.

    out_dir defaults to the real _OUT_DIR (used by build_all_claims/main);
    tests MUST pass a tmp_path so fixture snapshots never land in
    data/cache/intel_claims/ and corrupt the committed real snapshots."""
    out_path, sub = build_surface_snapshot(df, metric, surface, out_dir=out_dir)
    n_considered = len(sub)
    qualifiers = sub[sub["n_matches"] >= MIN_N_MATCHES_ON_SURFACE].copy()
    qualifiers = qualifiers.dropna(subset=[metric.column])
    n_excluded = n_considered - len(qualifiers)
    # tie-break: value DESC, THEN player_id ASC -- matches claims_validator.py's
    # generic recompute tie-break, see tennis_ranking_claims.py docstring.
    qualifiers = qualifiers.sort_values([metric.column, "player_id"], ascending=[False, True]).reset_index(drop=True)

    # player_name is NOT written to the snapshot parquet (kept numeric-only,
    # matching tennis_claims_v3.py's snapshot shape exactly) -- it is joined
    # in-memory here purely to enrich the claim's own `ranking` rows so
    # ask.py's name-based entity_lookup can resolve them; ids genuinely
    # absent from the name source get player_name=None, counted honestly
    # rather than silently dropped or faked.
    names = _name_lookup()
    ids_without_name = int(sum(1 for pid in qualifiers["player_id"] if int(pid) not in names))

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        pid = int(getattr(row, "player_id"))
        ranking.append({
            "rank": i,
            "player_id": pid,
            "player_name": names.get(pid),
            "value": round(float(getattr(row, metric.column)), 4),
            "n": int(getattr(row, "n_matches")),
        })

    corpus_as_of = str(sub["as_of"].iloc[0]) if len(sub) else "unknown"
    claim_id = f"tennis_surface_split_{metric.column}_{surface.lower()}_full"
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": (
            f"Which ATP players have the highest {metric.label} on {surface} "
            f"(full population above floor, career-to-date)?"
        ),
        "criteria": {
            "metric": metric.column,
            "formula": metric.column,
            "window": f"career_to_date_{surface.lower()}",
            "window_spec": {"kind": "career_to_date", "season": None, "n": None, "order_by": None},
            "min_sample": {"n_matches": MIN_N_MATCHES_ON_SURFACE},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [_rel(out_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "ids_without_name": ids_without_name,
        "caveats": [
            f"{metric.column} = per-player mean {metric.label} on {surface} matches, "
            "sourced from data/cache/tennis_atlas/surface_splits.parquet (domains/tennis/"
            "atlas_persist_layers.persist_surface_splits -- full-career descriptive "
            "aggregate over the Sackmann ATP matches.parquet + match_stats.parquet corpus, "
            f"corpus as_of={corpus_as_of}) via a single-surface snapshot slice "
            "(source_files points at the pre-filtered per-surface parquet so the "
            "independent validator can recompute without a categorical-filter primitive).",
            f"min_sample floor n_matches>={MIN_N_MATCHES_ON_SURFACE} on THIS surface "
            "(stricter than the persistence layer's own storage-noise floor of "
            "n_matches>=10) -- a defensible guard against small-sample noise on a "
            "per-surface serve aggregate, not a tour-standard threshold.",
            "FULL POPULATION: every player clearing the floor on this surface is ranked "
            "(no top-N slice); below-floor players are counted in "
            "n_excluded_below_floor, never dropped without a trace.",
            _CLOSED_CLASS_CAVEAT,
        ],
    }


def build_all_claims(out_dir: Path | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Build every (metric, surface) claim where the surface has at least one
    row in the on-disk corpus. Returns (claims, dims_corpus_absent) -- the
    latter names any (metric, surface) combination with zero on-disk rows
    for that surface (honest gap, never silently omitted).

    out_dir is forwarded to build_ranking_claim/build_surface_snapshot for
    every claim; None (the default, used by main()) means "use the real
    module _OUT_DIR looked up at call time" -- tests should pass a tmp_path
    explicitly so fixture snapshots never land in data/cache/intel_claims/."""
    resolved_out_dir = out_dir if out_dir is not None else _OUT_DIR
    df = _load_surface_splits()
    claims: list[dict[str, Any]] = []
    absent: list[str] = []
    for metric in METRICS:
        for surface in PRIMARY_SURFACES:
            dim_label = f"{metric.column}.{surface.lower()}"
            if surface not in set(df["surface"].unique()):
                absent.append(dim_label)
                continue
            claims.append(build_ranking_claim(df, metric, surface, out_dir=resolved_out_dir))
    return claims, absent


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit tennis surface-split DESCRIPTIVE ranking claims (no gate, closed-class guard)"
    )
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims, absent = build_all_claims()
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} "
              f"top1={c['ranking'][0] if c['ranking'] else None}")
    if absent:
        print(f"dims_corpus_absent (honest gap, no on-disk rows for this surface): {absent}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
