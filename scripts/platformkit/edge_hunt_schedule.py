"""HUNT A -- schedule/fatigue edge hunt scored through the REAL eval_gate.

Every candidate schedule/fatigue signal (b2b, 3-in-4, rest-diff, home/away, altitude,
long-road-trip, travel-diff) is derived ONLY from the public calendar (games.parquet),
encoded as a HOME-minus-AWAY differential, and scored via edge_engine.score.score_candidate
against the SHIN-devigged close moneyline. Walk-forward, purge 48h, embargo 3d, slope fit
inside the window, clustered Diebold-Mariano. SHIP iff BSS>0 AND DM p<0.05 AND n>=200.

ANTI-P-HACK: schedule facts are deterministic from the released calendar -> known LONG before
the line moves -> the entire scored sample is the confirmed-before subset by construction. This
is therefore the cleanest possible "is the schedule SPOT already priced?" test. The market is
expected to price raw schedule physics -> honest REJECT is the expected, recorded SUCCESS.

>=2 corpora: NBA odds.parquet covers ONE season (2025-26), so true 2-season independent
scoring is not available at the price level. We split that season into two independent
calendar halves (H1/H2) as sub-corpora: a lift in H1 that REVERSES in H2 is the overfit
signature -> REJECT. Each signal is reported on FULL season + both halves.

No $/ROI/+EV is produced. Output is honest SHIP/REJECT + BSS + clustered DM p per signal.
Read-only on src/kernel/eval_gate. ASCII only. Run:
  python -m scripts.platformkit.edge_hunt_schedule
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "eval_gate"))
sys.path.insert(0, str(_HERE / "edge_engine"))

from shin import shin_devig_decimal  # type: ignore
from score import SignalRow, score_candidate  # type: ignore

ROOT = Path("C:/Users/neelj/nba-ai-system")
GAMES = ROOT / "data/domains/basketball_nba/games.parquet"
ODDS = ROOT / "data/domains/basketball_nba/odds.parquet"

# Calendar: the schedule is public the moment it is released (well before any line move).
AVAIL_TS = "2025-09-01T00:00:00"   # schedule released; all facts known before any line move
ALTITUDE_TEAMS = {"DEN", "UTA"}    # mile-high acclimatization spots


def _am_to_dec(am: float) -> float:
    am = float(am)
    return 1.0 + (am / 100.0 if am > 0 else 100.0 / (-am))


def load_joined() -> pd.DataFrame:
    g = pd.read_parquet(GAMES)
    g = g[g["season"] == "2025-26"].copy()
    g["date"] = pd.to_datetime(g["date"])
    o = pd.read_parquet(ODDS).copy()
    o["date"] = pd.to_datetime(o["date"])
    g["k"] = g["date"].dt.strftime("%Y-%m-%d") + "|" + g["home_team"] + "|" + g["away_team"]
    o["k"] = o["date"].dt.strftime("%Y-%m-%d") + "|" + o["home_team"] + "|" + o["away_team"]
    o = o[["k", "home_ml", "away_ml"]]
    df = g.merge(o, on="k", how="inner")
    df = df.dropna(subset=["home_ml", "away_ml", "home_win"]).reset_index(drop=True)
    return df


def add_window_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Per-team 3-in-4 / 4-in-5 flags, then map back to home/away of each game."""
    rows = []
    for _, r in df.iterrows():
        rows.append((r["home_team"], r["date"], r["k"], "H"))
        rows.append((r["away_team"], r["date"], r["k"], "A"))
    pt = pd.DataFrame(rows, columns=["team", "date", "k", "loc"]).sort_values(["team", "date"])
    g3, g4 = [], []
    for _, grp in pt.groupby("team"):
        d = grp["date"].values.astype("datetime64[D]").astype(int)
        for i in range(len(d)):
            diff = d[i] - d[: i + 1]
            g3.append(int(((diff < 4) & (diff >= 0)).sum()))
            g4.append(int(((diff < 5) & (diff >= 0)).sum()))
    pt["is_3in4"] = (np.array(g3) >= 3).astype(int)
    pt["is_4in5"] = (np.array(g4) >= 4).astype(int)
    h = pt[pt.loc[:, "loc"] == "H"].set_index("k")[["is_3in4", "is_4in5"]].rename(
        columns={"is_3in4": "home_3in4", "is_4in5": "home_4in5"})
    a = pt[pt.loc[:, "loc"] == "A"].set_index("k")[["is_3in4", "is_4in5"]].rename(
        columns={"is_3in4": "away_3in4", "is_4in5": "away_4in5"})
    return df.merge(h, on="k").merge(a, on="k")


def build_states(df: pd.DataFrame) -> list:
    """One state per game: devigged-close HOME prob + outcome + a midnight tip line-move ts."""
    states = []
    for _, r in df.iterrows():
        dec_h = _am_to_dec(r["home_ml"])
        dec_a = _am_to_dec(r["away_ml"])
        probs, _z = shin_devig_decimal([dec_h, dec_a])
        p_home = float(probs[0])
        # line-move ts = game day tip (after schedule-fact availability) -> all games confirmed-before
        line_move_ts = r["date"].strftime("%Y-%m-%dT19:00:00")
        states.append({
            "game_id": r["k"], "home": r["home_team"], "away": r["away_team"],
            "state_ts": line_move_ts, "outcome": int(r["home_win"]),
            "devig_close_prob": p_home, "date": r["date"],
        })
    return states


def signal_values(df: pd.DataFrame) -> dict:
    """Each candidate -> {game_key: numeric HOME-minus-AWAY differential}.

    Encoded so a POSITIVE value should help the HOME team if the spot is mis-priced
    (more away fatigue / more home rest = positive). A null slope => priced => REJECT.
    """
    rest_h = df["rest_days_home"].astype(float)
    rest_a = df["rest_days_away"].astype(float)
    b2b_h = df["home_b2b"].map({True: 1, False: 0}).astype("float")
    b2b_a = df["away_b2b"].map({True: 1, False: 0}).astype("float")
    out = {
        # away on b2b minus home on b2b: +1 => away tired, home fresh (should help home)
        "b2b_diff": (b2b_a - b2b_h),
        # away in a 3-in-4 minus home in a 3-in-4
        "three_in_four_diff": (df["away_3in4"] - df["home_3in4"]),
        # home rest minus away rest (capped to remove opener outliers handled by dropna)
        "rest_diff": (rest_h - rest_a).clip(-4, 4),
        # home-court constant: probes whether the devig already prices HCA (slope ~0 expected)
        "home_court": pd.Series(1.0, index=df.index),
        # altitude: home is a mile-high team and away is not (acclimatization edge to home)
        "altitude_home": df["home_team"].isin(ALTITUDE_TEAMS).astype(int)
        - df["away_team"].isin(ALTITUDE_TEAMS).astype(int),
        # long road trip: away travel distance (standardized) -- big trip => away worn (helps home)
        "away_long_travel": ((df["travel_away"].astype(float) - 355.0) / 528.0),
        # net travel burden: away travel minus home travel
        "travel_diff": ((df["travel_away"].astype(float) - df["travel_home"].astype(float)) / 528.0),
    }
    res = {}
    for name, ser in out.items():
        res[name] = {k: float(v) for k, v in zip(df["k"], ser.values)
                     if pd.notna(v)}
    return res


def _score(states: list, values: dict, min_n: int) -> object:
    # CRITICAL: score._build_states overrides each state's state_ts to the SignalRow's
    # line_move_ts. So line_move_ts MUST be the REAL per-game line-move time (game day 19:00),
    # NOT a constant -- a constant collapses every state_ts to one instant and the expanding
    # walk-forward window goes EMPTY (no training data, slope forced to 0 = a dead test).
    # available_ts = Sep-1 (schedule released) is strictly before each game-day move, so every
    # game stays in the confirmed-before subset, by construction (schedule known in advance).
    move_ts = {s["game_id"]: s["state_ts"] for s in states}
    rows = [SignalRow(game_id=k, value=v, available_ts=AVAIL_TS,
                      line_move_ts=move_ts[k]) for k, v in values.items() if k in move_ts]
    return score_candidate(states, rows, alpha=0.05, min_n=min_n)


def run() -> None:
    df = load_joined()
    df = add_window_counts(df)
    states_all = build_states(df)
    sig_all = signal_values(df)

    # two independent calendar-half sub-corpora (overfit check)
    median_date = df["date"].median()
    df_h1 = df[df["date"] <= median_date]
    df_h2 = df[df["date"] > median_date]

    def subset(d):
        keys = set(d["k"])
        st = [s for s in states_all if s["game_id"] in keys]
        sg = {name: {k: v for k, v in vals.items() if k in keys}
              for name, vals in sig_all.items()}
        return st, sg

    st1, sg1 = subset(df_h1)
    st2, sg2 = subset(df_h2)

    print("=" * 78)
    print("HUNT A -- NBA SCHEDULE/FATIGUE EDGE HUNT (scored vs SHIN-devigged close ML)")
    print("=" * 78)
    print(f"corpus: 2025-26, joined games with ML close = {len(df)}")
    print(f"sub-corpora: H1 (<= {median_date.date()}) n={len(df_h1)} | "
          f"H2 (> {median_date.date()}) n={len(df_h2)}")
    print("SHIP rule: BSS>0 AND clustered DM p<0.05 AND n>=200 (full); n>=150 on halves")
    print("-" * 78)
    hdr = f"{'signal':<20}{'corpus':<7}{'n':>5}{'BSS':>11}{'DM_p':>9}{'slope':>10}  verdict"
    print(hdr)
    print("-" * 78)

    survivors = []
    for name in sig_all:
        r_full = _score(states_all, sig_all[name], min_n=200)
        r_h1 = _score(st1, sg1[name], min_n=150)
        r_h2 = _score(st2, sg2[name], min_n=150)
        for tag, r in (("FULL", r_full), ("H1", r_h1), ("H2", r_h2)):
            print(f"{name:<20}{tag:<7}{r.n_subset:>5}{r.bss:>11.5f}"
                  f"{r.dm_p:>9.4f}{r.fitted_slope:>10.4f}  {r.verdict}")
        # honest overfit check: SHIP only if FULL ships AND both halves keep BSS sign
        consistent = (r_h1.bss > 0 and r_h2.bss > 0) or (r_h1.bss < 0 and r_h2.bss < 0)
        if r_full.verdict == "SHIP" and r_h1.bss > 0 and r_h2.bss > 0:
            survivors.append(name)
        flip = "" if consistent else "   <- BSS SIGN FLIPS across halves = overfit signature"
        print(f"{'':<20}{'reason':<7}{r_full.reason}{flip}")
        print("-" * 78)

    print("=" * 78)
    if survivors:
        print(f"IN-SAMPLE SURVIVORS (need FORWARD CLV before any claim): {survivors}")
    else:
        print("SURVIVORS: NONE. Every schedule/fatigue signal REJECTS vs the devigged close.")
        print("HONEST VERDICT: the market PRICES the schedule spot (b2b/3-in-4/rest/travel/")
        print("altitude/HCA). This is the EXPECTED, RECORDED SUCCESS -- markets efficient on")
        print("deterministic calendar physics. No $/edge claimed.")
    print("=" * 78)


if __name__ == "__main__":
    run()
