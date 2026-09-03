"""S136 -- the local factory screen over the ROUND-GRAIN tennis schedule-density / travel
tables, and the leak probe that says whether the round order actually removed the leak.

S122 built the WTA halves of both tables, measured that declaring them carries both families
over the frozen 0.8 coverage floor, and WITHHELD the declaration because the screen it unlocked
was a LEAK: Sackmann's `date` is the tourney START date, so the frozen builders count a window
that spans rounds played AFTER the match and assign the rolling result onto a duplicated date
index. The 2025 Wimbledon champion's seven matches served `0,3,4,5,1,6,2` and the served
p1-minus-p2 `matches_last_7d` correlated +0.2616 with the OUTCOME.

`domains/tennis/schedule_density_roundgrain.py` rebuilds both tables ordered by
`(tourney start date, ROUND)`, counting only rows strictly before at that grain. This script
declares the two families over the `_rg` sources FOR THE LIFE OF THE PROCESS ONLY -- nothing on
disk changes, `foundry/asof_supply.py` is owned by another lane -- and reports:

  --leak-probe  the champion's sequence and the served-value / outcome correlation on the same
                800-row screen window S122 used, so the before and after are comparable;
  --out-dir     the coverage the round-grain acquisition reaches and every T1 screen, with the
                CI recomputed from each trial's archived per-event differential.

CHARGES ARE OFF AND UNREACHABLE HERE: `allow_charge=False` (the runner's default), so
`tiers.charge_tier` is never called, the ledger path is a scratch path that is never created,
and the production `data/cache/eval_gate/backtest_fwer.jsonl` is neither read nor written.

THE CI IS RECOMPUTED from the archived per-event differential in the documented direction
(d = loss_incumbent - loss_model), never taken from the stored `dm_stat` -- S79 filed that
`tiers._run_screen` passes the sign mirror and that finding is unrepaired.

A SCREEN IS A NON-FINDING. Calibration language only -- no dollar, ROI or edge claim, and the
S122 `+0.0202` is a MEASUREMENT ARTIFACT that must never be quoted as a result.

Run:
  python -m scripts.platformkit.eval_gate.s136_screen --leak-probe
  python -m scripts.platformkit.eval_gate.s136_screen --out-dir <scratch>
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate import s111_screen
from scripts.platformkit.foundry import asof_supply

TARGETS = {
    "tennis": ("tennis_schedule_density", "tennis_travel_scouting",
               "tennis_serve_return_profiles"),
}

DENSITY_SRC = ("data/domains/tennis/schedule_density_rg.parquet,"
               "data/domains/tennis/schedule_density_rg_wta.parquet")
TRAVEL_SRC = ("data/domains/tennis/travel_scouting_rg.parquet,"
              "data/domains/tennis/travel_scouting_rg_wta.parquet")
# `rest_days` is NOT here: real rest days inside a tourney are unrecoverable from a
# tourney-grain date, so the member is dropped CLOSED AT LIMIT rather than served as a
# round-depth proxy. Its hypotheses stay UNCOVERED, exactly as they are today.
DENSITY_COLUMNS = ("matches_last_7d", "matches_last_14d")
TRAVEL_COLUMNS = ("miles_flown_in", "venue_altitude_m")


def _load_tennis_sides(path: str) -> pd.DataFrame:
    """The density table carries `player_id` but no side flag, so the side is read off the
    event_id, counted from the END (S122: a dashed tourney_id shifts the head)."""
    frame = asof_supply._load_glob(path).copy()
    frame["_is_p1"] = (frame["player_id"].astype(str)
                       == frame["event_id"].astype(str).str.split("-").str[-3])
    return frame


# S129 added a `pregame` field to `Supply`: the side rule serves the EVENT'S OWN ROW, so an
# entry must DECLARE the as-of basis that makes that row legal or the rule fails closed. Both
# entries below carry one. The keyword is passed only when the landed dataclass has the field,
# because `foundry/asof_supply.py` is owned by another lane and this script must run either way.
DENSITY_PREGAME = ("schedule_density_roundgrain: a match at (D, r) counts only rows with "
                   "date < D, or date == D and round < r -- strictly before at (tourney start "
                   "date, Sackmann round) grain, so the row can never see itself, a sibling of "
                   "equal round, or a later round of its own event")
TRAVEL_PREGAME = ("schedule_density_roundgrain: prior_city_travel reads the player's PREVIOUS "
                  "resolved host city under that same (date, round) order -- a first "
                  "appearance is NaN, never 0; venue_altitude_m is a property of the venue, "
                  "published with the draw")


def register_roundgrain() -> None:
    """Declare both families over the round-grain sources IN THIS PROCESS ONLY."""
    supply = asof_supply.Supply
    has_pregame = "pregame" in getattr(supply, "__dataclass_fields__", {})
    asof_supply._LOADERS["tennis_sides"] = _load_tennis_sides
    asof_supply.REGISTRY["tennis_schedule_density"] = supply(
        DENSITY_SRC, "side", DENSITY_COLUMNS, side="_is_p1", entity_from="player",
        loader="tennis_sides", **({"pregame": DENSITY_PREGAME} if has_pregame else {}))
    asof_supply.REGISTRY["tennis_travel_scouting"] = supply(
        TRAVEL_SRC, "side", TRAVEL_COLUMNS, side="is_p1", entity_from="player",
        loader="glob", overrides=(("venue_altitude_m", "a"),),
        **({"pregame": TRAVEL_PREGAME} if has_pregame else {}))
    asof_supply._frame.cache_clear()


def leak_probe() -> None:
    """The S122 measurements, re-taken on the round-grain tables."""
    from scripts.platformkit.foundry import screen_predictor as sp

    matches = pd.read_parquet("data/domains/tennis/matches.parquet")
    density = pd.concat([pd.read_parquet("data/domains/tennis/schedule_density_rg.parquet"),
                         pd.read_parquet("data/domains/tennis/schedule_density_rg_wta.parquet")],
                        ignore_index=True)
    wimbledon = matches[matches["tourney_id"] == "2025-540"]
    keyed = density.set_index(["event_id", "player_id"])["matches_last_7d"]
    final = wimbledon[wimbledon["round"] == "F"].iloc[0]
    champion = int(final["p1_id"] if final["winner"] == 1 else final["p2_id"])
    order = {r: i for i, r in enumerate(["R128", "R64", "R32", "R16", "QF", "SF", "F"])}
    served = sorted(((order[r["round"]], float(keyed.loc[(r["event_id"], champion)]))
                     for _, r in wimbledon.iterrows()
                     if champion in (r["p1_id"], r["p2_id"])))
    print("2025 Wimbledon champion, matches_last_7d by round R128..F: %s"
          % [v for _, v in served])
    print("round-grain rows reading matches_last_7d == 0: %.4f of %d"
          % (density["matches_last_7d"].eq(0).mean(), len(density)))
    print("rest_days present in the round-grain table: %s"
          % ("rest_days" in density.columns))

    register_roundgrain()
    states, table, incumbent = sp.corpus_states("tennis")
    binder = sp.ScreenBinder("tennis", states, table, s111_screen.SCREEN_ROWS, incumbent)
    outcome = np.array([s["outcome"] for s in states], float)[-s111_screen.SCREEN_ROWS:]
    for family, column in (("tennis_schedule_density", "matches_last_7d"),
                           ("tennis_schedule_density", "matches_last_14d"),
                           ("tennis_travel_scouting", "miles_flown_in")):
        value = asof_supply.supply(family, column, binder.frame.index,
                                   binder.frame).to_numpy(float)[-s111_screen.SCREEN_ROWS:]
        ok = np.isfinite(value)
        print("%-24s filled %3d/%d  corr(p1-minus-p2, outcome) = %+.4f"
              % (column, int(ok.sum()), len(value),
                 float(np.corrcoef(value[ok], outcome[ok])[0, 1])))


def main() -> None:
    parser = argparse.ArgumentParser(description="S136 round-grain factory screen (charges off)")
    parser.add_argument("--out-dir", help="scratch directory; nothing else is written")
    parser.add_argument("--leak-probe", action="store_true",
                        help="the S122 measurements re-taken on the round-grain tables")
    args = parser.parse_args()
    if args.leak_probe:
        leak_probe()
        return
    if not args.out_dir:
        parser.error("--out-dir is required unless --leak-probe")
    register_roundgrain()
    print("REGISTERED IN-PROCESS over the round-grain sources -- nothing on disk changed")
    # ponytail: the whole run/report machinery is s111_screen's; only the family set differs.
    original, s111_screen.TARGETS = s111_screen.TARGETS, TARGETS
    try:
        s111_screen.report(s111_screen.run(Path(args.out_dir)))
    finally:
        s111_screen.TARGETS = original


if __name__ == "__main__":
    main()
