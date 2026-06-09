"""ENRICH the possession corpus with cross-ASPECT, leak-free, possession-START state signals
(MASTER_SYSTEM_BUILD north star: every aspect of basketball feeds as many models as it can).

All derived from columns already in legacy_possessions -- each known AT/BEFORE the possession starts (leak-free):
  CLUTCH        is_clutch    = Q4+ & <=5min & margin<=5            (the leverage aspect)
  TRANSITION    fastbreak    = after a live turnover & quick (<8s)  (the pace/transition aspect)
  SHOT-CLOCK    early_clock  = poss_dur < 7s ;  late_clock >= 18s   (the shot-clock-state aspect)
  RHYTHM        prev_scored  = the offense scored on its PRIOR poss (the momentum/rhythm aspect; leak-free)
  GARBAGE       garbage      = |margin| >= 20                       (the score-blowout regime aspect)
  GAME-FLOW     poss_idx     = possession number within the game    (the fatigue/flow aspect)

Additive (existing columns unchanged) -> cross_season + cluster_lab stay valid. Atomic write.

  python scripts/team_system/enrich_possession_signals.py
"""
from __future__ import annotations
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY = os.path.join(ROOT, "data", "cache", "team_system", "legacy_possessions.parquet")


def enrich(D: pd.DataFrame) -> pd.DataFrame:
    D = D.copy()
    D["is_clutch"] = ((D.period >= 4) & (D.grem <= 300) & (D.abs_margin <= 5)).astype(int)
    D["fastbreak"] = ((D.after_to == 1) & (D.poss_dur < 8)).astype(int)
    D["early_clock"] = (D.poss_dur < 7).astype(int)
    D["late_clock"] = (D.poss_dur >= 18).astype(int)
    D["garbage"] = (D.abs_margin >= 20).astype(int)
    # rhythm: did THIS offense score on its previous possession (chronological within game)? leak-free.
    D = D.sort_values(["gid", "off", "grem"], ascending=[True, True, False])
    D["prev_scored"] = (D.groupby(["gid", "off"]).pts.shift(1) > 0).fillna(False).astype(int)
    # game-flow / fatigue: possession ordinal within the game (normalized 0..1)
    D = D.sort_values(["gid", "grem"], ascending=[True, False])
    D["poss_idx"] = D.groupby("gid").cumcount()
    D["poss_frac"] = D.groupby("gid").poss_idx.transform(lambda s: s / max(1, s.max()))
    return D


def main():
    D = pd.read_parquet(LEGACY)
    n0, c0 = len(D), set(D.columns)
    D = enrich(D)
    new = sorted(set(D.columns) - c0)
    tmp = LEGACY + ".tmp"
    D.to_parquet(tmp, index=False)
    os.replace(tmp, LEGACY)
    print(f"enriched {n0} possessions with {len(new)} cross-aspect signals: {new}")
    print("\nraw PPP by aspect-state (sanity):")
    for c in ["is_clutch", "fastbreak", "early_clock", "late_clock", "garbage", "prev_scored"]:
        on = D[D[c] == 1].pts.mean(); off = D[D[c] == 0].pts.mean()
        print(f"  {c:12s} rate {D[c].mean()*100:4.1f}%  PPP on {on:.3f} / off {off:.3f}  (delta {on-off:+.3f})")


if __name__ == "__main__":
    main()
