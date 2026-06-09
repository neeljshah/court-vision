"""Physical & biographical attributes — the layer the user flagged (Wemby 7'4", small guards).

Rates already bake in a player's OWN size (Wemby's height is in his block/rim rates). The new
value of attributes is (a) MATCHUP size differentials rates can't see, and (b) PRIORS for thin-
data players (a 7-footer rookie should expect blocks before any data). This builds the per-player
attribute profile + position-relative z-scores used by the sim's size-matchup physics and the
intelligence memory.

Source: data/cache/player_profile_features.parquet (850 players: height_in, weight_lb, age, exp,
position, draft). Output: data/cache/team_system/player_attributes.parquet.

  python scripts/team_system/build_player_attributes.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
PROF = os.path.join(ROOT, "data", "cache", "player_profile_features.parquet")


def _pos_bucket(pos: str) -> str:
    p = str(pos or "").lower()
    if "center" in p and "forward" not in p:
        return "C"
    if "center" in p:
        return "BIG"          # forward-center / center-forward
    if "forward" in p and "guard" in p:
        return "WING"
    if "forward" in p:
        return "F"
    return "G"


def main():
    df = pd.read_parquet(PROF)
    df = df[df.height_in.notna() & (df.height_in > 0)].copy()
    df["age"] = (df["age_precise_days_as_of"] / 365.25).round(1)
    df["exp"] = df["season_exp"].fillna(0).astype(int)
    df["pos"] = df["position"].map(_pos_bucket)
    df["height_in"] = df["height_in"].astype(float)
    df["weight_lb"] = df["weight_lb"].astype(float)

    # position-relative z-scores (size unique within role)
    df["size_z"] = df.groupby("pos")["height_in"].transform(lambda s: (s - s.mean()) / (s.std(ddof=0) or 1))
    df["strength_z"] = df.groupby("pos")["weight_lb"].transform(lambda s: (s - s.mean()) / (s.std(ddof=0) or 1))
    # league-wide too (for cross-position matchups)
    df["height_z_lg"] = (df.height_in - df.height_in.mean()) / df.height_in.std(ddof=0)
    # derived basketball-meaningful flags / proxies
    df["is_rim_protector"] = (df.height_in >= 82).astype(int)            # 6'10"+
    df["is_small"] = (df.height_in <= 75).astype(int)                    # <=6'3"
    df["bmi_proxy"] = (df.weight_lb / (df.height_in ** 2) * 703).round(1)  # mass/frame
    df["agility_proxy"] = (-df.height_z_lg + np.clip((27 - df.age) / 6, -1, 1)).round(2)  # smaller+younger=quicker
    df["age_fatigue_w"] = np.clip((df.age - 27) / 6, 0, 1.2).round(2)    # older -> more B2B decline
    df["prime"] = ((df.age >= 25) & (df.age <= 30)).astype(int)

    out = df[["player_id", "player_name", "pos", "height_in", "weight_lb", "age", "exp",
              "draft_number", "undrafted_flag", "size_z", "strength_z", "height_z_lg",
              "is_rim_protector", "is_small", "bmi_proxy", "agility_proxy", "age_fatigue_w",
              "prime", "rookie_flag_as_of"]].rename(columns={"player_id": "pid"})
    out.to_parquet(os.path.join(TS, "player_attributes.parquet"), index=False)

    asc = lambda s: str(s).encode("ascii", "replace").decode()
    print(f"DONE: attributes for {len(out)} players. league mean height {df.height_in.mean():.1f}in")
    print(f"  rim-protector cutoff 82in: {int(out.is_rim_protector.sum())} bigs | small(<=75): {int(out.is_small.sum())}")
    for pid, nm in [(1641705, "Wemby"), (1628973, "Brunson"), (1626157, "KAT"), (1628969, "Bridges")]:
        r = out[out.pid == pid]
        if len(r):
            r = r.iloc[0]
            print(f"  {asc(nm):8s} {r.height_in:.0f}in size_z(pos {r.pos}) {r.size_z:+.2f} "
                  f"strength_z {r.strength_z:+.2f} age {r.age} agility {r.agility_proxy:+.2f} "
                  f"age_fatigue_w {r.age_fatigue_w} rim_protector={r.is_rim_protector}")


if __name__ == "__main__":
    main()
