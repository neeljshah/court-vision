# cv_fix_predict_g7_v2.py - WCF G7 prediction with season-prior blend + G7 pace factor
# Usage: JWILL=out K=10 python3 scripts/cv_fix_predict_g7_v2.py
from __future__ import annotations
import json, os, random
from collections import defaultdict

random.seed(7)
CV = "data/cache/cv_fix"
GAMES = ["0042500311","0042500312","0042500313","0042500314","0042500315","0042500316"]
HOME_G7 = "OKC"; HCA_XFG = 1.025; NSIMS = 20000
RECENCY = {0:0.8,1:0.85,2:0.9,3:1.0,4:1.1,5:1.25}
ZPTS = lambda z: 3 if "3" in z else 2
# G7 pace/efficiency discount: series avg ~223 total, market 212.5 (-4.7%)
GAME7_PACE_FACTOR = 0.962
K_BLEND = int(os.environ.get("K", "10"))

def load(p): return json.load(open(p)) if os.path.exists(p) else None
def mean_sd(d):
    v=list(d.values())
    if not v: return 0.0,0.0
    m=sum(v)/len(v); sd=(sum((x-m)**2 for x in v)/len(v))**0.5 if len(v)>1 else max(1.0,m**0.5)
    return m,sd
def rnorm(m,s): return max(0,int(round(random.gauss(m,max(0.5,s)))))
def pc(a):
    a=sorted(a); n=len(a)
    return dict(mean=round(sum(a)/n,1),p25=a[n//4],p50=a[n//2],p75=a[3*n//4],p10=a[n//10],p90=a[9*n//10])

def main():
    season={int(pid):v for pid,v in (load(f"{CV}/season_stats.json") or {}).items()}
    pid_name,pid_team={},{}
    zone_ct=defaultdict(lambda: defaultdict(float))
    fga_by_game=defaultdict(dict); fta_by_game=defaultdict(dict)
    ftm_by_game=defaultdict(dict); pts_by_game=defaultdict(dict)
    reb_by_game=defaultdict(dict); ast_by_game=defaultdict(dict)
    fgm_tot=defaultdict(float); fg3m_tot=defaultdict(float); fga_tot=defaultdict(float)
    team_fga_tot=defaultdict(float); team_fta_tot=defaultdict(float)
    zone_made=defaultdict(float); zone_att=defaultdict(float)
    for gi,g in enumerate(GAMES):
        nd=f"{CV}/nba_{g}"; w=RECENCY[gi]
        for s in (load(f"{nd}/shotchart.json") or []):
            zone_ct[s["PLAYER_ID"]][s["SHOT_ZONE_BASIC"]]+=w
            zone_att[s["SHOT_ZONE_BASIC"]]+=1
            zone_made[s["SHOT_ZONE_BASIC"]]+=s["SHOT_MADE_FLAG"]
        for b in (load(f"{nd}/box_traditional.json") or []):
            pid=b.get("personId"); st=b.get("statistics",b)
            if str(st.get("minutes","0")) in ("0","0:00","","PT00M00.00S"): continue
            nm=b.get("nameI") or (b.get("firstName","")+" "+b.get("familyName","")).strip()
            if nm.startswith("J. Williams") and b.get("firstName"):
                nm=b["firstName"][:4]+". "+b["familyName"]
            pid_name[pid]=nm; pid_team[pid]=b.get("teamTricode","")
            fga_by_game[pid][gi]=st.get("fieldGoalsAttempted",0) or 0
            fta_by_game[pid][gi]=st.get("freeThrowsAttempted",0) or 0
            ftm_by_game[pid][gi]=st.get("freeThrowsMade",0) or 0
            pts_by_game[pid][gi]=st.get("points",0) or 0
            reb_by_game[pid][gi]=st.get("reboundsTotal",0) or 0
            ast_by_game[pid][gi]=st.get("assists",0) or 0
            fgm_tot[pid]+=st.get("fieldGoalsMade",0) or 0
            fg3m_tot[pid]+=st.get("threePointersMade",0) or 0
            fga_tot[pid]+=st.get("fieldGoalsAttempted",0) or 0
            team_fga_tot[pid_team[pid]]+=st.get("fieldGoalsAttempted",0) or 0
            team_fta_tot[pid_team[pid]]+=st.get("freeThrowsAttempted",0) or 0
    JWILL=os.environ.get("JWILL","blend"); JW=1631114
    if JWILL=="healthy":
        for d in (fga_by_game,fta_by_game,ftm_by_game,pts_by_game,reb_by_game,ast_by_game):
            if JW in d and 0 in d[JW]: d[JW]={0:d[JW][0]}
    LEAGUE={"Restricted Area":0.625,"In The Paint (Non-RA)":0.435,"Mid-Range":0.415,
            "Left Corner 3":0.385,"Right Corner 3":0.385,"Above the Break 3":0.360,"Backcourt":0.05}
    ZONE_FG_SER={}
    for z,att in zone_att.items(): ZONE_FG_SER[z]=(zone_made[z]+20*LEAGUE.get(z,0.40))/(att+20)
    ser_efg=(sum(fgm_tot.values())+0.5*sum(fg3m_tot.values()))/max(1,sum(fga_tot.values()))
    pm={}
    for pid in pid_name:
        if not({4,5}&set(fga_by_game[pid].keys())): continue
        if JWILL=="out" and pid==JW: continue
        zc=zone_ct[pid]
        if not zc: continue
        ztot=sum(zc.values()); zones=list(zc.keys()); zprob=[zc[z]/ztot for z in zones]
        n_g=len(fga_by_game[pid])
        fga_m_raw,fga_s=mean_sd(fga_by_game[pid]); fta_m_raw,fta_s=mean_sd(fta_by_game[pid])
        if fga_m_raw<1: continue
        ftm_tot_p=sum(ftm_by_game[pid].values()); fta_tot_p=sum(fta_by_game[pid].values())
        ft_pct=(ftm_tot_p/fta_tot_p) if fta_tot_p else 0.75
        reb_m_raw,reb_s=mean_sd(reb_by_game[pid]); ast_m_raw,ast_s=mean_sd(ast_by_game[pid])
        pts_vals=list(pts_by_game[pid].values())
        pts_series_m=sum(pts_vals)/len(pts_vals) if pts_vals else 0.0
        s=season.get(pid); has_s=s is not None and s.get("gp",0)>=10
        if has_s:
            reb_m=(n_g*reb_m_raw+K_BLEND*s["reb"])/(n_g+K_BLEND)
            ast_m=(n_g*ast_m_raw+K_BLEND*s["ast"])/(n_g+K_BLEND)
            ser_fg_pct=fgm_tot[pid]/max(1,fga_tot[pid])
            pts_per_fga=ser_fg_pct*2.0*(1+0.5*fg3m_tot[pid]/max(1,fgm_tot[pid]))
            season_fga_impl=max(0.5,(s["pts"]-fta_m_raw*ft_pct)/max(0.5,pts_per_fga))
            fga_m=(n_g*fga_m_raw+K_BLEND*season_fga_impl)/(n_g+K_BLEND)
        else:
            reb_m=reb_m_raw; ast_m=ast_m_raw; fga_m=fga_m_raw
        att_p=fga_tot[pid]; raw_efg=(fgm_tot[pid]+0.5*fg3m_tot[pid])/max(1,att_p)
        shr_efg=(att_p*raw_efg+25*ser_efg)/(att_p+25)
        pers=max(0.85,min(1.20,shr_efg/ser_efg)) if ser_efg else 1.0
        hca=HCA_XFG if pid_team[pid]==HOME_G7 else 1.0
        if pid_team[pid]=="OKC": hca*={"healthy":1.03,"out":0.99}.get(JWILL,1.01)
        pm[pid]=dict(name=pid_name[pid],team=pid_team[pid],zones=zones,zprob=zprob,
                     fga_m=fga_m,fga_s=fga_s,fta_m=fta_m_raw,fta_s=fta_s,ft_pct=ft_pct,
                     reb_m=reb_m,reb_s=reb_s,ast_m=ast_m,ast_s=ast_s,pers=pers,hca=hca,
                     gp=n_g,pts_series=pts_series_m,reb_series=reb_m_raw,ast_series=ast_m_raw,
                     pts_season=s["pts"] if has_s else None,reb_season=s["reb"] if has_s else None,
                     ast_season=s["ast"] if has_s else None)
    for team in ("OKC","SAS"):
        cf=sum(m["fga_m"] for m in pm.values() if m["team"]==team)
        tf=team_fga_tot[team]/len(GAMES); sf=(tf/cf) if cf else 1.0
        cft=sum(m["fta_m"] for m in pm.values() if m["team"]==team)
        tft=team_fta_tot[team]/len(GAMES); sft=(tft/cft) if cft else 1.0
        for m in pm.values():
            if m["team"]==team: m["fga_m"]*=sf;m["fga_s"]*=sf;m["fta_m"]*=sft;m["fta_s"]*=sft
    for m in pm.values():
        m["fga_m"]*=GAME7_PACE_FACTOR; m["fga_s"]*=GAME7_PACE_FACTOR
        m["fta_m"]*=GAME7_PACE_FACTOR; m["fta_s"]*=GAME7_PACE_FACTOR
    pts_d=defaultdict(list);reb_d=defaultdict(list);ast_d=defaultdict(list);pra_d=defaultdict(list)
    team_d=defaultdict(list);wins=defaultdict(int)
    for _ in range(NSIMS):
        tot=defaultdict(int)
        for pid,m in pm.items():
            nfga=rnorm(m["fga_m"],m["fga_s"]); pts=0
            for _ in range(nfga):
                z=random.choices(m["zones"],weights=m["zprob"])[0]
                if random.random()<max(0.02,min(0.97,ZONE_FG_SER.get(z,0.4)*m["pers"]*m["hca"])): pts+=ZPTS(z)
            nfta=rnorm(m["fta_m"],m["fta_s"])
            for _ in range(nfta):
                if random.random()<m["ft_pct"]: pts+=1
            rb=rnorm(m["reb_m"],m["reb_s"]); a=rnorm(m["ast_m"],m["ast_s"])
            pts_d[pid].append(pts);reb_d[pid].append(rb);ast_d[pid].append(a);pra_d[pid].append(pts+rb+a)
            tot[m["team"]]+=pts
        for t in ("OKC","SAS"): team_d[t].append(tot[t])
        wins["OKC" if tot["OKC"]>=tot["SAS"] else "SAS"]+=1
    out={"game":"0042500317","home":HOME_G7,"series":"3-3",
         "model_version":"v2_season_blend","k_blend":K_BLEND,"game7_pace_factor":GAME7_PACE_FACTOR,
         "win_prob":{t:round(100*wins[t]/NSIMS,1) for t in ("OKC","SAS")},
         "team_score":{t:pc(team_d[t]) for t in ("OKC","SAS")},"players":{}}
    for pid,m in pm.items():
        out["players"][m["name"]]={"team":m["team"],"gp":m["gp"],
            "pts":pc(pts_d[pid]),"reb":pc(reb_d[pid]),"ast":pc(ast_d[pid]),"pra":pc(pra_d[pid]),
            "series_ppg":round(m["pts_series"],1),"season_pts":m.get("pts_season"),
            "season_reb":m.get("reb_season"),"season_ast":m.get("ast_season"),
            "series_reb":round(m["reb_series"],1),"series_ast":round(m["ast_series"],1),
            "form_mult":round(m["pers"],3)}
    json.dump(out,open(f"{CV}/predict_g7.json","w"),indent=2)
    ts=out["team_score"]; total=round(ts["OKC"]["mean"]+ts["SAS"]["mean"],1)
    print("="*72)
    print(f"WCF GAME 7 v2  K={K_BLEND}  G7-factor={GAME7_PACE_FACTOR}")
    print("="*72)
    okc_wp=out["win_prob"]["OKC"]; sas_wp=out["win_prob"]["SAS"]
    print(f"WIN PROB: OKC {okc_wp}%  SAS {sas_wp}%")
    print(f"SCORE OKC {ts[chr(79)+chr(75)+chr(67)][chr(109)+chr(101)+chr(97)+chr(110)]} SAS {ts[chr(83)+chr(65)+chr(83)][chr(109)+chr(101)+chr(97)+chr(110)]}")
    print(f"TOTAL: {total}  (market: 212.5)")
    print()
    print("Player                   Tm GP  SerPTS  SeaPTS  ProjPTS  ProjREB  ProjAST")
    for pid,m in sorted(pm.items(),key=lambda kv:-out["players"][kv[1]["name"]]["pra"]["mean"]):
        r=out["players"][m["name"]]
        if r["pra"]["mean"]<4: continue
        nm2=m["name"]; tm2=m["team"]; gp2=r["gp"]
        sp_str=f"{r[chr(115)+chr(101)+chr(97)+chr(115)+chr(111)+chr(110)+chr(95)+chr(112)+chr(116)+chr(115)]:.1f}" if r["season_pts"] else "---"
        pm2=r["pts"]["mean"]; pp25=r["pts"]["p25"]; pp75=r["pts"]["p75"]
        rm2=r["reb"]["mean"]; am2=r["ast"]["mean"]
        sp2=r["series_ppg"]
        print(f"{nm2:24s} {tm2:3s} {gp2:>2d}  {sp2:>5.1f}   {sp_str:>5s}  {pm2:>5.1f}({pp25:2d}-{pp75:2d})  {rm2:>4.1f}  {am2:>4.1f}")
    print("wrote "+CV+"/predict_g7.json")

if __name__=="__main__": main()
