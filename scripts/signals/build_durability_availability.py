"""Wave 1 builder: per-player DURABILITY & AVAILABILITY signal profile.

Sources (official / non-CV):
  - data/dnp_rows.parquet           : per-game DNP rows with reason (injury / coach_decision)
  - data/player_adv_stats.parquet   : per-game minutes (game_date granularity)
  - data/cache/player_profile_features.parquet : birthdate + position -> aging-curve

Signals emitted (one wide row per player):
  - games_missed_injury_<season>   : injury DNPs per season (last 3 full seasons)
  - games_missed_cd_<season>       : coach-decision DNPs per season (load mgmt proxy)
  - avail_rate_<season>            : games appeared / (appeared + injury DNP) per season
  - avail_rate_l3seas              : mean availability rate over last 3 seasons
  - min_mpg_<season>               : mean minutes per game per season
  - high_min_rate_<season>         : fraction of games with >=32 min per season
  - min_l10_latest                 : most-recent rolling-10 mean minutes (prior-game-only)
  - age_as_of                      : age in years as of build date
  - years_from_peak                : years past canonical position peak age (neg = before peak)
  - days_since_last_7d_absence     : days elapsed since last 7+ day inter-game gap (rampup flag)
  - games_since_last_7d_absence    : games played since that gap (None if no gap found)

Leak rule: season-aggregate signals are labelled "season-agg" (scouting only). The rolling
minutes signal uses shift(1) so the current game is never included. days/games_since_7d_absence
uses only prior-game dates (pregame safe). For in-game use, re-compute at game time.

Consumer: A (scouting / intelligence vault), B (in-game availability context).

    python scripts/signals/build_durability_availability.py
"""
from __future__ import annotations

import os
from datetime import date

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DNP_PATH = os.path.join(ROOT, "data", "dnp_rows.parquet")
ADV_PATH = os.path.join(ROOT, "data", "player_adv_stats.parquet")
PROF_PATH = os.path.join(ROOT, "data", "cache", "player_profile_features.parquet")
OUT_DIR = os.path.join(ROOT, "data", "cache", "signals")
OUT = os.path.join(OUT_DIR, "durability_availability.parquet")

# Seasons to compute per-season signals for (last 3 full regular seasons in data)
TARGET_SEASONS = ["2022-23", "2023-24", "2024-25"]

# Canonical position peak ages (basketball consensus, used for aging-curve position)
PEAK_AGE: dict[str, float] = {
    "Guard": 27.5, "Guard-Forward": 27.5,
    "Forward": 28.0, "Forward-Guard": 28.0, "Forward-Center": 28.5,
    "Center": 28.0, "Center-Forward": 28.0,
}

HIGH_MIN_THRESHOLD = 32.0   # minutes >= this counts as a high-minute game
BUILD_DATE = pd.Timestamp(date.today())


# ── helpers ──────────────────────────────────────────────────────────────────

def infer_season(game_date: str) -> str:
    """'2022-10-18' -> '2022-23', '2023-01-05' -> '2022-23'."""
    yr, mo = int(game_date[:4]), int(game_date[5:7])
    if mo >= 10:
        return f"{yr}-{str(yr + 1)[2:]}"
    return f"{yr - 1}-{str(yr)[2:]}"


def _dnp_signals(dnp: pd.DataFrame) -> pd.DataFrame:
    """Games missed by reason per season (3 seasons) → one wide row per player."""
    dnp = dnp[dnp.season.isin(TARGET_SEASONS)].copy()
    # injury DNPs
    inj = (dnp[dnp.dnp_reason == "injury"]
           .groupby(["player_id", "season"])
           .size().rename("games_missed_injury"))
    # coach-decision DNPs (load management proxy)
    cd = (dnp[dnp.dnp_reason == "coach_decision"]
          .groupby(["player_id", "season"])
          .size().rename("games_missed_cd"))

    rows = []
    for pid in dnp.player_id.unique():
        r: dict = {"player_id": int(pid)}
        for s in TARGET_SEASONS:
            tag = s.replace("-", "_")
            r[f"games_missed_injury_{tag}"] = int(inj.get((pid, s), 0))
            r[f"games_missed_cd_{tag}"] = int(cd.get((pid, s), 0))
        rows.append(r)
    return pd.DataFrame(rows)


def _avail_signals(adv: pd.DataFrame, dnp: pd.DataFrame) -> pd.DataFrame:
    """Availability rate = games appeared / (appeared + injury DNP) per season."""
    adv = adv.copy()
    adv["season"] = adv.game_date.apply(infer_season)
    adv = adv[adv.season.isin(TARGET_SEASONS)]

    appeared = (adv.groupby(["player_id", "season"])["game_id"]
                .nunique().rename("games_appeared"))
    dnp_inj = dnp[dnp.dnp_reason == "injury"].copy()
    inj_dnps = (dnp_inj[dnp_inj.season.isin(TARGET_SEASONS)]
                .groupby(["player_id", "season"]).size().rename("inj_dnp"))

    # All player×season pairs that appear in either source
    pids = set(adv.player_id.unique()) | set(dnp.player_id.unique())
    rows = []
    for pid in pids:
        r: dict = {"player_id": int(pid)}
        rates = []
        for s in TARGET_SEASONS:
            tag = s.replace("-", "_")
            gp = int(appeared.get((pid, s), 0))
            gm = int(inj_dnps.get((pid, s), 0))
            total = gp + gm
            rate = round(gp / total, 4) if total > 0 else None
            r[f"avail_rate_{tag}"] = rate
            if rate is not None:
                rates.append(rate)
        r["avail_rate_l3seas"] = round(float(np.mean(rates)), 4) if rates else None
        rows.append(r)
    return pd.DataFrame(rows)


def _minutes_signals(adv: pd.DataFrame) -> pd.DataFrame:
    """Mean MPG, high-min-game rate, and rolling-L10 minutes (prior-game-only)."""
    adv = adv.copy()
    adv["season"] = adv.game_date.apply(infer_season)
    adv = adv.sort_values(["player_id", "game_date"])

    # Rolling L10 (shift(1) = prior-game-only, no current-game leak)
    adv["min_l10"] = (adv.groupby("player_id")["minutes"]
                      .transform(lambda x: x.shift(1).rolling(10, min_periods=3).mean()))

    # Per-season aggregates
    sea_agg = (adv[adv.season.isin(TARGET_SEASONS)]
               .groupby(["player_id", "season"])
               .agg(
                   min_mpg=("minutes", "mean"),
                   high_min_rate=("minutes", lambda x: (x >= HIGH_MIN_THRESHOLD).mean()),
               ).reset_index())

    rows = []
    for pid, grp in adv.groupby("player_id"):
        r: dict = {"player_id": int(pid)}
        # Per-season
        for s in TARGET_SEASONS:
            tag = s.replace("-", "_")
            sub = sea_agg[(sea_agg.player_id == pid) & (sea_agg.season == s)]
            if len(sub):
                r[f"min_mpg_{tag}"] = round(float(sub.min_mpg.iloc[0]), 2)
                r[f"high_min_rate_{tag}"] = round(float(sub.high_min_rate.iloc[0]), 4)
            else:
                r[f"min_mpg_{tag}"] = None
                r[f"high_min_rate_{tag}"] = None
        # Latest rolling L10 (last row with a value)
        l10_vals = grp["min_l10"].dropna()
        r["min_l10_latest"] = round(float(l10_vals.iloc[-1]), 2) if len(l10_vals) else None
        rows.append(r)
    return pd.DataFrame(rows)


def _age_curve_signals(prof: pd.DataFrame) -> pd.DataFrame:
    """Age as of build date and position on the canonical aging curve."""
    prof = prof.copy()
    prof["birthdate_dt"] = pd.to_datetime(prof["birthdate"])
    prof["age_as_of"] = (BUILD_DATE - prof["birthdate_dt"]).dt.days / 365.25
    prof["peak_age"] = prof["position"].map(PEAK_AGE).fillna(28.0)
    prof["years_from_peak"] = prof["age_as_of"] - prof["peak_age"]
    return prof[["player_id", "age_as_of", "years_from_peak"]].assign(
        age_as_of=lambda d: d.age_as_of.round(2),
        years_from_peak=lambda d: d.years_from_peak.round(2),
    )


def _rampup_signals(adv: pd.DataFrame) -> pd.DataFrame:
    """days_since_last_7d_absence and games_since_last_7d_absence (prior-game-only).

    For each player, look at the most recent game in the data and trace back through
    sorted game dates to find the last inter-game gap >= 7 days.
    """
    adv = adv.copy()
    adv = adv.sort_values(["player_id", "game_date"])
    adv["game_date_dt"] = pd.to_datetime(adv["game_date"])
    adv["prev_date"] = adv.groupby("player_id")["game_date_dt"].shift(1)
    adv["gap_days"] = (adv["game_date_dt"] - adv["prev_date"]).dt.days
    adv["is_7d_gap"] = adv["gap_days"] >= 7

    rows = []
    for pid, grp in adv.groupby("player_id"):
        grp = grp.reset_index(drop=True)
        # Find most recent 7d+ gap
        gap_idx = grp.index[grp["is_7d_gap"]].tolist()
        r: dict = {"player_id": int(pid)}
        if gap_idx:
            last_gap_i = gap_idx[-1]
            # The game AT last_gap_i was the first game back after the absence
            # games_since = how many games after (and including) that return game
            games_since = len(grp) - last_gap_i - 1  # games AFTER the return game
            # days since: from the date of the return game to the latest game date
            latest_date = grp["game_date_dt"].iloc[-1]
            return_date = grp["game_date_dt"].iloc[last_gap_i]
            days_since = (latest_date - return_date).days
            r["days_since_last_7d_absence"] = int(days_since)
            r["games_since_last_7d_absence"] = int(games_since)
        else:
            r["days_since_last_7d_absence"] = None
            r["games_since_last_7d_absence"] = None
        rows.append(r)
    return pd.DataFrame(rows)


# ── main ─────────────────────────────────────────────────────────────────────

def build() -> pd.DataFrame:
    dnp = pd.read_parquet(DNP_PATH)
    adv = pd.read_parquet(ADV_PATH)
    prof = pd.read_parquet(PROF_PATH)

    # Keep game_id as string to avoid leading-zero strip
    adv["game_id"] = adv["game_id"].astype(str)

    dnp_sig = _dnp_signals(dnp)
    avail_sig = _avail_signals(adv, dnp)
    min_sig = _minutes_signals(adv)
    age_sig = _age_curve_signals(prof)
    ramp_sig = _rampup_signals(adv)

    # Merge all frames on player_id — left-join from the union of all players
    all_pids = pd.DataFrame(
        {"player_id": list(
            set(adv.player_id.unique()) | set(dnp.player_id.unique())
        )}
    )
    out = (all_pids
           .merge(dnp_sig,   on="player_id", how="left")
           .merge(avail_sig,  on="player_id", how="left")
           .merge(min_sig,    on="player_id", how="left")
           .merge(age_sig,    on="player_id", how="left")
           .merge(ramp_sig,   on="player_id", how="left"))

    # Sanity: row count must be ≈ entity count
    assert len(out) == len(all_pids), (
        f"Row count drift: {len(out)} vs {len(all_pids)} players — possible cartesian join."
    )

    # Attach player name from profile (for readability / sanity checks)
    name_map = prof[["player_id", "player_name"]].drop_duplicates()
    out = out.merge(name_map, on="player_id", how="left")

    out = out.sort_values("player_id").reset_index(drop=True)
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    out = build()
    out.to_parquet(OUT, index=False)
    n_players = out.player_id.nunique()
    print(f"DONE: durability_availability signals -> {OUT}")
    print(f"  rows={len(out)}  distinct players={n_players}")
    print()

    # 3 sample rows
    print("=== 3 sample rows ===")
    print(out.head(3).to_string())
    print()

    # Sanity: players with highest injury DNP count in 2024-25
    col = "games_missed_injury_2024_25"
    if col in out.columns:
        top = out[out[col].notna()].nlargest(10, col)[
            ["player_name", "player_id", col,
             "avail_rate_2024_25", "min_mpg_2024_25", "age_as_of", "years_from_peak"]
        ]
        print(f"=== Top 10 by {col} (injury absences) ===")
        print(top.to_string(index=False))
    print()

    # Sanity: players on rampup (returning from absence)
    r = out[out.games_since_last_7d_absence.notna()].nsmallest(8, "games_since_last_7d_absence")
    print("=== Players most recently in rampup window (fewest games since 7d+ gap) ===")
    print(r[["player_name", "games_since_last_7d_absence", "days_since_last_7d_absence",
             "min_l10_latest"]].to_string(index=False))


if __name__ == "__main__":
    main()
