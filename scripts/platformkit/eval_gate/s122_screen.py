"""S122 -- the local factory screen over the two tennis families S111 left at limit, and the
leak probe that keeps them OUT of the as-of bridge.

`tennis_schedule_density` (469/800) and `tennis_travel_scouting` (454/800) sat under the frozen
0.8 coverage floor because `schedule_density.parquet` and `travel_scouting.parquet` are built
from the ATP spine only. `domains/tennis/wta_schedule_travel.py` builds the WTA halves, and
declaring the ATP+WTA source pair DOES carry both families over the floor (800/800 and
785/800). It is not landed, because the screen it unlocks is a LEAK:

Sackmann's `date` is the TOURNEY START date -- 1451/1451 ATP and 974/974 WTA tourneys carry
exactly ONE distinct date -- so a trailing-window count cannot order a player's matches within
an event. 46.2 pct of all rows read `rest_days == 0`, the 2025 Wimbledon champion's seven
matches serve `0,3,4,5,1,6,2` (the right chronological sequence assigned to the wrong rows),
and the served p1-minus-p2 value correlates +0.2616 with the OUTCOME on the screen window.

So `--register-leaky` is how a verifier reproduces both halves of that account from the landed
tree: it declares the two families for the life of the process only (nothing on disk changes),
runs the same screen, and prints the coverage the acquisition reaches and the improvement it
fabricates. WITHOUT the flag it screens the landed registry, where both families are refused.

`tennis_serve_return_profiles` is the REGRESSION CHECK for the `_sides` side-parse repair:
423/800 filled under `str[4]` and 423/800 under `str[-3]`, so no landed number moves.

CHARGES ARE OFF AND UNREACHABLE HERE: `allow_charge=False` (the runner's default), so
`tiers.charge_tier` is never called, the ledger path is a scratch path that is never created,
and the production `data/cache/eval_gate/backtest_fwer.jsonl` is neither read nor written.

THE CI IS RECOMPUTED from the archived per-event differential in the documented direction
(d = loss_incumbent - loss_model), never taken from the stored `dm_stat` -- S79 filed that
`tiers._run_screen` passes the sign mirror and that finding is unrepaired.

A SCREEN IS A NON-FINDING, and a LEAKY screen is not even that. Calibration language only --
no dollar, ROI or edge claim. The +0.0202 this script can reproduce is a MEASUREMENT ARTIFACT
and must never be quoted as a result.

Run:
  python -m scripts.platformkit.eval_gate.s122_screen --out-dir <scratch>
  python -m scripts.platformkit.eval_gate.s122_screen --out-dir <scratch> --register-leaky
  python -m scripts.platformkit.eval_gate.s122_screen --leak-probe
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate import s111_screen
from scripts.platformkit.foundry import asof_supply

# The two S122 acquisitions plus the side-parse regression check.
TARGETS = {
    "tennis": ("tennis_schedule_density", "tennis_travel_scouting",
               "tennis_serve_return_profiles"),
}

_DENSITY_SRC = ("data/domains/tennis/schedule_density.parquet,"
                "data/domains/tennis/schedule_density_wta.parquet")
_TRAVEL_SRC = ("data/domains/tennis/travel_scouting.parquet,"
               "data/domains/tennis/travel_scouting_wta.parquet")


def _load_tennis_sides(path: str) -> pd.DataFrame:
    """The long tables carry player_id but no side flag, so the side is read off the event_id.
    Counted from the END: a dashed tourney_id shifts the head, so `str[4]` names p1 on 93.2 pct
    of ATP / 74.9 pct of WTA rows where `str[-3]` hits 100 pct of both."""
    frame = asof_supply._load_glob(path).copy()
    frame["_is_p1"] = (frame["player_id"].astype(str)
                       == frame["event_id"].astype(str).str.split("-").str[-3])
    return frame


def register_leaky() -> None:
    """Declare the two families IN THIS PROCESS ONLY, so the coverage the acquisition reaches
    and the improvement it fabricates are both reproducible from the landed tree."""
    supply = asof_supply.Supply
    asof_supply._LOADERS["tennis_sides"] = _load_tennis_sides
    asof_supply.REGISTRY["tennis_schedule_density"] = supply(
        _DENSITY_SRC, "side", ("rest_days", "matches_last_7d", "matches_last_14d"),
        side="_is_p1", entity_from="player", loader="tennis_sides")
    asof_supply.REGISTRY["tennis_travel_scouting"] = supply(
        _TRAVEL_SRC, "side", ("miles_flown_in", "venue_altitude_m"), side="is_p1",
        entity_from="player", loader="glob", overrides=(("venue_altitude_m", "a"),))
    asof_supply._frame.cache_clear()


def leak_probe() -> None:
    """The three measurements that forbid the registration, from the corpus on disk."""
    from scripts.platformkit.foundry import screen_predictor as sp

    for name, path in (("ATP", "data/domains/tennis/matches.parquet"),
                       ("WTA", "data/domains/tennis/wta_matches.parquet")):
        spine = pd.read_parquet(path)
        per = spine.groupby("tourney_id")["date"].nunique()
        print("%s spine: %d tourneys, %d with exactly ONE distinct date"
              % (name, len(per), int(per.eq(1).sum())))

    density = pd.concat([pd.read_parquet("data/domains/tennis/schedule_density.parquet"),
                         pd.read_parquet("data/domains/tennis/schedule_density_wta.parquet")],
                        ignore_index=True)
    print("rows reading rest_days == 0: %.4f of %d" % (density["rest_days"].eq(0).mean(),
                                                       len(density)))

    matches = pd.read_parquet("data/domains/tennis/matches.parquet")
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

    register_leaky()
    states, table, incumbent = sp.corpus_states("tennis")
    binder = sp.ScreenBinder("tennis", states, table, s111_screen.SCREEN_ROWS, incumbent)
    outcome = np.array([s["outcome"] for s in states], float)[-s111_screen.SCREEN_ROWS:]
    for family, column in (("tennis_schedule_density", "matches_last_7d"),
                           ("tennis_travel_scouting", "miles_flown_in")):
        value = asof_supply.supply(family, column, binder.frame.index,
                                   binder.frame).to_numpy(float)[-s111_screen.SCREEN_ROWS:]
        ok = np.isfinite(value)
        print("%-24s filled %3d/%d  corr(p1-minus-p2, outcome) = %+.4f"
              % (column, int(ok.sum()), len(value),
                 float(np.corrcoef(value[ok], outcome[ok])[0, 1])))


def main() -> None:
    parser = argparse.ArgumentParser(description="S122 local factory screen (charges off)")
    parser.add_argument("--out-dir", help="scratch directory; nothing else is written")
    parser.add_argument("--register-leaky", action="store_true",
                        help="declare the two families in-process to reproduce the leak")
    parser.add_argument("--leak-probe", action="store_true",
                        help="print the measurements that forbid the registration")
    args = parser.parse_args()
    if args.leak_probe:
        leak_probe()
        return
    if not args.out_dir:
        parser.error("--out-dir is required unless --leak-probe")
    if args.register_leaky:
        register_leaky()
        print("REGISTERED IN-PROCESS -- any improvement below is a LEAK ARTIFACT, not a result")
    # ponytail: the whole run/report machinery is s111_screen's; only the family set differs.
    original, s111_screen.TARGETS = s111_screen.TARGETS, TARGETS
    try:
        s111_screen.report(s111_screen.run(Path(args.out_dir)))
    finally:
        s111_screen.TARGETS = original


if __name__ == "__main__":
    main()
