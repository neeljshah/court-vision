"""NBA "lineup context" claim family (new lane nba_lineup_context) -- four
on/off DELTA rankings over the existing lineup-reconstruction parquets.

CRITICAL HONESTY RULE (binding, user-established): every claim here is an
on/off DELTA (net rating, teammate eFG%, gravity, rim protection while on
the floor vs off). These deltas are NOT causal player-impact measurements --
who shares the floor with a player correlates with coach trust, opponent
strength, and garbage-time usage (the ROSTER CONFOUND). Every claim carries
label="DESCRIPTIVE_ONLY" and a caveat naming that confound verbatim; none
is promoted to a predictive/edge claim without an earned predictive-validity
receipt (predictive_validity/ harness, not built here).

PREREGISTERED FLOORS (declared here BEFORE any scoring code runs):
  net_rating_delta / teammate_efg_lift (on_off_<season>.parquet):
      min_on >= 500, min_off >= 300, n_games >= 30
  gravity_proxy (gravity_proxy_<season>.parquet, already-computed column):
      min_on >= 300, n_games >= 20
  rim_protection_delta (zone_onoff_<season>.parquet):
      min_on >= 500, min_off >= 300, n_games >= 30,
      rim_fga_on >= 30, rim_fga_off >= 20

SOURCES: full, unfiltered per-entity parquets built by
domains/basketball_nba/lineups/{on_off,gravity_spacing,zone_onoff}.py --
same "point at the full population, apply the floor here" precedent as
nba_on_off_claims.py / nba_gravity_proxy_claims.py, so claims_validator.py's
plain-formula path re-derives both the value AND the floor independently.

Pair-keyed entity (player_id, team_id) throughout -- same rationale as the
sibling on_off/gravity claims (mid-window trades put >1 team_id under some
player_ids). The 5th claim in the family (spacing best/worst per team) lives
in nba_lineup_context_spacing.py (separate module, this file is at the
300-LOC rail already) and is combined into the SAME output store by main().

NETWORK: zero. CLI:
    python -m scripts.platformkit.intel_validation.nba_lineup_context_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/nba_lineup_context_claims.jsonl \
        --output data/cache/intel_claims/nba_lineup_context_claims_validation.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_LINEUPS_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "nba_lineup_context_claims.jsonl"

# season window -> human corpus descriptor (same convention as the sibling
# on_off/gravity_proxy/lineup_spacing claim families).
SEASONS = {"2024_25": "1230-game", "2025_26": "196-game"}

ON_OFF_MIN_ON = 500.0
ON_OFF_MIN_OFF = 300.0
ON_OFF_MIN_GAMES = 30
GRAVITY_MIN_ON = 300.0
GRAVITY_MIN_GAMES = 20
RIM_MIN_ON = 500.0
RIM_MIN_OFF = 300.0
RIM_MIN_GAMES = 30
RIM_MIN_FGA_ON = 30
RIM_MIN_FGA_OFF = 20

ROSTER_CONFOUND_CAVEAT = (
    "ROSTER CONFOUND: this on/off delta is NOT a causal player-impact estimate -- "
    "who shares the floor with a player correlates with coach trust, opponent "
    "strength, and garbage-time usage, and none of those are controlled for here. "
    "DESCRIPTIVE_ONLY until an earned predictive-validity receipt says otherwise."
)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _ranking_row(i: int, row: Any, value: float) -> dict[str, Any]:
    return {
        "rank": i, "player_id": int(row.player_id), "team_id": int(row.team_id),
        "player_name": str(row.player_name), "value": round(float(value), 4),
        "n": round(float(row.min_on), 2),
    }


def _delta_claim(
    *, df: pd.DataFrame, mask: pd.Series, value_col: str, src: Path, season: str,
    claim_id: str, question: str, metric: str, formula: str, min_sample: dict[str, Any],
    extra_caveats: list[str],
) -> dict[str, Any]:
    n_considered = len(df)
    q = df[mask].copy()
    n_excluded = n_considered - len(q)
    q = q.sort_values(value_col, ascending=False).reset_index(drop=True)
    ranking = [_ranking_row(i, row, getattr(row, value_col))
               for i, row in enumerate(q.itertuples(index=False), start=1)]
    return {
        "claim_id": claim_id, "kind": "ranking", "label": "DESCRIPTIVE_ONLY",
        "question": question,
        "criteria": {
            "metric": metric, "formula": formula,
            "window": f"season_{season}_nba_lineup_corpus", "min_sample": min_sample,
            "direction": "desc", "value_precision": 4, "entity_key": ["player_id", "team_id"],
        },
        "ranking": ranking, "source_files": [_rel(src)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered, "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [ROSTER_CONFOUND_CAVEAT, *extra_caveats,
                    "FULL POPULATION above floor, no top-N cap. DESCRIPTIVE_ONLY -- "
                    "NOT a gate, no market/$ edge claimed."],
    }


def build_net_rating_delta_claim(season: str = "2025_26") -> dict[str, Any]:
    src = _LINEUPS_DIR / f"on_off_{season}.parquet"
    df = pd.read_parquet(src)
    df["net_rating_delta"] = df["net_rating_on_per48"] - df["net_rating_off_per48"]
    mask = (
        (df["min_on"] >= ON_OFF_MIN_ON) & (df["min_off"] >= ON_OFF_MIN_OFF)
        & (df["n_games"] >= ON_OFF_MIN_GAMES) & df["net_rating_delta"].notna()
    )
    return _delta_claim(
        df=df, mask=mask, value_col="net_rating_delta", src=src, season=season,
        claim_id=f"nba_lineup_context_net_rating_delta_{season}",
        question=(f"Which NBA players' teams have the biggest net-rating swing between them "
                  f"on vs. off the floor ({SEASONS[season]} {season} slice)?"),
        metric="net_rating_delta", formula="net_rating_on_per48 - net_rating_off_per48",
        min_sample={"min_on": ON_OFF_MIN_ON, "min_off": ON_OFF_MIN_OFF, "n_games": ON_OFF_MIN_GAMES},
        extra_caveats=[
            "net_rating_delta = net_rating_on_per48 - net_rating_off_per48 from "
            f"{_rel(src)} (stint-level attribution, {SEASONS[season]} {season} PBP corpus).",
        ],
    )


def build_teammate_efg_lift_claim(season: str = "2025_26") -> dict[str, Any]:
    src = _LINEUPS_DIR / f"on_off_{season}.parquet"
    df = pd.read_parquet(src)
    df["teammate_efg_lift"] = df["teammate_efg_on"] - df["teammate_efg_off"]
    mask = (
        (df["min_on"] >= ON_OFF_MIN_ON) & (df["min_off"] >= ON_OFF_MIN_OFF)
        & (df["n_games"] >= ON_OFF_MIN_GAMES) & df["teammate_efg_lift"].notna()
    )
    return _delta_claim(
        df=df, mask=mask, value_col="teammate_efg_lift", src=src, season=season,
        claim_id=f"nba_lineup_context_teammate_efg_lift_{season}",
        question=(f"Whose teammates shoot the best eFG% with them on the floor vs. off it "
                  f"({SEASONS[season]} {season} slice)?"),
        metric="teammate_efg_lift", formula="teammate_efg_on - teammate_efg_off",
        min_sample={"min_on": ON_OFF_MIN_ON, "min_off": ON_OFF_MIN_OFF, "n_games": ON_OFF_MIN_GAMES},
        extra_caveats=[
            "teammate_efg_lift = teammate_efg_on - teammate_efg_off from "
            f"{_rel(src)} -- 'teammates shoot better with him on', a DESCRIPTIVE association, "
            "not a validated gravity/spacing-creation measurement.",
        ],
    )


def build_gravity_proxy_claim(season: str = "2025_26") -> dict[str, Any]:
    src = _LINEUPS_DIR / f"gravity_proxy_{season}.parquet"
    df = pd.read_parquet(src)
    mask = (
        (df["min_on"] >= GRAVITY_MIN_ON) & (df["n_games"] >= GRAVITY_MIN_GAMES)
        & df["gravity_proxy"].notna()
    )
    return _delta_claim(
        df=df, mask=mask, value_col="gravity_proxy", src=src, season=season,
        claim_id=f"nba_lineup_context_gravity_proxy_{season}",
        question=(f"Which NBA players carry the strongest already-computed gravity proxy "
                  f"({SEASONS[season]} {season} slice)?"),
        metric="gravity_proxy", formula="gravity_proxy",
        min_sample={"min_on": GRAVITY_MIN_ON, "n_games": GRAVITY_MIN_GAMES},
        extra_caveats=[
            f"gravity_proxy is read as-is (already computed) from {_rel(src)} -- see "
            "domains/basketball_nba/lineups/gravity_spacing.py for its own build_gravity().",
        ],
    )


def build_rim_protection_claim(season: str = "2025_26") -> dict[str, Any]:
    src = _LINEUPS_DIR / f"zone_onoff_{season}.parquet"
    df = pd.read_parquet(src)
    df["rim_protection_delta"] = df["rim_efg_allowed_off"] - df["rim_efg_allowed_on"]
    mask = (
        (df["min_on"] >= RIM_MIN_ON) & (df["min_off"] >= RIM_MIN_OFF)
        & (df["n_games"] >= RIM_MIN_GAMES) & (df["rim_fga_on"] >= RIM_MIN_FGA_ON)
        & (df["rim_fga_off"] >= RIM_MIN_FGA_OFF) & df["rim_protection_delta"].notna()
    )
    return _delta_claim(
        df=df, mask=mask, value_col="rim_protection_delta", src=src, season=season,
        claim_id=f"nba_lineup_context_rim_protection_delta_{season}",
        question=(f"Which NBA players cut opponent rim eFG% the most while on the floor vs. "
                  f"off it ({SEASONS[season]} {season} slice)?"),
        metric="rim_protection_delta", formula="rim_efg_allowed_off - rim_efg_allowed_on",
        min_sample={
            "min_on": RIM_MIN_ON, "min_off": RIM_MIN_OFF, "n_games": RIM_MIN_GAMES,
            "rim_fga_on": RIM_MIN_FGA_ON, "rim_fga_off": RIM_MIN_FGA_OFF,
        },
        extra_caveats=[
            "rim_protection_delta = rim_efg_allowed_off - rim_efg_allowed_on (positive = "
            f"opponents shoot WORSE at the rim while this player is on) from {_rel(src)} "
            "(defensive-side zone attribution).",
        ],
    )


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kept = [c for c in claims if c["ranking"]]
    for c in claims:
        if not c["ranking"]:
            print(f"SKIP {c['claim_id']}: 0 of {c['n_considered']} rows clear "
                  f"min_sample floor -- claim not emitted")
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in kept:
            f.write(json.dumps(claim) + "\n")
    return out_path


def build_all_claims(seasons: list[str] | None = None) -> list[dict[str, Any]]:
    from scripts.platformkit.intel_validation.nba_lineup_context_spacing import build_spacing_claims

    seasons = seasons or list(SEASONS)
    claims: list[dict[str, Any]] = []
    for season in seasons:
        claims.append(build_net_rating_delta_claim(season))
        claims.append(build_teammate_efg_lift_claim(season))
        claims.append(build_gravity_proxy_claim(season))
        claims.append(build_rim_protection_claim(season))
        claims.extend(build_spacing_claims(season))
    return claims


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit NBA lineup-context claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    parser.add_argument("--season", type=str, default="all", choices=[*SEASONS, "all"])
    args = parser.parse_args(argv)

    seasons = list(SEASONS) if args.season == "all" else [args.season]
    claims = build_all_claims(seasons)
    out_path = write_claims(claims, Path(args.output))
    for claim in claims:
        if not claim["ranking"]:
            continue
        print(
            f"{claim['claim_id']}: n_considered={claim['n_considered']} "
            f"n_excluded_below_floor={claim['n_excluded_below_floor']} "
            f"top1={json.dumps(claim['ranking'][0])}"
        )
    print(f"wrote {len([c for c in claims if c['ranking']])} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
