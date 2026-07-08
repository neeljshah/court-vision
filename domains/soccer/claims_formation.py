"""Soccer formation-vs-formation DESCRIPTIVE claims (statsbomb 400-match
corpus). SOURCE: data/cache/statsbomb/events/{match_id}.json (Starting XI
events -> tactics.formation per side) joined to data/cache/statsbomb/matches/
*.json (home_score/away_score/home_team_id/match_date -- GAME-DATED). Small
corpus (400 matches): only formation pairings with n>=MIN_N are ranked.

Builds ONE derived per-match SOURCE parquet (match_id, home_formation,
away_formation, pairing, is_home_win, is_draw, is_away_win, total_goals,
date) under data/cache/intel_claims/, then THREE ranking claims over
entity_key=pairing: home_win_rate, draw_rate, avg_total_goals.

DESCRIPTIVE only: no market/$ edge claimed, not a betting signal.

CLI: python -m domains.soccer.claims_formation
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_MATCHES_DIR = REPO_ROOT / "data" / "cache" / "statsbomb" / "matches"
_EVENTS_DIR = REPO_ROOT / "data" / "cache" / "statsbomb" / "events"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "soccer_formation_claims.jsonl"

MIN_N = 10  # min matches per formation pairing to rank it


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _fmt_formation(code: int) -> str:
    """statsbomb tactics.formation is a bare int like 4231 -> "4-2-3-1"."""
    return "-".join(str(code))


def _load_match_lookup(matches_dir: Path = _MATCHES_DIR) -> dict[int, dict]:
    lookup: dict[int, dict] = {}
    for fn in os.listdir(matches_dir):
        with open(matches_dir / fn, encoding="utf-8") as f:
            for m in json.load(f):
                lookup[m["match_id"]] = m
    return lookup


def build_source(
    match_lookup: Optional[dict[int, dict]] = None, events_dir: Path = _EVENTS_DIR,
) -> pd.DataFrame:
    """One row per event-file match with resolved home/away formation + result."""
    lookup = match_lookup if match_lookup is not None else _load_match_lookup()
    rows = []
    for fn in os.listdir(events_dir):
        match_id = int(fn.replace(".json", ""))
        meta = lookup.get(match_id)
        if meta is None or meta.get("home_score") is None:
            continue
        with open(events_dir / fn, encoding="utf-8") as f:
            events = json.load(f)
        home_id = meta["home_team"]["home_team_id"]
        away_id = meta["away_team"]["away_team_id"]
        home_form = away_form = None
        for e in events:
            if e.get("type", {}).get("name") != "Starting XI":
                continue
            team_id = e.get("team", {}).get("id")
            formation = (e.get("tactics") or {}).get("formation")
            if formation is None:
                continue
            if team_id == home_id:
                home_form = _fmt_formation(formation)
            elif team_id == away_id:
                away_form = _fmt_formation(formation)
        if home_form is None or away_form is None:
            continue
        home_score, away_score = meta["home_score"], meta["away_score"]
        rows.append({
            "match_id": match_id,
            "pairing": f"{home_form}_vs_{away_form}",
            "is_home_win": int(home_score > away_score),
            "is_draw": int(home_score == away_score),
            "is_away_win": int(home_score < away_score),
            "total_goals": home_score + away_score,
            "date": meta.get("match_date"),
        })
    return pd.DataFrame(rows)


def _rank(source: pd.DataFrame, value_col: str) -> tuple[list[dict], int, int]:
    grouped = source.groupby("pairing")[value_col]
    n = grouped.count()
    value = grouped.mean()
    table = pd.DataFrame({"n": n, "value": value}).reset_index()
    n_considered = len(table)
    qualifiers = table[table["n"] >= MIN_N].sort_values("value", ascending=False).reset_index(drop=True)
    n_excluded = n_considered - len(qualifiers)
    ranking = [
        {"rank": i, "pairing": row.pairing, "value": round(float(row.value), 4), "n": int(row.n)}
        for i, row in enumerate(qualifiers.itertuples(index=False), start=1)
    ]
    return ranking, n_considered, n_excluded


def _claim(claim_id: str, question: str, metric: str, value_col: str,
           src_path: Path, ranking: list[dict], n_considered: int, n_excluded: int) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": question,
        "criteria": {
            "metric": metric,
            "formula": f"mean({value_col})",
            "aggregate": {"group_by": "pairing", "derived": {"n": f"count({value_col})"}},
            "window": "statsbomb_400_match_corpus",
            "min_sample": {"n": MIN_N},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "pairing",
        },
        "ranking": ranking,
        "source_files": [_rel(src_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            "pairing = home_formation_vs_away_formation from statsbomb Starting XI tactics events; "
            "small corpus (400 matches) -- only pairings with n>=" + str(MIN_N) + " matches are ranked.",
            "DESCRIPTIVE split only -- not causal (opponent quality, competition tier, home advantage "
            "are not controlled for), no market/$ edge claimed.",
        ],
    }


def build_claims(out_dir: Path = _OUT_DIR) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    source = build_source()
    src_path = out_dir / "soccer_formation_source.parquet"
    source.to_parquet(src_path, index=False)

    claims = []
    for metric, col, label in (
        ("home_win_rate", "is_home_win", "home win rate"),
        ("draw_rate", "is_draw", "draw rate"),
        ("avg_total_goals", "total_goals", "average total goals"),
    ):
        ranking, n_considered, n_excluded = _rank(source, col)
        claims.append(_claim(
            f"soccer_formation_{metric}",
            f"Which home-vs-away formation pairings have the highest {label} (statsbomb 400-match corpus)?",
            metric, col, src_path, ranking, n_considered, n_excluded,
        ))
    return claims


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit soccer formation-pairing claims")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = build_claims()
    out_path = write_claims(claims, Path(args.output))

    print(f"wrote {len(claims)} claims -> {out_path}")
    for claim in claims:
        print(f"{claim['claim_id']}: n_considered={claim['n_considered']} "
              f"n_excluded_below_floor={claim['n_excluded_below_floor']} n_ranked={len(claim['ranking'])}")
        for row in claim["ranking"][:3]:
            print(f"  sample: {json.dumps(row)}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
