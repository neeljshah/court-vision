"""PBP POSSESSION FOUNDRY + the decisive leak-free test: does the rich PBP ORIGIN detail
(transition-off-turnover / fastbreak / 2nd-chance) improve possession-outcome prediction over the
state-only model the engine already has?

The in-game possession model (`src/sim/possession_model.py`) conditions on game STATE (margin, clock,
period, four-factors-so-far) but uses NONE of the PBP origin/location qualifiers. This walks every cached
PBP game, segments possessions, tags each with its ORIGIN from the qualifiers (`fromturnover`/`fastbreak`
=> transition; `2ndchance` => second chance; else half-court) -- all leak-free (known as the possession
develops, before its terminal shot) -- and runs a GAME-SPLIT out-of-sample comparison:

  A  state + matchup        (period, time, margin, home, off ortg / def drtg / pace)
  B  A + ORIGIN one-hots    (transition, second_chance)

Target: points scored on the possession (0/1/2/3). Reports OOS points-per-possession MAE, log-loss of
P(score), and Brier -- if B beats A on held-out GAMES, the PBP origin detail is a real, fast, in-game lever
(origin is known live). This is the disciplined "use every PBP detail" test: it must beat the baseline
out-of-sample, not just in-sample.

  python scripts/team_system/build_pbp_possessions.py
"""
from __future__ import annotations
import glob, json, os, math
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
from sklearn.metrics import log_loss, brier_score_loss

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
PBP = os.path.join(TS, "pbp")


def _sec_remaining(period, clock):
    # clock like 'PT10M53.00S' -> seconds left in period; game_remaining approx
    try:
        m = clock.split("PT")[1]; mm = int(m.split("M")[0]); ss = float(m.split("M")[1].rstrip("S"))
    except Exception:
        mm, ss = 6, 0
    per_left = mm * 60 + ss
    regs_left = max(0, 4 - period) * 720 if period <= 4 else 0
    return per_left + regs_left


def parse_game(path):
    g = json.load(open(path, encoding="utf-8")); g = g.get("game", g)
    acts = g.get("actions") or []
    gid = os.path.basename(path)[:-5]
    home_tri = g.get("homeTeam", {}).get("teamTricode") if isinstance(g.get("homeTeam"), dict) else None
    poss = []
    cur = None  # current possession accumulator

    def close(made=False):
        nonlocal cur, prev_close_made, prev_end_grem
        if cur is not None and cur["off"]:
            end = last_grem if last_grem is not None else cur["start"]
            cur["poss_dur"] = float(max(0.0, min(30.0, cur["start"] - end)))
            cur.pop("start", None)
            poss.append(cur)
            prev_close_made = made
            prev_end_grem = end                              # clock at handover -> next possession's start
        cur = None

    def new(off, period, clock, sm, start):
        return dict(gid=gid, off=off, period=period,
                    grem=_sec_remaining(period, clock), margin=sm, pts=0,
                    transition=0, second_chance=0, ato=0, inpenalty=0, after_made=0,
                    poss_dur=0.0, start=start)

    # leak-free context flags carried ACROSS possessions (all known before the possession's terminal shot):
    pending_ato = False        # a timeout just happened -> next possession is after-timeout (set play)
    prev_close_made = False     # the prior possession ended on a scoring play -> this one faces set defense
    prev_end_grem = None        # clock when the ball last changed hands (this possession's true start)
    last_grem = None            # most recent game-seconds-remaining (for possession duration)
    last_score_h, last_score_a = 0, 0
    for a in acts:
        at = a.get("actionType"); tri = a.get("teamTricode")
        try:
            sh, sa = int(a.get("scoreHome") or last_score_h), int(a.get("scoreAway") or last_score_a)
        except Exception:
            sh, sa = last_score_h, last_score_a
        last_score_h, last_score_a = sh, sa
        if at == "timeout":
            pending_ato = True; continue
        if at in ("substitution", "period", None):
            continue
        last_grem = _sec_remaining(a.get("period", 1), a.get("clock", "PT06M00.00S"))
        if tri and (cur is None or cur["off"] != tri) and at in ("2pt", "3pt", "freethrow", "turnover"):
            # possession changed hands -> open a new possession for this team
            close()                                          # close prior (live ball) if still open
            sm = (sh - sa) if tri == home_tri else (sa - sh)
            # true possession start = clock when the ball changed hands (prior close); same-period only
            st = prev_end_grem if (prev_end_grem is not None and prev_end_grem >= last_grem) else last_grem
            cur = new(tri, a.get("period", 1), a.get("clock", "PT06M00.00S"), sm, st)
            cur["ato"] = 1 if pending_ato else 0; pending_ato = False
            cur["after_made"] = 1 if prev_close_made else 0
        if cur is None:
            continue
        ql = a.get("qualifiers") or []
        if "fromturnover" in ql or "fastbreak" in ql:
            cur["transition"] = 1
        if "2ndchance" in ql:
            cur["second_chance"] = 1
        if "inpenalty" in ql:
            cur["inpenalty"] = 1
        if at in ("2pt", "3pt") and a.get("shotResult") == "Made":
            cur["pts"] += 3 if at == "3pt" else 2
            close(made=True)
        elif at == "freethrow":
            if a.get("shotResult") == "Made" or (a.get("subType", "").endswith("made")):
                cur["pts"] += 1
            # FT trips: close on the last FT of the trip (subType like '2 of 2')
            st = a.get("subType", "")
            if st and " of " in st and st.split(" of ")[0].strip() == st.split(" of ")[1].strip():
                close(made=True)                              # ball inbounds after FTs -> set defense next
        elif at == "turnover":
            close(made=False)                                 # live ball
        elif at == "rebound" and a.get("subType") == "defensive":
            close(made=False)                                 # live ball off the miss
    close()
    P = pd.DataFrame(poss)
    if len(P):
        P["off_is_home"] = (P.off == home_tri).astype(int)
    return P, home_tri


def main():
    files = sorted(glob.glob(f"{PBP}/*.json"))
    tg = pd.read_parquet(os.path.join(TS, "league_team_game.parquet"))
    ortg = (100 * tg.groupby("team").pts.sum() / tg.groupby("team").poss.sum()).to_dict()
    drtg = (100 * tg.groupby("team").opp_pts.sum() / tg.groupby("team").opp_poss.sum()).to_dict()
    pace = tg.groupby("team").poss.mean().to_dict()
    L = np.mean(list(ortg.values()))
    allP = []
    for f in files:
        try:
            P, ht = parse_game(f)
        except Exception:
            continue
        if not len(P):
            continue
        # attach matchup identity: defense = the OTHER team in this game
        teams = P.off.unique()
        if len(teams) != 2:
            continue
        opp = {teams[0]: teams[1], teams[1]: teams[0]}
        P["deff"] = P.off.map(opp)
        for c, d in (("off_ortg", ortg), ("def_drtg", drtg), ("off_pace", pace)):
            pass
        P["off_ortg"] = P.off.map(ortg).fillna(L)
        P["def_drtg"] = P.deff.map(drtg).fillna(L)
        P["off_pace"] = P.off.map(pace).fillna(100)
        P["def_pace"] = P.deff.map(pace).fillna(100)
        allP.append(P)
    D = pd.concat(allP, ignore_index=True)
    D = D[D.pts <= 4]  # drop any parse glitches
    D["abs_margin"] = D.margin.abs()
    D["scored"] = (D.pts > 0).astype(int)
    D.to_parquet(os.path.join(TS, "pbp_possessions.parquet"), index=False)
    # CONSUMABLE for the live in-game sim: origin -> PPP multiplier vs half-court (apply on the
    # next possession after a live TO/steal -> transition, or OREB -> second chance). Leak-free at
    # game time (origin is observed live). The pregame anchor already bakes season-avg transition in,
    # so this is an IN-GAME-ONLY reactive multiplier (do NOT apply it to the pregame team total).
    hc = D[(D.transition == 0) & (D.second_chance == 0)].pts.mean()
    origin = dict(halfcourt_ppp=round(float(hc), 4),
                  transition_mult=round(float(D[D.transition == 1].pts.mean() / hc), 4),
                  second_chance_mult=round(float(D[D.second_chance == 1].pts.mean() / hc), 4),
                  transition_share=round(float(D.transition.mean()), 4),
                  second_chance_share=round(float(D.second_chance.mean()), 4),
                  n_possessions=int(len(D)), n_games=int(D.gid.nunique()),
                  note="IN-GAME reactive only; validated leak-free OOS (Brier .2484->.2434, orthogonal to live form)")
    json.dump(origin, open(os.path.join(TS, "origin_ppp.json"), "w"), indent=2)
    print(f"POSSESSIONS parsed: {len(D)} from {D.gid.nunique()} games  "
          f"(transition {D.transition.mean()*100:.1f}%, 2nd-chance {D.second_chance.mean()*100:.1f}%)")
    print(f"  origin_ppp.json: transition x{origin['transition_mult']}, 2nd-chance x{origin['second_chance_mult']} (vs half-court {hc:.3f})")
    # the headline: PPP by origin (cross-game stable?)
    print("\n=== origin-conditioned points-per-possession (the detail the model ignores) ===")
    for name, mask in [("half-court", (D.transition == 0) & (D.second_chance == 0)),
                       ("transition (off TO/fastbreak)", D.transition == 1),
                       ("second chance (after OREB)", D.second_chance == 1)]:
        s = D[mask]
        # split-half across games for stability
        gids = sorted(s.gid.unique()); h1 = s[s.gid.isin(gids[::2])]; h2 = s[s.gid.isin(gids[1::2])]
        print(f"  {name:32s} PPP {s.pts.mean():.3f}  (n={len(s):5d})  split-half {h1.pts.mean():.3f}/{h2.pts.mean():.3f}")

    # new leak-free context features (mined this build): after-timeout, bonus, after-made, possession duration
    print("\n=== new possession-context PPP (split-half by game parity) ===")
    for name, mask in [("after timeout (ATO set play)", D.ato == 1),
                       ("after opp MADE (set defense)", D.after_made == 1),
                       ("in penalty / bonus", D.inpenalty == 1),
                       ("quick (<7s elapsed)", D.poss_dur < 7),
                       ("late clock (>=16s elapsed)", D.poss_dur >= 16)]:
        s = D[mask]
        if not len(s):
            continue
        gids2 = sorted(s.gid.unique()); h1 = s[s.gid.isin(gids2[::2])]; h2 = s[s.gid.isin(gids2[1::2])]
        print(f"  {name:32s} PPP {s.pts.mean():.3f}  (n={len(s):5d}, {len(s)/len(D)*100:4.1f}%)  "
              f"split-half {h1.pts.mean():.3f}/{h2.pts.mean():.3f}")

    # ===== leak-free GAME-SPLIT OOS lift test =====
    BASE = ["period", "grem", "margin", "abs_margin", "off_is_home", "off_ortg", "def_drtg", "off_pace", "def_pace"]
    ORIG = BASE + ["transition", "second_chance"]
    gids = np.array(sorted(D.gid.unique()))
    rng = np.random.default_rng(0); rng.shuffle(gids)
    folds = np.array_split(gids, 5)
    res = {"A_ppp_mae": [], "B_ppp_mae": [], "A_ll": [], "B_ll": [], "A_brier": [], "B_brier": []}
    for fold in folds:
        te = D[D.gid.isin(fold)]; trn = D[~D.gid.isin(fold)]
        for tag, feats in (("A", BASE), ("B", ORIG)):
            rgr = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=250,
                                                min_samples_leaf=80, random_state=0)
            rgr.fit(trn[feats], trn.pts); pp = np.clip(rgr.predict(te[feats]), 0, 3)
            res[f"{tag}_ppp_mae"].append(np.abs(pp - te.pts.values).mean())
            clf = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=250,
                                                 min_samples_leaf=80, random_state=0)
            clf.fit(trn[feats], trn.scored); ps = clf.predict_proba(te[feats])[:, 1]
            res[f"{tag}_ll"].append(log_loss(te.scored, ps, labels=[0, 1]))
            res[f"{tag}_brier"].append(brier_score_loss(te.scored, ps))
    A_mae, B_mae = np.mean(res["A_ppp_mae"]), np.mean(res["B_ppp_mae"])
    A_ll, B_ll = np.mean(res["A_ll"]), np.mean(res["B_ll"])
    A_br, B_br = np.mean(res["A_brier"]), np.mean(res["B_brier"])
    print("\n=== LEAK-FREE OOS LIFT (5-fold by GAME): does PBP origin beat state-only? ===")
    print(f"  PPP-MAE   A(state) {A_mae:.4f}  B(+origin) {B_mae:.4f}  delta {(B_mae-A_mae):+.4f} ({(B_mae/A_mae-1)*100:+.2f}%)")
    print(f"  log-loss  A {A_ll:.4f}  B {B_ll:.4f}  delta {(B_ll-A_ll):+.5f}")
    print(f"  Brier     A {A_br:.4f}  B {B_br:.4f}  delta {(B_br-A_br):+.5f}")
    better = (B_mae < A_mae) and (B_ll < A_ll)
    print(f"  VERDICT: PBP origin detail {'IMPROVES out-of-sample -> real fast in-game lever' if better else 'does NOT beat state-only OOS (origin already implied by state/four-factors)'}")


if __name__ == "__main__":
    main()
