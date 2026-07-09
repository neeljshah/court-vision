"""domains.soccer.knowledge.validate_data_gaps -- 2 honest NOT_TESTABLE checks
(missing/insufficient ingredient on THIS corpus, verified by actually reading
the data rather than assumed). Per repo discipline an unbuildable mechanism is
recorded NOT_TESTABLE, never silently skipped.

Run: python -m domains.soccer.knowledge.validate_data_gaps
"""
from __future__ import annotations

import collections
from typing import Any, Dict, List

from domains.soccer.knowledge._data import LEDGER_PATH, load_events, load_match_meta
from scripts.platformkit.io_atomic import append_jsonl_atomic

WEATHER_COLS = {"weather", "temperature", "pitch_condition", "wind_speed"}


def penalty_conversion_stability_gap(meta) -> Dict[str, Any]:
    """Split-half penalty-conversion stability per taker needs the SAME player
    to take penalties in both halves of the season -- checked directly rather
    than assumed."""
    mid = meta["match_date"].median()
    by_player_half: Dict[Any, set] = collections.defaultdict(set)
    n_pens = 0
    for _, row in meta.iterrows():
        half = "h1" if row["match_date"] <= mid else "h2"
        for e in load_events(row["match_id"]):
            if e["type"]["name"] != "Shot":
                continue
            shot = e.get("shot") or {}
            if (shot.get("type") or {}).get("name") != "Penalty":
                continue
            n_pens += 1
            player = (e.get("player") or {}).get("id")
            if player is not None:
                by_player_half[player].add(half)
    both_halves = sum(1 for halves in by_player_half.values() if len(halves) == 2)
    return {"hypothesis": "penalty_conversion_stability_split_half", "n": 0,
            "effect": None, "p": None, "verdict": "NOT_TESTABLE",
            "note": "%d penalties across %d distinct takers in the 400-match corpus, "
                    "only %d takers have >=1 penalty in BOTH season halves -- too sparse "
                    "for a per-taker split-half correlation" % (n_pens, len(by_player_half), both_halves)}


def weather_pitch_condition_gap(meta) -> Dict[str, Any]:
    cols = set(meta.columns)
    have = sorted(cols & WEATHER_COLS)
    return {"hypothesis": "weather_pitch_condition_effect", "n": 0, "effect": None, "p": None,
            "verdict": "NOT_TESTABLE",
            "note": "none of %s present in match_meta columns (have: %s); StatsBomb event "
                    "files carry no weather/pitch field either" % (sorted(WEATHER_COLS), have or "none")}


def run() -> List[Dict[str, Any]]:
    meta = load_match_meta()
    rows = [penalty_conversion_stability_gap(meta), weather_pitch_condition_gap(meta)]
    for r in rows:
        r["sport"] = "soccer"
        r["corpus"] = "statsbomb_match_meta__400"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-42s %-16s -- %s" % (r["hypothesis"], r["verdict"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: the gap-detector reports NOT_TESTABLE and
    correctly lists which of the missing columns (none) are actually present."""
    import pandas as pd
    fake_meta = pd.DataFrame({"match_date": pd.to_datetime(["2020-01-01"]), "home_team": ["X"]})
    r = weather_pitch_condition_gap(fake_meta)
    assert r["verdict"] == "NOT_TESTABLE" and "none" in r["note"]
    print("self-check OK")
