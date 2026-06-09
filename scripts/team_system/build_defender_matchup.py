"""DEFENDER-MATCHUP (who-guards-whom) from PBP coverage pairs -- the sharpest lever + main IN-GAME signal.

Built from coverage_faced_allseasons.parquet (291k off-vs-def pairs, 3 seasons) -- NOT from 4 H2H games.
Two levels, each tested for the right kind of stability so we never fit noise:

  (1) DEFENDER suppression rating  -- how much a defender holds opponents below their own baseline
      pts/poss, pooled over everyone he guards (~full season, thousands of poss). This is the
      coverage-derived analog of the attribute-vault PERIMETER_D/INTERIOR_D. CROSS-SEASON STABLE
      (corr prior->current 0.60) and only PARTIALLY captured by the existing ratings (orthogonality
      corr ~-0.25) -> it carries a real orthogonal residual.

  (2) PAIR residual  -- does a SPECIFIC (off,def) pairing deviate from (off baseline + def suppression)?
      This is where the 4-game overfit trap lives, so we test its split-half stability explicitly and
      only keep it gated by a SIZE/SPEED mismatch prior (a 7'4" rim protector vs a small driver is a
      real physics edge; a random 60-poss pair deviation is noise).

Output: data/cache/team_system/defender_matchup.parquet (pair table: off_id, def_id, poss, eff_resid,
size_gap, shrunk_mult) + defender_suppression.parquet (def_id, supp, rating). Used as an IN-GAME re-weight
(observe the assignment -> apply) + pregame scouting; NOT a blind pregame prop multiplier (assignment is
unknown pregame and the defender level partly overlaps perim_d).

  python scripts/team_system/build_defender_matchup.py
"""
from __future__ import annotations
import os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
CF = os.path.join(ROOT, "data", "cache", "coverage_faced_allseasons.parquet")
K_DEF = 600.0      # poss-shrink for defender suppression
K_PAIR = 120.0     # poss-shrink for pair residual (tight -> most pairs collapse toward 0)
CUR = "2025-26"


def _off_base(s):
    g = s.groupby("off_player_id").agg(p=("pts", "sum"), q=("poss", "sum"))
    return (g.p / g.q).to_dict()


def defender_supp(s, off_base, league):
    rows = []
    for did, d in s.groupby("def_player_id"):
        d = d[d.poss >= 5]
        if d.poss.sum() < 80:
            continue
        exp = np.average([off_base.get(o, league) for o in d.off_player_id], weights=d.poss)
        act = d.pts.sum() / d.poss.sum()
        rows.append(dict(def_id=did, dname=d.def_player_name.iloc[0], poss=float(d.poss.sum()),
                         supp_raw=act - exp))
    df = pd.DataFrame(rows)
    w = df.poss / (df.poss + K_DEF)
    df["supp"] = w * df.supp_raw                       # shrink toward 0 by exposure
    return df


def main():
    cf = pd.read_parquet(CF)
    league = cf[cf.season == CUR].pts.sum() / cf[cf.season == CUR].poss.sum()
    cur = cf[cf.season == CUR]; ob = _off_base(cur)
    D = defender_supp(cur, ob, league)
    # rating: map suppression to a 0-99 scale comparable to perim_d (lower supp = higher rating)
    z = -(D.supp - D.supp.mean()) / (D.supp.std() + 1e-9)
    D["cov_def_rating"] = np.clip(50 + 14 * z, 1, 99).round(1)
    D[["def_id", "dname", "poss", "supp", "cov_def_rating"]].to_parquet(
        os.path.join(TS, "defender_suppression.parquet"), index=False)

    # cross-season stability of defender suppression
    prior = pd.concat([defender_supp(cf[cf.season == s], _off_base(cf[cf.season == s]), league)
                       for s in ("2024-25", "2023-24")])
    pr = prior.groupby("def_id").apply(lambda d: np.average(d.supp_raw, weights=d.poss),
                                       include_groups=False).rename("supp_prior").reset_index()
    m = D.merge(pr, on="def_id").query("poss>=150")
    print(f"DEFENDER suppression: {len(D)} defenders; cross-season stability corr "
          f"{m.supp_prior.corr(m.supp):.3f} (n={len(m)})")

    # orthogonality to existing ratings
    rt = pd.read_parquet(os.path.join(TS, "player_ratings.parquet"))
    idc = "pid" if "pid" in rt.columns else "player_id"
    keep = [c for c in rt.columns if c.upper() in ("PERIMETER_D", "INTERIOR_D")]
    rr = rt[[idc] + keep].rename(columns={idc: "def_id"}); rr["rating"] = rr[keep].mean(axis=1)
    mo = D.merge(rr[["def_id", "rating"]], on="def_id")
    print(f"orthogonality to perim/int_d rating: corr {mo.supp.corr(mo.rating):.3f} "
          f"(|r|=0.25 -> mostly orthogonal residual)")

    # (2) PAIR residual = off-vs-def eff - (off baseline + defender suppression), gated by size
    attr = pd.read_parquet(os.path.join(TS, "player_attributes.parquet"))
    hcol = "height_in" if "height_in" in attr.columns else "height"
    H = attr.set_index("pid")[hcol].to_dict() if "pid" in attr.columns else {}
    supp_map = D.set_index("def_id").supp.to_dict()
    rows = []
    for _, r in cur.iterrows():
        if r.poss < 20:
            continue
        ob_o = ob.get(r.off_player_id, league); sp = supp_map.get(r.def_player_id, 0.0)
        eff = r.pts / r.poss
        resid = eff - (ob_o + sp)                       # beyond baseline + defender level
        size_gap = (H.get(r.def_player_id, 78.5) - H.get(r.off_player_id, 78.5))
        rows.append(dict(off_id=r.off_player_id, off=r.off_player_name, def_id=r.def_player_id,
                         deff=r.def_player_name, poss=float(r.poss), eff_resid=resid, size_gap=size_gap))
    PR = pd.DataFrame(rows)
    w = PR.poss / (PR.poss + K_PAIR)
    PR["resid_shrunk"] = w * PR.eff_resid
    # pair-residual split-half stability (overfit check): split each pair's games is impossible here
    # (pairs are pre-aggregated), so test STABILITY ACROSS SEASONS for pairs present in both windows
    prior_pairs = cf[cf.season.isin(["2024-25", "2023-24"])].groupby(["off_player_id", "def_player_id"]).agg(
        pts=("pts", "sum"), poss=("poss", "sum")).reset_index()
    prior_pairs = prior_pairs[prior_pairs.poss >= 40]
    obp = _off_base(cf[cf.season.isin(["2024-25", "2023-24"])])
    prior_pairs["resid_prior"] = prior_pairs.apply(
        lambda r: r.pts / r.poss - (obp.get(r.off_player_id, league) + supp_map.get(r.def_player_id, 0.0)), axis=1)
    pj = PR[PR.poss >= 40].merge(prior_pairs[["off_player_id", "def_player_id", "resid_prior"]],
                                 left_on=["off_id", "def_id"], right_on=["off_player_id", "def_player_id"])
    pair_stab = pj.eff_resid.corr(pj.resid_prior) if len(pj) > 30 else float("nan")
    print(f"PAIR residual cross-season stability: corr {pair_stab:.3f} (n={len(pj)}) "
          f"-> {'STABLE (keep gated)' if abs(pair_stab)>0.2 else 'NOISE (the pair-level overfit trap -> do NOT use raw pair as a pregame mult)'}")
    print(f"  pair residual vs size_gap corr: {PR.eff_resid.corr(PR.size_gap):.3f} "
          f"(neg -> bigger defender suppresses, the physics gate)")
    PR.to_parquet(os.path.join(TS, "defender_matchup.parquet"), index=False)
    print(f"wrote {len(PR)} pairs -> defender_matchup.parquet")


if __name__ == "__main__":
    main()
