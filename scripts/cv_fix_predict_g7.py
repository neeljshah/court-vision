"""
cv_fix_predict_g7.py — PRE-GAME prediction for WCF Game 7 (0042500317, OKC home, series 3-3),
built from the 6 prior games of the actual series. Outputs player prop projections + team
win probability + intelligence.

Method: aggregate each player's SERIES shot profile (zone mix) + per-game volume MEAN & SD
(empirical — fixes the Poisson over-dispersion); simulate Game 7 with talent + home-court.
"""
from __future__ import annotations
import json, math, os, random
from collections import defaultdict

random.seed(7)
CV = "data/cache/cv_fix"
GAMES = ["0042500311", "0042500312", "0042500313", "0042500314", "0042500315", "0042500316"]
HOME_G7 = "OKC"           # Game 7 host (higher seed)
HCA_XFG = 1.025           # home-court field-goal boost (~+2-3 team pts), league-typical
NSIMS = 20000
RECENCY = {0: 0.8, 1: 0.85, 2: 0.9, 3: 1.0, 4: 1.1, 5: 1.25}  # weight later games more (form)

ZONE_FG = {"Restricted Area": 0.625, "In The Paint (Non-RA)": 0.435, "Mid-Range": 0.415,
           "Left Corner 3": 0.385, "Right Corner 3": 0.385, "Above the Break 3": 0.360, "Backcourt": 0.02}
ZPTS = lambda z: 3 if "3" in z else 2  # noqa: E731


def load(p):
    return json.load(open(p)) if os.path.exists(p) else None


def main():
    # per player accumulation
    pid_name, pid_team = {}, {}
    zone_ct = defaultdict(lambda: defaultdict(float))      # pid -> zone -> weighted count
    fga_by_game = defaultdict(dict); fta_by_game = defaultdict(dict)
    ftm_by_game = defaultdict(dict); pts_by_game = defaultdict(dict)
    reb_by_game = defaultdict(dict); ast_by_game = defaultdict(dict)
    fgm_tot = defaultdict(float); fg3m_tot = defaultdict(float); fga_tot = defaultdict(float)
    team_fga_tot = defaultdict(float); team_fta_tot = defaultdict(float)  # for volume normalization
    # series zone FG% (pooled, both teams) — anchors the make-model to THIS series' shooting
    zone_made = defaultdict(float); zone_att = defaultdict(float)

    for gi, g in enumerate(GAMES):
        nd = f"{CV}/nba_{g}"
        w = RECENCY[gi]
        sc = load(f"{nd}/shotchart.json") or []
        for s in sc:
            zone_ct[s["PLAYER_ID"]][s["SHOT_ZONE_BASIC"]] += w
            zone_att[s["SHOT_ZONE_BASIC"]] += 1
            zone_made[s["SHOT_ZONE_BASIC"]] += s["SHOT_MADE_FLAG"]
        box = load(f"{nd}/box_traditional.json") or []
        for b in box:
            pid = b.get("personId"); st = b.get("statistics", b)
            mins = str(st.get("minutes", "0"))
            if mins in ("0", "0:00", "", "PT00M00.00S"):
                continue
            nm = b.get("nameI") or f"{b.get('firstName','')} {b.get('familyName','')}".strip()
            # disambiguate the two OKC J. Williams (Jalen vs Jaylin)
            fam = b.get("familyName", ""); first = b.get("firstName", "")
            if nm.startswith("J. Williams") and first:
                nm = f"{first[:4]}. {fam}"
            pid_name[pid] = nm
            pid_team[pid] = b.get("teamTricode", "")
            fga_by_game[pid][gi] = st.get("fieldGoalsAttempted", 0) or 0
            fta_by_game[pid][gi] = st.get("freeThrowsAttempted", 0) or 0
            ftm_by_game[pid][gi] = st.get("freeThrowsMade", 0) or 0
            pts_by_game[pid][gi] = st.get("points", 0) or 0
            reb_by_game[pid][gi] = st.get("reboundsTotal", 0) or 0
            ast_by_game[pid][gi] = st.get("assists", 0) or 0
            fgm_tot[pid] += st.get("fieldGoalsMade", 0) or 0
            fg3m_tot[pid] += st.get("threePointersMade", 0) or 0
            fga_tot[pid] += st.get("fieldGoalsAttempted", 0) or 0
            team_fga_tot[b.get("teamTricode", "")] += st.get("fieldGoalsAttempted", 0) or 0
            team_fta_tot[b.get("teamTricode", "")] += st.get("freeThrowsAttempted", 0) or 0

    # ── Availability handling (the #1 swing factor) ──────────────────────────
    # Exclude players who didn't play either of the last 2 games (G5/G6) — likely out for G7
    # (auto-drops A. Mitchell, last played G3). Jalen Williams (1631114) is the unknown:
    # injured G2, missed G3-G5, 1-shot token return G6 — run as a scenario.
    JWILL = os.environ.get("JWILL", "blend"); JW = 1631114
    if JWILL == "healthy":  # use his last HEALTHY game (G1) profile
        for d in (fga_by_game, fta_by_game, ftm_by_game, pts_by_game, reb_by_game, ast_by_game):
            if JW in d and 0 in d[JW]:
                d[JW] = {0: d[JW][0]}

    # series zone FG% (shrunk toward league prior with k=20 pseudo-attempts)
    LEAGUE = {"Restricted Area": 0.625, "In The Paint (Non-RA)": 0.435, "Mid-Range": 0.415,
              "Left Corner 3": 0.385, "Right Corner 3": 0.385, "Above the Break 3": 0.360, "Backcourt": 0.05}
    ZONE_FG_SER = {}
    for z, att in zone_att.items():
        prior = LEAGUE.get(z, 0.40); k = 20
        ZONE_FG_SER[z] = (zone_made[z] + k * prior) / (att + k)
    # series-average eFG (for per-player personalization denominator)
    ser_efg = ((sum(fgm_tot.values()) + 0.5 * sum(fg3m_tot.values())) / max(1, sum(fga_tot.values())))

    def mean_sd(d):
        v = list(d.values())
        if not v:
            return 0.0, 0.0
        m = sum(v) / len(v)
        sd = (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5 if len(v) > 1 else max(1.0, m ** 0.5)
        return m, sd

    # build sim model per player
    pm = {}
    for pid in pid_name:
        # availability: must have played G5 or G6 (idx 4 or 5); else likely out for G7
        if not ({4, 5} & set(fga_by_game[pid].keys())):
            continue
        if JWILL == "out" and pid == JW:
            continue
        zc = zone_ct[pid]
        if not zc:
            continue
        ztot = sum(zc.values())
        zones = list(zc.keys()); zprob = [zc[z] / ztot for z in zones]
        fga_m, fga_s = mean_sd(fga_by_game[pid])
        if fga_m < 1:
            continue
        fta_m, fta_s = mean_sd(fta_by_game[pid])
        ftm_tot = sum(ftm_by_game[pid].values()); fta_tot = sum(fta_by_game[pid].values())
        ft_pct = (ftm_tot / fta_tot) if fta_tot else 0.75
        reb_m, reb_s = mean_sd(reb_by_game[pid]); ast_m, ast_s = mean_sd(ast_by_game[pid])
        # in-series shooting personalization: player's series eFG (shrunk) vs series average
        att = fga_tot[pid]
        raw_efg = (fgm_tot[pid] + 0.5 * fg3m_tot[pid]) / max(1, att)
        k = 25
        shr_efg = (att * raw_efg + k * ser_efg) / (att + k)
        pers = max(0.85, min(1.20, shr_efg / ser_efg)) if ser_efg else 1.0
        hca = HCA_XFG if pid_team[pid] == HOME_G7 else 1.0
        # Jalen-Williams-return team-efficiency factor on OKC (his All-NBA creation lifts the
        # whole offense). Series-pooled FG% already blends his in/out games; this shifts OKC
        # for the scenario: healthy +3% eFG, blend +1%, out -1% (relative to the blended base).
        if pid_team[pid] == "OKC":
            hca *= {"healthy": 1.03, "out": 0.99}.get(JWILL, 1.01)
        pm[pid] = dict(name=pid_name[pid], team=pid_team[pid], zones=zones, zprob=zprob,
                       fga_m=fga_m, fga_s=fga_s, fta_m=fta_m, fta_s=fta_s, ft_pct=ft_pct,
                       reb_m=reb_m, reb_s=reb_s, ast_m=ast_m, ast_s=ast_s, pers=pers, hca=hca,
                       gp=len(fga_by_game[pid]), pts_series=mean_sd(pts_by_game[pid])[0])

    # Normalize each team's simulated shot/FT volume to its series-average team totals,
    # so summing per-player per-game means doesn't inflate team possessions.
    for team in ("OKC", "SAS"):
        cur_fga = sum(m["fga_m"] for m in pm.values() if m["team"] == team)
        tgt_fga = team_fga_tot[team] / len(GAMES)
        sf = (tgt_fga / cur_fga) if cur_fga else 1.0
        cur_fta = sum(m["fta_m"] for m in pm.values() if m["team"] == team)
        tgt_fta = team_fta_tot[team] / len(GAMES)
        sft = (tgt_fta / cur_fta) if cur_fta else 1.0
        for m in pm.values():
            if m["team"] == team:
                m["fga_m"] *= sf; m["fga_s"] *= sf
                m["fta_m"] *= sft; m["fta_s"] *= sft

    def rnorm(m, s):
        return max(0, int(round(random.gauss(m, max(0.5, s)))))

    pts_d = defaultdict(list); reb_d = defaultdict(list); ast_d = defaultdict(list); pra_d = defaultdict(list)
    team_d = defaultdict(list); wins = defaultdict(int)
    for _ in range(NSIMS):
        tot = defaultdict(int)
        for pid, m in pm.items():
            nfga = rnorm(m["fga_m"], m["fga_s"]); pts = 0
            for _ in range(nfga):
                z = random.choices(m["zones"], weights=m["zprob"])[0]
                if random.random() < max(0.02, min(0.97, ZONE_FG_SER.get(z, 0.4) * m["pers"] * m["hca"])):
                    pts += ZPTS(z)
            nfta = rnorm(m["fta_m"], m["fta_s"])
            for _ in range(nfta):
                if random.random() < m["ft_pct"]:
                    pts += 1
            rb = rnorm(m["reb_m"], m["reb_s"]); a = rnorm(m["ast_m"], m["ast_s"])
            pts_d[pid].append(pts); reb_d[pid].append(rb); ast_d[pid].append(a); pra_d[pid].append(pts + rb + a)
            tot[m["team"]] += pts
        for t in ("OKC", "SAS"):
            team_d[t].append(tot[t])
        wins["OKC" if tot["OKC"] >= tot["SAS"] else "SAS"] += 1

    def pc(a):
        a = sorted(a); n = len(a)
        return dict(mean=round(sum(a) / n, 1), p25=a[n // 4], p50=a[n // 2], p75=a[3 * n // 4],
                    p10=a[n // 10], p90=a[9 * n // 10])

    out = {"game": "0042500317 (WCF Game 7)", "home": HOME_G7, "series": "3-3",
           "win_prob": {t: round(100 * wins[t] / NSIMS, 1) for t in ("OKC", "SAS")},
           "team_score": {t: pc(team_d[t]) for t in ("OKC", "SAS")}, "players": {}}
    for pid, m in pm.items():
        out["players"][m["name"]] = {"team": m["team"], "gp": m["gp"],
            "pts": pc(pts_d[pid]), "reb": pc(reb_d[pid]), "ast": pc(ast_d[pid]), "pra": pc(pra_d[pid]),
            "series_ppg": round(m["pts_series"], 1), "form_mult": round(m["pers"], 3)}
    json.dump(out, open(f"{CV}/predict_g7.json", "w"), indent=2)

    # console
    print("="*70)
    print("WCF GAME 7 PREDICTION — OKC (home) vs SAS — series 3-3")
    print("="*70)
    print(f"WIN PROBABILITY:  OKC {out['win_prob']['OKC']}%   SAS {out['win_prob']['SAS']}%")
    ts = out["team_score"]
    print(f"PROJECTED SCORE:  OKC {ts['OKC']['mean']} ({ts['OKC']['p25']}-{ts['OKC']['p75']})  "
          f"SAS {ts['SAS']['mean']} ({ts['SAS']['p25']}-{ts['SAS']['p75']})")
    print(f"\n{'Player':24s} {'Tm':3s} {'GP':2s} {'PTS(p25-75)':>14s} {'REB':>9s} {'AST':>9s} {'PRA(p25-75)':>13s}")
    for pid, m in sorted(pm.items(), key=lambda kv: -out["players"][kv[1]['name']]["pra"]["mean"]):
        r = out["players"][m["name"]]
        if r["pra"]["mean"] < 6:
            continue
        p, rb, a, pra = r["pts"], r["reb"], r["ast"], r["pra"]
        print(f"{m['name']:24s} {m['team']:3s} {r['gp']:2d} "
              f"{p['mean']:5.1f}({p['p25']:2d}-{p['p75']:2d}) {rb['mean']:4.1f}({rb['p25']}-{rb['p75']}) "
              f"{a['mean']:4.1f}({a['p25']}-{a['p75']}) {pra['mean']:5.1f}({pra['p25']:2d}-{pra['p75']:2d})")
    print(f"\nwrote {CV}/predict_g7.json")


if __name__ == "__main__":
    main()
