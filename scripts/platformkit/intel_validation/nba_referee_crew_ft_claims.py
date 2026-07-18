"""Per-official FT/foul-environment descriptive claims (nba_referee_crew_ft).

DESCRIPTIVE only: for each NBA official, the mean per-game total PF
(personal fouls, both teams combined) and total FTA (free throw attempts,
both teams combined) across every game that official is listed as working.
This is a plain descriptive split -- "games officiated by X run foul/FT
-heavy or -light on average" -- NOT the crew_b2b_fatigue causal hypothesis
(scripts/platformkit/pod_sprint/crew_fatigue_r1.py, DEEP_FEATURES_PREREG.md
R1): no team-baseline adjustment, no rest-day conditioning, no confound
control, no prediction. edge_claimed is always False. See
.claude/rules/no-edge-claims.md.

SOURCE (real run, not exercised in this worktree -- see EVIDENCE NOTE):
  data/nba/officials/officials_<season>.json -- game_id -> list of 2-4
      official name strings per game (crew_fatigue_r1.py's own documented
      schema; officials are joined by exact name string, no ref-id column
      exists locally -- same known landmine, not fixed here).
  data/domains/basketball_nba/player_boxscores.parquet -- player-grain rows
      with game_id/team/pf/fta, summed to one game-total row (both teams).

An official/game pair only contributes if that game_id has a boxscore row
(inner join); officials whose games carry no boxscore data are excluded
from n_games entirely, counted honestly, never zero-filled.

EVIDENCE NOTE: this worktree is isolated -- data/ is absent here (verified
at build time: `data/nba/officials/` and `data/domains/basketball_nba/
player_boxscores.parquet` do not exist in this checkout), so no real
official/game counts can be produced or checked fresh in this session. Every
builder function below takes an injectable frame/dict so it is fully
testable against synthetic fixtures; `main()`'s default paths point at the
real files and are exercised on the RunPod post-merge, never faked here.

GRAMMAR NOTE: per-game team-summed PF/FTA, THEN per-official mean, is two
aggregation steps -- not expressible in claims_validator's single-groupby
aggregate grammar (sum/mean/count/count_distinct only -- claims_validator.py
:105, safe_formula.py:105). Same escape hatch as line_value_dispersion_
claims.py: this module performs both aggregation steps itself and writes a
snapshot parquet with the per-official mean already baked in; each claim's
criteria.formula is a plain IDENTITY column read off that snapshot
(aggregate=None).

CONTRACT: kind="ranking", edge_claimed=False. entity_key="entity_id" ==
official name. min_sample floor n_games>=20 games officiated (with boxscore
data) per official.

CLI:
    python -m scripts.platformkit.intel_validation.nba_referee_crew_ft_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/nba_referee_crew_ft_claims.jsonl \
        --output data/cache/intel_claims/nba_referee_crew_ft_claims_validation.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_OFFICIALS_DIR = REPO_ROOT / "data" / "nba" / "officials"
_BOX_PATH = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_SNAPSHOT_PATH = REPO_ROOT / "data" / "cache" / "intel_claims" / "nba_referee_crew_ft_snapshot.parquet"
_CLAIMS_OUT = REPO_ROOT / "data" / "cache" / "intel_claims" / "nba_referee_crew_ft_claims.jsonl"

FLOOR_GAMES = 20
SEASON_WINDOW = "alltime"
_SEASONS = ("2022-23", "2023-24", "2024-25", "2025-26")


def load_officials_by_season(seasons: tuple[str, ...] = _SEASONS,
                              officials_dir: Path | None = None) -> dict[str, dict[str, list[str]]]:
    """{season: {game_id: [official names]}} read from officials_<season>.json
    files. A missing season file is skipped honestly (no exception), same
    convention crew_fatigue_r1.py uses for seasons with no local file."""
    d = officials_dir or _OFFICIALS_DIR
    out: dict[str, dict[str, list[str]]] = {}
    for season in seasons:
        p = d / f"officials_{season}.json"
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as f:
            out[season] = json.load(f)
    return out


def build_crew_long(officials_by_season: dict[str, dict[str, list[str]]]) -> pd.DataFrame:
    """One row per (game_id, official) across all seasons present. Empty
    crew lists contribute zero rows."""
    rows = [
        {"game_id": game_id, "official": name}
        for crews in officials_by_season.values()
        for game_id, names in crews.items()
        for name in names
    ]
    return pd.DataFrame(rows, columns=["game_id", "official"])


def build_game_stats(player_box: pd.DataFrame) -> pd.DataFrame:
    """One row per game_id: total_pf, total_fta = both teams' player rows
    summed for that game."""
    return player_box.groupby("game_id", as_index=False).agg(
        total_pf=("pf", "sum"), total_fta=("fta", "sum"))


def build_snapshot(officials_by_season: dict[str, dict[str, list[str]]],
                    game_stats: pd.DataFrame) -> pd.DataFrame:
    """Per-official mean total_pf/total_fta across games with boxscore data.
    Officials whose games have no boxscore row are excluded from n_games
    entirely (inner join), counted via the caller's n_crew_rows vs n_games
    delta, never zero-filled."""
    crew_long = build_crew_long(officials_by_season)
    merged = crew_long.merge(game_stats, on="game_id", how="inner")
    agg = merged.groupby("official", as_index=False).agg(
        n_games=("game_id", "nunique"),
        mean_pf=("total_pf", "mean"),
        mean_fta=("total_fta", "mean"),
    )
    agg["entity_id"] = agg["official"]
    return agg[["entity_id", "official", "n_games", "mean_pf", "mean_fta"]]


def write_snapshot(snapshot: pd.DataFrame, out_path: Path = _SNAPSHOT_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot.to_parquet(out_path, index=False)
    return out_path


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


_CAVEATS = [
    "descriptive per-official foul/FT-attempt environment split, NOT an "
    "advantage, NOT a beatable gap, NOT a predictor -- no market/roi/dollar "
    "edge is claimed.",
    f"min_sample floor n_games>={FLOOR_GAMES} games officiated (with "
    "boxscore data) per official; below-floor officials are excluded and "
    "counted, never silently dropped.",
    "mean_pf/mean_fta = both teams' PF/FTA summed per game, then averaged "
    "across every game that official is listed as working -- no team-"
    "baseline adjustment, no rest-day/b2b conditioning, no confound "
    "control; NOT the crew_b2b_fatigue hypothesis test (see "
    "pod_sprint/crew_fatigue_r1.py for that causal-adjacent, prereg'd, "
    "controlled family).",
    "officials are joined by exact name string across season files -- no "
    "ref-id column exists locally; a spelling inconsistency across season "
    "files would split one official into two entities, uncorrected here.",
    "games whose game_id has no player_boxscores.parquet row are excluded "
    "from that official's n_games entirely, not zero-filled.",
]


def _build_ranking_claim(snapshot: pd.DataFrame, metric_col: str, label: str) -> dict[str, Any]:
    n_considered = len(snapshot)
    qualifiers = snapshot[snapshot["n_games"] >= FLOOR_GAMES].dropna(subset=[metric_col]).copy()
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values(metric_col, ascending=False).reset_index(drop=True)
    ranking = [
        {"rank": i, "entity_id": str(r.entity_id), "value": round(float(getattr(r, metric_col)), 6),
         "n_games": int(r.n_games)}
        for i, r in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return {
        "claim_id": f"nba_referee_crew_ft_{label}_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": f"NBA official {label.replace('_', ' ')} (both-teams-combined per game), "
                     f"{SEASON_WINDOW}?",
        "criteria": {
            "metric": metric_col, "formula": metric_col, "window": SEASON_WINDOW,
            "aggregate": None, "min_sample": {"n_games": FLOOR_GAMES}, "direction": "desc",
            "value_precision": 6, "entity_key": "entity_id",
        },
        "ranking": ranking,
        "source_files": [_rel(_SNAPSHOT_PATH)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": list(_CAVEATS),
    }


def build_all_claims(snapshot: pd.DataFrame) -> list[dict[str, Any]]:
    claims = [
        _build_ranking_claim(snapshot, "mean_pf", "mean_pf_environment"),
        _build_ranking_claim(snapshot, "mean_fta", "mean_fta_environment"),
    ]
    # An empty ranking means nothing cleared the floor -- claiming nothing is
    # not a claim, skip emission honestly (domains/mlb/profiles/claims.py
    # idiom) rather than shipping an UNVERIFIABLE row.
    kept = [c for c in claims if c["ranking"]]
    for c in claims:
        if not c["ranking"]:
            print(f"SKIP {c['claim_id']}: 0 of {c['n_considered']} officials clear "
                  f"min_sample floor -- claim not emitted")
    return kept


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA referee-crew FT/foul-environment DESCRIPTIVE claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    if not _OFFICIALS_DIR.exists() or not _BOX_PATH.exists():
        print(f"BLOCKED: source data absent locally -- {_OFFICIALS_DIR} exists="
              f"{_OFFICIALS_DIR.exists()}, {_BOX_PATH} exists={_BOX_PATH.exists()}. "
              "Run on the RunPod where data/ is present.")
        return 1

    officials_by_season = load_officials_by_season()
    player_box = pd.read_parquet(_BOX_PATH, columns=["game_id", "pf", "fta"])
    game_stats = build_game_stats(player_box)
    snapshot = build_snapshot(officials_by_season, game_stats)
    snapshot_path = write_snapshot(snapshot)
    claims = build_all_claims(snapshot)
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        top = c["ranking"][0] if c["ranking"] else None
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} n_ranked={len(c['ranking'])} "
              f"top={top}")
    print(f"wrote snapshot ({len(snapshot)} officials) -> {snapshot_path}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    if not claims:
        print("no claims cleared the floor -- nothing to validate")
        return 0

    from scripts.platformkit.intel_validation.validate_store import validate_and_write
    result = validate_and_write(str(out_path))
    print(f"validation: {result['n_verified']}/{result['n_claims']} verified, "
          f"{result['n_mismatch']} mismatch, {result['n_unverifiable']} unverifiable "
          f"-> {result['out']}")
    return 0 if (result["n_mismatch"] == 0 and result["n_unverifiable"] == 0) else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
