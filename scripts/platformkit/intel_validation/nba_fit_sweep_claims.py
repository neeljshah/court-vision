"""NBA fit-sweep claims producer (PROGRAM v3, lane fit-sweep).

Emits ONE ranking claim ranking every NBA team by a DECLARED, frozen
SCOUTING fit score for one player (default LeBron James, pid 2544),
composed ONLY from the three already-VERIFIED fit-ingredient claims this
lane's sibling (nba_fit_ingredient_claims.py) produces:

  nba_fit_archetype_profile_current              (player attribute profile)
  nba_fit_team_scheme_identity_current           (team scheme identity)
  nba_fit_role_vacancy_by_team_posgroup_current  (team x posgroup vacancy)

GATE VERDICT (read-only truth, never regenerated here):
data/domains/nba/fit_validity_gate_verdict.json returned REJECT on
2026-07-05 (n=417 moves, 5 folds, both planted nulls died) -- fit score
does NOT predict post-move performance. This module is SCOUTING/descriptive
composition ONLY, never a prediction; the REJECT citation is carried in
every claim's caveats.

DECLARED WEIGHTS (frozen BEFORE any sweep computation, 2026-07-05 -- never
tuned after seeing a single result): W_COMPLEMENT=0.40, W_SCHEME=0.35,
W_VACANCY=0.25. SCHEME_TAG_PERIM_WEIGHT is a declared, UNVALIDATED heuristic
mapping a team's dominant defensive scheme tag to how much its scheme_fit
ingredient weighs perimeter defense vs rim protection.

CONTRACT: kind="ranking", entity_key="team", aggregate path (criteria.
aggregate.group_by="team") so the independent claims_validator.py
(zero import of this module) recomputes fit_score straight from the
declared formula string + the materialized snapshot parquet.

NETWORK: zero. Pure pandas over the 3 VERIFIED claim rows (via
intel_query.ask.load_verified_claims) plus a materialized snapshot parquet.

CLI:
    python -m scripts.platformkit.intel_validation.nba_fit_sweep_claims
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

from scripts.platformkit.intel_query.ask import load_verified_claims

REPO_ROOT = Path(__file__).resolve().parents[3]

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_SNAPSHOT_PATH = _OUT_DIR / "nba_fit_sweep_lebron_snapshot.parquet"
_CLAIMS_OUT = _OUT_DIR / "nba_fit_sweep_claims.jsonl"

_ARCHETYPE_CLAIM_ID = "nba_fit_archetype_profile_current"
_SCHEME_CLAIM_ID = "nba_fit_team_scheme_identity_current"
_VACANCY_CLAIM_ID = "nba_fit_role_vacancy_by_team_posgroup_current"
_REQUIRED_CLAIM_IDS = (_ARCHETYPE_CLAIM_ID, _SCHEME_CLAIM_ID, _VACANCY_CLAIM_ID)

DEFAULT_PLAYER_PID = 2544
DEFAULT_PLAYER_NAME = "LeBron James"

# --- Declared BEFORE any sweep computation (2026-07-05). Frozen: never
# tuned after seeing results. ---
W_COMPLEMENT = 0.40
W_SCHEME = 0.35
W_VACANCY = 0.25

COMPLEMENT_AXES = (
    "creation", "playmaking", "spacing", "rim_pressure",
    "rebounding", "rim_protect", "perimeter_d", "self_create",
)

# w: scheme_fit = w*player.perimeter_d + (1-w)*player.rim_protect.
# Unknown tag -> 0.5. A declared, UNVALIDATED heuristic map.
SCHEME_TAG_PERIM_WEIGHT: dict[str, float] = {
    "SWITCH HEAVY": 1.0,
    "ISO FORCE": 1.0,
    "DROP COVERAGE": 0.0,
    "PAINT-FIRST DEFENSE": 0.0,
    "HELP DEFENSE": 0.5,
    "BALANCED": 0.5,
    "PACE CONTROL": 0.5,
}

MIN_ROSTER_N = 3  # n_roster floor applied to the SWEEP ranking (not the ingredients' own floors)


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)


def _build_formula(player: dict[str, Any]) -> str:
    """AGGREGATE-grammar formula string (safe_formula.evaluate_group_formula)
    algebraically identical to the producer-side fit_score computation."""
    terms = " + ".join(f"{player[a]}*(1-mean({a}))" for a in COMPLEMENT_AXES)
    return (
        f"{W_COMPLEMENT}*(({terms})/8) + "
        f"{W_SCHEME}*mean(scheme_fit) + {W_VACANCY}*mean(vacancy_share)"
    )


def build_sweep_snapshot(
    player_pid: int = DEFAULT_PLAYER_PID,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build the snapshot parquet + the single sweep ranking claim.

    Returns (claim_dict, unanswerable_teams). Fails closed with SystemExit
    if any of the 3 required VERIFIED ingredient claims is missing/not
    VERIFIED, or if player_pid has no row in the archetype claim.
    """
    verified = load_verified_claims()
    missing = [cid for cid in _REQUIRED_CLAIM_IDS if cid not in verified]
    if missing:
        raise SystemExit(f"nba_fit_sweep_claims: required VERIFIED claim(s) not available: {missing}")

    archetype_ranking = verified[_ARCHETYPE_CLAIM_ID].get("ranking", [])
    player = next((r for r in archetype_ranking if r.get("pid") == player_pid), None)
    if player is None:
        raise SystemExit(f"nba_fit_sweep_claims: player_pid={player_pid} has no row in {_ARCHETYPE_CLAIM_ID}")
    # NaN attr would render as identifier `nan` in the formula string and a
    # non-standard NaN JSON token -- fail closed like the other guards.
    bad = [a for a in COMPLEMENT_AXES
           if not isinstance(player.get(a), (int, float)) or player[a] != player[a]]
    if bad:
        raise SystemExit(f"nba_fit_sweep_claims: player_pid={player_pid} has non-numeric/NaN attribute(s) {bad}")
    posgroup = player["posgroup"]

    scheme_ranking = verified[_SCHEME_CLAIM_ID].get("ranking", [])
    scheme_by_team = {str(row["team"]).upper(): row for row in scheme_ranking}

    vacancy_ranking = verified[_VACANCY_CLAIM_ID].get("ranking", [])
    vacancy_by_team = {
        str(row["team"]).upper(): row for row in vacancy_ranking if row.get("posgroup") == posgroup
    }

    roster_by_team: dict[str, list[dict[str, Any]]] = {}
    for row in archetype_ranking:
        if row.get("pid") == player_pid:
            continue
        roster_by_team.setdefault(str(row["team"]).upper(), []).append(row)

    snapshot_rows: list[dict[str, Any]] = []
    unanswerable: list[dict[str, Any]] = []
    team_meta: dict[str, dict[str, Any]] = {}

    for team in sorted(scheme_by_team.keys()):
        vacancy_row = vacancy_by_team.get(team)
        roster_rows = roster_by_team.get(team, [])
        if vacancy_row is None:
            unanswerable.append({
                "team": team, "missing_ingredient": "role_vacancy",
                "reason": f"no VERIFIED role-vacancy row for team_posgroup={team}|{posgroup}",
            })
            continue
        if not roster_rows:
            unanswerable.append({
                "team": team, "missing_ingredient": "roster",
                "reason": f"no roster rows (excluding player_pid={player_pid}) for team={team}",
            })
            continue

        scheme_row = scheme_by_team[team]
        tag = scheme_row.get("dominant_tag")
        w = SCHEME_TAG_PERIM_WEIGHT.get(tag, 0.5)
        scheme_fit = w * float(player["perimeter_d"]) + (1 - w) * float(player["rim_protect"])
        vacancy_share = float(vacancy_row["value"])
        team_meta[team] = {"dominant_tag": tag, "vacancy_n": int(vacancy_row.get("n") or 0)}

        for r in roster_rows:
            row_dict: dict[str, Any] = {"team": team, "pid": int(r["pid"])}
            for a in COMPLEMENT_AXES:
                row_dict[a] = float(r[a])
            row_dict["scheme_fit"] = float(scheme_fit)
            row_dict["vacancy_share"] = vacancy_share
            snapshot_rows.append(row_dict)

    snapshot_df = pd.DataFrame(snapshot_rows)
    _write_parquet(snapshot_df, _SNAPSHOT_PATH)

    team_counts = snapshot_df.groupby("team").size() if not snapshot_df.empty else pd.Series(dtype="int64")
    n_considered = int(len(team_counts))
    n_excluded_below_floor = int((team_counts < MIN_ROSTER_N).sum())

    ranked: list[dict[str, Any]] = []
    for team, grp in (snapshot_df.groupby("team") if not snapshot_df.empty else []):
        n_roster = len(grp)
        if n_roster < MIN_ROSTER_N:
            continue
        roster_means = {a: float(grp[a].mean()) for a in COMPLEMENT_AXES}
        archetype_complement = sum(
            float(player[a]) * (1.0 - roster_means[a]) for a in COMPLEMENT_AXES
        ) / len(COMPLEMENT_AXES)
        scheme_fit = float(grp["scheme_fit"].iloc[0])
        vacancy_share = float(grp["vacancy_share"].iloc[0])
        fit_score = W_COMPLEMENT * archetype_complement + W_SCHEME * scheme_fit + W_VACANCY * vacancy_share
        ranked.append({
            "team": team, "fit_score": fit_score, "archetype_complement": archetype_complement,
            "scheme_fit": scheme_fit, "vacancy_share": vacancy_share, "n_roster": int(n_roster),
            "dominant_tag": team_meta[team]["dominant_tag"], "vacancy_n": team_meta[team]["vacancy_n"],
        })

    ranked.sort(key=lambda d: (-d["fit_score"], d["team"]))
    ranking = [
        {
            "rank": i, "team": d["team"], "value": round(d["fit_score"], 4), "n": d["n_roster"],
            "archetype_complement": round(d["archetype_complement"], 4),
            "scheme_fit": round(d["scheme_fit"], 4), "vacancy_share": round(d["vacancy_share"], 4),
            "dominant_tag": d["dominant_tag"], "vacancy_n": d["vacancy_n"],
        }
        for i, d in enumerate(ranked, start=1)
    ]

    rel_source = str(_SNAPSHOT_PATH.relative_to(REPO_ROOT)).replace("\\", "/")
    claim = {
        "claim_id": "nba_fit_sweep_lebron_james_current",
        "kind": "ranking",
        "question": (
            "Which team's current context best complements LeBron James's VERIFIED "
            "attribute profile (SCOUTING composition, current)?"
        ),
        "criteria": {
            "metric": "fit_score",
            "formula": _build_formula(player),
            "window": "current",
            "min_sample": {"n_roster": MIN_ROSTER_N},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "team",
            "aggregate": {"group_by": "team", "derived": {"n_roster": "count(pid)"}},
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded_below_floor,
        "unanswerable_teams": unanswerable,
        "declared_weights": {
            "archetype_complement": W_COMPLEMENT, "scheme_fit": W_SCHEME, "vacancy_share": W_VACANCY,
            "declared_at": "2026-07-05",
            "note": "declared before computation; never tuned against results",
        },
        "caveats": [
            "GATE VERDICT: fit-validity gate verdict: REJECT (2026-07-05; n=417 moves, 5 "
            "folds, both planted nulls died) -- fit score is NOT a forecast of post-move "
            "performance. SCOUTING/descriptive only.",
            "PROVENANCE: composed ONLY from the three VERIFIED fit-ingredient claims -- "
            f"{_ARCHETYPE_CLAIM_ID} (data/cache/team_system/player_roles.parquet), "
            f"{_SCHEME_CLAIM_ID} (data/cache/team_system/scheme_coverage.parquet), "
            f"{_VACANCY_CLAIM_ID} (DERIVED role-vacancy snapshot over player_boxscores "
            "joined to player_roles).",
            "DEFINITIONS: archetype_complement = mean over 8 attribute axes of "
            "player_attr*(1-team_roster_mean_attr), with the target player EXCLUDED from "
            "his own team's roster mean; scheme_fit = w*perimeter_d + (1-w)*rim_protect "
            "where w = SCHEME_TAG_PERIM_WEIGHT[dominant_tag] (a declared, UNVALIDATED "
            "heuristic map, default 0.5 for an unknown tag); vacancy_share = the "
            "team|posgroup role-vacancy claim's value (league-wide posgroup-median "
            "definition, see that claim's own caveats).",
            f"FLOORS: roster mpg>=10.0 inherited from the archetype claim, "
            f"n_roster>={MIN_ROSTER_N} applied here, vacancy n_players>=3 inherited from "
            "the role-vacancy claim.",
        ],
    }
    return claim, unanswerable


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA fit-sweep ranking claim for one player")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    parser.add_argument("--player-pid", type=int, default=DEFAULT_PLAYER_PID)
    args = parser.parse_args(argv)

    claim, unanswerable = build_sweep_snapshot(args.player_pid)
    out_path = write_claims([claim], Path(args.output))

    print(
        f"{claim['claim_id']}: n_considered={claim['n_considered']} "
        f"n_excluded_below_floor={claim['n_excluded_below_floor']} rows={len(claim['ranking'])}"
    )
    for r in claim["ranking"][:5]:
        print(f"  #{r['rank']} {r['team']} value={r['value']}")
    for u in unanswerable:
        print(f"  unanswerable: {u['team']} missing_ingredient={u['missing_ingredient']}")
    print(f"wrote 1 claim -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
