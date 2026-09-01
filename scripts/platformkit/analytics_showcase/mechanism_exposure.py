"""Pregame mechanism exposure sheets.

This artifact computes NO new statistics -- it is a relevance join over rows
that already passed their own validation. It is DESCRIPTIVE_ONLY: the sheet
only reports whether declared schedule conditions are live for a game.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from scripts.platformkit.analytics_showcase import mechanism_wiring

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_JSON = Path(__file__).parent / "out" / "mechanism_exposure.json"
SPORTS = ("basketball_nba", "mlb", "soccer", "tennis")
NO_NEW_NUMBERS = ("This artifact computes NO new statistics -- it is a relevance join over rows "
                  "that already passed their own validation.")
# Exact section slugs only. Entries that do not exist as CONFIRMED sections are
# deliberately inert; no approximate title matching is performed.
TRIGGER_REGISTRY = {
    "is_b2b": {"threshold": 1, "slugs": ["back_to_back_b2b_rest_penalty"]},
    "three_in_four": {"threshold": 3, "slugs": ["three_in_four_fatigue", "three_in_four_fatigue_local_null"]},
    "rest_advantage": {"threshold": 2, "slugs": ["rest_advantage"]},
}


def slugify(value: str) -> str:
    """Return the declared, ASCII section key used by the trigger registry."""
    value = re.sub(r"^\d+\.\s*", "", value).lower()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def parse_mechanisms(path: Path) -> list[dict]:
    """Parse confirmed/replicated mechanism sections and preserve quote lines."""
    sections = re.split(r"^###\s+", path.read_text(encoding="utf-8"), flags=re.M)[1:]
    parsed = []
    for section in sections:
        lines = section.splitlines()
        if not lines:
            continue
        status = next((line for line in lines[1:] if line.startswith("- **status**:")), None)
        if status is None or not ("CONFIRMED" in status or "REPLICATED" in status):
            continue
        name = lines[0].strip()
        quote = [line for line in lines[1:] if "measured" in line.lower() or "effect" in line.lower()]
        parsed.append({"mechanism": name, "slug": slugify(name),
                       "ledger_status": status.split(":", 1)[1].strip(), "ledger_quote": quote})
    return parsed


def ledger_confirmed_count(path: Path) -> int:
    """Count ledger verdict rows that are confirmed or replicated."""
    rows = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return sum("CONFIRMED" in str(row.get("verdict", "")) or "REPLICATED" in str(row.get("verdict", ""))
               for row in rows)


def load_schedule(path: Path) -> pd.DataFrame:
    """Load the complete schedule at its declared game/date/team grain."""
    if not path.exists():
        raise FileNotFoundError(f"required schedule input is absent: {path}")
    schedule = pd.read_parquet(path, columns=["date", "home_team", "away_team"]).copy()
    schedule["date"] = pd.to_datetime(schedule["date"]).dt.normalize()
    schedule = schedule.drop_duplicates(["date", "home_team", "away_team"]).sort_values(
        ["date", "away_team", "home_team"], kind="stable").reset_index(drop=True)
    schedule["game_id"] = [f"{d.date()}-{a}-{h}-{i}" for i, (d, a, h) in
                           enumerate(zip(schedule.date, schedule.away_team, schedule.home_team))]
    return schedule


def _team_history(schedule: pd.DataFrame, team: str, game_date: pd.Timestamp) -> list[pd.Timestamp]:
    """Return only schedule dates available as of this game date."""
    dates = schedule.loc[(schedule.date <= game_date) &
                         ((schedule.home_team == team) | (schedule.away_team == team)), "date"]
    return sorted(dates.drop_duplicates().tolist())


def _team_flags(schedule: pd.DataFrame, team: str, game_date: pd.Timestamp) -> dict:
    dates = _team_history(schedule, team, game_date)
    prior = [date for date in dates if date < game_date]
    last = prior[-1] if prior else None
    rest_days = None if last is None else int((game_date - last).days - 1)
    return {"is_b2b": bool(last is not None and (game_date - last).days == 1),
            "three_in_four": sum(date >= game_date - pd.Timedelta(days=3) for date in dates) >= 3,
            "rest_days": rest_days}


def _trigger_evidence(home: dict, away: dict) -> dict[str, dict]:
    rest_values = [home["rest_days"], away["rest_days"]]
    differential = None if None in rest_values else abs(rest_values[0] - rest_values[1])
    return {
        "is_b2b": {"name": "is_b2b", "value": {"home": home["is_b2b"], "away": away["is_b2b"]}, "threshold": 1},
        "three_in_four": {"name": "three_in_four", "value": {"home": home["three_in_four"], "away": away["three_in_four"]}, "threshold": 3},
        "rest_advantage": {"name": "rest_advantage", "value": differential, "threshold": 2,
                           "home_rest_days": home["rest_days"], "away_rest_days": away["rest_days"]},
    }


def game_sheets(schedule: pd.DataFrame, mechanisms: list[dict],
                column_exposures: dict[tuple, list[dict]] | None = None) -> list[dict]:
    """Emit NBA sheets using only schedule facts dated no later than each game.

    ``column_exposures`` carries the as-of-column trigger evidence keyed by
    (date, home_team, away_team); those mechanisms are wired by declared column,
    the schedule triggers below by declared schedule condition.
    """
    by_slug = {row["slug"]: row for row in mechanisms}
    column_exposures = column_exposures or {}
    sheets = []
    for game in schedule.itertuples(index=False):
        home, away = _team_flags(schedule, game.home_team, game.date), _team_flags(schedule, game.away_team, game.date)
        evidence = _trigger_evidence(home, away)
        live = {"is_b2b": home["is_b2b"] or away["is_b2b"],
                "three_in_four": home["three_in_four"] or away["three_in_four"],
                "rest_advantage": evidence["rest_advantage"]["value"] is not None and evidence["rest_advantage"]["value"] >= 2}
        exposures = []
        for trigger, enabled in live.items():
            if enabled:
                for slug in TRIGGER_REGISTRY[trigger]["slugs"]:
                    if slug in by_slug:
                        row = by_slug[slug]
                        exposures.append({"mechanism": row["mechanism"], "ledger_status": row["ledger_status"],
                                          "ledger_quote": row["ledger_quote"], "trigger_evidence": evidence[trigger]})
        key = (game.date.strftime("%Y-%m-%d"), game.home_team, game.away_team)
        seen = {row["mechanism"] for row in exposures}
        for hit in column_exposures.get(key, []):
            row = by_slug.get(hit["slug"])
            if row is not None and row["mechanism"] not in seen:
                exposures.append({"mechanism": row["mechanism"], "ledger_status": row["ledger_status"],
                                  "trigger_evidence": hit["trigger_evidence"]})
        sheets.append({"game_id": game.game_id, "date": game.date.strftime("%Y-%m-%d"),
                       "home_team": game.home_team, "away_team": game.away_team, "exposures": exposures})
    return sheets


def sport_rollup(mechanisms: list[dict], sheets: list[dict] | None = None) -> dict:
    """Report wiring coverage without concealing non-wired confirmed sections."""
    schedule_slugs = {slug for spec in TRIGGER_REGISTRY.values() for slug in spec["slugs"]}
    column_slugs = set(mechanism_wiring.TESTABLE)
    declared = set(mechanism_wiring.WIRING)
    wired = [row for row in mechanisms if row["slug"] in schedule_slugs or row["slug"] in declared]
    not_wired = [row["mechanism"] for row in mechanisms
                 if row["slug"] not in schedule_slugs and row["slug"] not in declared]
    sheets = sheets or []
    live = sum(bool(sheet["exposures"]) for sheet in sheets)
    return {"confirmed_total": len(mechanisms), "wired": len(wired), "not_wired": not_wired,
            "wired_by_schedule_trigger": sum(row["slug"] in schedule_slugs for row in mechanisms),
            "wired_by_asof_column": sum(row["slug"] in column_slugs for row in mechanisms),
            "wired_not_testable": sum(row["slug"] in declared and row["slug"] not in column_slugs
                                      for row in mechanisms),
            "pct_games_with_live_mechanism": round(100.0 * live / len(sheets), 3) if sheets else 0.0}


def build(root: Path = REPO_ROOT) -> dict:
    """Build the declared-input artifact and fail before writing on any guard breach."""
    confirmed = {}
    ledger_counts = {}
    for sport in SPORTS:
        knowledge = root / "domains" / sport / "knowledge"
        confirmed[sport] = parse_mechanisms(knowledge / "mechanisms.md")
        ledger_counts[sport] = ledger_confirmed_count(knowledge / "validation_ledger.jsonl")
        low, high = len(confirmed[sport]), ledger_counts[sport]
        assert low and high and max(low, high) <= 2 * min(low, high), (
            f"{sport}: mechanisms confirmed={low}, ledger confirmed={high}; mismatch exceeds 2x")
    schedule = load_schedule(root / "data" / "domains" / "basketball_nba" / "odds.parquet")
    index = mechanism_wiring.matchup_index(root)
    by_game = mechanism_wiring.column_exposures(sorted(set(index.values())), root)
    sheets = game_sheets(schedule, confirmed["basketball_nba"],
                         {key: by_game[game] for key, game in index.items() if by_game.get(game)})
    examples = sorted(sheets, key=lambda row: (not bool(row["exposures"]), row["date"], row["game_id"]))[:3]
    return {"label": "DESCRIPTIVE_ONLY", "edge_claimed": False,
            "as_of": schedule.date.max().strftime("%Y-%m-%d"), "generated_at": datetime.now(timezone.utc).isoformat(),
            "no_new_numbers_claim": NO_NEW_NUMBERS,
            "source": "domains/<sport>/knowledge/mechanisms.md + data/domains/basketball_nba/odds.parquet",
            "ledger_cross_check": {sport: {"parsed_confirmed": len(confirmed[sport]),
                                             "ledger_confirmed": ledger_counts[sport]} for sport in SPORTS},
            "per_sport": {sport: sport_rollup(confirmed[sport], sheets if sport == "basketball_nba" else []) for sport in SPORTS},
            "example_game_sheets": examples, "game_sheets": sheets}


def main() -> None:
    result = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="ascii")
    print("wrote", OUT_JSON)
    for sport, values in result["per_sport"].items():
        print(sport, "wired", values["wired"], "not_wired", len(values["not_wired"]))


if __name__ == "__main__":
    main()
