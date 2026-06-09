"""
cv_fix_simulate.py <gid> [nsims] — Tracking-driven game simulator (expected box score).

Simulates the game possession-shot by shot from REAL inputs, isolating shot QUALITY from
shot-MAKING, with the CV layer supplying contest difficulty:

  shot profile     : each player's actual shot locations/zones      (NBA shotchart — truth)
  base make-model  : league FG% by zone                              (NBA league avg — truth)
  CV contest layer : defender distance at the shot frame -> xFG mult (anchored CV — the moat)
  volume/secondary : FTA/FT%, REB, AST, TOV per player               (NBA box — truth)

For each of N sims, every shot is resolved make/miss ~ Bernoulli(xFG); points aggregate to a
per-player distribution. Comparing the simulated EXPECTED output to the ACTUAL box isolates
who beat / fell short of their shot quality, and the CV contest layer explains why
(open miss = variance/skill; contested miss = defense).

Outputs: data/cache/cv_fix/sim_<gid>.json  + console validation table.
"""
from __future__ import annotations
import json, math, os, sys
from collections import defaultdict

GID = sys.argv[1]
NSIMS = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
NBA = f"data/cache/cv_fix/nba_{GID}" if os.path.isdir(f"data/cache/cv_fix/nba_{GID}") else "data/cache/cv_fix/nba"
ANCHORED = f"data/cache/cv_fix/anchored_{GID}.csv"

# Deterministic PRNG (Date/Random-free determinism not required, but seed for reproducibility).
import random
random.seed(42)

# League FG% priors by zone (NBA ~2024-26 baselines; refined below from league-avg file if present)
ZONE_FG = {
    "Restricted Area": 0.625, "In The Paint (Non-RA)": 0.435, "Mid-Range": 0.415,
    "Left Corner 3": 0.385, "Right Corner 3": 0.385, "Above the Break 3": 0.360,
    "Backcourt": 0.02,
}
ZONE_PTS = lambda z: 3 if "3" in z else 2  # noqa: E731


def load_json(p):
    return json.load(open(p)) if os.path.exists(p) else None


def refine_zone_fg():
    la = load_json(f"{NBA}/shotchart_league_avg.json")
    if not la:
        return
    for row in la:
        z = row.get("SHOT_ZONE_BASIC")
        fga = row.get("FGA") or 0
        fgm = row.get("FGM") or 0
        if z in ZONE_FG and fga and fga > 50:
            ZONE_FG[z] = max(0.05, min(0.95, fgm / fga))


def contest_mult_by_player():
    """From anchored CV: a per-player xFG multiplier based on how contested their shots were
    vs ~6ft neutral. Closer defender -> lower make. Conservative slope (+/-1.5% per foot,
    capped +/-12%). Only players with >=2 contest-resolved shots; else neutral (1.0)."""
    mult = defaultdict(lambda: 1.0)
    if os.environ.get("COURTV_NO_CONTEST") == "1" or not os.path.exists(ANCHORED):
        return mult, {}
    import csv
    per = defaultdict(list)
    for r in csv.DictReader(open(ANCHORED)):
        cf = r.get("contest_ft"); bd = r.get("ball_dist_to_shooter_ft")
        if cf in ("", "None") or bd in ("", "None"):
            continue
        if float(bd) > 12:
            continue
        per[r["name"]].append(float(cf))
    info = {}
    for name, cs in per.items():
        if len(cs) < 2:
            continue
        avg = sum(cs) / len(cs)
        slope = 0.015  # FG% per foot of extra separation
        m = 1.0 + max(-0.12, min(0.12, (avg - 6.0) * slope))
        mult[name] = m
        info[name] = {"n_contest": len(cs), "avg_contest_ft": round(avg, 1), "xfg_mult": round(m, 3)}
    return mult, info


def main():
    refine_zone_fg()
    cmult, cinfo = contest_mult_by_player()
    shots = load_json(f"{NBA}/shotchart.json")
    box = load_json(f"{NBA}/box_traditional.json")
    if not shots or not box:
        print("missing shotchart/box"); return

    # group shots per player (real locations/zones)
    pshots = defaultdict(list)
    for s in shots:
        pshots[s["PLAYER_NAME"]].append(s)

    # per-player secondary stats from box
    bx = {}
    for b in box:
        nm = b.get("firstName", "") + " " + b.get("familyName", "")
        nm = b.get("nameI") or nm
        st = b.get("statistics", b)
        bx[b.get("personId")] = {
            "name": b.get("nameI") or nm, "fullname": f"{b.get('firstName','')} {b.get('familyName','')}".strip(),
            "fta": st.get("freeThrowsAttempted", 0) or 0, "ftm": st.get("freeThrowsMade", 0) or 0,
            "pts": st.get("points", 0) or 0, "reb": st.get("reboundsTotal", 0) or 0,
            "ast": st.get("assists", 0) or 0, "min": st.get("minutes", "0"),
            "team": b.get("teamTricode", ""),
        }
    name_to_pid = {v["fullname"]: k for k, v in bx.items()}

    # Player true-talent shooting multiplier (season eFG vs league) — separates skill from luck.
    talent = load_json("data/cache/cv_fix/talent.json") or {"mult": {}}
    tmult = talent.get("mult", {})

    # Pre-build each player's per-shot xFG list + FT params
    pmodel = {}
    for pname, plist in pshots.items():
        pid = name_to_pid.get(pname)
        meta = bx.get(pid, {})
        fta = meta.get("fta", 0); ftm = meta.get("ftm", 0)
        cm = cmult.get(pname, 1.0)
        tm = float(tmult.get(str(pid), 1.0)) if pid is not None else 1.0
        xfgs = [(max(0.02, min(0.97, ZONE_FG.get(s["SHOT_ZONE_BASIC"], 0.40) * cm * tm)),
                 ZONE_PTS(s["SHOT_ZONE_BASIC"])) for s in plist]
        pmodel[pname] = {"xfgs": xfgs, "fta": int(fta), "ft_pct": (ftm / fta) if fta else 0.0,
                         "team": meta.get("team", ""), "cm": cm, "tm": round(tm, 3),
                         "actual_pts": meta.get("pts"), "fga": len(plist),
                         "reb": meta.get("reb", 0) or 0, "ast": meta.get("ast", 0) or 0}

    # Game-level sim: every sim resolves ALL shots so team totals & win prob are coherent.
    teams = sorted({m["team"] for m in pmodel.values() if m["team"]})
    pts_dist = defaultdict(list)
    reb_dist = defaultdict(list); ast_dist = defaultdict(list); pra_dist = defaultdict(list)
    team_dist = {t: [] for t in teams}
    team_wins = defaultdict(int)
    PREDICTIVE = os.environ.get("COURTV_PREDICTIVE") == "1"

    def pois(lam):
        # Knuth Poisson (random-module only; no numpy dependency)
        if lam <= 0:
            return 0
        L = math.exp(-lam); k = 0; p = 1.0
        while True:
            k += 1; p *= random.random()
            if p <= L:
                return k - 1

    for _ in range(NSIMS):
        tot = defaultdict(int)
        for pname, m in pmodel.items():
            pts = 0
            xfgs = m["xfgs"]; fta = m["fta"]
            if PREDICTIVE and xfgs:
                # Pre-game mode: shot VOLUME is uncertain — resample count ~Poisson(mean)
                # and draw that many shots WITH REPLACEMENT from the player's zone mix.
                k = pois(len(xfgs))
                shots = [random.choice(xfgs) for _ in range(k)]
                fta = pois(m["fta"])
            else:
                shots = xfgs
            for p_make, val in shots:
                if random.random() < p_make:
                    pts += val
            for _ft in range(fta):
                if random.random() < m["ft_pct"]:
                    pts += 1
            # REB/AST: rate-based (Poisson around box total) — more stable than shot-driven pts
            rb = pois(m["reb"]); asst = pois(m["ast"])
            pts_dist[pname].append(pts); reb_dist[pname].append(rb)
            ast_dist[pname].append(asst); pra_dist[pname].append(pts + rb + asst)
            if m["team"]:
                tot[m["team"]] += pts
        for t in teams:
            team_dist[t].append(tot[t])
        if len(teams) == 2:
            a, b = teams
            team_wins[a if tot[a] >= tot[b] else b] += 1

    def pctl(arr):
        a = sorted(arr); n = len(a)
        return {"mean": round(sum(a) / n, 1), "p10": a[n // 10], "p25": a[n // 4],
                "p50": a[n // 2], "p75": a[3 * n // 4], "p90": a[9 * n // 10]}

    results = {}
    for pname, m in pmodel.items():
        d = sorted(pts_dist[pname]); n = len(d)
        results[pname] = {"team": m["team"], "fga": m["fga"],
            "exp_pts_mean": round(sum(d) / n, 1), "p10": d[n // 10], "p50": d[n // 2],
            "p90": d[9 * n // 10], "actual_pts": m["actual_pts"],
            "xfg_mult": round(m["cm"], 3), "contest": cinfo.get(pname),
            "pts": pctl(pts_dist[pname]), "reb": pctl(reb_dist[pname]),
            "ast": pctl(ast_dist[pname]), "pra": pctl(pra_dist[pname]),
            "actual_reb": m["reb"], "actual_ast": m["ast"]}

    # team simulation: sum player points distributions are independent -> team expected
    out = {"game_id": GID, "nsims": NSIMS, "zone_fg_used": ZONE_FG, "players": {}}
    # rank by fga
    valid = sorted(results.items(), key=lambda kv: -kv[1]["fga"])
    covered = 0; total = 0
    print(f"\n=== TRACKING-DRIVEN SIM: {GID} ({NSIMS} sims) ===")
    print(f"{'player':22s} {'team':4s} {'FGA':>3s} {'expPTS(p10-p90)':>18s} {'actual':>6s} {'xFGmult':>7s} {'fit'}")
    for pname, r in valid:
        if r["fga"] < 3:
            continue
        out["players"][pname] = r
        ap = r["actual_pts"]
        fit = ""
        if ap is not None:
            total += 1
            inside = r["p10"] <= ap <= r["p90"]
            covered += int(inside)
            fit = "OK" if inside else ("OVER" if ap > r["p90"] else "UNDER")
        ct = f"{r['contest']['avg_contest_ft']}ft" if r.get("contest") else "-"
        print(f"{pname:22s} {r['team']:4s} {r['fga']:3d} "
              f"{r['exp_pts_mean']:5.1f} ({r['p10']:2d}-{r['p90']:2d})      "
              f"{str(ap):>6s} {r['xfg_mult']:7.3f} {fit} {ct}")
    out["calibration"] = {"players_checked": total, "actual_inside_p10_p90": covered,
                          "coverage_pct": round(100 * covered / max(1, total), 1)}
    print(f"\nCalibration: {covered}/{total} players' actual points inside sim p10-p90 "
          f"({out['calibration']['coverage_pct']}%) — target ~80% for a well-calibrated 10-90 band")

    # ── Team-level: score distributions + win probability + shot-quality verdict ──
    actual_team = defaultdict(int)
    for pname, m in pmodel.items():
        if m["team"] and m["actual_pts"] is not None:
            actual_team[m["team"]] += m["actual_pts"]
    out["teams"] = {}
    print(f"\n=== TEAM SIM (shots held to actual; resolves shot-MAKING variance only) ===")
    for t in teams:
        d = sorted(team_dist[t]); n = len(d)
        wp = round(100 * team_wins[t] / NSIMS, 1)
        out["teams"][t] = {"exp_score_mean": round(sum(d) / n, 1), "p10": d[n // 10],
                           "p50": d[n // 2], "p90": d[9 * n // 10], "actual": actual_team.get(t),
                           "win_prob_pct": wp}
        print(f"  {t}: expected {sum(d)/n:5.1f} (p10-p90 {d[n//10]}-{d[9*n//10]})  "
              f"actual {actual_team.get(t)}  sim win% {wp}")
    if len(teams) == 2:
        a, b = teams
        ea, eb = out["teams"][a]["exp_score_mean"], out["teams"][b]["exp_score_mean"]
        aa, ab = actual_team[a], actual_team[b]
        winner_actual = a if aa > ab else b
        winner_exp = a if ea > eb else b
        verdict = ("shot quality + volume DESERVED the result"
                   if winner_exp == winner_actual else
                   "result driven by shot-MAKING variance beyond shot quality")
        print(f"  -> Expected margin {a} {ea:.0f}-{eb:.0f} {b} | Actual {a} {aa}-{ab} {b} | {verdict}")
        out["verdict"] = verdict
    # ── Prop slate: full stat-line projections + shot-quality regression edge ──
    slate = [f"# Prop Slate — {GID} ({NSIMS} sims, shot-quality + talent)\n",
             "Projections are simulated DISTRIBUTIONS (p25–p75 = the fair O/U band). "
             "`EDGE` flags where actual PTS diverged from shot-quality expectation — the "
             "regression signal (UNDER-perf → buy next game; OVER-perf → fade).\n",
             "| Player | Tm | PTS proj (p25–p75) | REB (p25–p75) | AST (p25–p75) | PRA (p25–p75) | actual P/R/A | edge |",
             "|---|---|---|---|---|---|---|---|"]
    for pname, r in sorted(results.items(), key=lambda kv: -kv[1]["pra"]["mean"]):
        if r["fga"] < 3 and r["pra"]["mean"] < 8:
            continue
        p, rb, a, pra = r["pts"], r["reb"], r["ast"], r["pra"]
        ap = r["actual_pts"]
        edge = ""
        if ap is not None:
            if ap > p["p90"]:
                edge = "OVER shot-qual (fade)"
            elif ap < p["p10"]:
                edge = "UNDER shot-qual (buy)"
        slate.append(f"| {pname} | {r['team']} | {p['mean']} ({p['p25']}–{p['p75']}) | "
                     f"{rb['mean']} ({rb['p25']}–{rb['p75']}) | {a['mean']} ({a['p25']}–{a['p75']}) | "
                     f"{pra['mean']} ({pra['p25']}–{pra['p75']}) | "
                     f"{ap}/{r['actual_reb']}/{r['actual_ast']} | {edge} |")
    open(f"data/cache/cv_fix/prop_slate_{GID}.md", "w").write("\n".join(slate))
    out["calibration"]["full_line"] = "PTS/REB/AST/PRA simulated; slate written"
    json.dump(out, open(f"data/cache/cv_fix/sim_{GID}.json", "w"), indent=2)
    print(f"wrote data/cache/cv_fix/sim_{GID}.json + prop_slate_{GID}.md")


if __name__ == "__main__":
    main()
