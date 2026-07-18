"""Tennis surface-conditioned form family "tennis_surface_context".

STEP-0 PREMISE: data/domains/tennis/matches*.parquet is MATCH-level (one row
per match, p1_id/p2_id/winner/surface/date/tour), NOT player-level -- so this
producer reshapes to a per-player-per-match LONG frame first (each match
contributes one row for p1's perspective and one for p2's), then aggregates
to a per-(tour, window, player) SNAPSHOT parquet (wins/n per surface), same
precedent as tennis_h2h_claims.py's pre-aggregated side parquet: the
independent validator's PLAIN (non-aggregate) formula path recomputes
straight off that snapshot, never re-deriving the match-level reshape
itself (criteria.aggregate.group_by takes one bare column, not the
match-level p1_id/p2_id split this needs).

WINDOWS (both declared, both emitted): "career" = every dated match in the
corpus (2015-2025 pooled); "recent_form" = matches on/after 2023-01-01. Every
claim states which window it is under criteria.window.

SURFACES: Hard/Clay/Grass only -- Unknown/Carpet rows are excluded from every
surface computation (stated in caveats), matching mission scope.

RETIREMENT: `retirement` rows are COUNTED AS DECIDED matches (the `winner`
column is authoritative regardless of retirement) -- a declared choice, not
an oversight; stated in every claim's caveats as a confound (a retirement
win is not the same signal as a played-out win).

WINNER VALUES: asserted to be exactly {1, 2} before any computation --
fail-closed (raises) if the corpus ever carries an unexpected winner code.

PREREG FLOORS (declared before any scoring):
  - surface win-rate GAP ranking (clay specialists / hard specialists):
    clay_n >= 25 AND hard_n >= 25 in the window.
  - surface FORM ranking (top players on a given surface): that surface's
    n >= 30 in the window.
  - GRASS ADAPTABILITY (grass_wr - overall_wr): grass_n >= 15 (grass is
    scarce on tour -- a 25/30 floor would empty the ranking; 15 is the
    lower, declared floor for this claim only).

CONFOUNDS (stated on every claim): opponent-strength is NOT controlled --
who a player faces on clay differs systematically from who they face on
hard (draws are not random), so a surface win-rate gap partly reflects
scheduling/seeding, not surface skill alone. DESCRIPTIVE_ONLY, no forecast,
no market/$ edge.

CLI:
    python -m scripts.platformkit.intel_validation.tennis_surface_context_claims
"""
from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[3]

_MATCHES_GLOB = str(REPO_ROOT / "data" / "domains" / "tennis" / "matches*.parquet")
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "tennis_surface_context_claims.jsonl"

SURFACES = ("Hard", "Clay", "Grass")
RECENT_FORM_START = "2023-01-01"
MIN_GAP_FLOOR = 25   # each of clay_n/hard_n, for the specialist-gap ranking
MIN_FORM_FLOOR = 30  # that surface's n, for the per-surface form ranking
MIN_GRASS_FLOOR = 15  # grass is scarce -- lower, explicitly declared floor
TOURS = ("ATP", "WTA")
WINDOWS = (("career", None), ("recent_form", RECENT_FORM_START))


def _load_matches() -> tuple[pd.DataFrame, list[str]]:
    """Glob matches*.parquet, concat, dedupe on event_id, assert winner in
    {1, 2} (fail-closed), return (frame, found relative filenames)."""
    files = sorted(glob.glob(_MATCHES_GLOB))
    if not files:
        raise FileNotFoundError(f"no matches*.parquet found under {_MATCHES_GLOB}")
    frames = [pd.read_parquet(f) for f in files]
    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["event_id"])
    bad_winners = set(df["winner"].dropna().unique()) - {1, 2}
    if bad_winners:
        raise ValueError(f"unexpected winner values, fail-closed: {sorted(bad_winners)}")
    rel = [str(Path(f).resolve().relative_to(REPO_ROOT)).replace("\\", "/") for f in files]
    return df, rel


def _long_format(matches: pd.DataFrame) -> pd.DataFrame:
    """One row per (match, perspective) -- p1's and p2's -- restricted to
    Hard/Clay/Grass surfaces (Unknown/Carpet dropped)."""
    cols = ["event_id", "date", "tour", "surface"]
    p1 = matches[cols + ["p1_id", "p1_name", "winner"]].rename(
        columns={"p1_id": "player_id", "p1_name": "player_name"})
    p1["win"] = (p1["winner"] == 1).astype(int)
    p2 = matches[cols + ["p2_id", "p2_name", "winner"]].rename(
        columns={"p2_id": "player_id", "p2_name": "player_name"})
    p2["win"] = (p2["winner"] == 2).astype(int)
    long_df = pd.concat([p1, p2], ignore_index=True).drop(columns=["winner"])
    return long_df[long_df["surface"].isin(SURFACES)]


def _build_snapshot(long_df: pd.DataFrame, tour: str, window_start: str | None) -> pd.DataFrame:
    """One row per player_id qualifying for `tour` in the declared window:
    hard_wr/hard_n, clay_wr/clay_n, grass_wr/grass_n, ov_wr/ov_n (pooled
    across the three surfaces only)."""
    sub = long_df[long_df["tour"].str.upper() == tour]
    if window_start is not None:
        sub = sub[sub["date"] >= window_start]
    wins = sub.pivot_table(index="player_id", columns="surface", values="win", aggfunc="sum", fill_value=0)
    ns = sub.pivot_table(index="player_id", columns="surface", values="win", aggfunc="count", fill_value=0)
    names = sub.drop_duplicates(subset=["player_id"]).set_index("player_id")["player_name"]

    out = pd.DataFrame(index=wins.index)
    out["player_name"] = names
    for surf, col in (("Hard", "hard"), ("Clay", "clay"), ("Grass", "grass")):
        n = ns.get(surf, pd.Series(0, index=out.index))
        w = wins.get(surf, pd.Series(0, index=out.index))
        out[f"{col}_n"] = n.astype(int)
        out[f"{col}_wr"] = w.astype(float) / n.replace(0, float("nan")).astype(float)
    out["ov_n"] = out[["hard_n", "clay_n", "grass_n"]].sum(axis=1).astype(int)
    ov_wins = wins.reindex(columns=list(SURFACES), fill_value=0).sum(axis=1)
    out["ov_wr"] = ov_wins.astype(float) / out["ov_n"].replace(0, float("nan")).astype(float)
    return out.reset_index()


def _write_snapshot(snapshot: pd.DataFrame, tour: str, window_label: str) -> str:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUT_DIR / f"tennis_surface_context_snapshot_{tour.lower()}_{window_label}.parquet"
    pq.write_table(pa.Table.from_pandas(snapshot, preserve_index=False), out_path)
    return str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")


_CONFOUND_CAVEAT = (
    "opponent-strength confound: who a player faces on one surface differs "
    "systematically from another (draws are not random) -- a surface gap partly "
    "reflects scheduling/seeding, not surface skill alone."
)
_RETIREMENT_CAVEAT = (
    "retirement rows are counted as DECIDED matches (winner column is authoritative "
    "regardless of retirement) -- a declared choice; a retirement win is not the same "
    "signal as a played-out win."
)
_SURFACE_CAVEAT = "Hard/Clay/Grass only -- Unknown/Carpet surface rows are excluded from every computation."
_DESCRIPTIVE_CAVEAT = "DESCRIPTIVE_ONLY -- not a forecast of a future match; no market/$ edge claimed."


def _ranking_from(snapshot: pd.DataFrame, floor_cols: dict[str, int], metric_col: str,
                   ascending: bool) -> tuple[list[dict[str, Any]], int, int]:
    n_considered = len(snapshot)
    mask = pd.Series(True, index=snapshot.index)
    for col, floor in floor_cols.items():
        mask &= snapshot[col].fillna(0) >= floor
    qualifiers = snapshot[mask].dropna(subset=[metric_col]).copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values(metric_col, ascending=ascending).reset_index(drop=True)
    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        entry = {
            "rank": i,
            "player_id": int(row.player_id),
            "player_name": str(row.player_name),
            "value": round(float(getattr(row, metric_col)), 4),
        }
        for col in floor_cols:
            entry[col] = int(getattr(row, col))
        ranking.append(entry)
    return ranking, n_considered, n_excluded


def _claim(claim_id: str, question: str, formula: str, metric: str, window_label: str,
           min_sample: dict[str, int], direction: str, ranking: list[dict[str, Any]],
           source_rel: str, n_considered: int, n_excluded: int, extra_caveats: list[str]) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": question,
        "criteria": {
            "metric": metric,
            "formula": formula,
            "window": window_label,
            "min_sample": min_sample,
            "direction": direction,
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [source_rel],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [_DESCRIPTIVE_CAVEAT, _SURFACE_CAVEAT, _RETIREMENT_CAVEAT, _CONFOUND_CAVEAT, *extra_caveats],
    }


def _claims_for_combo(snapshot: pd.DataFrame, tour: str, window_label: str, source_rel: str) -> list[dict[str, Any]]:
    """Builds all 6 candidate claims for one (tour, window) combo, then drops
    any whose ranking came back empty (skip idiom -- rails: never publish an
    empty ranking; a floor that eliminates every player in this combo means
    there is nothing honest to rank, not a claim to emit with an empty list)."""
    tl = tour.lower()
    candidates = []

    # (1) surface win-rate gap: clay specialists (desc) + hard specialists (asc)
    gap = snapshot.copy()
    gap["clay_minus_hard"] = gap["clay_wr"] - gap["hard_wr"]
    floor = {"clay_n": MIN_GAP_FLOOR, "hard_n": MIN_GAP_FLOOR}
    for direction_name, ascending in (("clay_specialists", False), ("hard_specialists", True)):
        ranking, n_c, n_e = _ranking_from(gap, floor, "clay_minus_hard", ascending)
        candidates.append(_claim(
            f"tennis_surface_context_gap_{direction_name}_{tl}_{window_label}",
            f"Which {tour} players lean most {'clay' if not ascending else 'hard'}-favoring "
            f"({window_label.replace('_', ' ')})?",
            "clay_wr - hard_wr", "clay_minus_hard", window_label,
            floor, "desc" if not ascending else "asc", ranking, source_rel, n_c, n_e,
            [f"min_sample floor clay_n>={MIN_GAP_FLOOR} AND hard_n>={MIN_GAP_FLOOR} in this window."],
        ))

    # (2) surface form ranking: top win rate per surface
    for surf, col in (("Hard", "hard"), ("Clay", "clay"), ("Grass", "grass")):
        ranking, n_c, n_e = _ranking_from(snapshot, {f"{col}_n": MIN_FORM_FLOOR}, f"{col}_wr", False)
        candidates.append(_claim(
            f"tennis_surface_context_form_{col}_{tl}_{window_label}",
            f"Who has the best {surf} win rate among {tour} players ({window_label.replace('_', ' ')})?",
            f"{col}_wr", f"{col}_wr", window_label,
            {f"{col}_n": MIN_FORM_FLOOR}, "desc", ranking, source_rel, n_c, n_e,
            [f"min_sample floor {col}_n>={MIN_FORM_FLOOR} in this window."],
        ))

    # (3) grass adaptability: grass_wr - ov_wr (lower floor -- grass is scarce)
    adapt = snapshot.copy()
    adapt["grass_adapt"] = adapt["grass_wr"] - adapt["ov_wr"]
    ranking, n_c, n_e = _ranking_from(adapt, {"grass_n": MIN_GRASS_FLOOR}, "grass_adapt", False)
    candidates.append(_claim(
        f"tennis_surface_context_grass_adapt_{tl}_{window_label}",
        f"Which {tour} players over/under-perform their overall win rate on grass "
        f"({window_label.replace('_', ' ')})?",
        "grass_wr - ov_wr", "grass_adapt", window_label,
        {"grass_n": MIN_GRASS_FLOOR}, "desc", ranking, source_rel, n_c, n_e,
        [f"min_sample floor grass_n>={MIN_GRASS_FLOOR} (lower than the {MIN_FORM_FLOOR}/{MIN_GAP_FLOOR} "
         "floors elsewhere: grass tour dates are scarce, a stricter floor would empty this ranking)."],
    ))
    return [c for c in candidates if c["ranking"]]


def build_all_claims() -> list[dict[str, Any]]:
    matches, found_files = _load_matches()
    long_df = _long_format(matches)
    claims: list[dict[str, Any]] = []
    for tour in TOURS:
        for window_label, window_start in WINDOWS:
            snapshot = _build_snapshot(long_df, tour, window_start)
            source_rel = _write_snapshot(snapshot, tour, window_label)
            combo_claims = _claims_for_combo(snapshot, tour, window_label, source_rel)
            for c in combo_claims:
                c["caveats"].append(f"source corpus files found: {found_files}")
            claims.extend(combo_claims)
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit tennis surface-context claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = build_all_claims()
    out_path = write_claims(claims, Path(args.output))
    for claim in claims:
        top1 = claim["ranking"][0] if claim["ranking"] else None
        print(f"{claim['claim_id']}: n_considered={claim['n_considered']} "
              f"n_excluded_below_floor={claim['n_excluded_below_floor']} top1={top1}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
