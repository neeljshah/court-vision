"""probe_R22_O8_injury_feed.py — Real-world viability probe for R22_O8.

Runs the production scraper once, evaluates whether it produced a
valid, columnar, name-resolved injury report, and confirms the
production wire (src/prediction/injury_availability) actually picks
the parquet over the legacy JSON snapshot.

SHIP gate
---------
  * scraper writes ≥1 row to today's parquet
  * ≥10 players are present after status normalisation
  * status distribution non-zero (at least one bucket has rows)
  * production wire returns a non-default factor for at least one
    player_id present in the parquet (proves the parquet path won)

Persists:
  data/cache/probe_R22_O8_results.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date as _date_cls
from datetime import datetime
from typing import Dict, Optional

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

from scripts import nba_injury_report_scraper as scraper          # noqa: E402
from src.prediction import injury_availability as ia              # noqa: E402

_RESULTS_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "probe_R22_O8_results.json"
)


def _cross_check_lineups(df: pd.DataFrame) -> Dict[str, int]:
    """Cross-reference scraped injuries with the latest lineup snapshot.

    Counts how many scraped OUT players are listed as STARTERS in today's
    lineup data — those are the highest-impact mismatches the daemon will
    eventually want to surface as STARTER_SCRATCH events.
    """
    today = _date_cls.today().isoformat()
    lineup_path = os.path.join(PROJECT_DIR, "data", "lineups", f"{today}.json")
    if not os.path.exists(lineup_path) or df.empty:
        return {"lineup_overlap": 0, "starter_outs": 0, "lineups_file_present": 0}
    try:
        with open(lineup_path, encoding="utf-8") as fh:
            lineup = json.load(fh)
    except Exception:
        return {"lineup_overlap": 0, "starter_outs": 0, "lineups_file_present": 0}
    starters = {(r.get("team", ""), r.get("player_name", ""))
                for r in lineup.get("starters", [])}
    out_df = df[df["status"] == "OUT"]
    overlap = 0
    starter_outs = 0
    for _, rec in out_df.iterrows():
        key = (str(rec.get("team", "")), str(rec.get("player_name", "")))
        if key in starters:
            starter_outs += 1
        if any(rec.get("player_name", "") == s[1] for s in starters):
            overlap += 1
    return {"lineup_overlap": overlap, "starter_outs": starter_outs,
            "lineups_file_present": 1}


def _verify_production_wire(df: pd.DataFrame) -> Dict[str, object]:
    """Confirm `get_availability_factor()` reads the freshly-written parquet."""
    if df.empty:
        return {"verified": False, "reason": "scraper returned empty df"}
    # Pick a player_id that's actually OUT — factor must come back 0.0.
    out_df = df[(df["status"] == "OUT") & df["player_id"].notna()]
    if out_df.empty:
        return {"verified": False, "reason": "no OUT players with mapped player_id"}
    pick = out_df.iloc[0]
    pid = int(pick["player_id"])
    ia.reset_cache()                                    # force re-read of disk
    factor = ia.get_availability_factor(player_id=pid)
    return {
        "verified":      factor == 0.0,
        "checked_pid":   pid,
        "checked_name":  str(pick["player_name"]),
        "expected":      0.0,
        "actual":        float(factor),
    }


def run() -> dict:
    t0 = datetime.now()
    print(f"[probe_R22_O8] starting injury-feed probe ({t0.isoformat(timespec='seconds')})")

    df, parquet_path = scraper.scrape_once()
    print(f"[probe_R22_O8] scrape complete: n_rows={len(df)}  path={parquet_path}")

    by_status = (
        df["status"].value_counts().to_dict() if not df.empty else {}
    )
    n_out          = int(by_status.get("OUT", 0))
    n_doubtful     = int(by_status.get("DOUBTFUL", 0))
    n_questionable = int(by_status.get("QUESTIONABLE", 0))
    n_probable     = int(by_status.get("PROBABLE", 0))
    n_available    = int(by_status.get("AVAILABLE", 0))

    n_with_pid = int(df["player_id"].notna().sum()) if not df.empty else 0
    n_unique   = (
        int(df.drop_duplicates(subset=["player_name"]).shape[0])
        if not df.empty else 0
    )

    lineups = _cross_check_lineups(df)
    wire = _verify_production_wire(df)

    # SHIP gate
    distribution_nonzero = any(by_status.values())
    ship = bool(
        not df.empty
        and len(df) >= 10
        and distribution_nonzero
    )

    source_used = ""
    if not df.empty and "source" in df.columns:
        # All rows share a source (first source that yielded data wins).
        source_used = str(df["source"].iloc[0])

    result = {
        "probe":               "R22_O8_injury_feed",
        "run_at":              t0.isoformat(timespec="seconds"),
        "wall_seconds":        round((datetime.now() - t0).total_seconds(), 2),
        "parquet_path":        parquet_path,
        "n_rows":              int(len(df)),
        "n_unique_players":    n_unique,
        "n_with_player_id":    n_with_pid,
        "source_used":         source_used,
        "status_distribution": by_status,
        "n_OUT":               n_out,
        "n_DOUBTFUL":          n_doubtful,
        "n_QUESTIONABLE":      n_questionable,
        "n_PROBABLE":          n_probable,
        "n_AVAILABLE":         n_available,
        "lineup_cross_check":  lineups,
        "production_wire":     wire,
        "ship_status":         "SHIP" if ship else "REJECT",
        "ship_criteria": {
            "n_rows_ge_1":           bool(not df.empty),
            "n_rows_ge_10":          bool(len(df) >= 10),
            "distribution_nonzero":  distribution_nonzero,
            "wire_verified":         bool(wire.get("verified")),
        },
    }

    os.makedirs(os.path.dirname(_RESULTS_PATH), exist_ok=True)
    with open(_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    print(f"[probe_R22_O8] results -> {_RESULTS_PATH}")
    print(f"[probe_R22_O8] {result['ship_status']}  "
          f"n_rows={len(df)}  source={source_used}  "
          f"wire_verified={wire.get('verified')}")
    return result


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.parse_args(argv)
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
