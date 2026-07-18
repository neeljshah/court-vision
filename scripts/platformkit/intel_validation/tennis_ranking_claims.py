"""Tennis ranking-dynamics claims producer "tennis_ranking" (2026-07-18 build
spec: only genuinely-missing tennis family -- no existing store answers
"does the higher-ranked player usually win", "which surface/level has the
most upsets", "how often do seeds win at Slams", or "what is player X's
current rank" today).

STEP-0 PREMISE (verified via python -c column dumps): matches.parquet (ATP)
and wta_matches.parquet (WTA) share an IDENTICAL schema (p1_rank/p2_rank/
winner/surface/tourney_level/date/p1_id/p2_id), so higher-rank-wins/rank_gap
is computed HERE directly from those plain columns for BOTH tours uniformly
-- atlas_h2h.parquet's precomputed equivalents are ATP-only and carry no
event_id (can't cleanly re-key), so depending on it would break tour
symmetry for a 3-line formula this module can compute itself. asof_meta.
parquet (seed columns) IS ATP-only (verified: 100% event_id overlap with
matches.parquet, 0% with wta_matches) -- seed_hold_rate is ATP-only, stated
as scope, not built for WTA.

METRICS (DESCRIPTIVE, no forecast -- p1_rank/p2_rank are a genuine pre-match
observable, only `winner` is post-match; no walk-forward/OOS claim is made):
  higher_rank_win_rate by 3 cuts (surface in {Hard,Clay,Grass}; tourney_level;
  rank_gap bucket in {1-5,6-20,21-50,50+}) -- TWO ranking claims per cut
  (desc="favorites dominate", asc="most upset-prone"), same two-direction-
  of-one-column idiom as tennis_surface_context_claims.py's clay/hard pair.
  seed_hold_rate by tourney_level (ATP only): share of seeded-vs-unseeded
  matches the seeded player wins (both-seeded/both-unseeded excluded --
  undefined "seed effect", stated in caveats).
  player_rank_snapshot: each player's LAST-SEEN match rank (not rank_points
  -- rank works both tours, rank_points needs the ATP-only asof_meta join).
  NOT a live ladder: corpus ends ~2025/2026, "last seen in this corpus,"
  same honest limit the build spec's own unanswerable table already states
  for "who is #1 today."

CONFOUNDS: retirements counted as decided (winner authoritative regardless);
draws/seeding are not random, so a gap partly reflects scheduling, not pure
skill -- same confound tennis_surface_context_claims.py already states.

CLI:
    python -m scripts.platformkit.intel_validation.tennis_ranking_claims
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
_MATCHES = {"atp": REPO_ROOT / "data" / "domains" / "tennis" / "matches.parquet",
            "wta": REPO_ROOT / "data" / "domains" / "tennis" / "wta_matches.parquet"}
_ASOF_META_ATP = REPO_ROOT / "data" / "domains" / "tennis" / "asof_meta.parquet"

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "tennis_ranking_claims.jsonl"

TOURS = ("atp", "wta")
SURFACES = ("Hard", "Clay", "Grass")  # Unknown/Carpet excluded, same scope as tennis_surface_context
CUT_FLOOR = 100  # matches-in-cut, declared (thousands of matches/tour; a defensible floor vs small-cut noise)

_DESCRIPTIVE_CAVEAT = "DESCRIPTIVE ranking only -- no forecast, no market/$ edge claimed."
_CONFOUND_CAVEAT = (
    "CONFOUNDS: retirements counted as decided (winner authoritative regardless); "
    "draws/seeding are not random, so a surface/level win-rate gap partly reflects "
    "scheduling, not pure skill."
)


def _bucket_rank_gap(gap: float) -> str:
    if gap <= 5:
        return "1-5"
    if gap <= 20:
        return "6-20"
    if gap <= 50:
        return "21-50"
    return "50+"


def _match_favorite_frame(matches: pd.DataFrame) -> pd.DataFrame:
    """Per-match favorite/underdog frame, computed straight from p1_rank/
    p2_rank/winner (works identically for ATP matches.parquet and WTA
    wta_matches.parquet -- same 20-col schema). Ties and missing ranks are
    excluded (an undefined "who is higher-ranked")."""
    df = matches.dropna(subset=["p1_rank", "p2_rank", "winner"]).copy()
    df = df[df["p1_rank"] != df["p2_rank"]]
    favorite_is_p1 = df["p1_rank"] < df["p2_rank"]
    df["higher_rank_wins"] = ((df["winner"] == 1) & favorite_is_p1) | ((df["winner"] == 2) & ~favorite_is_p1)
    df["rank_gap"] = (df["p1_rank"] - df["p2_rank"]).abs()
    df["rank_gap_bucket"] = df["rank_gap"].map(_bucket_rank_gap)
    return df


def _cut_snapshot(df: pd.DataFrame, cut_col: str) -> pd.DataFrame:
    g = df.groupby(cut_col)
    return pd.DataFrame({cut_col: g.size().index, "higher_rank_win_rate": g["higher_rank_wins"].mean().values,
                          "n": g.size().values})


def _write_snapshot(df: pd.DataFrame, name: str) -> Path:
    out_path = _OUT_DIR / name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out_path)
    return out_path


def _cut_ranking_claims(df: pd.DataFrame, cut_col: str, cut_label: str, tour: str) -> list[dict[str, Any]]:
    """Both directions (desc="favorites dominate", asc="most upset-prone")
    off ONE cut snapshot -- same two-direction-of-one-column idiom as
    tennis_surface_context_claims.py's clay/hard specialist pair."""
    snapshot = _cut_snapshot(df, cut_col)
    n_considered = len(snapshot)
    qualifiers = snapshot[snapshot["n"] >= CUT_FLOOR]
    n_excluded = n_considered - len(qualifiers)
    if qualifiers.empty:
        return []
    out_path = _write_snapshot(snapshot, f"tennis_ranking_snapshot_{cut_label}_{tour}.parquet")
    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    tour_label = tour.upper()
    claims = []
    for direction_name, ascending in (("favorites_dominate", False), ("most_upset_prone", True)):
        ranked = qualifiers.sort_values("higher_rank_win_rate", ascending=ascending).reset_index(drop=True)
        ranking = [
            {"rank": i + 1, cut_col: getattr(row, cut_col),
             "value": round(float(row.higher_rank_win_rate), 4), "n": int(row.n)}
            for i, row in enumerate(ranked.itertuples(index=False))
        ]
        claims.append({
            "claim_id": f"tennis_ranking_{cut_label}_{direction_name}_{tour}",
            "kind": "ranking",
            "question": (
                f"Which {cut_label.replace('_', ' ')} is most upset-prone on the {tour_label} tour?"
                if ascending else
                f"On which {cut_label.replace('_', ' ')} does the higher-ranked {tour_label} player "
                "win most often?"
            ),
            "criteria": {
                "metric": "higher_rank_win_rate", "formula": "higher_rank_win_rate",
                "window": f"career_{tour}", "min_sample": {"n": CUT_FLOOR},
                "direction": "asc" if ascending else "desc", "value_precision": 4, "entity_key": cut_col,
            },
            "ranking": ranking,
            "source_files": [rel_source],
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "n_considered": n_considered,
            "n_excluded_below_floor": n_excluded,
            "caveats": [_DESCRIPTIVE_CAVEAT, _CONFOUND_CAVEAT,
                        f"min_sample floor n>={CUT_FLOOR} matches in this cut."],
        })
    return claims


def _seed_hold_claim(tour: str = "atp") -> dict[str, Any] | None:
    """ATP only: asof_meta.p1_seed/p2_seed has zero WTA overlap (verified).
    seed_hold_rate = share of matches, among those where EXACTLY ONE side is
    seeded, that the seeded player wins."""
    if tour != "atp":
        return None
    matches = pd.read_parquet(_MATCHES["atp"])
    meta = pd.read_parquet(_ASOF_META_ATP)
    df = matches.merge(meta[["event_id", "p1_seed", "p2_seed"]], on="event_id", how="inner")
    df = df.dropna(subset=["winner"])
    p1_seeded, p2_seeded = df["p1_seed"].notna(), df["p2_seed"].notna()
    df = df[p1_seeded ^ p2_seeded].copy()
    seeded_is_p1 = df["p1_seed"].notna()
    df["seed_hold"] = ((df["winner"] == 1) & seeded_is_p1) | ((df["winner"] == 2) & ~seeded_is_p1)

    g = df.groupby("tourney_level")
    snapshot = pd.DataFrame({"tourney_level": g.size().index, "seed_hold_rate": g["seed_hold"].mean().values,
                              "n": g.size().values})
    n_considered = len(snapshot)
    qualifiers = snapshot[snapshot["n"] >= CUT_FLOOR]
    n_excluded = n_considered - len(qualifiers)
    if qualifiers.empty:
        return None
    out_path = _write_snapshot(snapshot, "tennis_ranking_snapshot_seed_atp.parquet")
    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    ranked = qualifiers.sort_values("seed_hold_rate", ascending=False).reset_index(drop=True)
    ranking = [
        {"rank": i + 1, "tourney_level": row.tourney_level, "value": round(float(row.seed_hold_rate), 4),
         "n": int(row.n)}
        for i, row in enumerate(ranked.itertuples(index=False))
    ]
    return {
        "claim_id": "tennis_ranking_seed_hold_rate_by_level_atp",
        "kind": "ranking",
        "question": "How often does the seeded player win at each ATP tournament level (e.g. Slams='G')?",
        "criteria": {
            "metric": "seed_hold_rate", "formula": "seed_hold_rate", "window": "career_atp",
            "min_sample": {"n": CUT_FLOOR}, "direction": "desc", "value_precision": 4,
            "entity_key": "tourney_level",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            _DESCRIPTIVE_CAVEAT, _CONFOUND_CAVEAT,
            f"min_sample floor n>={CUT_FLOOR} matches in this level where EXACTLY ONE side was seeded "
            "(both-seeded and both-unseeded matches excluded -- undefined 'seed effect').",
            "ATP only: asof_meta.p1_seed/p2_seed has zero overlap with WTA event_ids on disk.",
        ],
    }


def _player_rank_snapshot_claim(tour: str) -> dict[str, Any] | None:
    """Each player's LAST-SEEN match rank (not a live ladder -- corpus ends
    ~2025/2026, stated explicitly)."""
    matches = pd.read_parquet(_MATCHES[tour])
    keep = ["player_id", "player_name", "date", "rank"]
    p1 = matches.rename(columns={"p1_id": "player_id", "p1_name": "player_name", "p1_rank": "rank"})[keep]
    p2 = matches.rename(columns={"p2_id": "player_id", "p2_name": "player_name", "p2_rank": "rank"})[keep]
    long_df = pd.concat([p1, p2], ignore_index=True).dropna(subset=["rank"])
    long_df["date"] = pd.to_datetime(long_df["date"])
    snapshot = long_df.sort_values("date", kind="mergesort").groupby("player_id", as_index=False).tail(1)
    if snapshot.empty:
        return None
    cols = snapshot[["player_id", "player_name", "rank"]].reset_index(drop=True)
    out_path = _write_snapshot(cols, f"tennis_ranking_snapshot_players_{tour}.parquet")
    rel_source = str(out_path.relative_to(REPO_ROOT)).replace("\\", "/")
    ranked = snapshot.sort_values("rank", ascending=True).reset_index(drop=True)
    ranking = [
        {"rank": i + 1, "player_id": int(row.player_id), "player_name": str(row.player_name),
         "value": round(float(getattr(row, "rank")), 4), "n": 1}
        for i, row in enumerate(ranked.itertuples(index=False))
    ]
    tour_label = tour.upper()
    return {
        "claim_id": f"tennis_ranking_player_snapshot_{tour}",
        "kind": "ranking",
        "question": f"What is each {tour_label} player's most recently observed ranking in this corpus?",
        "criteria": {
            "metric": "rank", "formula": "rank", "window": f"last_seen_{tour}", "min_sample": {},
            "direction": "asc", "value_precision": 4, "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": len(snapshot),
        "n_excluded_below_floor": 0,
        "caveats": [
            _DESCRIPTIVE_CAVEAT,
            "NOT a live/authoritative current ladder: this is the player's LAST-SEEN rank in this "
            "on-disk corpus (which ends ~2025/early-2026), not today's real ATP/WTA ranking.",
        ],
    }


def build_all_claims() -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for tour in TOURS:
        matches = pd.read_parquet(_MATCHES[tour])
        fav = _match_favorite_frame(matches)
        surf = fav[fav["surface"].isin(SURFACES)]
        for cut_col, cut_label, cut_df in (
            ("surface", "surface", surf), ("tourney_level", "tourney_level", fav),
            ("rank_gap_bucket", "rank_gap_bucket", fav),
        ):
            claims.extend(_cut_ranking_claims(cut_df, cut_col, cut_label, tour))
        seed_claim = _seed_hold_claim(tour)
        if seed_claim:
            claims.append(seed_claim)
        player_claim = _player_rank_snapshot_claim(tour)
        if player_claim:
            claims.append(player_claim)
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit tennis ranking-dynamics claims (ATP+WTA)")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

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
