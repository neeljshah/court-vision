"""
cv_fix_predict_oos.py - Out-of-sample predictor for WCF series.
For a target game N, builds projections using ONLY games 1..(N-1).
No leakage from game N or later.

Usage:
    python scripts/cv_fix_predict_oos.py --target 3   # predict G3 using G1+G2
    python scripts/cv_fix_predict_oos.py --target 4   # predict G4 using G1-G3
    python scripts/cv_fix_predict_oos.py --target 5   # predict G5 using G1-G4
    python scripts/cv_fix_predict_oos.py --target 6   # predict G6 using G1-G5
"""
from __future__ import annotations
import argparse, json, os, random
from collections import defaultdict

random.seed(42)

CV = "data/cache/cv_fix"
ALL_GAMES = [
    "0042500311",  # G1
    "0042500312",  # G2
    "0042500313",  # G3
    "0042500314",  # G4
    "0042500315",  # G5
    "0042500316",  # G6
]
GAME_LABELS = {g: f"G{i+1}" for i, g in enumerate(ALL_GAMES)}
GAME_HOME = {
    "0042500311": "OKC", "0042500312": "OKC",
    "0042500313": "SAS", "0042500314": "SAS",
    "0042500315": "OKC", "0042500316": "SAS",
}

HCA_XFG = 1.025
NSIMS = 20000

LEAGUE = {"Restricted Area": 0.625, "In The Paint (Non-RA)": 0.435, "Mid-Range": 0.415,
          "Left Corner 3": 0.385, "Right Corner 3": 0.385, "Above the Break 3": 0.360, "Backcourt": 0.05}
ZPTS = lambda z: 3 if "3" in z else 2


def load(p):
    return json.load(open(p)) if os.path.exists(p) else None


def recency_weight(gi, total):
    if total == 1:
        return 1.0
    return 0.8 + (gi / (total - 1)) * 0.45  # 0.8 to 1.25


def run_prediction(target_game_idx, games):
    prior_games = games[:target_game_idx]
    target_gid = games[target_game_idx]
    n_prior = len(prior_games)
    home_team = GAME_HOME[target_gid]
    away_team = "SAS" if home_team == "OKC" else "OKC"

    print(f"\n--- Predicting {GAME_LABELS[target_gid]} ({target_gid}) ---")
    print(f"    Using {n_prior} prior games: {[GAME_LABELS[g] for g in prior_games]}")
    print(f"    Home: {home_team}")

    pid_name, pid_team = {}, {}
    zone_ct = defaultdict(lambda: defaultdict(float))
    fga_by_game = defaultdict(dict)
    fta_by_game = defaultdict(dict)
    ftm_by_game = defaultdict(dict)
    pts_by_game = defaultdict(dict)
    reb_by_game = defaultdict(dict)
    ast_by_game = defaultdict(dict)
    fgm_tot = defaultdict(float)
    fg3m_tot = defaultdict(float)
    fga_tot = defaultdict(float)
    team_fga_tot = defaultdict(float)
    team_fta_tot = defaultdict(float)
    zone_made = defaultdict(float)
    zone_att = defaultdict(float)

    for gi, g in enumerate(prior_games):
        nd = f"{CV}/nba_{g}"
        w = recency_weight(gi, n_prior)

        sc = load(f"{nd}/shotchart.json") or []
        for s in sc:
            zone_ct[s["PLAYER_ID"]][s["SHOT_ZONE_BASIC"]] += w
            zone_att[s["SHOT_ZONE_BASIC"]] += 1
            zone_made[s["SHOT_ZONE_BASIC"]] += s["SHOT_MADE_FLAG"]

        box = load(f"{nd}/box_traditional.json") or []
        for b in box:
            pid = b.get("personId")
            st = b.get("statistics", b)
            mins = str(st.get("minutes", "0"))
            if mins in ("0", "0:00", "", "PT00M00.00S"):
                continue
            nm = b.get("nameI") or f"{b.get('firstName','')} {b.get('familyName','')}".strip()
            fam = b.get("familyName", "")
            first = b.get("firstName", "")
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

    ZONE_FG_SER = {}
    for z, att in zone_att.items():
        prior = LEAGUE.get(z, 0.40)
        k = 20
        ZONE_FG_SER[z] = (zone_made[z] + k * prior) / (att + k)

    ser_efg = (
        (sum(fgm_tot.values()) + 0.5 * sum(fg3m_tot.values()))
        / max(1, sum(fga_tot.values()))
    )

    def mean_sd(d):
        v = list(d.values())
        if not v:
            return 0.0, 0.0
        m = sum(v) / len(v)
        sd = (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5 if len(v) > 1 else max(1.0, m ** 0.5)
        return m, sd

    pm = {}
    for pid in pid_name:
        if n_prior >= 2 and (n_prior - 1) not in fga_by_game[pid]:
            continue
        zc = zone_ct[pid]
        if not zc:
            continue
        ztot = sum(zc.values())
        zones = list(zc.keys())
        zprob = [zc[z] / ztot for z in zones]
        fga_m, fga_s = mean_sd(fga_by_game[pid])
        if fga_m < 0.5:
            continue
        fta_m, fta_s = mean_sd(fta_by_game[pid])
        ftm_tot_v = sum(ftm_by_game[pid].values())
        fta_tot_v = sum(fta_by_game[pid].values())
        ft_pct = (ftm_tot_v / fta_tot_v) if fta_tot_v else 0.75
        reb_m, reb_s = mean_sd(reb_by_game[pid])
        ast_m, ast_s = mean_sd(ast_by_game[pid])
        att = fga_tot[pid]
        raw_efg = (fgm_tot[pid] + 0.5 * fg3m_tot[pid]) / max(1, att)
        k = 25
        shr_efg = (att * raw_efg + k * ser_efg) / (att + k)
        pers = max(0.85, min(1.20, shr_efg / ser_efg)) if ser_efg else 1.0
        hca = HCA_XFG if pid_team[pid] == home_team else 1.0
        pm[pid] = dict(
            name=pid_name[pid], team=pid_team[pid],
            zones=zones, zprob=zprob,
            fga_m=fga_m, fga_s=fga_s,
            fta_m=fta_m, fta_s=fta_s, ft_pct=ft_pct,
            reb_m=reb_m, reb_s=reb_s,
            ast_m=ast_m, ast_s=ast_s,
            pers=pers, hca=hca,
            gp=len(fga_by_game[pid]),
            pts_series=mean_sd(pts_by_game[pid])[0]
        )

    for team in ("OKC", "SAS"):
        cur_fga = sum(m["fga_m"] for m in pm.values() if m["team"] == team)
        tgt_fga = team_fga_tot[team] / max(1, n_prior)
        sf = (tgt_fga / cur_fga) if cur_fga else 1.0
        cur_fta = sum(m["fta_m"] for m in pm.values() if m["team"] == team)
        tgt_fta = team_fta_tot[team] / max(1, n_prior)
        sft = (tgt_fta / cur_fta) if cur_fta else 1.0
        for m in pm.values():
            if m["team"] == team:
                m["fga_m"] *= sf
                m["fga_s"] *= sf
                m["fta_m"] *= sft
                m["fta_s"] *= sft

    def rnorm(mu, s):
        return max(0, int(round(random.gauss(mu, max(0.5, s)))))

    pts_d = defaultdict(list)
    reb_d = defaultdict(list)
    ast_d = defaultdict(list)
    pra_d = defaultdict(list)
    team_d = defaultdict(list)
    wins = defaultdict(int)

    for _sim in range(NSIMS):
        tot = defaultdict(int)
        for pid, m in pm.items():
            nfga = rnorm(m["fga_m"], m["fga_s"])
            pts = 0
            for _shot in range(nfga):
                z = random.choices(m["zones"], weights=m["zprob"])[0]
                fg_prob = max(0.02, min(0.97, ZONE_FG_SER.get(z, 0.4) * m["pers"] * m["hca"]))
                if random.random() < fg_prob:
                    pts += ZPTS(z)
            nfta = rnorm(m["fta_m"], m["fta_s"])
            for _ft in range(nfta):
                if random.random() < m["ft_pct"]:
                    pts += 1
            rb = rnorm(m["reb_m"], m["reb_s"])
            a = rnorm(m["ast_m"], m["ast_s"])
            pts_d[pid].append(pts)
            reb_d[pid].append(rb)
            ast_d[pid].append(a)
            pra_d[pid].append(pts + rb + a)
            tot[m["team"]] += pts
        for t in ("OKC", "SAS"):
            team_d[t].append(tot[t])
        wins["OKC" if tot["OKC"] >= tot["SAS"] else "SAS"] += 1

    out = {
        "game": GAME_LABELS[target_gid],
        "gid": target_gid,
        "home": home_team,
        "away": away_team,
        "prior_games": [GAME_LABELS[g] for g in prior_games],
        "win_prob": {t: round(100 * wins[t] / NSIMS, 1) for t in ("OKC", "SAS")},
        "team_score": {},
        "players": {}
    }
    for t in ("OKC", "SAS"):
        d = sorted(team_d[t])
        n = len(d)
        out["team_score"][t] = {
            "mean": round(sum(d) / n, 1),
            "p25": d[n // 4], "p50": d[n // 2], "p75": d[3 * n // 4]
        }

    for pid, m in pm.items():
        out["players"][m["name"]] = {
            "team": m["team"],
            "gp_prior": m["gp"],
            "pts_proj": round(sum(pts_d[pid]) / len(pts_d[pid]), 1),
            "reb_proj": round(sum(reb_d[pid]) / len(reb_d[pid]), 1),
            "ast_proj": round(sum(ast_d[pid]) / len(ast_d[pid]), 1),
            "pra_proj": round(sum(pra_d[pid]) / len(pra_d[pid]), 1),
            "pts_dist": pts_d[pid],
            "reb_dist": reb_d[pid],
            "ast_dist": ast_d[pid],
        }

    ts = out["team_score"]
    print(f"    Win prob: OKC {out['win_prob']['OKC']}%  SAS {out['win_prob']['SAS']}%")
    print(f"    Score: OKC {ts['OKC']['mean']} vs SAS {ts['SAS']['mean']}")
    print(f"    Players in sim: {len(pm)}")

    return out


def score_props(pred, props, actuals):
    results = []
    stat_map = {
        "player_points": ("pts_proj", "pts_dist", "points"),
        "player_rebounds": ("reb_proj", "reb_dist", "reboundsTotal"),
        "player_assists": ("ast_proj", "ast_dist", "assists"),
    }

    for player_name, stat_data in props.items():
        pred_player = None
        last_name = player_name.split()[-1].lower()
        for pn in pred["players"]:
            if pn.lower() == player_name.lower():
                pred_player = pn
                break
            if last_name == pn.split()[-1].lower():
                pred_player = pn
                break
        if pred_player is None:
            for pn in pred["players"]:
                if last_name in pn.lower():
                    pred_player = pn
                    break

        if pred_player is None:
            continue

        pd_info = pred["players"][pred_player]

        for stat_key, stat_info in stat_data.items():
            if stat_key not in stat_map:
                continue
            proj_key, dist_key, actual_key = stat_map[stat_key]

            line_data = stat_info.get("fanduel")
            if not line_data:
                keys = list(stat_info.keys())
                if keys:
                    line_data = stat_info[keys[0]]
            if not line_data or "Over" not in line_data:
                continue

            line = line_data["Over"]["point"]
            over_price = line_data["Over"]["price"]
            under_data = line_data.get("Under", {})
            under_price = under_data.get("price", -110) if under_data else -110

            proj = pd_info.get(proj_key)
            dist = pd_info.get(dist_key, [])
            if proj is None or not dist:
                continue

            model_pick = "Over" if proj > line else "Under"
            over_p = sum(1 for x in dist if x > line) / len(dist)

            actual = None
            if player_name in actuals:
                actual = actuals[player_name].get(actual_key)
            if actual is None:
                for an, av in actuals.items():
                    if last_name in an.lower() or an.split()[-1].lower() in player_name.lower():
                        actual = av.get(actual_key)
                        break

            if actual is None:
                print(f"  WARNING: No actual for {player_name} ({stat_key})")
                continue

            actual_result = "Over" if actual > line else "Under"
            correct = (model_pick == actual_result)

            pick_price = over_price if model_pick == "Over" else under_price
            if correct:
                roi = (pick_price / 100.0) if pick_price > 0 else (100.0 / abs(pick_price))
            else:
                roi = -1.0

            results.append({
                "game": pred["game"],
                "gid": pred["gid"],
                "player": player_name,
                "pred_player": pred_player,
                "stat": stat_key,
                "line": line,
                "proj": proj,
                "over_prob": round(over_p, 3),
                "model_pick": model_pick,
                "pick_price": pick_price,
                "actual": actual,
                "actual_result": actual_result,
                "correct": correct,
                "roi": round(roi, 3),
            })

    return results


def load_actuals(gid):
    p = f"{CV}/nba_{gid}/box_traditional.json"
    box = load(p) or []
    actuals = {}
    for b in box:
        nm = b.get("nameI") or f"{b.get('firstName','')} {b.get('familyName','')}".strip()
        fam = b.get("familyName", "")
        first = b.get("firstName", "")
        if nm.startswith("J. Williams") and first:
            nm = f"{first[:4]}. {fam}"
        full_nm = f"{first} {fam}".strip()
        st = b.get("statistics", b)
        mins = str(st.get("minutes", "0"))
        if mins in ("0", "0:00", "", "PT00M00.00S"):
            continue
        data = {
            "points": st.get("points", 0) or 0,
            "reboundsTotal": st.get("reboundsTotal", 0) or 0,
            "assists": st.get("assists", 0) or 0,
        }
        actuals[nm] = data
        actuals[full_nm] = data
    return actuals


def load_actuals_game_level(gid):
    p = f"{CV}/nba_{gid}/box_traditional.json"
    box = load(p) or []
    team_pts = defaultdict(int)
    for b in box:
        st = b.get("statistics", b)
        mins = str(st.get("minutes", "0"))
        if mins in ("0", "0:00", "", "PT00M00.00S"):
            continue
        team = b.get("teamTricode", "")
        team_pts[team] += st.get("points", 0) or 0
    return dict(team_pts)


def score_game_lines(pred, game_lines, team_actuals):
    bk_data = None
    for bk in game_lines.get("bookmakers", []):
        if bk["key"] == "fanduel":
            bk_data = bk
            break
    if not bk_data and game_lines.get("bookmakers"):
        bk_data = game_lines["bookmakers"][0]
    if not bk_data:
        return {}

    h2h = {}
    spreads = {}
    totals = {}
    for mkt in bk_data.get("markets", []):
        if mkt["key"] == "h2h":
            h2h = {o["name"]: o["price"] for o in mkt["outcomes"]}
        elif mkt["key"] == "spreads":
            spreads = {o["name"]: o for o in mkt["outcomes"]}
        elif mkt["key"] == "totals":
            totals = {o["name"]: o for o in mkt["outcomes"]}

    okc_proj = pred["team_score"].get("OKC", {}).get("mean", 0)
    sas_proj = pred["team_score"].get("SAS", {}).get("mean", 0)
    model_total = okc_proj + sas_proj
    model_winner = "OKC" if okc_proj > sas_proj else "SAS"

    actual_okc = team_actuals.get("OKC", 0)
    actual_sas = team_actuals.get("SAS", 0)
    actual_total = actual_okc + actual_sas
    actual_winner = "OKC" if actual_okc > actual_sas else "SAS"

    result = {
        "game": pred["game"],
        "gid": pred["gid"],
        "home": pred["home"],
        "away": pred["away"],
        "model_winner": model_winner,
        "actual_winner": actual_winner,
        "moneyline_correct": model_winner == actual_winner,
        "okc_proj": okc_proj,
        "sas_proj": sas_proj,
        "actual_okc": actual_okc,
        "actual_sas": actual_sas,
        "model_total": round(model_total, 1),
        "actual_total": actual_total,
    }

    if totals:
        line_total = totals["Over"]["point"]
        model_total_pick = "Over" if model_total > line_total else "Under"
        actual_total_result = "Over" if actual_total > line_total else "Under"
        result["total_line"] = line_total
        result["model_total_pick"] = model_total_pick
        result["actual_total_result"] = actual_total_result
        result["total_correct"] = model_total_pick == actual_total_result

    okc_spread_data = None
    sas_spread_data = None
    for name, o in spreads.items():
        if "Oklahoma" in name:
            okc_spread_data = o
        elif "San Antonio" in name:
            sas_spread_data = o

    if okc_spread_data:
        okc_spread = okc_spread_data["point"]
        model_okc_cover = (okc_proj - sas_proj) > (-okc_spread)
        actual_okc_cover = (actual_okc - actual_sas) > (-okc_spread)
        result["ats_okc_spread"] = okc_spread
        result["model_spread_pick"] = "OKC" if model_okc_cover else "SAS"
        result["actual_spread_result"] = "OKC" if actual_okc_cover else "SAS"
        result["ats_correct"] = result["model_spread_pick"] == result["actual_spread_result"]

    return result


def main():
    parser = argparse.ArgumentParser(description="OOS backtest for WCF series")
    parser.add_argument("--target", type=int, choices=[3, 4, 5, 6],
                        help="Target game number. Omit to run all G3-G6.")
    args = parser.parse_args()

    targets = [args.target] if args.target else [3, 4, 5, 6]

    props_all = load("data/cache/cv_fix/player_props.json") or {}
    game_lines_raw = load("data/cache/cv_fix/game_lines.json") or {}

    all_prop_results = []
    all_game_results = []
    predictions = {}
    game_label_map = {3: "G3", 4: "G4", 5: "G5", 6: "G6"}

    for tgt in targets:
        gid = ALL_GAMES[tgt - 1]
        g_label = game_label_map[tgt]

        pred = run_prediction(tgt - 1, ALL_GAMES)
        predictions[g_label] = {
            "gid": gid,
            "home": pred["home"],
            "away": pred["away"],
            "prior_games": pred["prior_games"],
            "win_prob": pred["win_prob"],
            "team_score": pred["team_score"],
            "players": {
                name: {k: v for k, v in info.items() if k not in ("pts_dist", "reb_dist", "ast_dist")}
                for name, info in pred["players"].items()
            }
        }

        actuals = load_actuals(gid)
        team_actuals = load_actuals_game_level(gid)
        print(f"    Actual: OKC {team_actuals.get('OKC', 0)} SAS {team_actuals.get('SAS', 0)}")

        game_props = props_all.get(g_label, {}).get("players", {})
        prop_results = score_props(pred, game_props, actuals)
        all_prop_results.extend(prop_results)
        print(f"    Props scored: {len(prop_results)}")

        gl_entry = game_lines_raw.get(g_label, {})
        game_result = score_game_lines(pred, gl_entry, team_actuals)
        if game_result:
            all_game_results.append(game_result)
            ml_ok = game_result.get("moneyline_correct", False)
            tot_ok = game_result.get("total_correct", False)
            ats_ok = game_result.get("ats_correct", False)
            print(f"    ML: {'WIN' if ml_ok else 'LOSS'}  Total: {'WIN' if tot_ok else 'LOSS'}  ATS: {'WIN' if ats_ok else 'LOSS'}")

    correct = [r for r in all_prop_results if r["correct"]]
    total_props = len(all_prop_results)
    hit_rate = len(correct) / total_props if total_props else 0
    total_roi = sum(r["roi"] for r in all_prop_results) / total_props if total_props else 0

    by_stat = defaultdict(list)
    for r in all_prop_results:
        by_stat[r["stat"]].append(r)
    stat_summary = {}
    for stat, rr in by_stat.items():
        n = len(rr)
        hits = sum(1 for r in rr if r["correct"])
        stat_summary[stat] = {
            "n": n,
            "hits": hits,
            "hit_rate": round(hits / n, 3),
            "roi": round(sum(r["roi"] for r in rr) / n, 3)
        }

    ml_wins = sum(1 for r in all_game_results if r.get("moneyline_correct"))
    tot_wins = sum(1 for r in all_game_results if r.get("total_correct"))
    ats_wins = sum(1 for r in all_game_results if r.get("ats_correct"))
    n_games = len(all_game_results)

    backtest = {
        "description": "WCF 2025-26 Out-of-Sample Backtest (G3-G6)",
        "method": "cv_fix_predict_oos -- trained on prior games only, no leakage",
        "games_tested": targets,
        "props": {
            "total": total_props,
            "hits": len(correct),
            "hit_rate": round(hit_rate, 3),
            "roi_per_bet": round(total_roi, 3),
            "breakeven": 0.524,
            "beats_breakeven": bool(hit_rate > 0.524),
            "by_stat": stat_summary,
        },
        "game_lines": {
            "n_games": n_games,
            "moneyline": {"wins": ml_wins, "pct": round(ml_wins / n_games, 3) if n_games else 0},
            "totals": {"wins": tot_wins, "pct": round(tot_wins / n_games, 3) if n_games else 0},
            "ats": {"wins": ats_wins, "pct": round(ats_wins / n_games, 3) if n_games else 0},
        },
        "detail": {
            "prop_results": all_prop_results,
            "game_results": all_game_results,
        },
        "predictions": predictions,
    }

    out_path = "data/cache/cv_fix/backtest_results.json"
    json.dump(backtest, open(out_path, "w"), indent=2)
    print(f"\nSaved to {out_path}")

    print("\n" + "=" * 70)
    print("OUT-OF-SAMPLE BACKTEST SCORECARD -- WCF G3-G6")
    print("=" * 70)
    print(f"\nPLAYER PROPS (n={total_props}):")
    print(f"  Hit rate:    {hit_rate:.1%}  (break-even: 52.4% at -110)")
    print(f"  ROI/bet:     {total_roi:+.3f} units")
    print(f"  Beat market: {'YES' if hit_rate > 0.524 else 'NO'}")
    print(f"\n  By stat:")
    for stat, ss in stat_summary.items():
        s_short = stat.replace("player_", "")
        print(f"    {s_short:10s}: {ss['hits']}/{ss['n']} = {ss['hit_rate']:.1%}  ROI: {ss['roi']:+.3f}")

    print(f"\nGAME LINES ({n_games} games):")
    if n_games:
        print(f"  Moneyline:   {ml_wins}/{n_games} = {ml_wins/n_games:.1%}")
        print(f"  Totals:      {tot_wins}/{n_games} = {tot_wins/n_games:.1%}")
        print(f"  ATS:         {ats_wins}/{n_games} = {ats_wins/n_games:.1%}")

    print(f"\nVERDICT: ", end="")
    if total_props < 10:
        print("INSUFFICIENT DATA (fewer than 10 props tested)")
    elif hit_rate > 0.524:
        print(f"POSSIBLE EDGE -- {hit_rate:.1%} hit rate BEATS break-even ({total_props} props)")
    else:
        print(f"NO PROVEN EDGE -- {hit_rate:.1%} hit rate at/below break-even ({total_props} props)")

    return backtest


if __name__ == "__main__":
    main()
