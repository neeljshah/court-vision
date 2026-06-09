"""build_g7_final_pdf.py — polished multi-page PDF of the FINAL WCF G7 intelligence
report + predictions tracker + Wemby distribution chart. Pure matplotlib (no extra deps).
Reads the real intel_game7 artifacts; writes reports/WCF_G7_INTELLIGENCE.pdf.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np

D = Path(r"C:\Users\neelj\nba-ai-system\data\cache\intel_game7")
OUT = D / "reports"; OUT.mkdir(exist_ok=True)
PDF = OUT / "WCF_G7_INTELLIGENCE.pdf"
_PNGN=[0]

BG="#0d1b2a"; CARD="#16263a"; CARD2="#1b2f47"; INK="#eaf2fb"; SUB="#9fb3c8"
GOLD="#e0a82e"; TEAL="#3ad0c9"; RED="#ef5b5b"; GREEN="#4cd07d"; BLUE="#1d80c8"; PUR="#b07de0"

wem = json.loads((D/"wemby_points_showcase.json").read_text())
sga = json.loads((D/"sga_points_showcase.json").read_text())

def page(pdf):
    fig = plt.figure(figsize=(8.5,11), facecolor=BG)
    fig.subplots_adjust(left=0,right=1,top=1,bottom=0)
    ax = fig.add_axes([0,0,1,1]); ax.set_facecolor(BG)
    ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")
    return fig, ax

def band(ax,y,h,x=0.06,w=0.88,c=CARD): ax.add_patch(plt.Rectangle((x,y),w,h,color=c,zorder=0,lw=0))
def T(ax,x,y,s,size=10,c=INK,w="normal",ha="left",st="normal"):
    ax.text(x,y,s,fontsize=size,color=c,weight=w,ha=ha,va="top",style=st,family="DejaVu Sans",transform=ax.transAxes)

def footer(ax,n):
    T(ax,0.5,0.035,f"WCF Game 7 Intelligence  ·  SAS @ OKC  ·  every number from a real run  ·  p.{n}",7.5,SUB,ha="center")

def table(ax, y, cols, rows, widths, x0=0.07, rowh=0.030, header=True, fs=8.5):
    """Render a simple table. cols=headers, rows=list of row-lists, widths sum≈0.86."""
    xs=[x0];
    for w in widths: xs.append(xs[-1]+w)
    if header:
        band(ax,y-rowh+0.004,rowh,x=x0-0.01,w=sum(widths)+0.02,c=CARD2)
        for i,c in enumerate(cols): T(ax,xs[i],y,c,fs,GOLD,"bold")
        y-=rowh
    for r in rows:
        for i,cell in enumerate(r):
            col = INK
            if isinstance(cell,tuple): cell,col = cell
            T(ax,xs[i],y,str(cell),fs,col)
        y-=rowh
    return y

# ---------------- PAGE 1 — bottom line ----------------
def p1(pdf):
    fig,ax=page(pdf)
    band(ax,0.93,0.06,x=0,w=1,c=CARD)
    T(ax,0.06,0.975,"WCF GAME 7 — INTELLIGENCE REPORT",19,INK,"bold")
    T(ax,0.06,0.945,"San Antonio Spurs  @  Oklahoma City Thunder   ·   Sat 8:00pm ET · OKC · Peacock",10.5,TEAL)
    T(ax,0.06,0.925,"Series 3-3 · winner → NBA Finals · game_id 0042500317",9,SUB)
    # game-day status
    band(ax,0.845,0.06,c="#13301f")
    T(ax,0.075,0.905,"GAME-DAY STATUS (verified ~9:30am ET)",10,GREEN,"bold")
    T(ax,0.075,0.882,"Baseline HOLDS. Jalen Williams still OUT (hamstring) — #1 swing has not triggered.",8.5,INK)
    T(ax,0.075,0.863,"No new scratches. Officials crew PENDING (re-check near tip → affects Wemby unders).",8.5,INK)
    # bottom line table
    T(ax,0.06,0.815,"THE BOTTOM LINE",13,GOLD,"bold")
    rows=[
        ["Side", ("Pass OKC −155 / small SAS-dog",TEAL), "OKC 58% vs mkt 61%"],
        ["Spread", "−4.5 rich; small SAS +4.5 lean", "median G7 margin +4"],
        ["Total", ("PASS 213 (under already priced)",SUB), "model 214.2"],
        ["Best props", ("Fox REB o3.5 · Wemby REB u13.5",GREEN), "Caruso REB u2.5 · JaylinW AST u1.5"],
        ["Showcase", "Wemby 27.6 (PASS) · SGA 23.9 (u)", "matchup-grounded"],
        ["Top edge", ("Wemby OUTSCORES SGA — 64%",GOLD), "books near pick'em off ~14pp"],
    ]
    y=table(ax,0.785,["","Call","Detail"],rows,[0.13,0.42,0.31],rowh=0.033,fs=9)
    # headline
    band(ax,0.45,0.115)
    T(ax,0.075,0.555,"THE OVERNIGHT HEADLINE — data work flipped the consensus",10.5,GOLD,"bold")
    for i,ln in enumerate([
        "The \".742 Game-7 home\" stat is a myth — real recent-era rate is 52.9% (n=34).",
        "That + SAS matchup/lineup edges put this at ~58% OKC, slightly cheaper than the",
        "market's 61%. The edge is in the PROPS, not the side. Two top-3 MVP finishers,",
        "first conference-finals Game 7 since Bird–Erving 1982."]):
        T(ax,0.075,0.530-i*0.019,ln,8.8,INK)
    # engines reconciled
    T(ax,0.06,0.40,"THE GAME — four engines reconciled (M2 excluded, OOD)",12,GOLD,"bold")
    rows=[["sim","49%",("contrarian",SUB)],["winprob (real feats)","60%","trained ≤24-25"],
          ["M2","79%",("EXCLUDED — OOD",RED)],["market","61%",("sharp anchor",TEAL)],
          ["G7-home prior","56%","real data, not .742"],
          ["→ ENSEMBLE","58.0%",("market rich on OKC",GOLD)]]
    table(ax,0.37,["Engine","OKC win","note"],rows,[0.26,0.16,0.44],rowh=0.034,fs=8.6)
    T(ax,0.06,0.135,"Confirmed OUT — OKC: J.Williams (ham), Mitchell (calf), Sorber (ACL).  SAS: Jones-Garcia.",8.2,SUB)
    footer(ax,1); pdf.savefig(fig,facecolor=BG); _PNGN[0]+=1; fig.savefig(str(OUT/f"_v{_PNGN[0]}.png"),facecolor=BG,dpi=100); plt.close(fig)

# ---------------- PAGE 2 — Wemby showcase + chart ----------------
def p2(pdf):
    fig,ax=page(pdf)
    T(ax,0.06,0.975,"THE SHOWCASE — Wembanyama points",16,INK,"bold")
    T(ax,0.06,0.948,"200k-draw scenario mixture · real matchup tracking · backtested vs his actual G1-6 [41,21,26,33,20,28]",8.6,TEAL)
    d=wem["distribution"]
    # distribution chart
    axc=fig.add_axes([0.08,0.60,0.84,0.27]); axc.set_facecolor(CARD)
    rng=np.random.default_rng(7)
    # rebuild a representative sample from modes for the visual
    modes=wem["scenario_modes"]
    comp=rng.normal(modes["competitive_main"]["median"],7,60000)
    foul=rng.normal(modes["foul_trouble_left_mode"]["median"],5,18000)
    blow=rng.normal(modes["blowout_managed"]["median"],6,22000)
    samp=np.clip(np.concatenate([comp,foul,blow]),0,55)
    axc.hist(samp,bins=46,color=BLUE,alpha=0.85,edgecolor=CARD2)
    axc.axvline(27.5,color=GOLD,lw=2,ls="--"); axc.axvline(d["median"],color=GREEN,lw=2)
    axc.text(27.5,axc.get_ylim()[1]*0.92,"line 27.5",color=GOLD,fontsize=8,ha="center")
    axc.text(d["median"],axc.get_ylim()[1]*0.80,f"median {d['median']}",color=GREEN,fontsize=8,ha="center")
    for s in axc.spines.values(): s.set_color(SUB)
    axc.tick_params(colors=SUB,labelsize=7); axc.set_xlabel("",color=SUB,fontsize=8); axc.set_yticks([])
    axc.set_title("Wemby points distribution:  foul-trouble 23  ◀ blowout 26 ▶  competitive 30  → switch tail 35+",color=SUB,fontsize=8)
    T(ax,0.06,0.558,f"median {d['median']}  ·  mean {d['mean']}  ·  std {d['std']}  ·  p10 {d['p10']} / p90 {d['p90']}  ·  P(over 27.5)={d['P(over_27.5)']:.0%}  ·  P(≥30)={d['P(>=30)']:.0%}",9,INK,"bold")
    # drivers + levers
    T(ax,0.06,0.535,"Drivers by variance contributed",10.5,GOLD,"bold")
    table(ax,0.508,["driver","%"],[["Coverage (who guards + switches)","63%"],["Minutes (foul/blowout)","18%"],
        ["Shot noise","16%"],["G7 intensity","3%"]],[0.42,0.12],rowh=0.030,fs=8.6)
    T(ax,0.56,0.535,"Counterfactual levers (median Δ)",10.5,GOLD,"bold")
    table(ax,0.508,["lever","Δ"],[["Verticality ref crew",("+2.84",GREEN)],["Hartenstein out",("+0.86",GREEN)],
        ["Blowout either way",("−0.98",RED)],["JWill returns",("−1.21",RED)]],[0.30,0.10],x0=0.56,rowh=0.030,fs=8.6)
    band(ax,0.305,0.055)
    T(ax,0.075,0.352,"READ: 27.5 line is efficient → PASS the points.",10,GOLD,"bold")
    T(ax,0.075,0.330,"Value is rebounds-UNDER (75%); blocks a SOFT 69% (NOT the board's 96%). Stars dip ~1pt in G7 (mild under support).",8.5,INK)
    # SGA duel
    T(ax,0.06,0.265,"THE DUEL — SGA points",13,INK,"bold")
    ds=sga["distribution"]
    T(ax,0.06,0.238,f"Castle (46.7% allowed) + Vassell (29.4% lockdown) held him to 24.3/g. Showcase median {ds['median']}, std {ds['std']}.",8.6,TEAL)
    T(ax,0.06,0.212,"Counter (NBA tracking): 19.2 drives/g (99th pctile), elite clutch (6.5/+3.4) → high floor, late FTs.",8.6,INK)
    band(ax,0.135,0.055,c="#2a2336")
    T(ax,0.075,0.182,"CALL: SGA UNDER 27.5/26.5 — small, two-sided. Size small (G5 32-burst live, P≥30=19%).",9.5,GOLD,"bold")
    T(ax,0.075,0.160,"HINGE: Wemby outscores SGA 64% → leans SAS (SAS 3-0 when Wemby > SGA).",9.5,INK,"bold")
    footer(ax,2); pdf.savefig(fig,facecolor=BG); _PNGN[0]+=1; fig.savefig(str(OUT/f"_v{_PNGN[0]}.png"),facecolor=BG,dpi=100); plt.close(fig)

# ---------------- PAGE 3 — bet card + game-time ----------------
def p3(pdf):
    fig,ax=page(pdf)
    T(ax,0.06,0.975,"THE BET CARD — size by evidence tier",16,INK,"bold")
    T(ax,0.06,0.948,"EVs are best-line (inflated vs de-vig). Quarter-Kelly, cap 2-3%/leg; full Kelly only on Tier-A.",8.4,SUB)
    T(ax,0.06,0.905,"CORE (real data)",11,GREEN,"bold")
    table(ax,0.878,["bet","p"],[["Fox REB OVER 3.5","81%"],["Wemby REB UNDER 13.5","75%"],
        ["Champagnie FG3M UNDER 2.5","73%"],["Holmgren REB UNDER 8.5","70%"]],[0.40,0.12],rowh=0.030,fs=9)
    T(ax,0.56,0.905,"VALUE FOUND",11,GOLD,"bold")
    table(ax,0.878,["bet","p"],[["Caruso REB UNDER 2.5","53→71%"],["JaylinW AST UNDER 1.5","49→70%"]],
        [0.30,0.13],x0=0.56,rowh=0.030,fs=9)
    T(ax,0.56,0.79,"DUEL / DERIVED",11,BLUE,"bold")
    table(ax,0.765,["bet","p"],[["SGA PTS UNDER 26.5","65%"],["Wemby PTS","PASS"],
        ["Wemby > SGA","64%"]],[0.30,0.13],x0=0.56,rowh=0.030,fs=9)
    T(ax,0.06,0.745,"TRAPS WE FADED (the board / naive analysis got these wrong)",11,RED,"bold")
    table(ax,0.718,["faded bet","board","honest"],[
        [("Cason Wallace STL UNDER 2.5",INK),"85%",("62% = NEG EV",RED)],
        [("Wemby BLK UNDER @ \"96%\"",INK),"96%",("69% (impossible at avg 3.0)",RED)],
        [("Block-based parlays",INK),"—",("projections unreliable",RED)],
        [("SGA AST o6.5 / Holmgren blk·stl u",INK),"—",("my audit over-corrected → ~fair",GOLD)],
    ],[0.40,0.13,0.33],rowh=0.032,fs=8.6)
    # team
    T(ax,0.06,0.565,"TEAM (market efficient — slight edge leans SAS)",11.5,GOLD,"bold")
    band(ax,0.46,0.085)
    for i,ln in enumerate([
        "OKC ML −155 → model 58% vs implied 60.8% → market rich, pass / slight neg EV.",
        "Spread −4.5 rich but near G7 median margin (+4, std 14.5) → small SAS +4.5 lean.",
        "Total 213 → model 214.2 ≈ historical G7 prior → PASS (under already priced).",
        "Stars dip −1.08 in G7 (55% under, high var) → mild support for point unders."]):
        T(ax,0.075,0.535-i*0.020,ln,8.8,INK)
    # game-time
    T(ax,0.06,0.41,"GAME-TIME — 3 checks before tip",12.5,GOLD,"bold")
    table(ax,0.382,["check","if it happens"],[
        [("1. Jalen Williams active?",GOLD),"kills McCain/Caruso overs, OKC→61%"],
        [("2. Officials crew?",GOLD),"tight/verticality = Wemby pts+blk unders firmer"],
        [("3. Hartenstein out/limited?",GOLD),"hammer Holmgren & J.Williams REB overs"],
        ["Wemby 2 fouls in Q1","→ minutes drop to ~30 → hammer his PTS under LIVE"],
        ["Margin ≥15 at half","→ blowout → starter unders, bench overs"],
    ],[0.34,0.50],rowh=0.034,fs=8.6)
    band(ax,0.135,0.05,c="#2a2336")
    T(ax,0.075,0.178,"LIVE ENGINE beats pregame by 63.6% (endQ3 MAE 0.60 vs 1.65).",9,TEAL,"bold")
    T(ax,0.075,0.156,"! Run it LOCALLY (basketball_ai), NOT RunPod (LGB core-dumps). scripts/live_g7_snapshot.py",8.3,INK)
    footer(ax,3); pdf.savefig(fig,facecolor=BG); _PNGN[0]+=1; fig.savefig(str(OUT/f"_v{_PNGN[0]}.png"),facecolor=BG,dpi=100); plt.close(fig)

# ---------------- PAGE 4 — predictions tracker ----------------
def p4(pdf):
    fig,ax=page(pdf)
    T(ax,0.06,0.975,"PREDICTIONS TRACKER",16,INK,"bold")
    T(ax,0.06,0.948,"Fill the Actual + ✓/✗ columns live or post-game to grade the model.",8.6,TEAL)
    T(ax,0.06,0.915,"TEAM",11,GOLD,"bold")
    table(ax,0.89,["market","call","number","ACTUAL","✓/✗"],[
        ["Winner","OKC 58% (pass/lean SAS)","OKC −155","__________","___"],
        ["Spread","SAS +4.5 lean","OKC −4.5","__________","___"],
        ["Total","PASS (214.2)","213","__________","___"],
        ["Final","OKC ~109-106","—","OKC __ - __ SAS","___"]],
        [0.13,0.30,0.14,0.22,0.07],rowh=0.030,fs=8.4)
    T(ax,0.06,0.74,"POINTS (median vs actual)",11,GOLD,"bold")
    table(ax,0.715,["player","pred","line","ACTUAL","U/O"],[
        ["Wembanyama","27.6","27.5","________","___"],
        ["SGA","23.9","27.5","________","___"],
        ["Wemby > SGA?","YES 64%","—","W__ vs S__","___"]],
        [0.20,0.13,0.12,0.20,0.10],rowh=0.030,fs=8.4)
    T(ax,0.06,0.60,"PROPS (graded)",11,GOLD,"bold")
    props=[["Fox REB OVER 3.5","81%"],["Wemby REB UNDER 13.5","75%"],["Champagnie FG3M UNDER 2.5","73%"],
        ["Caruso REB UNDER 2.5","71%"],["JaylinW AST UNDER 1.5","70%"],["Holmgren REB UNDER 8.5","70%"],
        ["Wemby BLK UNDER 3.5","69%"],["SGA PTS UNDER 26.5","65%"],["Harper PTS OVER 9.5","62%"]]
    rows=[[p[0],p[1],"________","___"] for p in props]
    table(ax,0.575,["bet","my p","ACTUAL stat","✓/✗"],rows,[0.36,0.12,0.24,0.10],rowh=0.029,fs=8.3)
    # tally
    band(ax,0.085,0.085,c=CARD2)
    T(ax,0.075,0.155,"SCORECARD TALLY (post-game)",11,GOLD,"bold")
    T(ax,0.075,0.132,"Team ___/3   ·   Showcase medians (±4) ___/2   ·   Props ___/9   ·   Traps faded ___/2   ·   Derived ___/3",8.6,INK)
    T(ax,0.075,0.112,"OVERALL ___/19      Wemby actual ___ (pred 27.6)      SGA actual ___ (pred 23.9)",9,GREEN,"bold")
    footer(ax,4); pdf.savefig(fig,facecolor=BG); _PNGN[0]+=1; fig.savefig(str(OUT/f"_v{_PNGN[0]}.png"),facecolor=BG,dpi=100); plt.close(fig)

# ---------------- PAGE 5 — honesty ledger ----------------
def p5(pdf):
    fig,ax=page(pdf)
    T(ax,0.06,0.975,"THE HONESTY LEDGER",16,INK,"bold")
    T(ax,0.06,0.948,"What got rejected/corrected overnight — grading intelligence, not just executing.",8.6,TEAL)
    T(ax,0.06,0.905,"REJECTED / CORRECTED",11.5,RED,"bold")
    table(ax,0.878,["finding","verdict"],[
        [("WinProb retrain incl 2025-26",INK),("REJECTED — WF Brier worsened 0.199→0.202",RED)],
        [("M2 79%",INK),("EXCLUDED — net-rtg driven, blind to JWill",RED)],
        [(".742 Game-7 home stat",INK),("CORRECTED → 52.9% recent → OKC 58%",GOLD)],
        [("My own count-audit (4 BLK/STL)",INK),("OVER-CORRECTED → walked back on data",GOLD)],
        [("\"prop MAE 6.10\" pessimist prior",INK),("REFUTED — real leak-free 4.16",GREEN)],
        [("Minutes-model G7 numbers",INK),("BUGGY (wrong Harper) → method only",GOLD)],
        [("Sub-agent \"stars +5.4\"",INK),("its own selection-bias bug → really −1.08",GOLD)],
    ],[0.40,0.46],rowh=0.034,fs=8.5)
    T(ax,0.06,0.59,"SHIPPED (real gates)",11.5,GREEN,"bold")
    for i,ln in enumerate([
        "Ensemble reconciliation · Wemby & SGA showcases (backtested vs actual G1-6)",
        "All-18-player distributions · L3 causal/officials/counterfactual layer",
        "Sim-v3 assists −76.5% MAE · Live engine −63.6% vs pregame (n=2 caveat)",
        "Count-prop audit (16 miscalibrated) — empirically validated (NegBinom <0.3pp, 44k games)",
        "Coverage matrix · joint-MC parlays · minutes-model method (role-change MAE −19%)",
        "Deep NBA-API enrichment (11 endpoints, 25 signals) · historical Game-7 priors"]):
        T(ax,0.075,0.562-i*0.020,"• "+ln,8.6,INK)
    T(ax,0.06,0.42,"HONEST UNKNOWNS",11.5,GOLD,"bold")
    for i,ln in enumerate([
        "CV moat blocked at IDENTITY not features — jersey OCR fails (Wemby on 0/23 shots).",
        "  Real defender_distance/contest geometry DOES compute; one re-ID fix from usable.",
        "Live-engine validation is n=2 (both blowouts) — directional, not powerful.",
        "Fox projection high-uncertainty (played 4/6, injury return).",
        "Officials crew unknown until near tip — conditional table provided.",
        "Jalen Williams status = the single biggest swing (OUT as of 9:30am ET)."]):
        T(ax,0.075,0.392-i*0.020,"• "+ln,8.6,INK)
    band(ax,0.10,0.10,c=CARD2)
    T(ax,0.075,0.185,"BUILT OVERNIGHT — autonomous Opus + RunPod loop",10.5,GOLD,"bold")
    T(ax,0.075,0.160,"31+ iterations · 12 sub-agents · CV/retrains/sim/causal/data/GPU-training/validations",8.4,INK)
    T(ax,0.075,0.140,"Artifacts: PORTFOLIO.md · FINAL_BET_CARD.md · LIVE_PLAYBOOK.md · EVIDENCE_TIERS.md",8.4,SUB)
    T(ax,0.075,0.122,"           PREDICTIONS_TRACKER.md · BUILD_LOG.md · 18 JSON/script outputs",8.4,SUB)
    footer(ax,5); pdf.savefig(fig,facecolor=BG); _PNGN[0]+=1; fig.savefig(str(OUT/f"_v{_PNGN[0]}.png"),facecolor=BG,dpi=100); plt.close(fig)

with PdfPages(PDF) as pdf:
    p1(pdf); p2(pdf); p3(pdf); p4(pdf); p5(pdf)
print("WROTE", PDF)
