"""NPB + KBO DESCRIPTIVE team-strength ranking claims producer (PROGRAM v3
breadth lane npb-kbo-strength-claims).

Emits FULL-population, per-league team-strength claims (every team above a
stated games-played floor, no top-N cap) straight from the OWNED game-level
results parquets (data/domains/kbo/kbo_results.parquet,
data/domains/npb/npb_results.parquet -- the wave-42 REBUILT 3,964-row NPB
corpus, row count asserted at build time), in the SAME claims contract shape
as wnba_claims.py / soccer_intl_strength_claims.py, zero code sharing with
the independent claims_validator.py.

THREE DIMENSIONS PER LEAGUE (6 claims total, split across this module + the
siblings npb_kbo_claims_io.py (snapshot-building I/O) and
npb_kbo_claims_home_away.py (the home/away split dimension) to keep every
file <=300 LOC, same precedent as wnba_claims.py's wnba_claims_ext.py/
ext2.py + basketball_claims.py/_dims.py/_io.py sibling splits):
  win_pct              -- team wins / decided games (ties excluded from the
                           denominator; a tie is neither a win nor a loss).
                           THIS module.
  run_diff_per_game    -- (runs_for - runs_against) / games, over ALL games
                           the team played (home or away), signed for the
                           team. THIS module.
  home_win_pct / away_win_pct -- the SAME team's win rate split by venue
                           role -- SIBLING module npb_kbo_claims_home_away.py
                           (reuses this module's snapshot builder/helpers).

WHY A PER-TEAM SIDE SNAPSHOT (not criteria.aggregate): the source parquet is
GAME-level and WIDE (one row per game, home_team/away_team/home_score/
away_score columns) -- a team's record is scattered across two asymmetric
roles (home rows AND away rows), which the claims contract's
criteria.aggregate.group_by path (a single bare group_by COLUMN) cannot
express in one groupby. Rather than touch the independent validator (RAILS:
claims_validator.py is UNMODIFIED), this producer follows the SAME
precedent as soccer_intl_strength_claims.py / tennis_h2h_claims.py:
pre-aggregate to a per-team side parquet (one row per team with plain
numeric columns already computed) and go through the validator's PLAIN
(non-aggregate) formula path -- the validator still independently
recomputes each ranking straight off that on-disk parquet (zero import of
this module), it just recomputes from pre-materialized per-team sums rather
than re-deriving them from raw game rows.

MIN-SAMPLE FLOOR: n_games>=30 -- a plain "enough games played this
league/window to not be single-week noise" floor (NPB's own corpus has 2
sparse-history team codes at n=8 each, evidently early-era franchise/code
artifacts; KBO's 10 teams all clear 600+). Every team below the floor is
counted honestly in n_excluded_below_floor, never silently dropped.

CAVEAT (binding, per lane brief): these are DESCRIPTIVE standings-derived
strength numbers over the full on-disk corpus (2022-2026 season rows) --
NOT a predictor, NOT a market/calibration claim. The existing NPB/KBO
PREGAME gate verdict (data/domains/{kbo,npb}/pregame_gate_verdict.json) and
the in-game base-fit verdict (ingame_base_fit_verdict.json, both leagues
HONEST_NEGATIVE) are SEPARATE, already-adjudicated artifacts this module
does not touch, replace, or contradict.

NON-ASCII TEAM NAMES: 13/14 NPB team codes are Japanese-script strings.
json.dumps' default ensure_ascii=True escapes them to \\uXXXX (still valid
ASCII bytes, so the ascii-encoding claims-file write never fails); CLI print
output instead uses an ascii-safe repr (never raw-prints a non-ASCII team
code to the cp1252 console).

NETWORK: zero. Pure pandas over already-materialized parquets.
DESCRIPTIVE ONLY -- NO MARKET EDGE CLAIMED, NO GATE, NO CALIBRATION CLAIM.

CLI:
    python -m scripts.platformkit.intel_validation.npb_kbo_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.platformkit.intel_validation.npb_kbo_claims_io import build_league_snapshot

REPO_ROOT = Path(__file__).resolve().parents[3]

_KBO_RESULTS = REPO_ROOT / "data" / "domains" / "kbo" / "kbo_results.parquet"
_NPB_RESULTS = REPO_ROOT / "data" / "domains" / "npb" / "npb_results.parquet"

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "npb_kbo_claims.jsonl"
_KBO_SNAPSHOT_OUT = _OUT_DIR / "kbo_team_strength_snapshot.parquet"
_NPB_SNAPSHOT_OUT = _OUT_DIR / "npb_team_strength_snapshot.parquet"

MIN_N_GAMES = 30  # plain "enough games this corpus" floor; excludes NPB's 2 sparse (n=8) team codes
NPB_EXPECTED_ROWCOUNT = 3964  # wave-42 rebuild row count (pre-rebuild dates were corrupted)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _ascii_safe(text: str) -> str:
    """Non-ASCII-safe repr for stdout (13/14 NPB team codes are Japanese
    script; the cp1252 console cannot print them raw)."""
    return text.encode("ascii", errors="backslashreplace").decode("ascii")


def npb_rowcount_check(results_path: Path | None = None) -> tuple[bool, int]:
    """Verify the NPB corpus on disk still has the wave-42 rebuilt row count
    before trusting it. Returns (matches, actual_rowcount)."""
    df = pd.read_parquet(results_path if results_path is not None else _NPB_RESULTS)
    n = len(df)
    return n == NPB_EXPECTED_ROWCOUNT, n


def rank_desc(
    table: pd.DataFrame, *, value_col: str, n_col: str, min_n: int,
) -> tuple[list[dict[str, Any]], int, int]:
    """Full-population ranking (no top-N cap): every row clearing n_col>=
    min_n ranked desc by value_col. Returns (ranking, n_considered,
    n_excluded_below_floor). Shared by this module + npb_kbo_claims_home_away."""
    n_considered = len(table)
    qualifiers = table[table[n_col] >= min_n].copy()
    qualifiers = qualifiers.dropna(subset=[value_col])
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values(value_col, ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            "team": str(row.team),
            "player_name": str(row.team),  # ask()'s cross-sport ranking display-name key
            "value": round(float(getattr(row, value_col)), 4),
            "n": int(getattr(row, n_col)),
        })
    return ranking, n_considered, n_excluded


def base_caveats(league: str, as_of_iso: str, floor_note: str) -> list[str]:
    """Shared trailing caveat block (floor rationale + full-pop + descriptive
    disclaimer + separate-gate-verdict disclaimer). Reused by the sibling
    home/away module."""
    return [
        f"{floor_note} min_sample floor n_games>={MIN_N_GAMES} -- plain 'enough games played "
        "this corpus' rationale; excludes small-sample/early-era team codes (NPB has 2 such "
        "codes at n=8 games each in this checkout).",
        "FULL POPULATION: every team clearing the floor is ranked, no top-N cap -- below-floor "
        "teams are counted in n_excluded_below_floor, never silently dropped.",
        f"DESCRIPTIVE standings-derived team-strength ranking over the full on-disk {league} "
        f"results corpus as-of {as_of_iso} -- NOT a predictor, NOT a market/$ edge claim, NOT "
        "a calibration claim.",
        f"The existing {league} PREGAME gate verdict and in-game base-fit verdict "
        f"(data/domains/{league.lower()}/pregame_gate_verdict.json, "
        "ingame_base_fit_verdict.json) are SEPARATE, already-adjudicated artifacts this claim "
        "does not touch, replace, or contradict.",
    ]


def build_win_pct_claim(league: str, snapshot_path: Path, as_of_iso: str, n_considered: int) -> dict[str, Any]:
    table = pd.read_parquet(snapshot_path)
    table["win_pct"] = table["wins"] / table["decided_games"]
    ranking, _n_considered, n_excluded = rank_desc(
        table, value_col="win_pct", n_col="games", min_n=MIN_N_GAMES,
    )
    return {
        "claim_id": f"{league.lower()}_team_win_pct_full_asof_{as_of_iso}",
        "kind": "ranking",
        "question": (
            f"Which {league} teams have the best overall win percentage "
            f"(full population above floor, as-of {as_of_iso})?"
        ),
        "criteria": {
            "metric": "win_pct",
            "formula": "wins / decided_games",
            "window": f"asof_{as_of_iso}_{league.lower()}",
            "window_spec": {"kind": "season", "season": None, "n": None, "order_by": None},
            "min_sample": {"games": MIN_N_GAMES},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "team",
        },
        "ranking": ranking,
        "source_files": [_rel(snapshot_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "win_pct = wins / decided_games (ties excluded from the denominator -- a tie is "
            f"neither a win nor a loss), from {_rel(snapshot_path)} (built over the full "
            f"data/domains/{league.lower()}/{league.lower()}_results.parquet game-level corpus).",
            *base_caveats(league, as_of_iso, "win_pct"),
        ],
    }


def build_run_diff_claim(league: str, snapshot_path: Path, as_of_iso: str, n_considered: int) -> dict[str, Any]:
    table = pd.read_parquet(snapshot_path)
    table["run_diff_per_game"] = (table["runs_for"] - table["runs_against"]) / table["games"]
    ranking, _n_considered, n_excluded = rank_desc(
        table, value_col="run_diff_per_game", n_col="games", min_n=MIN_N_GAMES,
    )
    return {
        "claim_id": f"{league.lower()}_team_run_diff_per_game_full_asof_{as_of_iso}",
        "kind": "ranking",
        "question": (
            f"Which {league} teams have the best run differential per game "
            f"(full population above floor, as-of {as_of_iso})?"
        ),
        "criteria": {
            "metric": "run_diff_per_game",
            "formula": "(runs_for - runs_against) / games",
            "window": f"asof_{as_of_iso}_{league.lower()}",
            "window_spec": {"kind": "season", "season": None, "n": None, "order_by": None},
            "min_sample": {"games": MIN_N_GAMES},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "team",
        },
        "ranking": ranking,
        "source_files": [_rel(snapshot_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "run_diff_per_game = (runs_for - runs_against) / games, summed across both home and "
            f"away roles, from {_rel(snapshot_path)} (built over the full "
            f"data/domains/{league.lower()}/{league.lower()}_results.parquet game-level corpus).",
            *base_caveats(league, as_of_iso, "run_diff_per_game"),
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def build_league_claims(league: str, results_path: Path, snapshot_out: Path) -> list[dict[str, Any]]:
    # Lazy import (not module-level): the sibling imports rank_desc/base_caveats
    # FROM this module, so this module cannot import it back at load time --
    # only safe once both modules are fully defined, i.e. here, inside the call.
    from scripts.platformkit.intel_validation import npb_kbo_claims_home_away as home_away

    snapshot_path, as_of_iso, n_considered = build_league_snapshot(
        league, results_path, snapshot_out, _OUT_DIR,
    )
    home_claim, away_claim = home_away.build_home_away_split_claims(
        league, snapshot_path, as_of_iso, n_considered,
    )
    return [
        build_win_pct_claim(league, snapshot_path, as_of_iso, n_considered),
        build_run_diff_claim(league, snapshot_path, as_of_iso, n_considered),
        home_claim,
        away_claim,
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NPB + KBO DESCRIPTIVE team-strength ranking claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    npb_matches, npb_rows = npb_rowcount_check()
    if not npb_matches:
        print(
            f"REFUSING: NPB corpus row count {npb_rows} != expected {NPB_EXPECTED_ROWCOUNT} "
            "(wave-42 rebuild) -- pre-rebuild dates were corrupted, do not trust a mismatched corpus"
        )
        return 1

    claims = [
        *build_league_claims("KBO", _KBO_RESULTS, _KBO_SNAPSHOT_OUT),
        *build_league_claims("NPB", _NPB_RESULTS, _NPB_SNAPSHOT_OUT),
    ]
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        top1 = c["ranking"][0] if c["ranking"] else None
        top1_safe = _ascii_safe(str(top1)) if top1 is not None else None
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} top1={top1_safe}")
    print(f"npb_rowcount_check: {npb_rows} == {NPB_EXPECTED_ROWCOUNT} (OK)")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
